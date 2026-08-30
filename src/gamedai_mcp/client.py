from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from datetime import UTC
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

DEFAULT_API_BASE = "https://gamedai-v2-preview.fly.dev"
_MAX_RETRIES = 2
_BACKOFF_SECONDS = (0.5, 1.0)
_MAX_RETRY_AFTER_SECONDS = 5.0
_MAX_BODY_CHARS = 200
_SCOUT_KEY_ENV = "GAMEDAI_SCOUT_API_KEY"
_SCOUT_KEY_ALIAS_ENV = "GAMEDAI_PUBLIC_API_KEY"


class GamedaiMCPError(RuntimeError):
    """Stable, structured error returned by the MCP tool surface."""

    def __init__(self, code: str, http_status: int | None, message: str) -> None:
        self.code = code
        self.http_status = http_status
        self.message = message[:_MAX_BODY_CHARS]
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "http_status": self.http_status,
            "message": self.message,
        }


@dataclass(frozen=True)
class GamedaiClientConfig:
    base_url: str = DEFAULT_API_BASE


class GamedaiClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        raw_base = base_url or os.environ.get("GAMEDAI_API_BASE") or DEFAULT_API_BASE
        self.config = GamedaiClientConfig(base_url=raw_base.rstrip("/"))
        self._scout_api_key = os.environ.get(_SCOUT_KEY_ENV) or os.environ.get(
            _SCOUT_KEY_ALIAS_ENV
        )
        self._client = http_client
        self._owns_client = http_client is None

    async def __aenter__(self) -> "GamedaiClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
        self._client = None

    async def get_game_scores(
        self,
        *,
        date: str | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        params = {"date": date} if date is not None else None
        slate = await self._request_json("GET", "/v1/games/slate", params=params)
        games = slate.get("games")
        if not isinstance(games, list):
            raise GamedaiMCPError(
                "backend_unavailable",
                200,
                "gamedai backend returned an invalid slate payload",
            )

        # The backend has no public event-specific summary route. Keep this
        # local filter so event_id remains a useful MCP-only convenience.
        if event_id is None:
            return slate

        match = next(
            (game for game in games if isinstance(game, dict) and game.get("event_id") == event_id),
            None,
        )
        return {"games": [match] if match is not None else [], "event_id": event_id}

    async def get_wire_news(self, *, page: int = 1, page_size: int = 10) -> dict[str, Any]:
        if page < 1:
            raise GamedaiMCPError("validation_failed", 422, "page must be at least 1")
        if page_size < 1 or page_size > 50:
            raise GamedaiMCPError(
                "validation_failed", 422, "page_size must be between 1 and 50"
            )
        return await self._request_json(
            "GET",
            "/api/wire/feed",
            params={"page": page, "page_size": page_size},
        )

    async def player_grade(
        self,
        player: str,
        season: int,
        week: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {"player": player, "season": season}
        if week is not None:
            params["week"] = week
        return await self._request_json(
            "GET", "/v1/scout/player-grade", params=params, scout=True
        )

    async def start_sit(
        self,
        player_a: str,
        player_b: str,
        season: int,
        week: int,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {
            "player_a": player_a,
            "player_b": player_b,
            "season": season,
            "week": week,
        }
        return await self._request_json(
            "GET", "/v1/scout/start-sit", params=params, scout=True
        )

    async def rankings(
        self,
        *,
        position: str = "ALL",
        scoring: str = "PPR",
        week: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {"position": position, "scoring": scoring}
        if week is not None:
            params["week"] = week
        return await self._request_json("GET", "/v1/scout/rankings", params=params, scout=True)

    async def scout_health(self) -> dict[str, Any]:
        return await self._request_json("GET", "/v1/scout/health", scout=True)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        scout: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        client = self._http_client()
        url = f"{self.config.base_url}{path}"
        headers = dict(kwargs.pop("headers", {}) or {})
        if scout and self._scout_api_key:
            headers["X-Scout-API-Key"] = self._scout_api_key
        if headers:
            kwargs["headers"] = headers

        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = await client.request(method, url, **kwargs)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                    continue
                raise GamedaiMCPError(
                    "backend_unavailable",
                    None,
                    f"gamedai backend transport error for {path}: {exc}",
                ) from exc
            except httpx.HTTPError as exc:
                raise GamedaiMCPError(
                    "backend_unavailable",
                    None,
                    f"gamedai backend request failed for {path}: {exc}",
                ) from exc

            if response.status_code < 400:
                return _json_object(response, path)

            if response.status_code in {408, 429} or response.status_code >= 500:
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(
                        max(_BACKOFF_SECONDS[attempt], _retry_after_seconds(response))
                    )
                    continue
            raise _http_error(response, path)

        raise AssertionError("request retry loop must return or raise")

    def _http_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(connect=5, read=15, write=5, pool=5)
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client


def _json_object(response: httpx.Response, path: str) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise GamedaiMCPError(
            "backend_unavailable",
            response.status_code,
            f"gamedai backend returned non-JSON for {path}: {_body_text(response)}",
        ) from exc
    if not isinstance(data, dict):
        raise GamedaiMCPError(
            "backend_unavailable",
            response.status_code,
            f"gamedai backend returned unexpected JSON for {path}: {_body_text(response)}",
        )
    return data


def _http_error(response: httpx.Response, path: str) -> GamedaiMCPError:
    status = response.status_code
    if status in {401, 403}:
        code = "invalid_scout_key" if path.startswith("/v1/scout/") else "auth_failed"
    elif status == 404:
        code = "not_found"
    elif status == 422:
        code = "validation_failed"
    elif status == 429:
        code = "rate_limited"
    elif status >= 500:
        code = "backend_unavailable"
    else:
        code = "validation_failed"
    return GamedaiMCPError(
        code,
        status,
        f"gamedai backend returned {status} for {path}: {_body_text(response)}",
    )


def _body_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text
    else:
        if isinstance(payload, dict):
            for key in ("detail", "error", "message"):
                value = payload.get(key)
                if value:
                    text = str(value)
                    break
            else:
                text = str(payload)
        else:
            text = str(payload)
    return (text or response.reason_phrase)[:_MAX_BODY_CHARS]


def _retry_after_seconds(response: httpx.Response) -> float:
    value = response.headers.get("Retry-After")
    if not value:
        return 0.0
    try:
        return min(_MAX_RETRY_AFTER_SECONDS, max(0.0, float(value)))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return min(
            _MAX_RETRY_AFTER_SECONDS,
            max(0.0, retry_at.timestamp() - time.time()),
        )
