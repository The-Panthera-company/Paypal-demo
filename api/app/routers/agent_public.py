"""Public, read-only view of what the agents did.

Only the fields on these response models leave the API: raw ``decisions``, audit
``inputs`` and every donor identifier stay inside the core API. The web can poll
``/agents/activity`` without a token; the responses are safe to cache for 5 seconds.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.demo import DEMO_MANDATE_ID
from app.models import AuditLog, Donation, MandateRun, Milestone, Procurement, Project, Supplier, WatchdogCase
from app.schemas import (
    AgentActivityOut,
    AgentRunChoice,
    AgentRunOut,
    AgentRunSkip,
    ErrorOut,
    TraceStep,
)

router = APIRouter(prefix="/agents", tags=["agents (public)"])

# The only audit actors shown in the public feed. Donor and system rows stay private.
PUBLIC_ACTORS = ("giving-agent", "milestone-agent", "watchdog-agent", "procurement-agent", "admin")
PROCUREMENT_AGENT = "procurement-agent"


def _public_run(run: MandateRun | None) -> bool:
    """The demo mandate's Giving Agent runs, and Procurement Agent runs (they belong to no donor)."""
    return run is not None and (run.mandate_id == DEMO_MANDATE_ID or run.agent == PROCUREMENT_AGENT)

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Generic results are statuses, not the rule that decided something.
_GENERIC_RESULTS = {
    "ok", "recorded", "released", "pending", "created", "processing",
    "awaiting_donor_approval", "held_for_admin", "sent_back", "reset",
    "duplicate", "success", "processed", "completed", "confirmed", "cleared",
    "denied", "cancelled", "returned", "set", "approved", "rejected",
    "scheduled", "open", "closed",
}


def _error(code: str, message: str) -> HTTPException:
    return HTTPException(404, detail={"error": code, "message": message})


def _safe_text(value: Any, limit: int = 500) -> str | None:
    """Redact email addresses and cap the length."""
    if value is None:
        return None
    text = _EMAIL.sub("[redacted]", str(value))
    return text[:limit]


def _private_key(key: Any) -> bool:
    name = str(key).lower()
    return (
        name in {"receiver", "is_guest", "show_on_leaderboard", "interests"}
        or "donor" in name
        or "payer" in name
        or "email" in name
        or "balance" in name
    )


def _safe(value: Any) -> Any:
    """Recursively drop donor/payer fields and redact email addresses."""
    if isinstance(value, dict):
        return {key: _safe(item) for key, item in value.items() if not _private_key(key)}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, str):
        return _EMAIL.sub("[redacted]", value)
    return value


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _cache(response: Response) -> None:
    """Allow a 5-second cache: the web polls every 2 seconds and this keeps it cheap."""
    response.headers["Cache-Control"] = "public, max-age=5"


def _decisions(run: MandateRun) -> dict:
    return run.decisions if isinstance(run.decisions, dict) else {}


def _titles(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return dict(db.execute(select(Project.id, Project.title).where(Project.id.in_(ids))).all())


def _trace(run: MandateRun) -> list[TraceStep]:
    raw = _decisions(run).get("trace")
    if not isinstance(raw, list):
        return []
    steps: list[TraceStep] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        steps.append(
            TraceStep(
                seq=_as_int(item.get("seq")) or index + 1,
                at=_at(item.get("at")),
                actor=_safe_text(item.get("actor"), 60),
                step=_safe_text(item.get("step"), 80) or "step",
                tool=_safe_text(item.get("tool"), 80),
                status=_safe_text(item.get("status"), 30) or "ok",
                title=_safe_text(item.get("title"), 240) or "Step",
                input=_safe(item.get("input")),
                result=_safe(item.get("result")),
                rule=_safe_text(item.get("rule"), 80),
                reason=_safe_text(item.get("reason"), 500),
                ref=_safe(item.get("ref")) if isinstance(item.get("ref"), dict) else None,
            )
        )
    return sorted(steps, key=lambda step: step.seq)


def _chosen_suppliers(db: Session, run: MandateRun, raw: list) -> list[AgentRunChoice]:
    """A Procurement Agent run chooses suppliers, not projects: {supplier_id, amount_cents} and
    optionally procurement_id or project_id. The project comes from the entry, its purchase, or
    the purchase this run proposed. Only the supplier's name is shown, never its PayPal email."""
    items = [item for item in raw if isinstance(item, dict)]
    supplier_ids = {_as_int(item.get("supplier_id")) for item in items} - {None}
    purchase_ids = {_as_int(item.get("procurement_id")) for item in items} - {None}
    suppliers = {s.id: s.name for s in db.scalars(select(Supplier).where(Supplier.id.in_(supplier_ids)))}
    purchases = {p.id: p for p in db.scalars(select(Procurement).where(
        (Procurement.run_id == run.id) | Procurement.id.in_(purchase_ids)))}
    of_run = [p for p in purchases.values() if p.run_id == run.id]

    resolved = []
    for item in items:
        purchase = purchases.get(_as_int(item.get("procurement_id")) or 0) or (of_run[0] if len(of_run) == 1 else None)
        project_id = _as_int(item.get("project_id")) or (purchase.project_id if purchase else None)
        supplier_id = _as_int(item.get("supplier_id")) or (purchase.supplier_id if purchase else None)
        if supplier_id is None and project_id is None:
            continue
        amount = _as_int(item.get("amount_cents")) or (purchase.amount_cents if purchase else None) or 0
        resolved.append((project_id, supplier_id, amount, item))
    titles = _titles(db, {pid for pid, *_ in resolved if pid is not None})
    missing = {sid for _, sid, *_ in resolved if sid is not None and sid not in suppliers}
    if missing:
        suppliers.update({s.id: s.name for s in db.scalars(select(Supplier).where(Supplier.id.in_(missing)))})

    chosen = []
    for project_id, supplier_id, amount, item in resolved:
        supplier = suppliers.get(supplier_id) if supplier_id is not None else None
        supplier = supplier or _safe_text(item.get("supplier_name") or item.get("title"), 160)
        project = titles.get(project_id) if project_id is not None else None
        title = " for ".join(part for part in (supplier, project) if part) or None
        chosen.append(AgentRunChoice(project_id=project_id, title=title, amount_cents=amount,
                                     supplier_id=supplier_id, supplier_name=supplier))
    return chosen


def _chosen(db: Session, run: MandateRun, decisions: dict) -> list[AgentRunChoice]:
    raw = decisions.get("chosen")
    if not isinstance(raw, list):
        return []
    if run.agent == PROCUREMENT_AGENT:
        return _chosen_suppliers(db, run, raw)
    ids: set[int] = set()
    for item in raw:
        if isinstance(item, dict) and (project_id := _as_int(item.get("project_id"))) is not None:
            ids.add(project_id)
    titles = _titles(db, ids)
    chosen: list[AgentRunChoice] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        project_id = _as_int(item.get("project_id"))
        if project_id is None:
            continue
        chosen.append(
            AgentRunChoice(
                project_id=project_id,
                title=titles.get(project_id) or _safe_text(item.get("title"), 160),
                amount_cents=_as_int(item.get("amount_cents")) or 0,
            )
        )
    return chosen


def _skipped(db: Session, decisions: dict) -> list[AgentRunSkip]:
    raw = decisions.get("skipped")
    if not isinstance(raw, list):
        return []
    ids: set[int] = set()
    for item in raw:
        if isinstance(item, dict) and (project_id := _as_int(item.get("project_id"))) is not None:
            ids.add(project_id)
    titles = _titles(db, ids)
    skipped: list[AgentRunSkip] = []
    for item in raw:
        if not isinstance(item, dict):
            reason = _safe_text(item, 300)
            if reason:
                skipped.append(AgentRunSkip(reason=reason))
            continue
        project_id = _as_int(item.get("project_id"))
        skipped.append(
            AgentRunSkip(
                project_id=project_id,
                title=titles.get(project_id) if project_id is not None else _safe_text(item.get("title"), 160),
                reason=_safe_text(item.get("reason"), 300),
            )
        )
    return skipped


def _run_out(db: Session, run: MandateRun) -> AgentRunOut:
    decisions = _decisions(run)
    return AgentRunOut(
        id=run.id,
        agent=run.agent or "giving-agent",
        run_at=run.run_at,
        report_text=_safe_text(run.report_text, 4000),
        trace=_trace(run),
        chosen=_chosen(db, run, decisions),
        skipped=_skipped(db, decisions),
    )


def _status(action: str, result: str | None) -> str:
    value = (result or "").lower()
    if action in {"donation_skipped", "payout_failed"} or "fail" in action:
        return "blocked"
    if action == "case_opened":
        return "pending"  # a case needs an admin
    if action == "checked_donation" and value not in {"recorded", "awaiting_donor_approval", "duplicate", "ok", ""}:
        return "blocked"  # a refused gift is logged with the rule that blocked it, e.g. over_monthly_budget
    if value in {"awaiting_donor_approval", "held_for_admin", "pending", "created", "processing"}:
        return "pending"
    if value in {"rejected", "failed", "error", "blocked", "mismatch", "unmatched", "denied", "returned"}:
        return "blocked"
    return "ok"


def _rule(result: str | None) -> str | None:
    value = (result or "").strip()
    return value if value and value.lower() not in _GENERIC_RESULTS else None


def _title(row: AuditLog, project_title: str | None) -> str:
    project = project_title or "a project"
    action = row.action
    result = row.rule_result or ""
    rule = _rule(result)
    status = _status(action, result)

    if action == "mandate_run":
        title = "Giving Agent recorded a run"
    elif action == "mandate_run_summary":
        title = "Giving Agent finished a run"
    elif action == "checked_donation":
        if status == "blocked":
            title = f"Agent gift to {project} blocked"
        elif status == "pending":
            title = f"Agent gift to {project} waiting for the donor"
        else:
            title = f"Agent gift recorded for {project}"
    elif action == "donation_skipped":
        title = f"Agent skipped {project}"
    elif action == "case_opened":
        title = f"Watchdog opened a {rule or 'rule'} case for {project}"
    elif action == "case_resolved":
        title = f"Admin {result or 'resolved'} a case for {project}"
    elif action == "payout_request":
        title = f"Milestone tranche for {project} {result.replace('_', ' ') or 'checked'}"
    elif action == "milestone_review":
        title = f"Admin {result.replace('_', ' ') or 'reviewed'} a tranche for {project}"
    elif action == "payout_sent":
        title = f"Payout sent for {project}"
    elif action == "payout_failed":
        title = f"Payout failed for {project}"
    elif action == "owner_token_reset":
        title = f"Admin reset the owner token for {project}"
    elif action == "refund":
        title = f"Admin refunded a donation to {project}"
    else:
        title = f"{row.actor.replace('-', ' ').title()}: {action.replace('_', ' ')}"
        if result:
            title += f" ({result})"

    if rule and rule.lower() not in title.lower():
        title += f" ({rule})"
    # Admin notes can contain free text about a person; agent reasons are rule-built and useful.
    if row.actor != "admin" and row.reason:
        detail = _safe_text(row.reason, 120)
        if detail:
            title += f" - {detail}"
    return title[:240]


def _activity(db: Session, rows: list[AuditLog]) -> list[AgentActivityOut]:
    inputs = [row.inputs if isinstance(row.inputs, dict) else {} for row in rows]

    milestone_ids = {mid for data in inputs if (mid := _as_int(data.get("milestone_id"))) is not None}
    donation_ids = {did for data in inputs if (did := _as_int(data.get("donation_id"))) is not None}
    case_ids = {cid for data in inputs if (cid := _as_int(data.get("case_id"))) is not None}

    milestone_project = dict(
        db.execute(select(Milestone.id, Milestone.project_id).where(Milestone.id.in_(milestone_ids))).all()
    ) if milestone_ids else {}
    donation_project = dict(
        db.execute(select(Donation.id, Donation.project_id).where(Donation.id.in_(donation_ids))).all()
    ) if donation_ids else {}
    case_project = dict(
        db.execute(select(WatchdogCase.id, WatchdogCase.project_id).where(WatchdogCase.id.in_(case_ids))).all()
    ) if case_ids else {}

    resolved: list[tuple[AuditLog, int | None, int | None]] = []
    for row, data in zip(rows, inputs):
        project_id = _as_int(data.get("project_id"))
        if project_id is None and (milestone_id := _as_int(data.get("milestone_id"))) is not None:
            project_id = milestone_project.get(milestone_id)
        if project_id is None and (donation_id := _as_int(data.get("donation_id"))) is not None:
            project_id = donation_project.get(donation_id)
        if project_id is None and (case_id := _as_int(data.get("case_id"))) is not None:
            project_id = case_project.get(case_id)
        run_id = _as_int(data.get("mandate_run_id")) or _as_int(data.get("run_id"))
        resolved.append((row, project_id, run_id))

    titles = _titles(db, {project_id for _, project_id, _ in resolved if project_id is not None})
    return [
        AgentActivityOut(
            id=row.id,
            at=row.created_at,
            actor=row.actor,
            action=row.action,
            title=_title(row, titles.get(project_id) if project_id is not None else None),
            status=_status(row.action, row.rule_result),
            rule=_rule(row.rule_result),
            project_id=project_id,
            project_title=titles.get(project_id) if project_id is not None else None,
            run_id=run_id,
        )
        for row, project_id, run_id in resolved
    ]


@router.get("/runs", response_model=list[AgentRunOut])
def list_agent_runs(
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Newest agent runs, with the same safe projection: the demo mandate's Giving Agent runs and
    the Procurement Agent's runs."""
    runs = list(
        db.scalars(
            select(MandateRun)
            .where((MandateRun.mandate_id == DEMO_MANDATE_ID) | (MandateRun.agent == PROCUREMENT_AGENT))
            .order_by(MandateRun.run_at.desc(), MandateRun.id.desc())
            .limit(limit)
        )
    )
    _cache(response)
    return [_run_out(db, run) for run in runs]


@router.get(
    "/runs/{run_id}",
    response_model=AgentRunOut,
    responses={404: {"model": ErrorOut, "description": "No run with that id"}},
)
def get_agent_run(run_id: int, response: Response, db: Session = Depends(get_db)):
    """One agent run (a demo Giving Agent run or a Procurement Agent run) with its ordered trace,
    chosen projects and skipped projects."""
    run = db.get(MandateRun, run_id)
    if not _public_run(run):
        raise _error("RUN_NOT_FOUND", "No such agent run")
    _cache(response)
    return _run_out(db, run)


@router.get("/activity", response_model=list[AgentActivityOut])
def agent_activity(
    response: Response,
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
):
    """Recent agent and admin actions, newest first. Pass before_id for the next page."""
    stmt = select(AuditLog).where(AuditLog.actor.in_(PUBLIC_ACTORS))
    if before_id is not None:
        stmt = stmt.where(AuditLog.id < before_id)
    rows = list(db.scalars(stmt.order_by(AuditLog.id.desc()).limit(limit)))
    _cache(response)
    return _activity(db, rows)
