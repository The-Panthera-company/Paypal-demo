"""Projected match for the open round, recomputed every few minutes.

Render's free plan has no cron jobs and the service sleeps when idle, so two things keep
projections fresh: a background loop inside the API while it is awake, and the leaderboard
refreshing a stale projection when it is read (the first read after a sleep).
"""

import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.engine import run_round
from app.models import MatchResult, Round, RoundStatus

log = logging.getLogger(__name__)


def computed_at(db: Session, round_id: int, is_final: bool) -> datetime | None:
    at = db.scalar(
        select(func.max(MatchResult.computed_at)).where(
            MatchResult.round_id == round_id, MatchResult.is_final.is_(is_final)
        )
    )
    # SQLite hands back naive datetimes; they were written in UTC.
    return at.replace(tzinfo=timezone.utc) if at is not None and at.tzinfo is None else at


def refresh(db: Session, round_: Round) -> None:
    """Recompute and save the round's projection. Two refreshes at once: the loser keeps the winner's rows."""
    run_round(db, round_, is_final=False)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def refresh_if_stale(db: Session, round_: Round, max_age_seconds: int) -> None:
    if round_.status not in (RoundStatus.open, RoundStatus.closing):
        return
    at = computed_at(db, round_.id, is_final=False)
    if at is None or datetime.now(timezone.utc) - at >= timedelta(seconds=max_age_seconds):
        refresh(db, round_)


def run_loop(stop: threading.Event, interval_seconds: int) -> None:
    """Refresh the open round's projection every interval until `stop` is set."""
    while not stop.wait(interval_seconds):
        try:
            with SessionLocal() as db:
                round_ = db.scalar(select(Round).where(Round.status == RoundStatus.open))
                if round_ is not None:
                    refresh(db, round_)
        except Exception:  # never let one bad run kill the loop
            log.exception("Projection run failed")


def start(interval_seconds: int) -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=run_loop, args=(stop, interval_seconds), name="projections", daemon=True).start()
    return stop
