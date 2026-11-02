"""Payment tables from the System Design data model.

Only the tables the donation flow needs today; projects, categories and the rest
come with their own endpoints. Amounts are integers in minor units.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TargetType(str, enum.Enum):
    PROJECT = "PROJECT"
    CATEGORY = "CATEGORY"
    AGENT = "AGENT"


class DonationStatus(str, enum.Enum):
    created = "created"  # order created, donor has not paid yet
    pending = "pending"  # captured but PayPal holds it (capture status PENDING); webhook settles it
    captured = "captured"
    failed = "failed"  # declined or denied
    refunded = "refunded"


class LedgerType(str, enum.Enum):
    donation = "donation"
    refund = "refund"
    match = "match"
    tranche = "tranche"
    payout = "payout"
    fee = "fee"


class Donor(Base):
    __tablename__ = "donors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Null for guest card payments that come back without a payer ID.
    paypal_payer_id: Mapped[str | None] = mapped_column(String(32), unique=True)
    is_guest: Mapped[bool] = mapped_column(default=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    show_on_leaderboard: Mapped[bool] = mapped_column(default=False)
    interests: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Donation(Base):
    __tablename__ = "donations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    donor_id: Mapped[int | None] = mapped_column(ForeignKey("donors.id"))
    round_id: Mapped[int | None] = mapped_column(Integer)
    target_type: Mapped[TargetType] = mapped_column(Enum(TargetType, native_enum=False))
    project_id: Mapped[int | None] = mapped_column(Integer)
    category_id: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    # Null for Giving Agent allocations, which are ledger moves, not PayPal orders.
    paypal_order_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    # Refunds and refund webhooks reference the capture, not the order.
    paypal_capture_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[DonationStatus] = mapped_column(
        Enum(DonationStatus, native_enum=False), default=DonationStatus.created
    )
    mandate_run_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[LedgerType] = mapped_column(Enum(LedgerType, native_enum=False))
    # Always positive; the type says which way the money moved.
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    project_id: Mapped[int | None] = mapped_column(Integer)
    donation_id: Mapped[int | None] = mapped_column(ForeignKey("donations.id"))
    payout_item_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
