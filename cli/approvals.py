#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apos_core.orchestrator import Orchestrator


def _make_orchestrator(workspace: str) -> Orchestrator:
    ws = Path(workspace).resolve()
    return Orchestrator(workspace_root=str(ws), history_db_path=ws / ".apos" / "history.sqlite3")


def _print_json(payload: object, pretty: bool) -> None:
    if pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage APOS approval queue items")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List pending approval items")
    list_parser.add_argument("--workspace", default=".")
    list_parser.add_argument("--task-id")
    list_parser.add_argument("--patch-id")
    list_parser.add_argument("--status")
    list_parser.add_argument("--item-type")
    list_parser.add_argument("--limit", type=int)
    list_parser.add_argument("--offset", type=int)
    list_parser.add_argument("--json", action="store_true")

    show_parser = subparsers.add_parser("show", help="Show one approval item")
    show_parser.add_argument("item_id")
    show_parser.add_argument("--workspace", default=".")
    show_parser.add_argument("--json", action="store_true")

    approve_parser = subparsers.add_parser("approve", help="Mark an approval item as approved")
    approve_parser.add_argument("item_id")
    approve_parser.add_argument("--workspace", default=".")
    approve_parser.add_argument("--approved-by")
    approve_parser.add_argument("--reason")
    approve_parser.add_argument("--json", action="store_true")

    reject_parser = subparsers.add_parser("reject", help="Mark an approval item as rejected")
    reject_parser.add_argument("item_id")
    reject_parser.add_argument("--workspace", default=".")
    reject_parser.add_argument("--rejected-by")
    reject_parser.add_argument("--reason")
    reject_parser.add_argument("--json", action="store_true")

    args = parser.parse_args()
    orch = _make_orchestrator(getattr(args, "workspace", "."))

    try:
        if args.command == "list":
            items = orch.list_pending_approvals(
                task_id=args.task_id,
                patch_id=args.patch_id,
                status=args.status,
                item_type=args.item_type,
                limit=args.limit,
                offset=args.offset,
            )
            if args.json:
                _print_json(items, pretty=True)
            else:
                for item in items:
                    print(f"{item.get('id')}\t{item.get('status')}\t{item.get('item_type')}\t{item.get('title')}")
            return 0

        if args.command == "show":
            item = orch.get_pending_approval(args.item_id)
            if not item:
                print(f"Approval item not found: {args.item_id}", file=sys.stderr)
                return 1
            _print_json(item, pretty=args.json)
            return 0

        if args.command == "approve":
            item = orch.approve_pending_approval(args.item_id, approved_by=args.approved_by, reason=args.reason)
            if not item:
                print(f"Approval item not found: {args.item_id}", file=sys.stderr)
                return 1
            _print_json(item, pretty=args.json)
            return 0

        if args.command == "reject":
            item = orch.reject_pending_approval(args.item_id, rejected_by=args.rejected_by, reason=args.reason)
            if not item:
                print(f"Approval item not found: {args.item_id}", file=sys.stderr)
                return 1
            _print_json(item, pretty=args.json)
            return 0

        return 2
    finally:
        try:
            orch.stop()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
