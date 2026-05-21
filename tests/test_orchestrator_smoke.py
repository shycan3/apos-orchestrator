import os
import sys
import time
import sqlite3
import tempfile
from pathlib import Path

from apos_core.orchestrator import Orchestrator


def wait_for_result(db_path: Path, task_id: str, timeout: float = 5.0):
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


def test_orchestrator_success_and_failure_flow_with_explicit_db_path():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        workspace_root = tmp_path / "workspace"
        other_cwd = tmp_path / "other_cwd"
        history_db_path = tmp_path / "history_store" / "history.sqlite3"

        workspace_root.mkdir(parents=True, exist_ok=True)
        other_cwd.mkdir(parents=True, exist_ok=True)

        cwd = os.getcwd()
        try:
            # Keep cwd different from workspace_root to verify DB path stability
            os.chdir(str(other_cwd))

            orch = Orchestrator(
                workspace_root=str(workspace_root),
                history_db_path=str(history_db_path),
            )
            orch.start()

            # 1) success case: write a python file and run it in workspace
            task1 = {
                "id": "t-success",
                "patches": [{"path": "workspace/hello.py", "action": "modify", "content": "print('ok-success')\n"}],
                "command": [sys.executable, "workspace/hello.py"],
                "timeout": 5,
            }
            orch.submit_task(task1)
            assert wait_for_result(history_db_path, "t-success", timeout=5.0)

            # 2) failure case: run a command that exits non-zero
            task2 = {
                "id": "t-fail",
                "command": [sys.executable, "-c", "import sys; sys.exit(3)"],
                "timeout": 5,
            }
            orch.submit_task(task2)
            assert wait_for_result(history_db_path, "t-fail", timeout=5.0)

            orch.stop()

            # verify explicit DB path is used and records exist
            assert history_db_path.exists()
            conn = sqlite3.connect(str(history_db_path))
            c = conn.cursor()
            c.execute("SELECT task_id, exit_code, stdout, stderr FROM results")
            rows = c.fetchall()
            conn.close()

            assert any(r[0] == "t-success" for r in rows)
            assert any(r[0] == "t-fail" for r in rows)

            # Ensure default DB path in cwd is not accidentally created
            assert not (other_cwd / ".apos_history.sqlite3").exists()

        finally:
            os.chdir(cwd)
