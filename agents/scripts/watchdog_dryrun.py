#!/usr/bin/env python
"""Watchdog dry run over a seeded feed. Read-only apart from MCP case calls.

Two feeds, chosen by --feed:

  ring  7 donors co-backing 3 projects with small gifts a few days apart, plus 6 ordinary
        donors each backing one project. Proves the graph detector fires and the other rules do
        not.
  real  the live GET /internal/donation-events feed through CoreEventsSource (needs
        INTERNAL_TOKEN and a reachable CORE_API_URL).

DRY_RUN=true stops every mutating MCP call, including open_watchdog_case, so this prints what
the Watchdog WOULD open without touching a project.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.watchdog import FakeEventsSource, WatchdogAgent  # noqa: E402
from app.config import settings  # noqa: E402
from app.core import Core  # noqa: E402
from app.mcp_client import build_client  # noqa: E402

RING_DONORS = (21, 22, 23, 24, 25, 26, 27)
RING_PROJECTS = (101, 102, 103)
NORMAL_DONORS = (41, 42, 43, 44, 45, 46)
# Titles for the three ring projects; the fake MCP client serves these by id.
RING_TITLES = {101: "Borehole repairs, Nakuru", 102: "School water tanks", 103: "Well maintenance"}


def seeded_events(now: datetime | None = None) -> list[dict]:
    """The ring plus ordinary donors. Small gifts, spread over a few days, inside 30 days."""
    now = now or datetime.now(timezone.utc)
    events: list[dict] = []
    serial = 1

    def add(project: int, donor: int, cents: int, days_ago: float) -> None:
        nonlocal serial
        events.append({
            "donation_id": serial,
            "project_id": project,
            "donor_id": donor,
            "status": "captured",
            "amount_cents": cents,
            "captured_at": (now - timedelta(days=days_ago)).isoformat(),
            "donor_created_at": (now - timedelta(days=days_ago + 400)).isoformat(),
            "owner_donor_id": 900 + project,
            "is_guest": False,
        })
        serial += 1

    # The ring: every donor backs every project, $5-$9 a gift, 1-5 days apart.
    for index, donor in enumerate(RING_DONORS):
        for offset, project in enumerate(RING_PROJECTS):
            add(project, donor, 500 + 100 * ((index + offset) % 4), 1 + (index + offset) % 5)

    # Ordinary donors: one project each, a larger one-off gift, well spread.
    for index, donor in enumerate(NORMAL_DONORS):
        add(200 + index, donor, 2500 + 500 * index, 2 + index % 6)

    return events


def fake_mcp():
    """Titles for the ring projects only; anything else gets the client default."""
    from app.mcp_client import FakeMcpClient

    def get_project(project_id: int, **_: object) -> dict:
        return {"id": project_id, "title": RING_TITLES.get(project_id, f"Project {project_id}")}

    return FakeMcpClient({"get_project": get_project})


async def main() -> int:
    parser = argparse.ArgumentParser(description="Watchdog dry run")
    parser.add_argument("--feed", choices=("ring", "real"), default="ring")
    args = parser.parse_args()

    cfg = settings()
    now = datetime.now(timezone.utc)
    if args.feed == "ring":
        source = FakeEventsSource(seeded_events(now))
        mcp = fake_mcp()
    else:
        from app.agents.watchdog import CoreEventsSource

        source = CoreEventsSource(Core(cfg))
        mcp = build_client(cfg)

    # Only the "real" feed has something to close; checked by attribute rather than by name,
    # because the import inside that branch is not in scope here.
    closable = args.feed == "real"

    agent = WatchdogAgent(mcp=mcp, source=source)
    print(f"feed: {args.feed}   dry_run: {cfg.dry_run}   core: {cfg.core_api_url}")
    try:
        opened = await agent.scan(now)
    finally:
        await agent.mcp.aclose()
        if closable:
            await source.aclose()  # type: ignore[attr-defined]

    if not opened:
        print("no cases opened")
        return 0
    # The reply is a dry-run stub under DRY_RUN, so report the evidence that was SENT:
    # the MCP client records every call it makes.
    sent = {id(item) for item in opened}
    for call in getattr(mcp, "calls", []):
        if call[0] != "open_watchdog_case":
            continue
        args = call[1]
        counts = (args.get("evidence") or {}).get("counts") or {}
        print(f"  {args['rule']}  project {args.get('project_id')}  "
              f"donors {counts.get('donors', '?')}  projects {counts.get('projects', '?')} "
              f"shared {counts.get('shared', '?')}  total {counts.get('total_cents', '?')}c")
    
    print(f"{len(opened)} case(s) opened")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
