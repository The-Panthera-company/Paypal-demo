"""Donor profile, report, Giving Agent mandate and gifts waiting for the donor's yes.

There is no login yet, so routes take the donor id; demo logins decide who is who.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Donor
from app.schemas import (
    ApprovalIn,
    DonationOut,
    DonorOut,
    DonorReport,
    DonorUpdate,
    MandateIn,
    MandateOut,
    MandateRunOut,
    PendingApproval,
)
from app.stubs import PLANNED, planned

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


@router.get("/{donor_id}/report", response_model=DonorReport, responses=PLANNED)
def donor_report(donor_id: int):
    """"Where your money went": gifts, match unlocked, impact updates and the agent's report."""
    planned("donor report")


@router.get("/{donor_id}/mandate", response_model=MandateOut, responses=PLANNED)
def get_mandate(donor_id: int):
    planned("mandates")


@router.put("/{donor_id}/mandate", response_model=MandateOut, responses=PLANNED)
def set_mandate(donor_id: int, body: MandateIn):
    """Create or replace the Giving Agent's rules. The budget is funded separately through PayPal."""
    planned("mandates")


@router.get("/{donor_id}/mandate/runs", response_model=list[MandateRunOut], responses=PLANNED)
def mandate_runs(donor_id: int):
    planned("mandates")


@router.get("/{donor_id}/pending-approvals", response_model=list[PendingApproval], responses=PLANNED)
def pending_approvals(donor_id: int):
    """Agent gifts above the donor's approval threshold."""
    planned("mandates")


@router.post(
    "/{donor_id}/pending-approvals/{donation_id}", response_model=DonationOut, responses=PLANNED
)
def decide_approval(donor_id: int, donation_id: int, body: ApprovalIn):
    planned("mandates")
