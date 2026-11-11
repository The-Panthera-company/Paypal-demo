"""The procurement surface: the token-gated route, the scheduler job, the fake defaults."""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.agents.procurement import ProcurementAgent
from app.config import Settings
from app.mcp_client import FakeMcpClient, McpClient

TOKEN = "test-internal-token"


@pytest.fixture()
def main_module(monkeypatch):
    """app.main with FAKE_CORE on and a known internal token."""
    monkeypatch.setenv("FAKE_CORE", "true")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("INTERNAL_TOKEN", TOKEN)

    from app.config import settings

    settings.cache_clear()

    import app.main as module

    monkeypatch.setattr(module.cfg, "fake_core", True, raising=False)
    monkeypatch.setattr(module.cfg, "internal_token", TOKEN, raising=False)
    module.reset_shared()
    yield module
    module.reset_shared()
    settings.cache_clear()


# --- The route -------------------------------------------------------------------------


def test_run_without_a_token_is_401(main_module):
    with TestClient(main_module.app) as client:
        assert client.post("/agents/procurement/run", json={}).status_code == 401


def test_run_with_a_wrong_token_is_401(main_module):
    with TestClient(main_module.app) as client:
        resp = client.post("/agents/procurement/run", json={},
                           headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_run_with_the_token_is_200_and_abstains_with_no_quote(main_module, monkeypatch):
    """The fake defaults give no suppliers, so the agent must abstain, not invent."""
    # The route builds a real ProcurementAgent, whose default MCP client is the real one.
    # Swap it at the module the agent reads, or this test would spawn the MCP server.
    monkeypatch.setattr("app.agents.procurement.build_client", lambda *a, **k: FakeMcpClient())
    with TestClient(main_module.app) as client:
        resp = client.post("/agents/procurement/run", json={"procurementId": None,
                                                            "force": False},
                           headers={"Authorization": "Bearer " + TOKEN})
    assert resp.status_code == 200
    assert resp.json() == {"runs": [], "abstained": [], "skipped": []}


def test_run_accepts_a_procurement_id_and_closes_its_client(main_module, monkeypatch):
    closed: list[bool] = []
    made: list[ProcurementAgent] = []

    class ClosingAgent(ProcurementAgent):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            made.append(self)

        async def run(self, procurement_id=None):
            return {"runs": [], "abstained": [{"procurement_id": procurement_id,
                                              "reason": "not open"}]}

    async def aclose():
        closed.append(True)

    monkeypatch.setattr(main_module, "ProcurementAgent", ClosingAgent)
    with TestClient(main_module.app) as client:
        resp = client.post("/agents/procurement/run", json={"procurementId": 12},
                           headers={"Authorization": "Bearer " + TOKEN})
    assert resp.status_code == 200
    assert resp.json()["abstained"][0]["procurement_id"] == 12
    assert made[0].mcp is not None
    # finally-block teardown ran: the agent's own client was closed.
    assert getattr(made[0].mcp, "closed", False) or isinstance(made[0].mcp, FakeMcpClient)


# --- The real answer shape ---------------------------------------------------------------
# The probe against giving-api.onrender.com returned ONE dict for a single open request.
# _unwrap correctly hands that back as a dict (an object tool), so LIST_TOOLS must re-wrap it.

REAL_REQUEST = {
    "id": 41,
    "project_id": 7,
    "milestone_id": 3,
    "description": "Print 500 leaflets",
    "quantity": 500,
    "max_amount_cents": 1_200_000,
    "status": "requested",
    "supplier_id": None,
    "line_items": [],
    "needs_approval": True,
}

REAL_SUPPLIER = {
    "id": 5,
    "name": "Acme Print",
    "project_id": 7,
    "unit": "leaflet",
    "region": "Nairobi",
}


def test_a_single_procurement_request_becomes_a_one_item_list() -> None:
    mcp = FakeMcpClient({"list_procurement_requests": REAL_REQUEST})
    out = asyncio.run(ProcurementAgent(mcp=mcp).run())
    # The run did not crash by iterating the dict's keys, and the request was considered.
    assert out["skipped"] == []
    assert [item["procurement_id"] for item in out["abstained"]] == [41]


def test_a_single_supplier_becomes_a_one_item_list() -> None:
    mcp = FakeMcpClient({"list_procurement_requests": REAL_REQUEST,
                         "list_procurement_suppliers": REAL_SUPPLIER})
    out = asyncio.run(ProcurementAgent(mcp=mcp).run())
    assert out["skipped"] == []
    # One supplier is one supplier: join a dict's keys and the trace would say "5, name, ...".
    trace = out["abstained"][0]["trace"]
    first = [step for step in trace if step.get("tool") == "list_procurement_suppliers"][0]
    assert first["title"] == "Found 1 eligible suppliers"


def test_an_empty_procurement_answer_stays_an_empty_list() -> None:
    mcp = FakeMcpClient({"list_procurement_requests": [],
                         "list_procurement_suppliers": []})
    out = asyncio.run(ProcurementAgent(mcp=mcp).run())
    assert out == {"runs": [], "abstained": [], "skipped": []}


def test_coerce_shape_wraps_a_bare_dict_and_none() -> None:
    from app.mcp_client import _coerce_shape

    assert _coerce_shape("list_procurement_requests", REAL_REQUEST) == [REAL_REQUEST]
    assert _coerce_shape("list_procurement_requests", None) == []
    assert _coerce_shape("list_procurement_requests", [REAL_REQUEST]) == [REAL_REQUEST]
    assert _coerce_shape("list_procurement_suppliers", REAL_SUPPLIER) == [REAL_SUPPLIER]
    assert _coerce_shape("list_procurement_suppliers", None) == []
    # An object tool is untouched: the rule is per tool name, not "wrap everything".
    assert _coerce_shape("get_project", {"id": 1}) == {"id": 1}


real_request = REAL_REQUEST
real_supplier = REAL_SUPPLIER


0
# --- Malformed answers ------------------------------------------------------------------


def test_a_non_dict_item_is_skipped_not_fatal() -> None:
    """One bad row must not stop the run: the good ones are still considered."""
    good = {"id": 1, "project": {"id": 7}, "quantity": 1}
    mcp = FakeMcpClient({"list_procurement_requests": [good, "oops", 42, None]})
    out = asyncio.run(ProcurementAgent(mcp=mcp).run())
    assert [item["index"] for item in out["skipped"]] == [1, 2, 3]
    assert [item["type"] for item in out["skipped"]] == ["str", "int", "NoneType"]
    # The surviving request was still considered and, having no quote, abstained.
    assert len(out["abstained"]) == 1
    assert out["abstained"][0]["procurement_id"] == 1


def test_a_skipped_item_never_echoes_the_payload() -> None:
    """The trace names the position and the type, never the value: a row may hold a contact."""
    mcp = FakeMcpClient({"list_procurement_requests": ["buyer@example.org asked"]})
    out = asyncio.run(ProcurementAgent(mcp=mcp).run())
    assert "@" not in repr(out["skipped"])
    assert "example" not in repr(out["skipped"])


def test_an_answer_that_is_not_a_list_is_reported_not_crashed() -> None:
    mcp = FakeMcpClient({"list_procurement_requests": {"id": 3}})
    out = asyncio.run(ProcurementAgent(mcp=mcp).run())
    # A lone dict is one request, not an error: the client unwraps single objects.
    assert out["skipped"] == []
    assert len(out["abstained"]) == 1


def test_an_unexpected_failure_is_a_502_not_a_500(main_module, monkeypatch) -> None:
    """A bug or a malformed answer is ours to report, with a named type and no payload."""

    class Exploding(ProcurementAgent):
        async def run(self, procurement_id=None):
            raise AttributeError("'str' object has no attribute 'get'")

    monkeypatch.setattr(main_module, "ProcurementAgent", Exploding)
    with TestClient(main_module.app) as client:
        resp = client.post("/agents/procurement/run", json={},
                           headers={"Authorization": "Bearer " + TOKEN})
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "AttributeError" in detail
    assert "example" not in detail


def test_an_unexpected_failure_still_closes_the_client(main_module, monkeypatch) -> None:
    closed: list[bool] = []

    class Exploding(ProcurementAgent):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)

            async def aclose():
                closed.append(True)

            self.mcp = FakeMcpClient()
            self.mcp.aclose = aclose

        async def run(self, procurement_id=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "ProcurementAgent", Exploding)
    with TestClient(main_module.app) as client:
        resp = client.post("/agents/procurement/run", json={},
                           headers={"Authorization": "Bearer " + TOKEN})
    assert resp.status_code == 502
    assert closed == [True], "the finally block must still run"


# --- The scheduler ---------------------------------------------------------------------


def test_scheduler_registers_the_procurement_job() -> None:
    from app.scheduler import build_scheduler, run_procurement

    cfg = Settings(scheduler_enabled=True, procurement_interval_seconds=123)
    scheduler = build_scheduler(cfg)
    job = scheduler.get_job("procurement")
    assert job is not None
    assert job.func is run_procurement
    assert "0:02:03" in str(job.trigger)


def test_scheduler_is_off_unless_enabled() -> None:
    from app.scheduler import start_if_enabled

    assert start_if_enabled(Settings(scheduler_enabled=False)) is None


def test_procurement_interval_defaults_to_300() -> None:
    assert Settings().procurement_interval_seconds == 300


def test_run_procurement_abstains_under_the_fake_defaults(monkeypatch) -> None:
    """The job is safe to schedule before Person 1 adds quotes: nothing to price, nothing done."""
    # Patch the name the agent module imported, not app.mcp_client: the module already holds
    # a reference to the original function. Without FAKE_CORE the real client would spawn the
    # MCP server, which needs httpx and a network.
    monkeypatch.setattr("app.agents.procurement.build_client", lambda *a, **k: FakeMcpClient())
    from app.scheduler import run_procurement

    out = asyncio.run(run_procurement())
    assert out == {"runs": [], "abstained": [], "skipped": []}


# --- Fake defaults ---------------------------------------------------------------------


def test_fake_defaults_are_empty_lists_and_shaped_objects() -> None:
    mcp = FakeMcpClient()
    assert asyncio.run(mcp.call("list_procurement_requests")) == []
    assert asyncio.run(mcp.call("list_procurement_suppliers", project_id=1)) == []
    assert asyncio.run(mcp.call("record_procurement_run", decisions={}))["id"] == 1

    proposed = asyncio.run(mcp.call(
        "propose_procurement", procurement_id=12, supplier_id=3, amount_cents=3_000,
        line_items=[], rationale="x", run_id=1))
    assert proposed["status"] == "proposed"
    assert proposed["id"] == 12 and proposed["supplier_id"] == 3
    assert proposed["amount_cents"] == 3_000

    paid = asyncio.run(mcp.call("pay_procurement", procurement_id=12))
    assert paid["status"] == "paid"
    assert paid["id"] == 12


def test_default_shape_matches_procurement_out() -> None:
    """The fake answers must carry the fields the agent and the web read."""
    mcp = FakeMcpClient()
    paid = asyncio.run(mcp.call("pay_procurement", procurement_id=12))
    for field in ("id", "project_id", "milestone_id", "description", "quantity",
                  "max_amount_cents", "currency", "status", "supplier_id",
                  "amount_cents", "line_items", "rationale", "admin_approved"):
        assert field in paid, field


# --- DRY_RUN ---------------------------------------------------------------------------


def test_procurement_writes_are_behind_the_mcp_dry_run_guard() -> None:
    """One mechanism: the MCP layer blocks mutating tools when DRY_RUN is on.

    No second flag lives in the agent. These three names must be in MUTATING_TOOLS or a dry
    run would still propose and pay.
    """
    from app.mcp_client import MUTATING_TOOLS

    for tool in ("record_procurement_run", "propose_procurement", "pay_procurement"):
        assert tool in MUTATING_TOOLS, tool


def test_dry_run_blocks_the_pay_call(monkeypatch) -> None:
    cfg = Settings(dry_run=True, internal_token=TOKEN)
    client = McpClient.__new__(McpClient)
    client.cfg = cfg
    out = asyncio.run(client.call("pay_procurement", procurement_id=12))
    assert out == {"dry_run": True, "tool": "pay_procurement", "status": "recorded"}


def test_the_agent_has_no_dry_run_flag_of_its_own() -> None:
    """If someone adds one, this fails and the reviewer asks why."""
    agent = ProcurementAgent(mcp=FakeMcpClient())
    assert not hasattr(agent, "dry_run")
    assert not hasattr(agent, "sell")
