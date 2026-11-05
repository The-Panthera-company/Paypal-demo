"""Giving Agent: rule-based scoring and allocation, one MCP write per decision.

Section 5.1. The LLM only writes report_text from the allocation computed here.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ..core import Core, build_core
from ..llm import LLM, LLMUnavailable, build_llm, data_block
from ..mcp_client import build_client

log = logging.getLogger(__name__)

# Section 5.1 constants live here only.
WEIGHTS: dict[str, float] = {
    "few_backers": 35,
    "progress": 25,
    "urgency": 20,
    "evidence": 10,
    "days_since_funded": 10,
}
MAX_PROJECTS = 5
FEW_BACKERS_SCALE = 20
DAYS_SCALE = 30
LISTED_STATUSES = {"verified", "active"}
STOP_REJECTIONS = {"over_monthly_budget", "insufficient_balance"}

STATE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "giving_state.json"


def _ratio(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_project(project: dict, weights: dict, evidence: bool,
                  days_since: float | None) -> tuple[float, dict]:
    raised = project.get("raised_cents") or 0
    goal = project.get("goal_cents") or 0
    factors = {
        "few_backers": _ratio(1 - (project.get("backer_count") or 0) / FEW_BACKERS_SCALE),
        "progress": _ratio(raised / goal) if goal > 0 else 0.0,
        "urgency": _ratio(((project.get("urgency") or 1) - 1) / 4),
        "evidence": 1.0 if evidence else 0.0,
        "days_since_funded": 1.0 if days_since is None else _ratio(days_since / DAYS_SCALE),
    }
    total_w = sum(weights.get(k, 0) for k in factors)
    if total_w <= 0:
        return 0.0, factors
    raw = sum(weights.get(k, 0) * v for k, v in factors.items()) / total_w
    return round(100 * raw, 2), {k: round(v, 4) for k, v in factors.items()}


def passes_hard_filters(project: dict) -> bool:
    return (
        project.get("status") in LISTED_STATUSES
        and not project.get("matching_frozen", False)
        and (project.get("raised_cents") or 0) < (project.get("goal_cents") or 0)
    )


def days_since_last_funding(history: list) -> float | None:
    points = [p for p in history if isinstance(p, dict)]
    if len(points) < 2:
        return None
    rising = None
    prev = None
    for point in points:
        raised = point.get("raised_cents")
        if prev is not None and isinstance(raised, int) and raised > prev:
            rising = point
        prev = raised if isinstance(raised, int) else prev
    if rising is None:
        return None
    try:
        when = datetime.fromisoformat(str(rising.get("date")).replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - when).total_seconds() / 86400)


def merge_weights(overrides: dict | None) -> dict:
    weights = dict(WEIGHTS)
    for key, value in (overrides or {}).items():
        if key in weights and isinstance(value, (int, float)):
            weights[key] = float(value)
    return weights


def reason_detail(project: dict, factors: dict) -> str:
    """Rule-built explanation handed to the LLM, e.g. "few backers (1), 2% funded, urgency 4/5".

    Built from the same numbers that produced the score, so the report explains the
    decision instead of inventing a rationale.
    """
    backers = project.get("backer_count") or 0
    goal = project.get("goal_cents") or 0
    pct = int(100 * (project.get("raised_cents") or 0) / goal) if goal else 0
    bits = [
        "few backers (" + str(backers) + ")",
        str(pct) + "% funded",
        "urgency " + str(project.get("urgency") or 1) + "/5",
    ]
    if factors.get("evidence") == 1.0:
        bits.append("receipts uploaded")
    if factors.get("days_since_funded") == 1.0:
        bits.append("no funding in " + str(DAYS_SCALE) + "+ days")
    return ", ".join(bits)


def reason_for(project: dict, factors: dict) -> str:
    backers = project.get("backer_count") or 0
    goal = project.get("goal_cents") or 0
    pct = int(100 * (project.get("raised_cents") or 0) / goal) if goal else 0
    bits = [str(backers) + " backer" + ("" if backers == 1 else "s"), str(pct) + "% funded"]
    if factors.get("evidence") == 1.0:
        bits.append("receipts uploaded")
    if (project.get("urgency") or 1) >= 4:
        bits.append("urgency " + str(project.get("urgency")) + "/5")
    return ", ".join(bits)


class GivingAgent:
    def __init__(self, mcp=None, core=None, llm=None, state_path=None):
        self.mcp = mcp or build_client()
        self.core = core or build_core()
        self.llm = llm or build_llm()
        self.state_path = Path(state_path) if state_path else STATE_PATH

    def _read_state(self):
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return {}

    def _write_state(self, state):
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(state, indent=2))
        except OSError as exc:
            log.warning("could not persist giving state: %s", exc)

    def already_ran(self, mandate_id):
        return self._read_state().get(str(mandate_id)) == date.today().strftime("%Y-%m")

    def _mark_ran(self, mandate_id):
        state = self._read_state()
        state[str(mandate_id)] = date.today().strftime("%Y-%m")
        self._write_state(state)

    async def run(self, mandate_id, force=False):
        if not force and self.already_ran(mandate_id):
            return {"run_id": None, "chosen": [], "results": [], "report_text": "",
                    "skipped_run": "already_ran_this_month"}

        mandates = await self.mcp.call("list_active_mandates")
        mandate = next((m for m in mandates or [] if m.get("id") == mandate_id), None)
        if mandate is None:
            raise ValueError("no active mandate " + str(mandate_id))

        weights = merge_weights(mandate.get("weight_overrides"))
        budget = int(mandate.get("monthly_budget_cents") or 0)
        balance = int(mandate.get("funded_balance_cents") or 0)
        cap = int(mandate.get("per_project_max_cents") or 0)
        excluded = set(mandate.get("excluded_tags") or [])

        seen = {}
        for category_id in mandate.get("categories") or []:
            found = await self.mcp.call(
                "search_projects",
                category_id=category_id,
                exclude_tags=sorted(excluded) or None,
                limit=100,
            )
            for project in found or []:
                seen.setdefault(int(project["id"]), project)

        candidates = []
        skipped = []
        for project in seen.values():
            if not passes_hard_filters(project):
                skipped.append({"project_id": project["id"], "reason": "hard_filter"})
                continue
            stories = await self.core.stories(int(project["id"]))
            history = await self.core.funding_history(int(project["id"]))
            score, factors = score_project(project, weights, bool(stories),
                                           days_since_last_funding(history))
            candidates.append({"project": project, "score": score, "factors": factors})

        candidates.sort(key=lambda c: (-c["score"], int(c["project"]["id"])))

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

        report = await self._report(mandate, chosen, skipped)

        decisions = {
            "candidates": [{"project_id": c["project"]["id"], "score": c["score"],
                            "factors": c["factors"]} for c in candidates],
            "chosen": [{"project_id": c["project"]["id"], "amount_cents": c["amount"]}
                       for c in chosen],
            "skipped": skipped,
        }
        run = await self.mcp.call("record_mandate_run", mandate_id=mandate_id,
                                  decisions=decisions, report_text=report)
        run_id = (run or {}).get("id")

        results = []
        for c in chosen:
            reason = reason_for(c["project"], c["factors"])
            answer = await self.mcp.call(
                "request_checked_donation",
                mandate_run_id=run_id,
                project_id=c["project"]["id"],
                amount_cents=c["amount"],
                reason=reason,
            ) or {}
            results.append({"project_id": c["project"]["id"], "amount_cents": c["amount"],
                            **answer})
            rule = answer.get("rule_result")
            if answer.get("status") == "rejected" and rule in STOP_REJECTIONS:
                break
            if answer.get("status") == "rejected":
                await self.mcp.call(
                    "log_decision",
                    actor="giving-agent",
                    action="donation_skipped",
                    reason=answer.get("reason") or reason,
                    rule_result=rule,
                    inputs={"project_id": c["project"]["id"],
                            "amount_cents": c["amount"], "mandate_run_id": run_id},
                )

        self._mark_ran(mandate_id)
        return {"run_id": run_id, "chosen": decisions["chosen"], "results": results,
                "report_text": report}

    async def _report(self, mandate, chosen, skipped):
        facts = {
            "donor_budget_cents": mandate.get("monthly_budget_cents"),
            "planned": [
                {"title": c["project"].get("title"), "amount_cents": c["amount"],
                 "reason": reason_for(c["project"], c["factors"]),
                 "why": reason_detail(c["project"], c["factors"])}
                for c in chosen
            ],
            "skipped": skipped[:10],
        }
        system = (
            "You write a short monthly giving report to a donor. Use only the facts given. "
            "Call each gift planned. Never invent amounts, projects or outcomes. "
            "For each gift, explain in one clause why it was chosen, using that gift's "
            "\"why\" field. Never change, round or recompute an amount."
        )
        try:
            text = await self.llm.complete_text(system, data_block("allocation", json.dumps(facts)))
            if text:
                return text
        except LLMUnavailable:
            log.info("LLM unavailable, using template report")
        if not chosen:
            return "No project matched your mandate this month, so nothing was planned."
        head = "Planned " + str(len(chosen)) + " gift" + ("" if len(chosen) == 1 else "s") + " this month:"
        body = [
            "- " + str(c["project"].get("title")) + ": $" + format(c["amount"] / 100, ".2f")
            + " (" + reason_detail(c["project"], c["factors"]) + ")"
            for c in chosen
        ]
        return chr(10).join([head] + body)
