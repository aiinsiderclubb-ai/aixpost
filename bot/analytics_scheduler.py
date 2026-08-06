"""
Analytics Scheduler
Handles scheduled collection of post performance metrics via facebook-scraper
and daily Telegram digests.
"""

import logging
import os
import threading
import time
from typing import Optional

import schedule

from app.core.config import AppConfig
from bot.analytics_collector import process_pending_checks
from bot.analytics_db import analytics_db

logger = logging.getLogger(__name__)


class AnalyticsScheduler:
    """Scheduler for automated analytics collection."""

    def __init__(self):
        self.running = False
        self.scheduler_thread = None
        self._cookies_provider = None
        self._job_queue = None
        self._digest_recipients_provider = None

    def set_cookies_provider(self, provider) -> None:
        """Optional callable returning Selenium/browser cookies for authenticated scraping."""
        self._cookies_provider = provider

    def set_job_queue(self, queue) -> None:
        """Optional RQ queue for analytics collection workers."""
        self._job_queue = queue

    def set_digest_recipients_provider(self, provider) -> None:
        """Optional callable returning [{user_id, chat_id, label}] for daily digests."""
        self._digest_recipients_provider = provider

    def start(self):
        if self.running:
            logger.warning("Analytics scheduler is already running")
            return

        self.running = True
        schedule.every(10).minutes.do(self._dispatch_collection)
        schedule.every().day.at("10:00").do(self._calculate_recommendations)
        digest_at = (os.environ.get("TELEGRAM_DIGEST_AT") or "20:00").strip() or "20:00"
        schedule.every().day.at(digest_at).do(self._send_daily_digests)

        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True, name="analytics-scheduler")
        self.scheduler_thread.start()
        backend = "rq" if AppConfig.USE_RQ_WORKERS and self._job_queue else "in-process"
        logger.info("Analytics scheduler started (backend=%s, digest_at=%s)", backend, digest_at)

    def stop(self):
        self.running = False
        schedule.clear()
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
        logger.info("Analytics scheduler stopped")

    def _run_scheduler(self):
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)
            except Exception as exc:
                logger.error("Error in scheduler loop: %s", exc)
                time.sleep(60)

    def _dispatch_collection(self):
        pending = analytics_db.get_pending_analytics_checks()
        if not pending:
            return
        if AppConfig.USE_RQ_WORKERS and self._job_queue is not None:
            from rq_tasks import run_analytics_batch_task

            self._job_queue.enqueue(run_analytics_batch_task, limit=10, job_timeout="30m")
            logger.info("Enqueued analytics batch for %s pending checks", len(pending))
            return
        cookies = self._cookies_provider() if self._cookies_provider else None
        result = process_pending_checks(limit=10, cookies=cookies)
        logger.info(
            "Processed analytics checks: completed=%s failed=%s",
            result.get("completed"),
            result.get("failed"),
        )

    def _calculate_recommendations(self):
        try:
            analytics_db.calculate_recommendation_scores()
            top_groups = analytics_db.get_top_performing_groups(5)
            if top_groups:
                logger.info("Top performing groups recalculated (%s entries)", len(top_groups))
        except Exception as exc:
            logger.error("Error calculating recommendations: %s", exc)

    def _send_daily_digests(self):
        try:
            from bot.telegram_reports import send_daily_digests

            recipients = []
            if self._digest_recipients_provider:
                recipients = list(self._digest_recipients_provider() or [])
            if not recipients:
                logger.info("Daily digest skipped: no recipients configured")
                return
            result = send_daily_digests(recipients)
            logger.info(
                "Daily digests sent=%s skipped=%s failed=%s",
                result.get("sent"),
                result.get("skipped"),
                result.get("failed"),
            )
        except Exception as exc:
            logger.error("Error sending daily digests: %s", exc)

    def force_analytics_check(self, check_type: str = None):
        try:
            if not check_type or check_type in ("1h", "24h", "7d", "all"):
                self._dispatch_collection()
            if not check_type or check_type == "recommendations":
                self._calculate_recommendations()
            if check_type == "digest":
                self._send_daily_digests()
        except Exception as exc:
            logger.error("Error in force analytics check: %s", exc)


analytics_scheduler = AnalyticsScheduler()
