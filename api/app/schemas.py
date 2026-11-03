"""Request and response shapes shared by the routers; these become the OpenAPI spec.

Money is always integer minor units in fields ending in _cents, plus a currency code.
Each response model carries an example so the Postman mock returns realistic data.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    CaseStatus,
    DocumentKind,
    DonationStatus,
    MilestoneStatus,
    PayoutStatus,
    ProjectStatus,
    RoundStatus,
    TargetType,
)


def _example(data: dict) -> ConfigDict:
    return ConfigDict(json_schema_extra={"example": data})


class ErrorOut(BaseModel):
    model_config = _example({"detail": {"error": "NOT_IMPLEMENTED", "message": "Planned: matching engine"}})
    detail: dict


# --- Catalogue -------------------------------------------------------------------------


class CategoryOut(BaseModel):
    model_config = _example({"id": 2, "name": "Education", "project_count": 4})
    id: int
    name: str
    project_count: int


class MilestoneOut(BaseModel):
    model_config = _example(
        {
            "id": 7,
            "seq": 1,
            "title": "Buy 40 books",
            "amount_cents": 30000,
            "match_amount_cents": 0,
            "currency": "USD",
            "due_date": "2026-11-30",
            "status": "open",
        }
    )
    id: int
    seq: int
    title: str
    amount_cents: int
    match_amount_cents: int
    currency: str
    due_date: date | None
    status: MilestoneStatus


class ProjectSummary(BaseModel):
    model_config = _example(
        {
            "id": 1,
            "title": "Lanet Library",
            "category_id": 2,
            "category": "Education",
            "tags": ["books", "literacy"],
            "cause": "literacy",
            "beneficiary_group": "children",
            "region": "Nakuru",
            "urgency": 4,
            "status": "active",
            "matching_frozen": False,
            "goal_cents": 120000,
            "raised_cents": 40000,
            "backer_count": 16,
            "projected_match_cents": 4000,
            "currency": "USD",
        }
    )
    id: int
    title: str
    category_id: int
    category: str
    tags: list[str]
    cause: str | None
    beneficiary_group: str | None
    region: str | None = Field(description="Null when the project hides its location")
    urgency: int = Field(ge=1, le=5)
    status: ProjectStatus
    matching_frozen: bool
    goal_cents: int
    raised_cents: int
    backer_count: int = Field(description="How many people backed it; never who")
    projected_match_cents: int
    currency: str


class ProjectDetail(ProjectSummary):
    model_config = _example(
        {
            **ProjectSummary.model_config["json_schema_extra"]["example"],
            "summary": "A community library for 300 pupils in Lanet.",
            "verified_at": "2026-11-01T10:00:00Z",
            "milestones": [MilestoneOut.model_config["json_schema_extra"]["example"]],
        }
    )
    summary: str | None
    verified_at: datetime | None
    milestones: list[MilestoneOut]


class StoryOut(BaseModel):
    model_config = _example(
        {
            "id": 3,
            "project_id": 1,
            "milestone_id": 7,
            "title": "40 books delivered",
            "body": "Receipts checked and the first tranche released.",
            "evidence_urls": ["https://files.example.com/receipt-7.jpg"],
            "created_at": "2026-11-08T12:00:00Z",
        }
    )
    id: int
    project_id: int
    milestone_id: int | None
    title: str
    body: str
    evidence_urls: list[str]
    created_at: datetime


class FundingPoint(BaseModel):
    model_config = _example({"date": "2026-11-03", "raised_cents": 12000, "backer_count": 5})
    date: date
    raised_cents: int
    backer_count: int


class ProjectApplicationIn(BaseModel):
    title: str
    summary: str
    category_id: int
    tags: list[str] = []
    cause: str | None = None
    beneficiary_group: Literal["children", "adults", "elderly"] | None = None
    region: str | None = None
    hide_location: bool = False
    goal_cents: int = Field(gt=0)
    urgency: int = Field(3, ge=1, le=5)


class DocumentIn(BaseModel):
    kind: DocumentKind
    file_url: str
    milestone_id: int | None = None


class DocumentOut(BaseModel):
    model_config = _example(
        {
            "id": 11,
            "project_id": 1,
            "milestone_id": 7,
            "kind": "receipt",
            "file_url": "https://files.example.com/receipt-7.jpg",
            "extracted_fields": {"total_cents": 29500, "supplier": "Nakuru Books Ltd", "date": "2026-11-07"},
            "flags": [],
        }
    )
    id: int
    project_id: int
    milestone_id: int | None
    kind: DocumentKind
    file_url: str
    extracted_fields: dict | None
    flags: list[str]


# --- Donations -------------------------------------------------------------------------


class SplitRule(BaseModel):
    rule: Literal["crowd", "equal", "closest_to_goal"] = Field(
        "crowd", description="crowd = 80% by project scores + 20% equally (default)"
    )


class CategoryPreviewIn(SplitRule):
    category_id: int
    amount_cents: int = Field(gt=0)
    excluded_tags: list[str] = []


class Allocation(BaseModel):
    project_id: int
    title: str
    amount_cents: int


class ExcludedProject(BaseModel):
    project_id: int
    title: str
    matched_tag: str


class CategoryPreviewOut(BaseModel):
    model_config = _example(
        {
            "category_id": 2,
            "amount_cents": 2000,
            "currency": "USD",
            "rule": "crowd",
            "allocations": [
                {"project_id": 1, "title": "Lanet Library", "amount_cents": 1100},
                {"project_id": 2, "title": "Kaptembwo Desks", "amount_cents": 600},
                {"project_id": 4, "title": "New Reading Corner", "amount_cents": 300},
            ],
            "excluded": [{"project_id": 3, "title": "Girls' STEM Club", "matched_tag": "faith-based"}],
        }
    )
    category_id: int
    amount_cents: int
    currency: str
    rule: str
    allocations: list[Allocation]
    excluded: list[ExcludedProject]


class DonationOut(BaseModel):
    model_config = _example(
        {
            "id": 4,
            "status": "captured",
            "target_type": "PROJECT",
            "project_id": 1,
            "category_id": None,
            "amount_cents": 2000,
            "currency": "USD",
            "paypal_order_id": "8E825560D88497210",
            "paypal_capture_id": "09G48096F55227148",
        }
    )
    id: int
    status: DonationStatus
    target_type: TargetType
    project_id: int | None
    category_id: int | None
    amount_cents: int
    currency: str
    paypal_order_id: str | None
    paypal_capture_id: str | None


# --- Donors and mandates ---------------------------------------------------------------


class DonorOut(BaseModel):
    model_config = _example(
        {
            "id": 1,
            "display_name": "Wanjiru",
            "is_guest": False,
            "show_on_leaderboard": False,
            "interests": {"categories": [2], "causes": ["literacy"], "excluded_tags": []},
        }
    )
    id: int
    display_name: str | None
    is_guest: bool
    show_on_leaderboard: bool
    interests: dict | None


class DonorUpdate(BaseModel):
    display_name: str | None = None
    show_on_leaderboard: bool | None = None
    interests: dict | None = None


class ReportGift(BaseModel):
    donation_id: int
    project_id: int | None
    project_title: str | None
    via: TargetType
    amount_cents: int
    status: DonationStatus
    match_unlocked_cents: int


class DonorReport(BaseModel):
    model_config = _example(
        {
            "donor_id": 1,
            "currency": "USD",
            "total_given_cents": 4000,
            "match_unlocked_cents": 2300,
            "gifts": [
                {
                    "donation_id": 4,
                    "project_id": 1,
                    "project_title": "Lanet Library",
                    "via": "PROJECT",
                    "amount_cents": 2000,
                    "status": "captured",
                    "match_unlocked_cents": 1150,
                }
            ],
            "updates": [StoryOut.model_config["json_schema_extra"]["example"]],
            "agent_report": "USD 3.00 to Kaptembwo Desks: 4 backers, 60% funded, receipts uploaded.",
        }
    )
    donor_id: int
    currency: str
    total_given_cents: int
    match_unlocked_cents: int
    gifts: list[ReportGift]
    updates: list[StoryOut]
    agent_report: str | None


class MandateIn(BaseModel):
    monthly_budget_cents: int = Field(gt=0)
    categories: list[int] = Field(description="Category ids the agent may give to")
    excluded_tags: list[str] = []
    per_project_max_cents: int = Field(gt=0)
    approval_threshold_cents: int = Field(gt=0, description="Single gifts above this wait for the donor")
    weight_overrides: dict[str, float] | None = Field(
        None, description="Adjust score weights within limits, e.g. {'few_backers': 45}"
    )
    active: bool = True


class MandateOut(MandateIn):
    model_config = _example(
        {
            "id": 1,
            "donor_id": 1,
            "currency": "USD",
            "monthly_budget_cents": 1000,
            "categories": [2],
            "excluded_tags": [],
            "per_project_max_cents": 400,
            "approval_threshold_cents": 500,
            "weight_overrides": {"few_backers": 45},
            "active": True,
            "funded_balance_cents": 1000,
        }
    )
    id: int
    donor_id: int
    currency: str
    funded_balance_cents: int = Field(description="Budget topped up through PayPal and not yet given")


class MandateRunOut(BaseModel):
    model_config = _example(
        {
            "id": 5,
            "mandate_id": 1,
            "run_at": "2026-11-06T09:00:00Z",
            "decisions": {
                "candidates": [{"project_id": 2, "score": 81.5}, {"project_id": 3, "score": 64.0}],
                "chosen": [{"project_id": 2, "amount_cents": 300}],
                "skipped": [{"project_id": 5, "reason": "excluded tag: gambling-recovery"}],
            },
            "report_text": "USD 3.00 to Kaptembwo Desks: 4 backers, 60% funded, receipts uploaded.",
        }
    )
    id: int
    mandate_id: int
    run_at: datetime
    decisions: dict | None
    report_text: str | None


class PendingApproval(BaseModel):
    model_config = _example(
        {"donation_id": 9, "project_id": 2, "project_title": "Kaptembwo Desks", "amount_cents": 600, "reason": "Above your 5.00 approval threshold"}
    )
    donation_id: int
    project_id: int
    project_title: str
    amount_cents: int
    reason: str


class ApprovalIn(BaseModel):
    approve: bool


# --- Rounds and matching ---------------------------------------------------------------


class RoundOut(BaseModel):
    model_config = _example(
        {
            "id": 1,
            "name": "November round",
            "starts_at": "2026-11-01T00:00:00Z",
            "ends_at": "2026-11-09T18:00:00Z",
            "matching_pool_cents": 1000000,
            "currency": "USD",
            "project_cap_pct": 30.0,
            "floor_pct": 20.0,
            "per_person_cap_cents": 5000,
            "status": "open",
        }
    )
    id: int
    name: str
    starts_at: datetime
    ends_at: datetime
    matching_pool_cents: int
    currency: str
    project_cap_pct: float
    floor_pct: float
    per_person_cap_cents: int
    status: RoundStatus


class LeaderboardRow(BaseModel):
    rank: int
    project_id: int
    title: str
    category: str
    backer_count: int
    raised_cents: int
    score: float
    floor_cents: int
    crowd_cents: int
    match_cents: int
    capped: bool
    matching_frozen: bool


class LeaderboardOut(BaseModel):
    model_config = _example(
        {
            "round_id": 1,
            "is_final": False,
            "computed_at": "2026-11-05T10:05:00Z",
            "currency": "USD",
            "rows": [
                {
                    "rank": 1,
                    "project_id": 1,
                    "title": "Lanet Library",
                    "category": "Education",
                    "backer_count": 16,
                    "raised_cents": 40000,
                    "score": 6000.0,
                    "floor_cents": 50000,
                    "crowd_cents": 533300,
                    "match_cents": 400000,
                    "capped": True,
                    "matching_frozen": False,
                }
            ],
        }
    )
    round_id: int
    is_final: bool = Field(description="False while the round is open: amounts are projected")
    computed_at: datetime | None
    currency: str
    rows: list[LeaderboardRow]


# --- Admin, Watchdog, payouts ----------------------------------------------------------


class VerifyIn(BaseModel):
    approve: bool
    note: str | None = None


class CaseOut(BaseModel):
    model_config = _example(
        {
            "id": 2,
            "project_id": 6,
            "rule": "new_payer_burst",
            "evidence": {"new_payer_ids": 20, "window_minutes": 15, "median_amount_cents": 100},
            "status": "open",
            "frozen_at": "2026-11-08T14:02:00Z",
            "resolved_by": None,
            "created_at": "2026-11-08T14:02:00Z",
        }
    )
    id: int
    project_id: int
    rule: str
    evidence: dict | None
    status: CaseStatus
    frozen_at: datetime | None
    resolved_by: str | None
    created_at: datetime


class CaseIn(BaseModel):
    project_id: int
    rule: Literal["new_payer_burst", "reciprocal_backing", "owner_donation", "refund_spike"]
    evidence: dict = Field(
        description='Include "donor_ids": [..] for the suspected cluster; if an admin confirms the case, '
        "the matching engine counts those donors as one person."
    )


class CaseResolveIn(BaseModel):
    action: Literal["clear", "confirm"] = Field(
        description="clear = resume matching; confirm = merge flagged donors into one cluster"
    )
    remove_project: bool = Field(False, description="With confirm: remove the project and refund its donations")
    note: str | None = None


class PayoutItem(BaseModel):
    project_id: int
    milestone_id: int | None
    amount_cents: int
    receiver: str | None = Field(description="Null until the project has a payout account")
    status: str = Field(description="NEW before sending, then PayPal's: PENDING, SUCCESS, UNCLAIMED, FAILED, ...")
    payout_item_id: str | None = None
    error: str | None = Field(None, description="Why it wasn't sent, e.g. NO_PAYOUT_ACCOUNT or a PayPal issue")


class PayoutAccountIn(BaseModel):
    paypal_email: str = Field(
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", description="In the sandbox, a sandbox personal account's email"
    )


class PayoutAccountOut(PayoutAccountIn):
    model_config = _example({"project_id": 1, "paypal_email": "lanet-library@example.com"})
    project_id: int


class PayoutOut(BaseModel):
    model_config = _example(
        {
            "id": 1,
            "sender_batch_id": "milestone-7-USD",
            "currency": "USD",
            "status": "success",
            "paypal_batch_id": "5UXD2E8A7EBQJ",
            "items": [
                {"project_id": 1, "milestone_id": 7, "amount_cents": 30000, "receiver": "lanet-library@example.com", "status": "SUCCESS"}
            ],
        }
    )
    id: int
    sender_batch_id: str
    currency: str
    status: PayoutStatus
    paypal_batch_id: str | None
    items: list[PayoutItem]


class MilestoneReviewIn(BaseModel):
    approve: bool
    note: str | None = None


# --- Agent (internal) endpoints --------------------------------------------------------


class CheckedDonationIn(BaseModel):
    mandate_run_id: int
    project_id: int
    amount_cents: int = Field(gt=0)
    reason: str = Field(description="Why the agent chose this project; stored in the audit log")


class CheckedDonationOut(BaseModel):
    model_config = _example(
        {
            "status": "recorded",
            "donation_id": 12,
            "rule_result": "ok",
            "reason": "Within budget, per-project max and exclusions",
        }
    )
    status: Literal["recorded", "awaiting_donor_approval", "rejected"]
    donation_id: int | None
    rule_result: str = Field(description="ok, or the rule that blocked it, e.g. over_per_project_max")
    reason: str


class MilestoneChecks(BaseModel):
    receipt_total_within_10pct: bool
    supplier_matches_plan: bool
    photo_not_duplicate: bool
    dated_in_window: bool


class PayoutRequestIn(BaseModel):
    milestone_id: int
    checks: MilestoneChecks
    summary: str = Field(description="LLM summary shown to the admin if the request is held")


class PayoutRequestOut(BaseModel):
    model_config = _example({"status": "released", "payout_id": 1, "reason": "All checks passed, below threshold"})
    status: Literal["released", "held_for_admin"]
    payout_id: int | None
    reason: str


class MandateRunIn(BaseModel):
    mandate_id: int
    decisions: dict
    report_text: str | None = None


class AuditIn(BaseModel):
    actor: str
    action: str
    inputs: dict | None = None
    rule_result: str | None = None
    reason: str | None = None


class AuditOut(AuditIn):
    model_config = _example(
        {
            "id": 40,
            "actor": "giving-agent",
            "action": "checked_donation",
            "inputs": {"mandate_run_id": 5, "project_id": 2, "amount_cents": 300},
            "rule_result": "ok",
            "reason": "Few backers (4), 60% funded, receipts uploaded",
            "created_at": "2026-11-06T09:00:02Z",
        }
    )
    id: int
    created_at: datetime


class ActiveMandate(MandateOut):
    pass


# --- Webhooks ----------------------------------------------------------------------------


class WebhookAck(BaseModel):
    model_config = _example({"event_id": "WH-2WR32451HC0233532-67976317FL4543714", "status": "processed"})
    event_id: str
    # duplicate = already handled; unmatched = not one of our donations; mismatch = amount or id disagreed
    status: Literal["processed", "duplicate", "ignored", "unmatched", "mismatch"]


class WebhookEventOut(BaseModel):
    model_config = _example(
        {
            "id": "WH-2WR32451HC0233532-67976317FL4543714",
            "event_type": "PAYMENT.CAPTURE.REFUNDED",
            "resource_id": "1JU08902781691411",
            "result": "processed",
            "received_at": "2026-11-06T09:00:02Z",
        }
    )
    id: str
    event_type: str
    resource_id: str | None
    result: str
    received_at: datetime


# --- Reconciliation ------------------------------------------------------------------------


class ReconciliationIssue(BaseModel):
    check: str
    severity: Literal["error", "warning"]
    detail: str
    refs: list = Field(description="Ids of the rows involved (donations, payouts, milestones, ...)")


class ReconciliationOut(BaseModel):
    model_config = _example(
        {
            "generated_at": "2026-11-10T09:00:00Z",
            "ok": True,
            "totals": {
                "received_via_paypal_cents": 120000,
                "refunded_cents": 2000,
                "paypal_fees_cents": 4100,
                "paid_out_cents": 30000,
                "platform_balance_cents": 83900,
                "agent_budget_unspent_cents": 700,
                "tranches_released_cents": 35000,
                "released_not_yet_paid_cents": 5000,
                "match_booked_cents": 274000,
                "category_unallocated_cents": 0,
            },
            "issues": [
                {"check": "payout_unclaimed", "severity": "warning",
                 "detail": "Payouts sent to an email with no PayPal account yet (returned after 30 days)", "refs": [3]}
            ],
        }
    )
    generated_at: datetime
    ok: bool = Field(description="False when any issue is an error")
    totals: dict[str, int]
    issues: list[ReconciliationIssue]


class SweepOut(BaseModel):
    model_config = _example({"checked": 2, "captured": [7], "failed": [5], "unchanged": [], "errors": []})
    checked: int
    captured: list[int] = Field(description="Donation ids captured or recorded now")
    failed: list[int] = Field(description="Voided, declined or abandoned (never approved)")
    unchanged: list[int]
    errors: list[str]
