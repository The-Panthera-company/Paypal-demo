"""Watchdog: plain rules over donation events. No LLM.

The donation-events endpoint does not exist yet (spec section 7), so the agent reads through an
EventsSource interface. Swap FakeEventsSource for the real one when Person 1 ships it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

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


class FakeEventsSource:
    """Test/seeded events. Each event: donation_id, project_id, status, amount_cents,
    captured_at, payer_id, is_guest, donor_created_at, owner_payer_id."""

    def __init__(self, events: list[dict] | None = None) -> None:
        self.events = list(events or [])

    async def since(self, iso: str) -> list[dict]:
        return list(self.events)


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
                        "donor_ids": [e.get("payer_id") for e in in_window],
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
        payer = event.get("payer_id")
        project = event.get("project_id")
        if payer is None or project is None:
            continue
        pairs.setdefault(project, set()).add(payer)
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
                if e.get("payer_id") in shared and e.get("project_id") in key
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
        owner = event.get("owner_payer_id")
        payer = event.get("payer_id")
        if owner and payer and owner == payer:
            hits.append({
                "project_id": event.get("project_id"),
                "rule": "owner_donation",
                "evidence": {"donor_ids": [payer], "counts": {"donations": 1},
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
                "evidence": {"donor_ids": [e.get("payer_id") for e in refunded],
                             "counts": {"refunds": len(refunded), "donations": total},
                             "window": {"hours": cfg["window_hours"]}},
            })
    return hits


class WatchdogAgent:
    def __init__(self, mcp=None, source: EventsSource | None = None) -> None:
        from ..mcp_client import build_client

        self.mcp = mcp or build_client()
        self.source = source or FakeEventsSource()
        self._last_iso: str | None = None

    async def scan(self, now: datetime | None = None) -> list[dict]:
        iso = self._last_iso or (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        events = await self.source.since(iso)
        if not events:
            return []
        hits = (
            new_payer_burst(events, now)
            + reciprocal_backing(events)
            + owner_donation(events)
            + refund_spike(events, now)
        )
        opened = []
        for hit in hits:
            answer = await self.mcp.call(
                "open_watchdog_case",
                project_id=hit["project_id"],
                rule=hit["rule"],
                evidence=hit["evidence"],
            )
            opened.append({"project_id": hit["project_id"], "rule": hit["rule"], "case": answer})
        self._last_iso = (now or datetime.now(timezone.utc)).isoformat()
        return opened
