"""Admin console: verification queue, Watchdog cases, payouts, milestone holds, agent log, round close."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import payouts, round_close
from app.auth import require_admin
from app.config import Settings, get_settings
from app.db import get_db
from app.models import (
    AuditLog,
    CaseStatus,
    Milestone,
    MilestoneStatus,
    Payout,
    PayoutAccount,
    Project,
    ProjectStatus,
    Round,
    WatchdogCase,
    WebhookEvent,
)
from app.paypal import PayPalClient, PayPalError, get_paypal
from app.routers.catalogue import _summaries, milestone_out, project_detail
from app.routers.internal import case_out, release_milestone
from app.routers.rounds import leaderboard
from app.schemas import (
    AuditOut,
    CaseOut,
    CaseResolveIn,
    ErrorOut,
    LeaderboardOut,
    MilestoneOut,
    MilestoneReviewIn,
    PayoutAccountIn,
    PayoutAccountOut,
    PayoutItem,
    PayoutOut,
    ProjectDetail,
    ProjectSummary,
    VerifyIn,
    WebhookEventOut,
)

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
    # A round waiting in `closing` for this case can finish now.
    if round_close.close_due(db):
        db.commit()
    return case_out(case)


@router.get("/milestones/held", response_model=list[MilestoneOut])
def held_milestones(db: Session = Depends(get_db)):
    """Tranche requests the Milestone Agent sent to a human (failed check, open case or above threshold).
    The agent's summary and the failed checks are in the audit log (actor milestone-agent)."""
    held = db.scalars(select(Milestone).where(Milestone.status == MilestoneStatus.held).order_by(Milestone.id))
    return [milestone_out(m) for m in held]


@router.post("/milestones/{milestone_id}/review", response_model=MilestoneOut, responses=ERRORS)
def review_milestone(
    milestone_id: int,
    body: MilestoneReviewIn,
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
):
    """Approve releases the tranche; reject sends it back so the project can submit better evidence."""
    milestone = db.get(Milestone, milestone_id)
    if milestone is None:
        raise _error(404, "MILESTONE_NOT_FOUND", "No such milestone")
    if milestone.status != MilestoneStatus.held:
        raise _error(409, "MILESTONE_NOT_HELD", f"Milestone is {milestone.status.value}")
    db.add(AuditLog(actor="admin", action="milestone_review", inputs={"milestone_id": milestone.id},
                    rule_result="released" if body.approve else "sent_back", reason=body.note))
    if body.approve:
        release_milestone(db, paypal, milestone)
    else:
        milestone.status = MilestoneStatus.open
    db.commit()
    return milestone_out(milestone)


def payout_out(p: Payout) -> PayoutOut:
    return PayoutOut(
        id=p.id,
        sender_batch_id=p.sender_batch_id,
        currency=p.currency,
        status=p.status,
        paypal_batch_id=p.paypal_batch_id,
        items=[PayoutItem(**i) for i in p.items or []],
    )


@router.get("/payouts", response_model=list[PayoutOut])
def list_payouts(db: Session = Depends(get_db)):
    return [payout_out(p) for p in db.scalars(select(Payout).order_by(Payout.id.desc()))]


def _payout_or_404(db: Session, payout_id: int) -> Payout:
    payout = db.get(Payout, payout_id)
    if payout is None:
        raise _error(404, "PAYOUT_NOT_FOUND", "No such payout")
    return payout


@router.post("/payouts/{payout_id}/send", response_model=PayoutOut, responses=ERRORS)
def send_payout(payout_id: int, db: Session = Depends(get_db), paypal: PayPalClient = Depends(get_paypal)):
    """Send a batch that is still pending (no payout account at release, or PayPal refused it).
    Same sender_batch_id, so it can never pay twice."""
    payout = _payout_or_404(db, payout_id)
    if payout.paypal_batch_id:
        raise _error(409, "ALREADY_SENT", "PayPal already accepted this batch; refresh it or retry failed items")
    payouts.send(db, paypal, payout)
    db.commit()
    return payout_out(payout)


@router.post("/payouts/{payout_id}/refresh", response_model=PayoutOut, responses={**ERRORS, 502: {"model": ErrorOut}})
def refresh_payout(payout_id: int, db: Session = Depends(get_db), paypal: PayPalClient = Depends(get_paypal)):
    """Ask PayPal for the batch's current status, in case a webhook was missed."""
    payout = _payout_or_404(db, payout_id)
    if not payout.paypal_batch_id:
        raise _error(409, "NOT_SENT", "This batch hasn't been sent to PayPal")
    try:
        payouts.apply_batch(db, payout, paypal.get_payout(payout.paypal_batch_id))
    except PayPalError as e:
        raise _error(502, e.issue, "PayPal could not return the batch")
    db.commit()
    return payout_out(payout)


@router.post("/payouts/{payout_id}/retry", response_model=PayoutOut, status_code=201, responses=ERRORS)
def retry_payout(payout_id: int, db: Session = Depends(get_db), paypal: PayPalClient = Depends(get_paypal)):
    """Failed, returned or blocked items go out again in a new batch with a new sender_batch_id."""
    payout = _payout_or_404(db, payout_id)
    new = payouts.retry(db, payout)
    if new is None:
        raise _error(409, "NOTHING_TO_RETRY", "No failed, returned or blocked items in this batch")
    db.commit()
    payouts.send(db, paypal, new)
    db.commit()
    return payout_out(new)


@router.get("/projects/{project_id}/payout-account", response_model=PayoutAccountOut, responses=ERRORS)
def get_payout_account(project_id: int, db: Session = Depends(get_db)):
    account = db.get(PayoutAccount, project_id)
    if account is None:
        raise _error(404, "NO_PAYOUT_ACCOUNT", "This project has no payout account")
    return PayoutAccountOut(project_id=project_id, paypal_email=account.paypal_email)


@router.put("/projects/{project_id}/payout-account", response_model=PayoutAccountOut, responses=ERRORS)
def set_payout_account(project_id: int, body: PayoutAccountIn, db: Session = Depends(get_db)):
    """The PayPal email the project's tranches are paid to."""
    if db.get(Project, project_id) is None:
        raise _error(404, "PROJECT_NOT_FOUND", "No such project")
    account = db.get(PayoutAccount, project_id) or PayoutAccount(project_id=project_id, paypal_email="")
    account.paypal_email = body.paypal_email
    db.add(account)
    db.add(AuditLog(actor="admin", action="payout_account_set", inputs={"project_id": project_id},
                    rule_result="set", reason=None))
    db.commit()
    return PayoutAccountOut(project_id=project_id, paypal_email=account.paypal_email)


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


@router.post("/rounds/{round_id}/close", response_model=LeaderboardOut, responses=ERRORS)
def close_round(
    round_id: int,
    early: bool = Query(False, description="Close before the round's end time (e.g. for the demo)"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Computes final results and adds each project's match to its next milestone tranche.

    Waits while any Watchdog case is open: the round moves to `closing`, the answer is 409
    WAITING_FOR_CASES, and it closes on its own (background loop) once the cases are resolved.
    Rounds also close on their own at their end time; this route is for closing now.
    """
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise _error(404, "ROUND_NOT_FOUND", "No such round")
    try:
        closed = round_close.close(db, round_, early=early)
    except round_close.CloseError as e:
        raise _error(409, e.code, e.message)
    db.commit()
    if not closed:
        cases = round_close.open_cases(db)
        raise _error(409, "WAITING_FOR_CASES", f"Resolve the open Watchdog cases first: {cases}")
    return leaderboard(round_id, db, settings)
