"""Natural-language mandate setup: prose plus the current form in, a draft mandate out.

The contract is the one web/src/components/MandateDraft.tsx already calls:
  POST /agents/mandate/draft  {text, current: {...}}
    -> {proposed, warnings, rejected, used_llm}

Nothing here writes. The web puts the draft into the form for the donor to confirm; the
mandate itself is created by the API. So the agent may fill a field but never silently drop
one: every value it could not apply is named in rejected or explained in warnings.

Ids: current.categories carries whatever the web had - API category ids when the web talks to
a real API, slug strings ("education") when it runs on mock data. This module never rewrites
them: /categories is used only for name -> id matching, so a category the donor already chose
keeps its original value.

Tags: the API has no public tag endpoint, so a named tag is checked against the tags visible
on projects. A tag that cannot be seen is kept and flagged, never dropped silently.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

from pydantic import BaseModel, Field

from ..core import Core, CoreError, build_core
from ..llm import LLM, LLMUnavailable, build_llm, data_block
from ..mcp_client import FakeMcpClient, McpClient, build_client

log = logging.getLogger(__name__)

MAX_TEXT = 1000
# The web aborts at 20 s. These budgets leave room to build and return the answer.
LOOKUP_SECONDS = 3.0
LLM_SECONDS = 12.0
CATEGORY_TTL_SECONDS = 600.0

# Mirrors the API limits, so a draft the donor sees is a draft the API will accept.
MAX_TAG_LENGTH = 32
MAX_TAGS = 20
MAX_WEIGHT_SHIFT = 20.0

DEFAULT_WEIGHTS = {
    "few_backers": 0.25,
    "progress": 0.20,
    "urgency": 0.20,
    "evidence": 0.20,
    "days_since_funded": 0.15,
}


class Current(BaseModel):
    """The form as it stands. Every field is optional: the web may send a partial form."""

    monthly_budget_cents: int | None = Field(default=None, gt=0)
    per_project_max_cents: int | None = Field(default=None, gt=0)
    approval_threshold_cents: int | None = Field(default=None, ge=0)
    categories: list[int | str] = Field(default_factory=list)
    excluded_tags: list[str] = Field(default_factory=list)


class DraftIn(BaseModel):
    text: str = Field(default="", max_length=MAX_TEXT)
    current: Current = Field(default_factory=Current)


class Proposal(BaseModel):
    """What the model may fill. Omitted means: leave the form as it is."""

    monthly_budget_cents: int | None = None
    per_project_max_cents: int | None = None
    approval_threshold_cents: int | None = None
    categories: list[int | str] = Field(default_factory=list)
    excluded_tags: list[str] = Field(default_factory=list)
    weight_overrides: dict[str, float] | None = None


LLM_SYSTEM = (
    "Turn a donor own words into a draft of their giving rules. Reply with JSON only. "
    "Use a field only when the text states it; leave it null or empty otherwise. Never "
    "invent an amount, a category or a tag. Amounts are whole cents: forty dollars is 4000. "
    "If the text says to skip something, put it in excluded_tags."
)


def _now() -> float:
    return time.monotonic()


class CategoryCache:
    """Name -> id lookup, refreshed at most once per TTL. Never raises to the caller."""

    def __init__(self, ttl: float = CATEGORY_TTL_SECONDS, now=_now) -> None:
        self.ttl = ttl
        self._now = now
        self._values: list[dict] = []
        self._at = 0.0

    async def get(self, core: Core) -> list[dict]:
        if self._values and self._now() - self._at < self.ttl:
            return self._values
        try:
            values = await asyncio.wait_for(core.categories(), timeout=LOOKUP_SECONDS)
        except (CoreError, asyncio.TimeoutError, OSError) as exc:
            log.warning("category lookup failed: %s", exc)
            return []
        except Exception as exc:
            log.warning("category lookup failed: %s", exc)
            return []
        self._values = values
        self._at = self._now()
        return values

    def clear(self) -> None:
        self._values = []
        self._at = 0.0


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def match_category(value: int | str, categories: list[dict]) -> int | str | None:
    """Resolve a name or slug to an id. An id, or an id-shaped string, passes through.

    Returns None when the value cannot be matched, so the caller can refuse to guess.
    """
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    wanted = slug(text)
    for category in categories:
        name = str(category.get("name") or "")
        if slug(name) == wanted or str(category.get("id")) == text:
            return category.get("id")
    return None


def clean_tag(tag: object) -> str:
    return str(tag or "").strip().lower()[:MAX_TAG_LENGTH]


def safe_weights(values: dict) -> tuple[dict[str, float], list[tuple[str, float]]]:
    """Keep the overrides the API will accept; report the ones it would reject."""
    kept: dict[str, float] = {}
    shifted: list[tuple[str, float]] = []
    for key, raw in (values or {}).items():
        if key not in DEFAULT_WEIGHTS:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        default = DEFAULT_WEIGHTS[key]
        low, high = max(0.0, default - MAX_WEIGHT_SHIFT), default + MAX_WEIGHT_SHIFT
        if value < low or value > high:
            shifted.append((key, value))
            value = min(max(value, low), high)
        kept[key] = value
    return kept, shifted


class MandateDraftAgent:
    def __init__(self, core: Core | None = None, llm: LLM | None = None,
                 mcp: McpClient | FakeMcpClient | None = None) -> None:
        self.core = core if core is not None else build_core()
        self.llm = llm if llm is not None else build_llm()
        self.mcp = mcp if mcp is not None else build_client()
        self.categories = CategoryCache()

    async def draft(self, text: str, current: Current) -> dict:
        text = (text or "").strip()[:MAX_TEXT]
        proposal, used_llm = await self._propose(text)
        return await self._merge(proposal, current, used_llm, bool(text))

    async def _propose(self, text: str) -> tuple[Proposal | None, bool]:
        if not text:
            return None, False
        try:
            reply = await asyncio.wait_for(
                self.llm.complete_json(LLM_SYSTEM, data_block("donor text", text), Proposal),
                timeout=LLM_SECONDS)
            return reply, True
        except (LLMUnavailable, asyncio.TimeoutError) as exc:
            log.info("draft LLM unavailable, keeping the form as it is: %s", exc)
            return None, False

    async def _merge(self, proposal: Proposal | None, current: Current, used_llm: bool,
                     had_text: bool) -> dict:
        warnings: list[str] = []
        rejected: list[str] = []
        proposed: dict[str, Any] = {}

        # Categories: the donor values are kept verbatim; a newly named one is resolved.
        cats = list(current.categories)
        cats = await self._add_categories(proposal.categories if proposal else [], cats,
                                          rejected)
        if cats:
            proposed["categories"] = cats

        if proposal is not None:
            for key in ("monthly_budget_cents", "per_project_max_cents",
                        "approval_threshold_cents"):
                value = getattr(proposal, key)
                if value is not None and value != getattr(current, key):
                    proposed[key] = value

        tags = await self._add_tags(proposal.excluded_tags if proposal else [],
                                    current.excluded_tags, warnings, rejected)
        if tags:
            proposed["excluded_tags"] = tags

        if proposal is not None and proposal.weight_overrides:
            overrides, shifted = safe_weights(proposal.weight_overrides)
            if overrides:
                proposed["weight_overrides"] = overrides
            for key, asked in shifted:
                using = overrides.get(key, DEFAULT_WEIGHTS.get(key, 0.0))
                text = (key + " was set to " + str(round(asked, 4))
                        + ", but a weight may shift at most 20 from its default; using "
                        + str(round(using, 4)))
                warnings.append(text)

        # 503 is only for "read nothing at all". An unchanged form is still an answer.
        if had_text and not used_llm and not proposed:
            raise LLMUnavailable("the text could not be read and nothing was proposed")

        return {"proposed": proposed, "warnings": warnings, "rejected": rejected,
                "used_llm": used_llm}

    async def _add_categories(self, wanted: list, cats: list, rejected: list) -> list:
        if not wanted:
            return cats
        known = await self.categories.get(self.core)
        for value in wanted:
            resolved = match_category(value, known)
            if resolved is None:
                rejected.append("category " + str(value) + ": no such category")
            elif resolved not in cats:
                cats.append(resolved)
        return cats

    async def _add_tags(self, wanted: list[str], existing: list[str], warnings: list,
                        rejected: list) -> list[str]:
        # Existing tags are normalised AND deduped: "Girls" and "  Girls " are one tag.
        tags: list[str] = []
        for raw in existing:
            tag = clean_tag(raw)
            if tag and tag not in tags:
                tags.append(tag)
        additions = [t for t in (clean_tag(x) for x in wanted) if t]
        if not additions:
            return tags
        visible = await self._visible_tags()
        # A failed lookup means "cannot see any tag", not "every tag is fine": the donor must
        # be told each tag went in unverified rather than silently trusting it.
        unseen = visible if visible is not None else set()
        for tag in additions:
            if tag in tags:
                continue
            if len(tags) >= MAX_TAGS:
                rejected.append("tag " + tag + ": only 20 excluded tags are allowed")
                continue
            tags.append(tag)
            if tag not in unseen:
                warnings.append("couldn't verify tag " + tag)
        return tags

    async def _visible_tags(self) -> set[str] | None:
        """Tags on projects we can see, or None when the search itself failed."""
        try:
            found = await asyncio.wait_for(
                self.mcp.call("search_projects", sort="urgency", limit=100),
                timeout=LOOKUP_SECONDS)
        except (asyncio.TimeoutError, Exception) as exc:
            log.warning("tag lookup failed, tags will be unverified: %s", exc)
            return None
        seen: set[str] = set()
        for project in found or []:
            if not isinstance(project, dict):
                continue
            for tag in project.get("tags") or []:
                if isinstance(tag, str) and tag.strip():
                    seen.add(tag.strip().lower())
        return seen

    async def aclose(self) -> None:
        try:
            await self.core.aclose()
        except Exception as exc:
            log.warning("core close failed: %s", exc)
