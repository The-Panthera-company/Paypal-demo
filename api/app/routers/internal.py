"""Endpoints for the agent service. Agents never hold PayPal credentials: every money action
comes through here, and the core API re-checks the rules before anything moves.

Every call that changes something writes an audit-log line with its inputs, rule result and reason.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import payouts
from app.auth import require_internal
from app.config import Settings, get_settings
from app.db import get_db
from app.mandates import check_gift
from app.models import (
    AuditLog,
    CaseStatus,
    Donation,
    DonationStatus,
    LedgerEntry,
    LedgerType,
    Mandate,
    MandateRun,
    Milestone,
    MilestoneStatus,
    Payout,
    Project,
    TargetType,
    WatchdogCase,
)
from app.money import to_paypal
from app.paypal import PayPalClient, get_paypal
from app.routers.donations import mark_captured
from app.routers.donors import mandate_out, run_out
from app.schemas import (
    ActiveMandate,
    AuditIn,
    AuditOut,
    CaseIn,
    CaseOut,
    CheckedDonationIn,
    CheckedDonationOut,
    ErrorOut,
    MandateRunIn,
    MandateRunOut,
    PayoutRequestIn,
    PayoutRequestOut,
)

router = APIRouter(prefix="/internal", tags=["internal (agents)"], dependencies=[Depends(require_internal)])

NOT_FOUND = {404: {"model": ErrorOut}}


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"error": code, "message": message})


def case_out(c: WatchdogCase) -> CaseOut:
    return CaseOut(
        id=c.id,
        project_id=c.project_id,
        rule=c.rule,
        evidence=c.evidence,
        status=c.status,
        frozen_at=c.frozen_at,
        resolved_by=c.resolved_by,
        created_at=c.created_at,
    )


@router.get("/mandates/active", response_model=list[ActiveMandate])
def active_mandates(db: Session = Depends(get_db)):
    """Mandates for the Giving Agent's run, with each donor's remaining funded balance."""
    mandates = db.scalars(select(Mandate).where(Mandate.active.is_(True)).order_by(Mandate.id))
    return [ActiveMandate(**mandate_out(db, m).model_dump()) for m in mandates]


@router.post("/mandate-runs", response_model=MandateRunOut, status_code=201, responses=NOT_FOUND)
def record_mandate_run(body: MandateRunIn, db: Session = Depends(get_db)):
    """The Giving Agent records its candidates, scores and choices before requesting donations."""
    if db.get(Mandate, body.mandate_id) is None:
        raise _error(404, "MANDATE_NOT_FOUND", "No such mandate")
    run = MandateRun(mandate_id=body.mandate_id, decisions=body.decisions, report_text=body.report_text)
    db.add(run)
    db.flush()
    db.add(
        AuditLog(
            actor="giving-agent",
            action="mandate_run",
            inputs={"mandate_id": body.mandate_id, "mandate_run_id": run.id},
            rule_result="recorded",
            reason=body.report_text,
        )
    )
    db.commit()
    return run_out(run)


_STATUS = {
    DonationStatus.captured: "recorded",
    DonationStatus.created: "awaiting_donor_approval",
    DonationStatus.failed: "rejected",
}


@router.post("/checked-donations", response_model=CheckedDonationOut, responses=NOT_FOUND)
def checked_donation(body: CheckedDonationIn, db: Session = Depends(get_db)):
    """Re-checks budget, per-project max, exclusions and project status, then records the gift
    (target_type AGENT) or parks it for the donor's approval. Never calls PayPal.

    Asking twice for the same run and project returns the first answer, so agent retries are safe.
    """
    run = db.get(MandateRun, body.mandate_run_id)
    if run is None:
        raise _error(404, "MANDATE_RUN_NOT_FOUND", "Record the run with POST /internal/mandate-runs first")
    earlier = db.scalar(
        select(Donation).where(Donation.mandate_run_id == run.id, Donation.project_id == body.project_id)
    )
    if earlier is not None:
        return CheckedDonationOut(
            status=_STATUS.get(earlier.status, "rejected"),
            donation_id=earlier.id,
            rule_result="duplicate",
            reason="Already requested in this run",
        )

    mandate = db.get(Mandate, run.mandate_id)
    project = db.get(Project, body.project_id)
    rule, why = check_gift(db, mandate, project, body.amount_cents)
    inputs = {"mandate_run_id": run.id, "project_id": body.project_id, "amount_cents": body.amount_cents}
    if rule != "ok":
        db.add(AuditLog(actor="giving-agent", action="checked_donation", inputs=inputs, rule_result=rule,
                        reason=f"{why}. Agent's reason: {body.reason}"))
        db.commit()
        return CheckedDonationOut(status="rejected", donation_id=None, rule_result=rule, reason=why)

    donation = Donation(
        donor_id=mandate.donor_id,
        target_type=TargetType.AGENT,
        project_id=project.id,
        amount=body.amount_cents,
        currency=mandate.currency,
        mandate_run_id=run.id,
    )
    db.add(donation)
    db.flush()
    if body.amount_cents > mandate.approval_threshold:
        status = "awaiting_donor_approval"
        why = f"Above the donor's {mandate.currency} {to_paypal(mandate.approval_threshold, mandate.currency)} approval threshold"
    else:
        mark_captured(db, donation, {})  # an internal move from the funded balance: no PayPal call
        status = "recorded"
    db.add(AuditLog(actor="giving-agent", action="checked_donation", inputs={**inputs, "donation_id": donation.id},
                    rule_result=status, reason=body.reason))
    db.commit()
    return CheckedDonationOut(status=status, donation_id=donation.id, rule_result="ok", reason=why)


@router.post("/watchdog/cases", response_model=CaseOut, status_code=201, responses=NOT_FOUND)
def open_case(body: CaseIn, db: Session = Depends(get_db)):
    """Watchdog rule hit: opens a case and freezes the project's matching (not its donations).

    The same rule firing again on a project with an open case returns that case instead of a new one.
    """
    project = db.get(Project, body.project_id)
    if project is None:
        raise _error(404, "PROJECT_NOT_FOUND", "No such project")
    existing = db.scalar(
        select(WatchdogCase).where(
            WatchdogCase.project_id == project.id,
            WatchdogCase.rule == body.rule,
            WatchdogCase.status == CaseStatus.open,
        )
    )
    if existing is not None:
        return case_out(existing)
    case = WatchdogCase(
        project_id=project.id, rule=body.rule, evidence=body.evidence, frozen_at=datetime.now(timezone.utc)
    )
    project.matching_frozen = True
    db.add(case)
    db.flush()
    db.add(AuditLog(actor="watchdog-agent", action="case_opened", inputs={"case_id": case.id, **body.model_dump()},
                    rule_result=body.rule, reason="Matching frozen until an admin resolves the case"))
    db.commit()
    return case_out(case)


def release_milestone(db: Session, paypal: PayPalClient, milestone: Milestone) -> Payout:
    """Mark a tranche released, book it, and send it through PayPal Payouts.

    The release is committed before PayPal is called, so a PayPal failure leaves a pending payout
    (send it again from the admin console) rather than undoing the release.
    """
    milestone.status = MilestoneStatus.released
    db.add(
        LedgerEntry(
            type=LedgerType.tranche,
            amount=milestone.amount + milestone.match_amount,
            currency=milestone.currency,
            project_id=milestone.project_id,
        )
    )
    payout = payouts.create_for_milestone(db, milestone)
    db.commit()
    payouts.send(db, paypal, payout)
    return payout


@router.post("/payout-requests", response_model=PayoutRequestOut, responses={**NOT_FOUND, 409: {"model": ErrorOut}})
def payout_request(
    body: PayoutRequestIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    paypal: PayPalClient = Depends(get_paypal),
):
    """Milestone Agent: all checks pass, no open Watchdog case and the tranche (including its match)
    is at most MILESTONE_AUTO_RELEASE_CENTS -> released and sent through PayPal Payouts;
    otherwise held for an admin."""
    milestone = db.get(Milestone, body.milestone_id)
    if milestone is None:
        raise _error(404, "MILESTONE_NOT_FOUND", "No such milestone")
    if milestone.status not in (MilestoneStatus.open, MilestoneStatus.evidence_submitted):
        raise _error(409, "MILESTONE_NOT_OPEN", f"Milestone is already {milestone.status.value}")

    problems = [name for name, ok in body.checks.model_dump().items() if not ok]
    total = milestone.amount + milestone.match_amount
    if total > settings.milestone_auto_release_cents:
        problems.append(f"above_threshold ({total} > {settings.milestone_auto_release_cents})")
    open_case = db.scalar(
        select(WatchdogCase.id).where(
            WatchdogCase.project_id == milestone.project_id, WatchdogCase.status == CaseStatus.open
        )
    )
    if open_case is not None:
        problems.append(f"open_watchdog_case ({open_case})")

    payout = None
    if problems:
        milestone.status = MilestoneStatus.held
        status, reason = "held_for_admin", "Held: " + ", ".join(problems)
    else:
        payout = release_milestone(db, paypal, milestone)
        status, reason = "released", "All checks passed, below threshold"
        if errors := {i.get("error") for i in payout.items if i.get("error")}:
            reason += f"; payout not sent yet: {', '.join(sorted(errors))}"
    db.add(
        AuditLog(
            actor="milestone-agent",
            action="payout_request",
            inputs={"milestone_id": milestone.id, "checks": body.checks.model_dump(), "amount_cents": total},
            rule_result=status,
            reason=f"{reason}. Summary: {body.summary}",
        )
    )
    db.commit()
    return PayoutRequestOut(status=status, payout_id=payout.id if payout else None, reason=reason)


@router.post("/audit", response_model=AuditOut, status_code=201)
def write_audit(body: AuditIn, db: Session = Depends(get_db)):
    """Agents log decisions that don't go through another endpoint (e.g. a skipped project)."""
    entry = AuditLog(**body.model_dump())
    db.add(entry)
    db.commit()
    return AuditOut(**body.model_dump(), id=entry.id, created_at=entry.created_at)
