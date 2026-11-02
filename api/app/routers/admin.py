"""Admin console: verification queue, Watchdog cases, payouts, milestone holds, agent log, round close."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.models import (
    AuditLog,
    CaseStatus,
    Milestone,
    MilestoneStatus,
    Payout,
    Project,
    ProjectStatus,
    WatchdogCase,
    WebhookEvent,
)
from app.routers.catalogue import _summaries, milestone_out, project_detail
from app.routers.internal import case_out, release_milestone
from app.schemas import (
    AuditOut,
    CaseOut,
    CaseResolveIn,
    ErrorOut,
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

ERRORS = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"error": code, "message": message})


@router.get("/projects", response_model=list[ProjectSummary])
def review_queue(status: ProjectStatus = ProjectStatus.pending_review, db: Session = Depends(get_db)):
    projects = list(db.scalars(select(Project).where(Project.status == status).order_by(Project.created_at)))
    return _summaries(db, projects)


@router.post("/projects/{project_id}/verify", response_model=ProjectDetail, responses=ERRORS)
def verify_project(project_id: int, body: VerifyIn, db: Session = Depends(get_db)):
    """Approve lists the project (verified); reject sends it back to the applicant (draft)."""
    project = db.get(Project, project_id)
    if project is None:
        raise _error(404, "PROJECT_NOT_FOUND", "No such project")
    if project.status != ProjectStatus.pending_review:
        raise _error(409, "NOT_PENDING_REVIEW", f"Project is {project.status.value}")
    if body.approve:
        project.status = ProjectStatus.verified
        project.verified_by = "admin"
        project.verified_at = datetime.now(timezone.utc)
    else:
        project.status = ProjectStatus.draft
    db.add(AuditLog(actor="admin", action="project_verification", inputs={"project_id": project.id},
                    rule_result="approved" if body.approve else "rejected", reason=body.note))
    db.commit()
    return project_detail(db, project)


@router.get("/cases", response_model=list[CaseOut])
def list_cases(status: CaseStatus | None = CaseStatus.open, db: Session = Depends(get_db)):
    stmt = select(WatchdogCase).order_by(WatchdogCase.created_at.desc())
    if status is not None:
        stmt = stmt.where(WatchdogCase.status == status)
    return [case_out(c) for c in db.scalars(stmt)]


@router.post("/cases/{case_id}/resolve", response_model=CaseOut, responses=ERRORS)
def resolve_case(case_id: int, body: CaseResolveIn, db: Session = Depends(get_db)):
    """clear: a false alarm, matching resumes. confirm: the evidence's donor_ids count as one person
    in matching, and matching resumes. confirm + remove_project: the project is delisted and its
    matching stays frozen; refund its donations in PayPal and the refund webhooks update the totals."""
    case = db.get(WatchdogCase, case_id)
    if case is None:
        raise _error(404, "CASE_NOT_FOUND", "No such case")
    if case.status != CaseStatus.open:
        raise _error(409, "CASE_ALREADY_RESOLVED", f"Case is already {case.status.value}")
    if body.remove_project and body.action != "confirm":
        raise _error(422, "INVALID_RESOLUTION", "remove_project only goes with confirm")

    case.status = CaseStatus.cleared if body.action == "clear" else CaseStatus.confirmed
    case.resolved_by = "admin"
    project = db.get(Project, case.project_id)
    if body.remove_project:
        project.status = ProjectStatus.frozen
    else:
        db.flush()
        still_open = db.scalar(
            select(WatchdogCase.id).where(WatchdogCase.project_id == project.id, WatchdogCase.status == CaseStatus.open)
        )
        project.matching_frozen = still_open is not None
    result = "removed" if body.remove_project else case.status.value
    db.add(AuditLog(actor="admin", action="case_resolved", inputs={"case_id": case.id, "project_id": project.id},
                    rule_result=result, reason=body.note))
    db.commit()
    return case_out(case)


@router.get("/milestones/held", response_model=list[MilestoneOut])
def held_milestones(db: Session = Depends(get_db)):
    """Tranche requests the Milestone Agent sent to a human (failed check, open case or above threshold).
    The agent's summary and the failed checks are in the audit log (actor milestone-agent)."""
    held = db.scalars(select(Milestone).where(Milestone.status == MilestoneStatus.held).order_by(Milestone.id))
    return [milestone_out(m) for m in held]


@router.post("/milestones/{milestone_id}/review", response_model=MilestoneOut, responses=ERRORS)
def review_milestone(milestone_id: int, body: MilestoneReviewIn, db: Session = Depends(get_db)):
    """Approve releases the tranche; reject sends it back so the project can submit better evidence."""
    milestone = db.get(Milestone, milestone_id)
    if milestone is None:
        raise _error(404, "MILESTONE_NOT_FOUND", "No such milestone")
    if milestone.status != MilestoneStatus.held:
        raise _error(409, "MILESTONE_NOT_HELD", f"Milestone is {milestone.status.value}")
    if body.approve:
        release_milestone(db, milestone)
    else:
        milestone.status = MilestoneStatus.open
    db.add(AuditLog(actor="admin", action="milestone_review", inputs={"milestone_id": milestone.id},
                    rule_result="released" if body.approve else "sent_back", reason=body.note))
    db.commit()
    return milestone_out(milestone)


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
