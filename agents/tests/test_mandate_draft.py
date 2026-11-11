"""Mandate draft tests: fake core, fake LLM, fake MCP. No network, no DB."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.agents.mandate_draft import (
    CategoryCache,
    Current,
    DEFAULT_WEIGHTS,
    FALLBACK_CONSTRAINTS,
    MandateDraftAgent,
    Proposal,
    clean_tag,
    match_category,
    LLM_SYSTEM,
    parse_amounts,
    parse_categories,
    safe_weights,
    system_prompt,
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


CATALOGUE = [{"id": 2, "name": "Education"}, {"id": 3, "name": "Environment"},
             {"id": 1, "name": "Health"}, {"id": 4, "name": "Water"}]


def test_match_category_resolves_names_and_slugs():
    cats = [{"id": 2, "name": "Education"}, {"id": 3, "name": "Environment"}]
    assert match_category("education", cats) == 2
    assert match_category("Environment", cats) == 3
    assert match_category("food-security", cats) is None


@pytest.mark.parametrize("value,expected", [
    ("Clean water", 4),
    ("water", 4),
    ("WATER ", 4),
    ("Water", 4),
    ("waters", 4),
    ("girls education", 2),
    ("Education", 2),
])
def test_match_category_accepts_tolerant_forms(value, expected):
    assert match_category(value, CATALOGUE) == expected


@pytest.mark.parametrize("value", ["clean energy", "food security", "", "   "])
def test_match_category_never_guesses_when_nothing_matches(value):
    assert match_category(value, CATALOGUE) is None


def test_match_category_refuses_ambiguity():
    """Two categories inside one string is a question, not an answer."""
    cats = [{"id": 1, "name": "Water"}, {"id": 2, "name": "Water Sanitation"}]
    assert match_category("clean water sanitation", cats) is None


def test_match_category_does_not_match_inside_longer_words():
    cats = [{"id": 1, "name": "Cleaner"}]
    assert match_category("clean water", cats) is None


def test_clean_tag_trims_lowercases_and_caps():
    assert clean_tag("  Faith-Based  ") == "faith-based"
    assert len(clean_tag("x" * 100)) == 40
    assert clean_tag(None) == ""


def test_safe_weights_clamps_and_reports():
    # Weights are on the API 0-100 scale and the band is default +/- 20.
    # urgency defaults to 20, so its band is 0..40: 22 is inside and survives as asked.
    kept, shifted = safe_weights({"few_backers": 90, "urgency": 22, "bogus": 5},
                                 FALLBACK_CONSTRAINTS)
    assert DEFAULT_WEIGHTS["urgency"] == 20
    assert kept["urgency"] == 22
    # few_backers defaults to 35, so anything above 55 clamps down to 55.
    assert DEFAULT_WEIGHTS["few_backers"] == 35
    assert kept["few_backers"] == 55
    # An unknown key is dropped, not clamped and not reported as a shift.
    assert "bogus" not in kept
    assert shifted == [("few_backers", 90.0)]

    kept, shifted = safe_weights({"few_backers": 5}, FALLBACK_CONSTRAINTS)
    assert kept["few_backers"] == 15, "below the band clamps up to default - 20"
    assert shifted == [("few_backers", 5.0)]


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
    out = await a.draft("skip girls projects", Current(categories=[1]))
    assert out["proposed"]["excluded_tags"] == ["girls"]
    assert out["warnings"] == []


@pytest.mark.asyncio
async def test_unverifiable_tag_is_kept_and_flagged():
    a = agent(proposal=Proposal(excluded_tags=["faith-based"]))
    out = await a.draft("nothing religious", Current(categories=[1]))
    assert out["proposed"]["excluded_tags"] == ["faith-based"]
    assert out["warnings"] == ["couldn't verify tag faith-based"]


@pytest.mark.asyncio
async def test_tag_lookup_failure_still_keeps_the_tag():
    class Broken(FakeMcpClient):
        async def call(self, tool, **args):
            raise RuntimeError("search down")

    a = MandateDraftAgent(core=FakeCore(), llm=FakeLLM(json_replies=[Proposal(
        excluded_tags=["faith-based"])]), mcp=Broken({}))
    out = await a.draft("nothing religious", Current(categories=[1]))
    assert out["proposed"]["excluded_tags"] == ["faith-based"]
    assert out["warnings"] == ["couldn't verify tag faith-based"]


@pytest.mark.asyncio
async def test_existing_tags_are_normalised_and_deduped():
    a = agent(proposal=Proposal(excluded_tags=["Girls"]))
    out = await a.draft("skip girls",
                        Current(categories=[1], excluded_tags=["girls", "  Girls "]))
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


# --- rule-based fallback ---------------------------------------------------------------


def test_parse_amounts_reads_the_reported_sentence():
    text = 'Clean water, $10 a month, $3 per project'
    assert parse_amounts(text) == {'monthly_budget_cents': 1000, 'per_project_max_cents': 300}


@pytest.mark.parametrize('text,expected', [
    ('20 dollars each month', {'monthly_budget_cents': 2000}),
    ('monthly budget of 40', {'monthly_budget_cents': 4000}),
    ('5 per project max', {'per_project_max_cents': 500}),
    ('I like helping out', {}),
    ('', {}),
])
def test_parse_amounts_variants(text, expected):
    assert parse_amounts(text) == expected


def test_parse_categories_is_case_insensitive():
    cats = [{'id': 4, 'name': 'Water'}, {'id': 2, 'name': 'Education'}]
    assert parse_categories('clean WATER please', cats) == [4]
    assert parse_categories('no match here', cats) == []


class DeadLLM(FakeLLM):
    """Raises LLMUnavailable the way a missing DEEPSEEK_API_KEY does."""

    async def complete_json(self, system, user, schema):
        self.calls.append(('json', system, user))
        raise LLMUnavailable('DEEPSEEK_API_KEY is not set')


def test_system_prompt_lists_allowed_names():
    prompt = system_prompt(CATALOGUE)
    for name in ("Education", "Environment", "Health", "Water"):
        assert name in prompt
    assert "exactly" in prompt
    assert "Clean water" in prompt  # named as the counter-example the model must avoid


def test_system_prompt_without_catalogue_is_still_valid():
    prompt = system_prompt([])
    assert prompt.startswith(LLM_SYSTEM)
    # The API limits are injected on every prompt, catalogue or not.
    assert "1000" in prompt or "100" in prompt
    assert "ignore" in prompt.lower()


@pytest.mark.asyncio
async def test_model_is_given_the_catalogue():
    """The prompt must reach the model with the names in it, not just exist as a helper."""
    llm = FakeLLM(json_replies=[Proposal(categories=["Water"])])
    a = MandateDraftAgent(core=FakeCore(), llm=llm,
                          mcp=FakeMcpClient({"search_projects": []}))
    await a.draft("clean water", Current())
    kind, system, _ = llm.calls[0]
    assert kind == "json"
    assert "Water" in system and "Education" in system


@pytest.mark.asyncio
async def test_report_repro_clean_water_is_accepted():
    """The prod bug, end to end: a model that echoes the donor's phrase is rescued."""
    a = MandateDraftAgent(
        core=FakeCore(),
        llm=FakeLLM(json_replies=[Proposal(categories=["Clean water"],
                                    monthly_budget_cents=1000,
                                    per_project_max_cents=300)]),
        mcp=FakeMcpClient({"search_projects": []}))
    out = await a.draft("Clean water, $10 a month, $3 per project", Current())
    assert out["proposed"]["categories"] == [4]
    assert out["rejected"] == []


@pytest.mark.asyncio
async def test_fallback_reads_amounts_when_the_llm_is_dead():
    text = 'Clean water, $10 a month, $3 per project'
    a = MandateDraftAgent(core=FakeCore(), llm=DeadLLM(),
                          mcp=FakeMcpClient({'search_projects': []}))
    out = await a.draft(text, Current())
    assert out['used_llm'] is False
    assert out['proposed']['monthly_budget_cents'] == 1000
    assert out['proposed']['per_project_max_cents'] == 300
    assert out['proposed']['categories'] == [4]


@pytest.mark.asyncio
async def test_fallback_still_raises_when_it_reads_nothing():
    a = MandateDraftAgent(core=FakeCore(), llm=DeadLLM(),
                          mcp=FakeMcpClient({'search_projects': []}))
    with pytest.raises(LLMUnavailable):
        await a.draft('I would like to help somehow', Current())


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
    assert set(body) == {"proposed", "warnings", "rejected", "used_llm", "diff"}
    assert isinstance(body["diff"], list)
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


def test_route_returns_200_with_cents_when_the_llm_is_unavailable(monkeypatch):
    """The reported bug, end to end: no API key, a readable sentence, a real 200."""
    main_module._hits.clear()
    monkeypatch.setattr(main_module.cfg, 'rate_limit_per_min', 1000, raising=False)
    monkeypatch.setattr(main_module, 'MandateDraftAgent', lambda: MandateDraftAgent(
        core=FakeCore(), llm=DeadLLM(),
        mcp=FakeMcpClient({'search_projects': []})))
    with TestClient(main_module.app) as c:
        r = c.post('/agents/mandate/draft', json={
            'text': 'Clean water, $10 a month, $3 per project',
            'current': {},
        })
    main_module._hits.clear()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['used_llm'] is False
    assert body['proposed']['monthly_budget_cents'] == 1000
    assert body['proposed']['per_project_max_cents'] == 300
    assert body['proposed']['categories'] == [4]


def test_route_still_503s_when_the_text_yields_nothing(monkeypatch):
    main_module._hits.clear()
    monkeypatch.setattr(main_module, 'MandateDraftAgent', lambda: MandateDraftAgent(
        core=FakeCore(), llm=DeadLLM(),
        mcp=FakeMcpClient({'search_projects': []})))
    with TestClient(main_module.app) as c:
        r = c.post('/agents/mandate/draft', json={'text': 'help somehow', 'current': {}})
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
        r = c.post("/agents/mandate/draft",
                   json={"text": "education", "current": {"categories": [1]}})
    main_module._hits.clear()
    assert r.status_code == 200
    body = r.json()
    # A cold core is not the donor fault: warn and leave the field alone rather than
    # sending them hunting for a category that does exist.
    assert body["rejected"] == []
    assert body["warnings"] == [
        "couldn" + "t verify category Education, try again in a minute"]
    # [1] is the donor's own untouched value; 2 (Education) is the unverified
    # category and must NOT appear.
    assert body["proposed"]["categories"] == [1]
    assert 2 not in body["proposed"]["categories"]


class FlakyCore(FakeCore):
    """Down for `failures` reads, then up. A cold core waking up.

    One draft reads the catalogue twice (once for the prompt, once in _add_categories),
    and each read retries once, so a draft against a dead core makes up to four reads.
    """

    def __init__(self, failures: int = 1, **kw) -> None:
        super().__init__(**kw)
        self.failures = failures
        self.calls = 0

    async def categories(self) -> list[dict]:
        from app.core import CoreError

        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise CoreError("GET /categories -> 500")
        return await super().categories()


def draft_agent(core, category: str = "Education") -> MandateDraftAgent:
    return MandateDraftAgent(
        core=core,
        llm=FakeLLM(json_replies=[Proposal(categories=[category])]),
        mcp=FakeMcpClient({"search_projects": []}))


def test_failed_lookup_warns_and_leaves_the_field_alone() -> None:
    agent_ = draft_agent(FlakyCore(failures=99))
    out = asyncio.run(agent_.draft("education", Current(categories=[1])))
    assert out["rejected"] == [], "a cold core is never a bad category"
    assert out["warnings"] == [
        "couldn" + "t verify category Education, try again in a minute"]
    # [1] is the donor's own untouched value; 2 (Education) is the unverified
    # category and must NOT appear.
    assert out["proposed"]["categories"] == [1]
    assert 2 not in out["proposed"]["categories"]


def test_lookup_is_retried_once_before_giving_up() -> None:
    """One retry per read, with the longer budget: two reads in a draft that fails."""
    core = FlakyCore(failures=99)
    agent_ = draft_agent(core)
    asyncio.run(agent_.draft("education", Current()))
    assert core.calls == 4, "two reads (propose + merge), each retried once"


def test_failure_is_not_cached_and_the_next_request_succeeds() -> None:
    """One cold failure must not pin no-categories for the TTL."""
    # Each read retries once, so a draft makes four reads (propose x2, merge x2).
    # All four must fail for the whole request to come back unverified.
    core = FlakyCore(failures=4)
    agent_ = draft_agent(core)

    first = asyncio.run(agent_.draft("education", Current(categories=[1])))
    assert first["rejected"] == [], "a cold core is not a bad category"
    assert first["warnings"] == [
        "couldn" + "t verify category Education, try again in a minute"]
    # [1] is the donor's own untouched value; 2 (Education) is the unverified
    # category and must NOT appear.
    assert first["proposed"]["categories"] == [1]
    assert 2 not in first["proposed"]["categories"]

    second = asyncio.run(agent_.draft("education", Current(categories=[1])))
    assert second["warnings"] == []
    assert second["rejected"] == []
    # Categories are applied as ids: 2 is Education in FAKE_CATEGORIES.
    # The donor's own [1] is kept, and the newly resolved Education (2) is added.
    assert second["proposed"]["categories"] == [1, 2]


def test_a_real_catalogue_still_rejects_an_unknown_name() -> None:
    """The failure path must not swallow genuine rejections."""
    agent_ = draft_agent(FakeCore(), category="Space travel")
    out = asyncio.run(agent_.draft("space travel", Current(categories=[1])))
    assert out["rejected"] == ["category Space travel: no such category"]
    assert out["warnings"] == []


def test_a_draft_with_no_cause_warns_instead_of_failing(client):
    """An empty effective cause list is a warning on a 200, never an error.

    The donor cannot save a mandate with no cause, so the draft says so plainly.
    """
    main_module._hits.clear()
    r = client.post("/agents/mandate/draft", json={
        "text": "give a bit each month",
        "current": {},
    })
    main_module._hits.clear()
    assert r.status_code == 200
    body = r.json()
    assert "Choose at least one cause before saving" in body["warnings"]
    assert body["rejected"] == []


def test_empty_catalogue_is_not_cached_and_the_cache_retries() -> None:
    """A deployed core always has categories, so [] means unavailable, not none-exist.

    Asserted on the cache directly: a draft reads it twice, so within one request the
    second read would already succeed and hide the point.
    """
    calls = {"n": 0}

    class EmptyThenFull(FakeCore):
        async def categories(self) -> list[dict]:
            calls["n"] += 1
            if calls["n"] <= 2:
                return []
            return [{"id": 2, "name": "Education", "project_count": 4}]

    core = EmptyThenFull()
    cache = CategoryCache()

    values, verified = asyncio.run(cache.lookup(core))
    assert (values, verified) == ([], False)
    assert calls["n"] == 2, "the empty answer was retried once"

    values, verified = asyncio.run(cache.lookup(core))
    assert verified is True
    assert values == [{"id": 2, "name": "Education", "project_count": 4}]

    # A good answer IS cached: no third fetch inside the TTL.
    asyncio.run(cache.lookup(core))
    assert calls["n"] == 3


def test_a_successful_lookup_is_cached_for_the_ttl() -> None:
    core = FlakyCore(failures=0)
    agent_ = draft_agent(core)
    asyncio.run(agent_.draft("education", Current()))
    asyncio.run(agent_.draft("education", Current()))
    assert core.calls == 1, "only failures are retried; successes are cached"
