"""FastAPI surface for the agents service.

Public: GET /health, POST /agents/discovery/chat (alias /agents/chat), POST /agents/recommendations.
Internal (INTERNAL_TOKEN): POST /agents/giving/run.
The chat path has no write tools: it only reads via search_projects.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from time import monotonic

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .agents.discovery import DiscoveryAgent
from .agents.giving import GivingAgent
from .agents.mandate_draft import DraftIn, MandateDraftAgent
from .config import settings
from .llm import LLM, LLMUnavailable, build_llm
from .mcp_client import FakeMcpClient, McpClient, build_client

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

MAX_MESSAGE = 1000
RATE_WINDOW = 60.0

cfg = settings()

_shared_mcp: McpClient | FakeMcpClient | None = None
_shared_llm: LLM | None = None


def shared_mcp() -> McpClient | FakeMcpClient:
    """One long-lived MCP client for the whole app.

    Building it never connects: McpClient connects lazily on the first call and
    reconnects internally (call() retries once after _reset()), so a sleeping core API
    cannot stop the app from starting.
    """
    global _shared_mcp
    if _shared_mcp is None:
        _shared_mcp = build_client(cfg)
    return _shared_mcp


def shared_llm() -> LLM:
    global _shared_llm
    if _shared_llm is None:
        _shared_llm = build_llm(cfg)
    return _shared_llm


def reset_shared() -> None:
    """Drop the shared singletons. Tests call this; lifespan calls it at shutdown."""
    global _shared_mcp, _shared_llm
    _shared_mcp = None
    _shared_llm = None


# Startup warm-up budget. Kept small: a cold Render API can take ~60 s, and the app must
# not wait for it. A miss just means the first chat pays the connect cost.
WARMUP_SECONDS = 5.0


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Best-effort warm-up, never fatal.

    A sleeping Render API can take ~60 s to wake, so startup does not wait on it: the
    client is built (cheap, no I/O) and the first chat request connects. Warm-up only
    happens for the real client, and any failure is logged and swallowed so /health and
    the rest of the service stay up.
    """
    try:
        client = shared_mcp()
        if isinstance(client, McpClient):
            try:
                await asyncio.wait_for(client.session(), timeout=WARMUP_SECONDS)
            except Exception as exc:
                log.warning("MCP warm-up skipped (%s); will connect on first request", exc)
    except Exception as exc:  # never let startup kill the app
        log.warning("MCP client unavailable at startup: %s", exc)

    yield

    client = _shared_mcp
    if client is not None:
        try:
            await client.aclose()
        except Exception as exc:  # best effort teardown
            log.warning("MCP shutdown failed: %s", exc)
    reset_shared()


app = FastAPI(title="Community Giving agents", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cfg.web_origin.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

_hits: dict[str, deque] = defaultdict(deque)


def client_key(request: Request) -> str:
    """First X-Forwarded-For address when present, else the socket peer.

    Behind Render every request shares the proxy IP, so the header is the only per-client
    signal available. It is client-controlled; that is acceptable for a rate limit and is
    never used for authentication.
    """
    forwarded = request.headers.get("x-forwarded-for") or ""
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else "unknown"


def _rate_limit(request: Request, now: float | None = None) -> None:
    """Counts every request, including the ones it rejects, before any work is done."""
    stamp = monotonic() if now is None else now
    bucket = _hits[client_key(request)]
    while bucket and stamp - bucket[0] > RATE_WINDOW:
        bucket.popleft()
    bucket.append(stamp)
    if len(bucket) > cfg.rate_limit_per_min:
        raise HTTPException(status_code=429, detail="too many requests")


def _require_token(token: str | None) -> None:
    expected = cfg.internal_token
    if not expected:
        raise HTTPException(status_code=503, detail="internal token not configured")
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="unauthorized")


class ChatIn(BaseModel):
    message: str = Field(default="", max_length=MAX_MESSAGE)
    # Accepted and ignored: the web may send its project list and history.
    projects: list[dict] | None = None
    history: list[dict] | None = None


class GivingIn(BaseModel):
    mandateId: int
    force: bool = False


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "fake_core": cfg.fake_core, "dry_run": cfg.dry_run,
            "model": cfg.deepseek_model}


async def _chat(body: ChatIn, request: Request) -> dict:
    # Before any work: a rejected request still costs a slot.
    _rate_limit(request)
    message = (body.message or "").strip()
    # Pydantic's max_length already rejects longer bodies with 422; this catches
    # whitespace-padded input that only exceeds the cap once trimmed.
    if len(message) > MAX_MESSAGE:
        raise HTTPException(status_code=422, detail="message too long")
    agent = DiscoveryAgent(mcp=shared_mcp(), llm=shared_llm())
    return await agent.chat(message)


@app.post("/agents/discovery/chat")
async def discovery_chat(body: ChatIn, request: Request) -> dict:
    return await _chat(body, request)


@app.post("/agents/chat")
async def chat_alias(body: ChatIn, request: Request) -> dict:
    return await _chat(body, request)


@app.post("/agents/mandate/draft")
async def mandate_draft(body: DraftIn, request: Request) -> dict:
    """Turn a donor's own words into a draft of their giving rules.

    Read-only: nothing here creates or changes a mandate. 429 is the shared rate limit;
    503 means the text could not be read and nothing was proposed, so the web tells the
    donor to use the form instead.
    """
    _rate_limit(request)
    agent = MandateDraftAgent()
    try:
        return await agent.draft(body.text, body.current)
    except LLMUnavailable as exc:
        raise HTTPException(status_code=503, detail="cannot read text right now") from exc
    finally:
        await agent.aclose()


@app.post("/agents/giving/run")
async def giving_run(body: GivingIn, authorization: str | None = Header(default=None)) -> dict:
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    _require_token(token)
    agent = GivingAgent()
    try:
        return await agent.run(body.mandateId, force=body.force)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        await agent.mcp.aclose()
