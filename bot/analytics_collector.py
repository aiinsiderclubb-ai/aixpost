"""Shared analytics collection logic for scheduler and RQ workers."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from bot.analytics_db import analytics_db
from bot.post_metrics import fetch_post_metrics

logger = logging.getLogger(__name__)


def process_single_check(check: Dict, cookies: Optional[list] = None) -> Dict:
    check_id = check["id"]
    check_type = check.get("check_type")
    try:
        metrics = fetch_post_metrics(
            group_url=check.get("group_url") or "",
            message=check.get("message_text") or "",
            post_url=check.get("post_url"),
            post_id=check.get("post_id"),
            cookies=cookies,
            page_limit=1,
        )
        if not metrics:
            analytics_db.mark_check_failed(check_id, "No metrics returned by facebook-scraper")
            return {"check_id": check_id, "status": "failed", "check_type": check_type}
        analytics_db.mark_check_completed(check_id, metrics)
        return {
            "check_id": check_id,
            "status": "completed",
            "check_type": check_type,
            "metrics": metrics,
        }
    except Exception as exc:
        analytics_db.mark_check_failed(check_id, str(exc))
        logger.error("Analytics check %s failed: %s", check_id, exc)
        return {"check_id": check_id, "status": "failed", "check_type": check_type, "error": str(exc)}


def process_pending_checks(limit: int = 10, cookies: Optional[list] = None) -> Dict:
    pending = analytics_db.get_pending_analytics_checks()
    results = []
    for check in pending[:limit]:
        results.append(process_single_check(check, cookies=cookies))
    analytics_db.calculate_recommendation_scores()
    completed = sum(1 for item in results if item.get("status") == "completed")
    failed = sum(1 for item in results if item.get("status") == "failed")
    return {
        "processed": len(results),
        "completed": completed,
        "failed": failed,
        "pending_before": len(pending),
        "results": results,
    }
