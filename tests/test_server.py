from __future__ import annotations

import inspect
import sys
import types
from typing import Any

from datetime import date

from gamedai_mcp.server import (
    build_arg_parser,
    build_mcp_server,
    latest_complete_nfl_season,
)


class FakeFastMCP:
    def __init__(self, name: str, **settings: Any) -> None:
        self.name = name
        self.settings = settings
        self.routes: list[dict[str, Any]] = []
        self.tools: list[str] = []
        self.tool_functions: dict[str, Any] = {}

    def custom_route(
        self,
        path: str,
        methods: list[str],
        name: str | None = None,
        include_in_schema: bool = True,
    ):
        def decorator(func):
            self.routes.append(
                {
                    "path": path,
                    "methods": methods,
                    "name": name,
                    "include_in_schema": include_in_schema,
                    "func": func,
                }
            )
            return func

        return decorator

    def tool(self, **_kwargs: Any):
        def decorator(func):
            self.tools.append(func.__name__)
            self.tool_functions[func.__name__] = func
            return func

        return decorator


class FakeJSONResponse(dict):
    def __init__(self, content: dict[str, str]) -> None:
        super().__init__(content)
        self.status_code = 200


def test_arg_parser_defaults_to_stdio_and_local_http_bind(monkeypatch) -> None:
    monkeypatch.delenv("PORT", raising=False)

    args = build_arg_parser().parse_args([])

    assert args.transport == "stdio"
    assert args.host == "127.0.0.1"
    assert args.port == 8080


def test_arg_parser_accepts_streamable_http_flags() -> None:
    args = build_arg_parser().parse_args(
        ["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9090"]
    )

    assert args.transport == "streamable-http"
    assert args.host == "0.0.0.0"
    assert args.port == 9090


def test_arg_parser_uses_port_env(monkeypatch) -> None:
    monkeypatch.setenv("PORT", "7777")

    args = build_arg_parser().parse_args([])

    assert args.port == 7777


def test_healthz_route_is_registered(monkeypatch) -> None:
    fastmcp_module = types.ModuleType("mcp.server.fastmcp")
    fastmcp_module.FastMCP = FakeFastMCP
    mcp_types_module = types.ModuleType("mcp.types")
    mcp_types_module.ToolAnnotations = lambda **kwargs: kwargs
    response_module = types.ModuleType("starlette.responses")
    response_module.JSONResponse = FakeJSONResponse
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fastmcp_module)
    monkeypatch.setitem(sys.modules, "mcp.types", mcp_types_module)
    monkeypatch.setitem(sys.modules, "starlette.responses", response_module)

    mcp = build_mcp_server(host="0.0.0.0", port=8080)

    assert mcp.settings == {"host": "0.0.0.0", "port": 8080}
    assert {
        "path": "/healthz",
        "methods": ["GET"],
        "name": None,
        "include_in_schema": False,
        "func": mcp.routes[0]["func"],
    } in mcp.routes
    start_sit_parameters = inspect.signature(
        mcp.tool_functions["get_start_sit_recommendation"]
    ).parameters
    assert start_sit_parameters["week"].default is inspect.Parameter.empty
    assert start_sit_parameters["season"].default is None
    assert "season" not in inspect.signature(
        mcp.tool_functions["get_scout_rankings"]
    ).parameters
    assert set(mcp.tools) == {
        "get_game_scores",
        "get_wire_news",
        "get_player_grade",
        "get_start_sit_recommendation",
        "get_scout_rankings",
    }


def test_season_default_uses_latest_complete_calendar_season() -> None:
    assert latest_complete_nfl_season(date(2026, 8, 30)) == 2025
    assert latest_complete_nfl_season(date(2026, 2, 28)) == 2024
