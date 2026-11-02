"""Matching rounds and the leaderboard."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Round, RoundStatus
from app.schemas import LeaderboardOut, RoundOut
from app.stubs import PLANNED, planned

router = APIRouter(prefix="/rounds", tags=["rounds"])


def _out(r: Round) -> RoundOut:
    return RoundOut(
        id=r.id,
        name=r.name,
        starts_at=r.starts_at,
        ends_at=r.ends_at,
        matching_pool_cents=r.matching_pool,
        currency=r.currency,
        project_cap_pct=r.project_cap_pct,
        floor_pct=r.floor_pct,
        per_person_cap_cents=r.per_person_cap,
        status=r.status,
    )


@router.get("/current", response_model=RoundOut, responses={404: {}})
def current_round(db: Session = Depends(get_db)):
    r = db.scalar(select(Round).where(Round.status.in_((RoundStatus.open, RoundStatus.closing))))
    if r is None:
        raise HTTPException(404, detail={"error": "NO_OPEN_ROUND", "message": "No round is open"})
    return _out(r)


@router.get("/{round_id}/leaderboard", response_model=LeaderboardOut, responses=PLANNED)
def leaderboard(round_id: int):
    """Projected match while the round is open (recomputed every 5 minutes); final after close."""
    planned("match projections")
