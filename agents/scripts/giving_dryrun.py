"""Giving Agent dry run against real projects, a canned mandate and the real DeepSeek.

Reads only: search_projects plus the public /funding-history and /stories endpoints.
Writes are impossible by construction: the mandate run is never recorded, no donation is
requested, and DRY_RUN is forced on so the MCP client would block both anyway.

    FAKE_CORE=false DRY_RUN=true .venv/bin/python scripts/giving_dryrun.py

Prints no env values and never the token.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.giving import (          # noqa: E402
    MAX_PROJECTS,
    GivingAgent,
    days_since_last_funding,
    merge_weights,
    passes_hard_filters,
    reason_for,
    score_project,
)
from app.config import Settings           # noqa: E402
from app.core import build_core           # noqa: E402
from app.llm import LLM, LLMUnavailable, build_llm  # noqa: E402
from app.mcp_client import build_client   # noqa: E402

DRY_RUN_ID = 0

# Canned mandate: never read from the API.
MANDATE = {
    "id": 0,
    "monthly_budget_cents": 1000,
    "per_project_max_cents": 400,
    "approval_threshold_cents": 500,
    "funded_balance_cents": 1000,
    "categories": [],      # filled with the live projects' category ids
    "excluded_tags": [],
    "weight_overrides": None,
}

FACTORS = ("few_backers", "progress", "urgency", "evidence", "days_since_funded")


class CountingLLM(LLM):
    """The real DeepSeek, counting its calls. Thinking is off for text completions."""

    def __init__(self, cfg):
        super().__init__(cfg)
        self.calls = 0

    async def complete_json(self, system, user, schema):
        self.calls += 1
        return await super().complete_json(system, user, schema)

    async def complete_text(self, system, user):
        self.calls += 1
        return await super().complete_text(system, user)


def category_ids(projects: list[dict]) -> list[int]:
    ids: list[int] = []
    for project in projects:
        value = project.get("category_id")
        if isinstance(value, int) and value not in ids:
            ids.append(value)
    return ids


async def main() -> int:
    cfg = Settings().model_copy(update={"fake_core": False, "dry_run": True})

    print("DRY RUN. No mandate run is recorded and no donation is requested.")
    print("core api: " + cfg.core_api_url)
    print("model: " + cfg.deepseek_model + " (thinking: disabled)")
    print("")

    mcp = build_client(cfg)
    core = build_core(cfg)
    llm = build_llm(cfg)
    try:
        live = await mcp.call("search_projects", limit=100, sort="urgency")
        if not isinstance(live, list):
            print("FAILED: search_projects returned " + type(live).__name__)
            return 1

        mandate = dict(MANDATE)
        mandate["categories"] = category_ids(live)
        if not mandate["categories"]:
            print("FAILED: no live project has a category_id")
            return 1

        print("candidates available: " + str(len(live)))
        print("mandate categories: " + str(mandate["categories"]))
        print("")

        weights = merge_weights(mandate.get("weight_overrides"))
        budget = int(mandate["monthly_budget_cents"])
        balance = int(mandate["funded_balance_cents"])
        cap = int(mandate["per_project_max_cents"])
        excluded = set(mandate["excluded_tags"])

        seen: dict[int, dict] = {}
        for category_id in mandate["categories"]:
            found = await mcp.call(
                "search_projects",
                category_id=category_id,
                exclude_tags=sorted(excluded) or None,
                limit=100,
            )
            for project in found or []:
                seen.setdefault(int(project["id"]), project)

        candidates = []
        skipped: list[dict] = []
        for project in seen.values():
            if not passes_hard_filters(project):
                skipped.append({"project_id": project["id"], "reason": "hard_filter"})
                continue
            stories = await core.stories(int(project["id"]))
            history = await core.funding_history(int(project["id"]))
            score, factors = score_project(project, weights, bool(stories),
                                           days_since_last_funding(history))
            candidates.append({"project": project, "score": score, "factors": factors})

        candidates.sort(key=lambda c: (-c["score"], int(c["project"]["id"])))

        print("--- candidates (score is 0-100) ---")
        for cand in candidates:
            p = cand["project"]
            print(
                str(p["id"]) + "  " + str(p.get("title"))
                + "  score=" + str(cand["score"])
            )
            print("    " + "  ".join(k + "=" + str(cand["factors"][k]) for k in FACTORS))
        if not candidates:
            print("(none)")
        print("")

        chosen = []
        remaining = budget
        for cand in candidates:
            if len(chosen) >= MAX_PROJECTS:
                break
            p = cand["project"]
            room = (p.get("goal_cents") or 0) - (p.get("raised_cents") or 0)
            amount = min(cap, remaining, balance, room)
            if amount <= 0:
                skipped.append({"project_id": p["id"],
                                "reason": "no_room" if room <= 0 else "budget_exhausted"})
                continue
            chosen.append({"project": p, "amount": int(amount), "score": cand["score"],
                           "factors": cand["factors"]})
            remaining -= int(amount)
            balance -= int(amount)

        print("--- planned allocation (not sent) ---")
        for c in chosen:
            print(
                str(c["project"]["id"]) + "  " + str(c.get("title"))
                + "  " + str(c["amount"]) + " cents"
            )
        if not chosen:
            print("(nothing chosen)")
        print("unallocated: " + str(remaining) + " cents of " + str(budget))
        print("")

        print("--- skipped ---")
        for item in skipped:
            print(str(item["project_id"]) + "  " + str(item["reason"]))
        if not skipped:
            print("(none)")
        print("")

        facts = {
            "donor_budget_cents": mandate["monthly_budget_cents"],
            "planned": [
                {"title": c["project"].get("title"), "amount_cents": c["amount"],
                 "reason": reason_for(c["project"], c["factors"])}
                for c in chosen
            ],
            "skipped": skipped[:10],
        }
        system = (
            "You write a short monthly giving report to a donor. Use only the facts given. "
            "Call each gift planned. Never invent amounts, projects or outcomes."
        )
        from app.llm import data_block

        counting = CountingLLM(cfg)
        try:
            report = (await counting.complete_text(
                system, data_block("allocation", json.dumps(facts))
            )).strip()
        except LLMUnavailable as exc:
            report = "(LLM unavailable: " + str(exc) + ")"

        print("--- report text ---")
        print(report or "(empty)")
        print("")
        print("run id: " + str(DRY_RUN_ID) + " (DRY RUN)")
        print("llm calls: " + str(counting.calls))
    except Exception as exc:
        print("FAILED: " + type(exc).__name__ + ": " + str(exc))
        return 1
    finally:
        await mcp.aclose()
        await core.aclose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
