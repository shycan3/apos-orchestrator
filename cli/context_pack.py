#!/usr/bin/env python3
"""Generate a safe APOS context pack for the current workspace."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apos_core.context_pack import ContextPackBuilder


def print_human(pack: dict) -> None:
    print(f"workspace_root: {pack.get('workspace_root')}")
    print(f"project_root: {pack.get('project_root')}")
    stats = pack.get("stats", {})
    print(f"files_collected: {stats.get('files_collected', 0)}")
    print(f"preview_chars_used: {stats.get('preview_chars_used', 0)}")
    print("recent_history:")
    for item in pack.get("recent_history", []):
        print(
            f"- {item.get('task_id')} status={item.get('status')} exit_code={item.get('exit_code')} task_type={item.get('task_type')}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an APOS context pack")
    parser.add_argument("--workspace-root", default=str(PROJECT_ROOT), help="Workspace root to scan")
    parser.add_argument("--history-db", default=None, help="Path to the APOS history SQLite database")
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--max-files", type=int, default=120)
    parser.add_argument("--max-file-preview-chars", type=int, default=1200)
    parser.add_argument("--max-total-chars", type=int, default=12000)
    parser.add_argument("--json", action="store_true", help="Print the context pack as JSON")
    args = parser.parse_args()

    builder = ContextPackBuilder(args.workspace_root, history_db_path=args.history_db)
    pack = builder.build(
        max_depth=args.max_depth,
        max_files=args.max_files,
        max_file_preview_chars=args.max_file_preview_chars,
        max_total_chars=args.max_total_chars,
    )

    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
    else:
        print_human(pack)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())