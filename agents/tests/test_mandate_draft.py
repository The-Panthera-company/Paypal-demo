"""Mandate draft tests: fake core, fake LLM, fake MCP. No network, no DB."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.agents.mandate_draft import (
    Current,
    DEFAULT_WEIGHTS,
    MandateDraftAgent,
    Proposal,
    clean_tag,
    match_category,
    safe_weights,
)
from app.core import FakeCore
from app.llm import FakeLLM, LLMUnavailable
from app.mcp_client import FakeMcpClient


def project(pid, **kw):
    base = {"id": pid, "title": "Project " + str(pid), "tags": ["girls", "education"]}
    base.update(kw)
    return base


def agent(tmp_path=None, proposal=None, projects=None, categories=None,
          llm_fails=False):
    llm = FakeLLM(json_replies=[] if llm_fails else [proposal or {}])
    mcp = FakeMcpClient({"search_projects": projects if projects is not None
                         else [project(1), project(2, tags=["water"])]})
    core = FakeCore(categories=categories)
    return MandateDraftAgent(core=core, llm=llm, mcp=mcp)


# --- pure helpers ----------------------------------------------------------------------


def test_match_category_passes_ids_through():
    assert match_category(2, []) == 2
    assert match_category("2", []) == 2


def test_match_category_resolves_names_and_slugs():
    cats = [{"id": 2, "name": "Education"}, {"id": 3, "name": "Environment"}]
    assert match_category("education", cats) == 2
    assert match_category("Environment", cats) == 3
    assert match_category("food-security", cats) is None


def test_clean_tag_trims_lowercases_and_caps():
    assert clean_tag("  Faith-Based  ") == "faith-based"
    assert len(clean_tag("x" * 100)) == 32
    assert clean_tag(None) == ""


def test_safe_weights_clamps_and_reports():
    kept, shifted = safe_weights({"few_backers": 45, "urgency": 0.22})
    default = DEFAULT_WEIGHTS["few_backers"]
    assert kept["few_backers"] == default + 20
    assert kept["urgency"] == 0.22
    assert shifted == [("few_backers", 45.0)]


def test_safe_weights_ignores_unknown_keys_and_negative_values():
    kept, shifted = safe_weights({"bogus": 1, "evidence": -5})
    assert "bogus" not in kept
    assert kept["evidence"] == 0.0
    assert shifted and shifted[0][0] == "evidence"


# --- ids in the same domain ------------------------------------------------------------


@pytest.mark.asyncio
async def test_existing_category_ids_are_returned_unchanged():
    a = agent()
    out = await a.draft("more education please", Current(categories=[2, 3]))
    assert out["proposed"]["categories"] == [2, 3]


@pytest.mark.asyncio
async def test_existing_slug_strings_are_returned_unchanged():
    """On mock data the web sends slugs, not ids. They must survive a round trip."""
    a = agent()
    out = await a.draft("anything", Current(categories=["education", "water"]))
    assert out["proposed"]["categories"] == ["education", "water"]


@pytest.mark.asyncio
async def test_named_category_is_resolved_through_categories():
    a = agent(proposal=Proposal(categories=["Education"]))
    out = await a.draft("add education", Current(categories=[4]))
    assert out["proposed"]["categories"] == [4, 2]


@pytest.mark.asyncio
async def test_unknown_category_is_rejected_not_invented():
    a = agent(proposal=Proposal(categories=["space travel"]))
    out = await a.draft("space travel", Current(categories=[1]))
    assert out["proposed"]["categories"] == [1]
    assert out["rejected"] == ["category space travel: no such category"]


# --- tags ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verified_tag_is_added_without_warning():
    a = agent(proposal=Proposal(excluded_tags=["girls"]))
    out = await a.draft("skip girls projects", Current())
    assert out["proposed"]["excluded_tags"] == ["girls"]
    assert out["warnings"] == []


@pytest.mark.asyncio
async def test_unverifiable_tag_is_kept_and_flagged():
    a = agent(proposal=Proposal(excluded_tags=["faith-based"]))
    out = await a.draft("nothing religious", Current())
    assert out["proposed"]["excluded_tags"] == ["faith-based"]
    assert out["warnings"] == ["couldn't verify tag faith-based"]


@pytest.mark.asyncio
async def test_tag_lookup_failure_still_keeps_the_tag():
    class Broken(FakeMcpClient):
        async def call(self, tool, **args):
            raise RuntimeError("search down")

    a = MandateDraftAgent(core=FakeCore(), llm=FakeLLM(json_replies=[Proposal(
        excluded_tags=["faith-based"])]), mcp=Broken({}))
    out = await a.draft("nothing religious", Current())
    assert out["proposed"]["excluded_tags"] == ["faith-based"]
    assert out["warnings"] == ["couldn't verify tag faith-based"]


@pytest.mark.asyncio
async def test_existing_tags_are_normalised_and_deduped():
    a = agent(proposal=Proposal(excluded_tags=["Girls"]))
    out = await a.draft("skip girls", Current(excluded_tags=["girls", "  Girls "]))
    assert out["proposed"]["excluded_tags"] == ["girls"]
    assert out["warnings"] == []


# --- amounts and fallbacks -------------------------------------------------------------


@pytest.mark.asyncio
async def test_amounts_are_proposed_only_when_they_change():
    a = agent(proposal=Proposal(monthly_budget_cents=5000))
    out = await a.draft("fifty a month", Current(monthly_budget_cents=5000))
    assert "monthly_budget_cents" not in out["proposed"]


@pytest.mark.asyncio
async def test_llm_failure_keeps_the_form_and_does_not_raise():
    a = agent(llm_fails=True)
    out = await a.draft("anything", Current(monthly_budget_cents=4000, categories=[1]))
    assert out["used_llm"] is False
    assert out["proposed"]["categories"] == [1]
    assert "monthly_budget_cents" not in out["proposed"]


@pytest.mark.asyncio
async def test_empty_text_makes_no_llm_call():
    a = agent()
    out = await a.draft("", Current())
    assert out["used_llm"] is False
    assert a.llm.calls == []


# --- through the route -----------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    main_module._hits.clear()
    monkeypatch.setattr(main_module.cfg, "rate_limit_per_min", 1000, raising=False)
    monkeypatch.setattr(main_module, "MandateDraftAgent",
                        lambda: MandateDraftAgent(
                            core=FakeCore(),
                            llm=FakeLLM(json_replies=[Proposal(monthly_budget_cents=5000)]),
                            mcp=FakeMcpClient({"search_projects": [project(1)]})))
    yield TestClient(main_module.app)
    main_module._hits.clear()


def test_route_returns_the_web_contract(client):
    r = client.post("/agents/mandate/draft", json={
        "text": "fifty a month",
        "current": {"monthly_budget_cents": 1000, "categories": [2]},
    })
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"proposed", "warnings", "rejected", "used_llm"}
    assert body["proposed"]["monthly_budget_cents"] == 5000
    assert body["proposed"]["categories"] == [2]
    assert all(isinstance(w, str) for w in body["warnings"])
    assert all(isinstance(x, str) for x in body["rejected"])
    assert body["used_llm"] is True


def test_route_returns_429_after_the_limit(monkeypatch):
    main_module._hits.clear()
    monkeypatch.setattr(main_module.cfg, "rate_limit_per_min", 1, raising=False)
    monkeypatch.setattr(main_module, "MandateDraftAgent", lambda: MandateDraftAgent(
        core=FakeCore(), llm=FakeLLM(json_replies=[Proposal()]),
        mcp=FakeMcpClient({"search_projects": []})))
    with TestClient(main_module.app) as c:
        first = c.post("/agents/mandate/draft", json={"text": "a", "current": {}})
        second = c.post("/agents/mandate/draft", json={"text": "b", "current": {}})
    main_module._hits.clear()
    assert first.status_code == 200
    assert second.status_code == 429


def test_route_returns_503_when_nothing_can_be_read(monkeypatch):
    main_module._hits.clear()
    monkeypatch.setattr(main_module, "MandateDraftAgent", lambda: MandateDraftAgent(
        core=FakeCore(), llm=FakeLLM(json_replies=[]),
        mcp=FakeMcpClient({"search_projects": []})))
    with TestClient(main_module.app) as c:
        r = c.post("/agents/mandate/draft", json={"text": "hello", "current": {}})
    main_module._hits.clear()
    assert r.status_code == 503


def test_route_rejects_an_overlong_text(client):
    r = client.post("/agents/mandate/draft", json={"text": "x" * 1001, "current": {}})
    assert r.status_code == 422


def test_category_lookup_failure_is_a_warning_not_a_500(monkeypatch):
    class BrokenCore(FakeCore):
        async def categories(self):
            from app.core import CoreError
            raise CoreError("GET /categories -> 500")

    main_module._hits.clear()
    monkeypatch.setattr(main_module, "MandateDraftAgent", lambda: MandateDraftAgent(
        core=BrokenCore(),
        llm=FakeLLM(json_replies=[Proposal(categories=["Education"])]),
        mcp=FakeMcpClient({"search_projects": []})))
    with TestClient(main_module.app) as c:
        r = c.post("/agents/mandate/draft", json={"text": "education", "current": {}})
    main_module._hits.clear()
    assert r.status_code == 200
    assert r.json()["rejected"] == ["category Education: no such category"]
