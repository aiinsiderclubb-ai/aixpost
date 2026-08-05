"""Durable cooperative control shared by local and queue workers."""

from __future__ import annotations

import time
import threading
from typing import Callable, Optional


class TaskStopped(RuntimeError):
    """Raised when durable task control requests cancellation."""


class CooperativeTaskControl:
    def __init__(self, store, task_id: int, user_id: int, poll_interval: float = 0.25):
        self.store = store
        self.task_id = task_id
        self.user_id = user_id
        self.poll_interval = poll_interval
        self._last_ack: Optional[tuple[str, str]] = None

    def state(self) -> dict:
        state = self.store.get_control_state(self.task_id, self.user_id)
        if not state:
            raise TaskStopped("Task ownership changed or task no longer exists")
        self.store.heartbeat_task(self.task_id)
        return state

    def checkpoint(
        self,
        *,
        on_pause: Optional[Callable[[], None]] = None,
        on_resume: Optional[Callable[[], None]] = None,
        on_stop: Optional[Callable[[], None]] = None,
        allow_pause: bool = True,
    ) -> str:
        state = self.state()
        action = state.get("requested_action") or "none"
        if action == "stop":
            if on_stop:
                on_stop()
            self._ack("stopping", "stop")
            raise TaskStopped("Stopped by user")
        if action == "pause":
            if not allow_pause:
                return "pause_unsupported"
            if on_pause:
                on_pause()
            self._ack("paused", "pause")
            return "paused"
        if action == "resume" or (
            action == "none" and state.get("acknowledged_state") == "paused"
        ):
            if on_resume:
                on_resume()
            self._ack("running", "resume")
            return "running"
        return state.get("acknowledged_state") or state.get("status") or "running"

    def wait_while_paused(
        self,
        *,
        on_pause: Optional[Callable[[], None]] = None,
        on_resume: Optional[Callable[[], None]] = None,
        on_stop: Optional[Callable[[], None]] = None,
    ) -> None:
        while True:
            outcome = self.checkpoint(
                on_pause=on_pause, on_resume=on_resume, on_stop=on_stop,
            )
            if outcome != "paused":
                return
            time.sleep(self.poll_interval)

    def sleep(self, seconds: float, **callbacks) -> None:
        deadline = time.monotonic() + max(0, seconds)
        while time.monotonic() < deadline:
            self.wait_while_paused(**callbacks)
            time.sleep(min(self.poll_interval, max(0, deadline - time.monotonic())))

    def _ack(self, state: str, action: str) -> None:
        key = (state, action)
        if self._last_ack != key:
            self.store.acknowledge_control(self.task_id, state, action)
            self._last_ack = key


class DurableControlMonitor:
    """Poll control state when a legacy operation cannot call checkpoints itself."""

    def __init__(self, control: CooperativeTaskControl, on_stop: Callable[[], None]):
        self.control = control
        self.on_stop = on_stop
        self._done = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name=f"control-{control.task_id}", daemon=True,
        )

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_args):
        self._done.set()
        self._thread.join(timeout=2)

    def _run(self):
        while not self._done.wait(self.control.poll_interval):
            state = self.control.state()
            if state.get("requested_action") == "stop":
                self.on_stop()
                self.control._ack("stopping", "stop")
                return
