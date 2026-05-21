"""CLI tools for safe snapshot inspection and file-level restore."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow direct script execution: python cli/snapshot_tools.py ...
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apos_core.snapshot import SnapshotManager


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="APOS snapshot inspection and file restore tools")
    parser.add_argument(
        "--workspace",
        default=os.getcwd(),
        help="Workspace root path (default: current working directory)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check-commit", help="Check whether a snapshot commit exists")
    check.add_argument("--commit", required=True, help="Snapshot commit hash")

    diff = sub.add_parser("diff", help="List changed files since snapshot commit")
    diff.add_argument("--commit", required=True, help="Snapshot commit hash")

    restore = sub.add_parser("restore-file", help="Restore a single file from snapshot commit")
    restore.add_argument("--commit", required=True, help="Snapshot commit hash")
    restore.add_argument("--path", required=True, help="Relative file path from workspace root")

    return parser


def main() -> int:
    parser = create_parser()
    args = parser.parse_args()

    manager = SnapshotManager(args.workspace)

    if args.command == "check-commit":
        res = manager.commit_exists(args.commit)
        print(f"ok={res['ok']} commit={args.commit}")
        if not res["ok"]:
            print(res["git"]["stderr"].strip())
            return 2
        return 0

    if args.command == "diff":
        res = manager.list_changed_files_since(args.commit)
        print(f"ok={res['ok']} commit={args.commit}")
        if not res["ok"]:
            print(res.get("message", "diff_failed"))
            return 2
        for item in res["files"]:
            print(item)
        return 0

    if args.command == "restore-file":
        res = manager.restore_file_from_snapshot(args.commit, args.path)
        print(f"ok={res['ok']} commit={args.commit} path={args.path}")
        if not res["ok"]:
            print(res.get("message", "restore_failed"))
            git = res.get("git")
            if git:
                print(git.get("stderr", "").strip())
            return 2
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
