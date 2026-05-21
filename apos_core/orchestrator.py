"""Orchestrator: basic execution loop tying executor and recorder together."""
from __future__ import annotations

import threading
import queue
import uuid
import json
import os
import time
from pathlib import Path
from typing import Optional, Union

from .executor import Executor
from .recorder import Recorder
from .snapshot import SnapshotManager
from .command_policy import CommandPolicy, AllowAllCommandPolicy
from .result_envelope import build_result_envelope, utc_now_iso
from .task_envelope import validate_task_envelope, envelope_to_task


class Orchestrator:
    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        history_db_path: Optional[Union[str, Path]] = None,
        enable_snapshots: bool = False,
        fail_on_snapshot_error: bool = True,
        snapshot_auto_init_git: bool = False,
        enable_command_policy: bool = True,
        enable_patch_dry_run: bool = True,
    ):
        self.workspace_root = str(Path(workspace_root).resolve()) if workspace_root else os.getcwd()
        self.enable_command_policy = enable_command_policy
        policy = CommandPolicy() if enable_command_policy else AllowAllCommandPolicy()
        self.executor = Executor(self.workspace_root, command_policy=policy)
        self.recorder = Recorder(db_path=history_db_path)
        self.enable_snapshots = enable_snapshots
        self.enable_patch_dry_run = enable_patch_dry_run
        self.fail_on_snapshot_error = fail_on_snapshot_error
        self.snapshot_auto_init_git = snapshot_auto_init_git
        self.snapshot_manager = SnapshotManager(self.workspace_root)
        self._queue = queue.Queue()
        self._worker_thread = None
        self._stop_event = threading.Event()
        self._task_envelopes = {}

    def submit_task(self, task: dict):
        task_id = task.get("id") or str(uuid.uuid4())
        task_payload = dict(task)
        task_payload["id"] = task_id
        self.recorder.record_task(task_id, task_payload)
        self._queue.put(task_payload)
        return task_id

    def get_task_envelope(self, task_id: str):
        return self._task_envelopes.get(task_id)

    def run_task_envelope(self, envelope: dict):
        check = validate_task_envelope(envelope)
        if not check.get("ok"):
            task_id = envelope.get("task_id", "invalid-task") if isinstance(envelope, dict) else "invalid-task"
            started_at = utc_now_iso()
            finished_at = utc_now_iso()
            result = build_result_envelope(
                task_id=task_id,
                status="validation_failed",
                exit_code=-6,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=0,
                patch_applied=False,
                patch_blocked=False,
                patch_blocked_reason="",
                patch_preview=None,
                snapshot_enabled=self.enable_snapshots,
                snapshot_commit=None,
                snapshot_error="",
                command=None,
                command_allowed=None,
                policy_blocked=False,
                blocked_reason="",
                stdout="",
                stderr="task_envelope_validation_failed",
                workspace_root=self.workspace_root,
                history_db_path=str(self.recorder.db_path),
                meta={"validation_errors": check.get("errors", [])},
            )
            self._task_envelopes[task_id] = result
            self.recorder.record_result(
                str(uuid.uuid4()),
                task_id,
                -6,
                "",
                "task_envelope_validation_failed",
                {"validation_errors": check.get("errors", [])},
                result_envelope=result,
            )
            return result

        normalized = check["normalized"]
        task_type = normalized.get("task_type")
        options = normalized.get("options", {})

        old_snapshot = self.enable_snapshots
        old_patch_dry = self.enable_patch_dry_run
        old_cmd_policy = self.enable_command_policy
        old_fail_snapshot = self.fail_on_snapshot_error
        old_policy_obj = self.executor.command_policy

        try:
            self.enable_snapshots = bool(options.get("enable_snapshots", self.enable_snapshots))
            self.enable_patch_dry_run = bool(options.get("enable_patch_dry_run", self.enable_patch_dry_run))
            self.enable_command_policy = bool(options.get("enable_command_policy", self.enable_command_policy))
            self.fail_on_snapshot_error = bool(options.get("fail_on_snapshot_error", self.fail_on_snapshot_error))
            self.executor.command_policy = CommandPolicy() if self.enable_command_policy else AllowAllCommandPolicy()

            if task_type == "preview_patch":
                task = envelope_to_task(normalized)
                task_id = task["id"]
                started_at = utc_now_iso()
                previews = self.executor.preview_patch(task.get("patches", []))
                blocked_items = [p for p in previews if not p.get("policy_allowed", False)]
                status = "patch_blocked" if blocked_items else "success"
                exit_code = -4 if blocked_items else 0
                blocked_reason = "; ".join(
                    f"{item.get('target')}: {item.get('blocked_reason')}" for item in blocked_items
                )
                finished_at = utc_now_iso()
                envelope_result = build_result_envelope(
                    task_id=task_id,
                    status=status,
                    exit_code=exit_code,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=0,
                    patch_applied=False,
                    patch_blocked=bool(blocked_items),
                    patch_blocked_reason=blocked_reason,
                    patch_preview=previews,
                    snapshot_enabled=self.enable_snapshots,
                    snapshot_commit=None,
                    snapshot_error="",
                    command=None,
                    command_allowed=None,
                    policy_blocked=False,
                    blocked_reason="",
                    stdout="",
                    stderr="",
                    workspace_root=self.workspace_root,
                    history_db_path=str(self.recorder.db_path),
                    meta={"task_type": "preview_patch"},
                )
                self._task_envelopes[task_id] = envelope_result
                self.recorder.record_result(
                    str(uuid.uuid4()),
                    task_id,
                    exit_code,
                    "",
                    blocked_reason or "",
                    {"task_type": "preview_patch"},
                    patch_blocked=bool(blocked_items),
                    patch_blocked_reason=blocked_reason,
                    patch_preview={"items": previews},
                    result_envelope=envelope_result,
                )
                return envelope_result

            if task_type == "restore_file":
                task = envelope_to_task(normalized)
                task_id = task["id"]
                restore_meta = normalized.get("meta", {})
                snapshot_commit = restore_meta.get("snapshot_commit")
                restore_path = restore_meta.get("path")
                started_at = utc_now_iso()
                restore_res = self.snapshot_manager.restore_file_from_snapshot(snapshot_commit, restore_path)
                status = "success" if restore_res.get("ok") else "failed"
                exit_code = 0 if restore_res.get("ok") else -1
                err = "" if restore_res.get("ok") else restore_res.get("message", "restore_failed")
                finished_at = utc_now_iso()
                envelope_result = build_result_envelope(
                    task_id=task_id,
                    status=status,
                    exit_code=exit_code,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=0,
                    patch_applied=False,
                    patch_blocked=False,
                    patch_blocked_reason="",
                    patch_preview=None,
                    snapshot_enabled=True,
                    snapshot_commit=snapshot_commit,
                    snapshot_error="",
                    command=None,
                    command_allowed=None,
                    policy_blocked=False,
                    blocked_reason="",
                    stdout=json.dumps(restore_res),
                    stderr=err,
                    workspace_root=self.workspace_root,
                    history_db_path=str(self.recorder.db_path),
                    meta={"task_type": "restore_file", "restore": restore_res},
                )
                self._task_envelopes[task_id] = envelope_result
                self.recorder.record_result(
                    str(uuid.uuid4()),
                    task_id,
                    exit_code,
                    json.dumps(restore_res),
                    err,
                    {"task_type": "restore_file", "restore": restore_res},
                    result_envelope=envelope_result,
                )
                return envelope_result

            task = envelope_to_task(normalized)
            self.submit_task(task)
            timeout = (task.get("timeout", 30) or 30) + 5
            start_wait = time.time()
            while time.time() - start_wait < timeout:
                env = self._task_envelopes.get(task["id"])
                if env:
                    return env
                time.sleep(0.1)

            return {
                "schema_version": "1.0",
                "task_id": task["id"],
                "status": "internal_error",
                "exit_code": -1,
                "stderr": "task_timeout_waiting_for_result",
            }
        finally:
            self.enable_snapshots = old_snapshot
            self.enable_patch_dry_run = old_patch_dry
            self.enable_command_policy = old_cmd_policy
            self.fail_on_snapshot_error = old_fail_snapshot
            self.executor.command_policy = old_policy_obj

    def _process_task(self, task: dict):
        started_at = utc_now_iso()
        started_perf = time.perf_counter()
        task_id = task["id"]
        snapshot_id = None
        snapshot_commit = None
        snapshot_error = ""
        snapshot_meta = {}

        if self.enable_snapshots:
            snapshot_id = str(uuid.uuid4())
            snap_res = self.snapshot_manager.create_snapshot(
                task_id,
                auto_init=self.snapshot_auto_init_git,
            )
            snapshot_meta = {"snapshot": snap_res}
            snapshot_commit = snap_res.get("snapshot_commit")
            if not snap_res.get("ok") and self.fail_on_snapshot_error:
                snapshot_error = snap_res.get("message", "snapshot_failed")
                result_id = str(uuid.uuid4())
                finished_at = utc_now_iso()
                duration_ms = int((time.perf_counter() - started_perf) * 1000)
                envelope = build_result_envelope(
                    task_id=task_id,
                    status="snapshot_failed",
                    exit_code=-5,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    patch_applied=False,
                    patch_blocked=False,
                    patch_blocked_reason="",
                    patch_preview=None,
                    snapshot_enabled=self.enable_snapshots,
                    snapshot_commit=snapshot_commit,
                    snapshot_error=snapshot_error,
                    command=task.get("command"),
                    command_allowed=None,
                    policy_blocked=False,
                    blocked_reason="",
                    stdout="",
                    stderr=f"Snapshot failed: {snapshot_error}",
                    workspace_root=self.workspace_root,
                    history_db_path=str(self.recorder.db_path),
                    meta={"snapshot": snap_res},
                )
                self.recorder.record_result(
                    result_id,
                    task_id,
                    -5,
                    "",
                    f"Snapshot failed: {snapshot_error}",
                    snapshot_meta,
                    snapshot_id=snapshot_id,
                    snapshot_commit=snapshot_commit,
                    result_envelope=envelope,
                )
                self._task_envelopes[task_id] = envelope
                return

        # 1) apply patch if present
        changes = task.get("patches") or []
        apply_report = []
        patch_preview = []
        patch_blocked = False
        patch_blocked_reason = ""
        patch_applied = False
        if changes:
            if self.enable_patch_dry_run:
                patch_preview = self.executor.preview_patch(changes)
                blocked_items = [p for p in patch_preview if not p.get("policy_allowed", False)]
                if blocked_items:
                    patch_blocked = True
                    patch_blocked_reason = "; ".join(
                        f"{item.get('target')}: {item.get('blocked_reason')}" for item in blocked_items
                    )
                    result_id = str(uuid.uuid4())
                    meta = {
                        "apply_report": [],
                        "patch_preview": patch_preview,
                        "patch_blocked": True,
                        "patch_blocked_reason": patch_blocked_reason,
                    }
                    meta.update(snapshot_meta)
                    finished_at = utc_now_iso()
                    duration_ms = int((time.perf_counter() - started_perf) * 1000)
                    envelope = build_result_envelope(
                        task_id=task_id,
                        status="patch_blocked",
                        exit_code=-4,
                        started_at=started_at,
                        finished_at=finished_at,
                        duration_ms=duration_ms,
                        patch_applied=False,
                        patch_blocked=True,
                        patch_blocked_reason=patch_blocked_reason,
                        patch_preview=patch_preview,
                        snapshot_enabled=self.enable_snapshots,
                        snapshot_commit=snapshot_commit,
                        snapshot_error=snapshot_error,
                        command=task.get("command"),
                        command_allowed=None,
                        policy_blocked=False,
                        blocked_reason="",
                        stdout="",
                        stderr=f"Patch dry-run blocked: {patch_blocked_reason}",
                        workspace_root=self.workspace_root,
                        history_db_path=str(self.recorder.db_path),
                        meta=meta,
                    )
                    self.recorder.record_result(
                        result_id,
                        task_id,
                        -4,
                        "",
                        f"Patch dry-run blocked: {patch_blocked_reason}",
                        meta,
                        snapshot_id=snapshot_id,
                        snapshot_commit=snapshot_commit,
                        patch_blocked=True,
                        patch_blocked_reason=patch_blocked_reason,
                        patch_preview={"items": patch_preview},
                        result_envelope=envelope,
                    )
                    self._task_envelopes[task_id] = envelope
                    return

            apply_report = self.executor.apply_patch(changes)
            patch_applied = any(item.get("status") in {"written", "deleted"} for item in apply_report)

        # 2) run command/tests
        command = task.get("command")
        if command:
            result = self.executor.run_command(command, cwd=self.workspace_root, timeout=task.get("timeout", 30))
            result_id = str(uuid.uuid4())
            meta = {"apply_report": apply_report}
            if patch_preview:
                meta["patch_preview"] = patch_preview
            meta["patch_blocked"] = patch_blocked
            if patch_blocked_reason:
                meta["patch_blocked_reason"] = patch_blocked_reason
            meta.update(snapshot_meta)
            meta["policy_blocked"] = bool(result.get("policy_blocked", False))
            if result.get("blocked_reason"):
                meta["blocked_reason"] = result.get("blocked_reason")

            status = "success"
            if result.get("policy_blocked"):
                status = "command_blocked"
            elif result.get("exit_code") not in (0, None):
                status = "failed"

            finished_at = utc_now_iso()
            duration_ms = int((time.perf_counter() - started_perf) * 1000)
            envelope = build_result_envelope(
                task_id=task_id,
                status=status,
                exit_code=result.get("exit_code"),
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                patch_applied=patch_applied,
                patch_blocked=patch_blocked,
                patch_blocked_reason=patch_blocked_reason,
                patch_preview=patch_preview if patch_preview else None,
                snapshot_enabled=self.enable_snapshots,
                snapshot_commit=snapshot_commit,
                snapshot_error=snapshot_error,
                command=task.get("command"),
                command_allowed=not bool(result.get("policy_blocked", False)),
                policy_blocked=bool(result.get("policy_blocked", False)),
                blocked_reason=result.get("blocked_reason", ""),
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                workspace_root=self.workspace_root,
                history_db_path=str(self.recorder.db_path),
                meta=meta,
            )
            self.recorder.record_result(
                result_id,
                task_id,
                result.get("exit_code"),
                result.get("stdout"),
                result.get("stderr"),
                meta,
                snapshot_id=snapshot_id,
                snapshot_commit=snapshot_commit,
                policy_blocked=result.get("policy_blocked"),
                blocked_reason=result.get("blocked_reason"),
                patch_blocked=patch_blocked,
                patch_blocked_reason=patch_blocked_reason,
                patch_preview={"items": patch_preview} if patch_preview else None,
                result_envelope=envelope,
            )
            self._task_envelopes[task_id] = envelope

            # 3) basic failure handling: create a suggestion placeholder
            if result.get("exit_code") not in (0, None):
                suggestion = self._generate_suggestion(task, result)
                sug_id = str(uuid.uuid4())
                self.recorder.record_suggestion(sug_id, task_id, suggestion)
                # write suggestion file
                sug_path = os.path.join(self.workspace_root, f".apos_suggestion_{sug_id}.json")
                with open(sug_path, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps({"task_id": task_id, "suggestion": suggestion}, indent=2))

    def _generate_suggestion(self, task: dict, result: dict) -> str:
        # Placeholder: produce a minimal suggestion message. Real implementation should use LLM analysis.
        return f"Exit code {result.get('exit_code')}. Inspect stderr: {result.get('stderr')[:200]}"

    def start(self):
        if self._worker_thread and self._worker_thread.is_alive():
            return

        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def stop(self):
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        try:
            self.recorder.close()
        except Exception:
            pass

    def _worker_loop(self):
        while not self._stop_event.is_set():
            try:
                task = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._process_task(task)
            except Exception as exc:
                # record an error result
                err_id = str(uuid.uuid4())
                started_at = utc_now_iso()
                finished_at = utc_now_iso()
                envelope = build_result_envelope(
                    task_id=task.get("id"),
                    status="internal_error",
                    exit_code=-1,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=0,
                    patch_applied=False,
                    patch_blocked=False,
                    patch_blocked_reason="",
                    patch_preview=None,
                    snapshot_enabled=self.enable_snapshots,
                    snapshot_commit=None,
                    snapshot_error="",
                    command=None,
                    command_allowed=None,
                    policy_blocked=False,
                    blocked_reason="",
                    stdout="",
                    stderr=str(exc),
                    workspace_root=self.workspace_root,
                    history_db_path=str(self.recorder.db_path),
                    meta={"phase": "processing"},
                )
                self.recorder.record_result(
                    err_id,
                    task.get("id"),
                    -1,
                    "",
                    str(exc),
                    {"phase": "processing"},
                    result_envelope=envelope,
                )
                self._task_envelopes[task.get("id")] = envelope
            finally:
                self._queue.task_done()
