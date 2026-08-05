import os
import pytest


def test_fernet_key_required(monkeypatch):
    monkeypatch.delenv('FERNET_KEY', raising=False)
    with pytest.raises(RuntimeError):
        # Importing config should fail without key
        import importlib
        import app.config as cfg
        importlib.reload(cfg)


def test_security_headers_present(monkeypatch):
    monkeypatch.setenv('FERNET_KEY', 'gAAAAABkyAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==')
    from run_test_v2 import app
    with app.test_client() as c:
        resp = c.get('/')
        assert resp.headers.get('Strict-Transport-Security') is not None
        assert resp.headers.get('X-Frame-Options') == 'DENY'
        assert resp.headers.get('X-Content-Type-Options') == 'nosniff'
        assert "default-src 'self'" in resp.headers.get('Content-Security-Policy', '')



