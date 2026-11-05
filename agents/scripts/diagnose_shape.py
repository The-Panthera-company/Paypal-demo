"""Diagnostic: print only the shape of a raw search_projects tool result.

No project values, no env values. Types and top-level keys only.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings            # noqa: E402
from app.mcp_client import McpClient       # noqa: E402


async def main() -> int:
    cfg = Settings().model_copy(update={"fake_core": False, "dry_run": True})
    client = McpClient(cfg)
    try:
        raw = await client.call("search_projects", limit=1)
    except Exception as exc:
        print("FAILED: " + type(exc).__name__ + ": " + str(exc))
        return 1
    finally:
        await client.aclose()

    print("type: " + type(raw).__name__)
    if isinstance(raw, dict):
        print("keys: " + repr(sorted(raw.keys())))
        for key in sorted(raw.keys()):
            print("  " + str(key) + " -> " + type(raw[key]).__name__)
    elif isinstance(raw, list):
        print("len: " + str(len(raw)))
        if raw:
            first = raw[0]
            print("item type: " + type(first).__name__)
            if isinstance(first, dict):
                print("item keys: " + repr(sorted(first.keys())))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
