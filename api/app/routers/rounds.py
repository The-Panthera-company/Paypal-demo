"""Matching rounds and the leaderboard."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import projections
from app.config import Settings, get_settings
from app.db import get_db
from app.models import MatchResult, Project, Round, RoundStatus
from app.routers.catalogue import LISTED, _summaries
from app.donor_board import donor_board
from app.schemas import DonorBoardOut, ErrorOut, LeaderboardOut, LeaderboardRow, RoundOut

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


@router.get("/{round_id}/leaderboard", response_model=LeaderboardOut, responses={404: {"model": ErrorOut}})
def leaderboard(round_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """Projected match while the round is open (recomputed every 5 minutes); final once the round closes.

    Projects whose matching the Watchdog froze are listed with a match of 0 and `matching_frozen: true`.
    """
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise HTTPException(404, detail={"error": "ROUND_NOT_FOUND", "message": "No such round"})

    is_final = projections.computed_at(db, round_id, is_final=True) is not None
    if not is_final:
        projections.refresh_if_stale(db, round_, settings.projection_interval_seconds or 300)
    results = {
        m.project_id: m
        for m in db.scalars(
            select(MatchResult).where(MatchResult.round_id == round_id, MatchResult.is_final.is_(is_final))
        )
    }
    projects = list(
        db.scalars(
            select(Project).where(
                Project.id.in_(results)
                | (Project.status.in_(LISTED) & Project.matching_frozen.is_(True))
            )
        )
    )
    summaries = {s.id: s for s in _summaries(db, projects)}
    rows = sorted(
        (
            LeaderboardRow(
                rank=0,
                project_id=p.id,
                title=p.title,
                category=summaries[p.id].category,
                backer_count=summaries[p.id].backer_count,
                raised_cents=summaries[p.id].raised_cents,
                score=results[p.id].score if p.id in results else 0.0,
                floor_cents=results[p.id].floor_amount if p.id in results else 0,
                crowd_cents=results[p.id].crowd_amount if p.id in results else 0,
                match_cents=results[p.id].final_amount if p.id in results else 0,
                capped=results[p.id].capped if p.id in results else False,
                matching_frozen=p.matching_frozen,
            )
            for p in projects
        ),
        key=lambda r: (-r.match_cents, -r.score, r.project_id),
    )
    for rank, row in enumerate(rows, start=1):
        row.rank = rank
    return LeaderboardOut(
        round_id=round_id,
        is_final=is_final,
        computed_at=projections.computed_at(db, round_id, is_final) or datetime.now(timezone.utc),
        currency=round_.currency,
        rows=rows,
    )


@router.get("/{round_id}/donors", response_model=DonorBoardOut, responses={404: {"model": ErrorOut}})
def donor_leaderboard(round_id: int, me: int | None = None, db: Session = Depends(get_db)):
    """Donor ladders for the round: given, matching unlocked, multiplier, reach, agent-given, impact points.
    Names only for donors who opted in; `me` marks the caller's own row (demo: no login yet)."""
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise HTTPException(404, detail={"error": "ROUND_NOT_FOUND", "message": "No such round"})
    return donor_board(db, round_, me)
