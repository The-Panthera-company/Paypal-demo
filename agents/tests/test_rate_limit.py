"""Rate limit tests: fake clock, no network, no MCP, no LLM."""
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import main as main_module


def _request(ip: str = "1.2.3.4", forwarded: str | None = None) -> Request:
    headers = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    return Request(
        {
            "type": "http",
            "headers": headers,
            "client": (ip, 12345),
            "method": "POST",
            "path": "/agents/chat",
        }
    )


@pytest.fixture(autouse=True)
def clean_buckets():
    main_module._hits.clear()
    yield
    main_module._hits.clear()


def test_limit_allows_exactly_the_configured_number(monkeypatch):
    monkeypatch.setattr(main_module.cfg, "rate_limit_per_min", 3, raising=False)
    for _ in range(3):
        main_module._rate_limit(_request(), now=100.0)


def test_limit_plus_one_raises_429(monkeypatch):
    monkeypatch.setattr(main_module.cfg, "rate_limit_per_min", 3, raising=False)
    for _ in range(3):
        main_module._rate_limit(_request(), now=100.0)
    with pytest.raises(HTTPException) as err:
        main_module._rate_limit(_request(), now=100.0)
    assert err.value.status_code == 429


def test_rejected_requests_still_count(monkeypatch):
    """20 rejections inside one window must not let a 21st through."""
    monkeypatch.setattr(main_module.cfg, "rate_limit_per_min", 2, raising=False)
    main_module._rate_limit(_request(), now=100.0)
    main_module._rate_limit(_request(), now=100.0)
    for _ in range(20):
        with pytest.raises(HTTPException):
            main_module._rate_limit(_request(), now=100.0)
    with pytest.raises(HTTPException):
        main_module._rate_limit(_request(), now=100.0)


def test_window_slides_past_old_hits(monkeypatch):
    monkeypatch.setattr(main_module.cfg, "rate_limit_per_min", 2, raising=False)
    main_module._rate_limit(_request(), now=100.0)
    main_module._rate_limit(_request(), now=100.0)
    # 61 s later the first two have expired.
    main_module._rate_limit(_request(), now=161.0)


def test_forwarded_for_first_address_is_the_key():
    key = main_module.client_key(_request(ip="10.0.0.1", forwarded="203.0.113.9, 10.0.0.1"))
    assert key == "203.0.113.9"


def test_forwarded_for_absent_falls_back_to_peer():
    assert main_module.client_key(_request(ip="10.0.0.1")) == "10.0.0.1"


def test_different_forwarded_clients_have_separate_buckets(monkeypatch):
    monkeypatch.setattr(main_module.cfg, "rate_limit_per_min", 1, raising=False)
    main_module._rate_limit(_request(forwarded="203.0.113.1"), now=100.0)
    main_module._rate_limit(_request(forwarded="203.0.113.2"), now=100.0)
    with pytest.raises(HTTPException):
        main_module._rate_limit(_request(forwarded="203.0.113.1"), now=100.0)


def test_endpoint_returns_429_after_the_limit(monkeypatch):
    """Through the ASGI app: the limiter runs before the agent is built."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main_module.cfg, "rate_limit_per_min", 2, raising=False)
    calls: list[str] = []

    class _Agent:
        def __init__(self, *a, **kw):
            calls.append("built")

        async def chat(self, message):
            return {"filters": {}, "projects": [], "explanation": "", "reply": "", "projectIds": []}

    monkeypatch.setattr(main_module, "DiscoveryAgent", _Agent)
    monkeypatch.setattr(main_module, "shared_mcp", lambda: object())
    monkeypatch.setattr(main_module, "build_llm", lambda *a, **kw: object())

    with TestClient(main_module.app) as client:
        codes = [
            client.post("/agents/chat", json={"message": "hi"}).status_code
            for _ in range(4)
        ]
    assert codes[:2] == [200, 200]
    assert codes[2] == 429 and codes[3] == 429
    # The agent must not run for rejected requests.
    assert len(calls) == 2
