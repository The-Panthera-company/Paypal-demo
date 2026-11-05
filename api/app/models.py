"""The fourteen tables from the System Design data model, plus webhook_events, payout_accounts,
category_gifts, category_allocations, paypal_plans and agent_subscriptions.

Amounts are integers in minor units. List fields (tags, categories) are JSON so the
same models run on Postgres and on SQLite in tests.
"""

import enum
from datetime import date, datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text
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


class ProjectStatus(str, enum.Enum):
    draft = "draft"
    pending_review = "pending_review"
    verified = "verified"
    active = "active"
    frozen = "frozen"  # removed by an admin; a Watchdog hit only sets matching_frozen
    completed = "completed"


class DocumentKind(str, enum.Enum):
    registration = "registration"
    plan = "plan"
    receipt = "receipt"
    photo = "photo"


class MilestoneStatus(str, enum.Enum):
    open = "open"
    evidence_submitted = "evidence_submitted"
    released = "released"
    held = "held"


class RoundStatus(str, enum.Enum):
    scheduled = "scheduled"
    open = "open"
    closing = "closing"  # ended, waiting for open Watchdog cases before final results
    closed = "closed"


class PayoutStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    success = "success"
    denied = "denied"


class CaseStatus(str, enum.Enum):
    open = "open"
    cleared = "cleared"
    confirmed = "confirmed"


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
    round_id: Mapped[int | None] = mapped_column(ForeignKey("rounds.id"))
    target_type: Mapped[TargetType] = mapped_column(Enum(TargetType, native_enum=False))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    # Null for Giving Agent allocations, which are ledger moves, not PayPal orders.
    paypal_order_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    # Refunds and refund webhooks reference the capture, not the order.
    paypal_capture_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[DonationStatus] = mapped_column(
        Enum(DonationStatus, native_enum=False), default=DonationStatus.created
    )
    mandate_run_id: Mapped[int | None] = mapped_column(ForeignKey("mandate_runs.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[LedgerType] = mapped_column(Enum(LedgerType, native_enum=False))
    # Always positive; the type says which way the money moved.
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    donation_id: Mapped[int | None] = mapped_column(ForeignKey("donations.id"))
    payout_item_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("donors.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str | None] = mapped_column(Text)
    # Neutral descriptive tags, e.g. "faith-based hospital"; donors can exclude any of them.
    tags: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, native_enum=False), default=ProjectStatus.draft
    )
    # Set by a Watchdog hit: donations still flow, matching is paused until an admin clears it.
    matching_frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    goal_amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    hide_location: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by: Mapped[str | None] = mapped_column(String(120))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    urgency: Mapped[int] = mapped_column(Integer, default=3)  # 1 (low) to 5 (critical)
    cause: Mapped[str | None] = mapped_column(String(60))
    beneficiary_group: Mapped[str | None] = mapped_column(String(30))  # children, adults, elderly
    region: Mapped[str | None] = mapped_column(String(60))
    # The group running the project on the ground, e.g. "Lanet Community Library Group".
    facilitator: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ProjectDocument(Base):
    __tablename__ = "project_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    milestone_id: Mapped[int | None] = mapped_column(ForeignKey("milestones.id"))
    kind: Mapped[DocumentKind] = mapped_column(Enum(DocumentKind, native_enum=False))
    file_url: Mapped[str] = mapped_column(String(500))
    extracted_fields: Mapped[dict | None] = mapped_column(JSON)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Milestone(Base):
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    seq: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    amount: Mapped[int] = mapped_column(BigInteger)
    # Matching money is added here at round close, so it is released only with evidence.
    match_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[MilestoneStatus] = mapped_column(
        Enum(MilestoneStatus, native_enum=False), default=MilestoneStatus.open
    )


class Mandate(Base):
    __tablename__ = "mandates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    donor_id: Mapped[int] = mapped_column(ForeignKey("donors.id"))
    monthly_budget: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    categories: Mapped[list] = mapped_column(JSON, default=list)  # category ids
    excluded_tags: Mapped[list] = mapped_column(JSON, default=list)
    per_project_max: Mapped[int] = mapped_column(BigInteger)
    approval_threshold: Mapped[int] = mapped_column(BigInteger)
    weight_overrides: Mapped[dict | None] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MandateRun(Base):
    __tablename__ = "mandate_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id"))
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decisions: Mapped[dict | None] = mapped_column(JSON)  # candidates, scores, chosen, reasons
    report_text: Mapped[str | None] = mapped_column(Text)


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    matching_pool: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    project_cap_pct: Mapped[float] = mapped_column(Float, default=30.0)
    floor_pct: Mapped[float] = mapped_column(Float, default=20.0)
    per_person_cap: Mapped[int] = mapped_column(BigInteger, default=5000)
    status: Mapped[RoundStatus] = mapped_column(
        Enum(RoundStatus, native_enum=False), default=RoundStatus.scheduled
    )


class MatchResult(Base):
    __tablename__ = "match_results"

    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"), primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    # Projections (False) are overwritten every 5 minutes; the final row is written once at close.
    is_final: Mapped[bool] = mapped_column(Boolean, primary_key=True, default=False)
    score: Mapped[float] = mapped_column(Float)
    floor_amount: Mapped[int] = mapped_column(BigInteger)
    crowd_amount: Mapped[int] = mapped_column(BigInteger)
    capped: Mapped[bool] = mapped_column(Boolean, default=False)
    final_amount: Mapped[int] = mapped_column(BigInteger)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Payout(Base):
    __tablename__ = "payouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Deterministic, e.g. round-3-match-USD; PayPal rejects a reuse within 30 days.
    sender_batch_id: Mapped[str] = mapped_column(String(127), unique=True)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[PayoutStatus] = mapped_column(
        Enum(PayoutStatus, native_enum=False), default=PayoutStatus.pending
    )
    items: Mapped[list] = mapped_column(JSON, default=list)
    paypal_batch_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WatchdogCase(Base):
    __tablename__ = "watchdog_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    rule: Mapped[str] = mapped_column(String(60))
    evidence: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus, native_enum=False), default=CaseStatus.open)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(60))  # e.g. "giving-agent", "admin", "system"
    action: Mapped[str] = mapped_column(String(60))
    inputs: Mapped[dict | None] = mapped_column(JSON)
    rule_result: Mapped[str | None] = mapped_column(String(60))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WebhookEvent(Base):
    """Every PayPal webhook we accepted, so a redelivery is recognised and skipped."""

    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # PayPal's event id, WH-...
    event_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    # processed, ignored, unmatched or mismatch
    result: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PayoutAccount(Base):
    """Where a project's tranches are paid: a PayPal account email. Its own table so existing
    databases pick it up at startup (create_all adds tables, not columns)."""

    __tablename__ = "payout_accounts"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    paypal_email: Mapped[str] = mapped_column(String(254))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class CategoryGift(Base):
    """The donor's split rule and exclusions for a category donation, chosen at checkout."""

    __tablename__ = "category_gifts"

    donation_id: Mapped[int] = mapped_column(ForeignKey("donations.id"), primary_key=True)
    rule: Mapped[str] = mapped_column(String(20), default="crowd")
    excluded_tags: Mapped[list] = mapped_column(JSON, default=list)


class CategoryAllocation(Base):
    """Where a captured category donation went: written once at capture, by the donor's rule.
    Counts toward each project's raised total while the donation stays captured."""

    __tablename__ = "category_allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    donation_id: Mapped[int] = mapped_column(ForeignKey("donations.id"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PaypalPlan(Base):
    """The PayPal billing plan behind monthly Giving Agent budgets, created once per currency."""

    __tablename__ = "paypal_plans"

    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(64))
    plan_id: Mapped[str] = mapped_column(String(64))


class AgentSubscription(Base):
    """A donor's monthly PayPal subscription that tops up their Giving Agent budget."""

    __tablename__ = "agent_subscriptions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # PayPal's subscription id, I-...
    donor_id: Mapped[int] = mapped_column(ForeignKey("donors.id"))
    amount: Mapped[int] = mapped_column(BigInteger)  # cents per month
    currency: Mapped[str] = mapped_column(String(3))
    # APPROVAL_PENDING until the donor approves in PayPal, then ACTIVE, SUSPENDED, CANCELLED or EXPIRED
    status: Mapped[str] = mapped_column(String(30), default="APPROVAL_PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
