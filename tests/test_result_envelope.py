import json
import sqlite3
import tempfile
import time
from pathlib import Path

from apos_core.orchestrator import Orchestrator


def _wait_for_result(db_path: Path, task_id: str, timeout: float = 5.0):
    start = time.time()
    while time.time() - start < timeout:
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            c = conn.cursor()
            c.execute("SELECT COUNT(1) FROM results WHERE task_id = ?", (task_id,))
            row = c.fetchone()
            conn.close()
            if row and row[0] > 0:
                return True
        time.sleep(0.1)
    return False


def _fetch_envelope(db_path: Path, task_id: str):
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("SELECT result_envelope FROM results WHERE task_id = ? ORDER BY timestamp DESC LIMIT 1", (task_id,))
    row = c.fetchone()
    conn.close()
    assert row is not None and row[0] is not None
    return json.loads(row[0])


def test_success_envelope_created_and_serializable():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = root / "hist" / "history.sqlite3"

        orch = Orchestrator(workspace_root=workspace, history_db_path=history_db)
        orch.start()
        task_id = "env-success"
        orch.submit_task(
            {
                "id": task_id,
                "patches": [{"path": "workspace/ok.py", "action": "modify", "content": "print('ok')\n"}],
                "command": ["python", "workspace/ok.py"],
                "timeout": 5,
            }
        )
        assert _wait_for_result(history_db, task_id)
        orch.stop()

        env = _fetch_envelope(history_db, task_id)
        assert env["schema_version"]
        assert env["task_id"] == task_id
        assert env["status"] == "success"
        json.dumps(env)


def test_command_blocked_envelope_created():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = root / "hist" / "history.sqlite3"

        orch = Orchestrator(workspace_root=workspace, history_db_path=history_db, enable_command_policy=True)
        orch.start()
        task_id = "env-command-blocked"
        orch.submit_task({"id": task_id, "command": ["rm", "-rf", "."], "timeout": 5})
        assert _wait_for_result(history_db, task_id)
        orch.stop()

        env = _fetch_envelope(history_db, task_id)
        assert env["status"] == "command_blocked"
        assert env["policy_blocked"] is True
        assert env["blocked_reason"]


def test_patch_blocked_envelope_created_and_saved():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = root / "hist" / "history.sqlite3"

        orch = Orchestrator(workspace_root=workspace, history_db_path=history_db, enable_patch_dry_run=True)
        orch.start()
        task_id = "env-patch-blocked"
        orch.submit_task(
            {
                "id": task_id,
                "patches": [{"path": ".env", "action": "modify", "content": "SECRET=1\n"}],
                "command": ["python", "-c", "print('never')"],
                "timeout": 5,
            }
        )
        assert _wait_for_result(history_db, task_id)
        orch.stop()

        env = _fetch_envelope(history_db, task_id)
        assert env["status"] == "patch_blocked"
        assert env["patch_blocked"] is True
        assert env["patch_blocked_reason"]
        assert "schema_version" in env and "task_id" in env and "status" in env
