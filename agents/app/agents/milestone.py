"""Milestone Agent: extract receipt fields with the LLM, decide the four checks in code.

MilestoneSource is an interface because the evidence-submitted endpoint does not exist yet
(spec section 7). FakeMilestoneSource serves seeded milestones until Person 1 ships it.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from ..llm import LLM, LLMUnavailable, build_llm, data_block

log = logging.getLogger(__name__)

TOLERANCE = 0.10
SUPPLIER_RATIO = 0.85
DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "milestones.sqlite"


class Receipt(BaseModel):
    total_cents: int | None = None
    supplier: str | None = None
    date: str | None = None


class MilestoneSource(Protocol):
    async def evidence_submitted(self) -> list[dict]:
        ...


class FakeMilestoneSource:
    def __init__(self, milestones: list[dict] | None = None) -> None:
        self.milestones = list(milestones or [])

    async def evidence_submitted(self) -> list[dict]:
        return list(self.milestones)


def _parse_date(text: Any) -> datetime | None:
    if not text:
        return None
    raw = str(text).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def total_within_10pct(receipt_total_cents: int | None, tranche_cents: int) -> bool:
    if receipt_total_cents is None or tranche_cents <= 0:
        return False
    return abs(receipt_total_cents - tranche_cents) <= TOLERANCE * tranche_cents


def supplier_matches(receipt_supplier: str | None, planned_supplier: str | None) -> bool:
    if not receipt_supplier or not planned_supplier:
        return False
    a = re.sub(r"\s+", " ", receipt_supplier.strip().lower())
    b = re.sub(r"\s+", " ", planned_supplier.strip().lower())
    return difflib.SequenceMatcher(None, a, b).ratio() >= SUPPLIER_RATIO


def dated_in_window(receipt_date: Any, window_start: Any, due_date: Any) -> bool:
    when = _parse_date(receipt_date)
    start = _parse_date(window_start)
    end = _parse_date(due_date)
    if when is None:
        return False
    if start and when < start:
        return False
    if end and when > end:
        return False
    return True


class HashStore:
    """Perceptual hashes of seen documents, in a local sqlite file."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or DB_PATH)

    def _conn(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute("CREATE TABLE IF NOT EXISTS hashes (hash TEXT PRIMARY KEY, doc_id TEXT)")
        return conn

    def seen_before(self, doc_hash: str) -> bool:
        with self._conn() as conn:
            row = conn.execute("SELECT 1 FROM hashes WHERE hash = ?", (doc_hash,)).fetchone()
        return row is not None

    def remember(self, doc_hash: str, doc_id: str) -> None:
        with self._conn() as conn:
            conn.execute("INSERT OR IGNORE INTO hashes (hash, doc_id) VALUES (?, ?)", (doc_hash, doc_id))


def photo_hash(photo: dict) -> str | None:
    """Prefer a real perceptual hash; fall back to a hash of the text version (DeepSeek is text-only)."""
    text = photo.get("extracted_text") or photo.get("text")
    if text:
        return "text:" + hashlib.sha256(str(text).encode()).hexdigest()
    url = photo.get("file_url")
    return "url:" + hashlib.sha256(str(url).encode()).hexdigest() if url else None


class MilestoneAgent:
    def __init__(self, mcp=None, llm: LLM | None = None, source: MilestoneSource | None = None,
                 store: HashStore | None = None) -> None:
        from ..mcp_client import build_client

        self.mcp = mcp or build_client()
        self.llm = llm or build_llm()
        self.source = source or FakeMilestoneSource()
        self.store = store or HashStore()

    async def scan(self) -> list[dict]:
        results = []
        for milestone in await self.source.evidence_submitted():
            results.append(await self.check(milestone))
        return results

    async def check(self, milestone: dict) -> dict:
        amount = int(milestone.get("amount_cents") or 0)
        documents = milestone.get("documents") or []
        receipt = await self._extract(milestone)

        photo = next((d for d in documents if d.get("kind") == "photo"), None)
        doc_hash = photo_hash(photo) if photo else None
        not_duplicate = bool(doc_hash) and not self.store.seen_before(doc_hash)

        checks = {
            "receipt_total_within_10pct": total_within_10pct(receipt.total_cents, amount),
            "supplier_matches_plan": supplier_matches(receipt.supplier, milestone.get("planned_supplier")),
            "photo_not_duplicate": not_duplicate,
            "dated_in_window": dated_in_window(receipt.date, milestone.get("window_start"),
                                              milestone.get("due_date")),
        }
        summary = await self._summary(milestone, receipt, checks)

        answer = await self.mcp.call(
            "request_milestone_payout",
            milestone_id=milestone.get("milestone_id"),
            receipt_total_within_10pct=checks["receipt_total_within_10pct"],
            supplier_matches_plan=checks["supplier_matches_plan"],
            photo_not_duplicate=checks["photo_not_duplicate"],
            dated_in_window=checks["dated_in_window"],
            summary=summary,
        )
        if doc_hash and not_duplicate:
            self.store.remember(doc_hash, str(milestone.get("milestone_id")))
        return {"milestone_id": milestone.get("milestone_id"), "checks": checks,
                "summary": summary, "result": answer}

    async def _extract(self, milestone: dict) -> Receipt:
        texts = [d.get("extracted_text_or_fields") for d in milestone.get("documents") or []
                 if d.get("extracted_text_or_fields")]
        if not texts:
            log.info("no receipt text on milestone %s", milestone.get("milestone_id"))
            return Receipt()
        system = (
            "Extract the receipt total in integer cents, the supplier name and the receipt date "
            "(ISO YYYY-MM-DD) from the text. Use null when a field is absent. Never guess."
        )
        try:
            return await self.llm.complete_json(
                system, data_block("receipt", chr(10).join(str(t) for t in texts)), Receipt,
            )
        except LLMUnavailable:
            log.info("receipt extraction failed for %s", milestone.get("milestone_id"))
            return Receipt()

    async def _summary(self, milestone: dict, receipt: Receipt, checks: dict) -> str:
        failed = [k for k, v in checks.items() if not v]
        if not failed:
            return "All four evidence checks passed for milestone " + str(milestone.get("milestone_id"))
        return ("Milestone " + str(milestone.get("milestone_id")) + " failed: " + ", ".join(failed)
                + ". Receipt fields: " + json.dumps(receipt.model_dump()))
