"""Round close (System Design, flow 4).

After the round's end time new donations simply fall outside its window. Close then waits until
no Watchdog case is open (the round sits in `closing`), computes the final match once, and adds
each project's match to its next unreleased milestone, so matching money is only paid out with
evidence. A project with no unreleased milestone gets a "Matching funds" milestone to hold it.
Closing is one-way: a closed round is never recomputed and its match never added twice.
`open_due` opens a scheduled round once its start time comes (one round runs at a time).
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.engine import run_round
from app.models import (
    CaseStatus,
    LedgerEntry,
    LedgerType,
    Milestone,
    MilestoneStatus,
    Round,
    RoundStatus,
    WatchdogCase,
)

UNRELEASED = (MilestoneStatus.open, MilestoneStatus.evidence_submitted, MilestoneStatus.held)


class CloseError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


def _aware(at: datetime) -> datetime:
    return at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at  # SQLite drops the zone


def open_cases(db: Session) -> list[int]:
    return list(db.scalars(select(WatchdogCase.id).where(WatchdogCase.status == CaseStatus.open)))


def _next_milestone(db: Session, round_: Round, project_id: int) -> Milestone:
    milestone = db.scalar(
        select(Milestone)
        .where(Milestone.project_id == project_id, Milestone.status.in_(UNRELEASED))
        .order_by(Milestone.seq)
    )
    if milestone is None:
        last = db.scalar(select(func.max(Milestone.seq)).where(Milestone.project_id == project_id)) or 0
        milestone = Milestone(
            project_id=project_id, seq=last + 1, title=f"Matching funds ({round_.name})", amount=0, currency=round_.currency
        )
        db.add(milestone)
    return milestone


def close(db: Session, round_: Round, *, now: datetime | None = None, early: bool = False) -> bool:
    """Try to close the round. True when closed now; False when it waits in `closing` for open cases.

    Raises CloseError if it is already closed, or hasn't ended and `early` isn't set. Caller commits.
    """
    now = now or datetime.now(timezone.utc)
    if round_.status == RoundStatus.closed:
        raise CloseError("ROUND_CLOSED", "This round is already closed")
    if not early and now < _aware(round_.ends_at):
        raise CloseError("ROUND_NOT_ENDED", f"The round ends at {round_.ends_at.isoformat()}")

    if cases := open_cases(db):
        if round_.status != RoundStatus.closing:
            round_.status = RoundStatus.closing
            audit.write(db, actor="system", action="round_closing", inputs={"round_id": round_.id, "open_cases": cases},
                        rule_result="waiting", reason="Final results wait until no Watchdog case is open")
        return False

    results = run_round(db, round_, is_final=True)
    for r in results:
        if r.final_amount <= 0:
            continue
        milestone = _next_milestone(db, round_, r.project_id)
        milestone.match_amount = (milestone.match_amount or 0) + r.final_amount
        db.add(LedgerEntry(type=LedgerType.match, amount=r.final_amount, currency=round_.currency, project_id=r.project_id))
    round_.status = RoundStatus.closed
    total = sum(r.final_amount for r in results)
    audit.write(db, actor="system", action="round_closed",
                inputs={"round_id": round_.id, "projects": len(results), "matched_cents": total},
                rule_result="closed", reason=f"{total} of {round_.matching_pool} matched; the rest stays unspent")
    return True


def close_due(db: Session, now: datetime | None = None) -> list[int]:
    """Close open rounds whose end time has passed, and closing rounds (already past their end,
    or closed early by an admin) whose cases are resolved. Returns the ids closed now."""
    now = now or datetime.now(timezone.utc)
    closed = []
    for round_ in db.scalars(select(Round).where(Round.status.in_((RoundStatus.open, RoundStatus.closing)))):
        waiting = round_.status == RoundStatus.closing
        if (waiting or _aware(round_.ends_at) <= now) and close(db, round_, now=now, early=waiting):
            closed.append(round_.id)
    return closed


def open_due(db: Session, now: datetime | None = None) -> Round | None:
    """Open the earliest scheduled round whose start has come, if no round is open or closing."""
    now = now or datetime.now(timezone.utc)
    if db.scalar(select(Round.id).where(Round.status.in_((RoundStatus.open, RoundStatus.closing)))):
        return None
    for round_ in db.scalars(select(Round).where(Round.status == RoundStatus.scheduled).order_by(Round.starts_at)):
        if _aware(round_.starts_at) <= now < _aware(round_.ends_at):
            round_.status = RoundStatus.open
            audit.write(db, actor="system", action="round_opened", inputs={"round_id": round_.id},
                        rule_result="open", reason=f"{round_.name} started")
            return round_
    return None
