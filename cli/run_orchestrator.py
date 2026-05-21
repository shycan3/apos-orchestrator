"""Simple CLI to run the APOS orchestrator and submit a demo task."""
from __future__ import annotations

import time
import os
import sys
import argparse
import json
from pathlib import Path

# Allow direct script execution: python cli/run_orchestrator.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apos_core.orchestrator import Orchestrator


def demo_task(workspace_root: str) -> dict:
    # This demo writes a file and runs a simple python command that may fail.
    return {
        "id": "demo-task-1",
        "patches": [
            {"path": "workspace/hello.py", "action": "modify", "content": "print('hello from APOS')\n"}
        ],
        "command": ["python", "workspace/hello.py"],
        "timeout": 10,
    }


def main():
    parser = argparse.ArgumentParser(description="Run APOS orchestrator demo task")
    parser.add_argument("--enable-snapshots", action="store_true", help="Enable pre-task git snapshots")
    parser.add_argument(
        "--continue-on-snapshot-error",
        action="store_true",
        help="Continue task execution even when snapshot creation fails",
    )
    parser.add_argument(
        "--snapshot-auto-init-git",
        action="store_true",
        help="Auto-run git init in workspace when repository is missing",
    )
    parser.add_argument(
        "--unsafe-disable-command-policy",
        action="store_true",
        help="Disable command allow/deny policy (unsafe; not recommended)",
    )
    parser.add_argument(
        "--unsafe-disable-patch-dry-run",
        action="store_true",
        help="Disable patch dry-run validation (unsafe; not recommended)",
    )
    parser.add_argument("--json", action="store_true", help="Print result envelope JSON only")
    args = parser.parse_args()

    workspace = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    history_db_path = Path(workspace) / ".apos" / "history.sqlite3"
    orch = Orchestrator(
        workspace_root=workspace,
        history_db_path=history_db_path,
        enable_snapshots=args.enable_snapshots,
        fail_on_snapshot_error=not args.continue_on_snapshot_error,
        snapshot_auto_init_git=args.snapshot_auto_init_git,
        enable_command_policy=not args.unsafe_disable_command_policy,
        enable_patch_dry_run=not args.unsafe_disable_patch_dry_run,
    )
    orch.start()

    if not args.json:
        print("Orchestrator started. Submitting demo task...")
        print(f"History DB: {history_db_path}")
        print(f"Snapshots enabled: {args.enable_snapshots}")
        print(f"Command policy enabled: {not args.unsafe_disable_command_policy}")
        print(f"Patch dry-run enabled: {not args.unsafe_disable_patch_dry_run}")
    task = demo_task(workspace)
    task_id = orch.submit_task(task)

    # wait for the task to complete
    time.sleep(2)
    envelope = orch.get_task_envelope(task_id)
    orch.stop()
    if args.json:
        print(json.dumps(envelope or {"task_id": task_id, "status": "pending"}, ensure_ascii=False))
    else:
        if envelope:
            print(
                "Result:",
                f"task_id={envelope.get('task_id')} status={envelope.get('status')} exit_code={envelope.get('exit_code')}",
            )
        print("Orchestrator stopped. Check history DB and .apos_suggestion_*.json files.")


if __name__ == "__main__":
    main()
