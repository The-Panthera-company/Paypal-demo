"""APScheduler wiring. Off unless SCHEDULER_ENABLED=true.

Jobs: Giving run for every active mandate (monthly), Watchdog scan, Milestone checks.
Nothing here starts on import; main.py only starts it when the flag is set.
"""
from __future__ import annotations

import logging

from .agents.giving import GivingAgent
from .agents.milestone import MilestoneAgent
from .agents.watchdog import CoreEventsSource, FakeEventsSource, WatchdogAgent
from .config import Settings, settings

log = logging.getLogger(__name__)


async def run_giving_for_all() -> list[dict]:
    """One Giving run per active mandate; the monthly guard skips mandates already run."""
    agent = GivingAgent()
    results: list[dict] = []
    try:
        mandates = await agent.mcp.call("list_active_mandates")
        for mandate in mandates or []:
            mandate_id = mandate.get("id")
            if mandate_id is None:
                continue
            try:
                results.append(await agent.run(int(mandate_id)))
            except Exception as exc:
                log.warning("giving run failed for mandate %s: %s", mandate_id, exc)
                results.append({"mandate_id": mandate_id, "error": str(exc)})
    finally:
        await agent.mcp.aclose()
    return results


async def run_watchdog(cfg: Settings | None = None) -> list[dict]:
    """Scan for abuse. The source follows FAKE_CORE: the real feed in a deployment, seeded
    (empty) events under the fake, so a test or demo never reaches for the network."""
    cfg = cfg or settings()
    source = FakeEventsSource() if cfg.fake_core else CoreEventsSource()
    agent = WatchdogAgent(source=source)
    try:
        return await agent.scan()
    finally:
        await agent.mcp.aclose()
        await source.aclose()  # both sources have aclose; FakeEventsSource gains one below


async def run_milestones() -> list[dict]:
    agent = MilestoneAgent()
    try:
        return await agent.scan()
    finally:
        await agent.mcp.aclose()


def build_scheduler(cfg: Settings | None = None):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    cfg = cfg or settings()
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_giving_for_all,
        "interval",
        hours=cfg.giving_interval_hours,
        id="giving",
        replace_existing=True,
    )
    scheduler.add_job(
        run_watchdog,
        "interval",
        seconds=cfg.watchdog_interval_seconds,
        id="watchdog",
        replace_existing=True,
    )
    scheduler.add_job(
        run_milestones,
        "interval",
        seconds=cfg.milestone_interval_seconds,
        id="milestones",
        replace_existing=True,
    )
    return scheduler


def start_if_enabled(cfg: Settings | None = None):
    cfg = cfg or settings()
    if not cfg.scheduler_enabled:
        log.info("scheduler disabled (SCHEDULER_ENABLED=false)")
        return None
    scheduler = build_scheduler(cfg)
    scheduler.start()
    log.info("scheduler started: giving=%sh watchdog=%ss milestones=%ss",
             cfg.giving_interval_hours, cfg.watchdog_interval_seconds,
             cfg.milestone_interval_seconds)
    return scheduler
