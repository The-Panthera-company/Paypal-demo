"""Impact stories and the donor report ("where your money went").

There is no stories table: a story is a released milestone, told from its own records. Its
evidence is the milestone's receipts and photos; its date is when its payout batch was created
(the release), so stories appear as soon as a tranche goes out.

Matching a donor unlocked is shared the quadratic-funding way: within a round, a project's match
is divided among its backers in proportion to the square root of what each counted for (after the
per-person cap, guests at half weight), because that is how each person moved the score.
"""

import math
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.allocation import GUEST_WEIGHT
from app.models import (
    CategoryAllocation,
    Donation,
    DonationStatus,
    Donor,
    Mandate,
    MandateRun,
    MatchResult,
    Milestone,
    MilestoneStatus,
    Payout,
    Project,
    ProjectDocument,
    Round,
    TargetType,
)
from app.money import to_paypal
from app.schemas import DonorReport, ReportGift, StoryOut

EVIDENCE = ("receipt", "photo")


def _aware(at: datetime) -> datetime:
    return at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at


def stories(db: Session, project_ids: list[int], limit: int = 50) -> list[StoryOut]:
    """Released milestones of these projects as impact updates, newest first."""
    milestones = list(db.scalars(select(Milestone).where(
        Milestone.project_id.in_(project_ids), Milestone.status == MilestoneStatus.released)))
    if not milestones:
        return []
    ids = {m.id for m in milestones}
    released_at: dict[int, datetime] = {}
    for p in db.scalars(select(Payout).order_by(Payout.id)):
        for item in p.items or []:
            if item.get("milestone_id") in ids:
                released_at.setdefault(item["milestone_id"], _aware(p.created_at))
    evidence: dict[int, list[str]] = defaultdict(list)
    for doc in db.scalars(select(ProjectDocument).where(ProjectDocument.milestone_id.in_(ids)).order_by(ProjectDocument.id)):
        if doc.kind.value in EVIDENCE:
            evidence[doc.milestone_id].append(doc.file_url)
    titles = dict(db.execute(select(Project.id, Project.title).where(Project.id.in_(project_ids))).all())

    out = []
    for m in milestones:
        total = to_paypal(m.amount + m.match_amount, m.currency)
        body = f"{m.currency} {total} released to {titles.get(m.project_id, 'the project')}"
        if m.match_amount:
            body += f", including {m.currency} {to_paypal(m.match_amount, m.currency)} of matching"
        body += ", after its receipts and photos were checked." if evidence[m.id] else ", after its evidence was checked."
        out.append(StoryOut(
            id=m.id, project_id=m.project_id, milestone_id=m.id, title=m.title, body=body,
            evidence_urls=evidence[m.id], created_at=released_at.get(m.id, datetime.now(timezone.utc)),
        ))
    return sorted(out, key=lambda s: (s.created_at, s.id), reverse=True)[:limit]


def _match_unlocked(db: Session, donor_id: int, gifts: list[Donation]) -> dict[int, int]:
    """Cents of matching each of the donor's project gifts unlocked, per donation id."""
    out = {g.id: 0 for g in gifts}
    for round_ in db.scalars(select(Round)):
        start, end = _aware(round_.starts_at), _aware(round_.ends_at)
        mine = [g for g in gifts if g.captured_at and start <= _aware(g.captured_at) < end]
        if not mine:
            continue
        results = list(db.scalars(select(MatchResult).where(MatchResult.round_id == round_.id)))
        final = {r.project_id: r.final_amount for r in results if r.is_final}
        match = final or {r.project_id: r.final_amount for r in results if not r.is_final}
        for project_id in {g.project_id for g in mine}:
            if not match.get(project_id):
                continue
            backers = db.execute(
                select(Donation.donor_id, Donation.amount, Donor.is_guest)
                .join(Donor, Donor.id == Donation.donor_id, isouter=True)
                .where(Donation.project_id == project_id, Donation.status == DonationStatus.captured,
                       Donation.target_type.in_((TargetType.PROJECT, TargetType.AGENT)),
                       Donation.captured_at >= round_.starts_at, Donation.captured_at < round_.ends_at)
            ).all()
            totals: dict = defaultdict(int)
            guest: dict = {}
            for backer, amount, is_guest in backers:
                totals[backer] += amount
                guest[backer] = bool(is_guest)
            roots = {b: (GUEST_WEIGHT if guest[b] else 1.0) * math.sqrt(min(t, round_.per_person_cap))
                     for b, t in totals.items()}
            share = match[project_id] * roots.get(donor_id, 0) / (sum(roots.values()) or 1)
            gifts_here = [g for g in mine if g.project_id == project_id]
            given = sum(g.amount for g in gifts_here)
            for g in gifts_here:
                out[g.id] += round(share * g.amount / given)
    return out


def donor_report(db: Session, donor: Donor, currency: str) -> DonorReport:
    donations = list(db.scalars(
        select(Donation)
        .where(Donation.donor_id == donor.id,
               Donation.status.in_((DonationStatus.captured, DonationStatus.pending, DonationStatus.refunded)))
        .order_by(Donation.id.desc())
    ))
    # Agent budget top-ups are money waiting to be given, not gifts.
    gifts = [d for d in donations if not (d.target_type == TargetType.AGENT and d.project_id is None)]
    project_gifts = [d for d in gifts if d.project_id is not None and d.status == DonationStatus.captured]
    unlocked = _match_unlocked(db, donor.id, project_gifts)

    titles = dict(db.execute(select(Project.id, Project.title)).all())
    shares: dict[int, list[int]] = defaultdict(list)  # category donation -> projects it reached
    for donation_id, project_id in db.execute(select(CategoryAllocation.donation_id, CategoryAllocation.project_id).where(
            CategoryAllocation.donation_id.in_([d.id for d in gifts]))):
        shares[donation_id].append(project_id)

    rows = []
    for d in gifts:
        title = titles.get(d.project_id) if d.project_id else None
        if d.target_type == TargetType.CATEGORY:
            title = f"Split across {len(shares[d.id])} projects" if shares[d.id] else "Category gift"
        rows.append(ReportGift(
            donation_id=d.id, project_id=d.project_id, project_title=title, via=d.target_type,
            amount_cents=d.amount, status=d.status, match_unlocked_cents=unlocked.get(d.id, 0),
        ))

    backed = {d.project_id for d in gifts if d.project_id} | {p for ps in shares.values() for p in ps}
    mandate = db.scalar(select(Mandate).where(Mandate.donor_id == donor.id))
    run = (db.scalar(select(MandateRun).where(MandateRun.mandate_id == mandate.id, MandateRun.report_text.is_not(None))
                     .order_by(MandateRun.id.desc())) if mandate else None)
    return DonorReport(
        donor_id=donor.id,
        currency=currency,
        total_given_cents=sum(d.amount for d in gifts if d.status == DonationStatus.captured),
        match_unlocked_cents=sum(unlocked.values()),
        gifts=rows,
        updates=stories(db, sorted(backed), limit=20) if backed else [],
        agent_report=run.report_text if run else None,
    )
