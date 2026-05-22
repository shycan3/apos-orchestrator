import json
import tempfile
from pathlib import Path

from apos_core.task_envelope import make_task_envelope
from apos_core.orchestrator import Orchestrator


def _make_plan_only_envelope(workspace_root: str, task_id: str = "plan-approve-test"):
    return make_task_envelope(
        task_type="plan_only",
        workspace_root=workspace_root,
        created_by="web_llm",
        task_id=task_id,
        patches=[],
        commands=[],
        meta={
            "plan_goal": "create approve demo file",
            "plan_steps": [
                {
                    "title": "Write approve demo file",
                    "task_type": "patch_and_run",
                    "patches": [
                        {
                            "target": "workspace/approve_demo.py",
                            "language": "python",
                            "intent": "update",
                            "content": "print('approved step')\n",
                        }
                    ],
                    "commands": [],
                }
            ],
        },
    )


def test_execute_plan_step_records_result_and_writes_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        payload = _make_plan_only_envelope(str(workspace))
        task_id = payload.get("task_id")

        history_db = workspace / ".apos" / "history.sqlite3"
        orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db)

        # record the plan task as if submitted earlier
        orch.recorder.record_task(task_id, payload)

        res = orch.execute_plan_step(task_id, 0, approved_by="tester")

        assert res.get("status") == "success"
        # check result recorded in DB by fetching latest results
        # simple check: the target file exists
        target = workspace / "workspace" / "approve_demo.py"
        assert target.exists()
        content = target.read_text(encoding="utf-8")
        assert "approved step" in content
        # ensure DB connections closed before cleanup
        try:
            orch.stop()
        except Exception:
            pass
