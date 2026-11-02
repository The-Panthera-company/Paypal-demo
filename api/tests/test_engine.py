"""Matching engine: the design's worked example, each Step 0 rule, caps, and the database path."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.engine import Gift, ProjectIn, compute, run_round
from app.matching import apply_caps
from app.models import (
    CaseStatus,
    Donation,
    DonationStatus,
    Donor,
    MatchResult,
    Project,
    Round,
    RoundStatus,
    TargetType,
    WatchdogCase,
)

BIG = 10**9  # a goal or per-person cap far away


def _people(prefix, n, amount, project_id, category_id=2):
    return [Gift(f"{prefix}{i}", 1.0, amount, category_id, project_id) for i in range(n)]


def _by_project(results):
    return {r.project_id: r for r in results}


EDUCATION = [ProjectIn(pid, 2, BIG) for pid in (1, 2, 3, 4)]  # Lanet, Desks, STEM, Reading Corner
WORKED = _people("lanet", 16, 25, 1) + _people("desks", 9, 25, 2) + _people("stem", 4, 100, 3)


def test_worked_example():
    """System Design: Education pool 10,000, cap 40% -> 4,000 / 3,024 / 2,256 / 720."""
    out = _by_project(compute(10_000, WORKED, EDUCATION, floor_pct=20, cap_pct=40, per_person_cap=BIG))
    assert {pid: r.final_amount for pid, r in out.items()} == {1: 4000, 2: 3024, 3: 2256, 4: 720}
    assert {pid: r.score for pid, r in out.items()} == {1: 6000, 2: 1800, 3: 1200, 4: 0}
    assert {pid: r.floor_amount for pid, r in out.items()} == {1: 500, 2: 500, 3: 500, 4: 500}
    assert {pid: r.crowd_amount for pid, r in out.items()} == {1: 5333, 2: 1600, 3: 1067, 4: 0}
    assert [pid for pid, r in out.items() if r.capped] == [1]


def test_pool_always_fully_shared_when_not_all_capped():
    out = compute(9_999, WORKED, EDUCATION, cap_pct=40, per_person_cap=BIG)
    assert sum(r.final_amount for r in out) == 9_999


def test_categories_share_by_people_not_money():
    projects = [ProjectIn(1, 1, BIG), ProjectIn(2, 2, BIG)]
    gifts = _people("many", 10, 100, 1, category_id=1) + [Gift("whale", 1.0, 100_000, 2, 2)]
    out = _by_project(compute(1000, gifts, projects, cap_pct=100))
    # Health: ten people; Education: one person giving 100x more, who scores nothing alone.
    assert (out[1].final_amount, out[2].final_amount) == (1000, 0)


def test_category_gift_counts_once_at_category_level_only():
    projects = [ProjectIn(1, 2, BIG), ProjectIn(2, 2, BIG)]
    gifts = _people("p", 4, 100, 1) + [Gift(f"c{i}", 1.0, 100, 2, None) for i in range(4)]
    out = _by_project(compute(1000, gifts, projects, cap_pct=100))
    # Category gifts add to the category's pool but not to any project's score.
    assert out[2].score == 0 and out[1].score > 0


def test_per_person_cap_stops_buying_influence():
    projects = [ProjectIn(1, 2, BIG), ProjectIn(2, 2, BIG)]
    rich = [Gift("a", 1.0, 1_000_000, 2, 1), Gift("b", 1.0, 1_000_000, 2, 1)]
    modest = [Gift("c", 1.0, 5000, 2, 2), Gift("d", 1.0, 5000, 2, 2)]
    out = _by_project(compute(1000, rich + modest, projects, cap_pct=100, per_person_cap=5000))
    assert out[1].score == out[2].score  # both pairs count as 2 x 50 USD


def test_guest_counts_half():
    projects = [ProjectIn(1, 2, BIG), ProjectIn(2, 2, BIG)]
    gifts = _people("a", 2, 100, 1) + [Gift("g1", 0.5, 100, 2, 2), Gift("g2", 0.5, 100, 2, 2)]
    out = _by_project(compute(1000, gifts, projects, cap_pct=100))
    assert out[2].score == out[1].score / 4  # (0.5*10 + 0.5*10)^2 - 2*25 = 50 vs 200


def test_merged_cluster_counts_as_one_voice():
    projects = [ProjectIn(1, 2, BIG), ProjectIn(2, 2, BIG)]
    honest = _people("h", 5, 100, 1)
    ring = [Gift("cluster:9", 1.0, 100, 2, 2) for _ in range(5)]  # five donors merged by the Watchdog
    out = _by_project(compute(1000, honest + ring, projects, cap_pct=100))
    assert out[2].score == 0 and out[1].score > 0


def test_cap_by_remaining_goal():
    projects = [ProjectIn(1, 2, 300), ProjectIn(2, 2, BIG)]
    gifts = _people("a", 10, 100, 1) + _people("b", 2, 100, 2)
    out = _by_project(compute(1000, gifts, projects, cap_pct=100))
    assert out[1].final_amount == 300 and out[1].capped
    assert out[2].final_amount == 700


def test_everyone_capped_leaves_money_in_pool():
    projects = [ProjectIn(1, 2, 100), ProjectIn(2, 2, 100)]
    out = compute(1000, _people("a", 3, 100, 1), projects, cap_pct=100)
    assert sum(r.final_amount for r in out) == 200


def test_gifts_to_ineligible_projects_are_ignored():
    out = compute(1000, _people("a", 5, 100, 99), [ProjectIn(1, 2, BIG)], cap_pct=100)
    assert out[0].final_amount == 1000 and out[0].score == 0


def test_apply_caps_repeats_until_settled():
    after, hit = apply_caps({1: 600, 2: 300, 3: 100}, {1: 400, 2: 400, 3: 400})
    # 200 excess -> 2 and 3 by 3:1 -> 2 reaches 450, over its cap -> 50 more to 3.
    assert hit == {1, 2} and round(after[3]) == 200


# --- database path ------------------------------------------------------------------------


def _round(db, **kw):
    now = datetime.now(timezone.utc)
    r = Round(
        name="R1",
        starts_at=now - timedelta(days=1),
        ends_at=now + timedelta(days=1),
        matching_pool=1000,
        currency="USD",
        status=RoundStatus.open,
        project_cap_pct=100,
        **kw,
    )
    db.add(r)
    db.flush()
    return r


def _donate(db, project_id, *, guest=False, status=DonationStatus.captured, donor=None, captured_at=None):
    if donor is None:
        donor = Donor(is_guest=guest)
        db.add(donor)
        db.flush()
    db.add(
        Donation(
            donor_id=donor.id,
            target_type=TargetType.PROJECT,
            project_id=project_id,
            amount=100,
            currency="USD",
            status=status,
            captured_at=captured_at or datetime.now(timezone.utc),
        )
    )
    return donor


def test_run_round_saves_projection_and_replaces_it(db_session_factory):
    # Seeded: projects 1 and 2 listed in category 1, project 3 pending.
    with db_session_factory() as db:
        r = _round(db)
        for _ in range(3):
            _donate(db, 1)
        run_round(db, r)
        db.commit()
        rows = {m.project_id: m for m in db.scalars(select(MatchResult))}
        assert set(rows) == {1, 2} and not rows[1].is_final
        assert rows[1].final_amount > rows[2].final_amount
        assert sum(m.final_amount for m in rows.values()) == 1000

        _donate(db, 2)
        run_round(db, r)  # overwrites, never duplicates
        db.commit()
        assert len(db.scalars(select(MatchResult)).all()) == 2


def test_run_round_cleans_inputs(db_session_factory):
    with db_session_factory() as db:
        r = _round(db)
        ring = [_donate(db, 2) for _ in range(4)]
        db.add(WatchdogCase(project_id=2, rule="reciprocal_backing", status=CaseStatus.confirmed,
                            evidence={"donor_ids": [d.id for d in ring]}))
        for _ in range(4):
            _donate(db, 2, status=DonationStatus.refunded)  # refunded: gone
            _donate(db, 2, captured_at=datetime.now(timezone.utc) - timedelta(days=5))  # before the round
        for _ in range(2):
            _donate(db, 1)
        db.flush()
        out = _by_project(run_round(db, r))
        assert out[2].score == 0  # one merged voice, nothing else counts
        assert out[1].score > 0


def test_frozen_project_gets_no_match(db_session_factory):
    with db_session_factory() as db:
        r = _round(db)
        for _ in range(3):
            _donate(db, 2)
        db.get(Project, 2).matching_frozen = True
        db.flush()
        out = _by_project(run_round(db, r))
        assert set(out) == {1} and out[1].final_amount == 1000
