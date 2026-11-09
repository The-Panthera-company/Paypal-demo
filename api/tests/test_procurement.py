"""Managed procurement: owner requests, eligible suppliers, proposals, payments and receipts."""

from sqlalchemy import func, select

from app.models import (
    DocumentKind,
    LedgerEntry,
    LedgerType,
    Milestone,
    MilestoneStatus,
    Payout,
    Procurement,
    ProcurementStatus,
    ProjectDocument,
    Supplier,
)

ADMIN = {"Authorization": "Bearer admin-test-token"}
INTERNAL = {"Authorization": "Bearer internal-test-token"}
SIGNED = {
    "paypal-auth-algo": "SHA256withRSA",
    "paypal-cert-url": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT",
    "paypal-transmission-id": "tx-procurement",
    "paypal-transmission-sig": "sig",
    "paypal-transmission-time": "2026-11-09T10:00:00Z",
}


def _owner(client):
    r = client.post("/admin/projects/1/owner-token", headers=ADMIN)
    assert r.status_code == 200, r.text
    return {"X-Project-Token": r.json()["owner_token"]}


def _milestone(factory, *, amount=3000, match=0, status=MilestoneStatus.open):
    with factory() as db:
        milestone = Milestone(
            project_id=1,
            seq=99,
            title="Buy books",
            amount=amount,
            match_amount=match,
            currency="USD",
            status=status,
        )
        db.add(milestone)
        db.commit()
        return milestone.id


def _supplier(factory, *, name="Nakuru Books", categories=None, tags=None, region="Nakuru", active=True):
    with factory() as db:
        supplier = Supplier(
            name=name,
            paypal_email=f"{name.casefold().replace(' ', '-')}@supplier.co.ke",
            categories=categories or ["Education"],
            tags=tags or ["books"],
            region=region,
            active=active,
        )
        db.add(supplier)
        db.commit()
        return supplier.id


def _request(client, headers, milestone_id, *, amount=3000):
    r = client.post(
        "/projects/1/procurement-requests",
        headers=headers,
        json={
            "milestone_id": milestone_id,
            "description": "40 reading sets",
            "quantity": 40,
            "max_amount_cents": amount,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _propose(client, procurement_id, supplier_id, *, amount=3000):
    return client.post(
        f"/internal/procurement/{procurement_id}/propose",
        headers=INTERNAL,
        json={
            "supplier_id": supplier_id,
            "amount_cents": amount,
            "line_items": [{"description": "Reading sets", "quantity": 40, "unit_amount_cents": 75}],
            "rationale": "Lowest quote, delivery included",
        },
    )


def test_owner_request_validates_milestone_and_duplicate(client, db_session_factory):
    headers = _owner(client)
    milestone_id = _milestone(db_session_factory, amount=5000)

    first = _request(client, headers, milestone_id, amount=3000)
    assert first["status"] == "requested"
    assert first["project_id"] == 1 and first["milestone_id"] == milestone_id

    duplicate = client.post(
        "/projects/1/procurement-requests",
        headers=headers,
        json={"milestone_id": milestone_id, "description": "Another", "quantity": 1, "max_amount_cents": 1000},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["error"] == "PROCUREMENT_EXISTS"

    too_big = client.post(
        "/projects/1/procurement-requests",
        headers=headers,
        json={"milestone_id": milestone_id, "description": "Too much", "quantity": 1, "max_amount_cents": 5001},
    )
    assert too_big.status_code == 422
    assert too_big.json()["detail"]["error"] == "AMOUNT_ABOVE_MILESTONE"

    wrong_project_milestone = _milestone(db_session_factory)
    with db_session_factory() as db:
        db.get(Milestone, wrong_project_milestone).project_id = 2
        db.commit()
    foreign = client.post(
        "/projects/1/procurement-requests",
        headers=headers,
        json={"milestone_id": wrong_project_milestone, "description": "Foreign", "quantity": 1, "max_amount_cents": 1000},
    )
    assert foreign.status_code == 404

    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Procurement)) == 1


def test_supplier_list_matches_and_hides_paypal_email(client, db_session_factory):
    eligible = _supplier(db_session_factory, name="Nakuru Books", tags=["literacy"])
    _supplier(db_session_factory, name="Mombasa Health", categories=["Health"], tags=["water"], region="Mombasa")
    _supplier(db_session_factory, name="Inactive Books", active=False)

    r = client.get("/internal/procurement/suppliers", params={"project_id": 1}, headers=INTERNAL)
    assert r.status_code == 200, r.text
    assert [s["id"] for s in r.json()] == [eligible]
    assert set(r.json()[0]) == {"id", "name", "categories", "tags", "region"}
    assert "paypal_email" not in r.json()[0]


def test_propose_rejects_ineligible_supplier_and_enforces_one_proposal(client, db_session_factory):
    headers = _owner(client)
    procurement = _request(client, headers, _milestone(db_session_factory, amount=5000))
    good = _supplier(db_session_factory, name="Good Books")
    wrong = _supplier(db_session_factory, name="Wrong Health", categories=["Health"], tags=["water"], region="Mombasa")

    assert _propose(client, procurement["id"], wrong).status_code == 422
    assert _propose(client, procurement["id"], 999_999).status_code == 422
    assert _propose(client, procurement["id"], good, amount=5001).status_code == 422

    proposed = _propose(client, procurement["id"], good)
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["status"] == "proposed"
    assert proposed.json()["supplier_id"] == good
    assert proposed.json()["amount_cents"] == 3000

    second = _propose(client, procurement["id"], good)
    assert second.status_code == 409
    assert second.json()["detail"]["error"] == "ALREADY_PROPOSED"

    requests = client.get("/internal/procurement/requests", headers=INTERNAL)
    assert requests.status_code == 200
    assert requests.json()[0]["project_title"] == "Lanet Library"
    assert requests.json()[0]["milestone_title"] == "Buy books"
    assert requests.json()[0]["goal_cents"] == 120000
    assert requests.json()[0]["tags"] == ["books", "literacy"]
    assert requests.json()[0]["region"] == "Nakuru"
    assert requests.json()[0]["project"]["id"] == 1


def test_pay_auto_approved_is_idempotent_and_books_receipt_and_expense(client, db_session_factory, fake_paypal):
    headers = _owner(client)
    procurement = _request(client, headers, _milestone(db_session_factory))
    supplier_id = _supplier(db_session_factory)
    assert _propose(client, procurement["id"], supplier_id).status_code == 200

    paid = client.post(f"/internal/procurement/{procurement['id']}/pay", headers=INTERNAL)
    assert paid.status_code == 200, paid.text
    body = paid.json()
    assert body["status"] == "paid"
    assert body["payout_id"] is not None
    assert body["receipt_document_id"] is not None
    assert len(fake_paypal.payouts) == 1
    assert next(iter(fake_paypal.payouts.values()))["sender_batch_header"]["sender_batch_id"] == f"procurement-{procurement['id']}-USD"

    first_payout_id = body["payout_id"]
    again = client.post(f"/internal/procurement/{procurement['id']}/pay", headers=INTERNAL)
    assert again.status_code == 200
    assert again.json()["payout_id"] == first_payout_id
    assert len(fake_paypal.payouts) == 1

    with db_session_factory() as db:
        row = db.get(Procurement, procurement["id"])
        assert row.status == ProcurementStatus.paid
        assert row.payout_id == first_payout_id
        assert row.receipt_document_id == body["receipt_document_id"]
        assert db.get(Milestone, row.milestone_id).status == MilestoneStatus.released
        expenses = db.scalars(select(LedgerEntry).where(LedgerEntry.type == LedgerType.expense)).all()
        assert len(expenses) == 1
        assert expenses[0].procurement_id == row.id
        assert expenses[0].amount == 3000
        receipt = db.get(ProjectDocument, row.receipt_document_id)
        assert receipt.kind == DocumentKind.receipt
        assert receipt.milestone_id == row.milestone_id
        assert receipt.extracted_fields["batch_id"].startswith("BATCH")
        assert receipt.extracted_fields["amount_cents"] == 3000
        payout = db.get(Payout, first_payout_id)
        assert payout.items[0]["procurement_id"] == row.id
        assert payout.items[0]["receiver"].endswith("@supplier.co.ke")


def test_pay_above_limit_waits_for_admin(client, db_session_factory, fake_paypal):
    headers = _owner(client)
    procurement = _request(client, headers, _milestone(db_session_factory, amount=30_000), amount=30_000)
    supplier_id = _supplier(db_session_factory)
    assert _propose(client, procurement["id"], supplier_id, amount=30_000).status_code == 200

    blocked = client.post(f"/internal/procurement/{procurement['id']}/pay", headers=INTERNAL)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["error"] == "APPROVAL_REQUIRED"
    assert fake_paypal.payouts == {}

    approved = client.post(
        f"/admin/procurement/{procurement['id']}/approve", headers=ADMIN, json={"approve": True, "note": "Quotes checked"}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["admin_approved"] is True

    paid = client.post(f"/internal/procurement/{procurement['id']}/pay", headers=INTERNAL)
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid"
    assert len(fake_paypal.payouts) == 1


def test_pay_failure_is_failed_and_retryable_without_duplicate_batch(client, db_session_factory, fake_paypal):
    headers = _owner(client)
    procurement = _request(client, headers, _milestone(db_session_factory))
    supplier_id = _supplier(db_session_factory)
    assert _propose(client, procurement["id"], supplier_id).status_code == 200

    fake_paypal.payout_error = (422, {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "INSUFFICIENT_FUNDS"}]})
    failed = client.post(f"/internal/procurement/{procurement['id']}/pay", headers=INTERNAL)
    assert failed.status_code == 200, failed.text
    assert failed.json()["status"] == "failed"
    assert failed.json()["error"] == "INSUFFICIENT_FUNDS"
    assert fake_paypal.payouts == {}

    with db_session_factory() as db:
        row = db.get(Procurement, procurement["id"])
        payout = db.get(Payout, row.payout_id)
        assert payout.items[0]["error"] == "INSUFFICIENT_FUNDS"
        payout_count = db.scalar(select(func.count()).select_from(Payout))

    fake_paypal.payout_error = None
    retried = client.post(f"/internal/procurement/{procurement['id']}/pay", headers=INTERNAL)
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "paid"
    assert len(fake_paypal.payouts) == 1
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Payout)) == payout_count


def test_payout_webhook_books_expense_once(client, db_session_factory, fake_paypal):
    headers = _owner(client)
    procurement = _request(client, headers, _milestone(db_session_factory))
    supplier_id = _supplier(db_session_factory)
    _propose(client, procurement["id"], supplier_id)
    paid = client.post(f"/internal/procurement/{procurement['id']}/pay", headers=INTERNAL).json()
    batch_id = next(iter(fake_paypal.payouts))
    sender_item_id = fake_paypal.payouts[batch_id]["items"][0]["sender_item_id"]

    resource = {
        "payout_batch_id": batch_id,
        "payout_item_id": f"ITEM-{batch_id}-1",
        "transaction_status": "SUCCESS",
        "payout_item": {
            "sender_item_id": sender_item_id,
            "receiver": fake_paypal.payouts[batch_id]["items"][0]["receiver"],
            "amount": fake_paypal.payouts[batch_id]["items"][0]["amount"],
        },
    }
    webhook = client.post(
        "/webhooks/paypal",
        headers=SIGNED,
        json={"id": "WH-PROC-1", "event_type": "PAYMENT.PAYOUTS-ITEM.SUCCEEDED", "resource": resource},
    )
    assert webhook.status_code == 200, webhook.text
    assert webhook.json()["status"] == "processed"

    with db_session_factory() as db:
        expenses = db.scalars(
            select(LedgerEntry).where(
                LedgerEntry.type == LedgerType.expense, LedgerEntry.procurement_id == procurement["id"]
            )
        ).all()
        assert len(expenses) == 1
        assert db.get(Procurement, procurement["id"]).receipt_document_id == paid["receipt_document_id"]


def test_tranche_routes_reject_procurement_managed_milestone(client, db_session_factory):
    headers = _owner(client)
    milestone_id = _milestone(db_session_factory)
    procurement = _request(client, headers, milestone_id)

    tranche = client.post(
        "/internal/payout-requests",
        headers=INTERNAL,
        json={
            "milestone_id": milestone_id,
            "checks": {
                "receipt_total_within_10pct": True,
                "supplier_matches_plan": True,
                "photo_not_duplicate": True,
                "dated_in_window": True,
            },
            "summary": "All checks passed",
        },
    )
    assert tranche.status_code == 409
    assert tranche.json()["detail"]["error"] == "PROCUREMENT_MANAGED"

    with db_session_factory() as db:
        db.get(Milestone, milestone_id).status = MilestoneStatus.held
        db.commit()
    review = client.post(
        f"/admin/milestones/{milestone_id}/review",
        headers=ADMIN,
        json={"approve": True, "note": "Approve"},
    )
    assert review.status_code == 409
    assert review.json()["detail"]["error"] == "PROCUREMENT_MANAGED"
    with db_session_factory() as db:
        assert db.get(Procurement, procurement["id"]).status == ProcurementStatus.requested


def test_public_list_admin_retry_and_display_fields(client, db_session_factory, fake_paypal):
    headers = _owner(client)
    big = _request(client, headers, _milestone(db_session_factory, amount=30_000), amount=30_000)
    supplier_id = _supplier(db_session_factory)
    assert _propose(client, big["id"], supplier_id, amount=30_000).status_code == 200

    listed = client.get("/projects/1/procurements")
    assert listed.status_code == 200
    row = listed.json()[0]
    assert row["needs_approval"] is True
    assert row["paypal_batch_id"] is None
    assert "paypal_email" not in listed.text and "@supplier.co.ke" not in listed.text
    assert client.get("/projects/9999/procurements").status_code == 404

    assert client.post(f"/admin/procurement/{big['id']}/retry", headers=ADMIN).json()["detail"]["error"] == "PROCUREMENT_NOT_FAILED"
    client.post(f"/admin/procurement/{big['id']}/approve", headers=ADMIN, json={"approve": True})
    fake_paypal.payout_error = (422, {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "INSUFFICIENT_FUNDS"}]})
    failed = client.post(f"/internal/procurement/{big['id']}/pay", headers=INTERNAL).json()
    assert failed["status"] == "failed" and failed["needs_approval"] is False

    fake_paypal.payout_error = None
    paid = client.post(f"/admin/procurement/{big['id']}/retry", headers=ADMIN)
    assert paid.status_code == 200, paid.text
    body = paid.json()
    assert body["status"] == "paid"
    assert body["paypal_batch_id"].startswith("BATCH")
    assert body["receipt_url"]
