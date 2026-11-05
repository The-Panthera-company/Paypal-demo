"""Matching rounds: the leaderboard, match previews, final results and sponsors."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import engine, projections, round_close
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Donation, DonationStatus, MatchResult, PoolContribution, Project, Round, RoundStatus, TargetType
from app.routers.catalogue import LISTED, _summaries
from app.donor_board import donor_board
from app.schemas import (
    DonorBoardOut,
    ErrorOut,
    LeaderboardOut,
    LeaderboardRow,
    MatchPreviewItem,
    MatchPreviewOut,
    RoundOut,
    RoundResultRow,
    RoundResultsOut,
    SponsorOut,
    SponsorsOut,
)

router = APIRouter(prefix="/rounds", tags=["rounds"])


def _out(r: Round) -> RoundOut:
    return RoundOut(
        id=r.id,
        name=r.name,
        starts_at=r.starts_at,
        ends_at=r.ends_at,
        matching_pool_cents=r.matching_pool,
        currency=r.currency,
        project_cap_pct=r.project_cap_pct,
        floor_pct=r.floor_pct,
        per_person_cap_cents=r.per_person_cap,
        status=r.status,
    )


def _round_or_404(db: Session, round_id: int) -> Round:
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise HTTPException(404, detail={"error": "ROUND_NOT_FOUND", "message": "No such round"})
    return round_


@router.get("", response_model=list[RoundOut])
def list_rounds(db: Session = Depends(get_db)):
    """Every round, newest first: scheduled, open, closing and closed."""
    return [_out(r) for r in db.scalars(select(Round).order_by(Round.starts_at.desc(), Round.id.desc()))]


@router.get("/current", response_model=RoundOut, responses={404: {}})
def current_round(db: Session = Depends(get_db)):
    if round_close.open_due(db):  # the background loop may be asleep (Render free plan)
        db.commit()
    r = db.scalar(select(Round).where(Round.status.in_((RoundStatus.open, RoundStatus.closing))))
    if r is None:
        raise HTTPException(404, detail={"error": "NO_OPEN_ROUND", "message": "No round is open"})
    return _out(r)


@router.get("/{round_id}/leaderboard", response_model=LeaderboardOut, responses={404: {"model": ErrorOut}})
def leaderboard(round_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """Projected match while the round is open (recomputed every 5 minutes); final once the round closes.

    Projects whose matching the Watchdog froze are listed with a match of 0 and `matching_frozen: true`.
    """
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise HTTPException(404, detail={"error": "ROUND_NOT_FOUND", "message": "No such round"})

    is_final = projections.computed_at(db, round_id, is_final=True) is not None
    if not is_final:
        projections.refresh_if_stale(db, round_, settings.projection_interval_seconds or 300)
    results = {
        m.project_id: m
        for m in db.scalars(
            select(MatchResult).where(MatchResult.round_id == round_id, MatchResult.is_final.is_(is_final))
        )
    }
    projects = list(
        db.scalars(
            select(Project).where(
                Project.id.in_(results)
                | (Project.status.in_(LISTED) & Project.matching_frozen.is_(True))
            )
        )
    )
    summaries = {s.id: s for s in _summaries(db, projects)}
    rows = sorted(
        (
            LeaderboardRow(
                rank=0,
                project_id=p.id,
                title=p.title,
                category=summaries[p.id].category,
                backer_count=summaries[p.id].backer_count,
                raised_cents=summaries[p.id].raised_cents,
                score=results[p.id].score if p.id in results else 0.0,
                floor_cents=results[p.id].floor_amount if p.id in results else 0,
                crowd_cents=results[p.id].crowd_amount if p.id in results else 0,
                match_cents=results[p.id].final_amount if p.id in results else 0,
                capped=results[p.id].capped if p.id in results else False,
                matching_frozen=p.matching_frozen,
            )
            for p in projects
        ),
        key=lambda r: (-r.match_cents, -r.score, r.project_id),
    )
    for rank, row in enumerate(rows, start=1):
        row.rank = rank
    return LeaderboardOut(
        round_id=round_id,
        is_final=is_final,
        computed_at=projections.computed_at(db, round_id, is_final) or datetime.now(timezone.utc),
        currency=round_.currency,
        rows=rows,
    )


@router.get("/{round_id}/donors", response_model=DonorBoardOut, responses={404: {"model": ErrorOut}})
def donor_leaderboard(round_id: int, me: int | None = None, db: Session = Depends(get_db)):
    """Donor ladders for the round: given, matching unlocked, multiplier, reach, agent-given, impact points.
    Names only for donors who opted in; `me` marks the caller's own row (demo: no login yet)."""
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise HTTPException(404, detail={"error": "ROUND_NOT_FOUND", "message": "No such round"})
    return donor_board(db, round_, me)


@router.get(
    "/{round_id}/match-preview",
    response_model=MatchPreviewOut,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut, "description": "Invalid amount"}},
)
def match_preview(
    round_id: int,
    amount_cents: int = Query(description="The gift you are thinking of, in cents"),
    project_id: int | None = Query(None, description="One project; leave out for every project in the round"),
    donor_id: int | None = Query(None, description="Count your earlier gifts (the square root and per-person cap use your total)"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """What a gift would add to a project's match: computed with and without it, on the round's
    live inputs. Small gifts to projects with few backers add the most; a gift beyond the per-person
    cap adds nothing. An estimate: other gifts before the round closes change the final match."""
    round_ = _round_or_404(db, round_id)
    if round_.status != RoundStatus.open:
        raise HTTPException(409, detail={"error": "ROUND_NOT_OPEN", "message": f"The round is {round_.status.value}"})
    if not settings.min_donation_cents <= amount_cents <= settings.max_donation_cents:
        raise HTTPException(422, detail={
            "error": "AMOUNT_OUT_OF_RANGE",
            "message": f"Amount must be between {settings.min_donation_cents} and {settings.max_donation_cents} cents",
        })
    results = engine.preview(db, round_, amount_cents, [project_id] if project_id is not None else None, donor_id)
    if project_id is not None and project_id not in results:
        raise HTTPException(404, detail={"error": "PROJECT_NOT_MATCHED",
                                         "message": "The project isn't listed, or its matching is frozen"})
    titles = dict(db.execute(select(Project.id, Project.title).where(Project.id.in_(results))).all())
    items = sorted(
        (MatchPreviewItem(project_id=pid, title=titles.get(pid, ""), match_before_cents=before,
                          match_after_cents=after, match_added_cents=after - before)
         for pid, (before, after) in results.items()),
        key=lambda i: (-i.match_added_cents, i.project_id),
    )
    return MatchPreviewOut(round_id=round_.id, amount_cents=amount_cents, currency=round_.currency, items=items)


@router.get("/{round_id}/results", response_model=RoundResultsOut, responses={404: {"model": ErrorOut}})
def round_results(round_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """The round's outcome: each project's last projected match next to its final match (null until
    close), and the totals: pool (with sponsors), matched, unspent, raised and backers."""
    round_ = _round_or_404(db, round_id)
    if round_.status in (RoundStatus.open, RoundStatus.closing):
        projections.refresh_if_stale(db, round_, settings.projection_interval_seconds or 300)
    rows = list(db.scalars(select(MatchResult).where(MatchResult.round_id == round_id)))
    projected = {r.project_id: r for r in rows if not r.is_final}
    final = {r.project_id: r for r in rows if r.is_final}
    is_final = bool(final) or round_.status == RoundStatus.closed
    projects = list(db.scalars(select(Project).where(Project.id.in_(set(projected) | set(final)))))
    summaries = {s.id: s for s in _summaries(db, projects)}

    gifts = db.execute(
        select(Donation.donor_id, Donation.amount).where(
            Donation.status == DonationStatus.captured,
            Donation.target_type.in_((TargetType.PROJECT, TargetType.CATEGORY, TargetType.AGENT)),
            Donation.captured_at >= round_.starts_at, Donation.captured_at < round_.ends_at,
            ~((Donation.target_type == TargetType.AGENT) & Donation.project_id.is_(None)),
        )
    ).all()
    matched = sum(r.final_amount for r in (final or projected).values())
    out_rows = sorted(
        (
            RoundResultRow(
                project_id=p.id, title=p.title, category=summaries[p.id].category,
                raised_cents=summaries[p.id].raised_cents, backer_count=summaries[p.id].backer_count,
                projected_match_cents=projected[p.id].final_amount if p.id in projected else 0,
                final_match_cents=final[p.id].final_amount if p.id in final else (0 if is_final else None),
                capped=(final.get(p.id) or projected.get(p.id)).capped,
            )
            for p in projects
        ),
        key=lambda r: (-(r.final_match_cents if r.final_match_cents is not None else r.projected_match_cents), r.project_id),
    )
    return RoundResultsOut(
        round_id=round_.id, name=round_.name, status=round_.status, is_final=is_final, currency=round_.currency,
        matching_pool_cents=round_.matching_pool, sponsored_cents=_sponsored(db, round_.id), matched_cents=matched,
        unspent_cents=max(round_.matching_pool - matched, 0), raised_cents=sum(a for _, a in gifts),
        backers=len({d for d, _ in gifts if d is not None}), rows=out_rows,
    )


def _sponsored(db: Session, round_id: int) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(Donation.amount), 0))
        .join(PoolContribution, PoolContribution.donation_id == Donation.id)
        .where(PoolContribution.round_id == round_id, PoolContribution.added_to_pool.is_(True))
    )


@router.get("/{round_id}/sponsors", response_model=SponsorsOut, responses={404: {"model": ErrorOut}})
def round_sponsors(round_id: int, db: Session = Depends(get_db)):
    """Who added to the round's matching pool through PayPal (a POOL donation), largest first."""
    round_ = _round_or_404(db, round_id)
    rows = db.execute(
        select(PoolContribution.sponsor_name, Donation.amount, Donation.captured_at)
        .join(Donation, Donation.id == PoolContribution.donation_id)
        .where(PoolContribution.round_id == round_id, PoolContribution.added_to_pool.is_(True))
        .order_by(Donation.amount.desc(), Donation.id)
    ).all()
    sponsors = [SponsorOut(name=name or "Anonymous sponsor", amount_cents=amount, given_at=at) for name, amount, at in rows]
    return SponsorsOut(round_id=round_.id, currency=round_.currency, total_cents=sum(s.amount_cents for s in sponsors),
                       sponsors=sponsors)
