"""Lifespan tests: the app must import and start without touching the network.

FAKE_CORE=true is forced before app.main is imported, so build_client() returns
FakeMcpClient and build_llm() returns FakeLLM. TestClient is used as a context manager
so startup and shutdown really run -- the mistake that let a NameError ship.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def fake_app(monkeypatch):
    """Import app.main with FAKE_CORE forced on, and reset its singletons."""
    monkeypatch.setenv("FAKE_CORE", "true")
    monkeypatch.setenv("DRY_RUN", "true")

    from app.config import settings

    settings.cache_clear()

    import app.main as main_module

    monkeypatch.setattr(main_module.cfg, "fake_core", True, raising=False)
    main_module.reset_shared()
    yield main_module
    main_module.reset_shared()
    settings.cache_clear()


def test_main_imports_without_network(fake_app):
    assert fake_app.app.title == "Community Giving agents"


def test_lifespan_starts_and_stops_with_fake_core(fake_app):
    with TestClient(fake_app.app) as client:
        assert client.get("/health").json()["fake_core"] is True
        # Startup built the fake client but did not connect to anything.
        assert isinstance(fake_app._shared_mcp, fake_app.FakeMcpClient)
    # Shutdown drops the singletons.
    assert fake_app._shared_mcp is None
    assert fake_app._shared_llm is None


def test_chat_works_through_lifespan_with_fakes(fake_app, monkeypatch):
    from app.llm import FakeLLM
    from app.mcp_client import FakeMcpClient

    project = {"id": 2, "title": "Girls STEM Club", "cause": "stem education",
               "beneficiary_group": "girls", "region": "nakuru",
               "tags": ["girls", "science"], "urgency": 1, "backer_count": 3,
               "raised_cents": 2000, "goal_cents": 120000, "status": "active"}
    fake_mcp = FakeMcpClient({"search_projects": [project]})
    fake_llm = FakeLLM(texts=["One project fits."])

    with TestClient(fake_app.app) as client:
        monkeypatch.setattr(fake_app, "_shared_mcp", fake_mcp)
        monkeypatch.setattr(fake_app, "_shared_llm", fake_llm)
        resp = client.post("/agents/discovery/chat",
                           json={"message": "I care about education for girls"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) >= {"filters", "projects", "explanation", "reply", "projectIds"}
    assert all(isinstance(v, str) for v in body["filters"].values())
    assert body["projectIds"] == ["2"]
    # Read-only path: no mutating tool was ever called.
    assert not any(c[0] in {"record_mandate_run", "request_checked_donation"} for c in fake_mcp.calls)


def test_startup_survives_a_client_that_cannot_connect(fake_app, monkeypatch):
    """A sleeping core API must not stop the app from starting."""

    class BrokenClient:
        def __init__(self):
            self.aclosed = False

        async def session(self):
            raise RuntimeError("core api asleep")

        async def aclose(self):
            self.aclosed = True

    broken = BrokenClient()
    monkeypatch.setattr(fake_app, "_shared_mcp", broken)

    with TestClient(fake_app.app) as client:
        assert client.get("/health").status_code == 200
    assert broken.aclosed is True


def test_startup_skips_warmup_for_fake_client(fake_app, monkeypatch):
    """FakeMcpClient has no session(); warm-up must not call it and must not fail."""
    from app.mcp_client import FakeMcpClient

    fake = FakeMcpClient()
    monkeypatch.setattr(fake_app, "_shared_mcp", fake)

    async def explode():
        raise AssertionError("warm-up must not touch a fake client")

    monkeypatch.setattr(fake, "session", explode, raising=False)

    with TestClient(fake_app.app) as client:
        assert client.get("/health").status_code == 200
