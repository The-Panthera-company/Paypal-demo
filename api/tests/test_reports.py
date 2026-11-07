"""Impact stories, the donor report, and the demo seed."""

import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import projections, reconciliation, reports
from app.db import Base
from app.engine import run_round
from app.models import (
    Donation,
    DonationStatus,
    Donor,
    Mandate,
    MandateRun,
    Milestone,
    Project,
    ProjectDocument,
    Round,
    RoundStatus,
    TargetType,
)
from scripts import seed_dev

ADMIN = {"Authorization": "Bearer admin-test-token"}
INTERNAL = {"Authorization": "Bearer internal-test-token"}
PASS = {"receipt_total_within_10pct": True, "supplier_matches_plan": True, "photo_not_duplicate": True, "dated_in_window": True}


def _release(client, db_session_factory, project_id=1, match=0, evidence=("receipt", "photo")):
    with db_session_factory() as db:
        m = Milestone(project_id=project_id, seq=1, title="40 books delivered", amount=3000, match_amount=match, currency="USD")
        db.add(m)
        db.flush()
        for kind in evidence:
            db.add(ProjectDocument(project_id=project_id, milestone_id=m.id, kind=kind, file_url=f"https://files.example.com/{kind}.jpg"))
        db.add(ProjectDocument(project_id=project_id, milestone_id=m.id, kind="plan", file_url="https://files.example.com/plan.pdf"))
        db.commit()
        milestone_id = m.id
    client.put(f"/admin/projects/{project_id}/payout-account", headers=ADMIN, json={"paypal_email": "lanet@example.com"})
    r = client.post("/internal/payout-requests", headers=INTERNAL, json={"milestone_id": milestone_id, "checks": PASS, "summary": "ok"})
    assert r.json()["status"] == "released", r.text
    return milestone_id


# --- stories ------------------------------------------------------------------------------


def test_released_milestone_becomes_a_story(client, db_session_factory):
    assert client.get("/projects/1/stories").json() == []
    milestone_id = _release(client, db_session_factory, match=500)
    r = client.get("/projects/1/stories")
    assert r.status_code == 200 and "X-Stub" not in r.headers
    [story] = r.json()
    assert (story["milestone_id"], story["title"]) == (milestone_id, "40 books delivered")
    assert story["evidence_urls"] == ["https://files.example.com/receipt.jpg", "https://files.example.com/photo.jpg"]
    assert "USD 35.00 released to Lanet Library, including USD 5.00 of matching" in story["body"]


def test_open_milestones_are_not_stories_and_unlisted_projects_404(client, db_session_factory):
    with db_session_factory() as db:
        db.add(Milestone(project_id=1, seq=1, title="Not yet", amount=100, currency="USD"))
        db.commit()
    assert client.get("/projects/1/stories").json() == []
    assert client.get("/projects/3/stories").status_code == 404  # pending review


# --- donor report -------------------------------------------------------------------------


def _round(db_session_factory):
    now = datetime.now(timezone.utc)
    with db_session_factory() as db:
        r = Round(name="R1", starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=1), matching_pool=1000,
                  currency="USD", status=RoundStatus.open, project_cap_pct=100)
        db.add(r)
        db.commit()
        return r.id


def _pay(client, **body):
    out = client.post("/donations/orders", json={"target_type": "PROJECT", "project_id": 1, "amount_cents": 2500} | body).json()
    client.post(f"/donations/orders/{out['order_id']}/capture")
    return out["donation_id"]


def test_report_lists_gifts_and_shares_match_by_square_root(client, db_session_factory):
    round_id = _round(db_session_factory)
    mine = _pay(client)  # donor 1 (the sandbox payer): 25 USD to Lanet Library
    with db_session_factory() as db:  # another backer: 100 USD to the same project
        other = Donor()
        db.add(other)
        db.flush()
        db.add(Donation(donor_id=other.id, target_type=TargetType.PROJECT, project_id=1, amount=10_000, currency="USD",
                        status=DonationStatus.captured, captured_at=datetime.now(timezone.utc)))
        db.commit()
        projections.refresh(db, db.get(Round, round_id))
    match = client.get(f"/rounds/{round_id}/leaderboard").json()["rows"][0]
    assert match["project_id"] == 1

    report = client.get("/donors/1/report").json()
    assert report["total_given_cents"] == 2500
    [gift] = report["gifts"]
    assert (gift["donation_id"], gift["project_title"], gift["via"]) == (mine, "Lanet Library", "PROJECT")
    # 100 USD is capped at 50 per person: shares are sqrt(25) : sqrt(50).
    expected = round(match["match_cents"] * math.sqrt(2500) / (math.sqrt(2500) + math.sqrt(5000)))
    assert gift["match_unlocked_cents"] == expected == report["match_unlocked_cents"]


def test_report_leaves_out_top_ups_and_names_category_gifts(client):
    _pay(client, target_type="AGENT", project_id=None)
    _pay(client, target_type="CATEGORY", project_id=None, category_id=1, rule="equal")
    report = client.get("/donors/1/report").json()
    assert [(g["via"], g["project_title"]) for g in report["gifts"]] == [("CATEGORY", "Split across 2 projects")]
    assert report["total_given_cents"] == 2500


def test_report_includes_updates_from_backed_projects_and_agent_report(client, db_session_factory):
    _pay(client)
    _release(client, db_session_factory)
    with db_session_factory() as db:
        mandate = Mandate(donor_id=1, monthly_budget=1000, currency="USD", categories=[1], excluded_tags=[],
                          per_project_max=500, approval_threshold=500)
        db.add(mandate)
        db.flush()
        db.add(MandateRun(mandate_id=mandate.id, report_text="USD 3.00 to Lanet Library: few backers."))
        db.commit()
    report = client.get("/donors/1/report").json()
    assert [u["title"] for u in report["updates"]] == ["40 books delivered"]
    assert report["agent_report"] == "USD 3.00 to Lanet Library: few backers."


def test_report_shows_refunds_but_does_not_count_them(client):
    donation_id = _pay(client)
    refund = {"id": "REF-1", "amount": {"currency_code": "USD", "value": "25.00"},
              "links": [{"rel": "up", "href": "https://api.sandbox.paypal.com/v2/payments/captures/CAP-ORDER1"}]}
    signed = {"paypal-transmission-sig": "s", "paypal-transmission-id": "t", "paypal-transmission-time": "n",
              "paypal-cert-url": "https://api.sandbox.paypal.com/c", "paypal-auth-algo": "SHA256withRSA"}
    client.post("/webhooks/paypal", headers=signed, json={"id": "WH-1", "event_type": "PAYMENT.CAPTURE.REFUNDED", "resource": refund})
    report = client.get("/donors/1/report").json()
    assert [(g["donation_id"], g["status"]) for g in report["gifts"]] == [(donation_id, "refunded")]
    assert report["total_given_cents"] == 0


def test_report_unknown_donor(client):
    assert client.get("/donors/99/report").json()["detail"]["error"] == "DONOR_NOT_FOUND"


# --- seed ---------------------------------------------------------------------------------


def test_seed_reproduces_the_worked_example_and_is_rerunnable(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(seed_dev, "engine", engine)
    monkeypatch.setattr(seed_dev, "SessionLocal", factory)
    seed_dev.main()
    seed_dev.main()  # again: nothing duplicated

    with factory() as db:
        projects = list(db.scalars(select(Project)))
        assert len(projects) == len(seed_dev.PROJECTS)
        assert len({p.category_id for p in projects}) == 4 and all(p.tags and p.facilitator for p in projects)
        assert db.scalar(select(Donor).order_by(Donor.id)).id == 1  # the demo donor
        mandate = db.get(Mandate, seed_dev.DEMO_MANDATE_ID)
        assert mandate is not None and mandate.active and mandate.donor_id == 1
        assert len(db.scalars(select(Mandate).where(Mandate.active.is_(True))).all()) == 1
        assert len(db.scalars(select(Donation)).all()) == 29
        round_ = db.scalar(select(Round))
        assert round_.project_cap_pct == 40
        titles = {p.id: p.title for p in projects}
        match = {titles[r.project_id]: (r.final_amount, r.capped) for r in run_round(db, round_) if r.final_amount}
    assert match == {
        "Lanet Library": (400_000, True),
        "Kaptembwo Desks": (302_400, False),
        "Girls' STEM Club": (225_600, False),
        "New Reading Corner": (72_000, False),
    }

    with factory() as db:
        milestones = list(db.scalars(select(Milestone)))
        per_project = {p.id: [m for m in milestones if m.project_id == p.id] for p in projects}
        assert all(2 <= len(ms) <= 4 for ms in per_project.values()) and all(m.due_date for m in milestones)
        assert sorted(m.status.value for m in milestones if m.status.value != "open") == [
            "evidence_submitted", "held", "released", "released"]
        # Seeded releases are paid in the database only: nothing to send, nothing wrong.
        assert reconciliation.report(db)["issues"] == []
        backed = [p.id for p in projects if p.title in ("Kaptembwo Desks", "Girls' STEM Club")]
        assert [s.title for s in reports.stories(db, backed)] == ["First 10 desks delivered", "Science kits for 30 girls"]
