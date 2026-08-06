import pytest
from cryptography.fernet import Fernet


def test_fernet_key_required(monkeypatch, tmp_path):
    monkeypatch.delenv("FERNET_KEY", raising=False)
    monkeypatch.setattr("app.core.config.PROJECT_ROOT", tmp_path)
    from app.core.config import AppConfig

    with pytest.raises(RuntimeError):
        AppConfig.get_fernet_key()


def test_security_headers_present(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    import run_test_v2 as rt

    if not rt._app_initialized:
        rt.create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "JWT_SECRET_KEY": "test-jwt-secret-key",
                "WTF_CSRF_ENABLED": False,
            }
        )
    with rt.app.test_client() as c:
        resp = c.get("/")
        assert resp.headers.get("Strict-Transport-Security") is not None
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert "default-src 'self'" in resp.headers.get("Content-Security-Policy", "")
