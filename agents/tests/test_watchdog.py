"""Watchdog rule tests. Pure functions over seeded events, no network, no LLM."""
from datetime import datetime, timedelta, timezone

from app.agents.watchdog import (
    new_payer_burst,
    owner_donation,
    reciprocal_backing,
    refund_spike,
)

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


def ev(pid=1, donor="d1", amount=100, minutes_ago=1, age_hours=1, status="captured",
       owner="owner-1"):
    return {
        "donation_id": str(pid) + donor + str(minutes_ago),
        "project_id": pid,
        "status": status,
        "amount_cents": amount,
        "captured_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
        "payer_id": donor,
        "is_guest": False,
        "donor_created_at": (NOW - timedelta(hours=age_hours)).isoformat(),
        "owner_payer_id": owner,
    }


def test_new_payer_burst_fires_on_eight_small_new_donors():
    events = [ev(pid=1, donor="d" + str(i), amount=400, minutes_ago=i) for i in range(8)]
    hits = new_payer_burst(events, NOW)
    assert len(hits) == 1
    assert hits[0]["rule"] == "new_payer_burst"
    assert len(hits[0]["evidence"]["donor_ids"]) == 8


def test_new_payer_burst_ignores_established_donors():
    events = [ev(pid=1, donor="d" + str(i), amount=400, minutes_ago=i, age_hours=48)
              for i in range(8)]
    assert new_payer_burst(events, NOW) == []


def test_new_payer_burst_ignores_large_amounts():
    events = [ev(pid=1, donor="d" + str(i), amount=900, minutes_ago=i) for i in range(8)]
    assert new_payer_burst(events, NOW) == []


def test_new_payer_burst_ignores_spread_out_donations():
    events = [ev(pid=1, donor="d" + str(i), amount=400, minutes_ago=i * 10) for i in range(8)]
    assert new_payer_burst(events, NOW) == []


def test_reciprocal_backing_fires_on_shared_donors():
    events = [
        ev(pid=1, donor="a"), ev(pid=2, donor="a"),
        ev(pid=1, donor="b"), ev(pid=2, donor="b"),
        ev(pid=1, donor="a"),
    ]
    hits = reciprocal_backing(events)
    assert len(hits) == 1
    assert hits[0]["rule"] == "reciprocal_backing"


def test_reciprocal_backing_ignores_single_shared_donor():
    events = [ev(pid=1, donor="a"), ev(pid=2, donor="a"), ev(pid=1, donor="a")]
    assert reciprocal_backing(events) == []


def test_owner_donation_fires_when_payer_is_owner():
    events = [ev(pid=1, donor="owner-1", owner="owner-1")]
    hits = owner_donation(events)
    assert len(hits) == 1
    assert hits[0]["evidence"]["donor_ids"] == ["owner-1"]


def test_owner_donation_ignores_other_donors():
    assert owner_donation([ev(pid=1, donor="x", owner="owner-1")]) == []


def test_refund_spike_fires_at_thirty_percent():
    events = [ev(pid=1, donor="d" + str(i), minutes_ago=i, status=("refunded" if i < 2 else "captured"))
              for i in range(6)]
    hits = refund_spike(events, NOW)
    assert len(hits) == 1
    assert hits[0]["evidence"]["counts"] == {"refunds": 2, "donations": 6}


def test_refund_spike_needs_five_donations():
    events = [ev(pid=1, donor="d" + str(i), status="refunded") for i in range(4)]
    assert refund_spike(events, NOW) == []


def test_refund_spike_ignores_old_donations():
    events = [ev(pid=1, donor="d" + str(i), minutes_ago=60 * 48, status="refunded")
              for i in range(6)]
    assert refund_spike(events, NOW) == []
