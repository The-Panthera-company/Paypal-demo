"""Released milestone tranches go out through PayPal Payouts.

One batch per released tranche, with a deterministic sender_batch_id (milestone-<id>-<currency>).
PayPal refuses a reused sender_batch_id for 30 days, so sending twice can never pay twice.
Payouts are asynchronous: the batch starts PENDING and the payout webhooks (or a refresh)
report each item. A SUCCESS item writes a `payout` ledger entry once. Items that FAILED,
were RETURNED or BLOCKED can be retried in a new batch with a new id (…-retry1, …-retry2).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.config import get_settings
from app.models import (
    LedgerEntry,
    LedgerType,
    Milestone,
    Payout,
    PayoutAccount,
    PayoutStatus,
    Procurement,
    Project,
    Supplier,
)
from app.money import to_paypal
from app.paypal import PayPalClient, PayPalError

RETRYABLE = {"FAILED", "RETURNED", "BLOCKED"}
BATCH_STATUS = {
    "PENDING": PayoutStatus.processing,
    "PROCESSING": PayoutStatus.processing,
    "SUCCESS": PayoutStatus.success,
    "DENIED": PayoutStatus.denied,
    "CANCELED": PayoutStatus.denied,
}


def create_for_milestone(db: Session, milestone: Milestone) -> Payout:
    """The tranche (its amount plus any match added at round close) as a one-item batch. Not sent yet."""
    account = db.get(PayoutAccount, milestone.project_id)
    payout = Payout(
        sender_batch_id=f"milestone-{milestone.id}-{milestone.currency}",
        currency=milestone.currency,
        items=[
            {
                "project_id": milestone.project_id,
                "milestone_id": milestone.id,
                "amount_cents": milestone.amount + milestone.match_amount,
                "receiver": account.paypal_email if account else None,
                "status": "NEW",
                "sender_item_id": f"milestone-{milestone.id}",
            }
        ],
    )
    db.add(payout)
    db.flush()
    return payout


def send(db: Session, paypal: PayPalClient, payout: Payout) -> None:
    """Send a batch PayPal hasn't accepted yet. Missing payout accounts or a PayPal error leave it
    pending with the reason on each item; send again once fixed. Caller commits."""
    if payout.paypal_batch_id:
        return
    items = [dict(i) for i in payout.items]
    for item in items:
        if not item.get("receiver"):
            if item.get("procurement_id"):
                procurement = db.get(Procurement, int(item["procurement_id"]))
                supplier = db.get(Supplier, procurement.supplier_id) if procurement and procurement.supplier_id else None
                item["receiver"] = supplier.paypal_email if supplier else None
            else:
                account = db.get(PayoutAccount, item["project_id"])
                item["receiver"] = account.paypal_email if account else None
    if missing := [i for i in items if not i["receiver"]]:
        for item in missing:
            item["error"] = "NO_PAYOUT_ACCOUNT"
        payout.items = items
        return

    titles = {p.id: p.title for p in db.scalars(select(Project).where(Project.id.in_({i["project_id"] for i in items})))}
    try:
        batch = paypal.create_payout(
            sender_batch_id=payout.sender_batch_id,
            currency=payout.currency,
            items=[
                {
                    "sender_item_id": i["sender_item_id"],
                    "receiver": i["receiver"],
                    "amount": to_paypal(i["amount_cents"], payout.currency),
                    "note": f"Milestone tranche for {titles.get(i['project_id'], 'your project')}",
                }
                for i in items
            ],
        )
    except PayPalError as e:
        for item in items:
            item["error"] = e.issue
            item["status"] = "FAILED"
        payout.items = items
        audit.write(db, actor="system", action="payout_failed", inputs={"payout_id": payout.id},
                    rule_result=e.issue, reason=f"PayPal refused batch {payout.sender_batch_id}")
        return

    header = batch.get("batch_header", {})
    payout.paypal_batch_id = header.get("payout_batch_id")
    payout.status = BATCH_STATUS.get(header.get("batch_status"), PayoutStatus.processing)
    for item in items:
        item.update(status="PENDING", error=None)
    payout.items = items
    audit.write(db, actor="system", action="payout_sent", inputs={"payout_id": payout.id},
                rule_result=header.get("batch_status"), reason=f"Batch {payout.sender_batch_id}")


def _update_item(db: Session, payout: Payout, sender_item_id: str, status: str, payout_item_id: str | None) -> bool:
    items = [dict(i) for i in payout.items]
    item = next((i for i in items if i.get("sender_item_id") == sender_item_id), None)
    if item is None:
        return False
    item["status"] = status
    item["payout_item_id"] = payout_item_id or item.get("payout_item_id")
    payout.items = items
    if status == "SUCCESS" and payout_item_id:
        if item.get("procurement_id"):
            # The purchase's expense is booked once, either at batch acceptance or here.
            from app import procurement as procurement_service

            procurement = db.get(Procurement, int(item["procurement_id"]))
            if procurement is not None:
                procurement_service.mark_paid(
                    db, procurement, batch_id=payout.paypal_batch_id, settings=get_settings()
                )
        else:
            booked = db.scalar(select(LedgerEntry.id).where(LedgerEntry.payout_item_id == payout_item_id))
            if booked is None:
                db.add(
                    LedgerEntry(
                        type=LedgerType.payout,
                        amount=item["amount_cents"],
                        currency=payout.currency,
                        project_id=item["project_id"],
                        payout_item_id=payout_item_id,
                    )
                )
    return True


def apply_batch(db: Session, payout: Payout, batch: dict) -> None:
    """A Payouts batch as PayPal returns it (GET /v1/payments/payouts/{id}, or a batch webhook)."""
    status = batch.get("batch_header", {}).get("batch_status")
    if status in BATCH_STATUS:
        payout.status = BATCH_STATUS[status]
    for item in batch.get("items", []):
        _update_item(
            db,
            payout,
            item.get("payout_item", {}).get("sender_item_id"),
            item.get("transaction_status"),
            item.get("payout_item_id"),
        )


def apply_item(db: Session, item: dict) -> bool:
    """A PAYMENT.PAYOUTS-ITEM.* webhook resource. False when it isn't one of our batches."""
    payout = db.scalar(select(Payout).where(Payout.paypal_batch_id == item.get("payout_batch_id")))
    if payout is None:
        return False
    return _update_item(
        db,
        payout,
        item.get("payout_item", {}).get("sender_item_id"),
        item.get("transaction_status"),
        item.get("payout_item_id"),
    )


def retry(db: Session, payout: Payout) -> Payout | None:
    """Failed, returned or blocked items in a new batch with a new id. None when nothing needs retrying."""
    failed = [dict(i) for i in payout.items if i.get("status") in RETRYABLE]
    if not failed:
        return None
    base = payout.sender_batch_id.split("-retry")[0]
    attempt = len(db.scalars(select(Payout.id).where(Payout.sender_batch_id.like(f"{base}-retry%"))).all()) + 1
    new = Payout(
        sender_batch_id=f"{base}-retry{attempt}",
        currency=payout.currency,
        items=[
            # receiver None: send() takes the project's current account, in case it was the problem.
            {**i, "status": "NEW", "error": None, "payout_item_id": None, "receiver": None,
             "sender_item_id": f"{i['sender_item_id'].split('-retry')[0]}-retry{attempt}"}
            for i in failed
        ],
    )
    payout.items = [{**i, "status": "RETRIED"} if i.get("status") in RETRYABLE else i for i in payout.items]
    db.add(new)
    db.flush()
    return new
