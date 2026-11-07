"""Global agent kill switch, stored in system_flags.

The switch is deliberately independent of any mandate or donor: an admin can stop every
money-moving agent route with one request. ``/internal/audit`` is not guarded, so an agent
can still record that it was stopped.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SystemFlag

PAUSED = "agents_paused"
REASON = "reason"
SINCE = "since"
UPDATED_BY = "updated_by"


def _value(db: Session, key: str) -> str | None:
    row = db.get(SystemFlag, key)
    return row.value if row is not None else None


def _set(db: Session, key: str, value: str | None) -> None:
    row = db.get(SystemFlag, key)
    if row is None:
        db.add(SystemFlag(key=key, value=value, updated_at=datetime.now(timezone.utc)))
    else:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    db.flush()


def is_paused(db: Session) -> bool:
    return (_value(db, PAUSED) or "").lower() == "true"


def status(db: Session) -> dict:
    since_raw = _value(db, SINCE)
    since = None
    if since_raw:
        try:
            since = datetime.fromisoformat(since_raw)
        except ValueError:
            since = None
    return {
        "paused": is_paused(db),
        "reason": _value(db, REASON),
        "since": since,
        "updated_by": _value(db, UPDATED_BY),
    }


def pause(db: Session, reason: str, updated_by: str = "admin") -> dict:
    now = datetime.now(timezone.utc)
    _set(db, PAUSED, "true")
    _set(db, REASON, reason)
    _set(db, SINCE, now.isoformat())
    _set(db, UPDATED_BY, updated_by)
    return status(db)


def resume(db: Session, reason: str, updated_by: str = "admin") -> dict:
    now = datetime.now(timezone.utc)
    _set(db, PAUSED, "false")
    _set(db, REASON, reason)
    _set(db, SINCE, now.isoformat())
    _set(db, UPDATED_BY, updated_by)
    return status(db)


def ensure_agents_running(db: Session) -> None:
    if is_paused(db):
        reason = _value(db, REASON) or "Agents are paused by an admin"
        raise HTTPException(
            status_code=409,
            detail={"error": "AGENTS_PAUSED", "message": f"Agents are paused: {reason}"},
        )


def require_agents_running(db: Session = Depends(get_db)) -> None:
    """FastAPI dependency for money-moving /internal routes."""
    ensure_agents_running(db)
