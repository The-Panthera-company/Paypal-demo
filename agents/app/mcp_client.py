"""Starts mcp-server/server.py over stdio and calls its tools.

Every tool is a thin call into the core API. This client adds three things the spec asks for:
long timeouts (Render free tier needs ~60 s to wake), auto-restart of a dead subprocess, and a
DRY_RUN guard that turns every mutating tool into a canned response.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from .config import Settings, settings

log = logging.getLogger(__name__)

# Tools that change state or move money. In DRY_RUN these never reach the server.
MUTATING_TOOLS = {
    "record_mandate_run",
    "request_checked_donation",
    "open_watchdog_case",
    "request_milestone_payout",
    "log_decision",
}

WAKE_TIMEOUT_SECONDS = 120


class McpUnavailable(RuntimeError):
    pass


class FakeMcpClient:
    """Canned results for FAKE_CORE / tests. Never touches the network."""

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, tool: str, **args: Any) -> Any:
        self.calls.append((tool, args))
        if tool in self.responses:
            value = self.responses[tool]
            return value(args) if callable(value) else value
        defaults: dict[str, Any] = {
            "list_active_mandates": [],
            "search_projects": [],
            "get_project": {"id": args.get("project_id"), "title": "Sample project", "milestones": []},
            "get_leaderboard": {"rows": []},
            "record_mandate_run": {"id": 1, "mandate_id": args.get("mandate_id")},
            "request_checked_donation": {"status": "recorded", "donation_id": 1, "rule_result": None},
            "open_watchdog_case": {"id": 1, "status": "open"},
            "request_milestone_payout": {"status": "held"},
            "log_decision": {"id": 1},
        }
        return defaults.get(tool, {})

    async def aclose(self) -> None:
        return None


class McpClient:
    def __init__(self, cfg: Settings | None = None) -> None:
        self.cfg = cfg or settings()
        self._session: Any = None
        self._stack: AsyncExitStack | None = None
        self._lock = asyncio.Lock()

    async def _connect(self) -> Any:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server = self.cfg.mcp_server_file
        if not server.exists():
            raise McpUnavailable(f"MCP server not found at {server}")

        env = dict(os.environ)
        env.update(
            {
                "CORE_API_URL": self.cfg.core_api_url.rstrip("/"),
                "INTERNAL_TOKEN": self.cfg.internal_token,
            }
        )
        params = StdioServerParameters(
            command=os.environ.get("PYTHON_BIN") or "python3",
            args=[str(server)],
            env=env,
        )
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session
        log.info("MCP connected: %s", server.name)
        return session

    async def session(self) -> Any:
        if self._session is not None:
            return self._session
        async with self._lock:
            if self._session is None:
                await self._connect()
        return self._session

    async def _reset(self) -> None:
        session, stack = self._session, self._stack
        self._session, self._stack = None, None
        try:
            if stack is not None:
                await stack.aclose()
        except Exception:  # pragma: no cover - best effort teardown
            pass
        del session

    async def call(self, tool: str, **args: Any) -> Any:
        if self.cfg.dry_run and tool in MUTATING_TOOLS:
            log.warning("DRY_RUN: %s(%s) not sent", tool, sorted(args))
            return {"dry_run": True, "tool": tool, "status": "recorded"}

        last: Exception | None = None
        for attempt in range(2):
            try:
                session = await self.session()
                result = await asyncio.wait_for(
                    session.call_tool(tool, arguments=args), timeout=WAKE_TIMEOUT_SECONDS
                )
                return _unwrap(result)
            except asyncio.TimeoutError as exc:  # Render wake-up
                last = exc
                log.warning("MCP call %s timed out, retrying", tool)
            except Exception as exc:  # subprocess died: restart once
                last = exc
                log.warning("MCP call %s failed (%s), restarting", tool, exc)
                await self._reset()
        raise McpUnavailable(f"MCP tool {tool} failed: {last}")

    async def aclose(self) -> None:
        await self._reset()


def _unwrap(result: Any) -> Any:
    """MCP returns content blocks; the server always answers with one JSON text block."""
    if getattr(result, "isError", False):
        texts = [getattr(c, "text", "") for c in getattr(result, "content", [])]
        raise McpUnavailable("; ".join(t for t in texts if t) or "MCP tool error")
    content = getattr(result, "content", None)
    if content is None:
        structured = getattr(result, "structuredContent", None)
        return structured
    for block in content:
        text = getattr(block, "text", None)
        if text is None:
            continue
        try:
            return json.loads(text)
        except ValueError:
            return text
    return None


def build_client(cfg: Settings | None = None) -> Any:
    cfg = cfg or settings()
    return FakeMcpClient() if cfg.fake_core else McpClient(cfg)
