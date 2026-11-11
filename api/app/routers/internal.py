"""Endpoints for the agent service. Agents never hold PayPal credentials: every money action
comes through here, and the core API re-checks the rules before anything moves.

Every call that changes something writes an audit-log line with its inputs, rule result and reason.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, kill_switch, payouts, procurement as procurement_service
from app.auth import require_internal
from app.config import Settings, get_settings
from app.db import get_db
from app.kill_switch import ensure_agents_running, require_agents_running
from app.mandates import check_gift
from app.models import (
    ProjectDocument,
    CaseStatus,
    Donation,
    DonationStatus,
    Donor,
    LedgerEntry,
    LedgerType,
    Mandate,
    MandateRun,
    Milestone,
    MilestoneStatus,
    Payout,
    Procurement,
    ProcurementStatus,
    Project,
    Supplier,
    TargetType,
    WatchdogCase,
)
from app.money import to_paypal
from app.paypal import PayPalClient, get_paypal
from app.routers.donations import mark_captured
from app.routers.catalogue import document_out, milestone_out
from app.routers.donors import mandate_out, run_out
from app.schemas import (
    EvidenceMilestone,
    ActiveMandate,
    AgentStatusOut,
    AuditIn,
    AuditOut,
    CaseIn,
    CaseOut,
    CheckedDonationIn,
    CheckedDonationOut,
    DonationEventOut,
    ErrorOut,
    MandateRunIn,
    MandateRunOut,
    PayoutRequestIn,
    PayoutRequestOut,
    ProcurementOut,
    ProcurementProposeIn,
    ProcurementRunIn,
    ProcurementRequestOut,
    SupplierOut,
)

router = APIRouter(prefix="/internal", tags=["internal (agents)"], dependencies=[Depends(require_internal)])

NOT_FOUND = {404: {"model": ErrorOut}}


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"error": code, "message": message})


def case_out(c: WatchdogCase) -> CaseOut:
    return CaseOut(
        id=c.id,
        project_id=c.project_id,
        rule=c.rule,
        evidence=c.evidence,
        status=c.status,
        frozen_at=c.frozen_at,
        resolved_by=c.resolved_by,
        created_at=c.created_at,
    )


def _invalid_evidence(message: str) -> HTTPException:
    return _error(422, "INVALID_EVIDENCE", message)


def _validate_collusion_evidence(db: Session, evidence: dict) -> None:
    """Validate a collusion cluster: Donor.id integers only, plus an optional graph.

    PayPal payer ids are strings; they are not donor ids and must never reach the matching
    engine, which merges confirmed clusters by Donor.id.
    """
    donor_ids = evidence.get("donor_ids")
    if not isinstance(donor_ids, list) or len(donor_ids) < 2:
        raise _invalid_evidence("collusion_cluster needs donor_ids with at least two Donor.id integers")
    if any(type(value) is not int for value in donor_ids):
        raise _invalid_evidence("donor_ids must be Donor.id integers, not PayPal payer ids")
    unique = set(donor_ids)
    if len(unique) < 2:
        raise _invalid_evidence("collusion_cluster needs at least two different donor_ids")
    found = set(db.scalars(select(Donor.id).where(Donor.id.in_(unique))).all())
    missing = sorted(unique - found)
    if missing:
        raise _invalid_evidence(f"Unknown donor_ids: {missing}")

    graph = evidence.get("graph")
    if graph is None:
        return
    if not isinstance(graph, dict):
        raise _invalid_evidence("graph must be an object")

    nodes = graph.get("nodes")
    if nodes is not None:
        if not isinstance(nodes, list):
            raise _invalid_evidence("graph.nodes must be a list")
        for node in nodes:
            if not isinstance(node, dict) or not {"id", "type", "label"} <= node.keys():
                raise _invalid_evidence("Each graph node needs id, type and label")
            if type(node["id"]) not in (int, str) or node["id"] == "":
                raise _invalid_evidence("A graph node id must be a non-empty integer or string")
            if not isinstance(node["type"], str) or not node["type"].strip():
                raise _invalid_evidence("A graph node type must be a non-empty string")
            if not isinstance(node["label"], str) or not node["label"].strip():
                raise _invalid_evidence("A graph node label must be a non-empty string")

    edges = graph.get("edges")
    if edges is not None:
        if not isinstance(edges, list):
            raise _invalid_evidence("graph.edges must be a list")
        for edge in edges:
            if not isinstance(edge, dict) or not {"source", "target", "weight"} <= edge.keys():
                raise _invalid_evidence("Each graph edge needs source, target and weight")
            if type(edge["source"]) not in (int, str) or edge["source"] == "":
                raise _invalid_evidence("A graph edge source must be a non-empty integer or string")
            if type(edge["target"]) not in (int, str) or edge["target"] == "":
                raise _invalid_evidence("A graph edge target must be a non-empty integer or string")
            if type(edge["weight"]) not in (int, float):
                raise _invalid_evidence("A graph edge weight must be a number")


@router.get("/status", response_model=AgentStatusOut)
def internal_status(db: Session = Depends(get_db)):
    """The agent service checks this before starting a run. Available while paused."""
    return kill_switch.status(db)


@router.get("/mandates/active", response_model=list[ActiveMandate])
def active_mandates(db: Session = Depends(get_db)):
    """Mandates for the Giving Agent's run, with each donor's remaining funded balance."""
    mandates = db.scalars(select(Mandate).where(Mandate.active.is_(True)).order_by(Mandate.id))
    return [ActiveMandate(**mandate_out(db, m).model_dump()) for m in mandates]


@router.get("/donation-events", response_model=list[DonationEventOut])
def donation_events(
    since: datetime = Query(..., description="Only donations captured at or after this ISO timestamp (UTC)."),
    limit: int = Query(500, ge=1, le=1000, description="Most events to return."),
    db: Session = Depends(get_db),
):
    """Watchdog's event feed: captured and refunded donations since a timestamp, newest first.

    donor_id and owner_donor_id are internal Donor.id integers, never PayPal payer ids.
    """
    rows = db.execute(
        select(Donation, Donor, Project.owner_id)
        .join(Donor, Donor.id == Donation.donor_id, isouter=True)
        .join(Project, Project.id == Donation.project_id, isouter=True)
        .where(
            Donation.status.in_((DonationStatus.captured, DonationStatus.refunded)),
            Donation.captured_at.is_not(None),
            Donation.captured_at >= since,
        )
        .order_by(Donation.captured_at.desc(), Donation.id.desc())
        .limit(limit)
    )
    return [
        DonationEventOut(
            donation_id=donation.id,
            project_id=donation.project_id,
            donor_id=donation.donor_id,
            status=donation.status,
            amount_cents=donation.amount,
            captured_at=donation.captured_at,
            donor_created_at=donor.created_at if donor else None,
            owner_donor_id=owner_id,
            is_guest=bool(donor and donor.is_guest),
        )
        for donation, donor, owner_id in rows.all()
    ]


@router.post(
    "/mandate-runs",
    response_model=MandateRunOut,
    status_code=201,
    responses={**NOT_FOUND, 409: {"model": ErrorOut}},
    dependencies=[Depends(require_agents_running)],
)
def record_mandate_run(body: MandateRunIn, db: Session = Depends(get_db)):
    """The Giving Agent records its candidates, scores and choices before requesting donations."""
    if db.get(Mandate, body.mandate_id) is None:
        raise _error(404, "MANDATE_NOT_FOUND", "No such mandate")
    run = MandateRun(mandate_id=body.mandate_id, decisions=body.decisions, report_text=body.report_text)
    db.add(run)
    db.flush()
    audit.write(
        db,
        actor="giving-agent",
        action="mandate_run",
        inputs={"mandate_id": body.mandate_id, "mandate_run_id": run.id},
        rule_result="recorded",
        reason=body.report_text,
    )
    db.commit()
    return run_out(run)


_STATUS = {
    DonationStatus.captured: "recorded",
    DonationStatus.created: "awaiting_donor_approval",
    DonationStatus.failed: "rejected",
}


@router.post(
    "/checked-donations",
    response_model=CheckedDonationOut,
    responses={**NOT_FOUND, 409: {"model": ErrorOut}},
    dependencies=[Depends(require_agents_running)],
)
def checked_donation(body: CheckedDonationIn, db: Session = Depends(get_db)):
    """Re-checks budget, per-project max, exclusions and project status, then records the gift
    (target_type AGENT) or parks it for the donor's approval. Never calls PayPal.

    Asking twice for the same run and project returns the first answer, so agent retries are safe.
    """
    run = db.get(MandateRun, body.mandate_run_id)
    if run is None:
        raise _error(404, "MANDATE_RUN_NOT_FOUND", "Record the run with POST /internal/mandate-runs first")
    earlier = db.scalar(
        select(Donation).where(Donation.mandate_run_id == run.id, Donation.project_id == body.project_id)
    )
    if earlier is not None:
        return CheckedDonationOut(
            status=_STATUS.get(earlier.status, "rejected"),
            donation_id=earlier.id,
            rule_result="duplicate",
            reason="Already requested in this run",
        )

    mandate = db.get(Mandate, run.mandate_id)
    project = db.get(Project, body.project_id)
    rule, why = check_gift(db, mandate, project, body.amount_cents)
    inputs = {"mandate_run_id": run.id, "project_id": body.project_id, "amount_cents": body.amount_cents}
    if rule != "ok":
        audit.write(db, actor="giving-agent", action="checked_donation", inputs=inputs, rule_result=rule,
                    reason=f"{why}. Agent's reason: {body.reason}")
        db.commit()
        return CheckedDonationOut(status="rejected", donation_id=None, rule_result=rule, reason=why)

    donation = Donation(
        donor_id=mandate.donor_id,
        target_type=TargetType.AGENT,
        project_id=project.id,
        amount=body.amount_cents,
        currency=mandate.currency,
        mandate_run_id=run.id,
    )
    db.add(donation)
    db.flush()
    if body.amount_cents > mandate.approval_threshold:
        status = "awaiting_donor_approval"
        why = f"Above the donor's {mandate.currency} {to_paypal(mandate.approval_threshold, mandate.currency)} approval threshold"
    else:
        ensure_agents_running(db)  # defense in depth: the switch may have flipped mid-request
        mark_captured(db, donation, {})  # an internal move from the funded balance: no PayPal call
        status = "recorded"
    audit.write(db, actor="giving-agent", action="checked_donation", inputs={**inputs, "donation_id": donation.id},
                rule_result=status, reason=body.reason)
    db.commit()
    return CheckedDonationOut(status=status, donation_id=donation.id, rule_result="ok", reason=why)


@router.post(
    "/watchdog/cases",
    response_model=CaseOut,
    status_code=201,
    responses={
        **NOT_FOUND,
        409: {"model": ErrorOut},
        422: {"model": ErrorOut, "description": "Invalid collusion_cluster evidence"},
    },
    dependencies=[Depends(require_agents_running)],
)
def open_case(body: CaseIn, db: Session = Depends(get_db)):
    """Watchdog rule hit: opens a case and freezes the project's matching (not its donations).

    collusion_cluster accepts Donor.id integers in evidence["donor_ids"] and an optional
    nodes/edges graph. The same rule firing again on a project with an open case returns that
    case instead of a new one. Opening or clearing a case never merges donors; only an admin's
    confirm decision does.
    """
    project = db.get(Project, body.project_id)
    if project is None:
        raise _error(404, "PROJECT_NOT_FOUND", "No such project")
    if body.rule == "collusion_cluster":
        _validate_collusion_evidence(db, body.evidence)
    existing = db.scalar(
        select(WatchdogCase).where(
            WatchdogCase.project_id == project.id,
            WatchdogCase.rule == body.rule,
            WatchdogCase.status == CaseStatus.open,
        )
    )
    if existing is not None:
        return case_out(existing)
    case = WatchdogCase(
        project_id=project.id, rule=body.rule, evidence=body.evidence, frozen_at=datetime.now(timezone.utc)
    )
    project.matching_frozen = True
    db.add(case)
    db.flush()
    audit.write(db, actor="watchdog-agent", action="case_opened", inputs={"case_id": case.id, **body.model_dump()},
                rule_result=body.rule, reason="Matching frozen until an admin resolves the case")
    db.commit()
    return case_out(case)


def release_milestone(db: Session, paypal: PayPalClient, milestone: Milestone) -> Payout:
    """Mark a tranche released, book it, and send it through PayPal Payouts.

    The release is committed before PayPal is called, so a PayPal failure leaves a pending payout
    (send it again from the admin console) rather than undoing the release.
    """
    milestone.status = MilestoneStatus.released
    db.add(
        LedgerEntry(
            type=LedgerType.tranche,
            amount=milestone.amount + milestone.match_amount,
            currency=milestone.currency,
            project_id=milestone.project_id,
        )
    )
    payout = payouts.create_for_milestone(db, milestone)
    db.commit()
    payouts.send(db, paypal, payout)
    return payout


@router.post(
    "/payout-requests",
    response_model=PayoutRequestOut,
    responses={**NOT_FOUND, 409: {"model": ErrorOut}},
    dependencies=[Depends(require_agents_running)],
)
def payout_request(
    body: PayoutRequestIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    paypal: PayPalClient = Depends(get_paypal),
):
    """Milestone Agent: all checks pass, no open Watchdog case and the tranche (including its match)
    is at most MILESTONE_AUTO_RELEASE_CENTS -> released and sent through PayPal Payouts;
    otherwise held for an admin."""
    milestone = db.get(Milestone, body.milestone_id)
    if milestone is None:
        raise _error(404, "MILESTONE_NOT_FOUND", "No such milestone")
    if procurement_service.managed_procurement(db, milestone.id) is not None:
        raise _error(409, "PROCUREMENT_MANAGED", "This milestone is paid through a managed procurement")
    if milestone.status not in (MilestoneStatus.open, MilestoneStatus.evidence_submitted):
        raise _error(409, "MILESTONE_NOT_OPEN", f"Milestone is already {milestone.status.value}")

    problems = [name for name, ok in body.checks.model_dump().items() if not ok]
    total = milestone.amount + milestone.match_amount
    if total > settings.milestone_auto_release_cents:
        problems.append(f"above_threshold ({total} > {settings.milestone_auto_release_cents})")
    open_case = db.scalar(
        select(WatchdogCase.id).where(
            WatchdogCase.project_id == milestone.project_id, WatchdogCase.status == CaseStatus.open
        )
    )
    if open_case is not None:
        problems.append(f"open_watchdog_case ({open_case})")

    payout = None
    if problems:
        milestone.status = MilestoneStatus.held
        status, reason = "held_for_admin", "Held: " + ", ".join(problems)
    else:
        ensure_agents_running(db)  # defense in depth: check again before PayPal
        payout = release_milestone(db, paypal, milestone)
        status, reason = "released", "All checks passed, below threshold"
        if errors := {i.get("error") for i in payout.items if i.get("error")}:
            reason += f"; payout not sent yet: {', '.join(sorted(errors))}"
    audit.write(
        db,
        actor="milestone-agent",
        action="payout_request",
        inputs={"milestone_id": milestone.id, "checks": body.checks.model_dump(), "amount_cents": total},
        rule_result=status,
        reason=f"{reason}. Summary: {body.summary}",
    )
    db.commit()
    return PayoutRequestOut(status=status, payout_id=payout.id if payout else None, reason=reason)


@router.get("/procurement/requests", response_model=list[ProcurementRequestOut])
def procurement_requests(db: Session = Depends(get_db)):
    """Purchase requests waiting for a supplier proposal, with the project, milestone, goal, tags
    and region the Procurement Agent uses to choose an eligible supplier."""
    rows = list(
        db.scalars(
            select(Procurement)
            .where(Procurement.status.in_((ProcurementStatus.requested, ProcurementStatus.proposed)))
            .order_by(Procurement.id)
        )
    )
    return [procurement_service.procurement_request_out(db, p) for p in rows]


@router.get(
    "/procurement/suppliers",
    response_model=list[SupplierOut],
    responses={404: {"model": ErrorOut}},
)
def procurement_suppliers(project_id: int, db: Session = Depends(get_db)):
    """Active suppliers whose categories or tags and service region match the project, with each
    one's unit price and reliability (null when unknown) to compare. The PayPal email is never
    returned: the agent doesn't need it."""
    project = db.get(Project, project_id)
    if project is None:
        raise _error(404, "PROJECT_NOT_FOUND", "No such project")
    suppliers = db.scalars(select(Supplier).where(Supplier.active.is_(True)).order_by(Supplier.name))
    return [
        SupplierOut(
            id=s.id,
            name=s.name,
            categories=list(s.categories or []),
            tags=list(s.tags or []),
            region=s.region,
            unit_amount_cents=s.unit_amount_cents,
            reliability=s.reliability,
        )
        for s in suppliers
        if procurement_service.supplier_eligible(db, s, project)
    ]


PROCUREMENT_AGENT = "procurement-agent"


@router.post("/procurement/runs", response_model=MandateRunOut, status_code=201,
             dependencies=[Depends(require_agents_running)])
def record_procurement_run(body: ProcurementRunIn, db: Session = Depends(get_db)):
    """The Procurement Agent records its run (the trace of what it looked at and why it chose a
    supplier) before proposing. The run belongs to no donor's mandate; its trace is public at
    GET /agents/runs/{id}, so keep supplier emails and personal details out of it."""
    run = MandateRun(mandate_id=None, agent=PROCUREMENT_AGENT, decisions=body.decisions, report_text=body.report_text)
    db.add(run)
    db.flush()
    audit.write(db, actor=PROCUREMENT_AGENT, action="procurement_run", inputs={"run_id": run.id},
                rule_result="recorded", reason=body.report_text)
    db.commit()
    return run_out(run)


@router.post(
    "/procurement/{procurement_id}/propose",
    response_model=ProcurementOut,
    responses={**NOT_FOUND, 409: {"model": ErrorOut},
                422: {"model": ErrorOut, "description": "Supplier is not eligible, or the price is above the request or milestone"}},
    dependencies=[Depends(require_agents_running)],
)
def propose_procurement(procurement_id: int, body: ProcurementProposeIn, db: Session = Depends(get_db)):
    """Choose an active, eligible supplier and a price within the request and the milestone.
    A procurement gets one proposal; asking twice is a conflict. Pass the run_id from
    POST /internal/procurement/runs so the purchase links to its trace."""
    procurement = db.get(Procurement, procurement_id)
    if procurement is None:
        raise _error(404, "PROCUREMENT_NOT_FOUND", "No such procurement")
    if procurement.status != ProcurementStatus.requested:
        raise _error(409, "ALREADY_PROPOSED", f"Procurement is {procurement.status.value}")
    supplier = db.get(Supplier, body.supplier_id)
    project = db.get(Project, procurement.project_id)
    if supplier is None or not supplier.active or project is None or not procurement_service.supplier_eligible(db, supplier, project):
        raise _error(422, "INVALID_SUPPLIER", "Supplier is unknown, inactive or not eligible for this project")
    if body.amount_cents > procurement.max_amount_cents:
        raise _error(422, "AMOUNT_ABOVE_REQUEST",
                     f"{body.amount_cents} is more than the {procurement.max_amount_cents} requested")
    milestone = db.get(Milestone, procurement.milestone_id)
    total = milestone.amount + milestone.match_amount
    if body.amount_cents > total:
        raise _error(422, "AMOUNT_ABOVE_MILESTONE", f"{body.amount_cents} is more than the milestone's {total}")
    if body.run_id is not None:
        run = db.get(MandateRun, body.run_id)
        if run is None or run.agent != PROCUREMENT_AGENT:
            raise _error(422, "RUN_NOT_FOUND", "Record the run with POST /internal/procurement/runs first")

    procurement.run_id = body.run_id
    procurement.supplier_id = supplier.id
    procurement.amount_cents = body.amount_cents
    procurement.line_items = body.line_items
    procurement.rationale = body.rationale
    procurement.status = ProcurementStatus.proposed
    audit.write(
        db,
        actor="procurement-agent",
        action="procurement_proposed",
        inputs={"procurement_id": procurement.id, "project_id": procurement.project_id, "supplier_id": supplier.id,
                "amount_cents": body.amount_cents, "run_id": body.run_id},
        rule_result="proposed",
        reason=body.rationale,
    )
    db.commit()
    return procurement_service.procurement_out(db, procurement)


@router.post(
    "/procurement/{procurement_id}/pay",
    response_model=ProcurementOut,
    responses={**NOT_FOUND, 409: {"model": ErrorOut},
                422: {"model": ErrorOut, "description": "The supplier is inactive, or the price is above the milestone"}},
    dependencies=[Depends(require_agents_running)],
)
def pay_procurement(
    procurement_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    paypal: PayPalClient = Depends(get_paypal),
):
    """Pay the proposed supplier through one deterministic PayPal Payouts batch. Above the
    automatic limit it answers 409 APPROVAL_REQUIRED until an admin approves. Paying twice
    returns the first result; a PayPal refusal leaves a failed, retryable batch."""
    procurement = db.get(Procurement, procurement_id)
    if procurement is None:
        raise _error(404, "PROCUREMENT_NOT_FOUND", "No such procurement")
    if procurement.status == ProcurementStatus.paid:
        return procurement_service.procurement_out(db, procurement)
    if procurement.status not in (ProcurementStatus.proposed, ProcurementStatus.approved, ProcurementStatus.failed):
        raise _error(409, "PROCUREMENT_NOT_PROPOSED", f"Procurement is {procurement.status.value}")
    if not procurement.amount_cents:
        raise _error(409, "PROCUREMENT_NOT_PROPOSED", "The procurement has no supplier proposal")
    if procurement.amount_cents > settings.procurement_auto_approve_cents and not (
        procurement.admin_approved or procurement.status == ProcurementStatus.approved
    ):
        raise _error(409, "APPROVAL_REQUIRED",
                     f"{procurement.amount_cents} is above the {settings.procurement_auto_approve_cents} automatic limit")
    supplier = db.get(Supplier, procurement.supplier_id)
    if supplier is None or not supplier.active:
        raise _error(422, "INVALID_SUPPLIER", "The supplier is unknown or inactive")
    milestone = db.get(Milestone, procurement.milestone_id)
    total = milestone.amount + milestone.match_amount
    if procurement.amount_cents > total:
        raise _error(422, "AMOUNT_ABOVE_MILESTONE", f"{procurement.amount_cents} is more than the milestone's {total}")

    payout = db.get(Payout, procurement.payout_id) if procurement.payout_id else None
    if payout is None:
        payout = Payout(
            sender_batch_id=f"procurement-{procurement.id}-{procurement.currency}",
            currency=procurement.currency,
            items=[
                {
                    "project_id": procurement.project_id,
                    "milestone_id": procurement.milestone_id,
                    "procurement_id": procurement.id,
                    "amount_cents": procurement.amount_cents,
                    "receiver": supplier.paypal_email,
                    "sender_item_id": f"procurement-{procurement.id}",
                    "status": "NEW",
                }
            ],
        )
        db.add(payout)
        db.flush()
        procurement.payout_id = payout.id
        db.commit()  # keep the deterministic batch id before talking to PayPal

    ensure_agents_running(db)
    payouts.send(db, paypal, payout)
    if payout.paypal_batch_id:
        procurement_service.mark_paid(
            db, procurement, batch_id=payout.paypal_batch_id, settings=settings
        )
        audit.write(
            db,
            actor="procurement-agent",
            action="procurement_paid",
            inputs={"procurement_id": procurement.id, "project_id": procurement.project_id, "payout_id": payout.id,
                    "amount_cents": procurement.amount_cents, "batch_id": payout.paypal_batch_id,
                    "run_id": procurement.run_id},
            rule_result="paid",
            reason=f"Paid {supplier.name} from the milestone",
        )
    else:
        procurement.status = ProcurementStatus.failed
        procurement.error = next((i.get("error") for i in payout.items or [] if i.get("error")), "PAYOUT_FAILED")
        audit.write(
            db,
            actor="procurement-agent",
            action="procurement_failed",
            inputs={"procurement_id": procurement.id, "project_id": procurement.project_id, "payout_id": payout.id,
                    "run_id": procurement.run_id},
            rule_result=procurement.error,
            reason="PayPal did not accept the supplier batch; retry the same procurement",
        )
    db.commit()
    return procurement_service.procurement_out(db, procurement)


@router.post("/audit", response_model=AuditOut, status_code=201, response_model_exclude_unset=True)
def write_audit(body: AuditIn, db: Session = Depends(get_db)):
    """Agents log decisions that don't go through another endpoint (e.g. a skipped project)."""
    entry = audit.write(db, **body.model_dump())
    db.commit()
    return AuditOut(**body.model_dump(), id=entry.id, created_at=entry.created_at)


@router.get("/milestones/evidence", response_model=list[EvidenceMilestone])
def evidence_queue(db: Session = Depends(get_db)):
    """Milestone Agent: tranches whose owners submitted evidence, oldest first, with all their
    documents. Check them, then POST /internal/payout-requests."""
    milestones = list(db.scalars(select(Milestone).where(Milestone.status == MilestoneStatus.evidence_submitted)
                                 .order_by(Milestone.id)))
    titles = dict(db.execute(select(Project.id, Project.title).where(Project.id.in_({m.project_id for m in milestones}))).all())
    docs = list(db.scalars(select(ProjectDocument).where(ProjectDocument.milestone_id.in_([m.id for m in milestones]))
                           .order_by(ProjectDocument.id)))
    return [
        EvidenceMilestone(milestone=milestone_out(m), project_id=m.project_id, project_title=titles.get(m.project_id, ""),
                          documents=[document_out(d) for d in docs if d.milestone_id == m.id])
        for m in milestones
    ]
