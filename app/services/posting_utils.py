"""Posting task helpers shared across API, local runner, and RQ worker."""

from typing import Optional


def poster_status_to_task_status(status: str) -> str:
    normalized = (status or "").lower()
    if "manual login" in normalized or "2fa" in normalized:
        return "waiting_manual"
    if normalized.startswith("paused"):
        return "paused"
    if normalized.startswith("error") or normalized.startswith("failed"):
        return "failed"
    if normalized.startswith("stopped") or normalized.startswith("cancel"):
        return "cancelled"
    if normalized.startswith("completed"):
        return "completed"
    if normalized.startswith("waiting"):
        return "running"
    return "running"
