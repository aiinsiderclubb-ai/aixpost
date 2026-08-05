"""Fetch real Facebook post engagement metrics via facebook-scraper."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _extract_group_id(group_url: str) -> Optional[str]:
    match = re.search(r"/groups/(\d+)", group_url or "")
    return match.group(1) if match else None


def _normalize_metrics(raw: Dict[str, Any]) -> Dict[str, Any]:
    likes = int(raw.get("likes") or raw.get("reactions") or 0)
    comments = int(raw.get("comments") or 0)
    shares = int(raw.get("shares") or 0)
    weighted = likes + comments * 3 + shares * 5
    engagement_rate = round(min(100.0, weighted * 0.5), 2)
    performance_score = round(min(100.0, (likes + comments + shares) * 2), 2)
    return {
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "engagement_rate": engagement_rate,
        "performance_score": performance_score,
        "post_url": raw.get("post_url") or raw.get("w3_fb_url"),
        "post_id": str(raw.get("post_id") or ""),
    }


def _message_matches(post_text: str, message: str) -> bool:
    left = re.sub(r"\s+", " ", (post_text or "").strip().lower())
    right = re.sub(r"\s+", " ", (message or "").strip().lower())
    if not right:
        return False
    probe = right[:80]
    return probe in left or left[:80] in right


def fetch_post_metrics(
    *,
    group_url: str,
    message: str,
    post_url: Optional[str] = None,
    post_id: Optional[str] = None,
    cookies: Optional[list] = None,
    credentials: Optional[tuple[str, str]] = None,
    page_limit: int = 1,
) -> Optional[Dict[str, Any]]:
    """Resolve a post in a group and return engagement metrics."""
    try:
        from facebook_scraper import get_posts
    except ImportError as exc:
        logger.warning("facebook-scraper is not installed: %s", exc)
        return None

    kwargs: Dict[str, Any] = {"page_limit": page_limit, "extra_info": True}
    if cookies:
        kwargs["cookies"] = cookies
    if credentials:
        kwargs["credentials"] = credentials

    if post_url:
        try:
            for post in get_posts(post_urls=iter([post_url]), **kwargs):
                return _normalize_metrics(post)
        except Exception as exc:
            logger.debug("Direct post URL scrape failed: %s", exc)

    group_id = _extract_group_id(group_url)
    if not group_id:
        return None

    try:
        for post in get_posts(group=group_id, **kwargs):
            candidate_id = str(post.get("post_id") or "")
            if post_id and candidate_id and candidate_id != str(post_id):
                continue
            if _message_matches(post.get("text") or post.get("post_text") or "", message):
                metrics = _normalize_metrics(post)
                if not metrics.get("post_url") and post.get("post_url"):
                    metrics["post_url"] = post.get("post_url")
                if not metrics.get("post_id") and candidate_id:
                    metrics["post_id"] = candidate_id
                return metrics
    except Exception as exc:
        logger.warning("Group metrics scrape failed for %s: %s", group_url, exc)
        return None

    return None


def selenium_cookies_for_scraper(driver) -> list:
    try:
        return driver.get_cookies() or []
    except Exception:
        return []
