"""run_watchdog picks its event source from FAKE_CORE.

The scheduler job must scan the real feed in a deployment and seeded events under the fake, so
a test or demo never reaches for the network. Both sources are swapped for recorders; the point
is which type the job builds, not what it does with the events.
"""
import pytest

from app.agents import watchdog as watchdog_module
from app.config import Settings


class RecordingSource:
    """Stands in for either source: records construction and whether aclose was called."""

    made: list["RecordingSource"] = []

    def __init__(self, *args, **kwargs) -> None:
        self.closed = False
        self.asked: list[str] = []
        RecordingSource.made.append(self)

    async def since(self, iso: str) -> list[dict]:
        self.asked.append(iso)
        return []

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture()
def recorder(monkeypatch):
    """Swap both source classes for recorders so nothing reaches the network.

    The patch targets app.scheduler, not app.agents.watchdog: run_watchdog binds the two
    names at import, so once app.scheduler is in sys.modules patching watchdog does nothing.
    """
    RecordingSource.made = []
    monkeypatch.setattr("app.scheduler.CoreEventsSource", RecordingSource)
    monkeypatch.setattr("app.scheduler.FakeEventsSource", RecordingSource)
    return RecordingSource


def test_watchdog_uses_the_core_feed_when_the_core_is_real(monkeypatch, recorder):
    from app.scheduler import run_watchdog

    built: list[dict] = []

    class Recorder:
        calls: list[tuple] = []

        def __init__(self, *args, **kwargs) -> None:
            pass

        async def call(self, *args, **kwargs):
            return None

        async def aclose(self) -> None:
            return None

    # WatchdogAgent builds its own MCP client; swap that for a no-op so the test is offline.
    monkeypatch.setattr("app.mcp_client.build_client", lambda *a, **k: Recorder())

    import asyncio

    asyncio.run(run_watchdog(Settings(fake_core=False)))

    assert len(recorder.made) == 1, "exactly one source built"
    assert isinstance(recorder.made[0], RecordingSource)
    assert recorder.made[0].closed, "the source is closed even with no events"


def test_watchdog_uses_seeded_events_when_fake_core(monkeypatch, recorder):
    from app.scheduler import run_watchdog

    class Recorder:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("app.mcp_client.build_client", lambda *a, **k: Recorder())

    import asyncio

    asyncio.run(run_watchdog(Settings(fake_core=True)))

    assert len(recorder.made) == 1
    assert recorder.made[0].closed
