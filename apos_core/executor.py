"""Executor: run commands safely with timeout and capture outputs."""
from __future__ import annotations

import subprocess
import threading
import os
from pathlib import Path
from typing import Optional

from .command_policy import CommandPolicy
from .patch_policy import PatchPolicy


def _is_within_root(path: str, root: str) -> bool:
    try:
        abs_path = os.path.abspath(path)
        abs_root = os.path.abspath(root)
        return os.path.commonpath([abs_path, abs_root]) == abs_root
    except Exception:
        return False


class ExecutionResult(dict):
    pass


class Executor:
    def __init__(self, workspace_root: Optional[str] = None, command_policy: Optional[object] = None):
        self.workspace_root = workspace_root or os.getcwd()
        self.command_policy = command_policy or CommandPolicy()
        self.patch_policy = PatchPolicy(self.workspace_root)

    def run_command(self, cmd, cwd: Optional[str] = None, timeout: int = 30) -> ExecutionResult:
        cwd = cwd or self.workspace_root
        if not _is_within_root(cwd, self.workspace_root):
            raise RuntimeError("Refusing to run outside workspace root")

        check = self.command_policy.validate_command(cmd)
        if not check.get("allowed", False):
            return ExecutionResult(
                stdout="",
                stderr=check.get("blocked_reason", "command_blocked_by_policy"),
                exit_code=-3,
                timed_out=False,
                policy_blocked=True,
                blocked_reason=check.get("blocked_reason", "command_blocked_by_policy"),
            )

        safe_cmd = check.get("normalized_command", cmd)

        proc = subprocess.Popen(
            safe_cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            text=True,
        )

        timer = threading.Timer(timeout, proc.kill)
        try:
            timer.start()
            stdout, stderr = proc.communicate()
            timed_out = proc.returncode == -9 or proc.returncode is None
        finally:
            timer.cancel()

        return ExecutionResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
            timed_out=timed_out,
            policy_blocked=False,
            blocked_reason="",
        )

    def apply_patch(self, changes: list) -> list:
        """Apply a list of changes. Each change is dict: {path, content, action:create|modify|delete}.

        Returns list of applied changes with status.
        """
        previews = self.preview_patch(changes)
        results = []
        for preview in previews:
            if not preview.get("policy_allowed", False):
                results.append(
                    {
                        "path": preview.get("target"),
                        "status": "rejected",
                        "patch_blocked": True,
                        "blocked_reason": preview.get("blocked_reason"),
                        "operation": preview.get("operation"),
                        "target": preview.get("target"),
                    }
                )
                continue

            path = preview.get("target")
            operation = preview.get("operation")
            target = os.path.abspath(os.path.join(self.workspace_root, path))
            content = preview.get("content", "")

            try:
                if operation == "delete":
                    if os.path.exists(target):
                        os.remove(target)
                    results.append({"path": path, "status": "deleted", "patch_blocked": False})
                else:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, "w", encoding="utf-8") as fh:
                        fh.write(content)
                    results.append({"path": path, "status": "written", "patch_blocked": False})
            except Exception as exc:
                results.append({"path": path, "status": "error", "reason": str(exc), "patch_blocked": False})

        return results

    def preview_patch(self, changes: list) -> list:
        previews = []
        for change in changes:
            original_target = change.get("path", "")
            action = change.get("action", "modify")
            content = change.get("content", "")
            check = self.patch_policy.validate_target(original_target)

            operation = self._resolve_operation(action, check.get("relative_target"))

            preview = {
                "target": check.get("relative_target") or original_target,
                "original_target": original_target,
                "operation": operation,
                "policy_allowed": bool(check.get("allowed", False)),
                "blocked_reason": check.get("blocked_reason", ""),
                "patch_blocked": not bool(check.get("allowed", False)),
                "content": content,
                "exists": False,
                "old_size": 0,
                "new_size": len(content.encode("utf-8")) if isinstance(content, str) else 0,
                "line_change_count": 0,
                "diff_summary": "",
            }

            if check.get("allowed"):
                target_abs = Path(self.workspace_root) / check["relative_target"]
                exists = target_abs.exists()
                preview["exists"] = exists
                if exists and target_abs.is_file():
                    old_content = target_abs.read_text(encoding="utf-8", errors="ignore")
                    preview["old_size"] = len(old_content.encode("utf-8"))
                    preview["line_change_count"] = self._line_change_count(old_content, content)
                    preview["diff_summary"] = self._diff_summary(old_content, content)
                else:
                    preview["line_change_count"] = len(str(content).splitlines())
                    preview["diff_summary"] = "new_file"

            previews.append(preview)

        return previews

    def _resolve_operation(self, action: str, relative_target: Optional[str]) -> str:
        if action == "delete":
            return "delete"
        exists = False
        if relative_target:
            exists = (Path(self.workspace_root) / relative_target).exists()
        if action == "create":
            return "overwrite" if exists else "create"
        if action in {"modify", "update"}:
            return "update" if exists else "create"
        return "overwrite" if exists else "create"

    def _line_change_count(self, old: str, new: str) -> int:
        old_lines = old.splitlines()
        new_lines = new.splitlines()
        common = min(len(old_lines), len(new_lines))
        changed = sum(1 for i in range(common) if old_lines[i] != new_lines[i])
        changed += abs(len(old_lines) - len(new_lines))
        return changed

    def _diff_summary(self, old: str, new: str) -> str:
        old_lines = old.splitlines()
        new_lines = new.splitlines()
        return f"old_lines={len(old_lines)}, new_lines={len(new_lines)}, changed_lines={self._line_change_count(old, new)}"
