"""Plan-only step management helpers for APOS."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from .result_envelope import build_result_envelope, utc_now_iso
from .task_envelope import validate_task_envelope

PLAN_STEP_STATUSES = {
    "pending",
    "approved",
    "rejected",
    "running",
    "executed",
    "failed",
    "skipped",
}


@dataclass(frozen=True)
class PlanStepRef:
    task_id: str
    step_index: int

    @property
    def item_id(self) -> str:
        return f"{self.task_id}:step:{self.step_index}"

    @property
    def result_task_id(self) -> str:
        return f"{self.task_id}-step-{self.step_index}"


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


def _normalize_step(step: dict, step_index: int) -> dict:
    patches = step.get("patches") if isinstance(step.get("patches"), list) else []
    commands = step.get("commands") if isinstance(step.get("commands"), list) else []
    return {
        "step_index": step_index,
        "title": str(step.get("title") or f"step {step_index}"),
        "task_type": str(step.get("task_type") or ""),
        "patches": patches,
        "commands": commands,
        "patch_count": len(patches),
        "command_count": len(commands),
        "description": str(step.get("description") or step.get("summary") or ""),
    }


class PlanStepManager:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.recorder = orchestrator.recorder
        self.executor = orchestrator.executor
        self.workspace_root = orchestrator.workspace_root

    def close(self) -> None:
        try:
            self.orchestrator.stop()
        except Exception:
            pass

    def list_plans(self, limit: Optional[int] = None, offset: Optional[int] = None) -> list[dict]:
        plans = []
        for task in self.recorder.list_tasks(task_type="plan_only", limit=limit, offset=offset):
            plans.append(self._build_plan_summary(task))
        return plans

    def get_plan(self, task_id: str) -> Optional[dict]:
        task = self.recorder.get_task(task_id)
        if not task:
            return None
        return self._build_plan_detail(task_id, task)

    def list_steps(self, task_id: str) -> list[dict]:
        detail = self.get_plan(task_id)
        if not detail:
            return []
        return detail.get("steps", [])

    def get_step(self, task_id: str, step_index: int) -> Optional[dict]:
        detail = self.get_plan(task_id)
        if not detail:
            return None
        steps = detail.get("steps", [])
        if step_index < 0 or step_index >= len(steps):
            return None
        return steps[step_index]

    def approve_step(self, task_id: str, step_index: int, approved_by: Optional[str] = None, reason: Optional[str] = None) -> Optional[dict]:
        ref = PlanStepRef(task_id, step_index)
        item = self._ensure_step_item(ref)
        if not item:
            return None

        updated = self.recorder.update_approval_item_status(
            ref.item_id,
            "approved",
            decided_by=approved_by,
            decision_reason=reason,
            meta={"plan_action": "approve_step"},
        )
        if approved_by:
            try:
                self.recorder.record_approval(str(uuid.uuid4()), task_id, step_index, approved_by, {"plan_action": "approve_step", "reason": reason or ""})
            except Exception:
                pass
        return updated

    def reject_step(self, task_id: str, step_index: int, rejected_by: Optional[str] = None, reason: Optional[str] = None) -> Optional[dict]:
        ref = PlanStepRef(task_id, step_index)
        item = self._ensure_step_item(ref)
        if not item:
            return None
        return self.recorder.update_approval_item_status(
            ref.item_id,
            "rejected",
            decided_by=rejected_by,
            decision_reason=reason,
            meta={"plan_action": "reject_step"},
        )

    def run_step(
        self,
        task_id: str,
        step_index: int,
        *,
        force: bool = False,
        approved_by: Optional[str] = None,
    ) -> dict:
        task_payload = self.recorder.get_task(task_id)
        if not task_payload:
            return self._skipped_result(task_id, step_index, "task_not_found", status="not_found", exit_code=-2)

        check = validate_task_envelope(task_payload)
        if not check.get("ok"):
            return build_result_envelope(
                task_id=task_id,
                status="validation_failed",
                exit_code=-6,
                started_at=utc_now_iso(),
                finished_at=utc_now_iso(),
                duration_ms=0,
                patch_applied=False,
                patch_blocked=False,
                patch_blocked_reason="",
                patch_preview=None,
                snapshot_enabled=False,
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
                meta={"validation_errors": check.get("errors", []), "plan_parent": task_id, "plan_step_index": step_index},
            )

        normalized = check["normalized"]
        if normalized.get("task_type") != "plan_only":
            return self._skipped_result(task_id, step_index, "not_a_plan_only_task", status="invalid_task_type", exit_code=-7)

        plan = self._build_plan_detail(task_id, normalized)
        steps = plan.get("steps", [])
        if step_index < 0 or step_index >= len(steps):
            return self._skipped_result(task_id, step_index, "invalid_step_index", status="invalid_step", exit_code=-8)

        step = steps[step_index]
        ref = PlanStepRef(task_id, step_index)
        item = self._ensure_step_item(ref, task_payload=normalized, step=step)
        if not item:
            return self._skipped_result(task_id, step_index, "plan_step_item_not_found", status="not_found", exit_code=-2)

        current_status = item.get("status") or "pending"
        if current_status == "running":
            return self._skipped_result(task_id, step_index, "step_already_running", status="skipped", exit_code=0)
        if current_status == "rejected":
            return self._skipped_result(task_id, step_index, "step_rejected", status="skipped", exit_code=0)
        if current_status == "pending":
            return self._skipped_result(task_id, step_index, "approval_required", status="skipped", exit_code=0)
        if current_status == "executed" and not force:
            return self._skipped_result(task_id, step_index, "step_already_executed", status="skipped", exit_code=0)
        if current_status == "failed" and not force:
            return self._skipped_result(task_id, step_index, "step_failed_requires_force", status="skipped", exit_code=0)
        if current_status not in PLAN_STEP_STATUSES:
            return self._skipped_result(task_id, step_index, f"unsupported_step_status:{current_status}", status="skipped", exit_code=0)

        started_at = utc_now_iso()
        try:
            self.recorder.update_approval_item_status(
                ref.item_id,
                "running",
                decided_by=approved_by,
                decision_reason=None,
                meta={"plan_action": "run_step", "force": force, "started_at": started_at},
            )
        except Exception:
            pass

        patch_results: list[dict] = []
        command_results: list[dict] = []
        aggregated_stdout: list[str] = []
        aggregated_stderr: list[str] = []
        status = "success"
        exit_code = 0
        blocked_reason = ""
        patch_applied = False
        patch_blocked = False
        policy_blocked = False

        try:
            patches = step.get("patches", [])
            if patches:
                changes = []
                for patch in patches:
                    action = "modify"
                    if patch.get("intent") in {"create", "overwrite"}:
                        action = "create"
                    elif patch.get("intent") in {"update", "modify"}:
                        action = "modify"
                    elif patch.get("intent") == "search_and_replace":
                        action = "search_and_replace"
                    change = {
                        "path": patch.get("target"),
                        "action": action,
                        "content": patch.get("content", ""),
                    }
                    if action == "search_and_replace":
                        change["search"] = patch.get("search", "")
                        change["replace"] = patch.get("replace", "")
                    changes.append(change)
                patch_results = self.executor.apply_patch(changes)
                patch_applied = any(result.get("status") in {"written", "deleted", "search_and_replace_applied"} for result in patch_results)
                if any(result.get("status") in {"blocked", "rejected", "error"} for result in patch_results):
                    patch_blocked = True
                    status = "patch_blocked"
                    exit_code = -4
                    blocked_reason = "; ".join(
                        str(result.get("blocked_reason") or result.get("reason") or "patch_blocked")
                        for result in patch_results
                        if result.get("status") in {"blocked", "rejected", "error"}
                    )
                    result_envelope = self._build_step_result(
                        ref,
                        normalized,
                        step,
                        status=status,
                        exit_code=exit_code,
                        started_at=started_at,
                        patch_results=patch_results,
                        command_results=command_results,
                        stdout="\n".join(aggregated_stdout),
                        stderr=blocked_reason,
                        patch_applied=patch_applied,
                        patch_blocked=patch_blocked,
                        policy_blocked=policy_blocked,
                        blocked_reason=blocked_reason,
                        approved_by=approved_by,
                        force=force,
                    )
                    self._finalize_step_result(ref, result_envelope, item_status="failed", decided_by=approved_by, reason=blocked_reason)
                    return result_envelope

            for command_index, command_entry in enumerate(step.get("commands", []) or []):
                command_value = command_entry.get("command") if isinstance(command_entry, dict) else command_entry
                timeout = 30
                if isinstance(command_entry, dict):
                    timeout = int(command_entry.get("timeout_seconds", 30))

                command_check = self.executor.command_policy.validate_command(command_value)
                if not command_check.get("allowed", False):
                    status = "command_blocked"
                    exit_code = -3
                    blocked_reason = command_check.get("blocked_reason", "command_blocked_by_policy")
                    command_results.append(
                        {
                            "index": command_index,
                            "command": command_value,
                            "policy_blocked": True,
                            "blocked_reason": blocked_reason,
                            "exit_code": -3,
                        }
                    )
                    policy_blocked = True
                    break

                command_result = self.executor.run_command(command_value, cwd=normalized.get("workspace_root") or self.workspace_root, timeout=timeout)
                command_results.append(
                    {
                        "index": command_index,
                        "command": command_value,
                        "policy_blocked": command_result.get("policy_blocked", False),
                        "blocked_reason": command_result.get("blocked_reason", ""),
                        "exit_code": command_result.get("exit_code"),
                        "stdout": command_result.get("stdout", ""),
                        "stderr": command_result.get("stderr", ""),
                        "timed_out": command_result.get("timed_out", False),
                    }
                )
                aggregated_stdout.append(command_result.get("stdout", "") or "")
                if command_result.get("stderr"):
                    aggregated_stderr.append(command_result.get("stderr", ""))
                exit_code = command_result.get("exit_code")
                if command_result.get("policy_blocked"):
                    status = "command_blocked"
                    policy_blocked = True
                    blocked_reason = command_result.get("blocked_reason", "command_blocked")
                    break
                if exit_code not in (0, None):
                    status = "failed"
                    blocked_reason = command_result.get("stderr", "") or f"command_exit_code:{exit_code}"
                    break

            if status == "success":
                status = "success"
                exit_code = 0

            finished_at = utc_now_iso()
            result_envelope = self._build_step_result(
                ref,
                normalized,
                step,
                status=status,
                exit_code=exit_code,
                started_at=started_at,
                finished_at=finished_at,
                patch_results=patch_results,
                command_results=command_results,
                stdout="\n".join(filter(None, aggregated_stdout)),
                stderr="\n".join(filter(None, aggregated_stderr)) if aggregated_stderr else blocked_reason,
                patch_applied=patch_applied,
                patch_blocked=patch_blocked,
                policy_blocked=policy_blocked,
                blocked_reason=blocked_reason,
                approved_by=approved_by,
                force=force,
            )
            final_status = "executed" if status == "success" else "failed"
            self._finalize_step_result(ref, result_envelope, item_status=final_status, decided_by=approved_by, reason=blocked_reason or None)
            return result_envelope
        except Exception as exc:
            finished_at = utc_now_iso()
            result_envelope = self._build_step_result(
                ref,
                normalized,
                step,
                status="internal_error",
                exit_code=-1,
                started_at=started_at,
                finished_at=finished_at,
                patch_results=patch_results,
                command_results=command_results,
                stdout="\n".join(filter(None, aggregated_stdout)),
                stderr=str(exc),
                patch_applied=patch_applied,
                patch_blocked=patch_blocked,
                policy_blocked=policy_blocked,
                blocked_reason=str(exc),
                approved_by=approved_by,
                force=force,
            )
            self._finalize_step_result(ref, result_envelope, item_status="failed", decided_by=approved_by, reason=str(exc))
            return result_envelope

    def _build_plan_summary(self, task_record: dict) -> dict:
        payload = task_record.get("payload") or {}
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        plan_steps = meta.get("plan_steps") if isinstance(meta.get("plan_steps"), list) else []
        step_items = self.recorder.list_approval_items(task_id=task_record.get("id"), item_type="plan_step")
        status_counts = self._step_status_counts(step_items)
        return {
            "task_id": task_record.get("id"),
            "created_at": task_record.get("created_at"),
            "task_type": payload.get("task_type") or "plan_only",
            "plan_goal": meta.get("plan_goal") or meta.get("goal") or "",
            "step_count": len(plan_steps),
            "pending_count": status_counts.get("pending", 0),
            "approved_count": status_counts.get("approved", 0),
            "running_count": status_counts.get("running", 0),
            "executed_count": status_counts.get("executed", 0),
            "failed_count": status_counts.get("failed", 0),
            "rejected_count": status_counts.get("rejected", 0),
            "skipped_count": status_counts.get("skipped", 0),
            "latest_status": self._latest_step_status(step_items),
        }

    def _build_plan_detail(self, task_id: str, payload: dict) -> dict:
        task = payload if payload.get("task_type") == "plan_only" else self.recorder.get_task(task_id) or payload
        meta = task.get("meta") if isinstance(task.get("meta"), dict) else {}
        plan_steps = meta.get("plan_steps") if isinstance(meta.get("plan_steps"), list) else []
        step_items = {item.get("step_index"): item for item in self.recorder.list_approval_items(task_id=task_id, item_type="plan_step")}
        steps: list[dict] = []
        for index, step in enumerate(plan_steps):
            normalized = _normalize_step(step if isinstance(step, dict) else {}, index)
            item = step_items.get(index) or self._ensure_step_item(PlanStepRef(task_id, index), task_payload=task, step=normalized)
            latest_result = self.recorder.get_latest_result(PlanStepRef(task_id, index).result_task_id)
            steps.append(
                {
                    **normalized,
                    "item_id": item.get("id") if item else PlanStepRef(task_id, index).item_id,
                    "status": item.get("status") if item else "pending",
                    "approved_by": item.get("decided_by") if item else None,
                    "decided_at": item.get("decided_at") if item else None,
                    "decision_reason": item.get("decision_reason") if item else None,
                    "result": self._summarize_result(latest_result),
                }
            )
        return {
            "task_id": task_id,
            "task_type": task.get("task_type") or "plan_only",
            "created_by": task.get("created_by") or "",
            "workspace_root": task.get("workspace_root") or self.workspace_root,
            "plan_goal": meta.get("plan_goal") or meta.get("goal") or "",
            "step_count": len(steps),
            "steps": steps,
            "summary": self._build_plan_summary({"id": task_id, "payload": task, "created_at": task.get("created_at")}),
        }

    def _ensure_step_item(self, ref: PlanStepRef, task_payload: Optional[dict] = None, step: Optional[dict] = None) -> Optional[dict]:
        item = self.recorder.get_approval_item(ref.item_id)
        if item:
            return item
        task = task_payload or self.recorder.get_task(ref.task_id)
        if not task:
            return None
        payload = task if isinstance(task, dict) else {}
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        plan_steps = meta.get("plan_steps") if isinstance(meta.get("plan_steps"), list) else []
        raw_step = step or (plan_steps[ref.step_index] if 0 <= ref.step_index < len(plan_steps) else {})
        normalized = _normalize_step(raw_step if isinstance(raw_step, dict) else {}, ref.step_index)
        step_payload = {
            "task_id": ref.task_id,
            "step_index": ref.step_index,
            "step": raw_step,
            "plan_goal": meta.get("plan_goal") or meta.get("goal") or "",
        }
        return self.recorder.record_approval_item(
            ref.item_id,
            ref.task_id,
            "plan_step",
            normalized.get("title") or f"step {ref.step_index}",
            step_payload,
            step_index=ref.step_index,
            workspace_root=payload.get("workspace_root") or self.workspace_root,
            status="pending",
            meta={"plan_goal": meta.get("plan_goal") or meta.get("goal") or "", "step_status": "pending"},
        )

    def _build_step_result(
        self,
        ref: PlanStepRef,
        normalized_task: dict,
        step: dict,
        *,
        status: str,
        exit_code: int,
        started_at: str,
        patch_results: Optional[list[dict]] = None,
        command_results: Optional[list[dict]] = None,
        stdout: str = "",
        stderr: str = "",
        patch_applied: bool = False,
        patch_blocked: bool = False,
        policy_blocked: bool = False,
        blocked_reason: str = "",
        approved_by: Optional[str] = None,
        force: bool = False,
        finished_at: Optional[str] = None,
    ) -> dict:
        finished = finished_at or utc_now_iso()
        meta = {
            "task_type": "plan_only",
            "plan_parent": ref.task_id,
            "plan_step_index": ref.step_index,
            "step_title": step.get("title") if isinstance(step, dict) else "",
            "step_task_type": step.get("task_type") if isinstance(step, dict) else "",
            "approved_by": approved_by,
            "force": force,
            "patch_results": patch_results or [],
            "command_results": command_results or [],
        }
        return build_result_envelope(
            task_id=ref.result_task_id,
            status=status,
            exit_code=exit_code,
            started_at=started_at,
            finished_at=finished,
            duration_ms=0,
            patch_applied=patch_applied,
            patch_blocked=patch_blocked,
            patch_blocked_reason=blocked_reason if patch_blocked else "",
            patch_preview=patch_results,
            snapshot_enabled=False,
            snapshot_commit=None,
            snapshot_error="",
            command=command_results[0]["command"] if command_results else None,
            command_allowed=not policy_blocked if command_results else None,
            policy_blocked=policy_blocked,
            blocked_reason=blocked_reason,
            stdout=stdout,
            stderr=stderr,
            workspace_root=normalized_task.get("workspace_root") or self.workspace_root,
            history_db_path=str(self.recorder.db_path),
            meta=meta,
        )

    def _finalize_step_result(self, ref: PlanStepRef, result: dict, *, item_status: str, decided_by: Optional[str], reason: Optional[str]) -> None:
        try:
            self.recorder.record_result(
                str(uuid.uuid4()),
                ref.result_task_id,
                result.get("exit_code"),
                result.get("stdout", ""),
                result.get("stderr", ""),
                {
                    "task_type": "plan_only",
                    "plan_parent": ref.task_id,
                    "plan_step_index": ref.step_index,
                    "step_status": item_status,
                    "approved_by": decided_by,
                    "command_results": result.get("meta", {}).get("command_results", []),
                    "patch_results": result.get("meta", {}).get("patch_results", []),
                },
                result_envelope=result,
            )
        except Exception:
            pass

        try:
            self.recorder.update_approval_item_status(
                ref.item_id,
                item_status,
                decided_by=decided_by,
                decision_reason=reason,
                meta={
                    "last_result": {
                        "task_id": result.get("task_id"),
                        "status": result.get("status"),
                        "exit_code": result.get("exit_code"),
                        "started_at": result.get("started_at"),
                        "finished_at": result.get("finished_at"),
                    },
                    "step_status": item_status,
                },
            )
        except Exception:
            pass

    def _skipped_result(self, task_id: str, step_index: int, reason: str, *, status: str = "skipped", exit_code: int = 0) -> dict:
        started_at = utc_now_iso()
        finished_at = utc_now_iso()
        result = build_result_envelope(
            task_id=f"{task_id}-step-{step_index}",
            status=status,
            exit_code=exit_code,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=0,
            patch_applied=False,
            patch_blocked=False,
            patch_blocked_reason="",
            patch_preview=None,
            snapshot_enabled=False,
            snapshot_commit=None,
            snapshot_error="",
            command=None,
            command_allowed=None,
            policy_blocked=False,
            blocked_reason=reason,
            stdout="",
            stderr=reason,
            workspace_root=self.workspace_root,
            history_db_path=str(self.recorder.db_path),
            meta={"task_type": "plan_only", "plan_parent": task_id, "plan_step_index": step_index, "skip_reason": reason},
        )
        try:
            self.recorder.record_result(
                str(uuid.uuid4()),
                result.get("task_id"),
                result.get("exit_code"),
                "",
                reason,
                {"task_type": "plan_only", "plan_parent": task_id, "plan_step_index": step_index, "skip_reason": reason},
                result_envelope=result,
            )
        except Exception:
            pass
        return result

    def _step_status_counts(self, items: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            status = str(item.get("status") or "pending")
            counts[status] = counts.get(status, 0) + 1
        return counts

    def _latest_step_status(self, items: list[dict]) -> str:
        if not items:
            return "pending"
        ordered = sorted(items, key=lambda item: float(item.get("step_index") or 0))
        return str(ordered[-1].get("status") or "pending")

    def _summarize_result(self, result: Optional[dict]) -> dict:
        if not result:
            return {}
        result_envelope = result.get("result_envelope") or {}
        meta = result_envelope.get("meta") or {}
        return {
            "task_id": result.get("task_id"),
            "status": result_envelope.get("status") or "",
            "exit_code": result.get("exit_code"),
            "stdout": (result.get("stdout") or "")[:240],
            "stderr": (result.get("stderr") or "")[:240],
            "command_results": meta.get("command_results", []),
            "patch_results": meta.get("patch_results", []),
        }
