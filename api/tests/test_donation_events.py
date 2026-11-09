"""The Watchdog's internal donation-event feed."""

from datetime import datetime, timedelta, timezone

from app.models import Donation, DonationStatus, Donor, Project, TargetType

INTERNAL = {"Authorization": "Bearer internal-test-token"}


def _donation(db, donor_id, project_id, amount, captured_at, status=DonationStatus.captured):
    donation = Donation(
        donor_id=donor_id,
        target_type=TargetType.PROJECT,
        project_id=project_id,
        amount=amount,
        currency="USD",
        status=status,
        captured_at=captured_at,
    )
    db.add(donation)
    db.flush()
    return donation


def test_event_feed_returns_donor_ids_newest_first_and_respects_since(client, db_session_factory):
    now = datetime.now(timezone.utc)
    with db_session_factory() as db:
        donor_a = Donor(paypal_payer_id="PAYER-AAA", created_at=now - timedelta(days=30))
        donor_b = Donor(paypal_payer_id="PAYER-BBB", created_at=now - timedelta(days=20))
        db.add_all([donor_a, donor_b])
        db.flush()
        db.get(Project, 2).owner_id = donor_b.id

        newest = _donation(db, donor_a.id, 1, 200, now - timedelta(hours=1))
        refunded = _donation(
            db, donor_b.id, 2, 300, now - timedelta(hours=2), status=DonationStatus.refunded
        )
        _donation(db, donor_a.id, 1, 400, now - timedelta(days=5))  # before since
        _donation(
            db, donor_a.id, 1, 500, now - timedelta(minutes=30), status=DonationStatus.pending
        )
        _donation(
            db, donor_a.id, 1, 600, now - timedelta(minutes=15), status=DonationStatus.failed
        )
        db.commit()
        expected = [newest.id, refunded.id]

    r = client.get(
        "/internal/donation-events",
        headers=INTERNAL,
        params={"since": (now - timedelta(days=1)).isoformat()},
    )
    assert r.status_code == 200, r.text
    events = r.json()
    assert [event["donation_id"] for event in events] == expected
    assert events[0]["donor_id"] == donor_a.id
    assert events[1]["donor_id"] == donor_b.id
    assert events[1]["owner_donor_id"] == donor_b.id
    assert events[1]["status"] == "refunded"
    assert isinstance(events[0]["donor_id"], int)
    assert isinstance(events[1]["owner_donor_id"], int)
    assert all(event["donor_created_at"] for event in events)
    assert "PAYER-" not in r.text


def test_event_feed_limit_and_auth(client, db_session_factory):
    now = datetime.now(timezone.utc)
    with db_session_factory() as db:
        donor = Donor()
        db.add(donor)
        db.flush()
        for i in range(3):
            _donation(db, donor.id, 1, 100, now - timedelta(minutes=i))
        db.commit()

    assert client.get("/internal/donation-events", params={"since": now.isoformat()}).status_code == 401
    r = client.get(
        "/internal/donation-events",
        headers=INTERNAL,
        params={"since": (now - timedelta(hours=1)).isoformat(), "limit": 2},
    )
    assert r.status_code == 200
    assert len(r.json()) == 2
