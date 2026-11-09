"""Giving Agent mandates: the funded balance and the checks every agent gift must pass.

The core API, not the agent, enforces these, so even a misbehaving agent cannot overspend.

Money model: a donor tops up the budget with a PayPal donation whose target_type is AGENT and
which has no project. Each agent gift is an AGENT donation with a project and the run that
chose it. Gifts waiting for the donor's yes (status created) already hold their share of the budget.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, Donation, DonationStatus, Mandate, Project, TargetType
from app.routers.catalogue import LISTED
from app.schemas import MandateIn

# The rules function's published weights; a donor may move each by up to MAX_WEIGHT_SHIFT.
DEFAULT_WEIGHTS = {"few_backers": 35, "progress": 25, "urgency": 20, "evidence": 10, "days_since_funded": 10}
MAX_WEIGHT_SHIFT = 20

# The mandate contract (GET /mandates/constraints). The website and the agents read these numbers
# instead of hard-coding them; an LLM's proposed mandate must fit them before it can be saved.
MAX_BUDGET_CENTS = 1_000_000  # 10,000 USD a month
MIN_AMOUNT_CENTS = 100  # per-project max and approval threshold: at least 1 USD
MAX_TAGS = 20
MAX_TAG_LENGTH = 40

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


def validate_mandate(db: Session, body: MandateIn) -> tuple[MandateIn, list[dict]]:
    """The one set of mandate rules, for PUT and preview alike. Returns the normalized mandate
    (tags trimmed, lowercased and deduped; categories deduped) and every problem found, each
    {field, code, message}. No problems means it can be saved as it is."""
    tags = list(dict.fromkeys(t.strip().lower() for t in body.excluded_tags if t.strip()))
    categories = list(dict.fromkeys(body.categories))
    normalized = body.model_copy(update={"excluded_tags": tags, "categories": categories})
    errors: list[dict] = []

    def problem(field: str, code: str, message: str) -> None:
        errors.append({"field": field, "code": code, "message": message})

    if not categories:
        problem("categories", "CATEGORIES_REQUIRED", "Choose at least one category")
    known = set(db.scalars(select(Category.id).where(Category.id.in_(categories)))) if categories else set()
    if missing := [c for c in categories if c not in known]:
        problem("categories", "CATEGORY_NOT_FOUND", f"No such categories: {missing}")

    budget = body.monthly_budget_cents
    if budget > MAX_BUDGET_CENTS:
        problem("monthly_budget_cents", "BUDGET_TOO_HIGH", f"The monthly budget can be at most {MAX_BUDGET_CENTS} cents")
    for field, value, code, label in (
        ("per_project_max_cents", body.per_project_max_cents, "PER_PROJECT_OVER_BUDGET", "Per-project max"),
        ("approval_threshold_cents", body.approval_threshold_cents, "THRESHOLD_OVER_BUDGET", "Approval threshold"),
    ):
        if value < MIN_AMOUNT_CENTS:
            problem(field, "AMOUNT_TOO_LOW", f"{label} must be at least {MIN_AMOUNT_CENTS} cents")
        elif value > budget:
            problem(field, code, f"{label} can't be more than the monthly budget")

    if len(tags) > MAX_TAGS:
        problem("excluded_tags", "TOO_MANY_TAGS", f"At most {MAX_TAGS} excluded tags")
    if long := [t for t in tags if len(t) > MAX_TAG_LENGTH]:
        problem("excluded_tags", "TAG_TOO_LONG", f"Tags can be at most {MAX_TAG_LENGTH} characters: {long[0][:60]!r}")

    for key, value in (body.weight_overrides or {}).items():
        if found := weight_problems({key: value}):
            problem(f"weight_overrides.{key}", "INVALID_WEIGHTS", found[0])
    return normalized, errors


def constraints() -> dict:
    return {
        "default_weights": DEFAULT_WEIGHTS,
        "max_weight_shift": MAX_WEIGHT_SHIFT,
        "max_budget_cents": MAX_BUDGET_CENTS,
        "max_tags": MAX_TAGS,
        "max_tag_length": MAX_TAG_LENGTH,
        "min_per_project_cents": MIN_AMOUNT_CENTS,
        "max_per_project_cents": MAX_BUDGET_CENTS,
        "min_approval_threshold_cents": MIN_AMOUNT_CENTS,
        "max_approval_threshold_cents": MAX_BUDGET_CENTS,
    }


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
