"""Watchdog: plain rules over donation events. No LLM.

Events come through EventsSource; the core API serves them at GET /internal/donation-events.
Every donor reference is an internal Donor.id integer, never a PayPal payer id.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from . import graph

log = logging.getLogger(__name__)

# Thresholds in one place (spec 5.3).
THRESHOLDS: dict[str, Any] = {
    "new_payer_burst": {"window_minutes": 30, "max_donations": 8, "max_amount_cents": 500,
                        "max_donor_age_hours": 24},
    "reciprocal_backing": {"min_donors": 2, "min_total": 3},
    "refund_spike": {"window_hours": 24, "min_donations": 5, "refund_ratio": 0.30},
}


class EventsSource(Protocol):
    async def since(self, iso: str) -> list[dict]:
        ...


# The feed caps at `limit` (1000 is its ceiling) newest-first, so a full page may be a truncated
# window: the oldest events the scan needs could be missing, which weakens any rule that counts
# people. Worth a warning, not an error.
FEED_PAGE_LIMIT = 1000


class CoreEventsSource:
    """Events from the core API: GET /internal/donation-events?since=<iso>&limit=1000.

    The endpoint already sends the Bearer header for any /internal path, so the token is not
    handled here. Fails soft: a core outage means no events this scan, not a crashed job, and
    the rules simply see nothing rather than acting on partial data.
    """

    def __init__(self, core=None, limit: int = FEED_PAGE_LIMIT) -> None:
        from ..core import build_core

        self.core = core or build_core()
        self.limit = limit

    async def since(self, iso: str) -> list[dict]:
        from ..core import CoreError

        try:
            data = await self.core.get("/internal/donation-events", since=iso, limit=self.limit)
        except CoreError as exc:
            log.warning("donation-events unavailable, scanning nothing this run: %s", exc)
            return []
        if not isinstance(data, list):
            log.warning("donation-events returned %s, expected a list", type(data).__name__)
            return []
        events = [e for e in data if isinstance(e, dict)]
        if len(events) >= self.limit:
            log.warning(
                "donation-events returned the full %s-event page: older events in the window may "
                "be missing, so donor counts can be low",
                len(events),
            )
        return events

    async def aclose(self) -> None:
        await self.core.aclose()


class FakeEventsSource:
    """Test/seeded events. Each event: donation_id, project_id, donor_id, status, amount_cents,
    captured_at, is_guest, donor_created_at, owner_donor_id."""

    def __init__(self, events: list[dict] | None = None) -> None:
        self.events = list(events or [])

    async def since(self, iso: str) -> list[dict]:
        return list(self.events)

    async def aclose(self) -> None:
        """Nothing to close. Present so the scheduler can close either source the same way."""


def _parse(ts: Any) -> datetime | None:
    if not ts:
        return None
    try:
        value = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def new_payer_burst(events: list[dict], now: datetime | None = None) -> list[dict]:
    cfg = THRESHOLDS["new_payer_burst"]
    now = now or datetime.now(timezone.utc)
    window = timedelta(minutes=cfg["window_minutes"])
    by_project: dict[int, list[dict]] = {}
    for event in events:
        captured = _parse(event.get("captured_at"))
        created = _parse(event.get("donor_created_at"))
        if captured is None or created is None:
            continue
        if (event.get("amount_cents") or 0) > cfg["max_amount_cents"]:
            continue
        if (now - created) > timedelta(hours=cfg["max_donor_age_hours"]):
            continue
        by_project.setdefault(int(event["project_id"]), []).append({**event, "_t": captured})

    hits = []
    for project_id, items in by_project.items():
        items.sort(key=lambda e: e["_t"])
        for i, start in enumerate(items):
            in_window = [e for e in items[i:] if e["_t"] - start["_t"] <= window]
            if len(in_window) >= cfg["max_donations"]:
                hits.append({
                    "project_id": project_id,
                    "rule": "new_payer_burst",
                    "evidence": {
                        "donor_ids": [e.get("donor_id") for e in in_window],
                        "counts": {"donations": len(in_window)},
                        "window": {"minutes": cfg["window_minutes"],
                                   "from": start["_t"].isoformat(),
                                   "to": in_window[-1]["_t"].isoformat()},
                    },
                })
                break
    return hits


def reciprocal_backing(events: list[dict]) -> list[dict]:
    cfg = THRESHOLDS["reciprocal_backing"]
    pairs: dict[tuple, set] = {}
    totals: dict[tuple, int] = {}
    for event in events:
        donor = event.get("donor_id")
        project = event.get("project_id")
        if donor is None or project is None:
            continue
        pairs.setdefault(project, set()).add(donor)
    donors_by_project = pairs
    projects = sorted(donors_by_project)
    hits = []
    for i, first in enumerate(projects):
        for second in projects[i + 1 :]:
            shared = donors_by_project[first] & donors_by_project[second]
            if len(shared) < cfg["min_donors"]:
                continue
            key = (first, second)
            total = sum(
                1 for e in events
                if e.get("donor_id") in shared and e.get("project_id") in key
            )
            if total >= cfg["min_total"]:
                hits.append({
                    "project_id": first,
                    "rule": "reciprocal_backing",
                    "evidence": {"donor_ids": sorted(shared),
                                 "counts": {"shared_donors": len(shared), "donations": total},
                                 "window": {"projects": [first, second]}},
                })
    return hits


def owner_donation(events: list[dict]) -> list[dict]:
    hits = []
    for event in events:
        owner = event.get("owner_donor_id")
        donor = event.get("donor_id")
        if owner is not None and donor is not None and owner == donor:
            hits.append({
                "project_id": event.get("project_id"),
                "rule": "owner_donation",
                "evidence": {"donor_ids": [donor], "counts": {"donations": 1},
                             "window": {"donation_id": event.get("donation_id")}},
            })
    return hits


def refund_spike(events: list[dict], now: datetime | None = None) -> list[dict]:
    cfg = THRESHOLDS["refund_spike"]
    now = now or datetime.now(timezone.utc)
    window = timedelta(hours=cfg["window_hours"])
    by_project: dict[int, list[dict]] = {}
    for event in events:
        captured = _parse(event.get("captured_at"))
        if captured is None or (now - captured) > window:
            continue
        by_project.setdefault(int(event["project_id"]), []).append(event)

    hits = []
    for project_id, items in by_project.items():
        total = len(items)
        refunded = [e for e in items if e.get("status") == "refunded"]
        if total >= cfg["min_donations"] and total and len(refunded) / total >= cfg["refund_ratio"]:
            hits.append({
                "project_id": project_id,
                "rule": "refund_spike",
                "evidence": {"donor_ids": [e.get("donor_id") for e in refunded],
                             "counts": {"refunds": len(refunded), "donations": total},
                             "window": {"hours": cfg["window_hours"]}},
            })
    return hits


def _open_key(donors: list[int]) -> tuple[int, ...]:
    return tuple(sorted(int(d) for d in donors))


def _is_subset(candidate: tuple[int, ...], others: list[tuple[int, ...]]) -> bool:
    """True when this donor set was already opened, or is contained in one that was."""
    mine = set(candidate)
    return any(mine <= set(other) for other in others)


def _drop_shadowed_reciprocal(hits: list[dict]) -> list[dict]:
    """Drop a reciprocal_backing hit that a larger collusion cluster already covers.

    Same project: if the cluster names more donors than the pair rule found, the cluster is
    the better case and the pair hit would only duplicate it. Otherwise both are kept.
    """
    clusters = [h for h in hits if h["rule"] == graph.RULE]
    kept = []
    for hit in hits:
        if hit["rule"] == "reciprocal_backing":
            mine = set(hit["evidence"].get("donor_ids") or [])
            shadowed = any(
                other["project_id"] == hit["project_id"]
                and len(other["evidence"].get("donor_ids") or []) > len(mine)
                and mine <= set(other["evidence"].get("donor_ids") or [])
                for other in clusters)
            if shadowed:
                log.info("reciprocal_backing on project %s dropped: a larger cluster covers it",
                         hit["project_id"])
                continue
        kept.append(hit)
    return kept


class WatchdogAgent:
    def __init__(self, mcp=None, source: EventsSource | None = None) -> None:
        from ..mcp_client import build_client

        self.mcp = mcp or build_client()
        self.source = source or FakeEventsSource()
        self._last_iso: str | None = None
        # Donor sets already opened (or already seen this process). The API also returns an
        # existing open case for the same project+rule, so this is about not re-reporting the
        # same people when the cluster moves to a different project.
        self._seen_clusters: list[tuple[int, ...]] = []

    async def scan(self, now: datetime | None = None) -> list[dict]:
        moment = now or datetime.now(timezone.utc)
        # The existing rules keep their own 1-day window; the graph needs the full window, so
        # fetch from the earlier of the two and let each rule filter what it wants.
        graph_iso = (moment - timedelta(days=graph.CONFIG["window_days"])).isoformat()
        short_iso = (moment - timedelta(days=1)).isoformat()
        iso = min(self._last_iso or graph_iso, graph_iso) if self._last_iso else graph_iso
        events = await self.source.since(iso)
        if not events:
            return []

        # Rules: unchanged behaviour, same short window they always used.
        recent = [e for e in events
                  if (ts := _parse(e.get("captured_at"))) is not None
                  and ts >= (moment - timedelta(days=1))]
        hits = (
            new_payer_burst(recent, moment)
            + reciprocal_backing(recent)
            + owner_donation(recent)
            + refund_spike(recent, moment)
        )

        # Graph: the full window, appended after the rules.
        clusters = graph.find_clusters(events, moment)
        fresh = [c for c in clusters
                 if not _is_subset(_open_key(c["donor_ids"]), self._seen_clusters)]
        if fresh:
            titles = await graph.project_titles(self.mcp,
                                                [c["project_id"] for c in fresh])
            hits = hits + graph.hits(fresh, titles)
        hits = _drop_shadowed_reciprocal(hits)

        opened = []
        for hit in hits:
            answer = await self.mcp.call(
                "open_watchdog_case",
                project_id=hit["project_id"],
                rule=hit["rule"],
                evidence=hit["evidence"],
            )
            opened.append({"project_id": hit["project_id"], "rule": hit["rule"], "case": answer})
            if hit["rule"] == graph.RULE:
                self._seen_clusters.append(_open_key(hit["evidence"]["donor_ids"]))
        self._last_iso = short_iso
        return opened
