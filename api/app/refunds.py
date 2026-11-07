"""Refunds and sponsor contributions to the matching pool: the bookkeeping both paths share.

A refund is booked once per PayPal refund id, whether the admin console asked for it
(POST /admin/donations/{id}/refund) or PayPal's PAYMENT.CAPTURE.REFUNDED webhook reported it.
A POOL donation raises its round's matching_pool when captured, and lowers it again if it is
fully refunded before the round closes.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.models import Donation, DonationStatus, LedgerEntry, LedgerType, PoolContribution, Round, RoundStatus


def refunded_total(db: Session, donation_id: int) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.donation_id == donation_id, LedgerEntry.type == LedgerType.refund
        )
    )


def book_refund(db: Session, donation: Donation, amount: int, refund_id: str | None, *, reversed_: bool = False) -> bool:
    """Book a refund (or a reversal) against the donation. False if this refund id is booked already."""
    if refund_id and db.scalar(select(LedgerEntry.id).where(LedgerEntry.paypal_refund_id == refund_id)):
        return False
    db.add(LedgerEntry(type=LedgerType.refund, amount=amount, currency=donation.currency,
                       project_id=donation.project_id, donation_id=donation.id, paypal_refund_id=refund_id))
    db.flush()
    # Fully refunded gifts leave project totals and matching; a partial refund stays counted.
    if refunded_total(db, donation.id) >= donation.amount:
        donation.status = DonationStatus.refunded
        remove_from_pool(db, donation)
    if reversed_:
        audit.write(db, actor="paypal", action="capture_reversed",
                    inputs={"donation_id": donation.id, "refund_id": refund_id, "amount_cents": amount},
                    rule_result="reversal", reason="Donor's bank or PayPal reversed the payment (chargeback or dispute)")
    return True


def add_to_pool(db: Session, donation: Donation) -> None:
    """A captured POOL donation joins its round's matching pool, unless the round has closed."""
    contribution = db.get(PoolContribution, donation.id)
    if contribution is None or contribution.added_to_pool:
        return
    round_ = db.get(Round, contribution.round_id)
    if round_ is None or round_.status == RoundStatus.closed:
        audit.write(db, actor="system", action="pool_contribution_late", inputs={"donation_id": donation.id},
                    rule_result="not_added", reason="The round closed before the payment completed; refund or reassign it")
        return
    round_.matching_pool += donation.amount
    contribution.added_to_pool = True
    audit.write(db, actor="system", action="pool_contribution", inputs={"donation_id": donation.id, "round_id": round_.id},
                rule_result="added", reason=f"{donation.amount} cents added to {round_.name}'s matching pool")


def remove_from_pool(db: Session, donation: Donation) -> None:
    contribution = db.get(PoolContribution, donation.id)
    if contribution is None or not contribution.added_to_pool:
        return
    round_ = db.get(Round, contribution.round_id)
    if round_ is not None and round_.status != RoundStatus.closed:
        round_.matching_pool = max(round_.matching_pool - donation.amount, 0)
        contribution.added_to_pool = False
