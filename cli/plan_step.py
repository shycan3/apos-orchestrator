#!/usr/bin/env python3
"""Execute a single step from a plan_only task envelope."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apos_core.orchestrator import Orchestrator
from apos_core.plan_flow import PlanStepManager
from apos_core.task_envelope import validate_task_envelope


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute one step from a plan_only envelope")
    parser.add_argument("plan_file", help="Path to plan_only task envelope JSON file")
    parser.add_argument("--step", type=int, default=0, help="Zero-based step index to execute")
    parser.add_argument("--approved-by", default="manual", help="Identifier to record with the approval")
    parser.add_argument("--reason", default=None, help="Optional approval reason")
    parser.add_argument("--force", action="store_true", help="Allow rerun of an executed or failed step")
    parser.add_argument("--json", action="store_true", help="Print result envelope as JSON")
    args = parser.parse_args()

    plan_path = Path(args.plan_file)
    if not plan_path.exists():
        print(f"Plan file not found: {plan_path}")
        return 2

    try:
        envelope = json.loads(plan_path.read_text(encoding="utf-8"))
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

    workspace = normalized.get("workspace_root")
    history_db_path = Path(workspace) / ".apos" / "history.sqlite3"
    orch = Orchestrator(workspace_root=workspace, history_db_path=history_db_path)
    try:
        orch.recorder.record_task(normalized.get("task_id"), normalized)
        manager = PlanStepManager(orch)
        manager.approve_step(normalized.get("task_id"), args.step, approved_by=args.approved_by, reason=args.reason)
        result = manager.run_step(
            normalized.get("task_id"),
            args.step,
            approved_by=args.approved_by,
            force=args.force,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"task_id={result.get('task_id')} status={result.get('status')} exit_code={result.get('exit_code')}")
        return 0
    finally:
        try:
            orch.stop()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
