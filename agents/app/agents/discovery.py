"""Discovery chat: code turns text into filters, code searches and ranks, the LLM explains.

Nothing here can move money or write state: the chat path only calls search_projects (read-only).
Response keeps the shape web/src/components/GivingAssistant.tsx parses:
  {filters: {str: str}, projects: [{id, ...}], explanation: str}
plus reply / projectIds, which the web ignores.

Ranking is plain code, never the model: word overlap between the message and each project's
title, tags, cause, region and beneficiary group, with urgency as the tie-break.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from ..llm import LLM, LLMUnavailable, build_llm, data_block
from ..mcp_client import build_client

log = logging.getLogger(__name__)

MAX_PROJECTS = 5

# Words that carry no search signal. Kept small on purpose: matching is fuzzy.
CUE_WORDS = {
    "i", "me", "my", "we", "us", "our", "you", "your", "it", "its",
    "a", "an", "the", "and", "or", "but", "for", "of", "to", "in", "on", "at",
    "with", "about", "care", "cares", "caring", "like", "want", "wants", "would",
    "help", "helps", "support", "supports", "give", "giving", "donate", "donating",
    "please", "some", "any", "is", "are", "be", "can", "could", "should",
}

# Suffixes stripped when comparing, so "girls" matches "girl".
SUFFIXES = ("ing", "ers", "er", "ies", "es", "s")


class Filters(BaseModel):
    category_id: int | None = None
    cause: str | None = None
    beneficiary_group: str | None = None
    region: str | None = None
    exclude_tags: list[str] = Field(default_factory=list)
    q: str | None = None


class _FilterReply(BaseModel):
    category_id: int | None = None
    cause: str | None = None
    beneficiary_group: str | None = None
    region: str | None = None
    exclude_tags: list[str] = Field(default_factory=list)
    q: str | None = None


def words(text: object) -> list[str]:
    """Lowercased content words, crude stem applied. Order preserved, duplicates kept."""
    if not isinstance(text, str):
        return []
    out: list[str] = []
    for raw in re.findall(r"[a-z0-9]+", text.lower()):
        if raw in CUE_WORDS or len(raw) < 3:
            continue
        out.append(_stem(raw))
    return out


def _stem(word: str) -> str:
    for suffix in SUFFIXES:
        if len(word) - len(suffix) >= 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def project_text(project: dict) -> list[str]:
    """Every field the ranker may match on, flattened to words."""
    parts: list[str] = []
    for key in ("title", "cause", "region", "beneficiary_group"):
        parts.extend(words(project.get(key)))
    for tag in project.get("tags") or []:
        parts.extend(words(tag))
    return parts


def overlap_score(message_words: list[str], project: dict) -> int:
    """How many distinct message concepts the project text contains."""
    if not message_words:
        return 0
    wanted = set(message_words)
    return len(wanted & set(project_text(project)))


def rank_projects(projects: list[dict], message: str) -> list[dict]:
    """Relevant first, urgency breaks ties, id breaks exact ties (stable output)."""
    message_words = words(message)
    ranked = sorted(
        projects,
        key=lambda p: (
            -overlap_score(message_words, p),
            -(p.get("urgency") or 0),
            int(p.get("id") or 0),
        ),
    )
    return ranked


def topic_of(message: str, projects: list[dict]) -> str:
    """Short phrase naming what the message asked for, from words the results share."""
    message_words = words(message)
    if not message_words:
        return ""
    common: list[str] = []
    for word in message_words:
        if word in common:
            continue
        if any(word in project_text(p) for p in projects):
            common.append(word)
    if not common:
        return ""
    return " ".join(common[:3])


def flatten_filters(filters: Filters, topic: str = "") -> dict[str, str]:
    """Chips are rendered with Object.values(filters), so every value must be a string."""
    out: dict[str, str] = {}
    if filters.category_id is not None:
        out["category_id"] = str(filters.category_id)
    for key in ("cause", "beneficiary_group", "region", "q"):
        value = getattr(filters, key)
        if value:
            out[key] = str(value)
    if filters.exclude_tags:
        out["excluding"] = ", ".join(str(t) for t in filters.exclude_tags)
    if topic:
        out["topic"] = topic
    return out


def keep_known_values(filters: _FilterReply, seen: dict[str, set[str]]) -> Filters:
    """Drop facet values the search results never showed (the model may invent them)."""
    data = filters.model_dump()
    clean: dict[str, Any] = {}
    for key in ("cause", "beneficiary_group", "region"):
        value = data.get(key)
        if value and str(value).strip().lower() in seen.get(key, set()):
            clean[key] = str(value).strip().lower()
    tags = [str(t).strip().lower() for t in data.get("exclude_tags") or []]
    clean["exclude_tags"] = [t for t in tags if t and t in seen.get("tag", set())]
    if data.get("category_id") is not None:
        clean["category_id"] = data["category_id"]
    q = data.get("q")
    if q and str(q).strip():
        clean["q"] = str(q).strip()
    return Filters(**clean)


def facets_of(projects: list[dict]) -> dict[str, set[str]]:
    seen: dict[str, set[str]] = {"cause": set(), "beneficiary_group": set(), "region": set(), "tag": set()}
    for project in projects:
        for key in ("cause", "beneficiary_group", "region"):
            value = project.get(key)
            if isinstance(value, str) and value.strip():
                seen[key].add(value.strip().lower())
        for tag in project.get("tags") or []:
            if isinstance(tag, str):
                seen["tag"].add(tag.strip().lower())
    return seen


def search_args(filters: Filters) -> dict[str, Any]:
    return {
        "category_id": filters.category_id,
        "cause": filters.cause,
        "beneficiary_group": filters.beneficiary_group,
        "region": filters.region,
        "exclude_tags": filters.exclude_tags or None,
        "q": filters.q,
        "sort": "urgency",
        "limit": 100,
    }


def money(cents: object) -> str:
    """Cents to a dollar string. The only place the conversion happens."""
    try:
        value = int(cents or 0)
    except (TypeError, ValueError):
        value = 0
    sign = "-" if value < 0 else ""
    value = abs(value)
    return sign + "$" + str(value // 100) + "." + str(value % 100).zfill(2)


class DiscoveryAgent:
    def __init__(self, mcp=None, llm: LLM | None = None) -> None:
        self.mcp = mcp or build_client()
        self.llm = llm or build_llm()

    async def chat(self, message: str) -> dict:
        message = (message or "").strip()[:1000]
        if not message:
            return self._empty("Ask me about a cause, a group of people, or a region.")

        filters = await self._filters(message)
        projects = await self._search(filters)
        projects = rank_projects(projects, message)[:MAX_PROJECTS]
        topic = topic_of(message, projects)
        explanation = await self._explain(message, projects)

        flat = flatten_filters(filters, topic)
        return {
            "filters": flat,
            "projects": projects,
            "explanation": explanation,
            "reply": explanation,
            "projectIds": [str(p.get("id")) for p in projects],
        }

    async def _filters(self, message: str) -> Filters:
        system = (
            "Turn a donor message into search filters. Only use these keys: category_id, "
            "cause, beneficiary_group, region, exclude_tags, q. Leave a field null when the "
            "message does not mention it. Never invent values."
        )
        try:
            reply = await self.llm.complete_json(system, data_block("donor message", message), _FilterReply)
        except LLMUnavailable:
            log.info("LLM unavailable, falling back to keyword search")
            return Filters(q=message)
        seen = await self._facet_values()
        return keep_known_values(reply, seen)

    async def _facet_values(self) -> dict[str, set[str]]:
        """Facet values are only known from results; one broad search gives the vocabulary."""
        try:
            sample = await self.mcp.call("search_projects", sort="urgency", limit=100)
        except Exception as exc:
            log.warning("facet sample failed: %s", exc)
            sample = []
        return facets_of(sample or [])

    async def _search(self, filters: Filters) -> list[dict]:
        try:
            found = await self.mcp.call("search_projects", **search_args(filters))
        except Exception as exc:
            log.warning("search_projects failed: %s", exc)
            return []
        seen: dict[int, dict] = {}
        for project in found or []:
            try:
                seen[int(project["id"])] = project
            except (KeyError, TypeError, ValueError):
                continue
        return list(seen.values())

    async def _explain(self, message: str, projects: list[dict]) -> str:
        if not projects:
            return "No open project matches that yet. Try a cause, who you would like to help, or a region."
        # Amounts are converted here, once. The model only ever sees dollar strings.
        facts = [
            {
                "id": p.get("id"),
                "title": p.get("title"),
                "cause": p.get("cause"),
                "region": p.get("region"),
                "beneficiary_group": p.get("beneficiary_group"),
                "backers": p.get("backer_count"),
                "raised": money(p.get("raised_cents")),
                "goal": money(p.get("goal_cents")),
            }
            for p in projects
        ]
        system = (
            "You explain search results to a donor in at most three sentences. Use only the "
            "given fields. Do not rank, score, promise outcomes or suggest donating an amount. "
            "Amounts are already formatted for display: quote them exactly as given. Never "
            "convert, recompute or restate cents, and never invent a number."
        )
        try:
            text = await self.llm.complete_text(
                system, data_block("projects", json.dumps(facts)),
            )
            if text:
                return text
        except LLMUnavailable:
            log.info("LLM unavailable, using template explanation")
        return self._template(projects)

    @staticmethod
    def _template(projects: list[dict]) -> str:
        count = len(projects)
        head = "Here are " + str(count) + " open project" + ("" if count == 1 else "s") + "."
        first = projects[0]
        backers = first.get("backer_count") or 0
        if backers < 5:
            return (head + " " + str(first.get("title")) + " has only " + str(backers) + " backer"
                    + ("" if backers == 1 else "s") + ", so a gift counts extra in matching.")
        return head

    @staticmethod
    def _empty(text: str) -> dict:
        return {"filters": {}, "projects": [], "explanation": text, "reply": text, "projectIds": []}
