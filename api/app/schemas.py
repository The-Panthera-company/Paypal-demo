"""Request and response shapes shared by the routers; these become the OpenAPI spec.

Money is always integer minor units in fields ending in _cents, plus a currency code.
Each response model carries an example so the Postman mock returns realistic data.
"""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    CaseStatus,
    DocumentKind,
    DonationStatus,
    MilestoneStatus,
    PayoutStatus,
    ProcurementStatus,
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
            "facilitator": "Lanet Community Library Group",
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
    facilitator: str | None = Field(description="The group running the project on the ground")
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


class MilestonePlanIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    amount_cents: int = Field(gt=0)
    due_date: date


class ProjectApplicationIn(BaseModel):
    title: str
    facilitator: str | None = Field(None, max_length=120, description="The group running the project on the ground")
    summary: str
    category_id: int
    tags: list[str] = []
    cause: str | None = None
    beneficiary_group: Literal["children", "adults", "elderly"] | None = None
    region: str | None = None
    hide_location: bool = False
    goal_cents: int = Field(gt=0)
    urgency: int = Field(3, ge=1, le=5)
    milestones: list[MilestonePlanIn] = Field(
        min_length=1, max_length=12, description="The tranches, in order; their amounts add up to goal_cents"
    )
    payout_email: str | None = Field(
        None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", description="PayPal account the tranches are paid to"
    )


class DocumentIn(BaseModel):
    kind: DocumentKind
    file_url: str = Field(pattern=r"^https://", max_length=500, description="Where the file is hosted (https)")
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


class MandateConstraintsOut(BaseModel):
    model_config = _example(
        {
            "default_weights": {"few_backers": 35, "progress": 25, "urgency": 20, "evidence": 10, "days_since_funded": 10},
            "max_weight_shift": 20,
            "max_budget_cents": 1000000,
            "max_tags": 20,
            "max_tag_length": 40,
            "min_per_project_cents": 100,
            "max_per_project_cents": 1000000,
            "min_approval_threshold_cents": 100,
            "max_approval_threshold_cents": 1000000,
        }
    )
    default_weights: dict[str, float] = Field(description="The agent's score weights; weight_overrides move them")
    max_weight_shift: float = Field(description="How far each weight may move from its default, either way")
    max_budget_cents: int = Field(description="Highest monthly budget a mandate may set")
    max_tags: int = Field(description="Most excluded tags a mandate may have")
    max_tag_length: int = Field(description="Longest excluded tag, in characters")
    min_per_project_cents: int = Field(description="Lowest per-project max")
    max_per_project_cents: int = Field(description="Also never more than the mandate's monthly budget")
    min_approval_threshold_cents: int = Field(description="Lowest approval threshold")
    max_approval_threshold_cents: int = Field(description="Also never more than the mandate's monthly budget")


class MandateProblem(BaseModel):
    field: str = Field(description="The field at fault, e.g. per_project_max_cents or weight_overrides.urgency")
    code: str = Field(description="A stable code, e.g. THRESHOLD_OVER_BUDGET")
    message: str = Field(description="What is wrong, for people")


class MandatePreviewOut(BaseModel):
    model_config = _example(
        {
            "ok": False,
            "errors": [{"field": "approval_threshold_cents", "code": "THRESHOLD_OVER_BUDGET",
                        "message": "Approval threshold can't be more than the monthly budget"}],
            "normalized": {"monthly_budget_cents": 1000, "categories": [2], "excluded_tags": ["faith-based"],
                           "per_project_max_cents": 400, "approval_threshold_cents": 5000,
                           "weight_overrides": None, "active": True},
        }
    )
    ok: bool = Field(description="True when PUT would save it as it is")
    errors: list[MandateProblem]
    normalized: MandateIn = Field(description="What would be saved: tags trimmed, lowercased and deduped")


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
    mandate_id: int | None = Field(description="The mandate the run was for; null for a Procurement Agent run")
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
    rule: Literal[
        "new_payer_burst", "reciprocal_backing", "owner_donation", "refund_spike", "collusion_cluster"
    ]
    evidence: dict = Field(
        description='Include "donor_ids": [..] for the suspected cluster; if an admin confirms the case, '
        "the matching engine counts those donors as one person. collusion_cluster also accepts an "
        'optional "graph": {"nodes": [{"id", "type", "label"}], "edges": [{"source", "target", "weight"}]}.'
    )


class DonationEventOut(BaseModel):
    model_config = _example(
        {
            "donation_id": 4,
            "project_id": 1,
            "donor_id": 12,
            "status": "captured",
            "amount_cents": 2000,
            "captured_at": "2026-11-08T14:02:00Z",
            "donor_created_at": "2026-11-01T09:00:00Z",
            "owner_donor_id": 3,
            "is_guest": False,
        }
    )
    donation_id: int
    project_id: int | None
    donor_id: int | None
    status: DonationStatus
    amount_cents: int
    captured_at: datetime
    donor_created_at: datetime | None
    owner_donor_id: int | None
    is_guest: bool


class CaseResolveIn(BaseModel):
    action: Literal["clear", "confirm"] = Field(
        description="clear = resume matching; confirm = merge flagged donors into one cluster"
    )
    remove_project: bool = Field(False, description="With confirm: remove the project and refund its donations")
    note: str | None = None


class PayoutItem(BaseModel):
    project_id: int
    milestone_id: int | None
    procurement_id: int | None = Field(None, description="Managed procurement this item pays, when it is a purchase")
    amount_cents: int
    receiver: str | None = Field(description="Null until the project has a payout account or a supplier proposal")
    sender_item_id: str | None = Field(None, description="Our deterministic id for this item, e.g. procurement-7")
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


# --- Managed procurement ----------------------------------------------------------------


class ProcurementRequestIn(BaseModel):
    model_config = _example(
        {
            "milestone_id": 7,
            "description": "40 copies of the Grade 3 reading set",
            "quantity": 40,
            "max_amount_cents": 3000,
        }
    )
    milestone_id: int = Field(description="Milestone this purchase is for")
    description: str = Field(min_length=1, max_length=500, description="What the project needs bought")
    quantity: int = Field(gt=0, description="How many units the request covers")
    max_amount_cents: int = Field(gt=0, description="Most the supplier may be paid, in cents")


class ProcurementProposeIn(BaseModel):
    model_config = _example(
        {
            "supplier_id": 1,
            "amount_cents": 3000,
            "line_items": [{"description": "40 reading sets", "quantity": 40, "unit_amount_cents": 75}],
            "rationale": "Lowest eligible quote, delivery included",
        }
    )
    supplier_id: int = Field(description="Supplier chosen from GET /internal/procurement/suppliers")
    amount_cents: int = Field(gt=0, description="What the supplier will be paid, in cents")
    line_items: list[dict] = Field(default_factory=list, description="The quoted lines; kept on the receipt")
    rationale: str = Field(min_length=1, max_length=2000, description="Why this supplier and price were chosen")
    run_id: int | None = Field(None, description="The agent run that chose it (POST /internal/procurement/runs), "
                                                 "so the purchase links to its public trace")


class ProcurementRunIn(BaseModel):
    model_config = _example(
        {
            "decisions": {"trace": [{"seq": 1, "step": "list_suppliers", "tool": "list_procurement_suppliers",
                                     "status": "ok", "title": "Found 2 eligible suppliers in Nakuru"}]},
            "report_text": "Chose Nakuru Books & Stationery: the only eligible bookseller, 30 USD with delivery.",
        }
    )
    decisions: dict = Field(description='What the agent considered and chose; "trace" is the ordered list of steps')
    report_text: str | None = Field(None, max_length=4000, description="A short account of the run, for people")


class ProcurementApproveIn(BaseModel):
    model_config = _example({"approve": True, "note": "Three quotes checked by phone"})
    approve: bool = Field(True, description="True to approve payment, false to decline the proposal")
    note: str | None = Field(None, description="Optional admin note, kept in the audit log")


class ProcurementOut(BaseModel):
    model_config = _example(
        {
            "id": 3,
            "project_id": 1,
            "milestone_id": 7,
            "description": "40 copies of the Grade 3 reading set",
            "quantity": 40,
            "max_amount_cents": 3000,
            "currency": "USD",
            "status": "paid",
            "supplier_id": 1,
            "supplier_name": "Nakuru Books & Stationery",
            "amount_cents": 3000,
            "line_items": [{"description": "40 reading sets", "quantity": 40, "unit_amount_cents": 75}],
            "rationale": "Lowest eligible quote, delivery included",
            "admin_approved": False,
            "approved_by": None,
            "approved_at": None,
            "payout_id": 8,
            "receipt_document_id": 21,
            "error": None,
            "created_at": "2026-11-09T09:00:00Z",
            "updated_at": "2026-11-09T09:02:00Z",
        }
    )
    id: int = Field(description="Procurement id")
    project_id: int = Field(description="Project that requested the purchase")
    milestone_id: int = Field(description="Milestone the purchase belongs to")
    description: str = Field(description="What the project needs bought")
    quantity: int = Field(description="How many units the request covers")
    max_amount_cents: int = Field(description="Most the supplier may be paid, in cents")
    currency: str = Field(description="Currency of the request")
    status: ProcurementStatus = Field(description="requested, proposed, approved, paid, failed or cancelled")
    supplier_id: int | None = Field(None, description="Supplier chosen by the Procurement Agent")
    supplier_name: str | None = Field(None, description="Supplier's name, joined for display")
    amount_cents: int | None = Field(None, description="Proposed supplier price, in cents")
    line_items: list[dict] = Field(default_factory=list, description="The supplier's quoted lines")
    rationale: str | None = Field(None, description="Why the agent chose this supplier and price")
    admin_approved: bool = Field(description="Whether an admin approved a purchase above the automatic limit")
    approved_by: str | None = Field(None, description="Who approved it")
    approved_at: datetime | None = Field(None, description="When it was approved")
    payout_id: int | None = Field(None, description="PayPal Payouts batch that pays the supplier")
    receipt_document_id: int | None = Field(None, description="Receipt document created from the PayPal batch")
    error: str | None = Field(None, description="Why the last payment attempt failed, when it did")
    created_at: datetime = Field(description="When the request was created (UTC)")
    updated_at: datetime = Field(description="When the request last changed (UTC)")
    paypal_batch_id: str | None = Field(None, description="PayPal's payout_batch_id once the batch was accepted")
    receipt_url: str | None = Field(None, description="A public receipt page anyone can open, once paid")
    run_id: int | None = Field(None, description="The Procurement Agent run behind the proposal: GET /agents/runs/{run_id}")
    needs_approval: bool = Field(False, description="The proposed amount is above the automatic limit and no admin approved it yet")


class ProcurementProjectOut(BaseModel):
    id: int = Field(description="Project id")
    title: str = Field(description="Project title")
    goal_cents: int = Field(description="Project funding goal, in cents")
    tags: list[str] = Field(description="Project tags the supplier can match")
    region: str | None = Field(description="Project region, null when hidden")


class ProcurementMilestoneOut(BaseModel):
    id: int = Field(description="Milestone id")
    title: str = Field(description="Milestone title")
    amount_cents: int = Field(description="Milestone amount, in cents")
    match_amount_cents: int = Field(description="Matching money added to the milestone, in cents")
    currency: str = Field(description="Milestone currency")
    status: MilestoneStatus = Field(description="Current milestone status")


class ProcurementRequestOut(ProcurementOut):
    model_config = _example(
        {
            **ProcurementOut.model_config["json_schema_extra"]["example"],
            "project": {"id": 1, "title": "Lanet Library", "goal_cents": 600000, "tags": ["books", "literacy"],
                        "region": "Nakuru"},
            "milestone": {"id": 7, "title": "Buy 40 books", "amount_cents": 3000, "match_amount_cents": 0,
                          "currency": "USD", "status": "open"},
            "project_title": "Lanet Library",
            "milestone_title": "Buy 40 books",
            "goal_cents": 600000,
            "tags": ["books", "literacy"],
            "region": "Nakuru",
        }
    )
    project: ProcurementProjectOut = Field(description="The requesting project")
    milestone: ProcurementMilestoneOut = Field(description="The milestone this purchase is for")
    project_title: str = Field(description="Project title, for a compact agent prompt")
    milestone_title: str = Field(description="Milestone title, for a compact agent prompt")
    goal_cents: int = Field(description="Project funding goal, in cents")
    tags: list[str] = Field(description="Project tags, for supplier matching")
    region: str | None = Field(description="Project region, for supplier matching")


class SupplierOut(BaseModel):
    model_config = _example(
        {
            "id": 1,
            "name": "Nakuru Books & Stationery",
            "categories": ["Education"],
            "tags": ["books", "literacy", "schools"],
            "region": "Nakuru",
        }
    )
    id: int = Field(description="Supplier id")
    name: str = Field(description="Supplier business name")
    categories: list[str | int] = Field(description="Category names or ids the supplier serves")
    tags: list[str | int] = Field(description="Project tags the supplier can supply")
    region: str | None = Field(description="Supplier's service area")


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
    # Only present when GET /admin/audit-log is called with include_hash=true.
    seq: int | None = None
    prev_hash: str | None = None
    hash: str | None = None


class AuditVerifyOut(BaseModel):
    model_config = _example(
        {
            "valid": True,
            "checked": 40,
            "first_bad_id": None,
            "first_bad_reason": None,
            "head_hash": "9f2c...",
        }
    )

    valid: bool
    checked: int
    first_bad_id: int | None = None
    first_bad_reason: str | None = None
    head_hash: str


class AgentStatusOut(BaseModel):
    model_config = _example(
        {
            "paused": True,
            "reason": "Investigating a Watchdog alert",
            "since": "2026-11-07T09:30:00Z",
            "updated_by": "admin",
        }
    )

    paused: bool
    reason: str | None = None
    since: datetime | None = None
    updated_by: str | None = None


class AgentToggleIn(BaseModel):
    model_config = _example({"reason": "Investigating a Watchdog alert"})

    reason: str = Field(min_length=1, max_length=500)


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
    refs: list[int] = Field(description="Ids of the rows involved (donations, payouts, milestones, ...)")


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


# --- Giving Agent subscriptions ------------------------------------------------------------


class SubscriptionIn(BaseModel):
    monthly_amount_cents: int = Field(ge=100, description="Whole dollars (multiples of 100), billed monthly")


class SubscriptionOut(BaseModel):
    model_config = _example(
        {
            "subscription_id": "I-BW452GLLEP1G",
            "donor_id": 1,
            "monthly_amount_cents": 2500,
            "currency": "USD",
            "status": "APPROVAL_PENDING",
            "approve_url": "https://www.sandbox.paypal.com/webapps/billing/subscriptions?ba_token=BA-2M539689T3856352J",
        }
    )
    subscription_id: str
    donor_id: int
    monthly_amount_cents: int
    currency: str
    status: str
    approve_url: str | None = Field(None, description="Send the donor here to approve (only while APPROVAL_PENDING)")


class DonorBoardRow(BaseModel):
    alias: str
    display_name: str | None = None
    is_me: bool = False
    given_cents: int
    match_unlocked_cents: int
    multiplier: float
    projects_backed: int
    categories_reached: int
    agent_given_cents: int
    impact_points: int


class DonorBoardOut(BaseModel):
    round_id: int
    currency: str
    rows: list[DonorBoardRow]


# --- Quadratic funding workflow: match preview, rounds, sponsors, applications, refunds ----


class MatchPreviewItem(BaseModel):
    project_id: int
    title: str
    match_before_cents: int = Field(description="The project's projected match now")
    match_after_cents: int = Field(description="Its projected match with your gift added")
    match_added_cents: int = Field(description="What your gift adds to its match (after minus before)")


class MatchPreviewOut(BaseModel):
    model_config = _example(
        {
            "round_id": 1,
            "amount_cents": 500,
            "currency": "USD",
            "items": [
                {"project_id": 4, "title": "New Reading Corner", "match_before_cents": 72000,
                 "match_after_cents": 75800, "match_added_cents": 3800}
            ],
        }
    )
    round_id: int
    amount_cents: int
    currency: str
    items: list[MatchPreviewItem] = Field(description="One per project asked about, biggest match added first")


class RoundIn(BaseModel):
    model_config = _example(
        {
            "name": "December round",
            "starts_at": "2026-12-01T00:00:00Z",
            "ends_at": "2026-12-15T18:00:00Z",
            "matching_pool_cents": 1000000,
            "project_cap_pct": 40.0,
            "floor_pct": 20.0,
            "per_person_cap_cents": 5000,
        }
    )
    name: str = Field(min_length=1, max_length=80)
    starts_at: datetime
    ends_at: datetime
    matching_pool_cents: int = Field(ge=0)
    project_cap_pct: float = Field(30.0, gt=0, le=100)
    floor_pct: float = Field(20.0, ge=0, le=100)
    per_person_cap_cents: int = Field(5000, gt=0)


class RoundUpdateIn(BaseModel):
    model_config = _example({"ends_at": "2026-12-20T18:00:00Z", "matching_pool_cents": 1500000})
    name: str | None = Field(None, min_length=1, max_length=80)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    matching_pool_cents: int | None = Field(None, ge=0)
    project_cap_pct: float | None = Field(None, gt=0, le=100)
    floor_pct: float | None = Field(None, ge=0, le=100)
    per_person_cap_cents: int | None = Field(None, gt=0)


class RoundResultRow(BaseModel):
    project_id: int
    title: str
    category: str
    raised_cents: int
    backer_count: int
    projected_match_cents: int = Field(description="The last projection before close (the live one while open)")
    final_match_cents: int | None = Field(description="Null until the round closes")
    capped: bool


class RoundResultsOut(BaseModel):
    model_config = _example(
        {
            "round_id": 1,
            "name": "November round",
            "status": "closed",
            "is_final": True,
            "currency": "USD",
            "matching_pool_cents": 1000000,
            "sponsored_cents": 25000,
            "matched_cents": 1000000,
            "unspent_cents": 0,
            "raised_cents": 51250,
            "backers": 29,
            "rows": [
                {"project_id": 1, "title": "Lanet Library", "category": "Education", "raised_cents": 20000,
                 "backer_count": 16, "projected_match_cents": 400000, "final_match_cents": 400000, "capped": True}
            ],
        }
    )
    round_id: int
    name: str
    status: RoundStatus
    is_final: bool
    currency: str
    matching_pool_cents: int = Field(description="Including what sponsors added during the round")
    sponsored_cents: int = Field(description="The part of the pool sponsors added through PayPal")
    matched_cents: int
    unspent_cents: int = Field(description="Pool not matched (caps and goals can leave some over)")
    raised_cents: int = Field(description="Gifts to projects during the round")
    backers: int = Field(description="People who gave to projects during the round")
    rows: list[RoundResultRow]


class SponsorOut(BaseModel):
    name: str = Field(description="As the sponsor asked to be credited, or Anonymous sponsor")
    amount_cents: int
    given_at: datetime


class SponsorsOut(BaseModel):
    model_config = _example(
        {
            "round_id": 1,
            "currency": "USD",
            "total_cents": 25000,
            "sponsors": [{"name": "Nakuru Rotary Club", "amount_cents": 25000, "given_at": "2026-11-04T09:30:00Z"}],
        }
    )
    round_id: int
    currency: str
    total_cents: int
    sponsors: list[SponsorOut] = Field(description="Largest first")


class ProjectApplicationOut(BaseModel):
    model_config = _example(
        {
            "project_id": 15,
            "status": "pending_review",
            "owner_token": "q3bX0n2R9w-example-token-k1",
            "milestone_ids": [41, 42, 43],
        }
    )
    project_id: int
    status: ProjectStatus
    owner_token: str = Field(description="Shown once: send it as X-Project-Token to upload documents and evidence")
    milestone_ids: list[int]


class EvidenceMilestone(BaseModel):
    milestone: MilestoneOut
    project_id: int
    project_title: str
    documents: list[DocumentOut]


class RefundIn(BaseModel):
    model_config = _example({"amount_cents": 1000, "reason": "Donor asked for a refund"})
    amount_cents: int | None = Field(None, gt=0, description="Leave out to refund everything not refunded yet")
    reason: str = Field(min_length=1, max_length=300)


class RefundOut(BaseModel):
    model_config = _example(
        {
            "donation_id": 4,
            "refund_id": "1JU08902781691411",
            "paypal_status": "COMPLETED",
            "amount_cents": 1000,
            "refunded_total_cents": 1000,
            "donation_status": "captured",
        }
    )
    donation_id: int
    refund_id: str
    paypal_status: str = Field(description="COMPLETED is booked now; PENDING is booked when PayPal's webhook confirms it")
    amount_cents: int
    refunded_total_cents: int
    donation_status: DonationStatus


class OwnerTokenOut(BaseModel):
    model_config = _example({"project_id": 1, "owner_token": "q3bX0n2R9w-example-token-k1"})
    project_id: int
    owner_token: str = Field(description="Shown once: the project's new X-Project-Token")


# --- Public agent trace: safe, read-only views ------------------------------------------------


class TraceStep(BaseModel):
    model_config = _example(
        {
            "seq": 1,
            "at": "2026-11-06T10:00:00Z",
            "actor": "giving-agent",
            "step": "request_donation",
            "tool": "request_checked_donation",
            "status": "ok",
            "title": "Asked the rules engine for a $5 gift",
            "input": {"project_id": 1, "amount_cents": 500},
            "result": {"status": "recorded"},
            "rule": "ok",
            "reason": "Three backers, 2% funded",
        }
    )

    seq: int = Field(description="Order of the step in the run; the API returns steps sorted by it")
    at: datetime | None = Field(None, description="When the step happened (UTC), when the agent recorded it")
    actor: str | None = Field(None, description="Agent that took the step, e.g. giving-agent")
    step: str = Field(description="Machine-readable step name, e.g. score or request_donation")
    tool: str | None = Field(None, description="Tool the agent called, e.g. search_projects, when it called one")
    status: str = Field("ok", description="ok, skipped, blocked or error")
    title: str = Field(description="One line describing what happened, safe to show on the public page")
    input: Any = Field(None, description="Safe summary of what the step saw; donor and payer fields are removed")
    result: Any = Field(None, description="Safe summary of what the step returned; donor and payer fields are removed")
    rule: str | None = Field(None, description="The rule that decided the step, when one did")
    reason: str | None = Field(None, description="Why, in plain words")
    ref: dict | None = Field(None, description="Optional pointer to a project, run or case")


class AgentRunChoice(BaseModel):
    model_config = _example({"project_id": 1, "title": "Lanet Library", "amount_cents": 500})

    project_id: int = Field(description="Project the agent chose")
    title: str | None = Field(None, description="Project title, joined for display")
    amount_cents: int = Field(description="What the agent asked the rules engine to give, in cents")


class AgentRunSkip(BaseModel):
    model_config = _example({"project_id": 2, "title": "Faith School Desks", "reason": "Already backed this month"})

    project_id: int | None = Field(None, description="Project the agent left out, when the decision names one")
    title: str | None = Field(None, description="Project title, joined for display")
    reason: str | None = Field(None, description="Why the agent skipped it")


class AgentRunOut(BaseModel):
    model_config = _example(
        {
            "id": 7,
            "run_at": "2026-11-06T10:00:00Z",
            "report_text": "I gave $5 to Lanet Library because three backers had already chosen it.",
            "trace": [
                {
                    "seq": 1,
                    "at": "2026-11-06T10:00:00Z",
                    "actor": "giving-agent",
                    "step": "request_donation",
                    "tool": "request_checked_donation",
                    "status": "ok",
                    "title": "Asked the rules engine for a $5 gift",
                    "input": {"project_id": 1, "amount_cents": 500},
                    "result": {"status": "recorded"},
                    "rule": "ok",
                    "reason": "Three backers, 2% funded",
                }
            ],
            "chosen": [{"project_id": 1, "title": "Lanet Library", "amount_cents": 500}],
            "skipped": [{"project_id": 2, "title": "Faith School Desks", "reason": "Already backed this month"}],
        }
    )

    id: int = Field(description="Agent run id")
    agent: str = Field("giving-agent", description="giving-agent or procurement-agent")
    run_at: datetime = Field(description="When the run happened (UTC)")
    report_text: str | None = Field(None, description="The run's report for the donor")
    trace: list[TraceStep] = Field(default_factory=list, description="Ordered steps the agent took")
    chosen: list[AgentRunChoice] = Field(default_factory=list, description="Projects the agent chose and the amounts it asked for")
    skipped: list[AgentRunSkip] = Field(default_factory=list, description="Projects the agent left out, with reasons")


class AgentActivityOut(BaseModel):
    model_config = _example(
        {
            "id": 42,
            "at": "2026-11-06T10:00:05Z",
            "actor": "giving-agent",
            "action": "checked_donation",
            "title": "Agent gift recorded for Lanet Library - Three backers, 2% funded",
            "status": "ok",
            "rule": None,
            "project_id": 1,
            "project_title": "Lanet Library",
            "run_id": 7,
        }
    )

    id: int = Field(description="Audit-log id; pass it as before_id to fetch older entries")
    at: datetime = Field(description="When the action was logged (UTC)")
    actor: str = Field(description="Who acted: giving-agent, milestone-agent, watchdog-agent or admin")
    action: str = Field(description="What was done, e.g. checked_donation, case_opened, payout_request")
    title: str = Field(description="Short human sentence for the public feed")
    status: str = Field(description="ok, pending, blocked or error")
    rule: str | None = Field(None, description="The rule that fired, when the result names one")
    project_id: int | None = Field(None, description="Project this action concerns, when known")
    project_title: str | None = Field(None, description="Project title, joined for display")
    run_id: int | None = Field(None, description="Giving Agent run this entry belongs to, when known")
