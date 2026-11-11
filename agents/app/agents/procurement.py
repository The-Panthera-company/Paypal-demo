"""Procurement Agent: turn a purchase request into one supplier proposal, then pay it.

Money moves only through the API: this module never writes to PayPal. Every number it sends
comes from a quote (QuoteSource) or from the request itself, and a request with no quote
abstains rather than guessing a price. max_amount_cents is a ceiling the project owner set,
never a price.

The steps, in order, each one recorded on the public trace:
  list requests -> list eligible suppliers for the project -> quote each -> score ->
  record run -> propose -> pay.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from ..llm import LLM, LLMUnavailable, build_llm
from ..mcp_client import build_client

log = logging.getLogger(__name__)

# The API pays automatically up to this ceiling; above it an admin must approve first.
# Mirrors api/app/config.py procurement_auto_approve_cents. Pre-checked so a purchase that
# cannot be paid yet is never proposed as if it could.
AUTO_APPROVE_CENTS = 5_000

QUOTE_UNIT_KEY = "unit_amount_cents"
QUOTE_RELIABILITY_KEY = "reliability"


class QuoteSource(Protocol):
    """Where prices come from.

    MilestoneSource is the precedent: an interface, so the agent never invents a price and the
    tests and the dry run can supply known ones. quote() returns {unit_amount_cents,
    reliability} or None when no real quote exists.
    """

    def quote(self, supplier: dict, request: dict) -> dict | None:
        ...


def _positive_int(value: Any) -> int | None:
    """A usable quote field, or None. Booleans are ints in Python; they are not prices."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _reliability(value: Any) -> float | None:
    """0..1, or None when absent. A value above 1 is read as a percentage."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = float(value)
    if score > 1.0:
        score = score / 100.0
    return max(0.0, min(1.0, score))


class ApiQuoteSource:
    """Reads the quote the API puts on the supplier row.

    list_procurement_suppliers is gaining unit_amount_cents and reliability per supplier. Until
    then, and for any supplier missing either field, there is no quote: None, not a guess.
    """

    def quote(self, supplier: dict, request: dict) -> dict | None:
        unit = _positive_int(supplier.get(QUOTE_UNIT_KEY))
        reliability = _reliability(supplier.get(QUOTE_RELIABILITY_KEY))
        if unit is None or reliability is None:
            log.info("no quote for supplier %s: both %s and %s are required",
                     supplier.get("id"), QUOTE_UNIT_KEY, QUOTE_RELIABILITY_KEY)
            return None
        return {QUOTE_UNIT_KEY: unit, QUOTE_RELIABILITY_KEY: reliability}


class FakeQuoteSource:
    """TEST AND DRY-RUN DOUBLE - NOT A SOURCE OF REAL PRICES.

    Prices are invented here. Never wire this into the running agent: a fake quote would
    authorise a real PayPal payment.
    """

    def __init__(self, unit_amount_cents: int = 75, reliability: float = 0.9) -> None:
        self.unit_amount_cents = unit_amount_cents
        self.reliability = reliability

    def quote(self, supplier: dict, request: dict) -> dict | None:
        return {QUOTE_UNIT_KEY: self.unit_amount_cents,
                QUOTE_RELIABILITY_KEY: self.reliability}


def build_quote_source() -> QuoteSource:
    """The real source. The fake is reachable only by passing it in explicitly."""
    return ApiQuoteSource()


def request_quantity(request: dict) -> int:
    return _positive_int(request.get("quantity")) or 1


def milestone_total(request: dict) -> int | None:
    """What the milestone can pay: its amount plus any match. None when absent."""
    milestone = request.get("milestone") or {}
    amount = _positive_int(milestone.get("amount_cents"))
    if amount is None:
        return None
    match = milestone.get("match_amount_cents")
    if isinstance(match, bool) or not isinstance(match, int) or match < 0:
        match = 0
    return amount + match


def budget_cents(request: dict) -> int | None:
    return _positive_int(request.get("max_amount_cents"))


def score_quote(quote: dict, cheapest: int) -> tuple[float, dict]:
    """Lower unit price is better; higher reliability is better. Equal weight, no magic.

    The cheapest quote scores 1.0 on price and everything else is scored against it, so a
    supplier 10x the price still scores something instead of being floored at zero.
    """
    unit = quote[QUOTE_UNIT_KEY]
    reliability = quote[QUOTE_RELIABILITY_KEY]
    price_term = min(1.0, cheapest / unit)
    score = round(0.5 * price_term + 0.5 * reliability, 4)
    return score, {"price_term": round(price_term, 4), "reliability": reliability,
                   "unit_amount_cents": unit}


def choose_supplier(suppliers: list[dict],
                    quotes: dict[int, dict]) -> tuple[dict | None, list[dict]]:
    """The best quoted supplier and the scored table, highest score first.

    A supplier with no quote is not a candidate: there is no price to compare, and a default
    price would be an invented one. Ties break on the smaller unit price, then supplier id,
    so the same inputs always pick the same supplier.
    """
    candidates = [(s, quotes[s["id"]]) for s in suppliers if quotes.get(s.get("id"))]
    if not candidates:
        return None, []
    cheapest = min(q[QUOTE_UNIT_KEY] for _, q in candidates)
    scored = []
    for supplier, quote in candidates:
        score, factors = score_quote(quote, cheapest)
        scored.append({"supplier": supplier, "score": score, "factors": factors,
                       "unit_amount_cents": quote[QUOTE_UNIT_KEY]})
    scored.sort(key=lambda row: (-row["score"], row["unit_amount_cents"],
                                 row["supplier"]["id"]))
    return scored[0]["supplier"], scored


def line_items_for(request: dict, quote: dict, quantity: int) -> list[dict]:
    """One quoted line: the request description at the quoted unit price."""
    return [{"description": str(request.get("description") or "Purchase"),
             "quantity": quantity,
             "unit_amount_cents": quote[QUOTE_UNIT_KEY]}]


def line_items_sum(line_items: list[dict]) -> int:
    total = 0
    for line in line_items:
        quantity = line.get("quantity") or 0
        unit = line.get("unit_amount_cents") or 0
        if isinstance(quantity, bool) or isinstance(unit, bool):
            raise ValueError("a boolean is not a quantity or a price")
        total += int(quantity) * int(unit)
    return total


def is_approval_error(exc: BaseException) -> bool:
    """APPROVAL_REQUIRED, as a fallback only.

    McpUnavailable carries the server text and no status code, so the pay call cannot be told
    apart from any other refusal except by its message. Everything else is pre-checked before
    the call (see needs_approval), so this is the belt to that braces. If the MCP server ever
    grows a typed error, this helper is the one place to change.
    """
    return "APPROVAL_REQUIRED" in str(exc)


def needs_approval(amount_cents: int, limit: int = AUTO_APPROVE_CENTS) -> bool:
    return amount_cents > limit


class ProcurementAgent:
    def __init__(self, mcp=None, quote_source: QuoteSource | None = None, llm=None,
                 auto_approve_cents: int = AUTO_APPROVE_CENTS) -> None:
        self.mcp = mcp or build_client()
        self.quotes = quote_source or build_quote_source()
        self.llm = llm or build_llm()
        self.auto_approve_cents = auto_approve_cents

    async def run(self, procurement_id: int | None = None) -> dict:
        """Propose and pay one request, or every open one when no id is given.

        Answers {"runs": [...], "abstained": [...]}: each entry says what happened, so a caller
        never has to guess whether a purchase was made.
        """
        requests = await self.mcp.call("list_procurement_requests") or []
        if procurement_id is not None:
            requests = [r for r in requests if r.get("id") == procurement_id]
            if not requests:
                return {"runs": [], "abstained": [
                    {"procurement_id": procurement_id, "reason": "not open"}]}
        runs, abstained = [], []
        for request in requests:
            result = await self._one(request)
            (runs if result.get("proposed") else abstained).append(result)
        return {"runs": runs, "abstained": abstained}

    async def _one(self, request: dict) -> dict:
        trace: list[dict] = []

        def step(title: str, *, status: str = "ok", tool: str | None = None,
                 reason: str | None = None, ref: dict | None = None) -> None:
            item = {"seq": len(trace) + 1, "actor": "procurement-agent",
                    "step": "procurement", "status": status, "title": title}
            if tool:
                item["tool"] = tool
            if reason:
                item["reason"] = reason
            if ref:
                item["ref"] = ref
            trace.append(item)

        procurement_id = request.get("id")
        project = request.get("project") or {}
        quantity = request_quantity(request)
        ceiling = budget_cents(request)
        tranche = milestone_total(request)

        suppliers = await self.mcp.call("list_procurement_suppliers",
                                        project_id=project.get("id")) or []
        region = request.get("region")
        step("Found " + str(len(suppliers)) + " eligible suppliers"
             + (" in " + str(region) if region else ""),
             tool="list_procurement_suppliers", ref={"project_id": project.get("id")})

        quotes = {}
        unquoted = []
        for supplier in suppliers:
            quote = self.quotes.quote(supplier, request)
            if quote is None:
                unquoted.append(str(supplier.get("name")))
            else:
                quotes[supplier["id"]] = quote
        if unquoted:
            step("No quote for " + ", ".join(unquoted), status="skipped",
                 reason="not a candidate without a price")

        supplier, scored = choose_supplier(suppliers, quotes)
        if supplier is None:
            step("No supplier quote available", status="abstained",
                 reason="abstained rather than invent a price")
            return {"procurement_id": procurement_id, "proposed": False,
                    "reason": "no supplier quote available", "trace": trace}

        unit = quotes[supplier["id"]][QUOTE_UNIT_KEY]
        amount = unit * quantity
        step("Chose " + str(supplier.get("name")) + ": " + str(quantity) + " x "
             + str(unit) + " = " + str(amount), tool="score_quotes",
             ref={"supplier_id": supplier.get("id"), "amount_cents": amount})

        # Everything the API would refuse, refused here first, so a request that cannot be
        # paid is never proposed. The API still re-checks; this is not a replacement.
        if ceiling is not None and amount > ceiling:
            step(str(amount) + " is over the " + str(ceiling) + " asked for",
                 status="abstained", reason="over request")
            return {"procurement_id": procurement_id, "proposed": False,
                    "reason": "over request", "trace": trace}
        if tranche is not None and amount > tranche:
            step(str(amount) + " is over the milestone tranche of " + str(tranche),
                 status="abstained", reason="over milestone")
            return {"procurement_id": procurement_id, "proposed": False,
                    "reason": "over milestone", "trace": trace}

        line_items = line_items_for(request, quotes[supplier["id"]], quantity)
        if line_items_sum(line_items) != amount:
            # Cannot happen with one line, and must never be papered over if it does.
            raise ValueError("line items do not sum to the amount")

        rationale = self._rationale(request, supplier, amount, quantity, unit)
        decisions = {"trace": trace, "quotes": scored, "chosen": [
            {"supplier_id": supplier.get("id"), "supplier_name": supplier.get("name"),
             "amount_cents": amount, "unit_amount_cents": unit, "quantity": quantity}]}
        run = await self.mcp.call("record_procurement_run", decisions=decisions,
                                  report_text=rationale) or {}
        run_id = run.get("id")
        step("Recorded the run", tool="record_procurement_run", ref={"run_id": run_id})

        proposal = await self.mcp.call(
            "propose_procurement", procurement_id=procurement_id,
            supplier_id=supplier["id"], amount_cents=amount, line_items=line_items,
            rationale=rationale, run_id=run_id) or {}
        step("Proposed " + str(amount) + " to " + str(supplier.get("name")),
             tool="propose_procurement",
             ref={"procurement_id": procurement_id, "amount_cents": amount})

        outcome = {"procurement_id": procurement_id, "proposed": True,
                   "supplier_id": supplier["id"], "supplier_name": supplier.get("name"),
                   "amount_cents": amount, "run_id": run_id, "trace": trace,
                   "proposal": proposal}

        if needs_approval(amount, self.auto_approve_cents):
            # Above the automatic limit the API refuses to pay until an admin approves, so
            # stop with a proposal the admin can act on instead of provoking a 409.
            step(str(amount) + " is over the " + str(self.auto_approve_cents)
                 + " automatic limit: waiting for an admin", status="pending",
                 reason="APPROVAL_REQUIRED")
            return {**outcome, "status": "awaiting_approval"}

        try:
            paid = await self.mcp.call("pay_procurement",
                                       procurement_id=procurement_id) or {}
        except Exception as exc:
            if not is_approval_error(exc):
                raise
            step("PayPal refused without admin approval", status="pending",
                 reason="APPROVAL_REQUIRED")
            return {**outcome, "status": "awaiting_approval"}
        # paid is the API ProcurementOut: its "status" field is authoritative and enum-valued
        # (paid/failed/...). A missing answer is not a payment: say so rather than pass None on.
        paid_status = str(paid.get("status") or "unknown").lower()
        step("Paid " + str(supplier.get("name")) + " from the milestone",
             tool="pay_procurement",
             status="ok" if paid_status == "paid" else "pending",
             ref={"procurement_id": procurement_id, "status": paid_status})
        return {**outcome, "status": paid_status, "payment": paid}

    def _rationale(self, request: dict, supplier: dict, amount: int, quantity: int,
                   unit: int) -> str:
        """Why this supplier, in plain words. Never invents a fact about them."""
        parts = [str(supplier.get("name")) + " quotes " + str(unit) + " per unit, so "
                 + str(quantity) + " costs " + str(amount) + "."]
        region = supplier.get("region")
        if region:
            parts.append("Serves " + str(region) + ".")
        parts.append("Chosen on price and reliability from the quotes on file.")
        return " ".join(parts)
