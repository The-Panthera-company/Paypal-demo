"""Read-only probe: does core.py actually fetch stories and funding history?

For each live project it prints only counts and one date -- no amounts, titles or env values.
Every failure is printed, never swallowed.

    FAKE_CORE=false DRY_RUN=true .venv/bin/python scripts/core_reads_probe.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings            # noqa: E402
from app.core import build_core           # noqa: E402
from app.mcp_client import build_client   # noqa: E402

MISSING = "missing"


async def main() -> int:
    cfg = Settings().model_copy(update={"fake_core": False, "dry_run": True})
    mcp = build_client(cfg)
    core = build_core(cfg)

    print("core class: " + type(core).__name__)
    print("")

    try:
        live = await mcp.call("search_projects", limit=100, sort="urgency")
    except Exception as exc:
        print("FAILED search_projects: " + type(exc).__name__ + ": " + str(exc))
        await mcp.aclose()
        return 1

    for project in live:
        pid = int(project["id"])

        # --- stories ---
        try:
            stories = await core.stories(pid)
            stories_status = "ok"
        except Exception as exc:
            stories = []
            stories_status = "FAILED " + type(exc).__name__ + ": " + str(exc)
        print("project " + str(pid) + " stories: "
              + str(len(stories)) + " calls=" + stories_status)

        # --- funding history ---
        try:
            history = await core.funding_history(pid)
            history_status = "ok"
        except Exception as exc:
            history = []
            history_status = "FAILED " + type(exc).__name__ + ": " + str(exc)
        print("project " + str(pid) + " history: "
              + str(len(history)) + " calls=" + history_status)

        # --- last point that actually raised funds ---
        last_raised_date = MISSING
        prev = None
        for point in history:
            raised = point.get("raised_cents") if isinstance(point, dict) else None
            if isinstance(raised, int) and prev is not None and raised > prev:
                last_raised_date = str(point.get("date"))
            if isinstance(raised, int):
                prev = raised
        print("project " + str(pid) + " last_raised_point: " + last_raised_date)
        print("")

    await mcp.aclose()
    await core.aclose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
