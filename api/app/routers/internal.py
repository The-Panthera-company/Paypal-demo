"""Endpoints for the agent service. Agents never hold PayPal credentials: every money action
comes through here, and the core API re-checks the rules before anything moves.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_internal
from app.db import get_db
from app.models import AuditLog
from app.schemas import (
    ActiveMandate,
    AuditIn,
    AuditOut,
    CaseIn,
    CaseOut,
    CheckedDonationIn,
    CheckedDonationOut,
    MandateRunIn,
    MandateRunOut,
    PayoutRequestIn,
    PayoutRequestOut,
)
from app.stubs import PLANNED, planned

router = APIRouter(prefix="/internal", tags=["internal (agents)"], dependencies=[Depends(require_internal)])


@router.get("/mandates/active", response_model=list[ActiveMandate], responses=PLANNED)
def active_mandates():
    """Mandates for the Giving Agent's run, with each donor's remaining funded balance."""
    planned("mandates")


@router.post("/mandate-runs", response_model=MandateRunOut, status_code=201, responses=PLANNED)
def record_mandate_run(body: MandateRunIn):
    """The Giving Agent records its candidates, scores and choices before requesting donations."""
    planned("mandates")


@router.post("/checked-donations", response_model=CheckedDonationOut, responses=PLANNED)
def checked_donation(body: CheckedDonationIn):
    """Re-checks budget, per-project max, exclusions and project status, then records the gift
    (target_type AGENT) or parks it for the donor's approval. Never calls PayPal."""
    planned("checked donations")


@router.post("/payout-requests", response_model=PayoutRequestOut, responses=PLANNED)
def payout_request(body: PayoutRequestIn):
    """Milestone Agent: all checks pass and below threshold -> PayPal payout; otherwise held for an admin."""
    planned("milestone payouts")


@router.post("/watchdog/cases", response_model=CaseOut, status_code=201, responses=PLANNED)
def open_case(body: CaseIn):
    """Watchdog rule hit: opens a case and freezes the project's matching (not its donations)."""
    planned("watchdog cases")


@router.post("/audit", response_model=AuditOut, status_code=201)
def write_audit(body: AuditIn, db: Session = Depends(get_db)):
    """Agents log decisions that don't go through another endpoint (e.g. a skipped project)."""
    entry = AuditLog(**body.model_dump())
    db.add(entry)
    db.commit()
    return AuditOut(**body.model_dump(), id=entry.id, created_at=entry.created_at)
