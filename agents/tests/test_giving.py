"""Giving Agent tests. Offline: FakeMcpClient + FakeCore + FakeLLM, no network."""
import json

import pytest

from app.agents.giving import (
    GivingAgent,
    WEIGHTS,
    days_since_last_funding,
    merge_weights,
    passes_hard_filters,
    reason_detail,
    reason_for,
    score_project,
)
from app.core import FakeCore
from app.llm import FakeLLM
from app.mcp_client import FakeMcpClient


def project(pid, **kw):
    base = {
        "id": pid,
        "title": "Project " + str(pid),
        "category_id": 1,
        "status": "active",
        "matching_frozen": False,
        "goal_cents": 100000,
        "raised_cents": 40000,
        "backer_count": 4,
        "urgency": 3,
        "currency": "USD",
    }
    base.update(kw)
    return base


def mandate(**kw):
    base = {
        "id": 1,
        "monthly_budget_cents": 10000,
        "funded_balance_cents": 50000,
        "per_project_max_cents": 3000,
        "categories": [1],
        "excluded_tags": [],
        "weight_overrides": {},
    }
    base.update(kw)
    return base


def agent(projects, m, llm=None, tmp_path=None, donations=None):
    responses = {
        "list_active_mandates": [m],
        "search_projects": projects,
        "record_mandate_run": {"id": 77},
    }
    if donations is not None:
        responses["request_checked_donation"] = donations
    mcp = FakeMcpClient(responses)
    core = FakeCore()
    return GivingAgent(mcp=mcp, core=core, llm=llm or FakeLLM(texts=["report"]),
                       state_path=(tmp_path / "state.json") if tmp_path else None)


# --- hard filters -------------------------------------------------------------------------

def test_hard_filter_keeps_listed_statuses_only():
    assert passes_hard_filters(project(1))
    assert passes_hard_filters(project(2, status="verified"))
    assert not passes_hard_filters(project(3, status="draft"))


def test_hard_filter_rejects_frozen_and_funded():
    assert not passes_hard_filters(project(1, matching_frozen=True))
    assert not passes_hard_filters(project(2, raised_cents=100000))


# --- factors ------------------------------------------------------------------------------

def test_few_backers_factor():
    score, factors = score_project(project(1, backer_count=0), WEIGHTS, False, None)
    assert factors["few_backers"] == 1.0
    score, factors = score_project(project(1, backer_count=20), WEIGHTS, False, None)
    assert factors["few_backers"] == 0.0


def test_progress_factor_is_raised_over_goal():
    _, factors = score_project(project(1, raised_cents=50000), WEIGHTS, False, None)
    assert factors["progress"] == 0.5


def test_urgency_factor_maps_1_to_5():
    _, low = score_project(project(1, urgency=1), WEIGHTS, False, None)
    _, high = score_project(project(2, urgency=5), WEIGHTS, False, None)
    assert low["urgency"] == 0.0
    assert high["urgency"] == 1.0


def test_evidence_factor():
    _, with_stories = score_project(project(1), WEIGHTS, True, None)
    _, without = score_project(project(1), WEIGHTS, False, None)
    assert with_stories["evidence"] == 1.0
    assert without["evidence"] == 0.0


def test_days_since_funded_defaults_to_1_without_history():
    _, factors = score_project(project(1), WEIGHTS, False, None)
    assert factors["days_since_funded"] == 1.0


def test_days_since_last_funding_uses_newest_rising_point():
    history = [
        {"date": "2026-01-01T00:00:00Z", "raised_cents": 100, "backer_count": 1},
        {"date": "2026-01-02T00:00:00Z", "raised_cents": 300, "backer_count": 2},
        {"date": "2026-01-03T00:00:00Z", "raised_cents": 300, "backer_count": 2},
    ]
    value = days_since_last_funding(history)
    assert value is not None and value > 30


def test_days_since_last_funding_without_rise_is_none():
    history = [
        {"date": "2026-01-01T00:00:00Z", "raised_cents": 300},
        {"date": "2026-01-02T00:00:00Z", "raised_cents": 300},
    ]
    assert days_since_last_funding(history) is None


def test_score_is_weighted_average_times_100():
    p = project(1, backer_count=0, raised_cents=100000, urgency=5)
    score, _ = score_project(p, WEIGHTS, True, None)
    assert score == pytest.approx(100.0)


def test_ties_break_on_lower_project_id():
    weights = {"few_backers": 1, "progress": 0, "urgency": 0, "evidence": 0, "days_since_funded": 0}
    project_a = project(2, backer_count=10)
    project_b = project(1, backer_count=10)
    score_a, _ = score_project(project_a, weights, False, None)
    score_b, _ = score_project(project_b, weights, False, None)
    ordered = sorted([(score_a, 2), (score_b, 1)], key=lambda t: (-t[0], t[1]))
    assert ordered[0][1] == 1


# --- weights ------------------------------------------------------------------------------

def test_merge_weights_applies_overrides_only_for_known_keys():
    merged = merge_weights({"few_backers": 0, "bogus": 99, "progress": "x"})
    assert merged["few_backers"] == 0.0
    assert merged["progress"] == WEIGHTS["progress"]
    assert "bogus" not in merged


def test_weight_override_changes_ranking():
    weights = {"few_backers": 0, "progress": 100, "urgency": 0, "evidence": 0, "days_since_funded": 0}
    low_progress, _ = score_project(project(1, raised_cents=10000), weights, False, None)
    high_progress, _ = score_project(project(2, raised_cents=90000), weights, False, None)
    assert high_progress > low_progress


# --- allocation ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_allocation_respects_per_project_cap(tmp_path):
    a = agent([project(1)], mandate(per_project_max_cents=2500), tmp_path=tmp_path)
    result = await a.run(1)
    assert result["chosen"][0]["amount_cents"] == 2500


@pytest.mark.asyncio
async def test_allocation_never_exceeds_goal_room(tmp_path):
    a = agent([project(1, raised_cents=98000)], mandate(), tmp_path=tmp_path)
    result = await a.run(1)
    assert result["chosen"][0]["amount_cents"] == 2000


@pytest.mark.asyncio
async def test_allocation_stops_at_five_projects(tmp_path):
    projects = [project(i, backer_count=i) for i in range(1, 9)]
    a = agent(projects, mandate(monthly_budget_cents=100000, funded_balance_cents=100000),
              tmp_path=tmp_path)
    result = await a.run(1)
    assert len(result["chosen"]) == 5


@pytest.mark.asyncio
async def test_zero_amount_projects_are_skipped(tmp_path):
    a = agent([project(1, raised_cents=100000)], mandate(), tmp_path=tmp_path)
    result = await a.run(1)
    assert result["chosen"] == []


# --- rejection handling -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_over_budget_rejection_stops_the_run(tmp_path):
    calls = []

    def donation(args):
        calls.append(args)
        return {"status": "rejected", "rule_result": "over_monthly_budget", "reason": "budget"}

    projects = [project(1), project(2)]
    a = agent(projects, mandate(), tmp_path=tmp_path, donations=donation)
    result = await a.run(1)
    assert len(calls) == 1
    assert len(result["results"]) == 1


@pytest.mark.asyncio
async def test_other_rejections_are_logged_and_run_continues(tmp_path):
    a = agent([project(1), project(2)], mandate(), tmp_path=tmp_path,
              donations=lambda args: {"status": "rejected", "rule_result": "excluded_tag",
                                      "reason": "tag"})
    result = await a.run(1)
    assert len(result["results"]) == 2
    logged = [c for c in a.mcp.calls if c[0] == "log_decision"]
    assert len(logged) == 2


@pytest.mark.asyncio
async def test_duplicate_run_is_skipped_without_force(tmp_path):
    a = agent([project(1)], mandate(), tmp_path=tmp_path)
    await a.run(1)
    second = await a.run(1)
    assert second["skipped_run"] == "already_ran_this_month"
    record_calls = [c for c in a.mcp.calls if c[0] == "record_mandate_run"]
    assert len(record_calls) == 1


@pytest.mark.asyncio
async def test_force_runs_again(tmp_path):
    a = agent([project(1)], mandate(), tmp_path=tmp_path)
    await a.run(1)
    result = await a.run(1, force=True)
    assert result["run_id"] == 77


@pytest.mark.asyncio
async def test_report_text_is_planned_wording_from_template(tmp_path):
    a = agent([project(1)], mandate(), llm=FakeLLM(), tmp_path=tmp_path)
    result = await a.run(1)
    assert "Planned" in result["report_text"]


def test_reason_mentions_backers_and_progress():
    _, factors = score_project(project(1, backer_count=4, raised_cents=60000), WEIGHTS, True, None)
    text = reason_for(project(1, backer_count=4, raised_cents=60000), factors)
    assert "4 backers" in text and "60% funded" in text and "receipts" in text


# --- days_since_last_funding: 0, 1 and 2+ points ------------------------------


def _point(date_str, raised):
    return {"date": date_str, "raised_cents": raised}


def test_days_no_points_returns_none():
    assert days_since_last_funding([]) is None


def test_days_ignores_non_dict_points():
    assert days_since_last_funding(["junk", 42]) is None


def test_days_single_point_above_zero_counts_as_a_raise():
    # The API only writes a point once money arrives, so one point means funded once.
    days = days_since_last_funding([_point("2026-10-17T00:00:00Z", 5000)])
    assert days is not None
    assert 19.0 <= days <= 21.0


def test_days_single_point_at_zero_is_never_funded():
    assert days_since_last_funding([_point("2026-10-17T00:00:00Z", 0)]) is None


def test_days_multi_point_uses_latest_increase():
    history = [
        _point("2026-01-01T00:00:00Z", 1000),
        _point("2026-10-17T00:00:00Z", 5000),
        _point("2026-10-20T00:00:00Z", 5000),  # flat, not a raise
    ]
    days = days_since_last_funding(history)
    assert days is not None
    assert 19.0 <= days <= 21.0


def test_days_multi_point_flat_history_is_never_funded():
    history = [_point("2026-01-01T00:00:00Z", 0), _point("2026-02-01T00:00:00Z", 0)]
    assert days_since_last_funding(history) is None


def test_days_unparseable_date_logs_and_returns_none(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="app.agents.giving"):
        days = days_since_last_funding([_point("not-a-date", 5000)])
    assert days is None
    assert any("unparseable" in r.message for r in caplog.records)


# --- reason_detail wording ----------------------------------------------------


def _factors():
    _, factors = score_project(project(1), WEIGHTS, False, None)
    return factors


def test_reason_detail_zero_backers():
    text = reason_detail(project(1, backer_count=0), _factors(), None)
    assert "0 backers" in text


def test_reason_detail_one_backer_is_singular():
    text = reason_detail(project(1, backer_count=1), _factors(), None)
    assert "1 backer," in text


def test_reason_detail_many_backers():
    text = reason_detail(project(1, backer_count=7), _factors(), None)
    assert "7 backers" in text


def test_reason_detail_never_funded_wording():
    text = reason_detail(project(1), _factors(), None)
    assert "not funded yet" in text


def test_reason_detail_funded_wording():
    text = reason_detail(project(1), _factors(), 12.4)
    assert "last funded 12 days ago" in text


def test_reason_detail_one_day_singular():
    text = reason_detail(project(1), _factors(), 1.0)
    assert "last funded 1 day ago" in text


def test_reason_detail_drops_old_few_backers_wording():
    text = reason_detail(project(1, backer_count=1), _factors(), None)
    assert "few backers" not in text


@pytest.mark.asyncio
async def test_report_prompt_carries_rule_built_why(tmp_path):
    llm = FakeLLM(texts=["Report."])
    a = agent([project(1, backer_count=1)], mandate(), llm=llm, tmp_path=tmp_path)
    await a.run(1)
    _, _, user = llm.calls[0]
    assert "why" in user
    assert "1 backer" in user


@pytest.mark.asyncio
async def test_report_prompt_forbids_changing_amounts(tmp_path):
    llm = FakeLLM(texts=["Report."])
    a = agent([project(1)], mandate(), llm=llm, tmp_path=tmp_path)
    await a.run(1)
    system, _, _ = llm.calls[0]
    assert "Never change, round or recompute an amount" in system

