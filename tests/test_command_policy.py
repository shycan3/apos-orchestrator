import sqlite3
import tempfile
import time
from pathlib import Path

from apos_core.executor import Executor
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


def test_allowed_python_command_executes():
    with tempfile.TemporaryDirectory() as tmp:
        ex = Executor(workspace_root=tmp)
        result = ex.run_command(["python", "-c", "print('ok-policy')"], cwd=tmp, timeout=5)
        assert result["policy_blocked"] is False
        assert result["exit_code"] == 0
        assert "ok-policy" in result["stdout"]


def test_dangerous_command_is_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        ex = Executor(workspace_root=tmp)
        result = ex.run_command(["rm", "-rf", "."], cwd=tmp, timeout=5)
        assert result["policy_blocked"] is True
        assert result["exit_code"] == -3
        assert result["blocked_reason"]


def test_shell_injection_patterns_are_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        ex = Executor(workspace_root=tmp)
        r1 = ex.run_command("python ok.py && del important.txt", cwd=tmp, timeout=5)
        r2 = ex.run_command("python ok.py ; rm -rf .", cwd=tmp, timeout=5)
        assert r1["policy_blocked"] is True
        assert r2["policy_blocked"] is True
        assert r1["blocked_reason"]
        assert r2["blocked_reason"]


def test_blocked_command_recorded_in_orchestrator_db():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = tmp_path / "hist" / "history.sqlite3"

        orch = Orchestrator(workspace_root=workspace, history_db_path=history_db, enable_command_policy=True)
        orch.start()
        task_id = "blocked-task"
        orch.submit_task({"id": task_id, "command": ["rm", "-rf", "."], "timeout": 5})
        assert _wait_for_result(history_db, task_id)
        orch.stop()

        conn = sqlite3.connect(str(history_db))
        c = conn.cursor()
        c.execute("SELECT policy_blocked, blocked_reason, meta FROM results WHERE task_id = ?", (task_id,))
        row = c.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == 1
        assert row[1]
        assert "policy_blocked" in (row[2] or "")
