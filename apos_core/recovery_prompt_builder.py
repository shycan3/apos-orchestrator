"""Build recovery prompts that can be pasted back into a web LLM."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .plan_flow import PlanStepRef
from .prompt_builder import PromptBuilder
from .report_builder import ReportBuilder


class RecoveryPromptBuilder:
    def __init__(self, workspace_root: str | Path, history_db_path: str | Path | None = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.history_db_path = Path(history_db_path) if history_db_path else self.workspace_root / ".apos" / "history.sqlite3"
        self.prompt_builder = PromptBuilder(self.workspace_root, history_db_path=self.history_db_path)
        self.report_builder = ReportBuilder(self.workspace_root, history_db_path=self.history_db_path)

    def close(self) -> None:
        try:
            self.report_builder.close()
        except Exception:
            pass

    def build(
        self,
        *,
        failure_id: str | None = None,
        latest: bool = False,
        drift: bool = False,
        plan_step: Optional[Tuple[str, int]] = None,
        mode: str | None = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        pack = self.report_builder.context_builder.build(max_recent_history=limit, max_pending_approvals=limit)
        source_kind, source_identifier, report = self._load_source_report(
            failure_id=failure_id,
            latest=latest,
            drift=drift,
            plan_step=plan_step,
            limit=limit,
            pack=pack,
        )
        legacy_recommended_mode = self._recommend_mode(report, source_kind, plan_step=plan_step)
        auto_recommended_mode = self._auto_recommend_mode(report, source_kind, plan_step=plan_step)
        requested_mode = str(mode or "").strip().lower()
        if requested_mode == "auto":
            effective_mode = auto_recommended_mode
            recommended_mode = auto_recommended_mode
        elif requested_mode:
            effective_mode = self.prompt_builder._normalize_mode(requested_mode)
            recommended_mode = legacy_recommended_mode
        else:
            effective_mode = self.prompt_builder._normalize_mode(legacy_recommended_mode)
            recommended_mode = legacy_recommended_mode
        recovery_goal = self._recovery_goal(report, source_kind, effective_mode, source_identifier)
        failure_summary = self._failure_summary(report, source_kind, source_identifier)
        likely_cause = self._likely_cause(report, source_kind)
        affected_files = self._affected_files(report)
        relevant_context = self._relevant_context(report, pack, source_kind)
        constraints = self._extra_constraints(source_kind, effective_mode)
        required_llm_output = self.prompt_builder.required_output_lines(effective_mode)
        safety_reminder = self._safety_reminder(source_kind, effective_mode)

        prompt_text = self.prompt_builder.render_recovery_markdown(
            pack,
            recovery_goal=recovery_goal,
            failure_summary=failure_summary,
            likely_cause=likely_cause,
            affected_files=affected_files,
            relevant_context=relevant_context,
            constraints=constraints,
            required_llm_output=required_llm_output,
            recommended_mode=effective_mode,
            safety_reminder=safety_reminder,
        )

        return {
            "report_type": "recovery_prompt",
            "workspace_root": str(self.workspace_root),
            "generated_at": pack.get("generated_at", ""),
            "source_kind": source_kind,
            "source_identifier": source_identifier,
            "requested_mode": requested_mode or None,
            "recommended_mode": recommended_mode,
            "mode": effective_mode,
            "summary": self._summary_line(source_kind, source_identifier, effective_mode, report),
            "recovery_goal": recovery_goal,
            "failure_summary": failure_summary,
            "likely_cause": likely_cause,
            "affected_files": affected_files,
            "relevant_context": relevant_context,
            "constraints": constraints,
            "required_llm_output": required_llm_output,
            "safety_reminder": safety_reminder,
            "prompt_text": prompt_text,
            "source_report": report,
        }

    def write_output(self, prompt_text: str, output_path: str | Path | None = None) -> None:
        self.prompt_builder.write_output(prompt_text, output_path)

    def copy_to_clipboard(self, prompt_text: str) -> bool:
        return self.prompt_builder.copy_to_clipboard(prompt_text)

    def _load_source_report(
        self,
        *,
        failure_id: str | None,
        latest: bool,
        drift: bool,
        plan_step: Optional[Tuple[str, int]],
        limit: int,
        pack: Dict[str, Any],
    ) -> tuple[str, str, Dict[str, Any]]:
        if drift:
            return "drift", "drift-report", self.report_builder.build_drift_report(context_pack=pack, limit=limit)

        if plan_step is not None:
            task_id, step_index = plan_step
            identifier = PlanStepRef(task_id, step_index).result_task_id
            return "plan_step_failure", identifier, self.report_builder.build_failure_detail(identifier, limit=limit)

        if failure_id:
            return "failure", failure_id, self.report_builder.build_failure_detail(failure_id, limit=limit)

        if latest:
            report = self.report_builder.build_failure_report(limit=limit)
            identifier = "latest-failure"
            if report.get("recent_failures"):
                identifier = str(report.get("recent_failures", [{}])[0].get("id") or identifier)
            return "latest_failure", identifier, report

        report = self.report_builder.build_failure_report(limit=limit)
        identifier = "latest-failure"
        if report.get("recent_failures"):
            identifier = str(report.get("recent_failures", [{}])[0].get("id") or identifier)
        return "latest_failure", identifier, report

    def _recommend_mode(self, report: Dict[str, Any], source_kind: str, *, plan_step: Optional[Tuple[str, int]] = None) -> str:
        if source_kind == "drift":
            return "review"

        if source_kind == "plan_step_failure":
            return self._recommend_for_failure(report, plan_step_failure=True)

        return self._recommend_for_failure(report, plan_step_failure=False)

    def _auto_recommend_mode(self, report: Dict[str, Any], source_kind: str, *, plan_step: Optional[Tuple[str, int]] = None) -> str:
        if source_kind == "drift":
            return "review"
        if source_kind == "plan_step_failure":
            return "plan"

        failure = self._primary_failure(report)
        if not failure:
            return "review"

        cause = str(failure.get("cause") or "unknown")
        if cause in {"invalid_envelope", "missing_file", "stale_context_possible", "unknown"}:
            return "review"
        if cause in {"policy_denied", "protected_path"}:
            return "review"
        if cause == "command_denied":
            return "plan"
        if cause == "patch_conflict":
            affected_files = failure.get("affected_files", []) if isinstance(failure.get("affected_files"), list) else []
            target = str(failure.get("target") or "")
            return "patch" if len(affected_files) <= 1 and target else "plan"
        if cause in {"test_failed", "execution_failed"}:
            return "plan"
        return "review"

    def _recommend_for_failure(self, report: Dict[str, Any], *, plan_step_failure: bool) -> str:
        failure = self._primary_failure(report)
        if not failure:
            return "review"

        cause = str(failure.get("cause") or "unknown")
        kind = str(failure.get("kind") or "")
        status = str(failure.get("status") or "")
        target = str(failure.get("target") or "")
        affected_files = failure.get("affected_files", []) if isinstance(failure.get("affected_files"), list) else []

        if cause in {"test_failed", "execution_failed", "command_denied"}:
            return "plan"
        if plan_step_failure:
            return "plan"
        if cause in {"missing_file", "patch_conflict"} and len(affected_files) <= 1 and target:
            return "patch"
        if cause in {"invalid_envelope", "protected_path", "policy_denied"}:
            return "review"
        if status in {"command_blocked", "validation_failed"}:
            return "review" if not target else "plan"
        if kind == "patch" and len(affected_files) <= 1:
            return "patch"
        return "review"

    def _primary_failure(self, report: Dict[str, Any]) -> Dict[str, Any]:
        recent_failures = report.get("recent_failures", [])
        if isinstance(recent_failures, list) and recent_failures:
            first = recent_failures[0]
            return first if isinstance(first, dict) else {}
        return {}

    def _recovery_goal(self, report: Dict[str, Any], source_kind: str, mode: str, source_identifier: str) -> str:
        failure = self._primary_failure(report)
        if source_kind == "drift":
            return "Refresh the Context Pack and ask the web LLM to work from the current workspace state again."
        if source_kind == "plan_step_failure":
            return f"Repair the failed plan step {source_identifier} with a safe {mode} follow-up."
        if failure:
            cause = failure.get("cause") or "unknown"
            return f"Recover from {cause} for {source_identifier} using a safe {mode} follow-up."
        return "Recover from the latest APOS failure with the safest next step."

    def _failure_summary(self, report: Dict[str, Any], source_kind: str, source_identifier: str) -> str:
        if source_kind == "drift":
            return str(report.get("recommended_human_action") or "Drift warning detected.")
        if source_kind == "plan_step_failure":
            return str(report.get("summary") or f"Plan step failure: {source_identifier}")
        if report.get("summary"):
            return str(report.get("summary"))
        return f"Failure source: {source_identifier}"

    def _likely_cause(self, report: Dict[str, Any], source_kind: str) -> str:
        if source_kind == "drift":
            signals = report.get("stale_context_signals", []) if isinstance(report.get("stale_context_signals"), list) else []
            return signals[0] if signals else "stale_context_possible"
        failure = self._primary_failure(report)
        return str(failure.get("cause") or (report.get("likely_causes", ["unknown"])[0] if report.get("likely_causes") else "unknown"))

    def _affected_files(self, report: Dict[str, Any]) -> List[str]:
        files = report.get("affected_files", [])
        if isinstance(files, list):
            return [str(item) for item in files if item]
        if report.get("changed_files"):
            return [str(item.get("path") or "") for item in report.get("changed_files", []) if isinstance(item, dict) and item.get("path")]
        return []

    def _relevant_context(self, report: Dict[str, Any], pack: Dict[str, Any], source_kind: str) -> List[str]:
        lines: List[str] = []
        if pack.get("generated_at"):
            lines.append(f"Context Pack generated at {pack.get('generated_at')}")
        if pack.get("recent_worklog_summary", {}).get("summary"):
            lines.append(str(pack.get("recent_worklog_summary", {}).get("summary")))
        approval_summary = pack.get("approval_queue_summary", {}) if isinstance(pack.get("approval_queue_summary"), dict) else {}
        if approval_summary.get("pending_count") is not None:
            lines.append(f"Pending approval items: {approval_summary.get('pending_count')}")
        if source_kind == "drift":
            for signal in report.get("stale_context_signals", []) if isinstance(report.get("stale_context_signals"), list) else []:
                lines.append(str(signal))
        else:
            for cause in report.get("likely_causes", []) if isinstance(report.get("likely_causes"), list) else []:
                lines.append(str(cause))
        for item in self._affected_files(report)[:5]:
            lines.append(item)
        return [line for line in lines if line]

    def _extra_constraints(self, source_kind: str, mode: str) -> List[str]:
        constraints = [
            "Do not auto-approve or auto-execute anything.",
            "Do not send the prompt automatically to the web LLM; copy it manually after review.",
            "Do not expose protected-path contents or secret-like values.",
        ]
        if source_kind == "drift":
            constraints.append("Refresh the Context Pack before proposing any code change.")
        if mode == "plan":
            constraints.append("Prefer a plan when commands or multi-step fixes are involved.")
        if mode == "patch":
            constraints.append("Keep the patch minimal and focused on one file when possible.")
        if mode == "review":
            constraints.append("If the root cause is unclear, stay in review mode and explain the uncertainty.")
        return constraints

    def _safety_reminder(self, source_kind: str, mode: str) -> str:
        if source_kind == "drift":
            return "Recovery prompts are guidance only. Re-check the live workspace before acting on them."
        if mode == "plan":
            return "Use plan mode when the fix needs commands, validation, or multiple steps."
        if mode == "patch":
            return "Use patch mode only if the change is small, local, and clear from the current context."
        return "Use review mode when the cause is uncertain or the safest action is still being determined."

    def _summary_line(self, source_kind: str, source_identifier: str, mode: str, report: Dict[str, Any]) -> str:
        if source_kind == "drift":
            return f"Recovery prompt for drift: recommended mode {mode}."
        failure = self._primary_failure(report)
        cause = failure.get("cause") or report.get("likely_causes", ["unknown"])[0] if report.get("likely_causes") else "unknown"
        return f"Recovery prompt for {source_identifier}: cause={cause}, recommended mode={mode}."
