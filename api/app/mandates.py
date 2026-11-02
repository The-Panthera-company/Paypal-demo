"""Giving Agent mandates: the funded balance and the checks every agent gift must pass.

The core API, not the agent, enforces these, so even a misbehaving agent cannot overspend.

Money model: a donor tops up the budget with a PayPal donation whose target_type is AGENT and
which has no project. Each agent gift is an AGENT donation with a project and the run that
chose it. Gifts waiting for the donor's yes (status created) already hold their share of the budget.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Donation, DonationStatus, Mandate, Project, TargetType
from app.routers.catalogue import LISTED

# The rules function's published weights; a donor may move each by up to MAX_WEIGHT_SHIFT.
DEFAULT_WEIGHTS = {"few_backers": 35, "progress": 25, "urgency": 20, "evidence": 10, "days_since_funded": 10}
MAX_WEIGHT_SHIFT = 20

HELD = (DonationStatus.captured, DonationStatus.created)  # given, or reserved awaiting approval


def weight_problems(overrides: dict[str, float] | None) -> list[str]:
    problems = []
    for key, value in (overrides or {}).items():
        if key not in DEFAULT_WEIGHTS:
            problems.append(f"unknown weight {key!r}; allowed: {', '.join(DEFAULT_WEIGHTS)}")
        elif abs(value - DEFAULT_WEIGHTS[key]) > MAX_WEIGHT_SHIFT or value < 0:
            low, high = max(DEFAULT_WEIGHTS[key] - MAX_WEIGHT_SHIFT, 0), DEFAULT_WEIGHTS[key] + MAX_WEIGHT_SHIFT
            problems.append(f"{key} must be between {low} and {high}")
    return problems


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _sum(db: Session, *where) -> int:
    return db.scalar(select(func.coalesce(func.sum(Donation.amount), 0)).where(*where))


def _gifts(donor_id: int, exclude_id: int | None):
    where = [
        Donation.donor_id == donor_id,
        Donation.target_type == TargetType.AGENT,
        Donation.project_id.is_not(None),
        Donation.status.in_(HELD),
    ]
    if exclude_id is not None:
        where.append(Donation.id != exclude_id)
    return where


def funded_balance(db: Session, donor_id: int, exclude_id: int | None = None) -> int:
    """Top-ups paid through PayPal minus gifts given or reserved."""
    topped_up = _sum(
        db,
        Donation.donor_id == donor_id,
        Donation.target_type == TargetType.AGENT,
        Donation.project_id.is_(None),
        Donation.status == DonationStatus.captured,
    )
    return topped_up - _sum(db, *_gifts(donor_id, exclude_id))


def check_gift(
    db: Session,
    mandate: Mandate,
    project: Project | None,
    amount: int,
    *,
    now: datetime | None = None,
    exclude_id: int | None = None,
) -> tuple[str, str]:
    """("ok", why) or (the rule that blocks the gift, why). `exclude_id` leaves out a pending gift being re-checked."""
    now = now or datetime.now(timezone.utc)
    if not mandate.active:
        return "mandate_inactive", "The donor has paused their mandate"
    if project is None or project.status not in LISTED:
        return "project_not_open", "Project does not exist or is not verified"
    if project.matching_frozen:
        return "project_frozen", "Project is under a Watchdog review"
    if project.category_id not in (mandate.categories or []):
        return "category_not_in_mandate", "Project's category is not one the donor chose"
    excluded = {t.lower() for t in mandate.excluded_tags or []}
    hit = next((t for t in project.tags or [] if t.lower() in excluded), None)
    if hit:
        return "excluded_tag", f"Project is tagged {hit!r}, which the donor excluded"

    this_month = [*_gifts(mandate.donor_id, exclude_id), Donation.created_at >= _month_start(now)]
    to_project = _sum(db, *this_month, Donation.project_id == project.id)
    if to_project + amount > mandate.per_project_max:
        return "over_per_project_max", f"Would give {to_project + amount} to this project this month; max {mandate.per_project_max}"
    spent = _sum(db, *this_month)
    if spent + amount > mandate.monthly_budget:
        return "over_monthly_budget", f"Would spend {spent + amount} this month; budget {mandate.monthly_budget}"
    balance = funded_balance(db, mandate.donor_id, exclude_id)
    if amount > balance:
        return "insufficient_balance", f"Funded balance is {balance}"
    return "ok", "Within budget, per-project max and exclusions"
