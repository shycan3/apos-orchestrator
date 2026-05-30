import json
import subprocess
import sys
import tempfile
from pathlib import Path

from apos_core.orchestrator import Orchestrator
from apos_core.task_envelope import make_task_envelope


REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_apos(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "cli/apos.py", *args],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def _make_plan_only_envelope(workspace_root: str, task_id: str = "plan-cli-flow"):
    return make_task_envelope(
        task_type="plan_only",
        workspace_root=workspace_root,
        created_by="web_llm",
        task_id=task_id,
        patches=[],
        commands=[],
        meta={
            "plan_goal": "exercise the plan lifecycle",
            "plan_steps": [
                {
                    "title": "Successful command step",
                    "task_type": "run",
                    "commands": [
                        {
                            "command": ["python", "-c", "print('step-0')"],
                            "timeout_seconds": 5,
                        }
                    ],
                },
                {
                    "title": "Rejected command step",
                    "task_type": "run",
                    "commands": [
                        {
                            "command": ["python", "-c", "print('step-1')"],
                            "timeout_seconds": 5,
                        }
                    ],
                },
                {
                    "title": "Failing multi-command step",
                    "task_type": "run",
                    "commands": [
                        {
                            "command": ["python", "-c", "print('first')"],
                            "timeout_seconds": 5,
                        },
                        {
                            "command": ["python", "-c", "raise SystemExit(4)"],
                            "timeout_seconds": 5,
                        },
                    ],
                },
            ],
        },
    )


def test_apos_plans_cli_covers_listing_detail_approval_and_execution():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = workspace / ".apos" / "history.sqlite3"

        payload = _make_plan_only_envelope(str(workspace))
        task_id = payload["task_id"]

        orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db)
        orch.recorder.record_task(task_id, payload)
        orch.stop()

        list_proc = _run_apos("plans", "list", "--workspace", str(workspace), "--json", cwd=REPO_ROOT)
        assert list_proc.returncode == 0, list_proc.stderr
        plans = json.loads(list_proc.stdout)
        assert any(item["task_id"] == task_id for item in plans)

        show_proc = _run_apos("plans", "show", task_id, "--workspace", str(workspace), "--json", cwd=REPO_ROOT)
        assert show_proc.returncode == 0, show_proc.stderr
        plan_detail = json.loads(show_proc.stdout)
        assert plan_detail["task_id"] == task_id
        assert plan_detail["step_count"] == 3
        assert [step["title"] for step in plan_detail["steps"]] == [
            "Successful command step",
            "Rejected command step",
            "Failing multi-command step",
        ]

        steps_proc = _run_apos("plans", "steps", task_id, "--workspace", str(workspace), "--json", cwd=REPO_ROOT)
        assert steps_proc.returncode == 0, steps_proc.stderr
        steps = json.loads(steps_proc.stdout)
        assert len(steps) == 3

        approve_proc = _run_apos(
            "plans",
            "approve-step",
            task_id,
            "0",
            "--workspace",
            str(workspace),
            "--approved-by",
            "tester",
            "--json",
            cwd=REPO_ROOT,
        )
        assert approve_proc.returncode == 0, approve_proc.stderr
        approved_item = json.loads(approve_proc.stdout)
        assert approved_item["status"] == "approved"
        assert approved_item["step_index"] == 0

        run_proc = _run_apos(
            "plans",
            "run-step",
            task_id,
            "0",
            "--workspace",
            str(workspace),
            "--approved-by",
            "tester",
            "--json",
            cwd=REPO_ROOT,
        )
        assert run_proc.returncode == 0, run_proc.stderr
        run_result = json.loads(run_proc.stdout)
        assert run_result["status"] == "success"
        assert run_result["meta"]["plan_step_index"] == 0
        assert run_result["meta"]["command_results"][0]["exit_code"] == 0
        assert "step-0" in run_result["meta"]["command_results"][0]["stdout"]

        reject_proc = _run_apos(
            "plans",
            "reject-step",
            task_id,
            "1",
            "--workspace",
            str(workspace),
            "--rejected-by",
            "tester",
            "--reason",
            "not needed",
            "--json",
            cwd=REPO_ROOT,
        )
        assert reject_proc.returncode == 0, reject_proc.stderr
        rejected_item = json.loads(reject_proc.stdout)
        assert rejected_item["status"] == "rejected"
        assert rejected_item["decision_reason"] == "not needed"

        plan_detail_after_reject = json.loads(
            _run_apos("plans", "show", task_id, "--workspace", str(workspace), "--json", cwd=REPO_ROOT).stdout
        )
        assert plan_detail_after_reject["steps"][1]["status"] == "rejected"

        failing_approve = _run_apos(
            "plans",
            "approve-step",
            task_id,
            "2",
            "--workspace",
            str(workspace),
            "--approved-by",
            "tester",
            "--json",
            cwd=REPO_ROOT,
        )
        assert failing_approve.returncode == 0, failing_approve.stderr

        fail_proc = _run_apos(
            "plans",
            "run-step",
            task_id,
            "2",
            "--workspace",
            str(workspace),
            "--approved-by",
            "tester",
            "--json",
            cwd=REPO_ROOT,
        )
        assert fail_proc.returncode == 0, fail_proc.stderr
        fail_result = json.loads(fail_proc.stdout)
        assert fail_result["status"] == "failed"
        assert len(fail_result["meta"]["command_results"]) == 2
        assert fail_result["meta"]["command_results"][0]["exit_code"] == 0
        assert fail_result["meta"]["command_results"][1]["exit_code"] == 4

        rerun_proc = _run_apos(
            "plans",
            "run-step",
            task_id,
            "0",
            "--workspace",
            str(workspace),
            "--approved-by",
            "tester",
            "--json",
            cwd=REPO_ROOT,
        )
        assert rerun_proc.returncode == 0, rerun_proc.stderr
        rerun_result = json.loads(rerun_proc.stdout)
        assert rerun_result["status"] == "skipped"

        forced_rerun_proc = _run_apos(
            "plans",
            "run-step",
            task_id,
            "0",
            "--workspace",
            str(workspace),
            "--approved-by",
            "tester",
            "--force",
            "--json",
            cwd=REPO_ROOT,
        )
        assert forced_rerun_proc.returncode == 0, forced_rerun_proc.stderr
        forced_rerun_result = json.loads(forced_rerun_proc.stdout)
        assert forced_rerun_result["status"] == "success"


def test_apos_plans_cli_rejects_invalid_identifiers():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = workspace / ".apos" / "history.sqlite3"

        payload = _make_plan_only_envelope(str(workspace))
        task_id = payload["task_id"]

        orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db)
        orch.recorder.record_task(task_id, payload)
        orch.stop()

        missing_task_proc = _run_apos(
            "plans",
            "run-step",
            "missing-task",
            "0",
            "--workspace",
            str(workspace),
            "--json",
            cwd=REPO_ROOT,
        )
        assert missing_task_proc.returncode != 0
        assert "plan step not runnable" in missing_task_proc.stderr

        invalid_step_proc = _run_apos(
            "plans",
            "run-step",
            task_id,
            "99",
            "--workspace",
            str(workspace),
            "--json",
            cwd=REPO_ROOT,
        )
        assert invalid_step_proc.returncode != 0
        assert "plan step not runnable" in invalid_step_proc.stderr