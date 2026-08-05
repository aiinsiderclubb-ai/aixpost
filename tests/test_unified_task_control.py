import threading
import time

from app.services.task_control import CooperativeTaskControl, TaskStopped
from platform_runtime import RuntimeStore


def _store(tmp_path):
    return RuntimeStore(str(tmp_path / "runtime.db"))


def test_ownership_safe_control_and_progress(tmp_path):
    store = _store(tmp_path)
    first = store.create_task(1, "fetch", "First fetch", {}, status="running")
    second = store.create_task(2, "fetch", "Second fetch", {}, status="running")
    store.append_task_event(first, "halfway", event_type="progress", metadata={"progress": 50})
    store.append_task_event(second, "secret", event_type="progress", metadata={"progress": 90})

    assert store.request_stop(second, 1) is None
    assert store.get_control_state(second, 1) is None
    assert store.get_user_task_summary(1, "fetch")["progress"]["progress"] == 50
    assert store.get_user_task_summary(2, "fetch")["progress"]["progress"] == 90


def test_shared_store_control_matches_rq_process_semantics(tmp_path):
    path = str(tmp_path / "runtime.db")
    web_store = RuntimeStore(path)
    worker_store = RuntimeStore(path)
    task_id = web_store.create_task(7, "posting", "Queue task", {}, status="running")
    control = CooperativeTaskControl(worker_store, task_id, 7, poll_interval=0.01)

    assert web_store.request_pause(task_id, 7)
    assert control.checkpoint() == "paused"
    assert web_store.get_task(task_id)["status"] == "paused"
    assert web_store.request_resume(task_id, 7)
    assert control.checkpoint() == "running"
    assert web_store.get_task(task_id)["requested_action"] == "none"
    assert web_store.request_stop(task_id, 7)
    try:
        control.checkpoint()
        assert False, "stop must interrupt worker"
    except TaskStopped:
        pass
    assert web_store.get_task(task_id)["acknowledged_state"] == "stopping"


def test_local_group_loop_pause_resume_stop(tmp_path):
    store = _store(tmp_path)
    task_id = store.create_task(3, "posting", "Local task", {}, status="running")
    control = CooperativeTaskControl(store, task_id, 3, poll_interval=0.01)
    visited = []

    def mocked_group_loop():
        try:
            for group in range(10):
                control.wait_while_paused()
                visited.append(group)
                control.sleep(0.02)
        except TaskStopped:
            return

    thread = threading.Thread(target=mocked_group_loop)
    thread.start()
    while len(visited) < 1:
        time.sleep(0.005)
    store.request_pause(task_id, 3)
    time.sleep(0.06)
    paused_count = len(visited)
    time.sleep(0.04)
    assert len(visited) == paused_count
    store.request_resume(task_id, 3)
    while len(visited) == paused_count:
        time.sleep(0.005)
    store.request_stop(task_id, 3)
    thread.join(timeout=1)
    assert not thread.is_alive()
    assert len(visited) < 10
