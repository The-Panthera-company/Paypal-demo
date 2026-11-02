"""Flow 1: a donor gives to a project or a category through the PayPal button.

The browser never decides the amount, currency or target that gets recorded:
create stores a pending donation first, and capture checks PayPal's answer against it.
"""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import Donation, DonationStatus, Donor, LedgerEntry, LedgerType, TargetType
from app.money import from_paypal, to_paypal
from app.paypal import PayPalClient, PayPalError, get_paypal

router = APIRouter(prefix="/donations", tags=["donations"])


class CreateOrderIn(BaseModel):
    target_type: Literal[TargetType.PROJECT, TargetType.CATEGORY]
    project_id: int | None = None
    category_id: int | None = None
    amount_cents: int

    @model_validator(mode="after")
    def one_target(self):
        if self.target_type == TargetType.PROJECT and (self.project_id is None or self.category_id is not None):
            raise ValueError("PROJECT donations need project_id only")
        if self.target_type == TargetType.CATEGORY and (self.category_id is None or self.project_id is not None):
            raise ValueError("CATEGORY donations need category_id only")
        return self


class CreateOrderOut(BaseModel):
    order_id: str
    donation_id: int


class DonationOut(BaseModel):
    id: int
    status: DonationStatus
    target_type: TargetType
    project_id: int | None
    category_id: int | None
    amount_cents: int
    currency: str
    paypal_order_id: str | None
    paypal_capture_id: str | None

    @classmethod
    def of(cls, d: Donation) -> "DonationOut":
        return cls(
            id=d.id,
            status=d.status,
            target_type=d.target_type,
            project_id=d.project_id,
            category_id=d.category_id,
            amount_cents=d.amount,
            currency=d.currency,
            paypal_order_id=d.paypal_order_id,
            paypal_capture_id=d.paypal_capture_id,
        )


def _error(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"error": code, "message": message, **extra})


def custom_id_for(donation: Donation) -> str:
    return f"donation:{donation.id}"


@router.post("/orders", response_model=CreateOrderOut)
def create_order(
    body: CreateOrderIn,
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
    settings: Settings = Depends(get_settings),
):
    if not settings.min_donation_cents <= body.amount_cents <= settings.max_donation_cents:
        raise _error(
            422,
            "AMOUNT_OUT_OF_RANGE",
            f"Amount must be between {settings.min_donation_cents} and {settings.max_donation_cents} cents",
        )
    # TODO: once the projects table lands, reject unverified or frozen targets here.

    donation = Donation(
        target_type=body.target_type,
        project_id=body.project_id,
        category_id=body.category_id,
        amount=body.amount_cents,
        currency=settings.currency,
    )
    db.add(donation)
    db.flush()  # assigns donation.id for custom_id

    target = f"project {body.project_id}" if body.project_id else f"category {body.category_id}"
    try:
        order = paypal.create_order(
            amount=to_paypal(donation.amount, donation.currency),
            currency=donation.currency,
            custom_id=custom_id_for(donation),
            description=f"Donation to {target}",
            request_id=f"create-{custom_id_for(donation)}",
        )
    except PayPalError as e:
        db.rollback()
        raise _error(502, e.issue, "PayPal could not create the order")

    donation.paypal_order_id = order["id"]
    db.commit()
    return CreateOrderOut(order_id=order["id"], donation_id=donation.id)


@router.post("/orders/{order_id}/capture", response_model=DonationOut)
def capture_order(order_id: str, db: Session = Depends(get_db), paypal: PayPalClient = Depends(get_paypal)):
    donation = db.scalar(select(Donation).where(Donation.paypal_order_id == order_id))
    if donation is None:
        raise _error(404, "ORDER_NOT_FOUND", "No donation for this order")
    # Already settled (double click, retry, or the webhook got there first).
    if donation.status in (DonationStatus.captured, DonationStatus.refunded):
        return DonationOut.of(donation)

    try:
        order = paypal.capture_order(order_id, request_id=f"capture-{order_id}")
    except PayPalError as e:
        if e.issue == "ORDER_ALREADY_CAPTURED":
            order = paypal.get_order(order_id)
        elif e.issue == "INSTRUMENT_DECLINED":
            # The frontend calls actions.restart() so the donor can pick another funding source.
            raise _error(422, "INSTRUMENT_DECLINED", "The payment method was declined", restart=True)
        else:
            raise _error(502, e.issue, "PayPal could not capture the order")

    apply_capture(db, donation, order)
    db.commit()
    return DonationOut.of(donation)


def apply_capture(db: Session, donation: Donation, order: dict) -> None:
    """Record PayPal's capture result on a donation. Safe to call more than once."""
    unit = order["purchase_units"][0]
    if unit.get("custom_id") != custom_id_for(donation):
        raise _error(409, "CUSTOM_ID_MISMATCH", "PayPal order does not belong to this donation")

    captures = unit.get("payments", {}).get("captures", [])
    if not captures:
        raise _error(502, "NO_CAPTURE", "PayPal returned no capture")
    capture = captures[0]

    currency = capture["amount"]["currency_code"]
    amount = from_paypal(capture["amount"]["value"], currency)
    if currency != donation.currency or amount != donation.amount:
        raise _error(409, "AMOUNT_MISMATCH", "Captured amount differs from the donation")

    donation.paypal_capture_id = capture["id"]
    donation.donor_id = _upsert_donor(db, order).id

    status = capture["status"]
    if status == "COMPLETED":
        _mark_captured(db, donation, capture)
    elif status == "PENDING":
        # Does not count for matching until PAYMENT.CAPTURE.COMPLETED arrives.
        donation.status = DonationStatus.pending
    else:  # DECLINED, FAILED
        donation.status = DonationStatus.failed


def _mark_captured(db: Session, donation: Donation, capture: dict) -> None:
    if donation.status == DonationStatus.captured:
        return
    donation.status = DonationStatus.captured
    donation.captured_at = datetime.now(timezone.utc)
    db.add(
        LedgerEntry(
            type=LedgerType.donation,
            amount=donation.amount,
            currency=donation.currency,
            project_id=donation.project_id,
            donation_id=donation.id,
        )
    )
    fee = capture.get("seller_receivable_breakdown", {}).get("paypal_fee")
    if fee:
        db.add(
            LedgerEntry(
                type=LedgerType.fee,
                amount=from_paypal(fee["value"], fee["currency_code"]),
                currency=fee["currency_code"],
                project_id=donation.project_id,
                donation_id=donation.id,
            )
        )


def _upsert_donor(db: Session, order: dict) -> Donor:
    payer = order.get("payer", {})
    payer_id = payer.get("payer_id")
    # A card payment without a PayPal account is a guest (half weight in matching).
    is_guest = "card" in order.get("payment_source", {})
    name = payer.get("name", {}).get("given_name")

    if payer_id:
        donor = db.scalar(select(Donor).where(Donor.paypal_payer_id == payer_id))
        if donor:
            return donor
    donor = Donor(paypal_payer_id=payer_id, is_guest=is_guest or payer_id is None, display_name=name)
    db.add(donor)
    db.flush()
    return donor
