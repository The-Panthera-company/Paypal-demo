"""The quadratic funding workflow around the engine: match preview, round controls and results,
sponsors adding to the pool, project applications with evidence uploads, and admin refunds."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Donation, DonationStatus, Donor, LedgerEntry, LedgerType, Milestone, Round, RoundStatus, TargetType

ADMIN = {"Authorization": "Bearer admin-test-token"}
INTERNAL = {"Authorization": "Bearer internal-test-token"}
NOW = datetime.now(timezone.utc)


def _round(db_session_factory, *, backers=(4, 1), pool=10_000, status=RoundStatus.open, starts=-2, ends=5):
    """An open round (no cap) with `backers` people giving 1 USD each to projects 1 and 2."""
    with db_session_factory() as db:
        r = Round(name="November", starts_at=NOW + timedelta(days=starts), ends_at=NOW + timedelta(days=ends),
                  matching_pool=pool, currency="USD", status=status, project_cap_pct=100)
        db.add(r)
        for project_id, n in zip((1, 2), backers):
            for _ in range(n):
                donor = Donor()
                db.add(donor)
                db.flush()
                db.add(Donation(donor_id=donor.id, target_type=TargetType.PROJECT, project_id=project_id, amount=100,
                                currency="USD", status=DonationStatus.captured, captured_at=NOW - timedelta(hours=1)))
        db.commit()
        return r.id


def _pay(client, **body):
    out = client.post("/donations/orders", json=body).json()
    return client.post(f"/donations/orders/{out['order_id']}/capture").json()


# --- match preview ---------------------------------------------------------------------------------


def test_small_gift_to_the_less_backed_project_adds_more(client, db_session_factory):
    round_id = _round(db_session_factory, backers=(4, 2))
    r = client.get(f"/rounds/{round_id}/match-preview", params={"amount_cents": 100})
    assert r.status_code == 200
    items = {i["project_id"]: i for i in r.json()["items"]}
    assert set(items) == {1, 2}
    assert all(i["match_after_cents"] - i["match_before_cents"] == i["match_added_cents"] for i in items.values())
    # One more backer for the project with 2 backers moves the match more than one more for the one with 4.
    assert items[2]["match_added_cents"] > items[1]["match_added_cents"] > 0
    assert r.json()["items"][0]["project_id"] == 2  # biggest effect first

    one = client.get(f"/rounds/{round_id}/match-preview", params={"amount_cents": 100, "project_id": 2}).json()
    assert [i["project_id"] for i in one["items"]] == [2] and one["items"][0] == items[2]


def test_preview_counts_the_donors_earlier_gifts(client, db_session_factory):
    round_id = _round(db_session_factory, backers=(4, 1))
    with db_session_factory() as db:
        backer = db.scalar(select(Donation.donor_id).where(Donation.project_id == 2))
    new = client.get(f"/rounds/{round_id}/match-preview", params={"amount_cents": 100, "project_id": 2}).json()
    again = client.get(f"/rounds/{round_id}/match-preview",
                       params={"amount_cents": 100, "project_id": 2, "donor_id": backer}).json()
    # A second gift from the same person adds less than a new person's first gift.
    assert again["items"][0]["match_added_cents"] < new["items"][0]["match_added_cents"]


def test_preview_errors(client, db_session_factory):
    round_id = _round(db_session_factory)
    assert client.get(f"/rounds/{round_id}/match-preview", params={"amount_cents": 1}).status_code == 422
    assert client.get(f"/rounds/{round_id}/match-preview", params={"amount_cents": 100, "project_id": 3}).status_code == 404
    assert client.get("/rounds/99/match-preview", params={"amount_cents": 100}).status_code == 404


# --- round controls and results ---------------------------------------------------------------------


def test_admin_schedules_a_round_that_opens_on_its_own(client):
    body = {"name": "December", "starts_at": (NOW + timedelta(hours=1)).isoformat(),
            "ends_at": (NOW + timedelta(days=7)).isoformat(), "matching_pool_cents": 50_000, "project_cap_pct": 40}
    assert client.post("/admin/rounds", json=body).status_code == 401
    r = client.post("/admin/rounds", json=body, headers=ADMIN)
    assert r.status_code == 201 and r.json()["status"] == "scheduled"
    round_id = r.json()["id"]
    assert client.get("/rounds/current").status_code == 404  # not started yet

    overlap = {**body, "name": "Clash"}
    assert client.post("/admin/rounds", json=overlap, headers=ADMIN).json()["detail"]["error"] == "ROUND_OVERLAP"
    backwards = {**body, "ends_at": body["starts_at"], "starts_at": body["ends_at"]}
    assert client.post("/admin/rounds", json=backwards, headers=ADMIN).status_code == 422

    # Moving the start to now opens it at the next read.
    r = client.patch(f"/admin/rounds/{round_id}", json={"starts_at": (NOW - timedelta(minutes=1)).isoformat()},
                     headers=ADMIN)
    assert r.status_code == 200
    assert client.get("/rounds/current").json()["id"] == round_id
    assert client.patch(f"/admin/rounds/{round_id}", json={"starts_at": NOW.isoformat()},
                        headers=ADMIN).json()["detail"]["error"] == "ROUND_STARTED"
    r = client.patch(f"/admin/rounds/{round_id}", json={"matching_pool_cents": 80_000}, headers=ADMIN)
    assert r.json()["matching_pool_cents"] == 80_000
    assert [x["id"] for x in client.get("/rounds").json()] == [round_id]


def test_results_show_projected_then_final(client, db_session_factory):
    round_id = _round(db_session_factory)
    before = client.get(f"/rounds/{round_id}/results").json()
    assert before["is_final"] is False and before["backers"] == 5 and before["raised_cents"] == 500
    assert all(r["final_match_cents"] is None and r["projected_match_cents"] > 0 for r in before["rows"])

    assert client.post(f"/admin/rounds/{round_id}/close", params={"early": True}, headers=ADMIN).status_code == 200
    after = client.get(f"/rounds/{round_id}/results").json()
    assert after["is_final"] is True and after["status"] == "closed"
    assert sum(r["final_match_cents"] for r in after["rows"]) == after["matched_cents"]
    assert after["matched_cents"] + after["unspent_cents"] == after["matching_pool_cents"]
    assert client.patch(f"/admin/rounds/{round_id}", json={"name": "x"}, headers=ADMIN).status_code == 409


# --- sponsors ------------------------------------------------------------------------------------------


def test_sponsor_adds_to_the_pool(client, db_session_factory):
    round_id = _round(db_session_factory, pool=10_000)
    assert client.post("/donations/orders", json={"target_type": "POOL", "amount_cents": 500, "project_id": 1}).status_code == 422
    assert client.post("/donations/orders", json={"target_type": "PROJECT", "project_id": 1, "amount_cents": 500,
                                                  "sponsor_name": "x"}).status_code == 422

    paid = _pay(client, target_type="POOL", amount_cents=250_000, sponsor_name="Nakuru Rotary Club")
    assert paid["status"] == "captured"
    assert client.get("/rounds/current").json()["matching_pool_cents"] == 260_000
    sponsors = client.get(f"/rounds/{round_id}/sponsors").json()
    assert sponsors["total_cents"] == 250_000 and sponsors["sponsors"][0]["name"] == "Nakuru Rotary Club"
    assert client.get(f"/rounds/{round_id}/results").json()["sponsored_cents"] == 250_000
    # Pool money isn't a gift to a project: no backers, nothing raised, no ladder entry.
    assert client.get(f"/rounds/{round_id}/results").json()["raised_cents"] == 500
    assert client.patch(f"/admin/rounds/{round_id}", json={"matching_pool_cents": 1000},
                        headers=ADMIN).json()["detail"]["error"] == "POOL_BELOW_SPONSORED"

    # A full refund while the round is open takes it out of the pool again.
    r = client.post(f"/admin/donations/{paid['id']}/refund", json={"reason": "Sponsor changed plans"}, headers=ADMIN)
    assert r.status_code == 200 and r.json()["donation_status"] == "refunded"
    assert client.get("/rounds/current").json()["matching_pool_cents"] == 10_000
    assert client.get(f"/rounds/{round_id}/sponsors").json()["sponsors"] == []


def test_pool_needs_an_open_round(client):
    r = client.post("/donations/orders", json={"target_type": "POOL", "amount_cents": 500})
    assert r.status_code == 422 and r.json()["detail"]["error"] == "NO_OPEN_ROUND"


# --- applications and evidence -------------------------------------------------------------------------

APPLICATION = {
    "title": "Mama Lishe Kitchen", "facilitator": "Kibera Women's Group", "summary": "A school kitchen.",
    "category_id": 2, "goal_cents": 30_000, "payout_email": "kitchen@example.com",
    "milestones": [{"title": "Stoves", "amount_cents": 10_000, "due_date": "2026-12-01"},
                   {"title": "First term of meals", "amount_cents": 20_000, "due_date": "2027-02-01"}],
}


def test_apply_upload_evidence_and_the_agent_sees_it(client):
    bad = {**APPLICATION, "goal_cents": 99_999}
    assert client.post("/projects", json=bad).json()["detail"]["error"] == "MILESTONES_DONT_ADD_UP"
    r = client.post("/projects", json=APPLICATION)
    assert r.status_code == 201 and r.json()["status"] == "pending_review"
    project_id, token = r.json()["project_id"], r.json()["owner_token"]
    first, second = r.json()["milestone_ids"]
    assert client.get(f"/projects/{project_id}").status_code == 404  # not public until verified
    assert client.get(f"/admin/projects/{project_id}/payout-account", headers=ADMIN).json()["paypal_email"] == "kitchen@example.com"

    doc = {"kind": "registration", "file_url": "https://files.example.com/reg.pdf"}
    assert client.post(f"/projects/{project_id}/documents", json=doc).status_code == 401
    assert client.post(f"/projects/{project_id}/documents", json=doc, headers={"X-Project-Token": "nope"}).status_code == 401
    owner = {"X-Project-Token": token}
    assert client.post(f"/projects/{project_id}/documents", json=doc, headers=owner).status_code == 201
    assert client.post(f"/projects/{project_id}/documents", json={**doc, "file_url": "http://x"}, headers=owner).status_code == 422

    receipt = {"kind": "receipt", "file_url": "https://files.example.com/stoves.jpg", "milestone_id": first}
    assert client.post(f"/projects/{project_id}/documents", json=receipt, headers=owner).status_code == 201
    assert client.post("/projects/1/documents", json=receipt, headers=owner).status_code == 401  # someone else's project

    queue = client.get("/internal/milestones/evidence", headers=INTERNAL).json()
    assert [(q["milestone"]["id"], q["milestone"]["status"], len(q["documents"])) for q in queue] == [(first, "evidence_submitted", 1)]
    assert len(client.get(f"/admin/projects/{project_id}/documents", headers=ADMIN).json()) == 2
    assert second not in [q["milestone"]["id"] for q in queue]


def test_admin_can_issue_an_owner_token(client, db_session_factory):
    token = client.post("/admin/projects/1/owner-token", headers=ADMIN).json()["owner_token"]
    doc = {"kind": "photo", "file_url": "https://files.example.com/library.jpg"}
    assert client.post("/projects/1/documents", json=doc, headers={"X-Project-Token": token}).status_code == 201


def test_evidence_only_for_open_tranches(client, db_session_factory):
    r = client.post("/projects", json=APPLICATION).json()
    with db_session_factory() as db:
        db.get(Milestone, r["milestone_ids"][0]).status = "released"
        db.commit()
    receipt = {"kind": "receipt", "file_url": "https://files.example.com/r.jpg", "milestone_id": r["milestone_ids"][0]}
    out = client.post(f"/projects/{r['project_id']}/documents", json=receipt, headers={"X-Project-Token": r["owner_token"]})
    assert out.status_code == 409 and out.json()["detail"]["error"] == "MILESTONE_NOT_OPEN"


# --- refunds -------------------------------------------------------------------------------------------


def test_admin_refund_is_booked_once(client, db_session_factory, fake_paypal):
    paid = _pay(client, target_type="PROJECT", project_id=1, amount_cents=2000)
    r = client.post(f"/admin/donations/{paid['id']}/refund", json={"amount_cents": 500, "reason": "Typo"}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json() | {} == {**r.json(), "paypal_status": "COMPLETED", "amount_cents": 500, "refunded_total_cents": 500,
                             "donation_status": "captured"}
    assert fake_paypal.refunds[0]["amount"] == {"value": "5.00", "currency_code": "USD"}

    # PayPal's webhook for the same refund doesn't book it again.
    refund = {"id": r.json()["refund_id"], "status": "COMPLETED", "amount": {"currency_code": "USD", "value": "5.00"},
              "links": [{"rel": "up", "href": f"https://api.sandbox.paypal.com/v2/payments/captures/{paid['paypal_capture_id']}"}]}
    client.post("/webhooks/paypal", headers={"paypal-transmission-id": "t", "paypal-transmission-time": "t",
                                             "paypal-transmission-sig": "s", "paypal-cert-url": "c", "paypal-auth-algo": "a"},
                json={"id": "WH-REF", "event_type": "PAYMENT.CAPTURE.REFUNDED", "resource": refund})
    with db_session_factory() as db:
        refunds = db.scalars(select(LedgerEntry.amount).where(LedgerEntry.type == LedgerType.refund)).all()
    assert refunds == [500]

    too_much = client.post(f"/admin/donations/{paid['id']}/refund", json={"amount_cents": 1600, "reason": "x"}, headers=ADMIN)
    assert too_much.json()["detail"]["error"] == "REFUND_TOO_LARGE"
    rest = client.post(f"/admin/donations/{paid['id']}/refund", json={"reason": "Donor asked"}, headers=ADMIN).json()
    assert rest["amount_cents"] == 1500 and rest["donation_status"] == "refunded"
    again = client.post(f"/admin/donations/{paid['id']}/refund", json={"reason": "x"}, headers=ADMIN)
    assert again.json()["detail"]["error"] == "NOT_REFUNDABLE"


def test_pending_refund_waits_for_the_webhook(client, fake_paypal):
    paid = _pay(client, target_type="PROJECT", project_id=1, amount_cents=2000)
    fake_paypal.refund_status = "PENDING"
    r = client.post(f"/admin/donations/{paid['id']}/refund", json={"reason": "x"}, headers=ADMIN).json()
    assert r["paypal_status"] == "PENDING" and r["refunded_total_cents"] == 0 and r["donation_status"] == "captured"
    assert "amount" not in fake_paypal.refunds[0]  # a full refund sends no amount
