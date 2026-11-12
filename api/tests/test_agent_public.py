"""Public agent trace: safe projections, newest-first runs and cursor activity."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import AuditLog, Donation, Donor, Mandate, MandateRun, Milestone, TargetType

PUBLIC_ACTORS = ("giving-agent", "milestone-agent", "watchdog-agent", "admin")


@pytest.fixture(autouse=True)
def _mandate(db_session_factory):
    """Every run needs a mandate; donor 1 also proves donor fields never leak."""
    with db_session_factory() as db:
        db.add(Donor(id=1, paypal_payer_id="PAYER-SECRET-1", display_name="Wanjiru"))
        db.flush()
        db.add(
            Mandate(
                id=1,
                donor_id=1,
                monthly_budget=1000,
                currency="USD",
                categories=[1],
                excluded_tags=[],
                per_project_max=500,
                approval_threshold=500,
            )
        )
        db.commit()


def _run(factory, *, mandate_id=1, minutes_ago=0, decisions=None, report_text="Your agent gave $5 to Lanet Library."):
    with factory() as db:
        run = MandateRun(
            mandate_id=mandate_id,
            run_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
            decisions=decisions,
            report_text=report_text,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run.id


def test_unknown_run_is_404(client):
    response = client.get("/agents/runs/999")
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "RUN_NOT_FOUND"


def test_run_has_trace_choices_and_no_donor_identifiers(client, db_session_factory):
    decisions = {
        "trace": [
            {
                "seq": 2,
                "at": "2026-11-06T10:00:01Z",
                "actor": "giving-agent",
                "step": "request_donation",
                "tool": "request_checked_donation",
                "status": "ok",
                "title": "Asked for a $5 gift",
                "input": {
                    "project_id": 1,
                    "amount_cents": 500,
                    "funded_balance_cents": 5000,
                    "balance": 5000,
                    "donor_id": 7,
                    "donor_ids": [7],
                    "donor_name": "Wanjiru",
                    "payer_id": "PAYER-SECRET-1",
                    "email": "donor@example.com",
                },
                "result": {"status": "recorded", "funded_balance_cents": 5000, "payer_id": "PAYER-SECRET-1"},
                "rule": "ok",
                "reason": "Three backers, donor@example.com confirmed",
            },
            {
                "seq": 1,
                "actor": "giving-agent",
                "step": "search",
                "title": "Kept two projects",
                "input": {"project_ids": [1, 2], "donor_ids": [7], "payer": "PAYER-SECRET-1", "balance": 5000},
                "result": {"count": 2},
            },
        ],
        "chosen": [{"project_id": 1, "amount_cents": 500}],
        "skipped": [{"project_id": 2, "reason": "Already backed this month"}],
    }
    run_id = _run(db_session_factory, decisions=decisions)

    response = client.get(f"/agents/runs/{run_id}")
    assert response.status_code == 200
    body = response.json()

    assert [step["seq"] for step in body["trace"]] == [1, 2]
    assert body["trace"][0]["title"] == "Kept two projects"
    assert body["trace"][0]["input"] == {"project_ids": [1, 2]}
    assert body["trace"][1]["input"] == {"project_id": 1, "amount_cents": 500}
    assert body["trace"][1]["result"] == {"status": "recorded"}
    assert body["trace"][1]["reason"] == "Three backers, [redacted] confirmed"
    assert body["chosen"] == [{"project_id": 1, "title": "Lanet Library", "amount_cents": 500,
                               "supplier_id": None, "supplier_name": None}]
    assert body["skipped"] == [
        {"project_id": 2, "title": "Faith School Desks", "reason": "Already backed this month"}
    ]
    assert "mandate_id" not in body
    assert "donor_id" not in response.text
    assert "payer_id" not in response.text
    assert "PAYER-SECRET-1" not in response.text
    assert "donor@example.com" not in response.text
    assert "balance" not in response.text
    assert response.headers["cache-control"] == "public, max-age=5"


def test_run_without_decisions_is_empty_not_an_error(client, db_session_factory):
    run_id = _run(db_session_factory, decisions=None)
    body = client.get(f"/agents/runs/{run_id}").json()
    assert body["trace"] == []
    assert body["chosen"] == []
    assert body["skipped"] == []


def test_runs_are_newest_first_and_limited(client, db_session_factory):
    newest = _run(db_session_factory, minutes_ago=0, report_text="newest")
    middle = _run(db_session_factory, minutes_ago=5, report_text="middle")
    _run(db_session_factory, minutes_ago=10, report_text="oldest")

    response = client.get("/agents/runs", params={"limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert [run["id"] for run in body] == [newest, middle]
    assert [run["report_text"] for run in body] == ["newest", "middle"]
    assert all("mandate_id" not in run for run in body)
    assert response.headers["cache-control"] == "public, max-age=5"


def test_runs_are_limited_to_the_demo_mandate(client, db_session_factory):
    with db_session_factory() as db:
        db.add(Donor(id=2, display_name="Other donor"))
        db.flush()
        db.add(
            Mandate(
                id=2,
                donor_id=2,
                monthly_budget=1000,
                currency="USD",
                categories=[1],
                excluded_tags=[],
                per_project_max=500,
                approval_threshold=500,
            )
        )
        db.commit()

    demo_run = _run(db_session_factory)
    other_run = _run(db_session_factory, mandate_id=2)

    body = client.get("/agents/runs").json()
    assert [run["id"] for run in body] == [demo_run]

    other = client.get(f"/agents/runs/{other_run}")
    assert other.status_code == 404
    assert other.json()["detail"]["error"] == "RUN_NOT_FOUND"
    assert client.get(f"/agents/runs/{demo_run}").status_code == 200


def test_activity_has_a_title_for_a_run_summary(client, db_session_factory):
    run_id = _run(db_session_factory)
    with db_session_factory() as db:
        db.add(
            AuditLog(
                actor="giving-agent",
                action="mandate_run_summary",
                inputs={"mandate_run_id": run_id},
                rule_result="ok",
                reason="2 recorded, 1 awaiting approval",
            )
        )
        db.commit()

    body = client.get("/agents/activity").json()
    summary = next(item for item in body if item["action"] == "mandate_run_summary")
    assert summary["run_id"] == run_id
    assert summary["title"] == "Giving Agent finished a run - 2 recorded, 1 awaiting approval"


def test_activity_is_newest_first_with_cursor_and_project_titles(client, db_session_factory):
    with db_session_factory() as db:
        milestone = Milestone(project_id=1, seq=1, title="Books", amount=1000, currency="USD")
        donation = Donation(target_type=TargetType.PROJECT, project_id=2, amount=1000, currency="USD")
        db.add_all([milestone, donation])
        db.flush()
        rows = [
            AuditLog(
                actor="giving-agent",
                action="checked_donation",
                inputs={"project_id": 1, "donor_id": 7, "payer_id": "PAYER-SECRET-1"},
                rule_result="ok",
                reason="Three backers, 2% funded",
            ),
            AuditLog(
                actor="milestone-agent",
                action="payout_request",
                inputs={"milestone_id": milestone.id},
                rule_result="held_for_admin",
                reason="Receipt missing",
            ),
            AuditLog(
                actor="admin",
                action="refund",
                inputs={"donation_id": donation.id, "amount_cents": 1000},
                rule_result="completed",
                reason="Donor asked; donor@example.com",
            ),
            AuditLog(
                actor="donor",
                action="private",
                inputs={"donor_id": 7},
                rule_result="ok",
                reason="Not public",
            ),
            AuditLog(
                actor="watchdog-agent",
                action="case_opened",
                inputs={"project_id": 2, "case_id": 9},
                rule_result="new_payer_burst",
                reason="Eight new payers in fifteen minutes",
            ),
        ]
        db.add_all(rows)
        db.commit()
        inserted = [row.id for row in rows]

    response = client.get("/agents/activity", params={"limit": 10})
    assert response.status_code == 200
    body = response.json()

    # The donor row is private; the rest are newest first.
    expected = [inserted[4], inserted[2], inserted[1], inserted[0]]
    assert [item["id"] for item in body] == expected

    watchdog, refund, held, gift = body
    assert watchdog["project_id"] == 2
    assert watchdog["project_title"] == "Faith School Desks"
    assert watchdog["status"] == "pending"
    assert watchdog["rule"] == "new_payer_burst"
    assert watchdog["title"].startswith("Watchdog opened a new_payer_burst case")

    assert refund["project_id"] == 2  # joined through the donation
    assert refund["project_title"] == "Faith School Desks"
    assert refund["status"] == "ok"
    assert "Donor asked" not in refund["title"]  # admin free text stays private

    assert held["project_id"] == 1  # joined through the milestone
    assert held["project_title"] == "Lanet Library"
    assert held["status"] == "pending"

    assert gift["project_title"] == "Lanet Library"
    assert gift["status"] == "ok"
    assert gift["rule"] is None
    assert "Three backers" in gift["title"]

    assert '"inputs"' not in response.text
    assert "donor_id" not in response.text
    assert "payer_id" not in response.text
    assert "PAYER-SECRET-1" not in response.text
    assert "donor@example.com" not in response.text
    assert response.headers["cache-control"] == "public, max-age=5"

    page = client.get("/agents/activity", params={"limit": 2, "before_id": body[1]["id"]}).json()
    assert [item["id"] for item in page] == [body[2]["id"], body[3]["id"]]
    assert all(item["id"] < body[1]["id"] for item in page)


def test_activity_rejects_bad_cursor(client):
    assert client.get("/agents/activity", params={"before_id": 0}).status_code == 422


def test_refused_agent_gifts_are_shown_as_blocked(client, db_session_factory):
    """The API logs a refused gift with the rule that blocked it; that is never "recorded"."""
    results = ["recorded", "awaiting_donor_approval", "over_monthly_budget", "excluded_tag", "insufficient_balance"]
    with db_session_factory() as db:
        db.add_all(AuditLog(actor="giving-agent", action="checked_donation", inputs={"project_id": 1},
                            rule_result=result, reason="Three backers") for result in results)
        db.commit()
    feed = {a["rule"] or a["title"]: (a["status"], a["title"])
            for a in client.get("/agents/activity", params={"limit": 10}).json()}
    for rule in ("over_monthly_budget", "excluded_tag", "insufficient_balance"):
        status, title = feed[rule]
        assert status == "blocked" and title.startswith("Agent gift to Lanet Library blocked"), (rule, title)
    statuses = sorted(s for s, _ in feed.values())
    assert statuses.count("ok") == 1 and statuses.count("pending") == 1  # recorded, and waiting for the donor
