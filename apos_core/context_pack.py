"""Build a safe, compact context pack for web LLM prompts."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .patch_policy import PatchPolicy


DEFAULT_CONTEXT_ROOTS = (
    "workspace",
    "src",
    "app",
    "cli",
    "apos_core",
    "tests",
    "docs",
    "examples",
    "README.md",
)


def _utc_iso_from_timestamp(value: Optional[float]) -> str:
    if value is None:
        return ""
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()


def _safe_json_loads(raw: Any) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class ContextPackBuilder:
    def __init__(self, workspace_root: str | Path, history_db_path: str | Path | None = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.history_db_path = Path(history_db_path) if history_db_path else self.workspace_root / ".apos" / "history.sqlite3"
        self.patch_policy = PatchPolicy(self.workspace_root)

    def build(
        self,
        *,
        max_depth: int = 4,
        max_files: int = 120,
        max_file_preview_chars: int = 1200,
        max_total_chars: int = 12000,
    ) -> Dict[str, Any]:
        files, totals = self._collect_files(
            max_depth=max_depth,
            max_files=max_files,
            max_file_preview_chars=max_file_preview_chars,
            max_total_chars=max_total_chars,
        )
        history = self._collect_recent_history(limit=5)

        return {
            "schema_version": "1.0",
            "workspace_root": str(self.workspace_root),
            "project_root": self.workspace_root.name,
            "allowed_work_paths": list(DEFAULT_CONTEXT_ROOTS),
            "excluded_paths": self._excluded_paths(),
            "current_files": files,
            "recent_history": history,
            "safety_policy": self._safety_policy_summary(),
            "warnings": [
                "Use this pack as a map, not as a full source dump.",
                "Protected paths are excluded to match APOS safety rules.",
            ],
            "limits": {
                "max_depth": max_depth,
                "max_files": max_files,
                "max_file_preview_chars": max_file_preview_chars,
                "max_total_chars": max_total_chars,
            },
            "stats": totals,
        }

    def _excluded_paths(self) -> List[str]:
        return [
            ".git/",
            ".venv/",
            "node_modules/",
            "__pycache__/",
            ".pytest_cache/",
            ".apos/",
            "*.sqlite3",
            ".env",
            "secrets.*",
            "private_key.*",
            ".codex/",
            "specifications/",
            "context/",
            "dist/",
            "build/",
        ]

    def _safety_policy_summary(self) -> Dict[str, Any]:
        return {
            "path_policy": "PatchPolicy",
            "workspace_bound": str(self.workspace_root),
            "protected_prefixes": sorted(self.patch_policy.protected_prefixes),
            "protected_exact": sorted(self.patch_policy.protected_exact),
            "protected_globs": sorted(self.patch_policy.protected_globs),
            "allowed_patch_roots": sorted(self.patch_policy.allowed_roots),
            "notes": [
                "Context Pack excludes protected paths and never emits full file contents by default.",
                "Search and replace operations should use the patch engine, not the pack.",
            ],
        }

    def _collect_files(
        self,
        *,
        max_depth: int,
        max_files: int,
        max_file_preview_chars: int,
        max_total_chars: int,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        total_preview_chars = 0
        visited = 0

        for root_name in DEFAULT_CONTEXT_ROOTS:
            root_path = self.workspace_root / root_name
            if not root_path.exists():
                continue

            if root_path.is_file():
                rel = root_path.relative_to(self.workspace_root).as_posix()
                if self._should_include(rel):
                    item, used_chars = self._build_file_item(root_path, max_file_preview_chars, max_total_chars - total_preview_chars)
                    if item is not None:
                        collected.append(item)
                        total_preview_chars += used_chars
                        visited += 1
                if visited >= max_files or total_preview_chars >= max_total_chars:
                    break
                continue

            for current_root, dirs, files in os.walk(root_path):
                current_path = Path(current_root)
                rel_root = current_path.relative_to(self.workspace_root).as_posix()
                depth = 0 if rel_root == "." else len(Path(rel_root).parts)
                if depth >= max_depth:
                    dirs[:] = []

                dirs[:] = [d for d in sorted(dirs) if self._should_descend(current_path / d)]

                for filename in sorted(files):
                    file_path = current_path / filename
                    if visited >= max_files or total_preview_chars >= max_total_chars:
                        break
                    rel = file_path.relative_to(self.workspace_root).as_posix()
                    if not self._should_include(rel):
                        continue
                    item, used_chars = self._build_file_item(
                        file_path,
                        max_file_preview_chars,
                        max_total_chars - total_preview_chars,
                    )
                    if item is None:
                        continue
                    collected.append(item)
                    total_preview_chars += used_chars
                    visited += 1

                if visited >= max_files or total_preview_chars >= max_total_chars:
                    break

            if visited >= max_files or total_preview_chars >= max_total_chars:
                break

        stats = {
            "files_collected": len(collected),
            "preview_chars_used": total_preview_chars,
        }
        return collected, stats

    def _should_descend(self, path: Path) -> bool:
        rel = path.relative_to(self.workspace_root).as_posix()
        normalized = self.patch_policy._normalize_rel(rel)
        if not normalized.get("ok"):
            return False
        return self.patch_policy._is_protected(normalized["relative"]) is None

    def _should_include(self, relative_path: str) -> bool:
        normalized = self.patch_policy._normalize_rel(relative_path)
        if not normalized.get("ok"):
            return False
        if self.patch_policy._is_protected(normalized["relative"]):
            return False
        return True

    def _build_file_item(
        self,
        file_path: Path,
        max_file_preview_chars: int,
        remaining_total_chars: int,
    ) -> tuple[Optional[Dict[str, Any]], int]:
        try:
            stat = file_path.stat()
        except OSError:
            return None, 0

        relative_path = file_path.relative_to(self.workspace_root).as_posix()
        preview_budget = min(max_file_preview_chars, max(0, remaining_total_chars))
        if preview_budget <= 0:
            return None, 0

        try:
            raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None, 0

        preview = raw_text[:preview_budget]
        truncated = len(raw_text) > len(preview)
        used_chars = len(preview)

        return (
            {
                "path": relative_path,
                "size_bytes": stat.st_size,
                "preview": preview,
                "preview_truncated": truncated,
                "preview_char_count": used_chars,
                "line_count": len(raw_text.splitlines()),
            },
            used_chars,
        )

    def _collect_recent_history(self, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.history_db_path.exists():
            return []

        try:
            conn = sqlite3.connect(str(self.history_db_path))
        except sqlite3.Error:
            return []

        try:
            c = conn.cursor()
            c.execute(
                """
                SELECT r.task_id, r.timestamp, r.exit_code, r.stdout, r.stderr, r.meta, r.result_envelope, t.payload
                FROM results r
                LEFT JOIN tasks t ON t.id = r.task_id
                ORDER BY r.timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = c.fetchall()
        except sqlite3.Error:
            return []
        finally:
            conn.close()

        recent: List[Dict[str, Any]] = []
        for row in rows:
            task_payload = _safe_json_loads(row[7])
            result_envelope = _safe_json_loads(row[6])
            meta = _safe_json_loads(row[5])
            recent.append(
                {
                    "task_id": row[0],
                    "timestamp": _utc_iso_from_timestamp(row[1]),
                    "exit_code": row[2],
                    "status": result_envelope.get("status", ""),
                    "task_type": task_payload.get("task_type") or meta.get("task_type") or "",
                    "command_count": len(task_payload.get("commands", [])) if isinstance(task_payload.get("commands"), list) else 0,
                    "patch_count": len(task_payload.get("patches", [])) if isinstance(task_payload.get("patches"), list) else 0,
                    "policy_blocked": result_envelope.get("policy_blocked", False),
                    "patch_blocked": result_envelope.get("patch_blocked", False),
                    "blocked_reason": result_envelope.get("blocked_reason", ""),
                    "stderr": (row[4] or "")[:240],
                }
            )

        return recent
