#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

from apos_core.orchestrator import Orchestrator


def main():
    p = argparse.ArgumentParser(description="List approval events for a task")
    p.add_argument("task_id", help="Task ID to query")
    p.add_argument("--workspace", default=".", help="Workspace root")
    p.add_argument("--approver", help="Filter by approver name")
    p.add_argument("--start", help="Filter: start timestamp (epoch seconds or ISO) ")
    p.add_argument("--end", help="Filter: end timestamp (epoch seconds or ISO) ")
    p.add_argument("--pretty", action="store_true", help="Pretty-print timestamps as ISO")
    p.add_argument("--limit", type=int, help="Limit number of results")
    p.add_argument("--offset", type=int, help="Offset for pagination")
    args = p.parse_args()

    ws = Path(args.workspace).resolve()
    history_db = ws / ".apos" / "history.sqlite3"
    orch = Orchestrator(workspace_root=str(ws), history_db_path=history_db)
    def parse_time(val):
        if not val:
            return None
        try:
            return float(val)
        except Exception:
            pass
        try:
            if val.endswith('Z'):
                val = val[:-1] + '+00:00'
            dt = datetime.fromisoformat(val)
            return dt.timestamp()
        except Exception:
            return None

    try:
        start_ts = parse_time(args.start)
        end_ts = parse_time(args.end)
        approvals = orch.recorder.get_approvals(
            args.task_id, approver=args.approver, start_ts=start_ts, end_ts=end_ts, limit=args.limit, offset=args.offset
        )
        if args.pretty:
            from datetime import datetime
            for a in approvals:
                a['timestamp_iso'] = datetime.fromtimestamp(a['timestamp']).isoformat()
        print(json.dumps(approvals, indent=2, ensure_ascii=False))
    finally:
        try:
            orch.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
