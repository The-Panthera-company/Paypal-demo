"""Admin console: verification queue, Watchdog cases, payouts, milestone holds, agent log, round close."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, kill_switch, payouts, reconciliation, round_close
from app.money import to_paypal
from app.refunds import book_refund, refunded_total
from app.auth import require_admin
from app.config import Settings, get_settings
from app.db import get_db
from app.models import (
    AuditLog,
    CaseStatus,
    Donation,
    DonationStatus,
    Milestone,
    MilestoneStatus,
    Payout,
    PayoutAccount,
    Project,
    ProjectDocument,
    ProjectStatus,
    Round,
    RoundStatus,
    WatchdogCase,
    WebhookEvent,
)
from app.paypal import PayPalClient, PayPalError, get_paypal
from app.auth import new_owner_token
from app.routers.catalogue import _summaries, document_out, milestone_out, project_detail
from app.routers.internal import case_out, release_milestone
from app.routers.rounds import _out as round_out, leaderboard, _sponsored
from app.schemas import (
    AgentStatusOut,
    AgentToggleIn,
    AuditOut,
    AuditVerifyOut,
    CaseOut,
    CaseResolveIn,
    DocumentOut,
    ErrorOut,
    OwnerTokenOut,
    LeaderboardOut,
    MilestoneOut,
    MilestoneReviewIn,
    PayoutAccountIn,
    PayoutAccountOut,
    PayoutItem,
    PayoutOut,
    ProjectDetail,
    ProjectSummary,
    ReconciliationOut,
    RefundIn,
    RefundOut,
    RoundIn,
    RoundOut,
    RoundUpdateIn,
    SweepOut,
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
    audit.write(db, actor="admin", action="project_verification", inputs={"project_id": project.id},
                rule_result="approved" if body.approve else "rejected", reason=body.note)
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
    audit.write(db, actor="admin", action="case_resolved", inputs={"case_id": case.id, "project_id": project.id},
                rule_result=result, reason=body.note)
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
    audit.write(db, actor="admin", action="milestone_review", inputs={"milestone_id": milestone.id},
                rule_result="released" if body.approve else "sent_back", reason=body.note)
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
    audit.write(db, actor="admin", action="payout_account_set", inputs={"project_id": project_id},
                rule_result="set", reason=None)
    db.commit()
    return PayoutAccountOut(project_id=project_id, paypal_email=account.paypal_email)


@router.get("/reconciliation", response_model=ReconciliationOut)
def reconciliation_report(db: Session = Depends(get_db)):
    """Money in and out, and every check that our records add up. `ok` is false when any issue is an error."""
    return reconciliation.report(db)


@router.post("/reconciliation/sweep", response_model=SweepOut)
def sweep_orders(db: Session = Depends(get_db), paypal: PayPalClient = Depends(get_paypal)):
    """Settle PayPal orders our capture route never finished: asks PayPal for each order still open
    after 30 minutes and captures, records or closes it."""
    return reconciliation.sweep(db, paypal)


@router.get("/audit-log", response_model=list[AuditOut], response_model_exclude_unset=True)
def audit_log(
    actor: str | None = Query(None, description="e.g. giving-agent, milestone-agent, watchdog-agent"),
    include_hash: bool = Query(
        False,
        description="Include each row's seq, prev_hash and hash for independent chain checks.",
    ),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """The agent log view: every action with its inputs, rule result and reason.

    Pass include_hash=true to also see the audit hash chain columns.
    """
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    rows = []
    for a in db.scalars(stmt):
        data = {
            "id": a.id,
            "actor": a.actor,
            "action": a.action,
            "inputs": a.inputs,
            "rule_result": a.rule_result,
            "reason": a.reason,
            "created_at": a.created_at,
        }
        if include_hash:
            data.update(seq=a.seq, prev_hash=a.prev_hash, hash=a.hash)
        rows.append(AuditOut(**data))
    return rows


@router.get("/audit-log/verify", response_model=AuditVerifyOut)
def verify_audit_log(db: Session = Depends(get_db)):
    """Recompute the audit hash chain and report the first row that no longer matches.

    An edited, deleted or reordered row is reported by id and the check stops there.
    """
    return audit.verify(db)


@router.get("/agents/status", response_model=AgentStatusOut)
def agent_status(db: Session = Depends(get_db)):
    """Whether the global agent kill switch is on, and who last moved it."""
    return kill_switch.status(db)


@router.post("/agents/pause", response_model=AgentStatusOut)
def pause_agents(body: AgentToggleIn, db: Session = Depends(get_db)):
    """Stop every money-moving agent route. Audit stays writable so agents can log the pause."""
    kill_switch.pause(db, body.reason)
    audit.write(
        db,
        actor="admin",
        action="agents_paused",
        inputs={"reason": body.reason},
        rule_result="paused",
        reason=body.reason,
    )
    db.commit()
    return kill_switch.status(db)


@router.post("/agents/resume", response_model=AgentStatusOut)
def resume_agents(body: AgentToggleIn, db: Session = Depends(get_db)):
    """Turn the global agent kill switch back off."""
    kill_switch.resume(db, body.reason)
    audit.write(
        db,
        actor="admin",
        action="agents_resumed",
        inputs={"reason": body.reason},
        rule_result="resumed",
        reason=body.reason,
    )
    db.commit()
    return kill_switch.status(db)


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


def _aware(at: datetime) -> datetime:
    return at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at


def _check_round(db: Session, round_: Round) -> None:
    """Dates in order, and no other unfinished round overlapping it (one round runs at a time)."""
    start, end = _aware(round_.starts_at), _aware(round_.ends_at)
    if end <= start:
        raise _error(422, "BAD_DATES", "ends_at must be after starts_at")
    for other in db.scalars(select(Round).where(Round.status != RoundStatus.closed, Round.id != (round_.id or 0))):
        if start < _aware(other.ends_at) and _aware(other.starts_at) < end:
            raise _error(409, "ROUND_OVERLAP", f"Overlaps {other.name} (round {other.id}, {other.status.value})")


@router.post("/rounds", response_model=RoundOut, status_code=201,
             responses={409: {"model": ErrorOut}, 422: {"model": ErrorOut, "description": "Dates out of order or in the past"}})
def create_round(body: RoundIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """Schedule a round. It opens on its own at starts_at (now, if that has passed) and closes at ends_at."""
    now = datetime.now(timezone.utc)
    if _aware(body.ends_at) <= now:
        raise _error(422, "BAD_DATES", "ends_at is in the past")
    round_ = Round(
        name=body.name, starts_at=body.starts_at, ends_at=body.ends_at, matching_pool=body.matching_pool_cents,
        currency=settings.currency, project_cap_pct=body.project_cap_pct, floor_pct=body.floor_pct,
        per_person_cap=body.per_person_cap_cents, status=RoundStatus.scheduled,
    )
    _check_round(db, round_)
    db.add(round_)
    db.flush()
    audit.write(db, actor="admin", action="round_created", inputs={"round_id": round_.id, **body.model_dump(mode="json")},
                rule_result="scheduled", reason=None)
    round_close.open_due(db, now)
    db.commit()
    return round_out(round_)


@router.patch("/rounds/{round_id}", response_model=RoundOut,
              responses={**ERRORS, 422: {"model": ErrorOut, "description": "Dates out of order, or the pool below what sponsors added"}})
def update_round(round_id: int, body: RoundUpdateIn, db: Session = Depends(get_db)):
    """Change a scheduled or open round: name, dates, pool, cap, floor or per-person cap. A closed
    round is final. An open round keeps its start, and its pool can't drop below what sponsors added."""
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise _error(404, "ROUND_NOT_FOUND", "No such round")
    if round_.status in (RoundStatus.closing, RoundStatus.closed):
        raise _error(409, "ROUND_CLOSED", f"The round is {round_.status.value}")
    changes = body.model_dump(exclude_unset=True)
    if round_.status == RoundStatus.open and "starts_at" in changes:
        raise _error(409, "ROUND_STARTED", "An open round's start can't change")
    if changes.get("matching_pool_cents") is not None and changes["matching_pool_cents"] < _sponsored(db, round_.id):
        raise _error(422, "POOL_BELOW_SPONSORED", "The pool can't be less than what sponsors added")
    fields = {"matching_pool_cents": "matching_pool", "per_person_cap_cents": "per_person_cap"}
    for key, value in changes.items():
        if value is not None:
            setattr(round_, fields.get(key, key), value)
    _check_round(db, round_)
    if round_.status == RoundStatus.open and _aware(round_.ends_at) <= datetime.now(timezone.utc):
        raise _error(422, "BAD_DATES", "ends_at is in the past (close the round instead)")
    audit.write(db, actor="admin", action="round_updated", inputs={"round_id": round_.id, **body.model_dump(mode="json", exclude_unset=True)},
                rule_result=round_.status.value, reason=None)
    round_close.open_due(db)
    db.commit()
    return round_out(round_)


@router.get("/projects/{project_id}/documents", response_model=list[DocumentOut], responses={404: {"model": ErrorOut}})
def project_documents(project_id: int, db: Session = Depends(get_db)):
    """Everything the project uploaded (registration and plan for verification, milestone evidence)."""
    if db.get(Project, project_id) is None:
        raise _error(404, "PROJECT_NOT_FOUND", "No such project")
    docs = db.scalars(select(ProjectDocument).where(ProjectDocument.project_id == project_id).order_by(ProjectDocument.id))
    return [document_out(d) for d in docs]


@router.post("/projects/{project_id}/owner-token", response_model=OwnerTokenOut, responses={404: {"model": ErrorOut}})
def reset_owner_token(project_id: int, db: Session = Depends(get_db)):
    """A new X-Project-Token for the project's owner (lost token, or a seeded project). The old one stops working."""
    project = db.get(Project, project_id)
    if project is None:
        raise _error(404, "PROJECT_NOT_FOUND", "No such project")
    token, project.owner_token_hash = new_owner_token()
    audit.write(db, actor="admin", action="owner_token_reset", inputs={"project_id": project_id}, rule_result="reset",
                reason=None)
    db.commit()
    return OwnerTokenOut(project_id=project_id, owner_token=token)


@router.post("/donations/{donation_id}/refund", response_model=RefundOut,
             responses={**ERRORS, 422: {"model": ErrorOut, "description": "More than is left to refund"},
                        502: {"model": ErrorOut}})
def refund_donation(donation_id: int, body: RefundIn, db: Session = Depends(get_db),
                    paypal: PayPalClient = Depends(get_paypal)):
    """Refund a PayPal-paid donation in full or in part. A completed refund is booked now (a full
    refund takes the gift out of totals and matching, and a sponsor's POOL contribution out of the
    open round's pool); a pending one is booked when PayPal's PAYMENT.CAPTURE.REFUNDED webhook arrives.
    Agent gifts from a funded balance never went through PayPal on their own and can't be refunded here."""
    donation = db.get(Donation, donation_id)
    if donation is None:
        raise _error(404, "DONATION_NOT_FOUND", "No such donation")
    if donation.status != DonationStatus.captured or not donation.paypal_capture_id:
        raise _error(409, "NOT_REFUNDABLE", f"Only captured PayPal payments can be refunded (this one is {donation.status.value})")
    left = donation.amount - refunded_total(db, donation.id)
    amount = body.amount_cents or left
    if amount > left:
        raise _error(422, "REFUND_TOO_LARGE", f"Only {left} cents are left to refund")
    done = refunded_total(db, donation.id)
    try:
        refund = paypal.refund_capture(
            donation.paypal_capture_id,
            amount=None if amount == donation.amount else to_paypal(amount, donation.currency),
            currency=donation.currency, note=body.reason, request_id=f"refund-{donation.id}-{done}-{amount}",
        )
    except PayPalError as e:
        raise HTTPException(502, detail={"error": e.issue, "message": "PayPal could not refund the payment"})
    status = refund.get("status", "PENDING")
    if status == "COMPLETED":
        book_refund(db, donation, amount, refund.get("id"))
    audit.write(db, actor="admin", action="refund", inputs={"donation_id": donation.id, "amount_cents": amount,
                                                           "refund_id": refund.get("id")},
                rule_result=status.lower(), reason=body.reason)
    db.commit()
    return RefundOut(donation_id=donation.id, refund_id=refund.get("id", ""), paypal_status=status, amount_cents=amount,
                     refunded_total_cents=refunded_total(db, donation.id), donation_status=donation.status)
