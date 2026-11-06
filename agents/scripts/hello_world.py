"""Smoke test: connect to the real mcp-server over stdio and read three projects.

Read-only by construction: this script only calls search_projects.
It never prints project values or env values. Run it with the command in agents/README.md:

    FAKE_CORE=false DRY_RUN=true .venv/bin/python scripts/hello_world.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings            # noqa: E402
from app.mcp_client import McpClient       # noqa: E402

LIMIT = 3
MISSING_QUERY = "zzzzqqqq"


async def describe(client, label: str, **args) -> None:
    try:
        out = await client.call("search_projects", **args)
    except Exception as exc:
        print(label + ": FAILED " + type(exc).__name__ + ": " + str(exc))
        return
    if isinstance(out, list):
        print(label + ": list, len=" + str(len(out)))
    else:
        print(label + ": " + type(out).__name__ + " (expected list)")


async def main() -> int:
    # Settings reads .env; no value is ever printed.
    cfg = Settings().model_copy(update={"fake_core": False, "dry_run": True})

    print("core api: " + cfg.core_api_url)
    print("mcp server: " + str(cfg.mcp_server_file))
    print("dry run: " + str(cfg.dry_run) + ", fake core: " + str(cfg.fake_core))
    print("")

    if os.environ.get("FAKE_CORE", "").lower() == "true":
        print("FAKE_CORE=true in the environment: export FAKE_CORE=false to use the real server.")

    client = McpClient(cfg)
    try:
        projects = await client.call("search_projects", limit=LIMIT, sort="urgency")
        if not isinstance(projects, list):
            print("FAILED: expected a list, got " + type(projects).__name__)
            return 1

        print("projects: " + str(len(projects)))
        for project in projects[:LIMIT]:
            print(
                str(project.get("id"))
                + "  "
                + str(project.get("status"))
                + "  "
                + str(project.get("title"))
            )
        print("")

        # Shape checks only: type and length, never values.
        await describe(client, "limit=1", limit=1, sort="urgency")
        await describe(client, "q=" + MISSING_QUERY, q=MISSING_QUERY)
    except Exception as exc:
        print("FAILED: " + type(exc).__name__ + ": " + str(exc))
        return 1
    finally:
        await client.aclose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
