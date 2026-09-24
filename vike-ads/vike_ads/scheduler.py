"""Optional weekly research refresh (APScheduler)."""

from __future__ import annotations

import logging

from .orchestrator import Orchestrator

log = logging.getLogger(__name__)


def weekly_job(orch: Orchestrator) -> None:
    try:
        res = orch.research(orch.settings.weekly_research_topic)
        log.info("weekly research refresh saved: %s (%d findings)", res.report.id, len(res.report.findings))
    except Exception:  # a failed run must not kill the scheduler
        log.exception("weekly research refresh failed")


def make_scheduler(orch: Orchestrator, *, blocking: bool):
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    s = orch.settings
    sched = (BlockingScheduler if blocking else BackgroundScheduler)(timezone=s.timezone)
    sched.add_job(weekly_job, CronTrigger(day_of_week=s.weekly_research_day, hour=s.weekly_research_hour,
                                          minute=0, timezone=s.timezone),
                  args=[orch], id="weekly-research", replace_existing=True, misfire_grace_time=6 * 3600)
    return sched
