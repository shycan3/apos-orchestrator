"""Generate failure and drift reports for APOS."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .context_pack import ContextPackBuilder, _normalize_text
from .recorder import Recorder


FAILURE_CAUSES = {
    "invalid_envelope",
    "policy_denied",
    "protected_path",
    "command_denied",
    "patch_conflict",
    "test_failed",
    "execution_failed",
    "missing_file",
    "stale_context_possible",
    "unknown",
}


@dataclass(frozen=True)
class FailureRecord:
    id: str
    task_id: str
    kind: str
    status: str
    timestamp: float
    target: str
    command: Any
    exit_code: Optional[int]
    stdout: str
    stderr: str
    cause: str
    source: str
    summary: str
    affected_files: List[str]
    recommended_human_action: str
    recommended_llm_prompt: str


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


def _utc_iso_from_timestamp(value: Optional[float]) -> str:
    if value is None:
        return ""
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()


def _normalize_for_report(text: Any, max_len: int = 240) -> str:
    value = _normalize_text(str(text or ""))
    if len(value) > max_len:
        return value[: max_len - 1] + "…"
    return value


class ReportBuilder:
    def __init__(self, workspace_root: str | Path, history_db_path: str | Path | None = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.context_builder = ContextPackBuilder(self.workspace_root, history_db_path=history_db_path)
        self.recorder = Recorder(db_path=history_db_path or self.workspace_root / ".apos" / "history.sqlite3")

    def close(self) -> None:
        try:
            self.recorder.close()
        except Exception:
            pass

    def build_failure_report(
        self,
        identifier: str | None = None,
        *,
        limit: int = 5,
        context_pack: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        pack = context_pack or self.context_builder.build(max_recent_history=limit, max_pending_approvals=limit)
        failures = self._collect_failures(identifier=identifier, limit=limit)
        drift = self.build_drift_report(context_pack=pack, limit=limit)
        recent_failures = [self._failure_to_dict(record) for record in failures]
        likely_causes = self._aggregate_likely_causes(failures, drift)
        affected_files = self._aggregate_affected_files(failures, drift)
        stale_signals = drift.get("stale_context_signals", [])
        summary = self._build_summary(failures, drift)
        recommended_human_action = self._build_human_action(failures, drift)
        recommended_llm_prompt = self._build_llm_prompt(failures, drift)
        return {
            "report_type": "failure_report",
            "workspace_root": str(self.workspace_root),
            "generated_at": _utc_now_iso(),
            "summary": summary,
            "recent_failures": recent_failures,
            "likely_causes": likely_causes,
            "affected_files": affected_files,
            "stale_context_signals": stale_signals,
            "recommended_human_action": recommended_human_action,
            "recommended_llm_prompt": recommended_llm_prompt,
            "drift": drift,
        }

    def build_drift_report(
        self,
        *,
        context_pack: Optional[Dict[str, Any]] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        pack = context_pack or self.context_builder.build(max_recent_history=limit, max_pending_approvals=limit)
        generated_at_raw = pack.get("generated_at")
        generated_at = self._parse_iso(generated_at_raw)
        file_summaries = pack.get("file_summaries", []) if isinstance(pack.get("file_summaries"), list) else []
        approval_summary = pack.get("approval_queue_summary", {}) if isinstance(pack.get("approval_queue_summary"), dict) else {}
        recent_history = pack.get("recent_history_summary", {}) if isinstance(pack.get("recent_history_summary"), dict) else {}
        recent_worklog = pack.get("recent_worklog_summary", {}) if isinstance(pack.get("recent_worklog_summary"), dict) else {}

        changed_files: List[Dict[str, Any]] = []
        missing_targets: List[str] = []
        for item in file_summaries:
            path = self.workspace_root / str(item.get("path") or "")
            last_modified = self._parse_iso(item.get("last_modified"))
            if generated_at and last_modified and last_modified > generated_at:
                changed_files.append(
                    {
                        "path": item.get("path"),
                        "last_modified": item.get("last_modified"),
                        "kind": item.get("kind", ""),
                    }
                )
            if not path.exists():
                missing_targets.append(str(item.get("path") or ""))

        pending_items = approval_summary.get("pending_items", []) if isinstance(approval_summary.get("pending_items"), list) else []
        old_pending_items: List[Dict[str, Any]] = []
        for item in pending_items:
            created_at = self._parse_ts(item.get("created_at"))
            if created_at and generated_at and created_at < generated_at:
                old_pending_items.append(
                    {
                        "item_id": item.get("item_id"),
                        "task_id": item.get("task_id"),
                        "target": item.get("target"),
                        "created_at": _utc_iso_from_timestamp(created_at),
                    }
                )

        recent_history_items = recent_history.get("items", []) if isinstance(recent_history.get("items"), list) else []
        failure_hotspots = self._failure_hotspots(recent_history_items)
        stale_context_signals: List[str] = []
        if changed_files:
            stale_context_signals.append(f"{len(changed_files)} file(s) changed after the Context Pack timestamp")
        if old_pending_items:
            stale_context_signals.append(f"{len(old_pending_items)} pending approval item(s) appear older than the Context Pack")
        if missing_targets:
            stale_context_signals.append(f"{len(missing_targets)} context-pack files are missing from the workspace now")
        if failure_hotspots:
            stale_context_signals.append("Recent failures are concentrated around one or two files")
        if recent_worklog.get("entries"):
            latest_worklog = recent_worklog.get("entries", [])[0]
            if isinstance(latest_worklog, dict) and latest_worklog.get("title") and changed_files:
                stale_context_signals.append("Recent worklog and current workspace state may be out of sync")

        drift_warning = bool(stale_context_signals)
        return {
            "report_type": "drift_report",
            "workspace_root": str(self.workspace_root),
            "generated_at": _utc_now_iso(),
            "context_pack_generated_at": generated_at_raw,
            "changed_files": changed_files,
            "missing_targets": missing_targets,
            "old_pending_items": old_pending_items,
            "failure_hotspots": failure_hotspots,
            "stale_context_signals": stale_context_signals,
            "drift_warning": drift_warning,
            "recommended_human_action": self._drift_human_action(stale_context_signals),
            "recommended_llm_prompt": self._drift_llm_prompt(stale_context_signals),
        }

    def build_next_prompt(self, identifier: str | None = None, *, limit: int = 5) -> str:
        report = self.build_failure_report(identifier, limit=limit)
        return report["recommended_llm_prompt"]

    def render_markdown(self, report: Dict[str, Any]) -> str:
        lines: List[str] = []
        lines.append("# APOS Failure / Drift Report")
        lines.append("")
        lines.append("## Summary")
        lines.append(f"- {report.get('summary', '')}")
        lines.append("")

        lines.append("## Recent Failures")
        recent_failures = report.get("recent_failures", []) if isinstance(report.get("recent_failures"), list) else []
        if recent_failures:
            for item in recent_failures:
                lines.append(
                    f"- {item.get('id', '')} | {item.get('kind', '')} | status={item.get('status', '')} | cause={item.get('cause', '')} | target={item.get('target', '')} | exit={item.get('exit_code', '')}"
                )
                if item.get("stderr"):
                    lines.append(f"  - stderr: {item.get('stderr', '')}")
                if item.get("stdout"):
                    lines.append(f"  - stdout: {item.get('stdout', '')}")
        else:
            lines.append("- No recent failures found")
        lines.append("")

        lines.append("## Likely Causes")
        for cause in report.get("likely_causes", []):
            lines.append(f"- {cause}")
        if not report.get("likely_causes"):
            lines.append("- unknown")
        lines.append("")

        lines.append("## Affected Files")
        affected = report.get("affected_files", []) if isinstance(report.get("affected_files"), list) else []
        if affected:
            for path in affected:
                lines.append(f"- {path}")
        else:
            lines.append("- No specific file could be confirmed")
        lines.append("")

        lines.append("## Stale Context Signals")
        signals = report.get("stale_context_signals", []) if isinstance(report.get("stale_context_signals"), list) else []
        if signals:
            for signal in signals:
                lines.append(f"- {signal}")
        else:
            lines.append("- No drift signal detected")
        lines.append("")

        lines.append("## Recommended Human Action")
        lines.append(f"- {report.get('recommended_human_action', '')}")
        lines.append("")

        lines.append("## Recommended LLM Prompt")
        lines.append(report.get("recommended_llm_prompt", ""))
        lines.append("")

        drift = report.get("drift")
        if isinstance(drift, dict):
            lines.append("## Drift Details")
            lines.append(f"- Drift warning: {'yes' if drift.get('drift_warning') else 'no'}")
            if drift.get("changed_files"):
                lines.append("- Changed files since pack:")
                for item in drift.get("changed_files", []):
                    lines.append(f"  - {item.get('path', '')} ({item.get('last_modified', '')})")
            if drift.get("old_pending_items"):
                lines.append("- Old pending items:")
                for item in drift.get("old_pending_items", []):
                    lines.append(f"  - {item.get('item_id', '')} | {item.get('target', '')}")
        return "\n".join(lines).rstrip() + "\n"

    def _collect_failures(self, identifier: str | None = None, limit: int = 5) -> List[FailureRecord]:
        task_ids: List[str] = []
        if identifier:
            task_ids.append(identifier)

        records: List[FailureRecord] = []
        recent_results = self._fetch_recent_results(limit=max(limit * 3, 10))
        recent_items = self.recorder.list_approval_items(limit=max(limit * 3, 10))
        if identifier:
            recent_items = [item for item in recent_items if item.get("id") == identifier or item.get("task_id") == identifier or item.get("patch_id") == identifier]

        for row in recent_results:
            if identifier and row.get("task_id") != identifier and row.get("id") != identifier:
                task_payload = self.recorder.get_task(identifier)
                if not task_payload or task_payload.get("task_id") != row.get("task_id"):
                    continue
            record = self._failure_from_result(row)
            if record:
                records.append(record)

        for item in recent_items:
            record = self._failure_from_approval(item)
            if record:
                records.append(record)

        seen: set[str] = set()
        deduped: List[FailureRecord] = []
        for record in sorted(records, key=lambda item: item.timestamp, reverse=True):
            key = record.id
            if key in seen:
                continue
            seen.add(key)
            deduped.append(record)
            if len(deduped) >= limit:
                break
        return deduped

    def _failure_to_dict(self, record: FailureRecord) -> Dict[str, Any]:
        return {
            "id": record.id,
            "task_id": record.task_id,
            "kind": record.kind,
            "status": record.status,
            "timestamp": record.timestamp,
            "timestamp_iso": _utc_iso_from_timestamp(record.timestamp),
            "target": record.target,
            "command": record.command,
            "exit_code": record.exit_code,
            "stdout": record.stdout,
            "stderr": record.stderr,
            "cause": record.cause,
            "source": record.source,
            "summary": record.summary,
            "affected_files": record.affected_files,
            "recommended_human_action": record.recommended_human_action,
            "recommended_llm_prompt": record.recommended_llm_prompt,
        }

    def _fetch_recent_results(self, limit: int = 10) -> List[Dict[str, Any]]:
        if not self.recorder.db_path.exists():
            return []
        try:
            conn = sqlite3.connect(str(self.recorder.db_path))
        except sqlite3.Error:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, task_id, timestamp, exit_code, stdout, stderr, meta, snapshot_id, snapshot_commit, policy_blocked, blocked_reason, patch_blocked, patch_blocked_reason, patch_preview, result_envelope FROM results ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
        except sqlite3.Error:
            return []
        finally:
            conn.close()

        results = []
        for row in rows:
            results.append(
                {
                    "id": row[0],
                    "task_id": row[1],
                    "timestamp": row[2],
                    "exit_code": row[3],
                    "stdout": row[4],
                    "stderr": row[5],
                    "meta": _safe_json_loads(row[6]),
                    "snapshot_id": row[7],
                    "snapshot_commit": row[8],
                    "policy_blocked": row[9],
                    "blocked_reason": row[10],
                    "patch_blocked": row[11],
                    "patch_blocked_reason": row[12],
                    "patch_preview": _safe_json_loads(row[13]),
                    "result_envelope": _safe_json_loads(row[14]),
                }
            )
        return results

    def _failure_from_result(self, row: Dict[str, Any]) -> Optional[FailureRecord]:
        envelope = _safe_json_loads(row.get("result_envelope"))
        status = envelope.get("status") or row.get("meta", {}).get("status") or ""
        exit_code = row.get("exit_code")
        if status not in {"failed", "patch_blocked", "command_blocked", "validation_failed", "internal_error", "skipped", "not_found", "invalid_step", "invalid_task_type"} and not (exit_code not in (0, None)):
            return None

        task_id = str(row.get("task_id") or "")
        task_payload = self.recorder.get_task(task_id) or {}
        meta = row.get("meta") or {}
        result_meta = envelope.get("meta") or {}
        kind = self._infer_kind(task_payload, result_meta, row.get("patch_preview") or {})
        command = self._extract_command(task_payload, result_meta, row)
        target = self._extract_target(task_payload, result_meta, row)
        stdout = _normalize_for_report(row.get("stdout", ""))
        stderr = _normalize_for_report(row.get("stderr", ""))
        cause = self.classify_failure(
            status=status,
            exit_code=exit_code,
            task_payload=task_payload,
            result_envelope=envelope,
            row=row,
        )
        affected_files = self._extract_affected_files(task_payload, result_meta, row)
        timestamp = float(row.get("timestamp") or 0)
        return FailureRecord(
            id=str(row.get("id") or task_id),
            task_id=task_id,
            kind=kind,
            status=str(status or "failed"),
            timestamp=timestamp,
            target=target,
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            cause=cause,
            source="result",
            summary=self._failure_summary(task_id, kind, status, exit_code, target),
            affected_files=affected_files,
            recommended_human_action=self._human_action_for_cause(cause, affected_files, target),
            recommended_llm_prompt=self._llm_prompt_for_cause(cause, task_payload, target, kind),
        )

    def _failure_from_approval(self, item: Dict[str, Any]) -> Optional[FailureRecord]:
        status = str(item.get("status") or "")
        if status not in {"failed", "rejected"}:
            return None
        task_payload = self.recorder.get_task(str(item.get("task_id") or "")) or {}
        target = str(item.get("target") or "")
        if not target and isinstance(item.get("payload"), dict):
            target = str(item.get("payload", {}).get("target") or "")
        cause = self.classify_failure(
            status=status,
            exit_code=None,
            task_payload=task_payload,
            result_envelope={},
            row={
                "blocked_reason": item.get("decision_reason") or item.get("title") or "",
                "patch_blocked_reason": item.get("decision_reason") or "",
                "meta": item.get("meta") or {},
            },
        )
        kind = self._infer_kind(task_payload, item.get("meta") or {}, item.get("payload") or {})
        affected_files = self._extract_affected_files(task_payload, item.get("meta") or {}, {"patch_preview": item.get("payload") or {}})
        timestamp = float(item.get("updated_at") or item.get("created_at") or 0)
        return FailureRecord(
            id=str(item.get("id") or item.get("task_id") or "approval"),
            task_id=str(item.get("task_id") or ""),
            kind=kind if kind != "unknown" else "approval",
            status=status,
            timestamp=timestamp,
            target=target,
            command=None,
            exit_code=None,
            stdout="",
            stderr=_normalize_for_report(item.get("decision_reason") or item.get("title") or ""),
            cause=cause,
            source="approval_items",
            summary=self._failure_summary(str(item.get("task_id") or item.get("id") or ""), kind, status, None, target),
            affected_files=affected_files,
            recommended_human_action=self._human_action_for_cause(cause, affected_files, target),
            recommended_llm_prompt=self._llm_prompt_for_cause(cause, task_payload, target, kind),
        )

    def classify_failure(
        self,
        *,
        status: str,
        exit_code: Optional[int],
        task_payload: Dict[str, Any],
        result_envelope: Dict[str, Any],
        row: Dict[str, Any],
    ) -> str:
        blocked_reason = " ".join(
            str(value or "") for value in [row.get("blocked_reason"), row.get("patch_blocked_reason"), result_envelope.get("blocked_reason"), result_envelope.get("patch_blocked_reason")]
        ).lower()
        stderr = str(row.get("stderr") or "").lower()
        stdout = str(row.get("stdout") or "").lower()
        combined = f"{blocked_reason} {stderr} {stdout}"
        if status == "validation_failed" or "task_envelope_validation_failed" in combined:
            return "invalid_envelope"
        if any(token in combined for token in ["policy_blocked", "command policy", "command_blocked", "blocked by policy"]):
            return "command_denied" if "command" in combined else "policy_denied"
        if any(token in combined for token in ["protected", "scratchpad", "protected write"]):
            return "protected_path"
        if any(token in combined for token in ["search matched multiple times", "conflict", "patch conflict"]):
            return "patch_conflict"
        if any(token in combined for token in ["does not exist", "missing file", "file not found", "target file does not exist"]):
            return "missing_file"
        if exit_code not in (None, 0):
            commands = task_payload.get("commands", []) if isinstance(task_payload.get("commands"), list) else []
            command_text = " ".join(str(cmd.get("command") if isinstance(cmd, dict) else cmd) for cmd in commands).lower()
            if "pytest" in command_text or "test" in command_text or "pytest" in combined:
                return "test_failed"
            return "execution_failed"
        if status in {"rejected"}:
            return "policy_denied" if "policy" in combined else "unknown"
        if self._looks_stale(task_payload, row, combined):
            return "stale_context_possible"
        return "unknown"

    def render_failure_markdown(self, identifier: str | None = None, *, limit: int = 5) -> str:
        report = self.build_failure_report(identifier, limit=limit)
        return self.render_markdown(report)

    def render_drift_markdown(self, *, limit: int = 5) -> str:
        report = self.build_drift_report(limit=limit)
        lines: List[str] = []
        lines.append("# APOS Drift Report")
        lines.append("")
        lines.append("## Summary")
        lines.append(f"- {'Drift warning detected.' if report.get('drift_warning') else 'No drift warning detected.'}")
        lines.append("")
        lines.append("## Recent Failures")
        if report.get("failure_hotspots"):
            for item in report.get("failure_hotspots", []):
                lines.append(f"- {item.get('path', '')} | failures={item.get('count', 0)} | causes={', '.join(item.get('causes', []))}")
        else:
            lines.append("- No concentrated failures detected")
        lines.append("")
        lines.append("## Likely Causes")
        for signal in report.get("stale_context_signals", []):
            lines.append(f"- {signal}")
        if not report.get("stale_context_signals"):
            lines.append("- No stale context signals detected")
        lines.append("")
        lines.append("## Affected Files")
        for item in report.get("changed_files", []):
            lines.append(f"- {item.get('path', '')}")
        if not report.get("changed_files"):
            lines.append("- No changed files since the Context Pack timestamp")
        lines.append("")
        lines.append("## Stale Context Signals")
        for signal in report.get("stale_context_signals", []):
            lines.append(f"- {signal}")
        lines.append("")
        lines.append("## Recommended Human Action")
        lines.append(f"- {report.get('recommended_human_action', '')}")
        lines.append("")
        lines.append("## Recommended LLM Prompt")
        lines.append(report.get("recommended_llm_prompt", ""))
        return "\n".join(lines).rstrip() + "\n"

    def build_failure_detail(self, identifier: str, *, limit: int = 5) -> Dict[str, Any]:
        report = self.build_failure_report(identifier, limit=limit)
        if report.get("recent_failures"):
            report["primary_failure"] = report["recent_failures"][0]
        return report

    def _aggregate_likely_causes(self, failures: List[FailureRecord], drift: Dict[str, Any]) -> List[str]:
        counts = Counter(record.cause for record in failures if record.cause)
        causes = [f"{cause} ({count})" for cause, count in counts.most_common() if cause]
        if drift.get("drift_warning"):
            causes.append("stale_context_possible")
        return causes or ["unknown"]

    def _aggregate_affected_files(self, failures: List[FailureRecord], drift: Dict[str, Any]) -> List[str]:
        paths: List[str] = []
        for record in failures:
            paths.extend(record.affected_files)
            if record.target:
                paths.append(record.target)
        for item in drift.get("changed_files", []):
            path = str(item.get("path") or "")
            if path:
                paths.append(path)
        for item in drift.get("missing_targets", []):
            if item:
                paths.append(str(item))
        seen: set[str] = set()
        deduped: List[str] = []
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            deduped.append(path)
        return deduped[:10]

    def _build_summary(self, failures: List[FailureRecord], drift: Dict[str, Any]) -> str:
        if not failures:
            if drift.get("drift_warning"):
                return "No direct failure selected, but drift signals suggest the context may be stale."
            return "No recent failure records were found."
        top = failures[0]
        return f"{top.kind} / {top.cause} on {top.task_id or top.id}; review the latest result and refresh context if needed."

    def _build_human_action(self, failures: List[FailureRecord], drift: Dict[str, Any]) -> str:
        if failures:
            top = failures[0]
            return top.recommended_human_action
        if drift.get("drift_warning"):
            return "Refresh the Context Pack, inspect changed files, and re-run the prompt builder before asking the LLM again."
        return "Inspect the latest history records and rerun the failing task with a smaller scope."

    def _build_llm_prompt(self, failures: List[FailureRecord], drift: Dict[str, Any]) -> str:
        if failures:
            top = failures[0]
            if top.cause in {"invalid_envelope", "protected_path", "command_denied", "policy_denied"}:
                return "Please switch to review mode and summarize the failure cause, then propose a safer patch or plan only if the Context Pack still supports it."
            if top.cause in {"patch_conflict", "missing_file", "stale_context_possible"}:
                return "Please refresh the Context Pack and then produce a new patch or plan that only uses currently existing files and approved paths."
            if top.cause in {"test_failed", "execution_failed"}:
                return "Please analyze the failing result envelope, identify the smallest fix, and return a patch or plan with one safe step."
        if drift.get("drift_warning"):
            return "Please review the drift signals, refresh the Context Pack, and only then propose the next patch or plan if the state still matches the request."
        return "Please review the current APOS history and return the safest next patch, plan, or review-only response."

    def _human_action_for_cause(self, cause: str, affected_files: List[str], target: str) -> str:
        if cause == "invalid_envelope":
            return "Inspect the task envelope and fix the malformed task fields before retrying."
        if cause == "policy_denied":
            return "Review the denied request against APOS policy, then narrow the task or request approval again."
        if cause == "command_denied":
            return "Replace the blocked command with an allowed alternative and rerun the task."
        if cause == "protected_path":
            return "Move the change into an allowed workspace path before retrying."
        if cause == "patch_conflict":
            return "Refresh the target file and rebase the patch against the current contents."
        if cause == "missing_file":
            return "Confirm the target file exists now, then regenerate the patch or update the path."
        if cause == "stale_context_possible":
            return "Refresh the Context Pack and rerun the task from the current workspace state."
        if cause in {"test_failed", "execution_failed"}:
            return "Inspect the failing result envelope, fix the smallest issue, and rerun validation."
        if affected_files:
            return f"Review the affected files ({', '.join(affected_files[:3])}) and rerun the task."
        if target:
            return f"Review the target {target} and rerun the task."
        return "Inspect the latest failure, refresh context, and retry with a smaller scope."

    def _llm_prompt_for_cause(self, cause: str, task_payload: Dict[str, Any], target: str, kind: str) -> str:
        if cause == "invalid_envelope":
            return "Please inspect the task envelope, point out the invalid fields, and suggest the smallest safe correction."
        if cause == "policy_denied":
            return "Please review the policy denial and propose a narrower task or a safer alternative within the current rules."
        if cause == "command_denied":
            return "Please replace the blocked command with an allowed approach and keep the next step within APOS policy."
        if cause in {"patch_conflict", "missing_file", "stale_context_possible"}:
            return "Please refresh the Context Pack and then propose a new patch or plan that only uses currently valid files and paths."
        if cause in {"test_failed", "execution_failed"}:
            return "Please inspect the failing result envelope, identify the smallest fix, and return one safe follow-up step."
        if target:
            return f"Please review the failure around {target} and produce the safest next {kind} step."
        if task_payload.get("commands"):
            return f"Please review the failed command task and propose the safest next {kind} step."
        if task_payload.get("patches"):
            return f"Please review the failed patch task and propose the safest next {kind} step."
        return "Please review the failure and propose the safest next APOS step only if the current context still supports it."

    def _drift_human_action(self, signals: List[str]) -> str:
        if signals:
            return "Refresh the Context Pack, inspect the changed files, and ask the LLM to work from the updated state."
        return "No special action needed beyond the usual validation and approval flow."

    def _drift_llm_prompt(self, signals: List[str]) -> str:
        if signals:
            return "The workspace appears to have drifted. Please re-read the latest Context Pack and then produce a patch, plan, or review response that only uses the current state."
        return "No drift warning detected. You may continue with the current APOS flow if the task still matches the Context Pack."

    def _failure_summary(self, task_id: str, kind: str, status: str, exit_code: Optional[int], target: str) -> str:
        exit_label = f"exit_code={exit_code}" if exit_code is not None else f"status={status}"
        if target:
            return f"{kind} failure for {task_id} at {target} ({exit_label})"
        return f"{kind} failure for {task_id} ({exit_label})"

    def _infer_kind(self, task_payload: Dict[str, Any], result_meta: Dict[str, Any], preview: Dict[str, Any]) -> str:
        if task_payload.get("task_type") == "plan_only" or result_meta.get("plan_step_index") is not None:
            return "plan step"
        if result_meta.get("task_type") == "bridge_patch" or preview.get("item_type") == "bridge_patch":
            return "bridge"
        if task_payload.get("commands"):
            return "command"
        if task_payload.get("patches"):
            return "patch"
        if preview.get("item_type") == "approval" or preview.get("item_type") == "bridge_patch":
            return "approval"
        return "unknown"

    def _extract_target(self, task_payload: Dict[str, Any], result_meta: Dict[str, Any], row: Dict[str, Any]) -> str:
        if row.get("patch_preview") and isinstance(row.get("patch_preview"), dict):
            preview = row.get("patch_preview") or {}
            if preview.get("target"):
                return str(preview.get("target"))
            if preview.get("path"):
                return str(preview.get("path"))
        patches = task_payload.get("patches") if isinstance(task_payload.get("patches"), list) else []
        if patches:
            first = patches[0]
            if isinstance(first, dict) and first.get("target"):
                return str(first.get("target"))
        plan_step_index = result_meta.get("plan_step_index")
        if plan_step_index is not None:
            steps = task_payload.get("meta", {}).get("plan_steps", []) if isinstance(task_payload.get("meta"), dict) else []
            if isinstance(steps, list) and 0 <= int(plan_step_index) < len(steps):
                step = steps[int(plan_step_index)]
                if isinstance(step, dict):
                    step_patches = step.get("patches") if isinstance(step.get("patches"), list) else []
                    if step_patches and isinstance(step_patches[0], dict) and step_patches[0].get("target"):
                        return str(step_patches[0].get("target"))
        return ""

    def _extract_command(self, task_payload: Dict[str, Any], result_meta: Dict[str, Any], row: Dict[str, Any]) -> Any:
        command_results = result_meta.get("command_results") if isinstance(result_meta.get("command_results"), list) else []
        if command_results:
            return command_results[0].get("command")
        commands = task_payload.get("commands") if isinstance(task_payload.get("commands"), list) else []
        if commands:
            first = commands[0]
            if isinstance(first, dict):
                return first.get("command")
            return first
        return row.get("command")

    def _extract_affected_files(self, task_payload: Dict[str, Any], result_meta: Dict[str, Any], row: Dict[str, Any]) -> List[str]:
        paths: List[str] = []
        patches = task_payload.get("patches") if isinstance(task_payload.get("patches"), list) else []
        for patch in patches:
            if isinstance(patch, dict) and patch.get("target"):
                paths.append(str(patch.get("target")))
        plan_step_index = result_meta.get("plan_step_index")
        if plan_step_index is not None:
            steps = task_payload.get("meta", {}).get("plan_steps", []) if isinstance(task_payload.get("meta"), dict) else []
            if isinstance(steps, list) and 0 <= int(plan_step_index) < len(steps):
                step = steps[int(plan_step_index)]
                if isinstance(step, dict):
                    for patch in step.get("patches") if isinstance(step.get("patches"), list) else []:
                        if isinstance(patch, dict) and patch.get("target"):
                            paths.append(str(patch.get("target")))
        if row.get("patch_preview") and isinstance(row.get("patch_preview"), dict):
            preview = row.get("patch_preview") or {}
            if preview.get("target"):
                paths.append(str(preview.get("target")))
        if row.get("target"):
            paths.append(str(row.get("target")))
        seen: set[str] = set()
        deduped: List[str] = []
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            deduped.append(path)
        return deduped

    def _looks_stale(self, task_payload: Dict[str, Any], row: Dict[str, Any], combined: str) -> bool:
        if "stale" in combined or "context" in combined:
            return True
        target = self._extract_target(task_payload, row.get("meta") or {}, row)
        if target and not (self.workspace_root / target).exists():
            return True
        return False

    def _failure_hotspots(self, recent_history_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in recent_history_items:
            status = str(item.get("status") or "")
            if status not in {"failed", "validation_failed", "patch_blocked", "command_blocked"}:
                continue
            key = str(item.get("task_id") or "")
            grouped[key].append(item)
        hotspots = []
        for path, items in grouped.items():
            causes = sorted({self.classify_failure(status=item.get("status", ""), exit_code=item.get("exit_code"), task_payload=self.recorder.get_task(str(item.get("task_id") or "")) or {}, result_envelope=item.get("result_envelope") or {}, row=item) for item in items})
            hotspots.append({"path": path, "count": len(items), "causes": causes})
        hotspots.sort(key=lambda item: item["count"], reverse=True)
        return hotspots[:5]

    def _parse_iso(self, value: Any) -> Optional[float]:
        if not value:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            return datetime.fromisoformat(text).timestamp()
        except Exception:
            return None

    def _parse_ts(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return self._parse_iso(value)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
