"""PayPal Payouts: released tranches are paid with deterministic batch ids, tracked, and retried."""

import json

from sqlalchemy import select

from app.models import LedgerEntry, Milestone, Payout

ADMIN = {"Authorization": "Bearer admin-test-token"}
INTERNAL = {"Authorization": "Bearer internal-test-token"}
PASS = {"receipt_total_within_10pct": True, "supplier_matches_plan": True, "photo_not_duplicate": True, "dated_in_window": True}
SIGNED = {"paypal-transmission-sig": "sig", "paypal-transmission-id": "t", "paypal-transmission-time": "now",
          "paypal-cert-url": "https://api.sandbox.paypal.com/cert", "paypal-auth-algo": "SHA256withRSA"}


def _milestone(db_session_factory, amount=30_000, match=5_000):
    with db_session_factory() as db:
        m = Milestone(project_id=1, seq=1, title="Buy 40 books", amount=amount, match_amount=match, currency="USD")
        db.add(m)
        db.commit()
        return m.id


def _account(client, email="lanet@example.com"):
    r = client.put("/admin/projects/1/payout-account", headers=ADMIN, json={"paypal_email": email})
    assert r.status_code == 200, r.text


def _release(client, milestone_id):
    r = client.post("/internal/payout-requests", headers=INTERNAL,
                    json={"milestone_id": milestone_id, "checks": PASS, "summary": "ok"})
    assert r.json()["status"] == "released", r.text
    return r.json()


def _payout(client, payout_id):
    return next(p for p in client.get("/admin/payouts", headers=ADMIN).json() if p["id"] == payout_id)


def _payout_entries(db_session_factory):
    with db_session_factory() as db:
        return [(e.amount, e.payout_item_id) for e in db.scalars(select(LedgerEntry)) if e.type.value == "payout"]


def _hook(client, event_id, event_type, resource):
    return client.post("/webhooks/paypal", headers=SIGNED,
                       json={"id": event_id, "event_type": event_type, "resource": resource}).json()


def test_release_sends_a_deterministic_batch(client, fake_paypal, db_session_factory):
    _account(client)
    mid = _milestone(db_session_factory)
    out = _release(client, mid)
    payout = _payout(client, out["payout_id"])
    assert payout["sender_batch_id"] == f"milestone-{mid}-USD"
    assert (payout["status"], payout["paypal_batch_id"]) == ("processing", "BATCH1")
    assert (payout["items"][0]["amount_cents"], payout["items"][0]["receiver"], payout["items"][0]["status"]) == (
        35_000, "lanet@example.com", "PENDING")

    sent = fake_paypal.payouts["BATCH1"]
    assert sent["items"][0]["amount"] == {"value": "350.00", "currency": "USD"}  # tranche + match
    req = next(q for q in fake_paypal.requests if q.url.path == "/v1/payments/payouts")
    assert req.headers["PayPal-Request-Id"] == f"milestone-{mid}-USD"
    assert _payout_entries(db_session_factory) == []  # not paid until PayPal says so


def test_no_payout_account_waits_then_sends(client, fake_paypal, db_session_factory):
    mid = _milestone(db_session_factory)
    out = _release(client, mid)
    assert "NO_PAYOUT_ACCOUNT" in out["reason"]
    payout = _payout(client, out["payout_id"])
    assert (payout["status"], payout["items"][0]["error"]) == ("pending", "NO_PAYOUT_ACCOUNT")
    assert fake_paypal.payouts == {}

    _account(client)
    sent = client.post(f"/admin/payouts/{out['payout_id']}/send", headers=ADMIN).json()
    assert sent["status"] == "processing" and sent["items"][0]["error"] is None
    again = client.post(f"/admin/payouts/{out['payout_id']}/send", headers=ADMIN).json()
    assert again["detail"]["error"] == "ALREADY_SENT"
    assert len(fake_paypal.payouts) == 1


def test_paypal_refusal_keeps_release_and_can_be_resent(client, fake_paypal, db_session_factory):
    _account(client)
    fake_paypal.payout_error = (422, {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "INSUFFICIENT_FUNDS"}]})
    mid = _milestone(db_session_factory)
    out = _release(client, mid)
    assert _payout(client, out["payout_id"])["items"][0]["error"] == "INSUFFICIENT_FUNDS"
    with db_session_factory() as db:
        assert db.get(Milestone, mid).status.value == "released"
    fake_paypal.payout_error = None
    assert client.post(f"/admin/payouts/{out['payout_id']}/send", headers=ADMIN).json()["status"] == "processing"


def test_refresh_books_successful_items_once(client, fake_paypal, db_session_factory):
    _account(client)
    out = _release(client, _milestone(db_session_factory))
    for _ in range(2):
        refreshed = client.post(f"/admin/payouts/{out['payout_id']}/refresh", headers=ADMIN).json()
    assert refreshed["status"] == "success"
    assert refreshed["items"][0]["status"] == "SUCCESS"
    assert _payout_entries(db_session_factory) == [(35_000, "ITEM-BATCH1-1")]


def test_item_webhooks_update_status_and_book_success(client, fake_paypal, db_session_factory):
    _account(client)
    out = _release(client, _milestone(db_session_factory))
    item = fake_paypal.payout_batch("BATCH1", "UNCLAIMED")["items"][0]
    assert _hook(client, "WH-P1", "PAYMENT.PAYOUTS-ITEM.UNCLAIMED", item)["status"] == "processed"
    assert _payout(client, out["payout_id"])["items"][0]["status"] == "UNCLAIMED"
    assert _payout_entries(db_session_factory) == []

    item = fake_paypal.payout_batch("BATCH1", "SUCCESS")["items"][0]
    _hook(client, "WH-P2", "PAYMENT.PAYOUTS-ITEM.SUCCEEDED", item)
    _hook(client, "WH-P3", "PAYMENT.PAYOUTS-ITEM.SUCCEEDED", item | {"x": 1})  # same item, new event id
    assert _payout_entries(db_session_factory) == [(35_000, "ITEM-BATCH1-1")]
    assert _hook(client, "WH-P4", "PAYMENT.PAYOUTS-ITEM.SUCCEEDED", item | {"payout_batch_id": "OTHER"})["status"] == "unmatched"


def test_batch_webhook_finds_payout_by_our_id_when_paypal_id_missing(client, fake_paypal, db_session_factory):
    _account(client)
    out = _release(client, _milestone(db_session_factory))
    with db_session_factory() as db:  # as if we crashed before saving PayPal's batch id
        db.get(Payout, out["payout_id"]).paypal_batch_id = None
        db.commit()
    batch = fake_paypal.payout_batch("BATCH1")
    assert _hook(client, "WH-B1", "PAYMENT.PAYOUTSBATCH.SUCCESS", batch)["status"] == "processed"
    payout = _payout(client, out["payout_id"])
    assert (payout["paypal_batch_id"], payout["status"]) == ("BATCH1", "success")


def test_failed_item_retried_in_new_batch_with_new_id(client, fake_paypal, db_session_factory):
    _account(client, "wrong@example.com")
    mid = _milestone(db_session_factory)
    out = _release(client, mid)
    fake_paypal.payout_item_status = "FAILED"
    client.post(f"/admin/payouts/{out['payout_id']}/refresh", headers=ADMIN)
    r = client.post(f"/admin/payouts/{out['payout_id']}/retry", headers=ADMIN)
    assert r.status_code == 201
    retry1 = r.json()
    assert (retry1["sender_batch_id"], retry1["paypal_batch_id"]) == (f"milestone-{mid}-USD-retry1", "BATCH2")

    # Still the wrong address, so it fails again; fix the account and retry that batch.
    _account(client, "lanet@example.com")
    client.post(f"/admin/payouts/{retry1['id']}/refresh", headers=ADMIN)
    retry2 = client.post(f"/admin/payouts/{retry1['id']}/retry", headers=ADMIN).json()
    assert retry2["sender_batch_id"] == f"milestone-{mid}-USD-retry2"
    assert retry2["items"][0]["receiver"] == "lanet@example.com"
    assert json.dumps(fake_paypal.payouts["BATCH3"]["items"][0]["sender_item_id"]) == f'"milestone-{mid}-retry2"'
    assert _payout(client, out["payout_id"])["items"][0]["status"] == "RETRIED"
    assert client.post(f"/admin/payouts/{out['payout_id']}/retry", headers=ADMIN).json()["detail"]["error"] == "NOTHING_TO_RETRY"


def test_admin_review_approval_pays_too(client, fake_paypal, db_session_factory):
    _account(client)
    mid = _milestone(db_session_factory, amount=60_000, match=0)  # above threshold: held
    r = client.post("/internal/payout-requests", headers=INTERNAL, json={"milestone_id": mid, "checks": PASS, "summary": "big"})
    assert r.json()["status"] == "held_for_admin"
    client.post(f"/admin/milestones/{mid}/review", headers=ADMIN, json={"approve": True})
    assert fake_paypal.payouts["BATCH1"]["sender_batch_header"]["sender_batch_id"] == f"milestone-{mid}-USD"


def test_payout_account_routes(client):
    assert client.get("/admin/projects/1/payout-account", headers=ADMIN).status_code == 404
    assert client.put("/admin/projects/1/payout-account", headers=ADMIN, json={"paypal_email": "nope"}).status_code == 422
    assert client.put("/admin/projects/99/payout-account", headers=ADMIN, json={"paypal_email": "a@b.co"}).status_code == 404
    _account(client)
    assert client.get("/admin/projects/1/payout-account", headers=ADMIN).json()["paypal_email"] == "lanet@example.com"
    assert client.put("/admin/projects/1/payout-account", json={"paypal_email": "a@b.co"}).status_code == 401
