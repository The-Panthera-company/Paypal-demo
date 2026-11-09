"""Watchdog cases, milestone payout requests, admin review and project verification."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.engine import run_round
from app.models import (
    CaseStatus,
    Donation,
    DonationStatus,
    Donor,
    LedgerEntry,
    Milestone,
    Project,
    Round,
    RoundStatus,
    TargetType,
    WatchdogCase,
)

ADMIN = {"Authorization": "Bearer admin-test-token"}
INTERNAL = {"Authorization": "Bearer internal-test-token"}
PASS = {"receipt_total_within_10pct": True, "supplier_matches_plan": True, "photo_not_duplicate": True, "dated_in_window": True}


def _case(client, project_id=1, rule="new_payer_burst", donor_ids=(1, 2), evidence=None):
    body = {"project_id": project_id, "rule": rule,
            "evidence": evidence if evidence is not None else {"donor_ids": list(donor_ids)}}
    r = client.post("/internal/watchdog/cases", headers=INTERNAL, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _donors(db_session_factory, *ids):
    with db_session_factory() as db:
        db.add_all([Donor(id=donor_id) for donor_id in ids])
        db.commit()


def _resolve(client, case_id, **body):
    return client.post(f"/admin/cases/{case_id}/resolve", headers=ADMIN, json={"action": "clear"} | body)


def _frozen(db_session_factory, project_id=1):
    with db_session_factory() as db:
        p = db.get(Project, project_id)
        return p.matching_frozen, p.status.value


def test_case_freezes_matching_not_donations(client, db_session_factory):
    case = _case(client)
    assert case["status"] == "open" and case["frozen_at"]
    assert _frozen(db_session_factory) == (True, "active")
    # Donations still go through.
    r = client.post("/donations/orders", json={"target_type": "PROJECT", "project_id": 1, "amount_cents": 500})
    assert r.status_code == 200
    # Same rule again: same case.
    assert _case(client)["id"] == case["id"]
    assert [c["id"] for c in client.get("/admin/cases", headers=ADMIN).json()] == [case["id"]]


def test_clear_resumes_matching_only_when_no_case_left(client, db_session_factory):
    a = _case(client, rule="new_payer_burst")
    b = _case(client, rule="refund_spike")
    assert _resolve(client, a["id"]).json()["status"] == "cleared"
    assert _frozen(db_session_factory)[0] is True  # b still open
    assert _resolve(client, b["id"], action="confirm").json()["status"] == "confirmed"
    assert _frozen(db_session_factory) == (False, "active")
    assert _resolve(client, b["id"]).json()["detail"]["error"] == "CASE_ALREADY_RESOLVED"


def test_confirm_and_remove_delists_project(client, db_session_factory):
    case = _case(client)
    assert _resolve(client, case["id"], action="clear", remove_project=True).status_code == 422
    assert _resolve(client, case["id"], action="confirm", remove_project=True).status_code == 200
    assert _frozen(db_session_factory) == (True, "frozen")
    assert client.get("/projects/1").status_code == 404


def test_case_errors_and_auth(client):
    body = {"project_id": 99, "rule": "owner_donation", "evidence": {}}
    assert client.post("/internal/watchdog/cases", json=body).status_code == 401
    assert client.post("/internal/watchdog/cases", headers=INTERNAL, json=body).status_code == 404
    assert _resolve(client, 99).status_code == 404


def test_collusion_cluster_opens_graph_case_without_auto_confirming(client, db_session_factory):
    _donors(db_session_factory, 10, 11)
    evidence = {
        "donor_ids": [10, 11],
        "graph": {
            "nodes": [
                {"id": 10, "type": "donor", "label": "Donor 3FA2C1"},
                {"id": 11, "type": "donor", "label": "Donor 81B4D0"},
                {"id": 1, "type": "project", "label": "Lanet Library"},
            ],
            "edges": [
                {"source": 10, "target": 1, "weight": 1},
                {"source": 11, "target": 1, "weight": 1},
            ],
        },
    }
    case = _case(client, rule="collusion_cluster", evidence=evidence)
    assert case["rule"] == "collusion_cluster" and case["status"] == "open"
    assert case["evidence"] == evidence
    assert _frozen(db_session_factory) == (True, "active")
    with db_session_factory() as db:
        stored = db.get(WatchdogCase, case["id"])
        assert stored.status == CaseStatus.open
        assert stored.resolved_by is None


def test_collusion_cluster_rejects_non_integer_and_unknown_donor_ids(client, db_session_factory):
    _donors(db_session_factory, 10, 11)
    url = "/internal/watchdog/cases"

    for donor_ids in ([10, "PAYER123"], [10, 11.0], [10, True]):
        r = client.post(url, headers=INTERNAL, json={
            "project_id": 1, "rule": "collusion_cluster", "evidence": {"donor_ids": donor_ids},
        })
        assert r.status_code == 422, (donor_ids, r.text)
        assert r.json()["detail"]["error"] == "INVALID_EVIDENCE"

    r = client.post(url, headers=INTERNAL, json={
        "project_id": 1, "rule": "collusion_cluster", "evidence": {"donor_ids": [10, 999]},
    })
    assert r.status_code == 422
    assert "Unknown donor_ids" in r.json()["detail"]["message"]


def test_collusion_cluster_graph_shape_is_validated(client, db_session_factory):
    _donors(db_session_factory, 10, 11)
    url = "/internal/watchdog/cases"
    bad_graphs = [
        {"nodes": [{"id": 10, "type": "donor"}]},  # no label
        {"nodes": [{"id": 10, "type": "", "label": "Donor"}]},  # no type
        {"edges": [{"source": 10, "target": 1}]},  # no weight
        {"edges": [{"source": 10, "target": 1, "weight": "strong"}]},  # weight not a number
        {"nodes": "not-a-list"},
    ]
    for graph in bad_graphs:
        r = client.post(url, headers=INTERNAL, json={
            "project_id": 1,
            "rule": "collusion_cluster",
            "evidence": {"donor_ids": [10, 11], "graph": graph},
        })
        assert r.status_code == 422, (graph, r.text)
        assert r.json()["detail"]["error"] == "INVALID_EVIDENCE"


def test_confirm_merges_collusion_cluster_in_the_engine(client, db_session_factory):
    _donors(db_session_factory, 10, 11)
    now = datetime.now(timezone.utc)
    with db_session_factory() as db:
        round_ = Round(
            name="Collusion round",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
            matching_pool=1000,
            currency="USD",
            status=RoundStatus.open,
            project_cap_pct=100,
        )
        db.add(round_)
        for donor_id in (10, 11):
            db.add(Donation(
                donor_id=donor_id,
                target_type=TargetType.PROJECT,
                project_id=2,
                amount=100,
                currency="USD",
                status=DonationStatus.captured,
                captured_at=now,
            ))
        db.commit()
        round_id = round_.id
        before = {r.project_id: r for r in run_round(db, round_)}
        db.commit()

    assert before[2].score > 0  # two separate people before the admin confirms

    case = _case(client, project_id=1, rule="collusion_cluster", donor_ids=(10, 11))
    assert _resolve(client, case["id"], action="confirm").json()["status"] == "confirmed"
    assert _frozen(db_session_factory, project_id=1) == (False, "active")

    with db_session_factory() as db:
        after = {r.project_id: r for r in run_round(db, db.get(Round, round_id))}
    assert after[2].score == 0  # one person after the cluster merge


# --- milestones ---------------------------------------------------------------------------


def _milestone(db_session_factory, amount=30_000, match=0, project_id=1):
    with db_session_factory() as db:
        m = Milestone(project_id=project_id, seq=1, title="Buy 40 books", amount=amount, match_amount=match, currency="USD")
        db.add(m)
        db.commit()
        return m.id


def _request(client, milestone_id, **checks):
    return client.post("/internal/payout-requests", headers=INTERNAL,
                       json={"milestone_id": milestone_id, "checks": PASS | checks, "summary": "Receipts match"})


def _tranches(db_session_factory):
    with db_session_factory() as db:
        return [(e.amount, e.project_id) for e in db.scalars(select(LedgerEntry)) if e.type.value == "tranche"]


def test_all_checks_pass_below_threshold_releases(client, db_session_factory):
    mid = _milestone(db_session_factory, amount=30_000, match=5_000)
    r = _request(client, mid).json()
    assert r["status"] == "released"
    assert _tranches(db_session_factory) == [(35_000, 1)]
    assert _request(client, mid).json()["detail"]["error"] == "MILESTONE_NOT_OPEN"
    assert client.get("/projects/1").json()["milestones"][0]["status"] == "released"


def test_failed_check_holds_for_admin(client, db_session_factory):
    mid = _milestone(db_session_factory)
    r = _request(client, mid, supplier_matches_plan=False).json()
    assert r["status"] == "held_for_admin" and "supplier_matches_plan" in r["reason"]
    assert [m["id"] for m in client.get("/admin/milestones/held", headers=ADMIN).json()] == [mid]
    assert _tranches(db_session_factory) == []
    log = client.get("/admin/audit-log", headers=ADMIN, params={"actor": "milestone-agent"}).json()
    assert "Receipts match" in log[0]["reason"]


def test_above_threshold_and_open_case_hold(client, db_session_factory):
    big = _milestone(db_session_factory, amount=45_000, match=10_000)  # 55,000 > 50,000 with its match
    assert "above_threshold" in _request(client, big).json()["reason"]
    _case(client, project_id=2)
    flagged = _milestone(db_session_factory, amount=100, project_id=2)
    assert "open_watchdog_case" in _request(client, flagged).json()["reason"]


def test_admin_review(client, db_session_factory):
    mid = _milestone(db_session_factory)
    _request(client, mid, dated_in_window=False)
    sent_back = client.post(f"/admin/milestones/{mid}/review", headers=ADMIN, json={"approve": False}).json()
    assert sent_back["status"] == "open"
    _request(client, mid, dated_in_window=False)
    approved = client.post(f"/admin/milestones/{mid}/review", headers=ADMIN, json={"approve": True, "note": "Checked by phone"})
    assert approved.json()["status"] == "released"
    assert _tranches(db_session_factory) == [(30_000, 1)]
    again = client.post(f"/admin/milestones/{mid}/review", headers=ADMIN, json={"approve": True})
    assert again.json()["detail"]["error"] == "MILESTONE_NOT_HELD"


# --- verification -------------------------------------------------------------------------


def test_verify_lists_project(client):
    assert client.get("/projects/3").status_code == 404  # pending review
    r = client.post("/admin/projects/3/verify", headers=ADMIN, json={"approve": True})
    assert r.status_code == 200 and r.json()["status"] == "verified" and r.json()["verified_at"]
    assert client.get("/projects/3").status_code == 200
    again = client.post("/admin/projects/3/verify", headers=ADMIN, json={"approve": True})
    assert again.json()["detail"]["error"] == "NOT_PENDING_REVIEW"


def test_reject_sends_back_to_draft(client):
    r = client.post("/admin/projects/3/verify", headers=ADMIN, json={"approve": False, "note": "No registration"})
    assert r.json()["status"] == "draft"
