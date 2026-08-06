"""Redis pub/sub bridge so RQ workers can emit Socket.IO events via the web process."""

from __future__ import annotations

import json
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

CHANNEL = "aipostx:user_events"


def publish_user_event(redis_conn, user_id: int, event: str, data: dict) -> None:
    if redis_conn is None:
        return
    try:
        redis_conn.publish(
            CHANNEL,
            json.dumps({"user_id": int(user_id), "event": event, "data": data or {}}),
        )
    except Exception as exc:
        logger.warning("Failed to publish user event: %s", exc)


def start_user_event_listener(redis_conn, broadcast_fn: Callable[[int, str, dict], None]) -> Optional[threading.Thread]:
    """Subscribe in a daemon thread and forward messages to broadcast_fn(user_id, event, data)."""
    if redis_conn is None:
        return None

    def _loop():
        try:
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(CHANNEL)
            for message in pubsub.listen():
                if message is None or message.get("type") != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                    broadcast_fn(
                        int(payload["user_id"]),
                        payload.get("event") or "task_event",
                        payload.get("data") or {},
                    )
                except Exception as parse_err:
                    logger.warning("Bad pubsub payload: %s", parse_err)
        except Exception as exc:
            logger.warning("User event listener stopped: %s", exc)

    thread = threading.Thread(target=_loop, name="aipostx-user-events", daemon=True)
    thread.start()
    return thread
