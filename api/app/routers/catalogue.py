"""Public catalogue: categories, projects, their stories and funding history."""

from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.auth import check_owner_token, new_owner_token
from app.config import Settings, get_settings
from app.db import get_db
from app.models import (
    CategoryAllocation,
    Category,
    DocumentKind,
    Donation,
    DonationStatus,
    MatchResult,
    Milestone,
    MilestoneStatus,
    PayoutAccount,
    Project,
    ProjectDocument,
    ProjectStatus,
    Round,
    RoundStatus,
)
from app.schemas import (
    CategoryOut,
    DocumentIn,
    DocumentOut,
    FundingPoint,
    MilestoneOut,
    ErrorOut,
    ProjectApplicationIn,
    ProjectApplicationOut,
    ProjectDetail,
    ProjectSummary,
    StoryOut,
)

router = APIRouter(tags=["catalogue"])

# Statuses donors can see and give to.
LISTED = (ProjectStatus.verified, ProjectStatus.active)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    counts = dict(
        db.execute(
            select(Project.category_id, func.count()).where(Project.status.in_(LISTED)).group_by(Project.category_id)
        ).all()
    )
    return [
        CategoryOut(id=c.id, name=c.name, project_count=counts.get(c.id, 0))
        for c in db.scalars(select(Category).order_by(Category.name))
    ]


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(
    category_id: int | None = None,
    cause: str | None = None,
    beneficiary_group: str | None = Query(None, description="children, adults or elderly"),
    region: str | None = None,
    exclude_tags: str | None = Query(None, description="Comma-separated tags to leave out"),
    q: str | None = Query(None, description="Case-insensitive title search"),
    sort: str = Query("urgency", pattern="^(urgency|newest|fewest_backers)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Project).where(Project.status.in_(LISTED))
    if category_id is not None:
        stmt = stmt.where(Project.category_id == category_id)
    if cause:
        stmt = stmt.where(Project.cause == cause)
    if beneficiary_group:
        stmt = stmt.where(Project.beneficiary_group == beneficiary_group)
    if region:
        stmt = stmt.where(Project.region == region, Project.hide_location.is_(False))
    if q:
        stmt = stmt.where(Project.title.ilike(f"%{q}%"))
    stmt = stmt.order_by(Project.urgency.desc() if sort == "urgency" else Project.created_at.desc(), Project.id)
    projects = list(db.scalars(stmt))

    # Tags are JSON, so exclusions are applied here rather than in SQL.
    excluded = {t.strip() for t in (exclude_tags or "").split(",") if t.strip()}
    if excluded:
        projects = [p for p in projects if not excluded.intersection(p.tags or [])]

    summaries = _summaries(db, projects)
    if sort == "fewest_backers":
        summaries.sort(key=lambda s: (s.backer_count, s.id))
    return summaries[offset : offset + limit]


@router.get("/projects/{project_id}", response_model=ProjectDetail, responses={404: {}})
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None or project.status not in LISTED + (ProjectStatus.completed,):
        raise HTTPException(404, detail={"error": "PROJECT_NOT_FOUND", "message": "No such project"})
    return project_detail(db, project)


def milestone_out(m: Milestone) -> MilestoneOut:
    return MilestoneOut(
        id=m.id,
        seq=m.seq,
        title=m.title,
        amount_cents=m.amount,
        match_amount_cents=m.match_amount,
        currency=m.currency,
        due_date=m.due_date,
        status=m.status,
    )


def project_detail(db: Session, project: Project) -> ProjectDetail:
    milestones = db.scalars(select(Milestone).where(Milestone.project_id == project.id).order_by(Milestone.seq))
    return ProjectDetail(
        **_summaries(db, [project])[0].model_dump(),
        summary=project.summary,
        verified_at=project.verified_at,
        milestones=[milestone_out(m) for m in milestones],
    )


@router.get("/projects/{project_id}/funding-history", response_model=list[FundingPoint])
def funding_history(project_id: int, db: Session = Depends(get_db)):
    """Cumulative amount raised and backers per day, from captured donations (category shares included)."""
    rows = sorted(project_gifts(db, [project_id]), key=lambda r: r[3])
    by_day: dict = defaultdict(int)
    backers_by_day: dict = {}
    seen: set = set()
    for _, donor_id, amount, captured_at in rows:
        day = captured_at.date()
        by_day[day] += amount
        seen.add(donor_id)
        backers_by_day[day] = len(seen)
    total = 0
    points = []
    for day in sorted(by_day):
        total += by_day[day]
        points.append(FundingPoint(date=day, raised_cents=total, backer_count=backers_by_day[day]))
    return points


@router.get("/projects/{project_id}/stories", response_model=list[StoryOut], responses={404: {}})
def project_stories(project_id: int, db: Session = Depends(get_db)):
    """Impact updates: released milestones with their evidence (receipts, photos), newest first."""
    from app.reports import stories  # app.reports imports this module

    project = db.get(Project, project_id)
    if project is None or project.status not in LISTED + (ProjectStatus.completed,):
        raise HTTPException(404, detail={"error": "PROJECT_NOT_FOUND", "message": "No such project"})
    return stories(db, [project_id])


EVIDENCE = (DocumentKind.receipt, DocumentKind.photo)


def document_out(d: ProjectDocument) -> DocumentOut:
    return DocumentOut(id=d.id, project_id=d.project_id, milestone_id=d.milestone_id, kind=d.kind,
                       file_url=d.file_url, extracted_fields=d.extracted_fields, flags=d.flags or [])


@router.post(
    "/projects",
    response_model=ProjectApplicationOut,
    status_code=201,
    responses={422: {"model": ErrorOut, "description": "Unknown category, or milestones that don't add up to the goal"}},
)
def apply_project(body: ProjectApplicationIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """A project owner applies with a milestone plan. The project starts as pending_review (not
    public) until an admin verifies it. Keep the owner_token: it is shown once and authorises
    document and evidence uploads."""
    if db.get(Category, body.category_id) is None:
        raise HTTPException(422, detail={"error": "CATEGORY_NOT_FOUND", "message": "No such category"})
    planned = sum(m.amount_cents for m in body.milestones)
    if planned != body.goal_cents:
        raise HTTPException(422, detail={"error": "MILESTONES_DONT_ADD_UP",
                                         "message": f"Milestones add up to {planned} cents, the goal is {body.goal_cents}"})
    token, token_hash = new_owner_token()
    project = Project(
        title=body.title, facilitator=body.facilitator, summary=body.summary, category_id=body.category_id,
        tags=body.tags, cause=body.cause, beneficiary_group=body.beneficiary_group, region=body.region,
        hide_location=body.hide_location, goal_amount=body.goal_cents, urgency=body.urgency,
        currency=settings.currency, status=ProjectStatus.pending_review, owner_token_hash=token_hash,
    )
    db.add(project)
    db.flush()
    milestones = [
        Milestone(project_id=project.id, seq=n, title=m.title, amount=m.amount_cents, currency=settings.currency,
                  due_date=m.due_date)
        for n, m in enumerate(body.milestones, start=1)
    ]
    db.add_all(milestones)
    if body.payout_email:
        db.add(PayoutAccount(project_id=project.id, paypal_email=body.payout_email))
    audit.write(db, actor="project-owner", action="project_applied", inputs={"project_id": project.id},
                rule_result="pending_review", reason=f"{body.title}: {len(milestones)} milestones")
    db.commit()
    return ProjectApplicationOut(project_id=project.id, status=project.status, owner_token=token,
                                 milestone_ids=[m.id for m in milestones])


@router.post(
    "/projects/{project_id}/documents",
    response_model=DocumentOut,
    status_code=201,
    responses={401: {"model": ErrorOut}, 404: {"model": ErrorOut}, 409: {"model": ErrorOut}},
)
def add_document(
    project_id: int,
    body: DocumentIn,
    x_project_token: str | None = Header(None, description="The owner_token from the application"),
    db: Session = Depends(get_db),
):
    """Registration, plan, receipt or photo, as a link to the hosted file. A receipt or photo with a
    milestone_id is evidence for that tranche: the milestone moves to evidence_submitted, where the
    Milestone Agent picks it up (GET /internal/milestones/evidence)."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, detail={"error": "PROJECT_NOT_FOUND", "message": "No such project"})
    check_owner_token(x_project_token, project.owner_token_hash)
    milestone = None
    if body.milestone_id is not None:
        milestone = db.get(Milestone, body.milestone_id)
        if milestone is None or milestone.project_id != project.id:
            raise HTTPException(404, detail={"error": "MILESTONE_NOT_FOUND", "message": "No such milestone on this project"})
        if body.kind in EVIDENCE:
            if milestone.status not in (MilestoneStatus.open, MilestoneStatus.evidence_submitted):
                raise HTTPException(409, detail={"error": "MILESTONE_NOT_OPEN",
                                                 "message": f"Milestone is {milestone.status.value}"})
            milestone.status = MilestoneStatus.evidence_submitted
    doc = ProjectDocument(project_id=project.id, milestone_id=body.milestone_id, kind=body.kind, file_url=body.file_url,
                          flags=[])
    db.add(doc)
    db.flush()
    audit.write(db, actor="project-owner", action="document_added",
                inputs={"project_id": project.id, "document_id": doc.id, "milestone_id": body.milestone_id},
                rule_result=body.kind.value,
                reason="Evidence submitted" if milestone is not None and body.kind in EVIDENCE else None)
    db.commit()
    return document_out(doc)


def project_gifts(db: Session, project_ids: list[int]) -> list[tuple[int, int | None, int, datetime]]:
    """(project_id, donor_id, cents, captured_at) for money that reached these projects: captured
    project and agent gifts, plus each captured category donation's share. Refunds drop out."""
    direct = select(Donation.project_id, Donation.donor_id, Donation.amount, Donation.captured_at).where(
        Donation.project_id.in_(project_ids), Donation.status == DonationStatus.captured
    )
    shares = (
        select(CategoryAllocation.project_id, Donation.donor_id, CategoryAllocation.amount, Donation.captured_at)
        .join(Donation, Donation.id == CategoryAllocation.donation_id)
        .where(CategoryAllocation.project_id.in_(project_ids), Donation.status == DonationStatus.captured)
    )
    return [tuple(r) for r in db.execute(direct).all() + db.execute(shares).all()]


def _summaries(db: Session, projects: list[Project]) -> list[ProjectSummary]:
    if not projects:
        return []
    ids = [p.id for p in projects]
    raised_by: dict[int, int] = defaultdict(int)
    backers_by: dict[int, set] = defaultdict(set)
    for pid, donor_id, amount, _ in project_gifts(db, ids):
        raised_by[pid] += amount
        backers_by[pid].add(donor_id)
    totals = {pid: (raised_by[pid], len(backers_by[pid])) for pid in raised_by}
    open_round = db.scalar(select(Round.id).where(Round.status == RoundStatus.open))
    projected = (
        dict(
            db.execute(
                select(MatchResult.project_id, MatchResult.final_amount).where(
                    MatchResult.round_id == open_round, MatchResult.is_final.is_(False), MatchResult.project_id.in_(ids)
                )
            ).all()
        )
        if open_round
        else {}
    )
    names = dict(db.execute(select(Category.id, Category.name)).all())
    return [
        ProjectSummary(
            id=p.id,
            title=p.title,
            facilitator=p.facilitator,
            category_id=p.category_id,
            category=names.get(p.category_id, ""),
            tags=p.tags or [],
            cause=p.cause,
            beneficiary_group=p.beneficiary_group,
            region=None if p.hide_location else p.region,
            urgency=p.urgency,
            status=p.status,
            matching_frozen=p.matching_frozen,
            goal_cents=p.goal_amount,
            raised_cents=totals.get(p.id, (0, 0))[0] or 0,
            backer_count=totals.get(p.id, (0, 0))[1],
            projected_match_cents=projected.get(p.id, 0),
            currency=p.currency,
        )
        for p in projects
    ]
