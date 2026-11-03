"""Watchdog cases, milestone payout requests, admin review and project verification."""

from sqlalchemy import select

from app.models import LedgerEntry, Milestone, Project

ADMIN = {"Authorization": "Bearer admin-test-token"}
INTERNAL = {"Authorization": "Bearer internal-test-token"}
PASS = {"receipt_total_within_10pct": True, "supplier_matches_plan": True, "photo_not_duplicate": True, "dated_in_window": True}


def _case(client, project_id=1, rule="new_payer_burst", donor_ids=(1, 2)):
    r = client.post("/internal/watchdog/cases", headers=INTERNAL,
                    json={"project_id": project_id, "rule": rule, "evidence": {"donor_ids": list(donor_ids)}})
    assert r.status_code == 201, r.text
    return r.json()


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
