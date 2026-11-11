"""Procurement Agent: quotes, scoring, abstention, and one propose+pay per request."""
from __future__ import annotations

import asyncio

import pytest

from app.agents.procurement import (
    ApiQuoteSource,
    FakeQuoteSource,
    ProcurementAgent,
    budget_cents,
    choose_supplier,
    is_approval_error,
    line_items_for,
    line_items_sum,
    milestone_total,
    needs_approval,
    request_quantity,
)
from app.mcp_client import FakeMcpClient, McpUnavailable


def request_(**over) -> dict:
    base = {
        "id": 12,
        "description": "40 copies of the Grade 3 reading set",
        "quantity": 40,
        "max_amount_cents": 3_500,
        "project": {"id": 1, "title": "Lanet Library", "tags": ["books"], "region": "Nakuru"},
        "milestone": {"id": 7, "title": "Buy 40 books", "amount_cents": 3_000,
                      "match_amount_cents": 0, "currency": "USD", "status": "open"},
        "region": "Nakuru",
    }
    base.update(over)
    return base


NAKURU = {"id": 3, "name": "Nakuru Books & Stationery", "categories": ["Education"],
          "tags": ["books", "literacy"], "region": "Nakuru"}


# What POST /internal/procurement/{id}/pay answers: the ProcurementOut, status enum-valued.
RUN = {"id": 1, "agent": "procurement-agent", "mandate_id": None}
PAID = {"id": 12, "status": "paid", "supplier_id": 3, "amount_cents": 3_000,
        "currency": "USD", "payout_id": 44}


def agent_(suppliers=None, unit=75, reliability=0.9, auto_approve=5_000, **mcp_rows):
    rows = {"list_procurement_requests": [request_()],
            "list_procurement_suppliers": suppliers if suppliers is not None else [NAKURU],
            "record_procurement_run": RUN,
            "pay_procurement": PAID}
    rows.update(mcp_rows)
    mcp = FakeMcpClient(rows)
    agent = ProcurementAgent(mcp=mcp,
                             quote_source=FakeQuoteSource(unit, reliability),
                             auto_approve_cents=auto_approve)
    return agent, mcp


def calls(mcp, tool: str) -> list[dict]:
    return [args for name, args in mcp.calls if name == tool]


# --- QuoteSource -----------------------------------------------------------------------


def test_api_quote_source_reads_both_fields() -> None:
    quote = ApiQuoteSource().quote({"unit_amount_cents": 75, "reliability": 0.9}, request_())
    assert quote == {"unit_amount_cents": 75, "reliability": 0.9}


@pytest.mark.parametrize("supplier", [
    {},
    {"unit_amount_cents": 75},
    {"reliability": 0.9},
    {"unit_amount_cents": None, "reliability": 0.9},
    {"unit_amount_cents": 75, "reliability": None},
    {"unit_amount_cents": 0, "reliability": 0.9},
    {"unit_amount_cents": -75, "reliability": 0.9},
    {"unit_amount_cents": "75", "reliability": 0.9},
    {"unit_amount_cents": True, "reliability": 0.9},
    {"unit_amount_cents": 75, "reliability": "high"},
])
def test_api_quote_source_returns_none_when_a_field_is_absent(supplier) -> None:
    """No partial quotes: a missing or unusable field is no quote, never a default."""
    assert ApiQuoteSource().quote(supplier, request_()) is None


def test_api_quote_source_accepts_a_percentage_reliability() -> None:
    quote = ApiQuoteSource().quote({"unit_amount_cents": 75, "reliability": 90}, request_())
    assert quote == {"unit_amount_cents": 75, "reliability": 0.9}


# --- The acceptance case ---------------------------------------------------------------


def test_forty_books_at_75_cents_proposes_nakuru_and_pays_once() -> None:
    """40 x 75 = 3000: the demo, end to end, with exactly one pay call."""
    agent, mcp = agent_()
    out = asyncio.run(agent.run(12))

    assert len(out["runs"]) == 1 and not out["abstained"]
    run = out["runs"][0]
    assert run["proposed"] is True
    assert run["supplier_name"] == "Nakuru Books & Stationery"
    assert run["amount_cents"] == 3_000
    assert run["status"] == "paid"

    proposed = calls(mcp, "propose_procurement")
    assert len(proposed) == 1
    body = proposed[0]
    assert body["supplier_id"] == 3
    assert body["amount_cents"] == 3_000
    assert body["line_items"] == [{"description": "40 copies of the Grade 3 reading set",
                                   "quantity": 40, "unit_amount_cents": 75}]
    assert body["run_id"] == 1

    assert len(calls(mcp, "pay_procurement")) == 1, "pay is called once, never twice"


def test_the_run_is_recorded_before_proposing_and_the_trace_is_ordered() -> None:
    agent, mcp = agent_()
    asyncio.run(agent.run(12))
    order = [name for name, _ in mcp.calls]
    assert order.index("record_procurement_run") < order.index("propose_procurement")
    decisions = calls(mcp, "record_procurement_run")[0]["decisions"]
    seqs = [item["seq"] for item in decisions["trace"]]
    assert seqs == sorted(seqs) and seqs == list(range(1, len(seqs) + 1))
    assert decisions["chosen"][0]["supplier_id"] == 3


# --- Abstention ------------------------------------------------------------------------


def test_no_quote_at_all_abstains_and_never_uses_the_budget_as_a_price() -> None:
    agent, mcp = agent_()
    agent.quotes = ApiQuoteSource()   # the real source: the seeded suppliers have no quote
    out = asyncio.run(agent.run(12))

    assert out["runs"] == []
    assert out["abstained"][0]["reason"] == "no supplier quote available"
    assert not calls(mcp, "propose_procurement")
    assert not calls(mcp, "pay_procurement")
    assert not calls(mcp, "record_procurement_run")


def test_an_unquoted_supplier_is_dropped_but_the_quoted_one_still_wins() -> None:
    other = {"id": 9, "name": "Lanet Printers", "categories": ["Education"],
             "tags": ["printing"], "region": "Nakuru"}

    class OneQuote(FakeQuoteSource):
        def quote(self, supplier, request):
            if supplier["id"] == 9:
                return None
            return super().quote(supplier, request)

    mcp = FakeMcpClient({"list_procurement_requests": [request_()],
                         "list_procurement_suppliers": [other, NAKURU]})
    agent = ProcurementAgent(mcp=mcp, quote_source=OneQuote())
    out = asyncio.run(agent.run(12))
    assert out["runs"][0]["supplier_id"] == 3


def test_amount_over_the_request_abstains_without_proposing() -> None:
    agent, mcp = agent_(suppliers=[NAKURU])
    mcp.responses["list_procurement_requests"] = [
        request_(quantity=40, max_amount_cents=2_999)]
    out = asyncio.run(agent.run(12))
    assert out["abstained"][0]["reason"] == "over request"
    assert not calls(mcp, "propose_procurement")


def test_amount_over_the_milestone_tranche_abstains() -> None:
    agent, mcp = agent_(suppliers=[NAKURU])
    mcp.responses["list_procurement_requests"] = [
        request_(quantity=40,
                 milestone={"id": 7, "title": "Buy 40 books", "amount_cents": 2_500,
                            "match_amount_cents": 400, "currency": "USD", "status": "open"})]
    out = asyncio.run(agent.run(12))
    assert out["abstained"][0]["reason"] == "over milestone"
    assert not calls(mcp, "propose_procurement")


# --- Approval --------------------------------------------------------------------------


def test_above_the_automatic_limit_proposes_and_stops_for_an_admin() -> None:
    agent, mcp = agent_(auto_approve=2_000)
    out = asyncio.run(agent.run(12))
    assert out["runs"][0]["status"] == "awaiting_approval"
    assert len(calls(mcp, "propose_procurement")) == 1
    assert not calls(mcp, "pay_procurement"), "never provoke the 409"


def test_an_approval_error_from_pay_is_handled_not_raised() -> None:
    """The fallback: the pre-check cannot know everything, so the message is matched once."""

    class ApprovalPay(FakeMcpClient):
        async def call(self, tool, **args):
            if tool == "pay_procurement":
                self.calls.append((tool, args))
                raise McpUnavailable(
                    "MCP tool pay_procurement failed: 409 APPROVAL_REQUIRED 3000 is above 5000")
            return await super().call(tool, **args)

    mcp = ApprovalPay({"list_procurement_requests": [request_()],
                       "list_procurement_suppliers": [NAKURU]})
    agent = ProcurementAgent(mcp=mcp, quote_source=FakeQuoteSource())
    out = asyncio.run(agent.run(12))
    assert out["runs"][0]["status"] == "awaiting_approval"
    assert out["runs"][0]["trace"][-1]["reason"] == "APPROVAL_REQUIRED"


def test_another_pay_failure_still_raises() -> None:
    """The fallback must not swallow real failures."""

    class BrokenPay(FakeMcpClient):
        async def call(self, tool, **args):
            if tool == "pay_procurement":
                raise McpUnavailable("MCP tool pay_procurement failed: 500 boom")
            return await super().call(tool, **args)

    mcp = BrokenPay({"list_procurement_requests": [request_()],
                     "list_procurement_suppliers": [NAKURU]})
    agent = ProcurementAgent(mcp=mcp, quote_source=FakeQuoteSource())
    with pytest.raises(McpUnavailable):
        asyncio.run(agent.run(12))


def test_is_approval_error_matches_only_the_code() -> None:
    assert is_approval_error(McpUnavailable("409 APPROVAL_REQUIRED x"))
    assert not is_approval_error(McpUnavailable("500 boom"))
    assert not is_approval_error(ValueError("approval required"))


# --- Pure helpers ----------------------------------------------------------------------


def test_choose_supplier_prefers_a_better_score_and_is_deterministic() -> None:
    suppliers = [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
    quotes = {1: {"unit_amount_cents": 90, "reliability": 0.95},
              2: {"unit_amount_cents": 75, "reliability": 0.9}}
    chosen, scored = choose_supplier(suppliers, quotes)
    assert chosen["name"] == "B", "75c at 0.90 beats 90c at 0.95"
    assert [row["supplier"]["id"] for row in scored] == [2, 1]
    assert choose_supplier(suppliers, quotes)[0]["name"] == "B"


def test_choose_supplier_breaks_ties_on_price_then_id() -> None:
    suppliers = [{"id": 5, "name": "A"}, {"id": 2, "name": "B"}]
    same = {"unit_amount_cents": 75, "reliability": 0.9}
    chosen, _ = choose_supplier(suppliers, {5: same, 2: dict(same)})
    assert chosen["id"] == 2, "identical quotes: the lower id wins, every time"


def test_choose_supplier_with_no_quotes_returns_nothing() -> None:
    assert choose_supplier([{"id": 1, "name": "A"}], {}) == (None, [])


def test_line_items_sum_and_the_guard() -> None:
    lines = line_items_for(request_(), {"unit_amount_cents": 75}, 40)
    assert line_items_sum(lines) == 3_000
    assert line_items_sum([{"quantity": 2, "unit_amount_cents": 50},
                           {"quantity": 1, "unit_amount_cents": 25}]) == 125
    with pytest.raises(ValueError):
        line_items_sum([{"quantity": True, "unit_amount_cents": 75}])


def test_request_fields_are_read_from_the_api_shape() -> None:
    req = request_()
    assert request_quantity(req) == 40
    assert request_quantity(request_(quantity=None)) == 1
    assert request_quantity(request_(quantity=0)) == 1
    assert budget_cents(req) == 3_500
    assert milestone_total(req) == 3_000
    assert milestone_total(request_(milestone=None)) is None


def test_needs_approval_is_strictly_above_the_limit() -> None:
    assert not needs_approval(5_000, 5_000), "the limit itself pays automatically"
    assert needs_approval(5_001, 5_000)
