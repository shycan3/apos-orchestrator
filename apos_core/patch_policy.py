"""Patch policy and dry-run preview for safe file modifications."""
from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any, Dict, Optional, Union


class PatchPolicy:
    def __init__(self, workspace_root: Union[str, Path]):
        self.workspace_root = Path(workspace_root).resolve()
        self.allowed_roots = {
            "workspace",
            "src",
            "app",
            "cli",
            "apos_core",
            "tests",
            "docs",
        }
        self.allowed_files = {"README.md"}
        self.protected_prefixes = {
            ".git/",
            ".venv/",
            "node_modules/",
            "__pycache__/",
            ".pytest_cache/",
            ".apos/history.sqlite3",
        }
        self.protected_exact = {".env"}
        self.protected_globs = {"*.sqlite3", "secrets.*", "private_key.*"}

    def _normalize_rel(self, target: str) -> Dict[str, Any]:
        if not isinstance(target, str) or not target.strip():
            return {"ok": False, "reason": "invalid_path"}

        raw = target.strip().replace("\\", "/")
        if raw.startswith("~"):
            return {"ok": False, "reason": "home_path_not_allowed"}

        p = Path(raw)
        if p.is_absolute():
            return {"ok": False, "reason": "absolute_path_not_allowed"}
        if any(part == ".." for part in p.parts):
            return {"ok": False, "reason": "path_traversal_not_allowed"}

        resolved = (self.workspace_root / p).resolve()
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError:
            return {"ok": False, "reason": "path_outside_workspace"}

        rel = str(p).replace("\\", "/")
        return {"ok": True, "relative": rel, "absolute": str(resolved)}

    def _is_protected(self, relative_path: str) -> Optional[str]:
        rel = relative_path.strip("/")
        lower_rel = rel.lower()

        if lower_rel in {x.lower() for x in self.protected_exact}:
            return "protected_exact_path"

        for prefix in self.protected_prefixes:
            if lower_rel == prefix.rstrip("/").lower() or lower_rel.startswith(prefix.lower()):
                return "protected_prefix"

        basename = Path(rel).name.lower()
        for pattern in self.protected_globs:
            if fnmatch.fnmatch(lower_rel, pattern.lower()) or fnmatch.fnmatch(basename, pattern.lower()):
                return "protected_pattern"

        return None

    def _is_allowed_root(self, relative_path: str) -> bool:
        rel = relative_path.strip("/")
        if rel in self.allowed_files:
            return True
        first = rel.split("/", 1)[0]
        return first in self.allowed_roots

    def validate_target(self, target: str) -> Dict[str, Any]:
        normalized = self._normalize_rel(target)
        if not normalized["ok"]:
            return {
                "allowed": False,
                "blocked_reason": normalized["reason"],
                "target": target,
                "relative_target": None,
            }

        rel = normalized["relative"]
        protected_reason = self._is_protected(rel)
        if protected_reason:
            return {
                "allowed": False,
                "blocked_reason": protected_reason,
                "target": target,
                "relative_target": rel,
            }

        if not self._is_allowed_root(rel):
            return {
                "allowed": False,
                "blocked_reason": "path_not_in_allowlist",
                "target": target,
                "relative_target": rel,
            }

        return {
            "allowed": True,
            "blocked_reason": "",
            "target": target,
            "relative_target": rel,
        }
