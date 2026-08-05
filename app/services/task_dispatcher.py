"""Dispatch background work to RQ workers or in-process persistent threads."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from app.core.config import AppConfig

logger = logging.getLogger(__name__)


class TaskDispatcher:
    def __init__(
        self,
        runtime_store,
        local_task_manager,
        job_queue=None,
        use_rq: Optional[bool] = None,
    ):
        self.store = runtime_store
        self.local = local_task_manager
        self.job_queue = job_queue
        self.use_rq = AppConfig.USE_RQ_WORKERS if use_rq is None else use_rq

    def _rq_available(self) -> bool:
        return bool(self.use_rq and self.job_queue is not None)

    def start_posting(
        self,
        *,
        user_id: int,
        title: str,
        payload: dict,
        local_runner: Callable[[int], dict],
        resumed_from_task_id: Optional[int] = None,
    ) -> dict:
        payload = dict(payload)
        payload["resumable"] = True
        if resumed_from_task_id:
            payload["resumed_from_task_id"] = resumed_from_task_id

        if self._rq_available():
            task_id = self.store.create_task(
                user_id,
                "posting",
                title,
                payload,
                status="queued",
                task_key=f"posting:{user_id}",
                queue_mode="rq",
                resumable=1,
            )
            try:
                from rq_tasks import run_post_task_v2

                self.job_queue.enqueue(
                    run_post_task_v2,
                    task_id=task_id,
                    user_id=user_id,
                    job_timeout="6h",
                )
                logger.info("Enqueued posting task %s for user %s", task_id, user_id)
                return self.store.get_task(task_id) or {"id": task_id, "status": "queued"}
            except Exception as exc:
                logger.warning("RQ enqueue failed, falling back to local thread: %s", exc)
                self.store.append_task_event(
                    task_id,
                    f"RQ enqueue failed; continuing in local worker: {exc}",
                    level="warning",
                    event_type="dispatch",
                )
                return self.local.start_task(
                    user_id=user_id,
                    task_type="posting",
                    title=title,
                    payload=payload,
                    runner=local_runner,
                    task_key=f"posting:{user_id}",
                    existing_task_id=task_id,
                )

        return self.local.start_task(
            user_id=user_id,
            task_type="posting",
            title=title,
            payload=payload,
            runner=local_runner,
            task_key=f"posting:{user_id}",
        )

    def start_fetch(
        self,
        *,
        user_id: int,
        title: str,
        payload: dict,
        local_runner: Callable[[int], dict],
    ) -> dict:
        if self._rq_available():
            task_id = self.store.create_task(
                user_id,
                "fetch",
                title,
                payload,
                status="queued",
                task_key=f"fetch:{user_id}",
                queue_mode="rq",
            )
            try:
                from rq_tasks import run_fetch_task_v2

                self.job_queue.enqueue(
                    run_fetch_task_v2,
                    task_id=task_id,
                    user_id=user_id,
                    headless=bool(payload.get("headless", True)),
                    use_session=bool(payload.get("use_session", True)),
                    job_timeout="2h",
                )
                return self.store.get_task(task_id) or {"id": task_id, "status": "queued"}
            except Exception as exc:
                logger.warning("RQ fetch enqueue failed, falling back to local thread: %s", exc)
                self.store.append_task_event(
                    task_id,
                    f"RQ enqueue failed; continuing in local worker: {exc}",
                    level="warning",
                    event_type="dispatch",
                )
                return self.local.start_task(
                    user_id=user_id,
                    task_type="fetch",
                    title=title,
                    payload=payload,
                    runner=local_runner,
                    task_key=f"fetch:{user_id}",
                    existing_task_id=task_id,
                )

        return self.local.start_task(
            user_id=user_id,
            task_type="fetch",
            title=title,
            payload=payload,
            runner=local_runner,
            task_key=f"fetch:{user_id}",
        )

    def resume_posting(
        self,
        *,
        task_id: int,
        user_id: int,
        title: str,
        payload: dict,
        local_runner: Callable[[int], dict],
    ) -> dict:
        groups = self.store.get_resumable_groups(task_id)
        if not groups:
            raise RuntimeError("No groups left to resume")
        resume_payload = dict(payload)
        resume_payload["group_urls"] = groups
        resume_payload["resume_mode"] = True
        return self.start_posting(
            user_id=user_id,
            title=title or f"Resume task #{task_id}",
            payload=resume_payload,
            local_runner=local_runner,
            resumed_from_task_id=task_id,
        )
