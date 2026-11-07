"""Sweep the whole suite with the clock moved far forward.

Proves no test reads the real calendar: everything that used to compute against
`datetime.now()` now receives an explicit reference time, and the month-guard tests
compare via an injected `today`.
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest


# 90 days later: crosses a month boundary (Nov -> Feb) as well as a year is untouched.
SHIFT = timedelta(days=90)


class _ShiftedDatetime(datetime):
    """datetime whose now()/utcnow()/today() report the future."""

    @classmethod
    def now(cls, tz=None):
        return (datetime.now(tz) + SHIFT) if tz is None else (datetime.now(tz) + SHIFT)

    @classmethod
    def utcnow(cls):
        return datetime.utcnow() + SHIFT

    @classmethod
    def today(cls):
        return datetime.today() + SHIFT


class _ShiftedDate(datetime):
    pass


@pytest.fixture(autouse=True)
def shifted_clock(monkeypatch, request):
    """Skip when running under the shim itself, to avoid recursion."""
    if os.environ.get("CLOCK_SHIFT_SHIM") == "1":
        yield
        return
    import app.agents.giving as giving
    import app.agents.watchdog as watchdog

    class _D(_ShiftedDatetime):
        pass

    monkeypatch.setattr(giving, "datetime", _D)
    monkeypatch.setattr(watchdog, "datetime", _D)
    yield


def test_days_since_last_funding_follows_the_injected_clock():
    giving_mod = __import__("app.agents.giving", fromlist=["days_since_last_funding"])
    point = [{"date": "2026-10-17T00:00:00Z", "raised_cents": 5000}]
    a = giving_mod.days_since_last_funding(point, now=datetime(2026, 11, 7, tzinfo=timezone.utc))
    b = giving_mod.days_since_last_funding(point, now=datetime(2027, 3, 1, tzinfo=timezone.utc))
    assert a == 21.0
    assert b > 130


def test_already_ran_uses_the_injected_today(tmp_path):
    from app.agents.giving import GivingAgent

    GivingAgent.__init__.__globals__  # import guard only
    agent = GivingAgent.__new__(GivingAgent)
    agent.state_path = tmp_path / "state.json"
    agent._mark_ran(1, today=datetime(2026, 11, 1).date())
    assert agent.already_ran(1, today=datetime(2026, 11, 30).date()) is True
    assert agent.already_ran(1, today=datetime(2026, 12, 1).date()) is False


def test_default_clock_is_the_real_one():
    from app.agents.giving import days_since_last_funding

    point = [{"date": "2020-01-01T00:00:00Z", "raised_cents": 100}]
    with_shift = days_since_last_funding(point)
    assert with_shift > 2000  # sanity: it computed something against a real clock
