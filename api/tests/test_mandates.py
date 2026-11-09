"""Giving Agent: mandate, PayPal top-up, checked donations and the donor's approvals."""

from sqlalchemy import select

from app.models import AuditLog, LedgerEntry

INTERNAL = {"Authorization": "Bearer internal-test-token"}
MANDATE = {
    "monthly_budget_cents": 1000,
    "categories": [1],
    "excluded_tags": ["faith-based"],
    "per_project_max_cents": 400,
    "approval_threshold_cents": 300,
}


def _top_up(client, amount=1000):
    """Pay into the agent budget through the PayPal order route; the payer becomes donor 1."""
    order = client.post("/donations/orders", json={"target_type": "AGENT", "amount_cents": amount}).json()
    assert client.post(f"/donations/orders/{order['order_id']}/capture").json()["status"] == "captured"


def _setup(client, **mandate):
    _top_up(client)
    r = client.put("/donors/1/mandate", json=MANDATE | mandate)
    assert r.status_code == 200, r.text
    return r.json()


def _run(client, mandate_id=1):
    r = client.post("/internal/mandate-runs", headers=INTERNAL, json={"mandate_id": mandate_id, "decisions": {"chosen": []}})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _give(client, run_id, project_id=1, amount=200):
    return client.post(
        "/internal/checked-donations",
        headers=INTERNAL,
        json={"mandate_run_id": run_id, "project_id": project_id, "amount_cents": amount, "reason": "few backers"},
    ).json()


def test_top_up_funds_the_balance(client, fake_paypal):
    m = _setup(client)
    assert m["funded_balance_cents"] == 1000
    sent = fake_paypal.orders["ORDER1"]["purchase_units"][0]
    assert sent["description"] == "Top-up of your Giving Agent budget"
    # A top-up is not a gift to any project.
    assert client.get("/projects/1").json()["raised_cents"] == 0


def test_mandate_validation(client):
    _top_up(client)
    put = lambda **kw: client.put("/donors/1/mandate", json=MANDATE | kw).json()["detail"]["error"]
    assert put(categories=[99]) == "CATEGORY_NOT_FOUND"
    assert put(categories=[]) == "CATEGORIES_REQUIRED"
    assert put(per_project_max_cents=5000) == "PER_PROJECT_OVER_BUDGET"
    assert put(approval_threshold_cents=5000) == "THRESHOLD_OVER_BUDGET"
    assert put(per_project_max_cents=50) == "AMOUNT_TOO_LOW"
    assert put(monthly_budget_cents=2_000_000, per_project_max_cents=400) == "BUDGET_TOO_HIGH"
    assert put(excluded_tags=[f"tag-{n}" for n in range(21)]) == "TOO_MANY_TAGS"
    assert put(excluded_tags=["x" * 41]) == "TAG_TOO_LONG"
    assert put(weight_overrides={"few_backers": 90}) == "INVALID_WEIGHTS"
    assert put(weight_overrides={"vibes": 10}) == "INVALID_WEIGHTS"
    assert client.put("/donors/1/mandate", json=MANDATE | {"weight_overrides": {"few_backers": 45}}).status_code == 200
    assert client.get("/donors/2/mandate").status_code == 404
    assert client.get("/donors/1/mandate").json()["weight_overrides"] == {"few_backers": 45}


def test_a_422_lists_every_problem_with_its_field(client):
    _top_up(client)  # creates donor 1
    r = client.put("/donors/1/mandate", json=MANDATE | {
        "categories": [99], "approval_threshold_cents": 5000, "weight_overrides": {"urgency": 99}})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "CATEGORY_NOT_FOUND"  # the first problem leads
    assert [(e["field"], e["code"]) for e in detail["errors"]] == [
        ("categories", "CATEGORY_NOT_FOUND"),
        ("approval_threshold_cents", "THRESHOLD_OVER_BUDGET"),
        ("weight_overrides.urgency", "INVALID_WEIGHTS"),
    ]


def test_tags_are_saved_trimmed_lowercased_and_deduped(client):
    _top_up(client)  # creates donor 1
    r = client.put("/donors/1/mandate", json=MANDATE | {"excluded_tags": [" Faith-Based ", "faith-based", "", "STEM"]})
    assert r.json()["excluded_tags"] == ["faith-based", "stem"]


def test_preview_checks_without_saving(client, db_session_factory):
    _top_up(client)  # creates donor 1
    bad = client.post("/donors/1/mandate/preview", json=MANDATE | {"approval_threshold_cents": 5000,
                                                                   "excluded_tags": [" STEM "]})
    assert bad.status_code == 200
    assert bad.json()["ok"] is False
    assert bad.json()["errors"] == [{"field": "approval_threshold_cents", "code": "THRESHOLD_OVER_BUDGET",
                                     "message": "Approval threshold can't be more than the monthly budget"}]
    assert bad.json()["normalized"]["excluded_tags"] == ["stem"]

    good = client.post("/donors/1/mandate/preview", json=MANDATE).json()
    assert good == {"ok": True, "errors": [], "normalized": good["normalized"]}
    # Nothing was saved, and nothing was logged.
    assert client.get("/donors/1/mandate").status_code == 404
    with db_session_factory() as db:
        assert not db.scalars(select(AuditLog).where(AuditLog.action == "mandate_updated")).all()
    assert client.post("/donors/99/mandate/preview", json=MANDATE).status_code == 404


def test_every_save_is_audited_with_before_and_after(client, db_session_factory):
    _top_up(client)  # creates donor 1
    client.put("/donors/1/mandate", json=MANDATE)
    client.put("/donors/1/mandate", json=MANDATE | {"monthly_budget_cents": 2000})
    with db_session_factory() as db:
        logs = db.scalars(select(AuditLog).where(AuditLog.action == "mandate_updated").order_by(AuditLog.id)).all()
    assert [(log.actor, log.rule_result) for log in logs] == [("donor", "ok"), ("donor", "ok")]
    assert logs[0].inputs["before"] is None and logs[0].inputs["after"]["monthly_budget_cents"] == 1000
    assert logs[1].inputs["before"]["monthly_budget_cents"] == 1000
    assert logs[1].inputs["after"]["monthly_budget_cents"] == 2000
    # A refused mandate writes nothing.
    client.put("/donors/1/mandate", json=MANDATE | {"categories": []})
    with db_session_factory() as db:
        assert len(db.scalars(select(AuditLog).where(AuditLog.action == "mandate_updated")).all()) == 2


def test_constraints_are_public(client):
    c = client.get("/mandates/constraints").json()
    assert c["default_weights"]["few_backers"] == 35 and c["max_weight_shift"] == 20
    assert c["max_budget_cents"] == 1_000_000 and c["max_tags"] == 20 and c["max_tag_length"] == 40
    assert c["min_per_project_cents"] == c["min_approval_threshold_cents"] == 100


def test_gift_within_rules_is_recorded_and_counts_as_donors(client, db_session_factory):
    _setup(client)
    run_id = _run(client)
    out = _give(client, run_id, amount=200)
    assert (out["status"], out["rule_result"]) == ("recorded", "ok")
    assert client.get(f"/donations/{out['donation_id']}").json()["target_type"] == "AGENT"
    assert client.get("/projects/1").json()["raised_cents"] == 200
    assert client.get("/donors/1/mandate").json()["funded_balance_cents"] == 800
    with db_session_factory() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.action == "checked_donation")).reason == "few backers"
        gifts = [e for e in db.scalars(select(LedgerEntry)) if e.project_id == 1]
        assert [(e.type.value, e.amount) for e in gifts] == [("donation", 200)]


def test_retry_returns_first_answer(client):
    _setup(client)
    run_id = _run(client)
    first = _give(client, run_id)
    again = _give(client, run_id)
    assert again["donation_id"] == first["donation_id"] and again["rule_result"] == "duplicate"
    assert client.get("/donors/1/mandate").json()["funded_balance_cents"] == 800


def test_rules_block_bad_gifts(client):
    _setup(client)
    run_id = _run(client)
    rule = lambda **kw: _give(client, run_id, **kw)["rule_result"]
    assert rule(project_id=2) == "excluded_tag"  # faith-based
    assert rule(project_id=3) == "project_not_open"  # pending review
    assert rule(amount=500) == "over_per_project_max"
    assert _give(client, _run(client), amount=300)["status"] == "recorded"
    assert rule(amount=200) == "over_per_project_max"  # 300 + 200 > 400 this month


def test_budget_and_balance(client):
    limits = {"per_project_max_cents": 1000, "monthly_budget_cents": 1000, "approval_threshold_cents": 1000}
    _setup(client, excluded_tags=[], **limits)
    assert _give(client, _run(client), amount=900)["status"] == "recorded"
    assert _give(client, _run(client), project_id=2, amount=200)["rule_result"] == "over_monthly_budget"
    client.put("/donors/1/mandate", json=MANDATE | limits | {"excluded_tags": [], "monthly_budget_cents": 5000})
    assert _give(client, _run(client), project_id=2, amount=200)["rule_result"] == "insufficient_balance"  # 100 left


def test_category_outside_mandate_and_paused_mandate(client):
    _setup(client, categories=[2])
    assert _give(client, _run(client))["rule_result"] == "category_not_in_mandate"
    client.put("/donors/1/mandate", json=MANDATE | {"active": False})
    assert _give(client, _run(client))["rule_result"] == "mandate_inactive"
    assert client.get("/internal/mandates/active", headers=INTERNAL).json() == []


def test_large_gift_waits_for_donor_then_approved(client):
    _setup(client)
    out = _give(client, _run(client), amount=350)  # above the 300 threshold
    assert out["status"] == "awaiting_donor_approval"
    assert client.get("/projects/1").json()["raised_cents"] == 0
    assert client.get("/donors/1/mandate").json()["funded_balance_cents"] == 650  # reserved

    pending = client.get("/donors/1/pending-approvals").json()
    assert [(p["donation_id"], p["project_title"]) for p in pending] == [(out["donation_id"], "Lanet Library")]
    assert "USD 3.00" in pending[0]["reason"]
    r = client.post(f"/donors/1/pending-approvals/{out['donation_id']}", json={"approve": True})
    assert r.json()["status"] == "captured"
    assert client.get("/projects/1").json()["raised_cents"] == 350
    assert client.get("/donors/1/pending-approvals").json() == []


def test_declined_gift_frees_the_budget(client):
    _setup(client)
    out = _give(client, _run(client), amount=350)
    client.post(f"/donors/1/pending-approvals/{out['donation_id']}", json={"approve": False})
    assert client.get("/donors/1/mandate").json()["funded_balance_cents"] == 1000
    assert client.post(f"/donors/1/pending-approvals/{out['donation_id']}", json={"approve": True}).status_code == 404


def test_approval_rechecks_the_mandate(client):
    _setup(client)
    out = _give(client, _run(client), amount=350)
    client.put("/donors/1/mandate", json=MANDATE | {"excluded_tags": ["books"]})  # donor changed their mind
    r = client.post(f"/donors/1/pending-approvals/{out['donation_id']}", json={"approve": True})
    assert (r.status_code, r.json()["detail"]["error"]) == (409, "EXCLUDED_TAG")
    assert client.get(f"/donations/{out['donation_id']}").json()["status"] == "failed"


def test_runs_listed_for_donor_and_active_mandates_for_agent(client):
    _setup(client)
    _run(client)
    assert len(client.get("/donors/1/mandate/runs").json()) == 1
    active = client.get("/internal/mandates/active", headers=INTERNAL).json()
    assert [(m["donor_id"], m["funded_balance_cents"]) for m in active] == [(1, 1000)]
    assert client.post("/internal/mandate-runs", headers=INTERNAL, json={"mandate_id": 9, "decisions": {}}).status_code == 404
    assert client.post("/internal/checked-donations", headers=INTERNAL, json={
        "mandate_run_id": 999, "project_id": 1, "amount_cents": 100, "reason": "x"}).status_code == 404
