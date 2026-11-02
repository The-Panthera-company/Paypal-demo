"""Round close: waits for Watchdog cases, final results once, match added to the next tranche."""

import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import projections, round_close
from app.models import (
    CaseStatus,
    Donation,
    DonationStatus,
    Donor,
    LedgerEntry,
    MatchResult,
    Milestone,
    MilestoneStatus,
    Round,
    RoundStatus,
    TargetType,
    WatchdogCase,
)

ADMIN = {"Authorization": "Bearer admin-test-token"}


def _round(db_session_factory, *, ended=True, backers=(3, 1)):
    """Pool 1,000, no cap; `backers` people for projects 1 and 2 inside the window."""
    now = datetime.now(timezone.utc)
    with db_session_factory() as db:
        r = Round(
            name="November",
            starts_at=now - timedelta(days=2),
            ends_at=now - timedelta(minutes=1) if ended else now + timedelta(days=1),
            matching_pool=1000,
            currency="USD",
            status=RoundStatus.open,
            project_cap_pct=100,
        )
        db.add(r)
        for project_id, n in zip((1, 2), backers):
            for _ in range(n):
                donor = Donor()
                db.add(donor)
                db.flush()
                db.add(Donation(donor_id=donor.id, target_type=TargetType.PROJECT, project_id=project_id, amount=100,
                                currency="USD", status=DonationStatus.captured, captured_at=now - timedelta(hours=1)))
        db.commit()
        return r.id


def _close(client, round_id, **params):
    return client.post(f"/admin/rounds/{round_id}/close", headers=ADMIN, params=params)


def _milestones(db_session_factory, project_id):
    with db_session_factory() as db:
        return [(m.title, m.amount, m.match_amount, m.status.value)
                for m in db.scalars(select(Milestone).where(Milestone.project_id == project_id).order_by(Milestone.seq))]


def test_close_writes_final_results_and_adds_match_to_next_tranche(client, db_session_factory):
    round_id = _round(db_session_factory)
    with db_session_factory() as db:
        db.add_all([
            Milestone(project_id=1, seq=1, title="Shelves", amount=500, currency="USD", status=MilestoneStatus.released),
            Milestone(project_id=1, seq=2, title="Books", amount=800, currency="USD"),
        ])
        db.commit()
    r = _close(client, round_id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_final"] is True
    match = {row["project_id"]: row["match_cents"] for row in body["rows"]}
    assert sum(match.values()) == 1000 and match[1] > match[2]

    # Project 1: added to its first unreleased milestone, not the released one.
    assert _milestones(db_session_factory, 1) == [("Shelves", 500, 0, "released"), ("Books", 800, match[1], "open")]
    # Project 2 had no milestone: one is created to hold the match.
    assert _milestones(db_session_factory, 2) == [("Matching funds (November)", 0, match[2], "open")]
    with db_session_factory() as db:
        assert db.get(Round, round_id).status == RoundStatus.closed
        assert sorted(e.amount for e in db.scalars(select(LedgerEntry)) if e.type.value == "match") == sorted(match.values())
        assert all(m.is_final for m in db.scalars(select(MatchResult).where(MatchResult.is_final.is_(True))))


def test_close_is_one_way(client, db_session_factory):
    round_id = _round(db_session_factory)
    _close(client, round_id)
    again = _close(client, round_id)
    assert (again.status_code, again.json()["detail"]["error"]) == (409, "ROUND_CLOSED")
    assert sum(m[2] for m in _milestones(db_session_factory, 1)) == client.get(
        f"/rounds/{round_id}/leaderboard").json()["rows"][0]["match_cents"]


def test_not_before_end_unless_early(client, db_session_factory):
    round_id = _round(db_session_factory, ended=False)
    assert _close(client, round_id).json()["detail"]["error"] == "ROUND_NOT_ENDED"
    assert _close(client, round_id, early=True).status_code == 200


def test_waits_for_open_cases_then_closes_when_resolved(client, db_session_factory):
    round_id = _round(db_session_factory)
    case = client.post("/internal/watchdog/cases", headers={"Authorization": "Bearer internal-test-token"},
                       json={"project_id": 2, "rule": "new_payer_burst", "evidence": {}}).json()
    r = _close(client, round_id)
    assert (r.status_code, r.json()["detail"]["error"]) == (409, "WAITING_FOR_CASES")
    with db_session_factory() as db:
        assert db.get(Round, round_id).status == RoundStatus.closing
        assert db.scalars(select(MatchResult).where(MatchResult.is_final.is_(True))).all() == []

    client.post(f"/admin/cases/{case['id']}/resolve", headers=ADMIN, json={"action": "clear"})
    with db_session_factory() as db:
        assert db.get(Round, round_id).status == RoundStatus.closed  # closed as soon as the case cleared
    assert client.get(f"/rounds/{round_id}/leaderboard").json()["is_final"] is True


def test_round_closed_early_waits_then_finishes(client, db_session_factory):
    round_id = _round(db_session_factory, ended=False)
    with db_session_factory() as db:
        db.add(WatchdogCase(project_id=2, rule="refund_spike", status=CaseStatus.open))
        db.commit()
    assert _close(client, round_id, early=True).json()["detail"]["error"] == "WAITING_FOR_CASES"
    with db_session_factory() as db:
        db.scalar(select(WatchdogCase)).status = CaseStatus.cleared
        db.commit()
        assert round_close.close_due(db) == [round_id]  # not past its end, but already closing


def test_background_loop_closes_ended_rounds(db_session_factory, monkeypatch):
    round_id = _round(db_session_factory)
    monkeypatch.setattr(projections, "SessionLocal", db_session_factory)
    stop = threading.Event()
    real_close_due = round_close.close_due

    def close_due_once(db):
        stop.set()  # one pass of the loop is enough
        return real_close_due(db)

    monkeypatch.setattr(round_close, "close_due", close_due_once)
    projections.run_loop(stop, interval_seconds=0)
    with db_session_factory() as db:
        assert db.get(Round, round_id).status == RoundStatus.closed


def test_unknown_round_and_auth(client):
    assert _close(client, 99).status_code == 404
    assert client.post("/admin/rounds/1/close").status_code == 401
