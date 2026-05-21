import json
import sqlite3
import tempfile
from pathlib import Path
import subprocess
import sys

from apos_core.orchestrator import Orchestrator
from apos_core.task_envelope import make_task_envelope, validate_task_envelope


def _fetch_result_envelope(db_path: Path, task_id: str):
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("SELECT result_envelope FROM results WHERE task_id = ? ORDER BY timestamp DESC LIMIT 1", (task_id,))
    row = c.fetchone()
    conn.close()
    return json.loads(row[0]) if row and row[0] else None


def test_task_envelope_validation_success():
    env = make_task_envelope(
        task_type="patch_and_run",
        workspace_root="C:/tmp/workspace",
        created_by="web_llm",
        patches=[
            {
                "target": "workspace/hello.py",
                "language": "python",
                "content": "print('x')\n",
                "intent": "update",
                "description": "demo",
            }
        ],
        commands=[
            {
                "command": ["python", "workspace/hello.py"],
                "description": "run demo",
                "expected_result": "prints x",
                "timeout_seconds": 5,
            }
        ],
        meta={"k": "v"},
    )
    res = validate_task_envelope(env)
    assert res["ok"] is True


def test_task_envelope_validation_missing_required_field():
    env = {"schema_version": "1.0"}
    res = validate_task_envelope(env)
    assert res["ok"] is False


def test_validation_failed_status_when_running_invalid_envelope():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "ws"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = root / "hist" / "history.sqlite3"

        invalid_env = {"schema_version": "1.0"}

        orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db)
        orch.start()
        result = orch.run_task_envelope(invalid_env)
        orch.stop()

        assert result["status"] == "validation_failed"
        assert result["exit_code"] == -6


def test_task_envelope_invalid_task_type_blocked():
    env = make_task_envelope(task_type="invalid", workspace_root="C:/tmp/workspace")
    res = validate_task_envelope(env)
    assert res["ok"] is False


def test_task_envelope_invalid_patches_type_blocked():
    env = make_task_envelope(task_type="run", workspace_root="C:/tmp/workspace")
    env["patches"] = {"bad": True}
    res = validate_task_envelope(env)
    assert res["ok"] is False


def test_task_envelope_invalid_commands_type_blocked():
    env = make_task_envelope(task_type="run", workspace_root="C:/tmp/workspace")
    env["commands"] = {"bad": True}
    res = validate_task_envelope(env)
    assert res["ok"] is False


def test_task_envelope_run_success_generates_result_envelope():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "ws"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = root / "hist" / "history.sqlite3"

        env = make_task_envelope(
            task_type="patch_and_run",
            workspace_root=str(workspace),
            task_id="task-env-success",
            patches=[
                {
                    "target": "workspace/hello.py",
                    "language": "python",
                    "content": "print('hello')\n",
                    "intent": "update",
                    "description": "demo",
                }
            ],
            commands=[
                {
                    "command": ["python", "workspace/hello.py"],
                    "description": "run",
                    "expected_result": "hello",
                    "timeout_seconds": 5,
                }
            ],
        )

        orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db)
        orch.start()
        result = orch.run_task_envelope(env)
        orch.stop()

        assert result["status"] == "success"
        assert result["schema_version"]
        assert result["task_id"] == "task-env-success"
        assert json.dumps(result)

        saved = _fetch_result_envelope(history_db, "task-env-success")
        assert saved is not None
        assert saved["status"] == "success"


def test_task_envelope_patch_blocked_stops_execution():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "ws"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = root / "hist" / "history.sqlite3"

        env = make_task_envelope(
            task_type="patch_and_run",
            workspace_root=str(workspace),
            task_id="task-env-patch-blocked",
            patches=[
                {
                    "target": ".env",
                    "language": "text",
                    "content": "SECRET=1\n",
                    "intent": "update",
                    "description": "should block",
                }
            ],
            commands=[
                {
                    "command": ["python", "-c", "print('no')"],
                    "description": "run",
                    "expected_result": "no",
                    "timeout_seconds": 5,
                }
            ],
        )

        orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db)
        orch.start()
        result = orch.run_task_envelope(env)
        orch.stop()
        assert result["status"] == "patch_blocked"


def test_task_envelope_command_blocked_generates_envelope():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "ws"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = root / "hist" / "history.sqlite3"

        env = make_task_envelope(
            task_type="run",
            workspace_root=str(workspace),
            task_id="task-env-cmd-blocked",
            commands=[
                {
                    "command": ["rm", "-rf", "."],
                    "description": "blocked",
                    "expected_result": "blocked",
                    "timeout_seconds": 5,
                }
            ],
        )

        orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db)
        orch.start()
        result = orch.run_task_envelope(env)
        orch.stop()
        assert result["status"] == "command_blocked"
        assert result["policy_blocked"] is True


def test_example_task_target_and_command_path_match():
    example_path = Path("examples/task_patch_and_run.json")
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    target = payload["patches"][0]["target"]
    cmd = payload["commands"][0]["command"]

    assert target == "workspace/hello.py"
    assert isinstance(cmd, list)
    assert len(cmd) >= 2
    assert cmd[1] == target


def test_run_orchestrator_json_patch_preview_target_is_workspace_hello():
    cmd = [sys.executable, "cli/run_orchestrator.py", "--json"]
    proc = subprocess.run(
        cmd,
        cwd=".",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout.strip())
    preview = payload.get("patch_preview") or []
    assert len(preview) >= 1
    assert preview[0]["target"] == "workspace/hello.py"
