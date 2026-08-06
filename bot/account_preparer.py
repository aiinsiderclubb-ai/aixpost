"""Prepare Facebook account sessions (visible Chrome + CAPTCHA wait)."""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


def _fetcher_cls():
    from bot.group_fetcher import FacebookGroupFetcher
    return FacebookGroupFetcher


def _manual_timeout() -> int:
    from bot.group_fetcher import MANUAL_VERIFICATION_TIMEOUT
    return int(MANUAL_VERIFICATION_TIMEOUT)

# Active prepare/fetch instances keyed by account_id for resume-manual signals.
_ACTIVE_PREPARERS: Dict[int, "AccountPreparer"] = {}
_LOCK = threading.Lock()


def get_active_preparer(account_id: int) -> Optional["AccountPreparer"]:
    with _LOCK:
        return _ACTIVE_PREPARERS.get(int(account_id))


class AccountPreparer:
    """Open visible Chrome, complete login/CAPTCHA, mark session trusted."""

    def __init__(
        self,
        *,
        user_id: int,
        account_id: int,
        username: str,
        password: str,
        profile_dir: Optional[str] = None,
        progress_callback: Optional[Callable[[dict], None]] = None,
        timeout_seconds: Optional[int] = None,
    ):
        self.user_id = int(user_id)
        self.account_id = int(account_id)
        self.username = username
        self.password = password
        self.profile_dir = profile_dir
        self.progress_callback = progress_callback
        self.timeout_seconds = timeout_seconds or max(_manual_timeout(), 900)
        self.resume_event = threading.Event()
        self.stop_event = threading.Event()
        self.fetcher = None
        self.error: Optional[str] = None
        self.status = "idle"
        self.message = ""

    def _emit(self, **payload) -> None:
        self.status = payload.get("status", self.status)
        self.message = payload.get("message", self.message)
        if self.progress_callback:
            try:
                self.progress_callback(payload)
            except Exception:
                pass

    def signal_resume_manual(self) -> bool:
        """User clicked 'I completed CAPTCHA'."""
        self.resume_event.set()
        if self.fetcher:
            setattr(self.fetcher, "manual_resume_requested", True)
        self._emit(
            status="waiting_manual",
            step="manual_resume",
            message="Проверяем сессию после ручной проверки...",
            progress=25,
        )
        return True

    def stop(self) -> bool:
        """Cooperatively stop preparation and close its browser."""
        self.stop_event.set()
        self.resume_event.set()
        if self.fetcher:
            self.fetcher.cleanup()
        return True

    def validate_only(self) -> dict:
        """Quick check: open profile and see if already logged in."""
        with _LOCK:
            _ACTIVE_PREPARERS[self.account_id] = self
        try:
            self._emit(status="running", step="validate", message="Проверка сохранённой сессии...", progress=10)
            fetcher = self._build_fetcher()
            self.fetcher = fetcher
            if not fetcher.setup_driver():
                self.error = fetcher.error or "Failed to start browser"
                return {"trusted": False, "status": "unknown", "error": self.error}
            trusted = bool(fetcher.is_logged_in())
            if trusted:
                fetcher.save_session()
                self._emit(status="trusted", step="validated", message="Сессия валидна", progress=100)
                return {
                    "trusted": True,
                    "status": "trusted",
                    "profile_dir": fetcher.profile_dir,
                    "validated_at": datetime.utcnow().isoformat(),
                }
            self._emit(status="needs_verify", step="validated", message="Сессия невалидна — нужен Prepare", progress=100)
            return {
                "trusted": False,
                "status": "needs_verify",
                "profile_dir": fetcher.profile_dir,
                "error": "Not logged in",
            }
        finally:
            self._cleanup_fetcher()
            with _LOCK:
                _ACTIVE_PREPARERS.pop(self.account_id, None)

    def prepare(self) -> dict:
        """Full prepare flow: visible login + CAPTCHA wait + trust mark."""
        with _LOCK:
            _ACTIVE_PREPARERS[self.account_id] = self
        try:
            self._emit(status="running", step="prepare_start", message="Запуск Chrome...", progress=5)
            fetcher = self._build_fetcher()
            self.fetcher = fetcher
            # Patch wait loop to honor resume_event and longer timeout.
            self._patch_manual_wait(fetcher)

            if not fetcher.setup_driver():
                self.error = fetcher.error or "Failed to start browser"
                self._emit(status="failed", step="driver_setup", message=self.error, progress=0)
                return {"trusted": False, "status": "failed", "error": self.error}

            self._emit(status="running", step="login", message="Вход в Facebook...", progress=20)
            ok = fetcher.login()
            if not ok:
                # Still waiting / failed
                if getattr(fetcher, "manual_verification_needed", False) or (
                    fetcher.error and "CAPTCHA" in (fetcher.error or "")
                ):
                    status = "needs_verify"
                else:
                    status = "failed"
                self.error = fetcher.error or "Login failed"
                self._emit(status=status, step="login", message=self.error, progress=30)
                return {
                    "trusted": False,
                    "status": status,
                    "error": self.error,
                    "profile_dir": fetcher.profile_dir,
                    "needs_manual": bool(getattr(fetcher, "manual_verification_needed", False)),
                }

            if not fetcher.is_logged_in():
                self.error = "Login completed but session not verified"
                self._emit(status="needs_verify", step="verify", message=self.error, progress=40)
                return {
                    "trusted": False,
                    "status": "needs_verify",
                    "error": self.error,
                    "profile_dir": fetcher.profile_dir,
                }

            fetcher.save_session()
            self._emit(status="trusted", step="completed", message="Аккаунт подготовлен (Trusted)", progress=100)
            return {
                "trusted": True,
                "status": "trusted",
                "profile_dir": fetcher.profile_dir,
                "validated_at": datetime.utcnow().isoformat(),
            }
        except Exception as exc:
            self.error = str(exc)
            logger.exception("Prepare failed for account %s", self.account_id)
            self._emit(status="failed", step="exception", message=self.error, progress=0)
            return {"trusted": False, "status": "failed", "error": self.error}
        finally:
            self._cleanup_fetcher()
            with _LOCK:
                _ACTIVE_PREPARERS.pop(self.account_id, None)

    def _build_fetcher(self):
        profile = self.profile_dir
        if not profile:
            base = os.path.join(
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
                "user_data",
                "profiles",
            )
            profile = os.path.join(base, f"profile_account_{self.account_id}")
        os.makedirs(profile, exist_ok=True)

        def _progress(payload: dict):
            merged = dict(payload)
            if merged.get("status") == "waiting_manual":
                self.status = "waiting_manual"
            self._emit(**merged)

        fetcher = _fetcher_cls()(
            username=self.username,
            password=self.password,
            headless=False,
            use_session=True,
            user_id=self.user_id,
            profile_dir=profile,
            progress_callback=_progress,
        )
        return fetcher

    def _patch_manual_wait(self, fetcher) -> None:
        original = fetcher._wait_for_manual_verification

        def _wait(reason: str, timeout_seconds: Optional[int] = None) -> bool:
            timeout = timeout_seconds or self.timeout_seconds
            fetcher.manual_verification_needed = True
            fetcher.step = "manual_verification"
            deadline = time.time() + timeout
            self._emit(
                status="waiting_manual",
                step="manual_verification",
                message=f"{reason} Пройдите проверку в Chrome или нажмите «Я прошёл проверку».",
                progress=22,
            )
            while time.time() < deadline:
                if self.stop_event.is_set():
                    fetcher.error = "Stopped by user"
                    return False
                if not fetcher._ensure_window_alive("manual verification"):
                    return False
                # Cross-process resume from dashboard (RQ worker)
                try:
                    from bot.prepare_signals import consume_prepare_resume

                    if consume_prepare_resume(self.account_id):
                        self.resume_event.set()
                        setattr(fetcher, "manual_resume_requested", True)
                except Exception:
                    pass
                if self.resume_event.is_set() or getattr(fetcher, "manual_resume_requested", False):
                    self.resume_event.clear()
                    setattr(fetcher, "manual_resume_requested", False)
                    time.sleep(2)
                if fetcher.is_logged_in():
                    fetcher.manual_verification_needed = False
                    fetcher.save_session()
                    return True
                remaining = max(0, int(deadline - time.time()))
                self._emit(
                    status="waiting_manual",
                    step="manual_verification",
                    message=f"{reason} Осталось ~{remaining // 60} мин. Браузер открыт.",
                    progress=22,
                )
                time.sleep(2)
            fetcher.error = f"{reason} Время ожидания истекло ({timeout // 60} мин)."
            return False

        fetcher._wait_for_manual_verification = _wait  # type: ignore[method-assign]
        # Keep reference so linters don't complain about unused original.
        setattr(fetcher, "_original_wait_for_manual_verification", original)

    def _cleanup_fetcher(self) -> None:
        if self.fetcher:
            try:
                # Keep profile; only close browser window.
                self.fetcher.cleanup()
            except Exception:
                pass
            self.fetcher = None
