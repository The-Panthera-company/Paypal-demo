"""PayPal webhooks. PayPal calls this; it is authenticated by signature verification, not a token.

Deliveries are at least once and in any order, so each event is recorded by id and every
handler checks the donation's current state before changing it. Unknown or unwanted event
types are recorded as ignored and answered 200, so PayPal stops resending them. A PayPal API
failure while handling answers 502 without recording, so PayPal retries later.
"""

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import AuditLog, Donation, DonationStatus, LedgerEntry, LedgerType, WebhookEvent
from app.money import from_paypal
from app.paypal import PayPalClient, PayPalError, get_paypal
from app.routers.donations import apply_capture
from app.schemas import ErrorOut, WebhookAck

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

SETTLE = {"PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.PENDING"}
REFUND = {"PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.REVERSED"}


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"error": code, "message": message})


@router.post(
    "/paypal",
    response_model=WebhookAck,
    responses={400: {"model": ErrorOut}, 502: {"model": ErrorOut}, 503: {"model": ErrorOut}},
)
def paypal_webhook(
    request: Request,
    event: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
    settings: Settings = Depends(get_settings),
):
    """Verifies the signature, skips repeats by event id, then handles PAYMENT.CAPTURE.COMPLETED,
    .PENDING, .DENIED, .REFUNDED and .REVERSED. Other types are recorded as ignored."""
    if not settings.paypal_webhook_id:
        raise _error(503, "WEBHOOK_NOT_CONFIGURED", "PAYPAL_WEBHOOK_ID is not set")
    event_id = event.get("id")
    if not event_id or "paypal-transmission-sig" not in request.headers:
        raise _error(400, "INVALID_WEBHOOK", "Not a PayPal webhook delivery")
    try:
        verified = paypal.verify_webhook_signature(
            headers=dict(request.headers), event=event, webhook_id=settings.paypal_webhook_id
        )
    except PayPalError as e:
        raise _error(502, e.issue, "PayPal could not verify the signature")
    if not verified:
        raise _error(400, "INVALID_SIGNATURE", "Webhook signature did not verify")

    if db.get(WebhookEvent, event_id):
        return WebhookAck(event_id=event_id, status="duplicate")

    event_type = event.get("event_type", "")
    resource = event.get("resource") or {}
    try:
        if event_type in SETTLE:
            result = _settle(db, paypal, resource)
        elif event_type == "PAYMENT.CAPTURE.DENIED":
            result = _deny(db, resource)
        elif event_type in REFUND:
            result = _refund(db, resource, reversed_=event_type.endswith("REVERSED"))
        else:
            result = "ignored"
    except PayPalError as e:
        db.rollback()
        raise _error(502, e.issue, "PayPal call failed while handling the event; PayPal will retry")

    db.add(
        WebhookEvent(
            id=event_id, event_type=event_type, resource_id=resource.get("id"), result=result, payload=event
        )
    )
    try:
        db.commit()
    except IntegrityError:  # the same event arrived twice at once and the other won
        db.rollback()
        return WebhookAck(event_id=event_id, status="duplicate")
    return WebhookAck(event_id=event_id, status=result)


def _donation_for_capture(db: Session, capture: dict) -> Donation | None:
    donation = db.scalar(select(Donation).where(Donation.paypal_capture_id == capture.get("id")))
    if donation is None:
        # Our capture call may have failed after PayPal captured, so the capture id is not stored yet.
        custom_id = capture.get("custom_id") or ""
        if custom_id.startswith("donation:") and custom_id.removeprefix("donation:").isdigit():
            donation = db.get(Donation, int(custom_id.removeprefix("donation:")))
    return donation


def _settle(db: Session, paypal: PayPalClient, capture: dict) -> str:
    """Capture completed or pending: re-read the order from PayPal and record it like the capture route."""
    donation = _donation_for_capture(db, capture)
    if donation is None:
        return "unmatched"
    if donation.status in (DonationStatus.captured, DonationStatus.refunded):
        return "processed"
    order_id = capture.get("supplementary_data", {}).get("related_ids", {}).get("order_id") or donation.paypal_order_id
    order = paypal.get_order(order_id)
    try:
        apply_capture(db, donation, order)
    except HTTPException:  # custom_id or amount disagree with what we stored
        return "mismatch"
    return "processed"


def _deny(db: Session, capture: dict) -> str:
    donation = _donation_for_capture(db, capture)
    if donation is None:
        return "unmatched"
    if donation.status in (DonationStatus.created, DonationStatus.pending):
        donation.status = DonationStatus.failed
    return "processed"


def _refund(db: Session, refund: dict, *, reversed_: bool) -> str:
    """A refund or a reversal (chargeback). The resource is the refund; its "up" link is the capture."""
    capture_id = next(
        (link["href"].rstrip("/").split("/")[-1] for link in refund.get("links", []) if link.get("rel") == "up"),
        refund.get("id"),
    )
    donation = db.scalar(select(Donation).where(Donation.paypal_capture_id == capture_id))
    if donation is None:
        return "unmatched"
    money = refund.get("amount") or {}
    currency = money.get("currency_code", donation.currency)
    amount = abs(from_paypal(money["value"], currency)) if money.get("value") else donation.amount
    if currency != donation.currency:
        return "mismatch"

    db.add(
        LedgerEntry(
            type=LedgerType.refund,
            amount=amount,
            currency=currency,
            project_id=donation.project_id,
            donation_id=donation.id,
        )
    )
    db.flush()
    refunded = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.donation_id == donation.id, LedgerEntry.type == LedgerType.refund
        )
    )
    # Fully refunded gifts leave project totals and matching; a partial refund stays counted.
    if refunded >= donation.amount:
        donation.status = DonationStatus.refunded
    if reversed_:
        db.add(
            AuditLog(
                actor="paypal",
                action="capture_reversed",
                inputs={"donation_id": donation.id, "capture_id": capture_id, "amount_cents": amount},
                rule_result="reversal",
                reason="Donor's bank or PayPal reversed the payment (chargeback or dispute)",
            )
        )
    return "processed"
