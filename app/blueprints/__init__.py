"""Register extracted Flask blueprints."""
from __future__ import annotations

import importlib
from flask import Flask

BLUEPRINT_MODULES = (
    "infra",
    "pages",
    "auth",
    "admin",
    "campaigns",
    "scheduler",
    "user",
    "telegram",
    "guide",
    "credentials",
    "groups",
    "accounts",
    "templates",
    "posting",
    "analytics",
)

# Always resolve from run_test_v2 so monkeypatches / late init stay visible.
_PROXY_NAMES = frozenset(
    {
        "runtime_store",
        "task_manager",
        "task_dispatcher",
        "campaign_manager",
        "job_scheduler",
        "redis_conn",
        "job_queue",
        "analytics_queue",
        "poster_instances",
        "_start_local_posting_thread",
        "_start_local_fetch_thread",
        "get_progress_tracker",
        "reset_progress_tracker",
        "broadcast_to_user",
        "broadcast_to_admins",
        "send_telegram_message",
        "encrypt_password",
        "decrypt_password",
    }
)


class _NameProxy:
    """Attribute/call forwarder bound to a run_test_v2 global name."""

    __slots__ = ("_name",)

    def __init__(self, name: str):
        object.__setattr__(self, "_name", name)

    def _target(self):
        import run_test_v2 as rt
        return getattr(rt, self._name)

    def __call__(self, *args, **kwargs):
        return self._target()(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._target(), item)

    def __bool__(self):
        return bool(self._target())

    def __iter__(self):
        return iter(self._target())

    def __repr__(self):
        return f"<NameProxy {self._name}>"


def bind_module_runtime(module_globals: dict) -> None:
    """Copy shared symbols from run_test_v2 into a blueprint module dict."""
    import run_test_v2 as rt

    protected = {
        "bp",
        "bind_runtime",
        "admin_required",
        "limiter",
        "_LimiterProxy",
        "__name__",
        "__doc__",
        "__package__",
        "__file__",
        "__loader__",
        "__spec__",
        "__builtins__",
        "jsonify",
        "request",
        "render_template",
        "redirect",
        "url_for",
        "make_response",
        "current_app",
        "Response",
        "send_file",
        "jwt_required",
        "get_jwt_identity",
        "create_access_token",
        "set_access_cookies",
        "unset_jwt_cookies",
        "wraps",
        "Blueprint",
    }
    for key, value in rt.__dict__.items():
        if key in protected:
            continue
        existing = module_globals.get(key)
        if existing is not None and getattr(existing, "__module__", None) == module_globals.get("__name__"):
            continue
        if key in _PROXY_NAMES:
            module_globals[key] = _NameProxy(key)
        else:
            module_globals[key] = value


def register_blueprints(app: Flask) -> None:
    for name in BLUEPRINT_MODULES:
        mod = importlib.import_module(f"app.blueprints.{name}")
        mod.bind_runtime()
        if name in app.blueprints:
            continue
        app.register_blueprint(mod.bp)


def rebind_all() -> None:
    """Refresh blueprint globals after runtime_store / schedulers are created."""
    for name in BLUEPRINT_MODULES:
        mod = importlib.import_module(f"app.blueprints.{name}")
        mod.bind_runtime()


def blueprint_view(name: str, view: str):
    """Resolve a view function moved onto a blueprint (for csrf.exempt etc.)."""
    mod = importlib.import_module(f"app.blueprints.{name}")
    return getattr(mod, view)
