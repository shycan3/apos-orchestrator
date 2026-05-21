"""Standard result envelope for APOS task outcomes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


SCHEMA_VERSION = "1.0"

ALLOWED_STATUSES = {
    "success",
    "failed",
    "patch_blocked",
    "command_blocked",
    "snapshot_failed",
    "validation_failed",
    "internal_error",
}


EXIT_CODE_MEANINGS = {
    -3: "command policy blocked",
    -4: "patch policy blocked",
    -5: "snapshot failed",
    -6: "task envelope validation failed",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_result_envelope(
    *,
    task_id: str,
    status: str,
    exit_code: Optional[int],
    started_at: str,
    finished_at: str,
    duration_ms: int,
    patch_applied: bool,
    patch_blocked: bool,
    patch_blocked_reason: str,
    patch_preview: Optional[Any],
    snapshot_enabled: bool,
    snapshot_commit: Optional[str],
    snapshot_error: str,
    command: Optional[Any],
    command_allowed: Optional[bool],
    policy_blocked: bool,
    blocked_reason: str,
    stdout: str,
    stderr: str,
    workspace_root: str,
    history_db_path: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "status": status,
        "exit_code": exit_code,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "patch_applied": patch_applied,
        "patch_blocked": patch_blocked,
        "patch_blocked_reason": patch_blocked_reason,
        "patch_preview": patch_preview,
        "snapshot_enabled": snapshot_enabled,
        "snapshot_commit": snapshot_commit,
        "snapshot_error": snapshot_error,
        "command": command,
        "command_allowed": command_allowed,
        "policy_blocked": policy_blocked,
        "blocked_reason": blocked_reason,
        "stdout": stdout,
        "stderr": stderr,
        "workspace_root": workspace_root,
        "history_db_path": history_db_path,
        "meta": meta or {},
    }
