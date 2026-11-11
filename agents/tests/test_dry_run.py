"""DRY_RUN default and guard tests.

An unset DRY_RUN must block every mutating MCP tool. These run with a clean Settings
(no env overrides) so they assert the shipped default, not a test fixture.
"""
import pytest

from app.config import Settings
from app.mcp_client import MUTATING_TOOLS, McpClient


EXPECTED_MUTATING = {
    "record_mandate_run",
    "request_checked_donation",
    "open_watchdog_case",
    "request_milestone_payout",
    "log_decision",
    # Procurement: recording a run is inert, but proposing commits a price and paying
    # moves money. A DRY_RUN that let either through would be worse than no guard.
    "record_procurement_run",
    "propose_procurement",
    "pay_procurement",
}


def test_dry_run_is_true_by_default(monkeypatch):
    """Shipped default: money-moving code must be opted into, not opted out of."""
    monkeypatch.delenv("DRY_RUN", raising=False)
    assert Settings().dry_run is True


def test_mutating_tools_set_is_exactly_the_expected():
    """A new write tool must be added here and to MUTATING_TOOLS together."""
    assert MUTATING_TOOLS == EXPECTED_MUTATING


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", sorted(EXPECTED_MUTATING))
async def test_default_settings_block_every_mutating_tool(tool, monkeypatch):
    """No env at all: every mutating tool returns a canned result and sends nothing."""
    monkeypatch.delenv("DRY_RUN", raising=False)
    cfg = Settings()
    assert cfg.dry_run is True

    client = McpClient(cfg)

    async def explode():
        raise AssertionError("DRY_RUN must not connect to the MCP server")

    monkeypatch.setattr(client, "session", explode)
    result = await client.call(tool, project_id=1, amount_cents=500)

    assert result["dry_run"] is True
    assert result["tool"] == tool
    assert result["status"] == "recorded"


@pytest.mark.asyncio
async def test_read_tools_still_work_under_dry_run(monkeypatch):
    """DRY_RUN blocks writes only; reads must keep working."""
    monkeypatch.delenv("DRY_RUN", raising=False)
    cfg = Settings()
    client = McpClient(cfg)

    called = []

    class _Session:
        async def call_tool(self, tool, arguments=None):
            called.append(tool)
            raise AssertionError("stop after recording the attempt")

    async def fake_session():
        return _Session()

    monkeypatch.setattr(client, "session", fake_session)
    with pytest.raises(Exception):
        await client.call("search_projects", limit=5)
    # call() retries once, so the read is attempted twice before giving up.
    assert called == ["search_projects", "search_projects"]


@pytest.mark.asyncio
async def test_explicit_dry_run_false_lets_a_write_through(monkeypatch):
    """The opt-out exists and is what arms the agents."""
    monkeypatch.setenv("DRY_RUN", "false")
    cfg = Settings()
    assert cfg.dry_run is False

    client = McpClient(cfg)
    called = []

    class _Session:
        async def call_tool(self, tool, arguments=None):
            called.append(tool)
            raise AssertionError("reached the server")

    async def fake_session():
        return _Session()

    monkeypatch.setattr(client, "session", fake_session)
    with pytest.raises(Exception):
        await client.call("record_mandate_run", mandate_id=1)
    # Reaching the server at all is the point: the write was not blocked.
    assert called and set(called) == {"record_mandate_run"}
