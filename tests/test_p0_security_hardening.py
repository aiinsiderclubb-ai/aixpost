import os

import pytest


@pytest.fixture()
def app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("FERNET_KEY", "x" * 44)
    # Valid Fernet key
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("FERNET_KEY", key)
    monkeypatch.setenv("FLASK_DEBUG", "true")

    import importlib
    import run_test_v2 as module
    importlib.reload(module)

    application = module.create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "JWT_SECRET_KEY": "test-jwt",
        "WTF_CSRF_ENABLED": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'app.db'}",
        "RUNTIME_DB_PATH": str(tmp_path / "runtime.db"),
        "RATELIMIT_ENABLED": False,
    })
    with application.app_context():
        module.db.create_all()
        user = module.User(
            email="user@example.test",
            first_name="U",
            last_name="Ser",
            email_verified=True,
            current_plan="FREE",
        )
        user.set_password("safe-test-password1")
        admin = module.User(
            email="admin@example.test",
            first_name="A",
            last_name="Dmin",
            email_verified=True,
            role="admin",
            current_plan="PREMIUM",
        )
        admin.set_password("safe-test-password1")
        module.db.session.add_all([user, admin])
        module.db.session.commit()
    yield module, application
    with application.app_context():
        module.db.session.remove()
        module.db.drop_all()


def test_debug_routes_hidden_when_not_debug(app_module):
    module, application = app_module
    application.debug = False
    client = application.test_client()
    assert client.get("/groups_no_jwt").status_code == 404
    assert client.get("/test_groups_simple").status_code == 404


def test_csrf_rejects_mutating_api_without_token(app_module):
    module, application = app_module
    client = application.test_client()
    login = client.post("/api/auth/login", json={
        "email": "user@example.test",
        "password": "safe-test-password1",
    })
    assert login.status_code == 200
    # CSRF enabled in this fixture — mutating call without token must fail
    resp = client.post("/api/user/settings", json={"use_headless": True})
    assert resp.status_code in (400, 403)


def test_plan_change_admin_only(app_module):
    module, application = app_module
    # Disable CSRF for focused authz check
    application.config["WTF_CSRF_ENABLED"] = False
    client = application.test_client()

    user_login = client.post("/api/auth/login", json={
        "email": "user@example.test",
        "password": "safe-test-password1",
    })
    token = user_login.get_json()["access_token"]
    denied = client.post(
        "/api/user/plan",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan": "PREMIUM"},
    )
    assert denied.status_code == 403

    admin_login = client.post("/api/auth/login", json={
        "email": "admin@example.test",
        "password": "safe-test-password1",
    })
    admin_token = admin_login.get_json()["access_token"]
    with application.app_context():
        target = module.User.query.filter_by(email="user@example.test").first()
        target_id = target.id
    ok = client.post(
        "/api/user/plan",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"plan": "PLUS", "user_id": target_id},
    )
    assert ok.status_code == 200
    assert ok.get_json()["current_plan"] == "PLUS"


def test_progress_tracker_is_per_user(app_module):
    module, _application = app_module
    a = module.reset_progress_tracker(1)
    b = module.reset_progress_tracker(2)
    a.update(message="user-one")
    b.update(message="user-two")
    assert module.get_progress_tracker(1).message == "user-one"
    assert module.get_progress_tracker(2).message == "user-two"
    assert a is not b
