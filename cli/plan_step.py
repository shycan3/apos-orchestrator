"""Execute a single step from a plan_only task envelope."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apos_core.task_envelope import validate_task_envelope, make_task_envelope
from apos_core.orchestrator import Orchestrator
from apos_core.result_envelope import build_result_envelope, utc_now_iso


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute one step from a plan_only envelope")
    parser.add_argument("plan_file", help="Path to plan_only task envelope JSON file")
    parser.add_argument("--step", type=int, default=0, help="Zero-based step index to execute")
    parser.add_argument("--json", action="store_true", help="Print result envelope as JSON")
    args = parser.parse_args()

    p = Path(args.plan_file)
    if not p.exists():
        print(f"Plan file not found: {p}")
        return 2

    try:
        envelope = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}")
        return 3

    check = validate_task_envelope(envelope)
    if not check.get("ok"):
        print("Plan envelope validation failed:")
        print(json.dumps(check.get("errors", []), ensure_ascii=False, indent=2))
        return 4

    normalized = check["normalized"]
    if normalized.get("task_type") != "plan_only":
        print("Provided task is not plan_only")
        return 5

    meta = normalized.get("meta", {})
    plan_steps = meta.get("plan_steps", [])
    if args.step < 0 or args.step >= len(plan_steps):
        print(f"Invalid step index: {args.step}")
        return 6

    step = plan_steps[args.step]

    # Build a standalone task envelope for the selected step
    step_task_type = step.get("task_type")
    step_patches = step.get("patches", [])
    step_commands = step.get("commands", [])

    task_env = make_task_envelope(
        task_type=step_task_type,
        workspace_root=normalized.get("workspace_root"),
        created_by=normalized.get("created_by"),
        task_id=f"{normalized.get('task_id')}-step-{args.step}",
        patches=step_patches,
        commands=step_commands,
        options=normalized.get("options"),
        meta={"plan_parent": normalized.get("task_id"), "plan_step_index": args.step},
    )

    workspace = task_env.get("workspace_root")
    history_db_path = Path(workspace) / ".apos" / "history.sqlite3"
    orch = Orchestrator(workspace_root=workspace, history_db_path=history_db_path)

    # Execute step synchronously using the Executor to avoid worker queue complexity
    started_at = utc_now_iso()
    try:
        executor = orch.executor
        # Convert patches shape: from plan step patches (target, intent, content) to executor changes
        applied = []
        for p in step_patches:
            change = {
                "path": p.get("target"),
                "action": "modify" if p.get("intent") in {"update", "modify"} else p.get("intent") or "modify",
                "content": p.get("content", ""),
            }
            if p.get("intent") == "search_and_replace":
                change["action"] = "search_and_replace"
                change["search"] = p.get("search")
                change["replace"] = p.get("replace")
            applied.append(change)

        patch_results = []
        if applied:
            patch_results = executor.apply_patch(applied)

        cmd_result = None
        if step_commands:
            # run the first command only
            cmd = step_commands[0].get("command")
            timeout = int(step_commands[0].get("timeout_seconds", 30))
            cmd_result = executor.run_command(cmd, cwd=workspace, timeout=timeout)

        finished_at = utc_now_iso()

        # Build a minimal result envelope
        status = "success"
        exit_code = 0
        stderr = ""
        stdout = ""
        if cmd_result:
            exit_code = cmd_result.get("exit_code")
            stdout = cmd_result.get("stdout", "")
            stderr = cmd_result.get("stderr", "")
            if exit_code not in (0, None):
                status = "failed"

        result = build_result_envelope(
            task_id=task_env.get("task_id"),
            status=status,
            exit_code=exit_code,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=0,
            patch_applied=bool(patch_results),
            patch_blocked=False,
            patch_blocked_reason="",
            patch_preview=patch_results or None,
            snapshot_enabled=False,
            snapshot_commit=None,
            snapshot_error="",
            command=step_commands[0] if step_commands else None,
            command_allowed=True,
            policy_blocked=False,
            blocked_reason="",
            stdout=stdout,
            stderr=stderr,
            workspace_root=workspace,
            history_db_path=str(orch.recorder.db_path),
            meta={"plan_parent": normalized.get("task_id"), "plan_step_index": args.step},
        )

    except Exception as exc:
        finished_at = utc_now_iso()
        result = build_result_envelope(
            task_id=task_env.get("task_id"),
            status="internal_error",
            exit_code=-1,
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
            blocked_reason="",
            stdout="",
            stderr=str(exc),
            workspace_root=workspace,
            history_db_path=str(orch.recorder.db_path),
            meta={"plan_parent": normalized.get("task_id"), "plan_step_index": args.step},
        )

    # Record result
    try:
        orch.recorder.record_result(
            str(__import__('uuid').uuid4()),
            result.get("task_id"),
            result.get("exit_code"),
            result.get("stdout"),
            result.get("stderr"),
            {"task_type": step_task_type},
            result_envelope=result,
        )
    except Exception:
        pass

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"task_id={result.get('task_id')} status={result.get('status')} exit_code={result.get('exit_code')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
