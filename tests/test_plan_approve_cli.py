import json
import subprocess
import sys
import tempfile
from pathlib import Path

from apos_core.task_envelope import make_task_envelope
from apos_core.orchestrator import Orchestrator


def _make_plan_only_envelope(workspace_root: str, task_id: str = "plan-approve-cli"):
    return make_task_envelope(
        task_type="plan_only",
        workspace_root=workspace_root,
        created_by="web_llm",
        task_id=task_id,
        patches=[],
        commands=[],
        meta={
            "plan_goal": "create a demo file for CLI approve",
            "plan_steps": [
                {
                    "title": "Write approve demo file via CLI",
                    "task_type": "patch_and_run",
                    "patches": [
                        {
                            "target": "workspace/approve_cli_demo.py",
                            "language": "python",
                            "intent": "update",
                            "content": "print('approved cli step')\n",
                        }
                    ],
                    "commands": [],
                }
            ],
        },
    )


def test_plan_approve_cli_logs_and_quiet_mode():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        payload = _make_plan_only_envelope(str(workspace))
        task_id = payload.get("task_id")

        history_db = workspace / ".apos" / "history.sqlite3"
        orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db)
        orch.recorder.record_task(task_id, payload)
        # close recorder in parent process to avoid locking
        orch.stop()

        log_file = root / "approve_log.jsonl"

        proc = subprocess.run(
            [
                sys.executable,
                "cli/plan_approve.py",
                task_id,
                "--workspace",
                str(workspace),
                "--step",
                "0",
                "--approved-by",
                "tester",
                "--quiet",
                "--log-file",
                str(log_file),
            ],
            cwd=Path(__file__).resolve().parent.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        assert proc.returncode == 0, proc.stderr
        # nothing printed to stdout because quiet
        assert proc.stdout.strip() == ""

        assert log_file.exists()
        data = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert data.get("status") == "success"
        assert "approve_cli_demo.py" in data.get("patch_preview")[0].get("path") or data.get("patch_applied")
