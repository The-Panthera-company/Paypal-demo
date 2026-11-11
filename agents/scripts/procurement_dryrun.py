#!/usr/bin/env python
"""Procurement Agent dry run: a demo request priced from FakeQuoteSource.

    FAKE_CORE=true DRY_RUN=true .venv/bin/python scripts/procurement_dryrun.py

The request is the demo one: 40 books at 75c, so 30.00 USD, asked of Nakuru Books &
Stationery. Quotes come from FakeQuoteSource, which INVENTS prices; it is only ever used
here and in the tests. Paying and proposing go through the MCP layer, where DRY_RUN blocks
every mutating call, so this prints what the agent WOULD propose and pay without moving money.

Against the real API nothing changes in the database. Against a real core the same run with
DRY_RUN=false would propose and pay; do not run it that way by accident.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.procurement import (          # noqa: E402
    FakeQuoteSource,
    ProcurementAgent,
)
from app.config import settings               # noqa: E402
from app.mcp_client import FakeMcpClient, build_client  # noqa: E402

QUANTITY = 40
UNIT_CENTS = 75

NAKURU = {"id": 3, "name": "Nakuru Books & Stationery", "categories": ["Education"],
          "tags": ["books", "literacy"], "region": "Nakuru"}

DEMO_REQUEST = {
    "id": 12,
    "description": "40 copies of the Grade 3 reading set",
    "quantity": QUANTITY,
    "max_amount_cents": 3_500,
    "project": {"id": 1, "title": "Lanet Library", "goal_cents": 600_000,
                "tags": ["books", "literacy"], "region": "Nakuru"},
    "milestone": {"id": 7, "title": "Buy 40 books", "amount_cents": 3_000,
                  "match_amount_cents": 0, "currency": "USD", "status": "open"},
    "project_title": "Lanet Library",
    "milestone_title": "Buy 40 books",
    "goal_cents": 600_000,
    "tags": ["books", "literacy"],
    "region": "Nakuru",
}


def demo_mcp() -> FakeMcpClient:
    """The demo request and one eligible supplier. Never the network."""
    return FakeMcpClient({
        "list_procurement_requests": [DEMO_REQUEST],
        "list_procurement_suppliers": [NAKURU],
    })


async def main() -> int:
    cfg = settings()
    dry = cfg.dry_run
    if not dry:
        print("DRY_RUN is false: this script would move money. Set DRY_RUN=true.")
        return 2

    mcp = demo_mcp()
    agent = ProcurementAgent(
        mcp=mcp,
        quote_source=FakeQuoteSource(unit_amount_cents=UNIT_CENTS, reliability=0.9),
    )

    out = await agent.run(DEMO_REQUEST["id"])

    for item in out["runs"]:
        print(json.dumps({k: item[k] for k in
                          ("procurement_id", "supplier_name", "amount_cents", "status", "run_id")},
                         indent=2))
        print("trace:")
        for step in item["trace"]:
            print("  " + str(step["seq"]) + ". [" + step["status"] + "] " + step["title"]
                  + ("  <- " + step["reason"] if step.get("reason") else ""))
    for item in out["abstained"]:
        print("abstained on " + str(item["procurement_id"]) + ": " + str(item["reason"]))

    proposed = [a for n, a in mcp.calls if n == "propose_procurement"]
    paid = [a for n, a in mcp.calls if n == "pay_procurement"]
    expected = UNIT_CENTS * QUANTITY
    ok = (len(proposed) == 1 and proposed[0]["supplier_id"] == NAKURU["id"]
          and proposed[0]["amount_cents"] == expected and len(paid) == 1)
    print()
    print("expected " + str(QUANTITY) + " x " + str(UNIT_CENTS) + " = " + str(expected)
          + " to " + NAKURU["name"] + ", pay called once")
    print("got      propose x" + str(len(proposed)) + " pay x" + str(len(paid)))
    print("OK" if ok else "MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
