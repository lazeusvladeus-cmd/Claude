"""Optional weekly research refresh (APScheduler)."""

from __future__ import annotations

import logging

from .orchestrator import Orchestrator

log = logging.getLogger(__name__)


def weekly_job(orch: Orchestrator) -> None:
    try:
        res = orch.research(orch.settings.weekly_research_topic)
        log.info("weekly research refresh saved: %s (%d findings)", res.report.id, len(res.report.findings))
        if orch.mirror is not None:
            orch.mirror.safe_push()
    except Exception:  # a failed run must not kill the scheduler
        log.exception("weekly research refresh failed")


def research_is_due(orch: Orchestrator, max_age_days: float = 7) -> bool:
    """True when there is no report, or the newest one is older than a week.

    Free hosts sleep when nobody visits, so a cron trigger can be missed; the web
    process checks this when it starts and catches up.
    """
    from datetime import datetime, timezone
    latest = orch.store.latest_report(with_findings=True)  # a failed run must not count
    if latest is None:
        return True
    return (datetime.now(timezone.utc) - latest.created_at).total_seconds() > max_age_days * 86400


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
