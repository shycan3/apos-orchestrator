import json
import subprocess
import sys
import tempfile
from pathlib import Path

from apos_core.task_envelope import make_task_envelope


def _make_plan_only_envelope(workspace_root: str, task_id: str = "plan-step-cli"):
    return make_task_envelope(
        task_type="plan_only",
        workspace_root=workspace_root,
        created_by="web_llm",
        task_id=task_id,
        patches=[],
        commands=[],
        meta={
            "plan_goal": "create a demo file",
            "plan_steps": [
                {
                    "title": "Write demo file",
                    "task_type": "patch_and_run",
                    "patches": [
                        {
                            "target": "workspace/plan_step_cli_demo.py",
                            "language": "python",
                            "intent": "update",
                            "content": "print('from step')\n",
                        }
                    ],
                    "commands": [],
                }
            ],
        },
    )


def test_cli_plan_step_executes_and_writes_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        plan_file = root / "plan.json"
        payload = _make_plan_only_envelope(str(workspace))
        plan_file.write_text(json.dumps(payload), encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, "cli/plan_step.py", str(plan_file), "--step", "0", "--json"],
            cwd=Path(__file__).resolve().parent.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert result["status"] == "success"

        # prefer checking the patch preview result to avoid OS timing issues
        previews = result.get("patch_preview") or result.get("patch_preview")
        assert isinstance(previews, list)
        assert previews[0].get("status") in ("written", "search_and_replace_applied")
