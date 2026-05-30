#!/usr/bin/env python3
"""Approve and execute a plan step by task_id and step index."""
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Approve and execute a step from a recorded plan_only task")
    parser.add_argument("task_id", help="Task id of the plan_only envelope (as recorded in history)")
    parser.add_argument("--workspace", help="Workspace root where task was intended to run", required=True)
    parser.add_argument("--step", type=int, default=0, help="Zero-based step index to execute")
    parser.add_argument("--approved-by", help="Identifier of approver", default="manual")
    parser.add_argument("--reason", help="Approval reason", default=None)
    parser.add_argument("--force", action="store_true", help="Allow rerun of an executed or failed step")
    parser.add_argument("--json", action="store_true", help="Print result envelope as JSON")
    parser.add_argument("--quiet", action="store_true", help="Suppress console output (exit code still reflects result)")
    parser.add_argument("--log-file", help="Append the result envelope JSON to a log file (path)")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    history_db_path = workspace / ".apos" / "history.sqlite3"
    orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db_path)

    try:
        manager = PlanStepManager(orch)
        manager.approve_step(args.task_id, args.step, approved_by=args.approved_by, reason=args.reason)
        result = manager.run_step(args.task_id, args.step, approved_by=args.approved_by, force=args.force)

        if args.log_file:
            try:
                p = Path(args.log_file)
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(result, ensure_ascii=False) + "\n")
            except Exception as exc:
                if not args.quiet:
                    print(f"Failed to write log file: {exc}", file=sys.stderr)

        if not args.quiet:
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
