"""PayPal webhooks: signature check, repeats, settle, deny, refund and reversal."""

from sqlalchemy import select

from app.config import get_settings
from app.main import app
from app.models import AuditLog, LedgerEntry, WebhookEvent

ADMIN = {"Authorization": "Bearer admin-test-token"}
SIGNED = {
    "paypal-auth-algo": "SHA256withRSA",
    "paypal-cert-url": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT",
    "paypal-transmission-id": "tx-1",
    "paypal-transmission-sig": "sig",
    "paypal-transmission-time": "2026-11-02T10:00:00Z",
}


def _order(client, amount=2000):
    return client.post(
        "/donations/orders", json={"target_type": "PROJECT", "project_id": 1, "amount_cents": amount}
    ).json()


def _send(client, event_id, event_type, resource):
    return client.post(
        "/webhooks/paypal", json={"id": event_id, "event_type": event_type, "resource": resource}, headers=SIGNED
    )


def _capture_resource(order_id, donation_id, status="COMPLETED"):
    return {
        "id": f"CAP-{order_id}",
        "status": status,
        "custom_id": f"donation:{donation_id}",
        "amount": {"currency_code": "USD", "value": "20.00"},
        "supplementary_data": {"related_ids": {"order_id": order_id}},
    }


def _refund_resource(capture_id, value="20.00"):
    return {
        "id": "REF-1",
        "status": "COMPLETED",
        "amount": {"currency_code": "USD", "value": value},
        "links": [{"rel": "up", "href": f"https://api.sandbox.paypal.com/v2/payments/captures/{capture_id}"}],
    }


def _ledger(db_session_factory):
    with db_session_factory() as db:
        return sorted((e.type.value, e.amount) for e in db.scalars(select(LedgerEntry)))


def test_rejects_unsigned_and_bad_signatures(client, fake_paypal):
    body = {"id": "WH-1", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {}}
    assert client.post("/webhooks/paypal", json=body).json()["detail"]["error"] == "INVALID_WEBHOOK"
    fake_paypal.verification_status = "FAILURE"
    r = client.post("/webhooks/paypal", json=body, headers=SIGNED)
    assert (r.status_code, r.json()["detail"]["error"]) == (400, "INVALID_SIGNATURE")


def test_fails_closed_without_webhook_id(client):
    app.dependency_overrides[get_settings]().paypal_webhook_id = ""
    r = _send(client, "WH-1", "PAYMENT.CAPTURE.COMPLETED", {})
    assert (r.status_code, r.json()["detail"]["error"]) == (503, "WEBHOOK_NOT_CONFIGURED")


def test_completed_webhook_records_a_capture_our_call_missed(client, fake_paypal, db_session_factory):
    """The browser closed after approval: PayPal captured, our capture route never ran."""
    out = _order(client)
    order_id = out["order_id"]
    fake_paypal.capture(order_id)

    r = _send(client, "WH-1", "PAYMENT.CAPTURE.COMPLETED", _capture_resource(order_id, out["donation_id"]))
    assert r.json() == {"event_id": "WH-1", "status": "processed"}
    assert client.get(f"/donations/{out['donation_id']}").json()["status"] == "captured"
    assert _ledger(db_session_factory) == [("donation", 2000), ("fee", 59)]


def test_repeat_delivery_is_skipped(client, db_session_factory):
    out = _order(client)
    client.post(f"/donations/orders/{out['order_id']}/capture")
    resource = _capture_resource(out["order_id"], out["donation_id"])
    assert _send(client, "WH-1", "PAYMENT.CAPTURE.COMPLETED", resource).json()["status"] == "processed"
    assert _send(client, "WH-1", "PAYMENT.CAPTURE.COMPLETED", resource).json()["status"] == "duplicate"
    # Already captured by the route: the webhook writes nothing more.
    assert _ledger(db_session_factory) == [("donation", 2000), ("fee", 59)]


def test_pending_then_completed(client, fake_paypal, db_session_factory):
    fake_paypal.capture_status = "PENDING"
    out = _order(client)
    assert client.post(f"/donations/orders/{out['order_id']}/capture").json()["status"] == "pending"
    assert _ledger(db_session_factory) == []

    fake_paypal.orders[out["order_id"]]["purchase_units"][0]["payments"]["captures"][0]["status"] = "COMPLETED"
    _send(client, "WH-2", "PAYMENT.CAPTURE.COMPLETED", _capture_resource(out["order_id"], out["donation_id"]))
    assert client.get(f"/donations/{out['donation_id']}").json()["status"] == "captured"
    assert _ledger(db_session_factory) == [("donation", 2000), ("fee", 59)]


def test_denied_marks_pending_donation_failed(client, fake_paypal):
    fake_paypal.capture_status = "PENDING"
    out = _order(client)
    client.post(f"/donations/orders/{out['order_id']}/capture")
    _send(client, "WH-3", "PAYMENT.CAPTURE.DENIED", _capture_resource(out["order_id"], out["donation_id"], "DECLINED"))
    assert client.get(f"/donations/{out['donation_id']}").json()["status"] == "failed"


def test_full_refund_leaves_totals(client, db_session_factory):
    out = _order(client)
    client.post(f"/donations/orders/{out['order_id']}/capture")
    assert client.get("/projects/1").json()["raised_cents"] == 2000

    r = _send(client, "WH-4", "PAYMENT.CAPTURE.REFUNDED", _refund_resource(f"CAP-{out['order_id']}"))
    assert r.json()["status"] == "processed"
    assert client.get(f"/donations/{out['donation_id']}").json()["status"] == "refunded"
    assert client.get("/projects/1").json()["raised_cents"] == 0
    assert ("refund", 2000) in _ledger(db_session_factory)


def test_partial_refund_keeps_donation_counted(client, db_session_factory):
    out = _order(client)
    client.post(f"/donations/orders/{out['order_id']}/capture")
    _send(client, "WH-5", "PAYMENT.CAPTURE.REFUNDED", _refund_resource(f"CAP-{out['order_id']}", "5.00"))
    assert client.get(f"/donations/{out['donation_id']}").json()["status"] == "captured"
    assert ("refund", 500) in _ledger(db_session_factory)
    # The rest refunded later completes it.
    _send(client, "WH-6", "PAYMENT.CAPTURE.REFUNDED", _refund_resource(f"CAP-{out['order_id']}", "15.00"))
    assert client.get(f"/donations/{out['donation_id']}").json()["status"] == "refunded"


def test_reversal_refunds_and_logs_for_admin(client, db_session_factory):
    out = _order(client)
    client.post(f"/donations/orders/{out['order_id']}/capture")
    _send(client, "WH-7", "PAYMENT.CAPTURE.REVERSED", _refund_resource(f"CAP-{out['order_id']}"))
    assert client.get(f"/donations/{out['donation_id']}").json()["status"] == "refunded"
    with db_session_factory() as db:
        assert db.scalar(select(AuditLog)).action == "capture_reversed"


def test_unknown_and_unmatched_events_are_recorded(client, db_session_factory):
    assert _send(client, "WH-8", "CHECKOUT.ORDER.APPROVED", {"id": "X"}).json()["status"] == "ignored"
    assert _send(client, "WH-9", "PAYMENT.CAPTURE.REFUNDED", _refund_resource("NOT-OURS")).json()["status"] == "unmatched"
    events = client.get("/admin/webhook-events", headers=ADMIN).json()
    assert {(e["id"], e["result"]) for e in events} == {("WH-8", "ignored"), ("WH-9", "unmatched")}


def test_amount_mismatch_is_not_recorded_as_captured(client, fake_paypal):
    out = _order(client)
    order_id = out["order_id"]
    fake_paypal.capture(order_id)
    fake_paypal.orders[order_id]["purchase_units"][0]["payments"]["captures"][0]["amount"]["value"] = "1.00"
    r = _send(client, "WH-10", "PAYMENT.CAPTURE.COMPLETED", _capture_resource(order_id, out["donation_id"]))
    assert r.json()["status"] == "mismatch"
    assert client.get(f"/donations/{out['donation_id']}").json()["status"] == "created"


def test_paypal_outage_is_not_recorded_so_paypal_retries(client, fake_paypal, db_session_factory):
    out = _order(client)
    fake_paypal.get_order_down = True
    r = _send(client, "WH-11", "PAYMENT.CAPTURE.COMPLETED", _capture_resource(out["order_id"], out["donation_id"]))
    assert r.status_code == 502
    with db_session_factory() as db:
        assert db.get(WebhookEvent, "WH-11") is None
