"""POST /donations/category-preview against real rows (projects 1 Lanet Library and 2 Faith School Desks)."""

from datetime import datetime, timezone

from app.allocation import project_scores
from app.models import Donation, DonationStatus, Donor, Project, ProjectStatus, Round, TargetType


def _preview(client, **body):
    return client.post("/donations/category-preview", json={"category_id": 1, "amount_cents": 1000} | body)


def _gifts(db_session_factory, project_id, amounts, guest=False):
    """Captured project donations, one new person per amount."""
    with db_session_factory() as db:
        for amount in amounts:
            donor = Donor(is_guest=guest)
            db.add(donor)
            db.flush()
            db.add(
                Donation(
                    donor_id=donor.id,
                    target_type=TargetType.PROJECT,
                    project_id=project_id,
                    amount=amount,
                    currency="USD",
                    status=DonationStatus.captured,
                    captured_at=datetime.now(timezone.utc),
                )
            )
        db.commit()


def _alloc(r):
    return {a["project_id"]: a["amount_cents"] for a in r.json()["allocations"]}


def test_no_backers_yet_splits_equally(client):
    r = _preview(client)
    assert r.status_code == 200, r.text
    assert _alloc(r) == {1: 500, 2: 500}
    assert r.json()["excluded"] == []


def test_crowd_follows_number_of_backers(client, db_session_factory):
    _gifts(db_session_factory, 1, [2500] * 4)  # four people
    _gifts(db_session_factory, 2, [2500])  # one person: no score
    # 20% floor = 100 each; the 800 crowd share all goes to Lanet.
    assert _alloc(_preview(client)) == {1: 900, 2: 100}


def test_exclusions_remove_projects_and_say_why(client):
    r = _preview(client, excluded_tags=["Faith-Based"])
    assert _alloc(r) == {1: 1000}
    assert r.json()["excluded"] == [{"project_id": 2, "title": "Faith School Desks", "matched_tag": "faith-based"}]


def test_equal_rule(client):
    assert _alloc(_preview(client, rule="equal", amount_cents=2001)) == {1: 1001, 2: 1000}


def test_closest_to_goal_rule(client, db_session_factory):
    _gifts(db_session_factory, 2, [49_000])  # desks: 1,000 short of its 50,000 goal
    assert _alloc(_preview(client, rule="closest_to_goal", amount_cents=3000)) == {2: 1000, 1: 2000}


def test_frozen_and_unlisted_projects_get_nothing(client, db_session_factory):
    with db_session_factory() as db:
        db.get(Project, 2).matching_frozen = True
        db.add(Project(category_id=1, title="Draft", status=ProjectStatus.draft, goal_amount=1000, currency="USD"))
        db.commit()
    assert _alloc(_preview(client)) == {1: 1000}


def test_errors(client):
    assert _preview(client, category_id=99).json()["detail"]["error"] == "CATEGORY_NOT_FOUND"
    r = _preview(client, excluded_tags=["books", "faith-based"])
    assert (r.status_code, r.json()["detail"]["error"]) == (422, "NO_ELIGIBLE_PROJECTS")
    assert _preview(client, rule="biggest").status_code == 422
    assert _preview(client, amount_cents=0).status_code == 422


def test_scores_cap_each_person_and_halve_guests(db_session_factory):
    _gifts(db_session_factory, 1, [10_000, 5000])  # first person capped at 5,000
    _gifts(db_session_factory, 2, [5000])
    _gifts(db_session_factory, 2, [5000], guest=True)
    with db_session_factory() as db:
        scores = project_scores(db, [1, 2], None)
    assert round(scores[1]) == 10_000  # (2 * sqrt 5000)^2 - 2 * 5000
    assert round(scores[2]) == 5000  # guest at half weight


def test_scores_only_count_the_open_rounds_window(db_session_factory):
    _gifts(db_session_factory, 1, [2500, 2500])
    future = Round(
        name="Next",
        starts_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        ends_at=datetime(2030, 2, 1, tzinfo=timezone.utc),
        matching_pool=0,
        currency="USD",
    )
    with db_session_factory() as db:
        assert project_scores(db, [1], future) == {1: 0}
        assert round(project_scores(db, [1], None)[1]) == 5000
