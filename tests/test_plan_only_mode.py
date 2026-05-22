import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from apos_core.orchestrator import Orchestrator
from apos_core.task_envelope import make_task_envelope, validate_task_envelope


def _fetch_result_envelope(db_path: Path, task_id: str):
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("SELECT result_envelope FROM results WHERE task_id = ? ORDER BY timestamp DESC LIMIT 1", (task_id,))
    row = c.fetchone()
    conn.close()
    return json.loads(row[0]) if row and row[0] else None


def _make_plan_only_envelope(workspace_root: str, task_id: str = "plan-only-demo"):
    return make_task_envelope(
        task_type="plan_only",
        workspace_root=workspace_root,
        created_by="web_llm",
        task_id=task_id,
        patches=[],
        commands=[],
        meta={
            "plan_goal": "update the demo file without executing it",
            "plan_steps": [
                {
                    "title": "Draft the file change",
                    "task_type": "patch_and_run",
                    "patches": [
                        {
                            "target": "workspace/plan_only_demo.py",
                            "language": "python",
                            "intent": "update",
                            "content": "print('planned change')\n",
                            "description": "Prepare file update",
                        }
                    ],
                    "commands": [],
                },
                {
                    "title": "Confirm the result",
                    "task_type": "run",
                    "commands": [
                        {
                            "command": [sys.executable, "-c", "print('plan review')"],
                            "description": "Show the planned follow-up",
                            "timeout_seconds": 5,
                        }
                    ],
                },
            ],
        },
    )


def test_plan_only_validation_accepts_step_plan():
    env = _make_plan_only_envelope("C:/tmp/workspace")
    res = validate_task_envelope(env)
    assert res["ok"] is True


def test_cli_validate_only_accepts_plan_only(tmp_path: Path):
    task_file = tmp_path / "plan_only.json"
    payload = _make_plan_only_envelope(str(tmp_path))
    task_file.write_text(json.dumps(payload), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "cli/run_task.py", str(task_file), "--validate-only", "--json"],
        cwd=Path(__file__).resolve().parent.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["status"] == "success"


def test_orchestrator_plan_only_returns_plan_summary_without_execution():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = root / "hist" / "history.sqlite3"
        demo_file = workspace / "plan_only_demo.py"
        demo_file.write_text("print('original')\n", encoding="utf-8")

        env = _make_plan_only_envelope(str(workspace), task_id="plan-only-run")

        orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db)
        orch.start()
        result = orch.run_task_envelope(env)
        orch.stop()

        assert result["status"] == "success"
        assert result["exit_code"] == 0
        assert result["meta"]["task_type"] == "plan_only"
        assert result["meta"]["plan"]["step_count"] == 2
        assert result["meta"]["plan"]["plan_goal"] == "update the demo file without executing it"
        assert result["patch_applied"] is False
        assert demo_file.read_text(encoding="utf-8") == "print('original')\n"

        saved = _fetch_result_envelope(history_db, "plan-only-run")
        assert saved is not None
        assert saved["meta"]["task_type"] == "plan_only"
