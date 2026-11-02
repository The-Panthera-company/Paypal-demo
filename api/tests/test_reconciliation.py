"""Category gifts reaching projects, the reconciliation report, and the stuck-order sweep."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import CategoryAllocation, Donation, LedgerEntry, Milestone, MilestoneStatus, Payout

ADMIN = {"Authorization": "Bearer admin-test-token"}
SIGNED = {"paypal-transmission-sig": "sig", "paypal-transmission-id": "t", "paypal-transmission-time": "now",
          "paypal-cert-url": "https://api.sandbox.paypal.com/cert", "paypal-auth-algo": "SHA256withRSA"}


def _order(client, **body):
    r = client.post("/donations/orders", json={"target_type": "PROJECT", "project_id": 1, "amount_cents": 2000} | body)
    assert r.status_code == 200, r.text
    return r.json()


def _pay(client, **body):
    out = _order(client, **body)
    client.post(f"/donations/orders/{out['order_id']}/capture")
    return out


def _age(db_session_factory, donation_id, minutes):
    with db_session_factory() as db:
        db.get(Donation, donation_id).created_at = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        db.commit()


def _report(client):
    r = client.get("/admin/reconciliation", headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()


def _checks(report):
    return {i["check"]: i["refs"] for i in report["issues"]}


# --- category gifts -----------------------------------------------------------------------


def test_category_gift_is_split_onto_projects_at_capture(client, db_session_factory):
    _pay(client, target_type="CATEGORY", project_id=None, category_id=1, rule="equal")
    assert [client.get(f"/projects/{i}").json()["raised_cents"] for i in (1, 2)] == [1000, 1000]
    assert client.get("/projects/1").json()["backer_count"] == 1
    assert client.get("/projects/1/funding-history").json()[-1]["raised_cents"] == 1000


def test_category_gift_respects_exclusions(client, db_session_factory):
    _pay(client, target_type="CATEGORY", project_id=None, category_id=1, excluded_tags=["faith-based"])
    assert client.get("/projects/1").json()["raised_cents"] == 2000
    assert client.get("/projects/2").json()["raised_cents"] == 0


def test_category_checkout_refused_when_nothing_eligible(client):
    r = client.post("/donations/orders", json={"target_type": "CATEGORY", "category_id": 1, "amount_cents": 2000,
                                               "excluded_tags": ["books", "faith-based"]})
    assert r.json()["detail"]["error"] == "NO_ELIGIBLE_PROJECTS"


def test_refunded_category_gift_leaves_project_totals(client):
    out = _pay(client, target_type="CATEGORY", project_id=None, category_id=1, rule="equal")
    refund = {"id": "REF-1", "amount": {"currency_code": "USD", "value": "20.00"},
              "links": [{"rel": "up", "href": f"https://api.sandbox.paypal.com/v2/payments/captures/CAP-{out['order_id']}"}]}
    client.post("/webhooks/paypal", headers=SIGNED, json={"id": "WH-R", "event_type": "PAYMENT.CAPTURE.REFUNDED", "resource": refund})
    assert client.get("/projects/1").json()["raised_cents"] == 0


def test_capturing_twice_never_allocates_twice(client, db_session_factory):
    out = _pay(client, target_type="CATEGORY", project_id=None, category_id=1)
    client.post(f"/donations/orders/{out['order_id']}/capture")
    with db_session_factory() as db:
        assert sum(a.amount for a in db.scalars(select(CategoryAllocation))) == 2000


# --- report -------------------------------------------------------------------------------


def test_clean_books_report_ok_with_totals(client):
    _pay(client)
    report = _report(client)
    assert report["ok"] is True and report["issues"] == []
    t = report["totals"]
    assert (t["received_via_paypal_cents"], t["paypal_fees_cents"], t["platform_balance_cents"]) == (2000, 59, 1941)


def test_report_finds_broken_records(client, db_session_factory):
    paid = _pay(client)
    stuck = _order(client)
    _age(db_session_factory, stuck["donation_id"], 45)
    with db_session_factory() as db:
        db.query(LedgerEntry).filter(LedgerEntry.donation_id == paid["donation_id"]).delete()
        m = Milestone(project_id=1, seq=1, title="Books", amount=500, currency="USD", status=MilestoneStatus.released)
        db.add(m)
        db.add(Payout(sender_batch_id="milestone-99-USD", currency="USD",
                      items=[{"project_id": 1, "milestone_id": 99, "amount_cents": 500, "receiver": None,
                              "status": "NEW", "error": "NO_PAYOUT_ACCOUNT"}]))
        db.commit()
        milestone_id = m.id
    report = _report(client)
    checks = _checks(report)
    assert report["ok"] is False
    assert checks["captured_without_ledger"] == [paid["donation_id"]]
    assert checks["stuck_orders"] == [stuck["donation_id"]]
    assert checks["released_without_payout"] == [milestone_id]
    assert checks["payout_not_sent"] == [1]
    severities = {i["check"]: i["severity"] for i in report["issues"]}
    assert severities["stuck_orders"] == "warning" and severities["captured_without_ledger"] == "error"


def test_report_needs_admin(client):
    assert client.get("/admin/reconciliation").status_code == 401


# --- sweep --------------------------------------------------------------------------------


def _sweep(client):
    r = client.post("/admin/reconciliation/sweep", headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()


def test_sweep_captures_approved_order_never_captured(client, fake_paypal, db_session_factory):
    """The donor approved in PayPal but our capture call never ran (the popup-loop case)."""
    out = _order(client)
    fake_paypal.orders[out["order_id"]]["status"] = "APPROVED"
    _age(db_session_factory, out["donation_id"], 45)
    result = _sweep(client)
    assert result["captured"] == [out["donation_id"]]
    assert client.get(f"/donations/{out['donation_id']}").json()["status"] == "captured"
    assert client.get("/projects/1").json()["raised_cents"] == 2000


def test_sweep_records_capture_paypal_already_made(client, fake_paypal, db_session_factory):
    out = _order(client)
    fake_paypal.capture(out["order_id"])
    _age(db_session_factory, out["donation_id"], 45)
    assert _sweep(client)["captured"] == [out["donation_id"]]


def test_sweep_closes_abandoned_and_skips_young_orders(client, fake_paypal, db_session_factory):
    old = _order(client)
    young = _order(client)
    _age(db_session_factory, old["donation_id"], 4 * 60)
    result = _sweep(client)
    assert result["failed"] == [old["donation_id"]] and result["checked"] == 1
    assert client.get(f"/donations/{young['donation_id']}").json()["status"] == "created"


def test_sweep_reports_paypal_errors_and_carries_on(client, fake_paypal, db_session_factory):
    broken = _order(client)
    fine = _order(client)
    fake_paypal.orders[fine["order_id"]]["status"] = "APPROVED"
    for d in (broken, fine):
        _age(db_session_factory, d["donation_id"], 45)
    del fake_paypal.orders[broken["order_id"]]  # PayPal answers 404 for it
    result = _sweep(client)
    assert result["errors"] and str(broken["donation_id"]) in result["errors"][0]
    assert result["captured"] == [fine["donation_id"]]
