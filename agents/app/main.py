"""FastAPI surface for the agents service.

Public: GET /health, POST /agents/discovery/chat (alias /agents/chat), POST /agents/recommendations.
Internal (INTERNAL_TOKEN): POST /agents/giving/run.
The chat path has no write tools: it only reads via search_projects.
"""
from __future__ import annotations

import hmac
import logging
from collections import defaultdict, deque
from time import monotonic

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .agents.discovery import DiscoveryAgent
from .agents.giving import GivingAgent
from .config import settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

MAX_MESSAGE = 1000
RATE_LIMIT = 30
RATE_WINDOW = 60.0

app = FastAPI(title="Community Giving agents", version="0.1.0")

cfg = settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cfg.web_origin.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

_hits: dict[str, deque] = defaultdict(deque)


def _rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = monotonic()
    bucket = _hits[ip]
    while bucket and now - bucket[0] > RATE_WINDOW:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="too many requests")
    bucket.append(now)


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
    _rate_limit(request)
    message = (body.message or "").strip()
    if len(message) > MAX_MESSAGE:
        raise HTTPException(status_code=422, detail="message too long")
    agent = DiscoveryAgent()
    try:
        return await agent.chat(message)
    finally:
        await agent.mcp.aclose()


@app.post("/agents/discovery/chat")
async def discovery_chat(body: ChatIn, request: Request) -> dict:
    return await _chat(body, request)


@app.post("/agents/chat")
async def chat_alias(body: ChatIn, request: Request) -> dict:
    return await _chat(body, request)


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
