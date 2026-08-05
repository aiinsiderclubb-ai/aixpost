import os
import subprocess
import sys
import types

import pytest


@pytest.fixture(scope="module")
def application(tmp_path_factory):
    root = tmp_path_factory.mktemp("app-integration")
    import run_test_v2 as module

    app = module.create_app({
        "TESTING": True,
        "SECRET_KEY": "integration-secret",
        "JWT_SECRET_KEY": "integration-jwt-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{root / 'app.db'}",
        "RUNTIME_DB_PATH": str(root / "runtime.db"),
        "RATELIMIT_ENABLED": False,
    })
    with app.app_context():
        module.db.create_all()
        first = module.User(
            email="first@example.test", first_name="First", last_name="User",
            email_verified=True,
        )
        first.set_password("safe-test-password")
        second = module.User(
            email="second@example.test", first_name="Second", last_name="User",
            email_verified=True,
        )
        second.set_password("safe-test-password")
        module.db.session.add_all([first, second])
        module.db.session.commit()
    yield module, app
    with app.app_context():
        module.db.session.remove()
        module.db.drop_all()


def _login(client, email="first@example.test"):
    response = client.post("/api/auth/login", json={
        "email": email, "password": "safe-test-password",
    })
    assert response.status_code == 200
    token = response.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_import_is_fast_and_side_effect_free():
    code = """
import threading, time
s = time.monotonic()
import run_test_v2 as app
assert time.monotonic() - s < 3
assert app.runtime_store is None
assert app.redis_conn is None
assert app.job_scheduler is None
assert app.FACEBOOK_POSTER_AVAILABLE is None
assert len(threading.enumerate()) == 1
"""
    env = os.environ.copy()
    env["FLASK_ENV"] = "testing"
    subprocess.run(
        [sys.executable, "-c", code], check=True, timeout=5,
        cwd=os.path.dirname(os.path.dirname(__file__)), env=env,
    )


def test_login_accounts_trust_prepare_without_browser(application, monkeypatch):
    module, app = application
    client = app.test_client()
    headers = _login(client)

    saved = client.post("/api/accounts", headers=headers, json={
        "login_email": "fake-facebook@example.test",
        "password": "never-used-test-password",
        "label": "Test account",
    })
    assert saved.status_code == 201
    account_id = saved.get_json()["account_id"]

    listed = client.get("/api/accounts", headers=headers)
    assert listed.status_code == 200
    assert listed.get_json()["accounts"][0]["id"] == account_id
    assert client.get(f"/api/accounts/{account_id}/trust", headers=headers).status_code == 200

    class ForbiddenPreparer:
        def __init__(self, **kwargs):
            raise AssertionError("Chrome must not be constructed by this integration test")

    monkeypatch.setitem(
        sys.modules, "bot.account_preparer",
        types.SimpleNamespace(AccountPreparer=ForbiddenPreparer),
    )
    monkeypatch.setattr(module.task_manager, "start_task", lambda **kw: {
        "id": 101, "status": "queued", "task_type": "prepare_account",
    })
    prepared = client.post(f"/api/accounts/{account_id}/prepare", headers=headers)
    assert prepared.status_code == 202

    other_headers = _login(client, "second@example.test")
    assert client.get(
        f"/api/accounts/{account_id}/trust", headers=other_headers,
    ).status_code == 404


def test_fetch_and_post_trust_gates_then_mocked_dispatch(application, monkeypatch):
    module, app = application
    client = app.test_client()
    headers = _login(client)
    account = module.runtime_store.list_accounts(1)[0]

    fetch = client.post("/api/start_fetch", headers=headers, json={
        "account_id": account["id"],
    })
    assert fetch.status_code == 403
    assert fetch.get_json()["code"] == "SESSION_NOT_TRUSTED"

    post = client.post("/api/post_to_groups", headers=headers, json={
        "account_id": account["id"], "message": "test only",
        "group_urls": ["https://www.facebook.com/groups/test-only"],
    })
    assert post.status_code == 403
    assert post.get_json()["code"] == "SESSION_NOT_TRUSTED"

    module.runtime_store.record_session(
        1, account["id"], "trusted", session_valid=True,
    )
    dispatched = {}

    def fake_posting(**kwargs):
        dispatched.update(kwargs)
        return {"id": 202, "status": "queued", "queue_mode": "mock"}

    monkeypatch.setattr(module, "_start_local_posting_thread", fake_posting)
    post = client.post("/api/post_to_groups", headers=headers, json={
        "account_id": account["id"], "message": "test only",
        "group_urls": ["https://www.facebook.com/groups/test-only"],
    })
    assert post.status_code == 202
    assert dispatched["user_id"] == 1


def test_analytics_are_scoped_and_task_ownership_enforced(application, monkeypatch):
    module, app = application
    client = app.test_client()
    headers = _login(client)
    seen = []

    analytics_db = types.SimpleNamespace(
        get_dashboard_data=lambda user_id: seen.append(("dashboard", user_id)) or {"owner": user_id},
        get_analytics_summary=lambda user_id: seen.append(("summary", user_id)) or {"user_id": user_id},
    )
    scheduler = types.SimpleNamespace(force_analytics_check=lambda: seen.append(("refresh", None)))
    monkeypatch.setitem(sys.modules, "bot.analytics_db", types.SimpleNamespace(analytics_db=analytics_db))
    monkeypatch.setitem(
        sys.modules, "bot.analytics_scheduler",
        types.SimpleNamespace(analytics_scheduler=scheduler),
    )
    assert client.get("/api/analytics/dashboard", headers=headers).get_json()["owner"] == 1
    assert client.post("/api/analytics/refresh", headers=headers).status_code == 200
    assert ("dashboard", 1) in seen and ("summary", 1) in seen

    task_id = module.runtime_store.create_task(2, "posting", "Other user's task", {})
    assert client.get(f"/api/tasks/{task_id}", headers=headers).status_code == 404
