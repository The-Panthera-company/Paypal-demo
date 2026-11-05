"""Smoke test: connect to the real mcp-server over stdio and read three projects.

Read-only by construction: this script calls search_projects and nothing else.
It never prints env values. Run it with the exact command in agents/README.md.

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


async def main() -> int:
    # Settings reads .env; the script never prints any of its values.
    base = Settings()
    cfg = base.model_copy(update={
        "fake_core": False,
        "dry_run": True,
    })

    print("core api: " + cfg.core_api_url)
    print("mcp server: " + str(cfg.mcp_server_file))
    print("dry run: " + str(cfg.dry_run) + ", fake core: " + str(cfg.fake_core))
    print("")

    if os.environ.get("FAKE_CORE", "").lower() == "true":
        print("FAKE_CORE=true in the environment: export FAKE_CORE=false to use the real server.")

    client = McpClient(cfg)
    try:
        projects = await client.call("search_projects", limit=LIMIT, sort="urgency")
    except Exception as exc:
        print("FAILED: " + type(exc).__name__ + ": " + str(exc))
        return 1
    finally:
        await client.aclose()

    if not isinstance(projects, list):
        print("FAILED: expected a list, got " + type(projects).__name__)
        return 1

    print("projects: " + str(len(projects)))
    print("")
    for project in projects[:LIMIT]:
        print(
            str(project.get("id"))
            + "  "
            + str(project.get("status"))
            + "  "
            + str(project.get("title"))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
