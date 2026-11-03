"""Monthly Giving Agent budgets through PayPal Subscriptions."""

from sqlalchemy import select

from app.models import Donor, LedgerEntry, PaypalPlan

ADMIN = {"Authorization": "Bearer admin-test-token"}
SIGNED = {"paypal-transmission-sig": "s", "paypal-transmission-id": "t", "paypal-transmission-time": "n",
          "paypal-cert-url": "https://api.sandbox.paypal.com/c", "paypal-auth-algo": "SHA256withRSA"}
MANDATE = {"monthly_budget_cents": 5000, "categories": [1], "excluded_tags": [], "per_project_max_cents": 1000,
           "approval_threshold_cents": 1000}


def _donor(db_session_factory):
    with db_session_factory() as db:
        donor = Donor(display_name="Demo donor")
        db.add(donor)
        db.commit()
        return donor.id


def _start(client, donor_id, cents=2500):
    return client.post(f"/donors/{donor_id}/mandate/subscription", json={"monthly_amount_cents": cents})


def _hook(client, event_id, event_type, resource):
    return client.post("/webhooks/paypal", headers=SIGNED,
                       json={"id": event_id, "event_type": event_type, "resource": resource}).json()


def _sale(sub_id, sale_id="SALE-1", total="25.00"):
    return {"id": sale_id, "state": "completed", "billing_agreement_id": sub_id,
            "amount": {"total": total, "currency": "USD"}, "transaction_fee": {"value": "1.03", "currency": "USD"}}


def test_start_creates_one_plan_and_a_subscription_for_the_amount(client, fake_paypal, db_session_factory):
    donor_id = _donor(db_session_factory)
    r = _start(client, donor_id)
    assert r.status_code == 201, r.text
    out = r.json()
    assert (out["status"], out["monthly_amount_cents"]) == ("APPROVAL_PENDING", 2500)
    assert out["approve_url"].startswith("https://www.sandbox.paypal.com/")
    sent = fake_paypal.subscriptions[out["subscription_id"]]
    assert (sent["quantity"], sent["custom_id"]) == ("25", f"donor:{donor_id}")
    assert sent["application_context"]["return_url"].endswith("/mandate?subscription=approved")
    [plan] = fake_paypal.plans.values()
    assert plan["quantity_supported"] is True
    assert plan["billing_cycles"][0]["pricing_scheme"]["fixed_price"] == {"value": "1.00", "currency_code": "USD"}

    # A second donor reuses the plan.
    _start(client, _donor(db_session_factory), 1000)
    assert len(fake_paypal.plans) == 1
    with db_session_factory() as db:
        assert db.scalar(select(PaypalPlan)).plan_id == "P-1"


def test_amount_must_be_whole_dollars_and_donor_must_exist(client, db_session_factory):
    donor_id = _donor(db_session_factory)
    assert _start(client, donor_id, 2550).json()["detail"]["error"] == "WHOLE_DOLLARS_ONLY"
    assert _start(client, donor_id, 50).status_code == 422
    assert _start(client, 999).status_code == 404


def test_monthly_charge_credits_the_agent_budget_once(client, fake_paypal, db_session_factory):
    donor_id = _donor(db_session_factory)
    sub_id = _start(client, donor_id).json()["subscription_id"]
    client.put(f"/donors/{donor_id}/mandate", json=MANDATE)
    assert _hook(client, "WH-A", "BILLING.SUBSCRIPTION.ACTIVATED", {"id": sub_id, "status": "ACTIVE"})["status"] == "processed"
    assert client.get(f"/donors/{donor_id}/mandate/subscription").json()["status"] == "ACTIVE"

    assert _hook(client, "WH-S1", "PAYMENT.SALE.COMPLETED", _sale(sub_id))["status"] == "processed"
    _hook(client, "WH-S1b", "PAYMENT.SALE.COMPLETED", _sale(sub_id))  # same sale, new event id
    assert client.get(f"/donors/{donor_id}/mandate").json()["funded_balance_cents"] == 2500
    _hook(client, "WH-S2", "PAYMENT.SALE.COMPLETED", _sale(sub_id, "SALE-2"))  # next month
    assert client.get(f"/donors/{donor_id}/mandate").json()["funded_balance_cents"] == 5000

    with db_session_factory() as db:
        entries = sorted((e.type.value, e.amount) for e in db.scalars(select(LedgerEntry)))
    assert entries == [("donation", 2500), ("donation", 2500), ("fee", 103), ("fee", 103)]
    # Reconciliation counts subscription charges as PayPal money and finds nothing wrong.
    report = client.get("/admin/reconciliation", headers=ADMIN).json()
    assert report["ok"] is True and report["totals"]["received_via_paypal_cents"] == 5000
    # Top-ups aren't gifts in the donor report.
    assert client.get(f"/donors/{donor_id}/report").json()["gifts"] == []


def test_unknown_subscription_sale_is_unmatched(client):
    assert _hook(client, "WH-X", "PAYMENT.SALE.COMPLETED", _sale("I-NOT-OURS"))["status"] == "unmatched"


def test_cancel_stops_it_at_paypal_and_keeps_credited_money(client, fake_paypal, db_session_factory):
    donor_id = _donor(db_session_factory)
    sub_id = _start(client, donor_id).json()["subscription_id"]
    client.put(f"/donors/{donor_id}/mandate", json=MANDATE)
    _hook(client, "WH-A", "BILLING.SUBSCRIPTION.ACTIVATED", {"id": sub_id})
    _hook(client, "WH-S1", "PAYMENT.SALE.COMPLETED", _sale(sub_id))
    r = client.post(f"/donors/{donor_id}/mandate/subscription/cancel")
    assert r.json()["status"] == "CANCELLED"
    assert fake_paypal.cancelled == [sub_id]
    assert client.get(f"/donors/{donor_id}/mandate").json()["funded_balance_cents"] == 2500
    assert client.get(f"/donors/{donor_id}/mandate/subscription").status_code == 404
    assert _start(client, donor_id).status_code == 201  # can subscribe again


def test_active_subscription_must_be_cancelled_before_a_new_one(client, db_session_factory):
    donor_id = _donor(db_session_factory)
    first = _start(client, donor_id).json()["subscription_id"]
    second = _start(client, donor_id)  # replaces an unapproved attempt
    assert second.status_code == 201
    _hook(client, "WH-A", "BILLING.SUBSCRIPTION.ACTIVATED", {"id": second.json()["subscription_id"]})
    assert _start(client, donor_id).json()["detail"]["error"] == "ALREADY_SUBSCRIBED"
    assert client.get(f"/donors/{donor_id}/mandate/subscription").json()["subscription_id"] != first


def test_status_webhooks(client, db_session_factory):
    donor_id = _donor(db_session_factory)
    sub_id = _start(client, donor_id).json()["subscription_id"]
    _hook(client, "WH-1", "BILLING.SUBSCRIPTION.ACTIVATED", {"id": sub_id})
    _hook(client, "WH-2", "BILLING.SUBSCRIPTION.SUSPENDED", {"id": sub_id})
    assert client.get(f"/donors/{donor_id}/mandate/subscription").json()["status"] == "SUSPENDED"
    _hook(client, "WH-3", "BILLING.SUBSCRIPTION.CANCELLED", {"id": sub_id})
    assert client.get(f"/donors/{donor_id}/mandate/subscription").status_code == 404
