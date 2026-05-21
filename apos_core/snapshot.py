"""Git snapshot manager for pre-task commits and rollback baseline."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Union, Dict, Any


class SnapshotManager:
    def __init__(self, workspace_root: Union[str, Path]):
        self.workspace_root = Path(workspace_root).resolve()

    def _run_git(self, args: list[str], timeout: int = 20) -> Dict[str, Any]:
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=str(self.workspace_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )
            return {
                "command": ["git", *args],
                "cwd": str(self.workspace_root),
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except Exception as exc:
            return {
                "command": ["git", *args],
                "cwd": str(self.workspace_root),
                "returncode": -1,
                "stdout": "",
                "stderr": str(exc),
            }

    def _validate_relative_path(self, relative_path: str) -> Dict[str, Any]:
        p = Path(relative_path)
        if p.is_absolute():
            return {"ok": False, "reason": "absolute_path_not_allowed"}
        if any(part == ".." for part in p.parts):
            return {"ok": False, "reason": "path_traversal_not_allowed"}

        resolved = (self.workspace_root / p).resolve()
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError:
            return {"ok": False, "reason": "path_outside_workspace"}

        return {"ok": True, "relative_path": str(p).replace("\\", "/")}

    def is_git_repository(self, timeout: int = 10) -> bool:
        res = self._run_git(["rev-parse", "--is-inside-work-tree"], timeout=timeout)
        return res["returncode"] == 0 and res["stdout"].strip() == "true"

    def ensure_repository(self, auto_init: bool = False, timeout: int = 15) -> Dict[str, Any]:
        if self.is_git_repository(timeout=timeout):
            return {"ok": True, "initialized": False, "details": "already_git_repo"}

        if not auto_init:
            return {"ok": False, "initialized": False, "details": "not_git_repo"}

        init_res = self._run_git(["init"], timeout=timeout)
        ok = init_res["returncode"] == 0 and self.is_git_repository(timeout=timeout)
        return {
            "ok": ok,
            "initialized": ok,
            "details": init_res,
        }

    def get_status(self, timeout: int = 10) -> Dict[str, Any]:
        return self._run_git(["status", "--short"], timeout=timeout)

    def commit_exists(self, snapshot_commit: str, timeout: int = 10) -> Dict[str, Any]:
        res = self._run_git(["cat-file", "-e", f"{snapshot_commit}^{{commit}}"], timeout=timeout)
        return {
            "ok": res["returncode"] == 0,
            "snapshot_commit": snapshot_commit,
            "git": res,
        }

    def list_changed_files_since(self, snapshot_commit: str, timeout: int = 10) -> Dict[str, Any]:
        commit_check = self.commit_exists(snapshot_commit, timeout=timeout)
        if not commit_check["ok"]:
            return {
                "ok": False,
                "snapshot_commit": snapshot_commit,
                "files": [],
                "message": "snapshot_commit_not_found",
                "commit_check": commit_check,
            }

        diff_res = self._run_git(["diff", "--name-only", snapshot_commit, "HEAD"], timeout=timeout)
        files = [line.strip() for line in diff_res["stdout"].splitlines() if line.strip()]
        return {
            "ok": diff_res["returncode"] == 0,
            "snapshot_commit": snapshot_commit,
            "files": files,
            "git": diff_res,
        }

    def restore_file_from_snapshot(
        self,
        snapshot_commit: str,
        relative_path: str,
        timeout: int = 15,
    ) -> Dict[str, Any]:
        commit_check = self.commit_exists(snapshot_commit, timeout=timeout)
        if not commit_check["ok"]:
            return {
                "ok": False,
                "snapshot_commit": snapshot_commit,
                "path": relative_path,
                "message": "snapshot_commit_not_found",
                "commit_check": commit_check,
            }

        path_check = self._validate_relative_path(relative_path)
        if not path_check["ok"]:
            return {
                "ok": False,
                "snapshot_commit": snapshot_commit,
                "path": relative_path,
                "message": path_check["reason"],
            }

        rel = path_check["relative_path"]
        restore_res = self._run_git(["checkout", snapshot_commit, "--", rel], timeout=timeout)
        return {
            "ok": restore_res["returncode"] == 0,
            "snapshot_commit": snapshot_commit,
            "path": rel,
            "git": restore_res,
        }

    def create_snapshot(
        self,
        task_id: str,
        timeout: int = 20,
        auto_init: bool = False,
    ) -> Dict[str, Any]:
        ensure = self.ensure_repository(auto_init=auto_init, timeout=timeout)
        if not ensure["ok"]:
            return {
                "ok": False,
                "snapshot_commit": None,
                "message": "git repository not available",
                "ensure": ensure,
            }

        add_res = self._run_git(["add", "-A"], timeout=timeout)
        if add_res["returncode"] != 0:
            return {
                "ok": False,
                "snapshot_commit": None,
                "message": "git add failed",
                "add": add_res,
            }

        commit_msg = f"APOS snapshot before task: {task_id}"
        commit_res = self._run_git(["commit", "--allow-empty", "-m", commit_msg], timeout=timeout)
        if commit_res["returncode"] != 0:
            return {
                "ok": False,
                "snapshot_commit": None,
                "message": "git commit failed",
                "commit": commit_res,
            }

        rev_res = self._run_git(["rev-parse", "HEAD"], timeout=timeout)
        snapshot_commit = rev_res["stdout"].strip() if rev_res["returncode"] == 0 else None
        return {
            "ok": snapshot_commit is not None,
            "snapshot_commit": snapshot_commit,
            "message": "snapshot_created" if snapshot_commit else "snapshot_created_but_no_head",
            "commit": commit_res,
        }
