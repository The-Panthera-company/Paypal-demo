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
    # A procurement proposal and its payment: both must be blocked by DRY_RUN.
    "record_procurement_run",
    "propose_procurement",
    "pay_procurement",
}

# Tools that always answer with a list. The decision is made here, by tool name, never by
# counting content blocks: "0 blocks -> []" and "1 block -> [one item]" would otherwise be
# indistinguishable from an object tool's empty/unary answer.
LIST_TOOLS = {
    "search_projects",
    "list_active_mandates",
    # The procurement lists are lists too: a single open request or supplier comes back as
    # one dict, and without this entry the agent iterates the dict's keys instead.
    "list_procurement_requests",
    "list_procurement_suppliers",
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
            # Queued responses go through the same per-tool shape rule as the real client,
            # so tests exercise the identical path.
            return _coerce_shape(tool, value(args) if callable(value) else value)
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
            # Procurement: empty by default, so a test or demo sees "nothing to buy" rather
            # than an invented purchase. The two write tools answer ProcurementOut-shaped
            # objects so a caller that reads status/id gets the real shape, not {}.
            "list_procurement_requests": [],
            "list_procurement_suppliers": [],
            "record_procurement_run": {"id": 1},
            "propose_procurement": {
                "id": args.get("procurement_id"), "project_id": None, "milestone_id": None,
                "description": "", "quantity": 1, "max_amount_cents": 0, "currency": "USD",
                "status": "proposed", "supplier_id": args.get("supplier_id"),
                "amount_cents": args.get("amount_cents"),
                "line_items": args.get("line_items") or [],
                "rationale": args.get("rationale"), "admin_approved": False,
            },
            "pay_procurement": {
                "id": args.get("procurement_id"), "project_id": None, "milestone_id": None,
                "description": "", "quantity": 1, "max_amount_cents": 0, "currency": "USD",
                "status": "paid", "supplier_id": None, "amount_cents": None,
                "line_items": [], "rationale": None, "admin_approved": False,
            },
        }
        return _coerce_shape(tool, defaults.get(tool, {}))

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
        stack = AsyncExitStack()
        self._stack = stack
        try:
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except BaseException:
            # CancelledError is a BaseException: a request the web gave up on, or a
            # shutdown, must not leak a half-open stack. Teardown can itself raise
            # (anyio: "Attempted to exit cancel scope in a different task"), so it is
            # swallowed here - the original error is the one worth propagating.
            self._session = None
            self._stack = None
            try:
                await stack.aclose()
            except BaseException as exc:
                log.warning("MCP connect teardown failed: %s", exc)
            raise
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
                return _unwrap(result, tool)
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


def _normalize(value: Any) -> Any:
    """mcp 2.x wraps tool results: a list comes back as {"result": [...]}.

    Unwrap exactly that shape so every caller sees the bare value. A dict that merely
    happens to have a "result" key alongside others is left alone.
    """
    if isinstance(value, dict) and len(value) == 1 and "result" in value:
        return value["result"]
    return value


def _coerce_shape(tool: str, value: Any) -> Any:
    """Apply the per-tool shape rule to an already-decoded value.

    List tools always get a list; object tools always get a dict (or None). Used by
    FakeMcpClient so tests and the real client agree on shape.
    """
    value = _normalize(value)
    if tool in LIST_TOOLS:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]
    return value


def _unwrap(result: Any, tool: str | None = None) -> Any:
    """MCP returns content blocks; the server answers with one JSON text block per item.

    Shape is decided by the tool name (LIST_TOOLS), not by counting blocks: a list tool
    must return a list even for 0 or 1 results, and an object tool must return a dict.
    """
    if getattr(result, "isError", False):
        texts = [getattr(c, "text", "") for c in getattr(result, "content", [])]
        raise McpUnavailable("; ".join(t for t in texts if t) or "MCP tool error")
    content = getattr(result, "content", None)
    if content is None:
        return _normalize(getattr(result, "structuredContent", None))

    # mcp 2.x emits ONE content block per list item, so a 3-item search_projects
    # answer arrives as 3 blocks. Parsing only the first silently dropped the rest.
    parsed: list[Any] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is None:
            continue
        try:
            parsed.append(json.loads(text))
        except ValueError:
            parsed.append(text)

    items = [_normalize(item) for item in parsed]
    if tool in LIST_TOOLS:
        # A single block may still carry the whole list; anything else is one item.
        if len(items) == 1 and isinstance(items[0], list):
            return items[0]
        return items
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    return items


def build_client(cfg: Settings | None = None) -> Any:
    cfg = cfg or settings()
    return FakeMcpClient() if cfg.fake_core else McpClient(cfg)
