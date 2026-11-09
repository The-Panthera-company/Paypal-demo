"""Managed procurement: project owners request purchases, the agent chooses an eligible supplier,
and a PayPal Payouts batch pays that supplier directly.

A purchase is a release path for its milestone. The ordinary tranche route must refuse a
milestone with a requested, proposed, approved or paid procurement, so the same money cannot be
released twice. Only the batch acceptance (or a later payout webhook) books the expense and the
receipt, once.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import (
    Category,
    DocumentKind,
    LedgerEntry,
    LedgerType,
    Milestone,
    MilestoneStatus,
    Payout,
    Procurement,
    ProcurementStatus,
    Project,
    ProjectDocument,
    Supplier,
)
from app.schemas import ProcurementMilestoneOut, ProcurementOut, ProcurementProjectOut, ProcurementRequestOut

# Once any of these exist for a milestone, the tranche route must not release it.
MANAGED_STATUSES = (
    ProcurementStatus.requested,
    ProcurementStatus.proposed,
    ProcurementStatus.approved,
    ProcurementStatus.paid,
)
ACTIVE_STATUSES = (
    ProcurementStatus.requested,
    ProcurementStatus.proposed,
    ProcurementStatus.approved,
)


def managed_procurement(db: Session, milestone_id: int) -> Procurement | None:
    return db.scalar(
        select(Procurement)
        .where(Procurement.milestone_id == milestone_id, Procurement.status.in_(MANAGED_STATUSES))
        .order_by(Procurement.id.desc())
    )


def active_procurement(db: Session, milestone_id: int) -> Procurement | None:
    return db.scalar(
        select(Procurement)
        .where(Procurement.milestone_id == milestone_id, Procurement.status.in_(ACTIVE_STATUSES))
        .order_by(Procurement.id.desc())
    )


def procurement_out(db: Session, procurement: Procurement) -> ProcurementOut:
    supplier = db.get(Supplier, procurement.supplier_id) if procurement.supplier_id else None
    payout = db.get(Payout, procurement.payout_id) if procurement.payout_id else None
    receipt = db.get(ProjectDocument, procurement.receipt_document_id) if procurement.receipt_document_id else None
    limit = get_settings().procurement_auto_approve_cents
    return ProcurementOut(
        paypal_batch_id=payout.paypal_batch_id if payout else None,
        receipt_url=receipt.file_url if receipt else None,
        needs_approval=bool(procurement.amount_cents and procurement.amount_cents > limit and not procurement.admin_approved
                            and procurement.status in (ProcurementStatus.proposed, ProcurementStatus.failed)),
        id=procurement.id,
        project_id=procurement.project_id,
        milestone_id=procurement.milestone_id,
        description=procurement.description,
        quantity=procurement.quantity,
        max_amount_cents=procurement.max_amount_cents,
        currency=procurement.currency,
        status=procurement.status,
        supplier_id=procurement.supplier_id,
        supplier_name=supplier.name if supplier else None,
        amount_cents=procurement.amount_cents,
        line_items=procurement.line_items or [],
        rationale=procurement.rationale,
        admin_approved=procurement.admin_approved,
        approved_by=procurement.approved_by,
        approved_at=procurement.approved_at,
        payout_id=procurement.payout_id,
        receipt_document_id=procurement.receipt_document_id,
        error=procurement.error,
        created_at=procurement.created_at,
        updated_at=procurement.updated_at,
    )


def procurement_request_out(db: Session, procurement: Procurement) -> ProcurementRequestOut:
    base = procurement_out(db, procurement).model_dump()
    project = db.get(Project, procurement.project_id)
    milestone = db.get(Milestone, procurement.milestone_id)
    return ProcurementRequestOut(
        **base,
        project=ProcurementProjectOut(
            id=project.id,
            title=project.title,
            goal_cents=project.goal_amount,
            tags=project.tags or [],
            region=project.region,
        ),
        milestone=ProcurementMilestoneOut(
            id=milestone.id,
            title=milestone.title,
            amount_cents=milestone.amount,
            match_amount_cents=milestone.match_amount,
            currency=milestone.currency,
            status=milestone.status,
        ),
        project_title=project.title,
        milestone_title=milestone.title,
        goal_cents=project.goal_amount,
        tags=project.tags or [],
        region=project.region,
    )


def _values(items: list | None) -> set[str]:
    return {str(item).strip().casefold() for item in (items or []) if str(item).strip()}


def supplier_eligible(db: Session, supplier: Supplier, project: Project) -> bool:
    """Region must match (or be global), and at least one category or tag must match."""
    region = (supplier.region or "").strip().casefold()
    project_region = (project.region or "").strip().casefold()
    region_ok = not region or region in {"global", "any", "*"} or not project_region or region == project_region
    if not region_ok:
        return False

    category_name = db.scalar(select(Category.name).where(Category.id == project.category_id)) or ""
    project_labels = _values(project.tags) | {str(project.category_id).casefold(), category_name.strip().casefold()}
    supplier_labels = _values(supplier.categories) | _values(supplier.tags)
    return bool(supplier_labels & (project_labels | {"all", "any", "*"}))


def batch_url(settings: Settings, batch_id: str | None) -> str:
    base = settings.paypal_base_url.rstrip("/")
    return f"{base}/v1/payments/payouts/{batch_id or 'pending'}"


def mark_paid(
    db: Session,
    procurement: Procurement,
    *,
    batch_id: str | None,
    settings: Settings,
    when: datetime | None = None,
) -> bool:
    """Book the purchase, receipt and release once. Returns True when this call changed anything."""
    when = when or datetime.now(timezone.utc)
    changed = False

    if db.scalar(
        select(LedgerEntry.id).where(
            LedgerEntry.type == LedgerType.expense,
            LedgerEntry.procurement_id == procurement.id,
        )
    ) is None:
        db.add(
            LedgerEntry(
                type=LedgerType.expense,
                amount=procurement.amount_cents or 0,
                currency=procurement.currency,
                project_id=procurement.project_id,
                procurement_id=procurement.id,
                created_at=when,
            )
        )
        changed = True

    supplier = db.get(Supplier, procurement.supplier_id) if procurement.supplier_id else None
    if procurement.receipt_document_id is None:
        receipt = ProjectDocument(
            project_id=procurement.project_id,
            milestone_id=procurement.milestone_id,
            kind=DocumentKind.receipt,
            file_url=batch_url(settings, batch_id),
            extracted_fields={
                "supplier": supplier.name if supplier else None,
                "supplier_id": supplier.id if supplier else None,
                "amount_cents": procurement.amount_cents,
                "date": when.isoformat(),
                "batch_id": batch_id,
                "line_items": procurement.line_items or [],
            },
            flags=[],
        )
        db.add(receipt)
        db.flush()
        procurement.receipt_document_id = receipt.id
        changed = True

    milestone = db.get(Milestone, procurement.milestone_id)
    if milestone is not None and milestone.status != MilestoneStatus.released:
        milestone.status = MilestoneStatus.released
        changed = True

    if procurement.status != ProcurementStatus.paid:
        procurement.status = ProcurementStatus.paid
        procurement.error = None
        procurement.updated_at = when
        changed = True
    return changed


def sync_from_payout(db: Session, payout: Payout, settings: Settings) -> None:
    """An admin send, payout webhook or refresh may be the only proof a purchase was paid."""
    for item in payout.items or []:
        procurement_id = item.get("procurement_id")
        if procurement_id is None:
            continue
        if not payout.paypal_batch_id or item.get("status") in ("FAILED", "RETURNED", "BLOCKED"):
            continue
        procurement = db.get(Procurement, int(procurement_id))
        if procurement is not None:
            mark_paid(db, procurement, batch_id=payout.paypal_batch_id, settings=settings)
