"""Donor profile, report, Giving Agent mandate and gifts waiting for the donor's yes.

There is no login yet, so routes take the donor id; demo logins decide who is who.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import reports
from app.config import Settings, get_settings
from app.db import get_db
from app.mandates import check_gift, funded_balance, weight_problems
from app.models import AuditLog, Category, Donation, DonationStatus, Donor, Mandate, MandateRun, Project, TargetType
from app.money import to_paypal
from app.routers.donations import donation_out, mark_captured
from app.schemas import (
    ApprovalIn,
    DonationOut,
    DonorOut,
    DonorReport,
    DonorUpdate,
    ErrorOut,
    MandateIn,
    MandateOut,
    MandateRunOut,
    PendingApproval,
)

router = APIRouter(prefix="/donors", tags=["donors"])


def _donor_or_404(db: Session, donor_id: int) -> Donor:
    donor = db.get(Donor, donor_id)
    if donor is None:
        raise HTTPException(404, detail={"error": "DONOR_NOT_FOUND", "message": "No such donor"})
    return donor


def _out(d: Donor) -> DonorOut:
    return DonorOut(
        id=d.id,
        display_name=d.display_name,
        is_guest=d.is_guest,
        show_on_leaderboard=d.show_on_leaderboard,
        interests=d.interests,
    )


@router.get("/{donor_id}", response_model=DonorOut, responses={404: {}})
def get_donor(donor_id: int, db: Session = Depends(get_db)):
    return _out(_donor_or_404(db, donor_id))


@router.patch("/{donor_id}", response_model=DonorOut, responses={404: {}})
def update_donor(donor_id: int, body: DonorUpdate, db: Session = Depends(get_db)):
    """Interests step at sign-up and the leaderboard opt-in."""
    donor = _donor_or_404(db, donor_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(donor, field, value)
    db.commit()
    return _out(donor)


@router.get("/{donor_id}/report", response_model=DonorReport, responses={404: {"model": ErrorOut}})
def donor_report(donor_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """"Where your money went": gifts (newest first; agent budget top-ups left out), the matching
    each project gift unlocked, impact updates from projects the donor backed, and the agent's
    latest report. Matching is final once the round closes, projected before that."""
    return reports.donor_report(db, _donor_or_404(db, donor_id), settings.currency)


def mandate_out(db: Session, m: Mandate) -> MandateOut:
    return MandateOut(
        id=m.id,
        donor_id=m.donor_id,
        currency=m.currency,
        monthly_budget_cents=m.monthly_budget,
        categories=m.categories or [],
        excluded_tags=m.excluded_tags or [],
        per_project_max_cents=m.per_project_max,
        approval_threshold_cents=m.approval_threshold,
        weight_overrides=m.weight_overrides,
        active=m.active,
        funded_balance_cents=funded_balance(db, m.donor_id),
    )


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"error": code, "message": message})


def _mandate(db: Session, donor_id: int) -> Mandate | None:
    return db.scalar(select(Mandate).where(Mandate.donor_id == donor_id))


@router.get("/{donor_id}/mandate", response_model=MandateOut, responses={404: {"model": ErrorOut}})
def get_mandate(donor_id: int, db: Session = Depends(get_db)):
    _donor_or_404(db, donor_id)
    m = _mandate(db, donor_id)
    if m is None:
        raise _error(404, "NO_MANDATE", "This donor has not set up the Giving Agent")
    return mandate_out(db, m)


@router.put(
    "/{donor_id}/mandate", response_model=MandateOut, responses={404: {"model": ErrorOut}, 422: {"model": ErrorOut}}
)
def set_mandate(
    donor_id: int, body: MandateIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
):
    """Create or replace the Giving Agent's rules. The budget is funded separately through PayPal:
    `POST /donations/orders` with `target_type: AGENT` and no project tops it up."""
    _donor_or_404(db, donor_id)
    known = set(db.scalars(select(Category.id).where(Category.id.in_(body.categories))))
    if missing := sorted(set(body.categories) - known):
        raise _error(422, "CATEGORY_NOT_FOUND", f"No such categories: {missing}")
    if body.per_project_max_cents > body.monthly_budget_cents:
        raise _error(422, "INVALID_MANDATE", "Per-project max can't be more than the monthly budget")
    if problems := weight_problems(body.weight_overrides):
        raise _error(422, "INVALID_WEIGHTS", "; ".join(problems))

    m = _mandate(db, donor_id) or Mandate(donor_id=donor_id, currency=settings.currency)
    m.monthly_budget = body.monthly_budget_cents
    m.categories = body.categories
    m.excluded_tags = body.excluded_tags
    m.per_project_max = body.per_project_max_cents
    m.approval_threshold = body.approval_threshold_cents
    m.weight_overrides = body.weight_overrides
    m.active = body.active
    db.add(m)
    db.commit()
    return mandate_out(db, m)


@router.get("/{donor_id}/mandate/runs", response_model=list[MandateRunOut])
def mandate_runs(donor_id: int, db: Session = Depends(get_db)):
    """The agent's runs for this donor, newest first: candidates, scores, choices and the report."""
    _donor_or_404(db, donor_id)
    m = _mandate(db, donor_id)
    if m is None:
        return []
    runs = db.scalars(select(MandateRun).where(MandateRun.mandate_id == m.id).order_by(MandateRun.id.desc()))
    return [run_out(r) for r in runs]


def run_out(r: MandateRun) -> MandateRunOut:
    return MandateRunOut(
        id=r.id, mandate_id=r.mandate_id, run_at=r.run_at, decisions=r.decisions, report_text=r.report_text
    )


def _pending(donor_id: int):
    return select(Donation).where(
        Donation.donor_id == donor_id,
        Donation.target_type == TargetType.AGENT,
        Donation.mandate_run_id.is_not(None),
        Donation.status == DonationStatus.created,
    )


@router.get("/{donor_id}/pending-approvals", response_model=list[PendingApproval])
def pending_approvals(donor_id: int, db: Session = Depends(get_db)):
    """Agent gifts above the donor's approval threshold."""
    _donor_or_404(db, donor_id)
    m = _mandate(db, donor_id)
    threshold = f"{m.currency} {to_paypal(m.approval_threshold, m.currency)}" if m else "approval"
    out = []
    for d in db.scalars(_pending(donor_id).order_by(Donation.id)):
        project = db.get(Project, d.project_id)
        out.append(
            PendingApproval(
                donation_id=d.id,
                project_id=d.project_id,
                project_title=project.title if project else "",
                amount_cents=d.amount,
                reason=f"Above your {threshold} approval threshold",
            )
        )
    return out


@router.post(
    "/{donor_id}/pending-approvals/{donation_id}",
    response_model=DonationOut,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}},
)
def decide_approval(donor_id: int, donation_id: int, body: ApprovalIn, db: Session = Depends(get_db)):
    """Yes records the gift after re-checking the mandate (it may have changed since); no cancels it."""
    donation = db.scalar(_pending(donor_id).where(Donation.id == donation_id))
    if donation is None:
        raise _error(404, "APPROVAL_NOT_FOUND", "No gift waiting for this donor's approval")
    if not body.approve:
        donation.status = DonationStatus.failed
        db.add(
            AuditLog(
                actor="donor",
                action="agent_gift_declined",
                inputs={"donation_id": donation.id},
                rule_result="declined",
                reason="Donor said no",
            )
        )
        db.commit()
        return donation_out(donation)

    project = db.get(Project, donation.project_id)
    rule, why = check_gift(db, _mandate(db, donor_id), project, donation.amount, exclude_id=donation.id)
    db.add(
        AuditLog(
            actor="donor", action="agent_gift_approved", inputs={"donation_id": donation.id}, rule_result=rule, reason=why
        )
    )
    if rule != "ok":
        donation.status = DonationStatus.failed
        db.commit()
        raise _error(409, rule.upper(), f"The gift no longer fits the mandate: {why}")
    mark_captured(db, donation, {})
    db.commit()
    return donation_out(donation)
