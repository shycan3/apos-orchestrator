#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from apos_core.orchestrator import Orchestrator


def main():
    p = argparse.ArgumentParser(description="List approval events for a task")
    p.add_argument("task_id", help="Task ID to query")
    p.add_argument("--workspace", default=".", help="Workspace root")
    p.add_argument("--approver", help="Filter by approver name")
    p.add_argument("--start", type=float, help="Filter: start timestamp (epoch seconds)")
    p.add_argument("--end", type=float, help="Filter: end timestamp (epoch seconds)")
    p.add_argument("--limit", type=int, help="Limit number of results")
    p.add_argument("--offset", type=int, help="Offset for pagination")
    args = p.parse_args()

    ws = Path(args.workspace).resolve()
    history_db = ws / ".apos" / "history.sqlite3"
    orch = Orchestrator(workspace_root=str(ws), history_db_path=history_db)
    try:
        approvals = orch.list_approvals(
            args.task_id,
        )
        # apply filters by calling recorder directly to use full options
        approvals = orch.recorder.get_approvals(
            args.task_id, approver=args.approver, start_ts=args.start, end_ts=args.end, limit=args.limit, offset=args.offset
        )
        print(json.dumps(approvals, indent=2, ensure_ascii=False))
    finally:
        try:
            orch.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
