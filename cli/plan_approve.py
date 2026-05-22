"""Approve and execute a plan step by task_id and step index."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apos_core.orchestrator import Orchestrator
from apos_core.result_envelope import utc_now_iso


def main() -> int:
    parser = argparse.ArgumentParser(description="Approve and execute a step from a recorded plan_only task")
    parser.add_argument("task_id", help="Task id of the plan_only envelope (as recorded in history)")
    parser.add_argument("--workspace", help="Workspace root where task was intended to run", required=True)
    parser.add_argument("--step", type=int, default=0, help="Zero-based step index to execute")
    parser.add_argument("--approved-by", help="Identifier of approver", default=None)
    parser.add_argument("--json", action="store_true", help="Print result envelope as JSON")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    history_db_path = workspace / ".apos" / "history.sqlite3"
    orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db_path)

    result = orch.execute_plan_step(args.task_id, args.step, approved_by=args.approved_by)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"task_id={result.get('task_id')} status={result.get('status')} exit_code={result.get('exit_code')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
