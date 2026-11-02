"""Admin console: verification queue, Watchdog cases, payouts, milestone holds, agent log, round close."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.models import AuditLog, CaseStatus, Payout, Project, ProjectStatus, WatchdogCase, WebhookEvent
from app.routers.catalogue import _summaries
from app.schemas import (
    AuditOut,
    CaseOut,
    CaseResolveIn,
    LeaderboardOut,
    MilestoneOut,
    MilestoneReviewIn,
    PayoutItem,
    PayoutOut,
    ProjectDetail,
    ProjectSummary,
    VerifyIn,
    WebhookEventOut,
)
from app.stubs import PLANNED, planned

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/projects", response_model=list[ProjectSummary])
def review_queue(status: ProjectStatus = ProjectStatus.pending_review, db: Session = Depends(get_db)):
    projects = list(db.scalars(select(Project).where(Project.status == status).order_by(Project.created_at)))
    return _summaries(db, projects)


@router.post("/projects/{project_id}/verify", response_model=ProjectDetail, responses=PLANNED)
def verify_project(project_id: int, body: VerifyIn):
    planned("project verification")


@router.get("/cases", response_model=list[CaseOut])
def list_cases(status: CaseStatus | None = CaseStatus.open, db: Session = Depends(get_db)):
    stmt = select(WatchdogCase).order_by(WatchdogCase.created_at.desc())
    if status is not None:
        stmt = stmt.where(WatchdogCase.status == status)
    return [
        CaseOut(
            id=c.id,
            project_id=c.project_id,
            rule=c.rule,
            evidence=c.evidence,
            status=c.status,
            frozen_at=c.frozen_at,
            resolved_by=c.resolved_by,
            created_at=c.created_at,
        )
        for c in db.scalars(stmt)
    ]


@router.post("/cases/{case_id}/resolve", response_model=CaseOut, responses=PLANNED)
def resolve_case(case_id: int, body: CaseResolveIn):
    planned("watchdog case resolution")


@router.get("/milestones/held", response_model=list[MilestoneOut], responses=PLANNED)
def held_milestones():
    """Tranche requests the Milestone Agent sent to a human (failed check or above threshold)."""
    planned("milestone payouts")


@router.post("/milestones/{milestone_id}/review", response_model=MilestoneOut, responses=PLANNED)
def review_milestone(milestone_id: int, body: MilestoneReviewIn):
    planned("milestone payouts")


@router.get("/payouts", response_model=list[PayoutOut])
def list_payouts(db: Session = Depends(get_db)):
    return [
        PayoutOut(
            id=p.id,
            sender_batch_id=p.sender_batch_id,
            currency=p.currency,
            status=p.status,
            paypal_batch_id=p.paypal_batch_id,
            items=[PayoutItem(**i) for i in p.items or []],
        )
        for p in db.scalars(select(Payout).order_by(Payout.created_at.desc()))
    ]


@router.get("/audit-log", response_model=list[AuditOut])
def audit_log(
    actor: str | None = Query(None, description="e.g. giving-agent, milestone-agent, watchdog-agent"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """The agent log view: every action with its inputs, rule result and reason."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    return [
        AuditOut(
            id=a.id,
            actor=a.actor,
            action=a.action,
            inputs=a.inputs,
            rule_result=a.rule_result,
            reason=a.reason,
            created_at=a.created_at,
        )
        for a in db.scalars(stmt)
    ]


@router.get("/webhook-events", response_model=list[WebhookEventOut])
def webhook_events(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    """Recent PayPal webhook deliveries and what we did with each; for checking the live setup."""
    return [
        WebhookEventOut(
            id=e.id, event_type=e.event_type, resource_id=e.resource_id, result=e.result, received_at=e.received_at
        )
        for e in db.scalars(select(WebhookEvent).order_by(WebhookEvent.received_at.desc()).limit(limit))
    ]


@router.post("/rounds/{round_id}/close", response_model=LeaderboardOut, responses=PLANNED)
def close_round(round_id: int):
    """Waits for open Watchdog cases, computes final results, adds each match to the next tranche."""
    planned("round close")
