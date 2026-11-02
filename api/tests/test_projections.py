"""Projected match: the leaderboard, refresh when stale, final results, and the background loop."""

import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import projections
from app.models import (
    Donation,
    DonationStatus,
    Donor,
    MatchResult,
    Project,
    Round,
    RoundStatus,
    TargetType,
)


def _setup(db_session_factory, status=RoundStatus.open, backers=(3, 1)):
    """An open round (pool 1,000, no cap) and `backers` separate people for projects 1 and 2."""
    now = datetime.now(timezone.utc)
    with db_session_factory() as db:
        r = Round(
            name="R1",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
            matching_pool=1000,
            currency="USD",
            status=status,
            project_cap_pct=100,
        )
        db.add(r)
        for project_id, n in zip((1, 2), backers):
            for _ in range(n):
                donor = Donor()
                db.add(donor)
                db.flush()
                db.add(
                    Donation(
                        donor_id=donor.id,
                        target_type=TargetType.PROJECT,
                        project_id=project_id,
                        amount=100,
                        currency="USD",
                        status=DonationStatus.captured,
                        captured_at=now,
                    )
                )
        db.commit()
        return r.id


def test_leaderboard_computes_projection_on_first_read(client, db_session_factory):
    round_id = _setup(db_session_factory)
    r = client.get(f"/rounds/{round_id}/leaderboard")
    assert r.status_code == 200, r.text
    assert "X-Stub" not in r.headers
    body = r.json()
    assert body["is_final"] is False and body["currency"] == "USD"
    rows = body["rows"]
    assert [(row["rank"], row["project_id"]) for row in rows] == [(1, 1), (2, 2)]
    assert sum(row["match_cents"] for row in rows) == 1000
    assert rows[0]["backer_count"] == 3 and rows[0]["raised_cents"] == 300
    # The catalogue shows the same projection.
    assert client.get("/projects/1").json()["projected_match_cents"] == rows[0]["match_cents"]


def test_fresh_projection_is_reused_and_stale_one_recomputed(client, db_session_factory):
    round_id = _setup(db_session_factory)
    first = client.get(f"/rounds/{round_id}/leaderboard").json()
    with db_session_factory() as db:  # a new backer for project 2
        donor = Donor()
        db.add(donor)
        db.flush()
        db.add(Donation(donor_id=donor.id, target_type=TargetType.PROJECT, project_id=2, amount=100,
                        currency="USD", status=DonationStatus.captured, captured_at=datetime.now(timezone.utc)))
        db.commit()
    assert client.get(f"/rounds/{round_id}/leaderboard").json()["computed_at"] == first["computed_at"]

    with db_session_factory() as db:  # age the projection past 5 minutes
        for m in db.scalars(select(MatchResult)):
            m.computed_at = datetime.now(timezone.utc) - timedelta(minutes=6)
        db.commit()
    again = client.get(f"/rounds/{round_id}/leaderboard").json()
    assert again["computed_at"] != first["computed_at"]
    assert again["rows"][1]["score"] > first["rows"][1]["score"]


def test_final_results_win_over_projection(client, db_session_factory):
    round_id = _setup(db_session_factory, status=RoundStatus.closed)
    with db_session_factory() as db:
        db.add(MatchResult(round_id=round_id, project_id=1, is_final=True, score=1, floor_amount=0,
                           crowd_amount=0, capped=False, final_amount=777))
        db.commit()
    body = client.get(f"/rounds/{round_id}/leaderboard").json()
    assert body["is_final"] is True
    assert [(row["project_id"], row["match_cents"]) for row in body["rows"]] == [(1, 777)]


def test_closed_round_without_results_is_not_recomputed(client, db_session_factory):
    round_id = _setup(db_session_factory, status=RoundStatus.closed)
    assert client.get(f"/rounds/{round_id}/leaderboard").json()["rows"] == []


def test_frozen_project_listed_with_no_match(client, db_session_factory):
    round_id = _setup(db_session_factory)
    with db_session_factory() as db:
        db.get(Project, 2).matching_frozen = True
        db.commit()
    rows = client.get(f"/rounds/{round_id}/leaderboard").json()["rows"]
    frozen = next(row for row in rows if row["project_id"] == 2)
    assert (frozen["match_cents"], frozen["matching_frozen"], frozen["rank"]) == (0, True, 2)
    assert rows[0]["match_cents"] == 1000


def test_unknown_round_404(client):
    assert client.get("/rounds/99/leaderboard").json()["detail"]["error"] == "ROUND_NOT_FOUND"


def test_background_loop_refreshes_open_round(db_session_factory, monkeypatch):
    round_id = _setup(db_session_factory)
    monkeypatch.setattr(projections, "SessionLocal", db_session_factory)
    stop = threading.Event()
    calls = []
    real_refresh = projections.refresh

    def refresh_once(db, round_):
        real_refresh(db, round_)
        calls.append(round_.id)
        stop.set()

    monkeypatch.setattr(projections, "refresh", refresh_once)
    projections.run_loop(stop, interval_seconds=0)
    assert calls == [round_id]
    with db_session_factory() as db:
        assert len(db.scalars(select(MatchResult)).all()) == 2
