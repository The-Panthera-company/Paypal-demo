"""Print the raw funding-history points for a project. Sample data: values are safe to print.

    FAKE_CORE=false DRY_RUN=true .venv/bin/python scripts/history_points.py 1
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.giving import days_since_last_funding  # noqa: E402
from app.config import Settings                          # noqa: E402
from app.core import build_core                          # noqa: E402


async def main(project_id: int) -> int:
    cfg = Settings().model_copy(update={"fake_core": False, "dry_run": True})
    core = build_core(cfg)
    try:
        history = await core.funding_history(project_id)
    except Exception as exc:
        print("FAILED: " + type(exc).__name__ + ": " + str(exc))
        return 1
    finally:
        await core.aclose()

    print("project " + str(project_id) + " points: " + str(len(history)))
    for index, point in enumerate(history):
        print("  point " + str(index) + ":")
        if not isinstance(point, dict):
            print("    type=" + type(point).__name__)
            continue
        for key in sorted(point.keys()):
            print("    " + str(key) + " = " + repr(point[key]))
    print("days_since_last_funding -> " + repr(days_since_last_funding(history)))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)))
