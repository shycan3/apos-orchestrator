"""Build a safe, compact context pack for web LLM prompts."""
from __future__ import annotations

import fnmatch
import json
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .patch_policy import PatchPolicy


DEFAULT_CONTEXT_ROOTS = (
    "workspace",
    "src",
    "app",
    "cli",
    "apos_core",
    "server",
    "extension",
    "tests",
    "docs",
    "examples",
    "project_updates",
    "README.md",
    "pyproject.toml",
    "package.json",
    "requirements.txt",
    "uv.lock",
    "pnpm-lock.yaml",
    "yarn.lock",
)

EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    "htmlcov",
    ".tox",
    ".idea",
    ".vscode",
}

EXCLUDED_FILE_GLOBS = {
    "*.sqlite3",
    "*.db",
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.tmp",
    "*.swp",
    "*.swo",
    "*.cache",
}

SENSITIVE_FILE_GLOBS = {
    ".env",
    ".env.*",
    "*.secret",
    "*.secrets",
    "secrets.*",
    "private_key.*",
}

SECRET_VALUE_PATTERNS = [
    re.compile(r"(?i)\b(secret|token|password|passphrase|api[_-]?key|client[_-]?secret|private[_-]?key)\b\s*[:=]\s*([^\n\r]+)"),
    re.compile(r"(?i)\b(bearer\s+[A-Za-z0-9._~+/=-]{8,})\b"),
    re.compile(r"(?i)\b(sk-[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9-]{8,}|AIza[0-9A-Za-z\-_]{8,})\b"),
]

PRIVATE_KEY_BLOCK_PATTERN = re.compile(
    r"-----BEGIN [^-]+PRIVATE KEY-----.*?-----END [^-]+PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)


def _utc_iso_from_timestamp(value: Optional[float]) -> str:
    if value is None:
        return ""
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _mask_sensitive_text(text: str) -> str:
    masked = str(text or "")
    masked = PRIVATE_KEY_BLOCK_PATTERN.sub("<redacted private key block>", masked)
    for pattern in SECRET_VALUE_PATTERNS:
        masked = pattern.sub("<redacted>", masked)
    return masked


def _detect_file_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix == ".py":
        return "python"
    if suffix in {".js", ".mjs", ".cjs"}:
        return "javascript"
    if suffix in {".ts", ".tsx"}:
        return "typescript"
    if suffix == ".json":
        return "json"
    if suffix in {".yml", ".yaml"}:
        return "yaml"
    if suffix in {".toml"}:
        return "toml"
    if suffix in {".txt", ".log"}:
        return "text"
    return "text"


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
        max_recent_history: int = 5,
        max_pending_approvals: int = 5,
        max_worklog_entries: int = 3,
    ) -> Dict[str, Any]:
        file_summaries = self._collect_file_summaries(
            max_depth=max_depth,
            max_files=max_files,
            max_file_preview_chars=max_file_preview_chars,
            max_total_chars=max_total_chars,
        )
        relevant_files = [item["path"] for item in file_summaries]
        recent_history = self._collect_recent_history(limit=max_recent_history)
        approval_summary = self._collect_approval_queue_summary(limit=max_pending_approvals)
        worklog_summary = self._collect_recent_worklog_summary(max_entries=max_worklog_entries)
        available_flows = self._available_flows()

        pack = {
            "schema_version": "1.0",
            "project_name": self.workspace_root.name,
            "project_root": str(self.workspace_root),
            "project_root_visible": True,
            "generated_at": _utc_iso_now(),
            "allowed_roots": self._allowed_roots(),
            "protected_roots": self._protected_roots(),
            "recent_worklog_summary": worklog_summary,
            "available_flows": available_flows,
            "approval_queue_summary": approval_summary,
            "recent_history_summary": recent_history,
            "relevant_files": relevant_files,
            "file_summaries": file_summaries,
            "known_warnings": self._known_warnings(file_summaries, recent_history, approval_summary),
            "next_recommended_actions": self._next_recommended_actions(recent_history, approval_summary),
            "stats": {
                "relevant_file_count": len(relevant_files),
                "preview_char_count": sum(item.get("preview_char_count", 0) for item in file_summaries),
                "recent_history_count": len(recent_history.get("items", [])),
                "pending_approval_count": approval_summary.get("pending_count", 0),
            },
            "current_files": file_summaries,
            "recent_history": recent_history.get("items", []),
        }
        return pack

    def render_markdown(self, pack: Dict[str, Any]) -> str:
        allowed_roots = pack.get("allowed_roots", [])
        protected_roots = pack.get("protected_roots", [])
        recent_worklog = pack.get("recent_worklog_summary", {})
        recent_history = pack.get("recent_history_summary", {})
        approval_summary = pack.get("approval_queue_summary", {})
        file_summaries = pack.get("file_summaries", [])

        lines: List[str] = []
        lines.append("# APOS Context Pack")
        lines.append("")
        lines.append("## Project Snapshot")
        lines.append(f"- Project: {pack.get('project_name', '')}")
        lines.append(f"- Project root visible: {'yes' if pack.get('project_root_visible') else 'no'}")
        lines.append(f"- Project root: {pack.get('project_root', '')}")
        lines.append(f"- Generated at: {pack.get('generated_at', '')}")
        lines.append(f"- Allowed roots: {', '.join(allowed_roots) if allowed_roots else '-'}")
        lines.append(f"- Protected roots: {', '.join(protected_roots) if protected_roots else '-'}")
        lines.append(f"- Relevant files: {len(file_summaries)}")
        lines.append("")

        lines.append("## Current Safe Working Scope")
        if allowed_roots:
            for root in allowed_roots:
                lines.append(f"- {root}")
        else:
            lines.append("- No allowed roots discovered")
        lines.append("")
        lines.append("## Recent Changes")
        worklog_entries = recent_worklog.get("entries", []) if isinstance(recent_worklog, dict) else []
        if recent_worklog.get("summary"):
            lines.append(f"- {recent_worklog.get('summary')}")
        for entry in worklog_entries:
            title = entry.get("title", "")
            bullets = entry.get("bullets", [])
            lines.append(f"- {title}")
            for bullet in bullets:
                lines.append(f"  - {bullet}")
        history_items = recent_history.get("items", []) if isinstance(recent_history, dict) else []
        if history_items:
            lines.append("- Recent execution history:")
            for item in history_items:
                lines.append(
                    f"  - {item.get('task_id', '')} | {item.get('task_type', '')} | status={item.get('status', '')} | exit={item.get('exit_code', '')}"
                )
        lines.append("")

        lines.append("## Approval Queue Summary")
        lines.append(f"- Pending approvals: {approval_summary.get('pending_count', 0)}")
        lines.append(f"- Total approval items: {approval_summary.get('total_count', 0)}")
        if approval_summary.get("pending_items"):
            for item in approval_summary["pending_items"]:
                lines.append(
                    f"- {item.get('item_id', '')} | {item.get('item_type', '')} | {item.get('title', '')} | {item.get('status', '')}"
                )
        else:
            lines.append("- No pending approval items")
        lines.append("")

        lines.append("## Relevant Files")
        if file_summaries:
            for item in file_summaries:
                lines.append(
                    f"- {item.get('path', '')} | {item.get('kind', '')} | {item.get('content_mode', '')} | {item.get('summary', '')}"
                )
        else:
            lines.append("- No relevant files discovered")
        lines.append("")

        lines.append("## Known Warnings")
        for warning in pack.get("known_warnings", []):
            lines.append(f"- {warning}")
        lines.append("")

        lines.append("## Recommended Next Prompt")
        for action in pack.get("next_recommended_actions", []):
            lines.append(f"- {action}")

        return "\n".join(lines).rstrip() + "\n"

    def write_output(
        self,
        pack: Dict[str, Any],
        *,
        output_format: str = "json",
        output_path: str | Path | None = None,
    ) -> str:
        normalized_format = (output_format or "json").strip().lower()
        if normalized_format not in {"json", "markdown"}:
            raise ValueError(f"Unsupported context pack format: {output_format}")

        if normalized_format == "json":
            rendered = json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True)
        else:
            rendered = self.render_markdown(pack)

        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8", newline="\n")
        return rendered

    def _allowed_roots(self) -> List[str]:
        roots = list(DEFAULT_CONTEXT_ROOTS)
        return roots

    def _protected_roots(self) -> List[str]:
        protected = set(self.patch_policy.protected_prefixes)
        protected.update(self.patch_policy.protected_exact)
        protected.update(self.patch_policy.protected_globs)
        protected.update(EXCLUDED_DIR_NAMES)
        protected.update(EXCLUDED_FILE_GLOBS)
        protected.update(SENSITIVE_FILE_GLOBS)
        return sorted(protected)

    def _context_roots_to_scan(self) -> List[Path]:
        roots: List[Path] = []
        for root_name in DEFAULT_CONTEXT_ROOTS:
            root_path = self.workspace_root / root_name
            if root_path.exists():
                roots.append(root_path)
        return roots

    def _should_descend(self, path: Path) -> bool:
        rel = path.relative_to(self.workspace_root).as_posix()
        normalized = self.patch_policy._normalize_rel(rel)
        if not normalized.get("ok"):
            return False
        if self.patch_policy._is_protected(normalized["relative"]):
            return False
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            return False
        return True

    def _should_include(self, relative_path: str) -> bool:
        normalized = self.patch_policy._normalize_rel(relative_path)
        if not normalized.get("ok"):
            return False
        rel = normalized["relative"]
        if self.patch_policy._is_protected(rel):
            return False
        path = Path(rel)
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            return False
        if any(fnmatch.fnmatch(path.name.lower(), pattern.lower()) or fnmatch.fnmatch(rel.lower(), pattern.lower()) for pattern in SENSITIVE_FILE_GLOBS):
            return False
        if rel == "README.md" or rel in {"pyproject.toml", "package.json", "requirements.txt", "uv.lock", "pnpm-lock.yaml", "yarn.lock"}:
            return True
        first = rel.split("/", 1)[0]
        return first in {
            "workspace",
            "src",
            "app",
            "cli",
            "apos_core",
            "server",
            "extension",
            "tests",
            "docs",
            "examples",
            "project_updates",
        }

    def _collect_file_summaries(
        self,
        *,
        max_depth: int,
        max_files: int,
        max_file_preview_chars: int,
        max_total_chars: int,
    ) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        total_preview_chars = 0

        for root_path in self._context_roots_to_scan():
            if root_path.is_file():
                rel = root_path.relative_to(self.workspace_root).as_posix()
                if self._should_include(rel):
                    summary, used_chars = self._build_file_summary(
                        root_path,
                        max_file_preview_chars,
                        max_total_chars - total_preview_chars,
                    )
                    if summary is not None:
                        collected.append(summary)
                        total_preview_chars += used_chars
                if len(collected) >= max_files or total_preview_chars >= max_total_chars:
                    break
                continue

            for current_root, dirs, files in os.walk(root_path):
                current_path = Path(current_root)
                rel_root = current_path.relative_to(self.workspace_root).as_posix()
                depth = 0 if rel_root == "." else len(Path(rel_root).parts)
                if depth >= max_depth:
                    dirs[:] = []

                dirs[:] = [directory for directory in sorted(dirs) if self._should_descend(current_path / directory)]

                for filename in sorted(files):
                    if len(collected) >= max_files or total_preview_chars >= max_total_chars:
                        break
                    file_path = current_path / filename
                    rel = file_path.relative_to(self.workspace_root).as_posix()
                    if not self._should_include(rel):
                        continue
                    summary, used_chars = self._build_file_summary(
                        file_path,
                        max_file_preview_chars,
                        max_total_chars - total_preview_chars,
                    )
                    if summary is None:
                        continue
                    collected.append(summary)
                    total_preview_chars += used_chars

                if len(collected) >= max_files or total_preview_chars >= max_total_chars:
                    break

            if len(collected) >= max_files or total_preview_chars >= max_total_chars:
                break

        return collected

    def _build_file_summary(
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

        line_count = len(raw_text.splitlines())
        kind = _detect_file_kind(file_path)
        is_large = stat.st_size > 40_000 or line_count > 500
        if is_large:
            summary = f"Large file omitted ({stat.st_size} bytes, {line_count} lines)."
            return (
                {
                    "path": relative_path,
                    "kind": kind,
                    "size_bytes": stat.st_size,
                    "line_count": line_count,
                    "content_mode": "metadata_only",
                    "summary": summary,
                    "preview_truncated": True,
                    "preview_char_count": 0,
                    "last_modified": _utc_iso_from_timestamp(stat.st_mtime),
                },
                0,
            )

        preview = raw_text[:preview_budget]
        masked_preview = _mask_sensitive_text(preview)
        summary = _normalize_text(masked_preview)
        truncated = len(raw_text) > len(preview)
        used_chars = len(masked_preview)

        return (
            {
                "path": relative_path,
                "kind": kind,
                "size_bytes": stat.st_size,
                "line_count": line_count,
                "content_mode": "preview",
                "summary": summary,
                "preview_truncated": truncated,
                "preview_char_count": used_chars,
                "last_modified": _utc_iso_from_timestamp(stat.st_mtime),
            },
            used_chars,
        )

    def _collect_recent_history(self, limit: int = 5) -> Dict[str, Any]:
        if not self.history_db_path.exists():
            return {"total_count": 0, "status_counts": {}, "items": [], "source": str(self.history_db_path)}

        try:
            conn = sqlite3.connect(str(self.history_db_path))
        except sqlite3.Error:
            return {"total_count": 0, "status_counts": {}, "items": [], "source": str(self.history_db_path)}

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT r.task_id, r.timestamp, r.exit_code, r.stdout, r.stderr, r.meta, r.result_envelope, t.payload
                FROM results r
                LEFT JOIN tasks t ON t.id = r.task_id
                ORDER BY r.timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        except sqlite3.Error:
            return {"total_count": 0, "status_counts": {}, "items": [], "source": str(self.history_db_path)}
        finally:
            conn.close()

        items: List[Dict[str, Any]] = []
        status_counts = Counter()
        for row in rows:
            task_payload = _safe_json_loads(row[7])
            result_envelope = _safe_json_loads(row[6])
            meta = _safe_json_loads(row[5])
            status = result_envelope.get("status", "") or "unknown"
            status_counts[status] += 1
            items.append(
                {
                    "task_id": row[0],
                    "timestamp": _utc_iso_from_timestamp(row[1]),
                    "exit_code": row[2],
                    "status": status,
                    "task_type": task_payload.get("task_type") or meta.get("task_type") or "",
                    "command_count": len(task_payload.get("commands", [])) if isinstance(task_payload.get("commands"), list) else 0,
                    "patch_count": len(task_payload.get("patches", [])) if isinstance(task_payload.get("patches"), list) else 0,
                    "policy_blocked": result_envelope.get("policy_blocked", False),
                    "patch_blocked": result_envelope.get("patch_blocked", False),
                    "blocked_reason": result_envelope.get("blocked_reason", ""),
                    "stderr": _normalize_text((row[4] or "")[:240]),
                }
            )

        return {
            "total_count": len(items),
            "status_counts": dict(status_counts),
            "items": items,
            "source": str(self.history_db_path),
        }

    def _collect_approval_queue_summary(self, limit: int = 5) -> Dict[str, Any]:
        if not self.history_db_path.exists():
            return {
                "total_count": 0,
                "pending_count": 0,
                "status_counts": {},
                "type_counts": {},
                "pending_items": [],
                "source": str(self.history_db_path),
            }

        try:
            conn = sqlite3.connect(str(self.history_db_path))
        except sqlite3.Error:
            return {
                "total_count": 0,
                "pending_count": 0,
                "status_counts": {},
                "type_counts": {},
                "pending_items": [],
                "source": str(self.history_db_path),
            }

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, task_id, patch_id, item_type, title, status, workspace_root, target, step_index, payload, meta, created_at, updated_at, decided_at, decided_by, decision_reason
                FROM approval_items
                ORDER BY created_at DESC
                """
            )
            rows = cursor.fetchall()
        except sqlite3.Error:
            return {
                "total_count": 0,
                "pending_count": 0,
                "status_counts": {},
                "type_counts": {},
                "pending_items": [],
                "source": str(self.history_db_path),
            }
        finally:
            conn.close()

        pending_items: List[Dict[str, Any]] = []
        status_counts = Counter()
        type_counts = Counter()
        for row in rows:
            status = row[5] or "unknown"
            item_type = row[3] or "unknown"
            status_counts[status] += 1
            type_counts[item_type] += 1
            if status == "pending" and len(pending_items) < limit:
                pending_items.append(
                    {
                        "item_id": row[0],
                        "task_id": row[1],
                        "patch_id": row[2],
                        "item_type": item_type,
                        "title": row[4],
                        "status": status,
                        "target": row[7],
                        "step_index": row[8],
                        "decided_by": row[14],
                        "decision_reason": row[15],
                    }
                )

        return {
            "total_count": len(rows),
            "pending_count": status_counts.get("pending", 0),
            "status_counts": dict(status_counts),
            "type_counts": dict(type_counts),
            "pending_items": pending_items,
            "source": str(self.history_db_path),
        }

    def _collect_recent_worklog_summary(self, max_entries: int = 3) -> Dict[str, Any]:
        worklog_path = self.workspace_root / "project_updates" / "WORKLOG.md"
        if not worklog_path.exists():
            return {
                "source": str(worklog_path),
                "summary": "No WORKLOG.md found.",
                "entries": [],
            }

        try:
            text = worklog_path.read_text(encoding="utf-8")
        except OSError:
            return {
                "source": str(worklog_path),
                "summary": "WORKLOG.md could not be read.",
                "entries": [],
            }

        summary_match = re.search(r"^최종 업데이트:\s*(.+)$", text, re.MULTILINE)
        latest_update = summary_match.group(1).strip() if summary_match else ""
        entries: List[Dict[str, Any]] = []
        current_title = ""
        current_bullets: List[str] = []

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("### "):
                if current_title:
                    entries.append({"title": current_title, "bullets": current_bullets[:3]})
                current_title = stripped[4:].strip()
                current_bullets = []
                continue
            if stripped.startswith("- ") and current_title:
                bullet = _normalize_text(stripped[2:])
                if bullet:
                    current_bullets.append(bullet)
        if current_title:
            entries.append({"title": current_title, "bullets": current_bullets[:3]})

        entries = entries[:max_entries]
        summary_bits = []
        if latest_update:
            summary_bits.append(f"Latest update {latest_update}")
        if entries:
            summary_bits.append(f"Recent entry: {entries[0]['title']}")
        if not summary_bits:
            summary_bits.append("WORKLOG.md is present.")

        return {
            "source": str(worklog_path),
            "summary": "; ".join(summary_bits),
            "latest_update": latest_update,
            "entries": entries,
        }

    def _available_flows(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "validate_only",
                "status": "stable",
                "entrypoint": "cli/run_task.py --validate-only --json",
                "purpose": "Validate task envelopes without writing files.",
            },
            {
                "name": "preview_patch",
                "status": "stable",
                "entrypoint": "cli/run_task.py --json",
                "purpose": "Preview patch effects before execution.",
            },
            {
                "name": "apos_patch_bridge",
                "status": "stable",
                "entrypoint": "server/apos_server.py + extension/contentScript.js",
                "purpose": "Accept apos-patch proposals from web LLM pages and require human commit_patch approval.",
            },
            {
                "name": "approval_queue",
                "status": "stable",
                "entrypoint": "cli/approvals.py list|show|approve|reject",
                "purpose": "Inspect and change pending approval item status.",
            },
            {
                "name": "context_pack",
                "status": "stable",
                "entrypoint": "cli/apos.py context build",
                "purpose": "Generate a safe project summary for web LLM prompts.",
            },
        ]

    def _known_warnings(
        self,
        file_summaries: Sequence[Dict[str, Any]],
        recent_history: Dict[str, Any],
        approval_summary: Dict[str, Any],
    ) -> List[str]:
        warnings = [
            "This pack is a safe map, not a full source dump.",
            "Protected paths and generated outputs are excluded.",
            "Secret-like values are masked heuristically and should still be treated cautiously.",
            "Large files are summarized with metadata only.",
        ]
        if not file_summaries:
            warnings.append("No relevant files were discovered under the allowed roots.")
        if recent_history.get("items") and any(item.get("status") not in {"success", "approved", "rejected"} for item in recent_history["items"]):
            warnings.append("Recent execution history contains non-success entries.")
        if approval_summary.get("pending_count", 0):
            warnings.append("Pending approval items exist and should be reviewed before automated continuation.")
        return warnings

    def _next_recommended_actions(
        self,
        recent_history: Dict[str, Any],
        approval_summary: Dict[str, Any],
    ) -> List[str]:
        actions = [
            "Use validate-only on the next task envelope before execution.",
            "Use preview_patch when you want a safe diff before writing files.",
            "Use apos-patch Bridge Flow for browser-authored patch proposals.",
        ]
        if approval_summary.get("pending_count", 0):
            actions.insert(0, "Inspect pending approval items with `python cli/approvals.py list --workspace <workspace> --status pending`.")
        if any(item.get("status") in {"failed", "validation_failed", "patch_blocked", "command_blocked"} for item in recent_history.get("items", [])):
            actions.append("Review the latest failed result envelope before retrying the same task.")
        return actions


def build_context_pack(
    workspace_root: str | Path,
    history_db_path: str | Path | None = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    return ContextPackBuilder(workspace_root, history_db_path=history_db_path).build(**kwargs)


def render_context_pack_markdown(pack: Dict[str, Any]) -> str:
    builder = ContextPackBuilder(pack.get("project_root") or ".")
    return builder.render_markdown(pack)
