"""Milestone Agent tests. Fake LLM, fake MCP, in-memory sqlite for hashes."""
from pathlib import Path

import pytest

from app.agents.milestone import (
    HashStore,
    MilestoneAgent,
    Receipt,
    dated_in_window,
    photo_hash,
    supplier_matches,
    total_within_10pct,
)
from app.llm import FakeLLM
from app.mcp_client import FakeMcpClient


def milestone(**kw):
    base = {
        "milestone_id": 5,
        "project_id": 1,
        "amount_cents": 50000,
        "planned_supplier": "Nakuru Books Ltd",
        "window_start": "2026-10-01",
        "due_date": "2026-11-30",
        "documents": [
            {"id": 1, "kind": "receipt", "extracted_text_or_fields": "Nakuru Books Ltd total 50,000"},
            {"id": 2, "kind": "photo", "extracted_text": "shelf photo", "file_url": "u1"},
        ],
    }
    base.update(kw)
    return base


def test_total_within_ten_percent():
    assert total_within_10pct(50000, 50000)
    assert total_within_10pct(55000, 50000)
    assert total_within_10pct(45000, 50000)
    assert not total_within_10pct(56000, 50000)
    assert not total_within_10pct(None, 50000)


def test_supplier_fuzzy_match():
    assert supplier_matches("nakuru books ltd", "Nakuru Books Ltd")
    assert supplier_matches("Nakuru Books Limited", "Nakuru Books Ltd")
    assert not supplier_matches("Mombasa Paper", "Nakuru Books Ltd")
    assert not supplier_matches(None, "Nakuru Books Ltd")


def test_dated_in_window():
    assert dated_in_window("2026-10-15", "2026-10-01", "2026-11-30")
    assert not dated_in_window("2026-09-15", "2026-10-01", "2026-11-30")
    assert not dated_in_window("2026-12-15", "2026-10-01", "2026-11-30")
    assert not dated_in_window(None, "2026-10-01", "2026-11-30")


def test_photo_hash_prefers_text_then_url():
    assert photo_hash({"extracted_text": "abc"}).startswith("text:")
    assert photo_hash({"file_url": "http://x"}).startswith("url:")
    assert photo_hash({}) is None


@pytest.mark.asyncio
async def test_all_checks_pass_and_payout_requested(tmp_path):
    store = HashStore(Path(tmp_path) / "h.sqlite")
    llm = FakeLLM(json_replies=[{"total_cents": 50000, "supplier": "Nakuru Books Ltd",
                                "date": "2026-10-15"}])
    mcp = FakeMcpClient({"request_milestone_payout": {"status": "released"}})
    agent = MilestoneAgent(mcp=mcp, llm=llm, source=None, store=store)
    out = await agent.check(milestone())
    assert all(out["checks"].values())
    assert out["result"]["status"] == "released"


@pytest.mark.asyncio
async def test_duplicate_photo_fails_check(tmp_path):
    store = HashStore(Path(tmp_path) / "h.sqlite")
    store.remember(photo_hash({"extracted_text": "shelf photo"}), "old")
    llm = FakeLLM(json_replies=[{"total_cents": 50000, "supplier": "Nakuru Books Ltd",
                                "date": "2026-10-15"}])
    agent = MilestoneAgent(mcp=FakeMcpClient(), llm=llm, store=store)
    out = await agent.check(milestone())
    assert out["checks"]["photo_not_duplicate"] is False


@pytest.mark.asyncio
async def test_extraction_failure_sets_all_checks_false(tmp_path):
    store = HashStore(Path(tmp_path) / "h.sqlite")
    agent = MilestoneAgent(mcp=FakeMcpClient(), llm=FakeLLM(), store=store)
    out = await agent.check(milestone())
    assert out["checks"]["receipt_total_within_10pct"] is False
    assert out["checks"]["supplier_matches_plan"] is False
    assert out["checks"]["dated_in_window"] is False


@pytest.mark.asyncio
async def test_summary_names_failed_checks(tmp_path):
    store = HashStore(Path(tmp_path) / "h.sqlite")
    llm = FakeLLM(json_replies=[{"total_cents": 90000, "supplier": "Wrong", "date": "2026-10-15"}])
    agent = MilestoneAgent(mcp=FakeMcpClient(), llm=llm, store=store)
    out = await agent.check(milestone())
    assert "receipt_total_within_10pct" in out["summary"]
    assert "supplier_matches_plan" in out["summary"]
