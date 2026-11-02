import json

from sqlalchemy import select

from app.models import Donation, Donor, LedgerEntry


def _create(client, **overrides):
    body = {"target_type": "PROJECT", "project_id": 1, "amount_cents": 2000} | overrides
    return client.post("/donations/orders", json=body)


def test_create_order_sets_server_side_amount_and_custom_id(client, fake_paypal):
    r = _create(client)
    assert r.status_code == 200, r.text
    out = r.json()

    order = fake_paypal.orders[out["order_id"]]
    unit = order["purchase_units"][0]
    assert (unit["amount"]["currency_code"], unit["amount"]["value"]) == ("USD", "20.00")
    assert unit["custom_id"] == f"donation:{out['donation_id']}"

    create_req = next(q for q in fake_paypal.requests if q.url.path == "/v2/checkout/orders")
    assert create_req.headers["PayPal-Request-Id"] == f"create-donation:{out['donation_id']}"


def test_order_is_a_donation_item_without_payment_source(client, fake_paypal):
    _create(client)
    sent = json.loads(next(q for q in fake_paypal.requests if q.url.path == "/v2/checkout/orders").content)
    # payment_source made the JS SDK popup loop without calling onApprove.
    assert "payment_source" not in sent
    unit = sent["purchase_units"][0]
    assert unit["items"][0]["category"] == "DONATION"
    assert unit["amount"]["breakdown"]["item_total"] == {"currency_code": "USD", "value": "20.00"}


def test_create_rejects_bad_input(client):
    assert _create(client, amount_cents=10).status_code == 422
    assert _create(client, amount_cents=10_000_000).status_code == 422
    assert _create(client, category_id=3).status_code == 422
    assert _create(client, target_type="AGENT").status_code == 422
    assert client.post("/donations/orders", json={"target_type": "CATEGORY", "amount_cents": 2000}).status_code == 422


def test_capture_records_donation_donor_and_ledger(client, fake_paypal, db_session_factory):
    order_id = _create(client).json()["order_id"]
    r = client.post(f"/donations/orders/{order_id}/capture")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "captured"
    assert out["paypal_capture_id"] == f"CAP-{order_id}"

    with db_session_factory() as db:
        donor = db.scalar(select(Donor))
        assert donor.paypal_payer_id == "PAYER123"
        assert donor.is_guest is False
        entries = {e.type.value: e.amount for e in db.scalars(select(LedgerEntry))}
        assert entries == {"donation": 2000, "fee": 59}


def test_capture_twice_is_idempotent(client, fake_paypal, db_session_factory):
    order_id = _create(client).json()["order_id"]
    client.post(f"/donations/orders/{order_id}/capture")
    r = client.post(f"/donations/orders/{order_id}/capture")
    assert r.status_code == 200
    with db_session_factory() as db:
        assert len(db.scalars(select(LedgerEntry)).all()) == 2
    captures = [q for q in fake_paypal.requests if q.url.path.endswith("/capture")]
    assert len(captures) == 1


def test_same_payer_reuses_donor(client, db_session_factory):
    for _ in range(2):
        order_id = _create(client).json()["order_id"]
        client.post(f"/donations/orders/{order_id}/capture")
    with db_session_factory() as db:
        assert len(db.scalars(select(Donor)).all()) == 1


def test_card_payment_marks_guest(client, fake_paypal, db_session_factory):
    fake_paypal.payment_source = {"card": {"last_digits": "1111"}}
    order_id = _create(client).json()["order_id"]
    client.post(f"/donations/orders/{order_id}/capture")
    with db_session_factory() as db:
        assert db.scalar(select(Donor)).is_guest is True


def test_pending_capture_does_not_hit_ledger(client, fake_paypal, db_session_factory):
    fake_paypal.capture_status = "PENDING"
    order_id = _create(client).json()["order_id"]
    assert client.post(f"/donations/orders/{order_id}/capture").json()["status"] == "pending"
    with db_session_factory() as db:
        assert db.scalars(select(LedgerEntry)).all() == []


def test_declined_card_asks_frontend_to_restart(client, fake_paypal):
    order_id = _create(client).json()["order_id"]
    fake_paypal.capture_override = (422, {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "INSTRUMENT_DECLINED"}]})
    r = client.post(f"/donations/orders/{order_id}/capture")
    assert r.status_code == 422
    assert r.json()["detail"] == {"error": "INSTRUMENT_DECLINED", "message": "The payment method was declined", "restart": True}


def test_already_captured_falls_back_to_get_order(client, fake_paypal, db_session_factory):
    order_id = _create(client).json()["order_id"]
    client.post(f"/donations/orders/{order_id}/capture")
    # Simulate our DB missing the result (e.g. we crashed after PayPal captured).
    with db_session_factory() as db:
        d = db.scalar(select(Donation))
        d.status = d.status.created
        db.query(LedgerEntry).delete()
        db.commit()
    fake_paypal.capture_override = (422, {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "ORDER_ALREADY_CAPTURED"}]})
    r = client.post(f"/donations/orders/{order_id}/capture")
    assert r.json()["status"] == "captured"


def test_amount_mismatch_is_rejected(client, fake_paypal, db_session_factory):
    order_id = _create(client).json()["order_id"]
    fake_paypal.orders[order_id]["purchase_units"][0]["amount"] = {"currency_code": "USD", "value": "1.00"}
    r = client.post(f"/donations/orders/{order_id}/capture")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "AMOUNT_MISMATCH"


def test_create_rejects_projects_not_open(client):
    assert _create(client, project_id=3).json()["detail"]["error"] == "PROJECT_NOT_OPEN"  # pending_review
    assert _create(client, project_id=999).json()["detail"]["error"] == "PROJECT_NOT_OPEN"
    r = client.post("/donations/orders", json={"target_type": "CATEGORY", "category_id": 99, "amount_cents": 2000})
    assert r.json()["detail"]["error"] == "CATEGORY_NOT_FOUND"


def test_order_description_uses_project_title(client, fake_paypal):
    out = _create(client).json()
    assert fake_paypal.orders[out["order_id"]]["purchase_units"][0]["description"] == "Donation to Lanet Library"


def test_get_donation(client):
    out = _create(client).json()
    r = client.get(f"/donations/{out['donation_id']}")
    assert r.status_code == 200
    assert r.json()["status"] == "created"
    assert client.get("/donations/999").status_code == 404


def test_unknown_order_404(client):
    assert client.post("/donations/orders/NOPE/capture").status_code == 404


def test_token_is_cached(client, fake_paypal):
    order_id = _create(client).json()["order_id"]
    client.post(f"/donations/orders/{order_id}/capture")
    assert fake_paypal.token_calls == 1
