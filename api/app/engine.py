"""Matching engine (System Design, "Matching engine"): shares a round's matching pool.

`compute` is pure: the same gifts and projects always give the same result, so it can be
tested against the design's worked example and rerun at close. `run_round` gathers the
inputs from the database and saves the results to match_results.

Step 0  clean inputs: one payer = one person, guests half weight, refunds out, Watchdog-confirmed
        clusters merged into one person, a person's first per_person_cap to a project counts.
Step 1  category pools: M_c = M * S_c / sum(S), S from each person's total to the category.
Step 2  project scores: P from project donations only.
Step 3  floor_pct of M_c equally, the rest by P (all equally when nobody has a score).
Step 4  caps: project_cap_pct of M_c and the project's remaining goal; excess re-shared.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.allocation import GUEST_WEIGHT, raised
from app.matching import apply_caps, quadratic_score, split, to_cents
from app.models import (
    CaseStatus,
    Donation,
    DonationStatus,
    Donor,
    MatchResult,
    Project,
    Round,
    TargetType,
    WatchdogCase,
)
from app.routers.catalogue import LISTED


@dataclass(frozen=True)
class Gift:
    person: str  # "donor:<id>", or "cluster:<case id>" for a merged Watchdog cluster
    weight: float  # 1.0, or GUEST_WEIGHT when every gift of this person is a guest card
    amount: int  # cents
    category_id: int
    project_id: int | None = None  # None = a category donation


@dataclass(frozen=True)
class ProjectIn:
    id: int
    category_id: int
    remaining_goal: int  # cents still needed to reach the goal


@dataclass
class ProjectResult:
    project_id: int
    category_id: int
    score: float
    floor_amount: int
    crowd_amount: int
    capped: bool
    final_amount: int


def compute(
    pool: int,
    gifts: list[Gift],
    projects: list[ProjectIn],
    *,
    floor_pct: float = 20.0,
    cap_pct: float = 30.0,
    per_person_cap: int = 5000,
) -> list[ProjectResult]:
    """Share `pool` cents across the eligible `projects`. Gifts to anything else are ignored."""
    eligible = {p.id: p for p in projects}
    categories = sorted({p.category_id for p in projects})
    if not categories or pool <= 0:
        return [ProjectResult(p.id, p.category_id, 0.0, 0, 0, False, 0) for p in projects]

    # Step 0: per-person totals, capped per project (and per category for category gifts).
    weight: dict[str, float] = {}
    to_project: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    to_category: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for g in gifts:
        if g.project_id is not None and g.project_id not in eligible:
            continue
        if g.category_id not in categories:
            continue
        weight[g.person] = max(weight.get(g.person, 0.0), g.weight)
        if g.project_id is None:
            to_category[g.category_id][g.person] += g.amount
        else:
            to_project[g.project_id][g.person] += g.amount
    capped_project = {
        pid: {person: min(total, per_person_cap) for person, total in people.items()}
        for pid, people in to_project.items()
    }

    # Step 1: category pools from each person's whole contribution to the category.
    category_score: dict[int, float] = {}
    for c in categories:
        totals: dict[str, int] = defaultdict(int)
        for p in projects:
            if p.category_id == c:
                for person, amount in capped_project.get(p.id, {}).items():
                    totals[person] += amount
        for person, amount in to_category[c].items():
            totals[person] += min(amount, per_person_cap)
        category_score[c] = quadratic_score((t, weight[person]) for person, t in totals.items())
    category_pool = split(pool, category_score)

    results: list[ProjectResult] = []
    for c in categories:
        members = sorted(p.id for p in projects if p.category_id == c)
        m_c = category_pool[c]
        # Step 2: project scores, from project donations only.
        scores = {
            pid: quadratic_score((d, weight[person]) for person, d in capped_project.get(pid, {}).items())
            for pid in members
        }
        # Step 3: floor + crowd.
        if sum(scores.values()) <= 0:
            floor, crowd = split(m_c, dict.fromkeys(members, 1)), dict.fromkeys(members, 0)
        else:
            floor_total = round(m_c * floor_pct / 100)
            floor, crowd = split(floor_total, dict.fromkeys(members, 1)), split(m_c - floor_total, scores)
        # Step 4: caps.
        caps = {pid: min(int(m_c * cap_pct / 100), eligible[pid].remaining_goal) for pid in members}
        before = {pid: float(floor[pid] + crowd[pid]) for pid in members}
        after, hit = apply_caps(before, caps)
        final = to_cents(after)
        results += [
            ProjectResult(pid, c, scores[pid], floor[pid], crowd[pid], pid in hit, final[pid]) for pid in members
        ]
    return results


def gather(db: Session, round_: Round) -> tuple[list[Gift], list[ProjectIn]]:
    """The round's inputs: captured donations inside its window (refunded ones are not captured),
    and the listed projects whose matching is not frozen."""
    projects = list(
        db.scalars(select(Project).where(Project.status.in_(LISTED), Project.matching_frozen.is_(False)))
    )
    so_far = raised(db, [p.id for p in projects])
    project_in = [ProjectIn(p.id, p.category_id, max(p.goal_amount - so_far[p.id], 0)) for p in projects]
    category_of = {p.id: p.category_id for p in projects}

    # Confirmed Watchdog cases merge their donors (evidence["donor_ids"]) into one person.
    cluster: dict[int, str] = {}
    for case in db.scalars(select(WatchdogCase).where(WatchdogCase.status == CaseStatus.confirmed)):
        for donor_id in (case.evidence or {}).get("donor_ids", []):
            cluster.setdefault(int(donor_id), f"cluster:{case.id}")

    rows = db.execute(
        select(Donation, Donor.is_guest)
        .join(Donor, Donor.id == Donation.donor_id, isouter=True)
        .where(
            Donation.status == DonationStatus.captured,
            Donation.captured_at >= round_.starts_at,
            Donation.captured_at < round_.ends_at,
        )
    )
    gifts = []
    for d, is_guest in rows:
        if d.target_type == TargetType.CATEGORY:
            category_id, project_id = d.category_id, None
        elif d.project_id in category_of:  # project and agent gifts
            category_id, project_id = category_of[d.project_id], d.project_id
        else:
            continue
        person = cluster.get(d.donor_id) or (f"donor:{d.donor_id}" if d.donor_id else f"anonymous:{d.id}")
        gifts.append(Gift(person, GUEST_WEIGHT if is_guest else 1.0, d.amount, category_id, project_id))
    return gifts, project_in


def run_round(db: Session, round_: Round, *, is_final: bool = False) -> list[ProjectResult]:
    """Compute the round and replace its saved projection (or final) rows. Caller commits."""
    gifts, projects = gather(db, round_)
    results = compute(
        round_.matching_pool,
        gifts,
        projects,
        floor_pct=round_.floor_pct,
        cap_pct=round_.project_cap_pct,
        per_person_cap=round_.per_person_cap,
    )
    now = datetime.now(timezone.utc)
    db.execute(delete(MatchResult).where(MatchResult.round_id == round_.id, MatchResult.is_final.is_(is_final)))
    db.add_all(
        MatchResult(
            round_id=round_.id,
            project_id=r.project_id,
            is_final=is_final,
            score=r.score,
            floor_amount=r.floor_amount,
            crowd_amount=r.crowd_amount,
            capped=r.capped,
            final_amount=r.final_amount,
            computed_at=now,
        )
        for r in results
    )
    return results
