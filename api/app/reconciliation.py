"""Reconciliation: do our records add up, and is any money stuck?

`report` reads only our database: totals of money in and out, and checks that every captured
payment, refund, release and payout has its matching record. `sweep` settles PayPal orders our
capture route never finished (browser closed after approval, popup trouble, a timeout) by asking
PayPal for their current state.
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.mandates import funded_balance
from app.models import (
    CategoryAllocation,
    Donation,
    DonationStatus,
    LedgerEntry,
    LedgerType,
    Mandate,
    MatchResult,
    Milestone,
    MilestoneStatus,
    Payout,
    Round,
    RoundStatus,
    TargetType,
)
from app.paypal import PayPalClient, PayPalError

STALE_CREATED = timedelta(minutes=30)  # approved but not captured, or simply abandoned
ABANDONED = timedelta(hours=3)  # PayPal lets an unapproved order lapse; we stop waiting
STALE_PENDING = timedelta(days=3)


def _aware(at: datetime) -> datetime:
    return at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at


def _ledger(db: Session, type_: LedgerType) -> int:
    return db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(LedgerEntry.type == type_))


def report(db: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    issues: list[dict] = []

    def issue(check: str, severity: str, detail: str, refs: list) -> None:
        if refs:
            issues.append({"check": check, "severity": severity, "detail": detail, "refs": refs})

    # Orders, plus subscription charges (no order; the sale id is stored as the capture id).
    paid_via_paypal = select(Donation).where(
        Donation.paypal_order_id.is_not(None) | Donation.paypal_capture_id.is_not(None),
        Donation.status.in_((DonationStatus.captured, DonationStatus.refunded)),
    )
    paypal_paid = list(db.scalars(paid_via_paypal))
    booked = set(db.scalars(select(LedgerEntry.donation_id).where(LedgerEntry.type == LedgerType.donation)))
    issue("captured_without_ledger", "error", "Captured payments with no donation ledger entry",
          [d.id for d in paypal_paid if d.id not in booked])
    issue("captured_without_capture_id", "error", "Captured payments missing PayPal's capture id (refunds can't be matched)",
          [d.id for d in paypal_paid if not d.paypal_capture_id])

    settled = set(db.scalars(select(Donation.id).where(
        Donation.status.in_((DonationStatus.captured, DonationStatus.refunded)))))
    issue("ledger_without_donation", "error", "Donation ledger entries whose donation isn't captured or refunded",
          sorted({i for i in booked if i is not None and i not in settled}))

    refunded = db.execute(
        select(LedgerEntry.donation_id, func.sum(LedgerEntry.amount))
        .where(LedgerEntry.type == LedgerType.refund)
        .group_by(LedgerEntry.donation_id)
    ).all()
    amounts = dict(db.execute(select(Donation.id, Donation.amount).where(Donation.id.in_([r[0] for r in refunded]))).all())
    issue("refunded_more_than_paid", "error", "Refunds add up to more than the donation",
          [d for d, total in refunded if total > amounts.get(d, 0)])

    open_orders = list(db.scalars(select(Donation).where(
        Donation.paypal_order_id.is_not(None), Donation.status.in_((DonationStatus.created, DonationStatus.pending)))))
    issue("stuck_orders", "warning",
          "Orders older than 30 minutes not captured yet (approved but never captured, or abandoned): run the sweep",
          [d.id for d in open_orders if d.status == DonationStatus.created and now - _aware(d.created_at) > STALE_CREATED])
    issue("long_pending", "warning", "Payments PayPal has held for over 3 days",
          [d.id for d in open_orders if d.status == DonationStatus.pending and now - _aware(d.created_at) > STALE_PENDING])

    categories = list(db.scalars(select(Donation).where(
        Donation.target_type == TargetType.CATEGORY, Donation.status == DonationStatus.captured)))
    allocated = dict(db.execute(
        select(CategoryAllocation.donation_id, func.sum(CategoryAllocation.amount)).group_by(CategoryAllocation.donation_id)
    ).all())
    unallocated = [d for d in categories if allocated.get(d.id, 0) != d.amount]
    issue("category_not_allocated", "error", "Category donations not fully split onto projects (no eligible project at capture)",
          [d.id for d in unallocated])

    mandates = list(db.scalars(select(Mandate)))
    balances = {m.donor_id: funded_balance(db, m.donor_id) for m in mandates}
    issue("negative_agent_balance", "error", "Giving Agent balances below zero", [d for d, b in balances.items() if b < 0])

    released = list(db.scalars(select(Milestone).where(Milestone.status == MilestoneStatus.released)))
    with_payout = {i.get("milestone_id") for p in db.scalars(select(Payout)) for i in p.items or []}
    issue("released_without_payout", "error", "Released tranches with no payout batch",
          [m.id for m in released if m.amount + m.match_amount > 0 and m.id not in with_payout])
    payouts = list(db.scalars(select(Payout)))
    issue("payout_not_sent", "warning", "Payout batches waiting to be sent (see each item's error)",
          [p.id for p in payouts if not p.paypal_batch_id])
    paid_items = set(db.scalars(select(LedgerEntry.payout_item_id).where(LedgerEntry.type == LedgerType.payout)))
    issue("payout_success_not_booked", "error", "Payout batches with a successful item that has no payout ledger entry",
          [p.id for p in payouts if any(i.get("status") == "SUCCESS" and i.get("payout_item_id") not in paid_items
                                         for i in p.items or [])])
    issue("payout_unclaimed", "warning", "Payouts sent to an email with no PayPal account yet (returned after 30 days)",
          [p.id for p in payouts if any(i.get("status") == "UNCLAIMED" for i in p.items or [])])
    issue("payout_failed", "warning", "Payout items that failed, were returned or blocked: retry them",
          [p.id for p in payouts if any(i.get("status") in ("FAILED", "RETURNED", "BLOCKED") for i in p.items or [])])

    over_pool = []
    for r in db.scalars(select(Round).where(Round.status == RoundStatus.closed)):
        total = db.scalar(select(func.coalesce(func.sum(MatchResult.final_amount), 0)).where(
            MatchResult.round_id == r.id, MatchResult.is_final.is_(True)))
        if total > r.matching_pool:
            over_pool.append(r.id)
    issue("match_over_pool", "error", "Closed rounds that matched more than their pool", over_pool)

    received = sum(d.amount for d in paypal_paid)
    refunds, fees, payouts_paid = _ledger(db, LedgerType.refund), _ledger(db, LedgerType.fee), _ledger(db, LedgerType.payout)
    balance = received - refunds - fees - payouts_paid
    if balance < 0:
        issue("negative_platform_balance", "error", "Paid out more than was received", [balance])

    tranches = _ledger(db, LedgerType.tranche)
    totals = {
        "received_via_paypal_cents": received,
        "refunded_cents": refunds,
        "paypal_fees_cents": fees,
        "paid_out_cents": payouts_paid,
        "platform_balance_cents": balance,
        "agent_budget_unspent_cents": sum(b for b in balances.values() if b > 0),
        "tranches_released_cents": tranches,
        "released_not_yet_paid_cents": tranches - payouts_paid,
        "match_booked_cents": _ledger(db, LedgerType.match),
        "category_unallocated_cents": sum(d.amount - allocated.get(d.id, 0) for d in unallocated),
    }
    return {
        "generated_at": now,
        "ok": not any(i["severity"] == "error" for i in issues),
        "totals": totals,
        "issues": issues,
    }


def sweep(db: Session, paypal: PayPalClient, now: datetime | None = None) -> dict:
    """Ask PayPal about every order still `created` after 30 minutes or `pending`, and settle it:
    approved → capture it now (the donor said yes); completed → record it; voided → failed;
    never approved after 3 hours → failed (abandoned). Commits after each order."""
    from app.routers.donations import apply_capture  # avoids an import cycle with the router

    now = now or datetime.now(timezone.utc)
    out = {"checked": 0, "captured": [], "failed": [], "unchanged": [], "errors": []}
    candidates = db.scalars(select(Donation).where(
        Donation.paypal_order_id.is_not(None), Donation.status.in_((DonationStatus.created, DonationStatus.pending))))
    for d in list(candidates):
        age = now - _aware(d.created_at)
        if d.status == DonationStatus.created and age <= STALE_CREATED:
            continue
        out["checked"] += 1
        before = d.status
        try:
            order = paypal.get_order(d.paypal_order_id)
            if order.get("status") == "APPROVED":
                try:
                    order = paypal.capture_order(d.paypal_order_id, request_id=f"capture-{d.paypal_order_id}")
                except PayPalError as e:
                    if e.issue == "ORDER_ALREADY_CAPTURED":
                        order = paypal.get_order(d.paypal_order_id)
                    elif e.issue == "INSTRUMENT_DECLINED":
                        d.status = DonationStatus.failed
                        order = None
                    else:
                        raise
            if order is None:
                pass
            elif order.get("status") == "COMPLETED":
                apply_capture(db, d, order)
            elif order.get("status") == "VOIDED" or (d.status == DonationStatus.created and age > ABANDONED):
                d.status = DonationStatus.failed
            db.commit()
        except (PayPalError, HTTPException) as e:
            db.rollback()
            reason = e.issue if isinstance(e, PayPalError) else e.detail.get("error")
            out["errors"].append(f"donation {d.id}: {reason}")
            continue
        if d.status == DonationStatus.captured and before != d.status:
            out["captured"].append(d.id)
        elif d.status == DonationStatus.failed:
            out["failed"].append(d.id)
        else:
            out["unchanged"].append(d.id)
    return out
