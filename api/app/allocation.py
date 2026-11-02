"""Where a category gift goes: eligible projects, their crowd scores, and the donor's split rule.

Used by the checkout preview now, and by category donation allocation and the matching engine later.
"""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.matching import closest_to_goal_split, crowd_split, quadratic_score, split
from app.models import (
    CategoryAllocation,
    CategoryGift,
    Donation,
    DonationStatus,
    Donor,
    Project,
    Round,
    RoundStatus,
    TargetType,
)
from app.routers.catalogue import LISTED, project_gifts

GUEST_WEIGHT = 0.5
DEFAULT_FLOOR_PCT = 20.0
DEFAULT_PER_PERSON_CAP = 5000  # cents: only a person's first 50 USD to one project counts


@dataclass
class CategorySplit:
    allocations: dict[int, int]  # project id -> cents
    projects: dict[int, Project]  # the eligible projects
    excluded: list[tuple[Project, str]]  # projects removed by the donor's exclusions, with the tag that matched


def project_scores(db: Session, project_ids: list[int], round_: Round | None) -> dict[int, float]:
    """Design Step 2: one PayPal payer = one person, guests at half weight, refunds gone,
    a person's total to a project capped at the round's per-person cap. Only project donations count."""
    stmt = select(Donation.project_id, Donation.donor_id, Donation.amount, Donor.is_guest).join(
        Donor, Donor.id == Donation.donor_id, isouter=True
    ).where(
        Donation.project_id.in_(project_ids),
        Donation.target_type == TargetType.PROJECT,
        Donation.status == DonationStatus.captured,
    )
    if round_ is not None:
        stmt = stmt.where(Donation.captured_at >= round_.starts_at, Donation.captured_at < round_.ends_at)
    cap = round_.per_person_cap if round_ is not None else DEFAULT_PER_PERSON_CAP

    per_person: dict[int, dict[int, list]] = defaultdict(dict)
    for project_id, donor_id, amount, is_guest in db.execute(stmt):
        entry = per_person[project_id].setdefault(donor_id, [0, GUEST_WEIGHT if is_guest else 1.0])
        entry[0] += amount
    return {
        pid: quadratic_score((min(total, cap), weight) for total, weight in per_person[pid].values())
        for pid in project_ids
    }


def raised(db: Session, project_ids: list[int]) -> dict[int, int]:
    totals = dict.fromkeys(project_ids, 0)
    for pid, _, amount, _ in project_gifts(db, project_ids):
        totals[pid] += amount
    return totals


def allocate_category_donation(db: Session, donation: Donation) -> int:
    """Split a just-captured category donation onto projects with the donor's rule and exclusions.
    Done once; returns the cents allocated (0 if no project was eligible: reconciliation flags it)."""
    if db.scalar(select(CategoryAllocation.id).where(CategoryAllocation.donation_id == donation.id)):
        return 0
    choice = db.get(CategoryGift, donation.id)
    result = category_split(
        db,
        donation.category_id,
        donation.amount,
        choice.rule if choice else "crowd",
        choice.excluded_tags if choice else [],
    )
    for project_id, cents in result.allocations.items():
        if cents > 0:
            db.add(CategoryAllocation(donation_id=donation.id, project_id=project_id, amount=cents))
    return sum(result.allocations.values())


def category_split(
    db: Session, category_id: int, amount: int, rule: str, excluded_tags: list[str]
) -> CategorySplit:
    """Split `amount` cents across the category's listed projects the donor hasn't excluded.

    Projects with matching frozen by the Watchdog get no category money until cleared.
    """
    exclude = {t.strip().lower() for t in excluded_tags if t.strip()}
    candidates = db.scalars(
        select(Project)
        .where(Project.category_id == category_id, Project.status.in_(LISTED), Project.matching_frozen.is_(False))
        .order_by(Project.id)
    )
    projects: dict[int, Project] = {}
    excluded: list[tuple[Project, str]] = []
    for p in candidates:
        hit = next((t for t in p.tags or [] if t.lower() in exclude), None)
        if hit:
            excluded.append((p, hit))
        else:
            projects[p.id] = p
    ids = list(projects)
    if not ids:
        return CategorySplit({}, projects, excluded)

    if rule == "equal":
        allocations = split(amount, dict.fromkeys(ids, 1))
    elif rule == "closest_to_goal":
        so_far = raised(db, ids)
        allocations = closest_to_goal_split(
            amount, {i: max(projects[i].goal_amount - so_far[i], 0) for i in ids}
        )
    else:
        round_ = db.scalar(select(Round).where(Round.status == RoundStatus.open))
        floor_pct = round_.floor_pct if round_ is not None else DEFAULT_FLOOR_PCT
        allocations = crowd_split(amount, project_scores(db, ids, round_), floor_pct)
    return CategorySplit(allocations, projects, excluded)
