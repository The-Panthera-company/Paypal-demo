"""Donor leaderboard for a round: several ladders, like a game's rankings.

Per donor, from captured gifts inside the round's window (agent budget top-ups are not gifts):
- given_cents: everything they gave (project, category and agent gifts)
- match_unlocked_cents: matching their gifts unlocked (same rule as My Impact)
- multiplier: matching unlocked per dollar given (the "K/D ratio")
- projects_backed / categories_reached: how widely their money spread ("reach")
- agent_given_cents: what their Giving Agent distributed for them
- impact_points: given + matching unlocked, in dollars, x reach bonus (1 + 0.25 per extra project)

Privacy: names only for donors who opted in (show_on_leaderboard); everyone else is
"Anonymous donor" with a stable alias that doesn't reveal their id.
"""

import hashlib
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CategoryAllocation, Donation, DonationStatus, Donor, Project, Round, TargetType
from app.reports import _match_unlocked
from app.schemas import DonorBoardOut, DonorBoardRow


def _aware(at: datetime) -> datetime:
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def _alias(donor_id: int) -> str:
    return "Donor " + hashlib.sha256(f"cg-donor-{donor_id}".encode()).hexdigest()[:6].upper()


def donor_board(db: Session, round_: Round, me: int | None = None) -> DonorBoardOut:
    start, end = _aware(round_.starts_at), _aware(round_.ends_at)
    gifts = [
        d for d in db.scalars(select(Donation).where(Donation.status == DonationStatus.captured, Donation.donor_id.is_not(None)))
        if d.captured_at and start <= _aware(d.captured_at) < end and not (d.target_type == TargetType.AGENT and d.project_id is None)
    ]
    by_donor: dict[int, list[Donation]] = defaultdict(list)
    for g in gifts:
        by_donor[g.donor_id].append(g)

    category_of = dict(db.execute(select(Project.id, Project.category_id)).all())
    reached: dict[int, set[int]] = defaultdict(set)  # donation id -> projects a category gift reached
    for donation_id, project_id in db.execute(select(CategoryAllocation.donation_id, CategoryAllocation.project_id)):
        reached[donation_id].add(project_id)

    rows = []
    for donor_id, mine in by_donor.items():
        donor = db.get(Donor, donor_id)
        projects = {g.project_id for g in mine if g.project_id} | {p for g in mine for p in reached.get(g.id, ())}
        categories = {category_of.get(p) for p in projects} | {g.category_id for g in mine if g.category_id}
        categories.discard(None)
        given = sum(g.amount for g in mine)
        unlocked = sum(_match_unlocked(db, donor_id, [g for g in mine if g.project_id is not None]).values())
        reach_bonus = 1 + 0.25 * max(0, len(projects) - 1)
        rows.append(DonorBoardRow(
            alias=_alias(donor_id),
            display_name=donor.display_name if donor and donor.show_on_leaderboard and donor.display_name else None,
            is_me=me == donor_id,
            given_cents=given,
            match_unlocked_cents=unlocked,
            multiplier=round(unlocked / given, 2) if given else 0.0,
            projects_backed=len(projects),
            categories_reached=len(categories),
            agent_given_cents=sum(g.amount for g in mine if g.target_type == TargetType.AGENT),
            impact_points=round((given + unlocked) / 100 * reach_bonus),
        ))
    return DonorBoardOut(round_id=round_.id, currency=round_.currency, rows=rows)
