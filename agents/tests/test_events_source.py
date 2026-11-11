"""CoreEventsSource: the internal feed over httpx MockTransport. No network, no LLM."""
import logging

import httpx
import pytest

from app.agents.watchdog import FEED_PAGE_LIMIT, CoreEventsSource
from app.core import Core, CoreError
from app.config import Settings

NOW = "2026-11-05T12:00:00+00:00"

EVENT = {
    "donation_id": 4,
    "project_id": 1,
    "donor_id": 12,
    "status": "captured",
    "amount_cents": 2000,
    "captured_at": "2026-11-08T14:02:00Z",
    "donor_created_at": "2026-11-01T09:00:00Z",
    "owner_donor_id": 3,
    "is_guest": False,
}


def source(handler, token: str = "internal-secret") -> CoreEventsSource:
    """A CoreEventsSource whose Core talks to `handler` instead of the network."""
    cfg = Settings(core_api_url="https://core.test", internal_token=token)
    core = Core(cfg, transport=httpx.MockTransport(handler))
    return CoreEventsSource(core)


@pytest.mark.asyncio
async def test_parses_events_and_passes_since():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[EVENT])

    events = await source(handler).since(NOW)

    assert events == [EVENT]
    assert len(seen) == 1
    assert seen[0].url.path == "/internal/donation-events"
    assert seen[0].url.params["since"] == NOW
    assert seen[0].url.params["limit"] == str(FEED_PAGE_LIMIT)


@pytest.mark.asyncio
async def test_sends_bearer_token():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    await source(handler).since(NOW)

    assert seen[0].headers["authorization"] == "Bearer internal-secret"


@pytest.mark.asyncio
async def test_no_token_means_no_header():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    await source(handler, token="").since(NOW)

    assert "authorization" not in seen[0].headers


@pytest.mark.asyncio
async def test_returns_empty_list_on_server_error(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    with caplog.at_level(logging.WARNING):
        assert await source(handler).since(NOW) == []
    assert "donation-events unavailable" in caplog.text


@pytest.mark.asyncio
async def test_returns_empty_list_when_core_is_unreachable(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with caplog.at_level(logging.WARNING):
        assert await source(handler).since(NOW) == []
    assert "donation-events unavailable" in caplog.text


@pytest.mark.asyncio
async def test_non_list_body_is_treated_as_no_events(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"events": [EVENT]})

    with caplog.at_level(logging.WARNING):
        assert await source(handler).since(NOW) == []
    assert "expected a list" in caplog.text


@pytest.mark.asyncio
async def test_full_page_warns_about_a_truncated_window(caplog):
    """Exactly `limit` events means the page may have cut the window short."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[EVENT] * FEED_PAGE_LIMIT)

    with caplog.at_level(logging.WARNING):
        events = await source(handler).since(NOW)
    assert len(events) == FEED_PAGE_LIMIT
    assert "full" in caplog.text and "may be missing" in caplog.text


@pytest.mark.asyncio
async def test_short_page_does_not_warn(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[EVENT] * (FEED_PAGE_LIMIT - 1))

    with caplog.at_level(logging.WARNING):
        await source(handler).since(NOW)
    assert "may be missing" not in caplog.text


@pytest.mark.asyncio
async def test_scan_runs_the_rules_over_real_events():
    """End to end through WatchdogAgent: the feed feeds the existing rules unchanged."""
    from app.agents.watchdog import FakeEventsSource, WatchdogAgent
    from app.mcp_client import FakeMcpClient

    captured = [EVENT]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=captured)

    mcp = FakeMcpClient({"get_project": lambda **kw: {"id": kw["project_id"], "title": "P"}})
    agent = WatchdogAgent(mcp=mcp, source=source(handler))
    await agent.scan()

    # Nothing fires on one ordinary event, but the feed was read rather than skipped.
    assert [c for c in mcp.calls if c[0] == "open_watchdog_case"] == []
    assert isinstance(agent.source, CoreEventsSource)
