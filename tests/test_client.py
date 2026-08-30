from __future__ import annotations

import asyncio
import httpx
import pytest

from gamedai_mcp.client import GamedaiClient, GamedaiMCPError


class FakeAsyncClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, dict]] = []
        self.closed = False

    async def request(self, method: str, url: str, **kwargs):
        self.requests.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    async def aclose(self) -> None:
        self.closed = True


def _response(status_code: int, json_data: object, url: str = "https://api.test/v1/test"):
    request = httpx.Request("GET", url)
    return httpx.Response(status_code, json=json_data, request=request)


def test_get_game_scores_reads_slate_and_filters_event_id() -> None:
    async def run() -> None:
        fake = FakeAsyncClient(
            [
                _response(
                    200,
                    {
                        "games": [
                            {
                                "event_id": "401671698",
                                "home_abbr": "SF",
                                "away_abbr": "DET",
                                "home_score": 34,
                                "away_score": 40,
                                "period": 4,
                                "clock": "0:00",
                                "kickoff_at": None,
                                "status": "FINAL",
                                "is_live": False,
                            }
                        ]
                    },
                )
            ]
        )
        client = GamedaiClient(base_url="https://api.test/", http_client=fake)  # type: ignore[arg-type]

        result = await client.get_game_scores(event_id="401671698")

        assert result["games"][0]["away_score"] == 40
        assert fake.requests[0][0] == "GET"
        assert fake.requests[0][1] == "https://api.test/v1/games/slate"

    asyncio.run(run())


def test_get_game_scores_passes_backend_date_and_keeps_event_filter_local() -> None:
    async def run() -> None:
        fake = FakeAsyncClient([_response(200, {"games": []})])
        client = GamedaiClient(base_url="https://api.test", http_client=fake)  # type: ignore[arg-type]

        await client.get_game_scores(date="2026-08-30", event_id="missing")

        assert fake.requests[0][2]["params"] == {"date": "2026-08-30"}

    asyncio.run(run())


def test_scout_methods_send_key_only_to_scout_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        monkeypatch.setenv("GAMEDAI_SCOUT_API_KEY", "scout-key")
        fake = FakeAsyncClient(
            [
                _response(200, {"grade": True}),
                _response(200, {"pick": True}),
                _response(200, {"rankings": []}),
                _response(200, {"ok": True}),
                _response(200, {"games": []}),
            ]
        )
        client = GamedaiClient(base_url="https://api.test", http_client=fake)  # type: ignore[arg-type]

        await client.player_grade("A", 2025)
        await client.start_sit("A", "B", 2025, 1)
        await client.rankings(position="RB", scoring="PPR", week=1)
        await client.scout_health()
        await client.get_game_scores()

        assert all("X-Scout-API-Key" in request[2]["headers"] for request in fake.requests[:4])
        assert "headers" not in fake.requests[4][2]
        assert fake.requests[2][2]["params"] == {"position": "RB", "scoring": "PPR", "week": 1}

    asyncio.run(run())


def test_public_key_is_a_scout_key_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        monkeypatch.delenv("GAMEDAI_SCOUT_API_KEY", raising=False)
        monkeypatch.setenv("GAMEDAI_PUBLIC_API_KEY", "alias-key")
        fake = FakeAsyncClient([_response(200, {"ok": True})])
        client = GamedaiClient(base_url="https://api.test", http_client=fake)  # type: ignore[arg-type]

        await client.scout_health()

        assert fake.requests[0][2]["headers"] == {"X-Scout-API-Key": "alias-key"}

    asyncio.run(run())


def test_get_wire_news_passes_supported_query_params() -> None:
    async def run() -> None:
        fake = FakeAsyncClient(
            [
                _response(
                    200,
                    {
                        "articles": [
                            {
                                "id": "wire-1",
                                "headline": "Camp battle sharpens",
                                "summary": "A rookie took first-team reps.",
                                "body_md": "Full wire body.",
                                "byline_persona": "Scout Desk",
                                "source_urls": ["https://example.com/story"],
                                "category": "team_news",
                                "published_at": "2026-07-03T12:00:00Z",
                            }
                        ],
                        "page": 2,
                        "page_size": 5,
                        "total": 1,
                        "has_more": False,
                    },
                )
            ]
        )
        client = GamedaiClient(base_url="https://api.test", http_client=fake)  # type: ignore[arg-type]

        result = await client.get_wire_news(page=2, page_size=5)

        assert result["articles"][0]["headline"] == "Camp battle sharpens"
        assert fake.requests[0][0] == "GET"
        assert fake.requests[0][1] == "https://api.test/api/wire/feed"
        assert fake.requests[0][2]["params"] == {"page": 2, "page_size": 5}

    asyncio.run(run())


def test_get_wire_news_rejects_out_of_range_page_size() -> None:
    async def run() -> None:
        client = GamedaiClient(base_url="https://api.test", http_client=FakeAsyncClient([]))  # type: ignore[arg-type]

        with pytest.raises(GamedaiMCPError, match="page_size must be between 1 and 50"):
            await client.get_wire_news(page_size=51)

    asyncio.run(run())


def test_backend_error_is_tool_error() -> None:
    async def run() -> None:
        fake = FakeAsyncClient([_response(401, {"detail": "missing_subject"})])
        client = GamedaiClient(base_url="https://api.test", http_client=fake)  # type: ignore[arg-type]

        with pytest.raises(GamedaiMCPError) as error:
            await client.get_wire_news()
        assert error.value.as_dict() == {
            "code": "auth_failed",
            "http_status": 401,
            "message": "gamedai backend returned 401 for /api/wire/feed: missing_subject",
        }

    asyncio.run(run())


def test_retries_rate_limit_then_honors_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        fake = FakeAsyncClient(
            [
                _response(429, {"detail": "slow down"}),
                _response(200, {"ok": True}),
            ]
        )
        fake.responses[0].headers["Retry-After"] = "10"
        delays: list[float] = []

        async def sleep(delay: float) -> None:
            delays.append(delay)

        monkeypatch.setattr("gamedai_mcp.client.asyncio.sleep", sleep)
        client = GamedaiClient(base_url="https://api.test", http_client=fake)  # type: ignore[arg-type]

        assert await client.scout_health() == {"ok": True}
        assert delays == [5.0]
        assert len(fake.requests) == 2

    asyncio.run(run())


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ConnectTimeout])
def test_retries_connect_errors(error_type, monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        fake = FakeAsyncClient(
            [
                error_type("connect failed"),
                _response(200, {"ok": True}),
            ]
        )
        delays: list[float] = []

        async def sleep(delay: float) -> None:
            delays.append(delay)

        monkeypatch.setattr("gamedai_mcp.client.asyncio.sleep", sleep)
        client = GamedaiClient(base_url="https://api.test", http_client=fake)  # type: ignore[arg-type]

        assert await client.scout_health() == {"ok": True}
        assert delays == [0.5]
        assert len(fake.requests) == 2

    asyncio.run(run())


def test_does_not_retry_read_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        fake = FakeAsyncClient([httpx.ReadTimeout("read timed out")])
        delays: list[float] = []

        async def sleep(delay: float) -> None:
            delays.append(delay)

        monkeypatch.setattr("gamedai_mcp.client.asyncio.sleep", sleep)
        client = GamedaiClient(base_url="https://api.test", http_client=fake)  # type: ignore[arg-type]

        with pytest.raises(GamedaiMCPError) as error:
            await client.scout_health()
        assert error.value.code == "backend_unavailable"
        assert delays == []
        assert len(fake.requests) == 1

    asyncio.run(run())


def test_scout_auth_failure_maps_to_invalid_scout_key() -> None:
    async def run() -> None:
        fake = FakeAsyncClient([_response(403, {"detail": "forbidden"})])
        client = GamedaiClient(base_url="https://api.test", http_client=fake)  # type: ignore[arg-type]

        with pytest.raises(GamedaiMCPError) as error:
            await client.scout_health()
        assert error.value.code == "invalid_scout_key"

    asyncio.run(run())
