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
# The one retry is allowed a longer budget: a cold core often needs more than 3 s to wake.
CATEGORY_RETRY_SECONDS = 8.0
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
    "invent an amount or a tag. Amounts are whole cents: forty dollars is 4000. "
    "If the text says to skip something, put it in excluded_tags. "
    "For categories, copy the exact name from the allowed list below into categories. "
    "Never use a donor's phrase as a category name: for clean water, return Water, "
    "not Clean water. If the donor names something that is not on the list, leave "
    "categories empty."
)


def system_prompt(categories: list[dict]) -> str:
    """The system prompt with the catalogue spliced in, so names come back exactly."""
    names = sorted({str(c.get("name")).strip() for c in categories
                    if str(c.get("name") or "").strip()})
    if not names:
        return LLM_SYSTEM
    return LLM_SYSTEM + "\n\nAllowed categories (use these names exactly): " + ", ".join(names)


def _now() -> float:
    return time.monotonic()


class CategoryCache:
    """Name -> id lookup, refreshed at most once per TTL. Never raises to the caller.

    Only a real catalogue is cached. A failed or empty answer is thrown away so the next
    request tries again: a cold core that fails once must not pin "no categories" for the
    whole TTL, which is worse than the extra call.
    """

    def __init__(self, ttl: float = CATEGORY_TTL_SECONDS, now=_now,
                 timeout: float = CATEGORY_RETRY_SECONDS) -> None:
        self.ttl = ttl
        self._now = now
        self.timeout = timeout
        self._values: list[dict] = []
        self._at = 0.0

    async def get(self, core: Core) -> list[dict]:
        """The catalogue, or [] when it could not be read. Callers that must tell the two
        apart use lookup()."""
        values, _ = await self.lookup(core)
        return values

    async def lookup(self, core: Core) -> tuple[list[dict], bool]:
        """(catalogue, verified). Never caches a failure or an empty answer.

        One retry with the longer budget: a cold core usually answers on the second ask,
        and wasting the whole request on one timeout would be a worse trade.
        """
        if self._values and self._now() - self._at < self.ttl:
            return self._values, True
        for attempt in range(2):
            if attempt:
                log.info("category lookup retrying with a %.1fs budget", self.timeout)
            try:
                values = await asyncio.wait_for(core.categories(), timeout=self.timeout)
            except (CoreError, asyncio.TimeoutError, OSError) as exc:
                log.warning("category lookup failed: %s", exc)
                continue
            except Exception as exc:
                log.warning("category lookup failed: %s", exc)
                continue
            # An empty answer is a failure too: a deployed core always has categories, so
            # caching it would pin the bug for the full TTL.
            if not values:
                log.warning("category lookup returned nothing, treating it as unavailable")
                continue
            self._values = list(values)
            self._at = self._now()
            return list(values), True
        return [], False

    def clear(self) -> None:
        self._values = []
        self._at = 0.0


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _singular(word: str) -> str:
    """Crude singular form, used only to compare one word against another."""
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("es") and word[-3] in "sxzh":
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def match_category(value: int | str, categories: list[dict]) -> int | str | None:
    """Resolve one returned category to an id, or None when the answer is not certain.

    In order: an id or id-shaped string passes through; an exact name match (case and
    spacing ignored) wins; then a whole-word match, so "Clean water" finds Water. Whole
    words are compared in singular form, so "waters" also finds Water, but a fragment of a
    longer word never matches ("clean" must not hit "cleaner").

    Ambiguity is never guessed: a string that matches more than one category returns None,
    and the caller reports it as rejected.
    """
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)

    by_name: dict[str, object] = {}
    for category in categories:
        name = str(category.get("name") or "").strip()
        if not name:
            continue
        if str(category.get("id")) == text:
            return category.get("id")
        by_name.setdefault(slug(name), category.get("id"))

    wanted = slug(text)
    if wanted in by_name:
        return by_name[wanted]

    words = {_singular(w) for w in wanted.split("-") if w}
    hits = set()
    for name_slug, cat_id in by_name.items():
        parts = {_singular(w) for w in name_slug.split("-") if w}
        if parts and parts.issubset(words):
            hits.add(cat_id)
    if len(hits) == 1:
        return hits.pop()
    return None


def clean_tag(tag: object) -> str:
    return str(tag or "").strip().lower()[:MAX_TAG_LENGTH]


# --- rule-based fallback -----------------------------------------------------------------

# A currency amount: an optional dollar sign and a whole-dollar figure, with optional cents.
# "$10", "10 dollars", "$3.50". Cents are ignored: the API takes whole cents.
_AMOUNT = r"\$?[ \s]*([0-9]{1,7})(?:\.[0-9]{1,2})?"
_MONTHLY = re.compile(
    _AMOUNT + r"[ \s]*(?:dollars?|bucks?)?[\s]*(?:per|a|each|every)[\s]*(?:month|mo)\b"
    r"|\bmonthly[\s]*(?:budget[\s]*)?(?:of[\s]*)?" + _AMOUNT,
    re.IGNORECASE)
_PER_PROJECT = re.compile(
    _AMOUNT + r"[ \s]*(?:dollars?|bucks?)?[\s]*(?:per|a|each|every)[\s]*project\b"
    r"|\bper[\s-]*project[\s]*(?:max(?:imum)?[\s]*)?(?:of[\s]*)?" + _AMOUNT,
    re.IGNORECASE)
_PERCENT = re.compile(r"([0-9]{1,3})[\s]*%")


def _first_int(match):
    """The first non-empty group that is a number."""
    if match is None:
        return None
    for group in match.groups():
        if group:
            return int(group)
    return None


def parse_amounts(text: str) -> dict:
    """Read amounts out of plain prose. No model involved, so it cannot fail."""
    found = {}
    monthly = _first_int(_MONTHLY.search(text))
    if monthly:
        found["monthly_budget_cents"] = monthly * 100
    per_project = _first_int(_PER_PROJECT.search(text))
    if per_project:
        found["per_project_max_cents"] = per_project * 100
    percent = _PERCENT.search(text)
    if percent and "monthly_budget_cents" in found:
        # "gifts over 10% wait for me" -> a threshold relative to the monthly budget.
        found["approval_threshold_cents"] = found["monthly_budget_cents"] * int(percent.group(1)) // 100
    return found


def parse_categories(text: str, categories: list) -> list:
    """Category names mentioned in the text, matched case-insensitively."""
    if not text or not categories:
        return []
    lowered = text.lower()
    words = set(slug(lowered).split("-"))
    found = []
    for category in categories:
        name = str(category.get("name") or "")
        if not name:
            continue
        if name.lower() in lowered or slug(name) in words:
            value = category.get("id")
            if value not in found:
                found.append(value)
    return found


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
        """The model first; plain parsing when it is unreachable or too slow.

        The fallback is not decoration: with no API key the whole endpoint still has to read
        "$10 a month, $3 per project", so it never returns None for non-empty text.
        """
        if not text:
            return None, False
        # The catalogue goes into the prompt so the model answers with exact names.
        known = await self.categories.get(self.core)
        try:
            reply = await asyncio.wait_for(
                self.llm.complete_json(system_prompt(known), data_block("donor text", text),
                                       Proposal),
                timeout=LLM_SECONDS)
            return reply, True
        except (LLMUnavailable, asyncio.TimeoutError) as exc:
            log.info("draft LLM unavailable, falling back to plain parsing: %s", exc)
        return await self._fallback(text, known), False

    async def _fallback(self, text: str, known: list) -> Proposal:
        """Read what plain prose allows: whole-dollar amounts and named categories."""
        amounts = parse_amounts(text)
        names = parse_categories(text, known)
        categories: list = []
        for name in names:
            resolved = match_category(name, known)
            if resolved is not None and resolved not in categories:
                categories.append(resolved)
        return Proposal(
            monthly_budget_cents=amounts.get("monthly_budget_cents"),
            per_project_max_cents=amounts.get("per_project_max_cents"),
            approval_threshold_cents=amounts.get("approval_threshold_cents"),
            categories=categories,
        )

    async def _merge(self, proposal: Proposal | None, current: Current, used_llm: bool,
                     had_text: bool) -> dict:
        warnings: list[str] = []
        rejected: list[str] = []
        proposed: dict[str, Any] = {}

        # Categories: the donor values are kept verbatim; a newly named one is resolved.
        cats = list(current.categories)
        cats = await self._add_categories(proposal.categories if proposal else [], cats,
                                          warnings, rejected)
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

        # 503 means "nothing could read this text": no model answer and no rule-based read.
        # A model that answered but proposed no change is still a successful read.
        if had_text and not used_llm and not proposed:
            raise LLMUnavailable("the text could not be read and nothing was proposed")

        return {"proposed": proposed, "warnings": warnings, "rejected": rejected,
                "used_llm": used_llm}

    async def _add_categories(self, wanted: list, cats: list, warnings: list,
                              rejected: list) -> list:
        if not wanted:
            return cats
        known, verified = await self.categories.lookup(self.core)
        for value in wanted:
            if not verified:
                # The catalogue could not be read. Saying "no such category" would blame
                # the donor for the core being cold, so warn and leave the field alone.
                warnings.append(
                    "couldn" + "t verify category " + str(value) + ", try again in a minute")
                continue
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
