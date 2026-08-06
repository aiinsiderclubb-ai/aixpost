"""Cross-process Prepare resume signals (web → RQ worker) via Redis."""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _redis():
    try:
        import redis
        from app.core.config import AppConfig

        url = AppConfig.REDIS_URL
        kwargs = {}
        if str(url).startswith("rediss://"):
            kwargs["ssl_cert_reqs"] = None
        return redis.from_url(url, socket_connect_timeout=3, **kwargs)
    except Exception as exc:
        logger.warning("Prepare signal redis unavailable: %s", exc)
        return None


def resume_key(account_id: int) -> str:
    return f"aipostx:prepare:resume:{int(account_id)}"


def request_prepare_resume(account_id: int, ttl_seconds: int = 900) -> bool:
    conn = _redis()
    if not conn:
        return False
    try:
        conn.setex(resume_key(account_id), int(ttl_seconds), "1")
        return True
    except Exception as exc:
        logger.warning("request_prepare_resume failed: %s", exc)
        return False


def consume_prepare_resume(account_id: int) -> bool:
    conn = _redis()
    if not conn:
        return False
    try:
        key = resume_key(account_id)
        # GETDEL if available
        try:
            value = conn.getdel(key)
        except Exception:
            value = conn.get(key)
            if value:
                conn.delete(key)
        return bool(value)
    except Exception:
        return False


def novnc_embed_url() -> Optional[str]:
    from app.core.config import AppConfig

    base = AppConfig.NOVNC_PUBLIC_URL
    if not base:
        base = (os.environ.get("NOVNC_PUBLIC_URL") or "").strip().rstrip("/")
    if not base:
        return None
    # autoconnect + scale to fit iframe
    return f"{base}/vnc.html?autoconnect=1&resize=scale&reconnect=1"
