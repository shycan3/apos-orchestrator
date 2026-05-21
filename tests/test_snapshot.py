import os
import sys
import time
import sqlite3
import tempfile
import subprocess
from pathlib import Path

from apos_core.snapshot import SnapshotManager
from apos_core.orchestrator import Orchestrator


def _git(cwd: Path, *args: str):
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def _prepare_git_repo(repo: Path):
    repo.mkdir(parents=True, exist_ok=True)
    assert _git(repo, "init").returncode == 0
    assert _git(repo, "config", "user.email", "apos@example.local").returncode == 0
    assert _git(repo, "config", "user.name", "APOS Test").returncode == 0


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


def test_snapshot_created_in_git_repository():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "repo"
        _prepare_git_repo(workspace)

        manager = SnapshotManager(workspace)
        result = manager.create_snapshot("task-1")

        assert result["ok"] is True
        assert result["snapshot_commit"] is not None


def test_snapshot_fails_safely_when_not_git_repo():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "no-repo"
        workspace.mkdir(parents=True, exist_ok=True)

        manager = SnapshotManager(workspace)
        result = manager.create_snapshot("task-2", auto_init=False)

        assert result["ok"] is False
        assert result["message"] == "git repository not available"


def test_orchestrator_enable_snapshots_false_keeps_execution_loop():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = tmp_path / "hist" / "history.sqlite3"

        orch = Orchestrator(
            workspace_root=workspace,
            history_db_path=history_db,
            enable_snapshots=False,
        )
        orch.start()
        task_id = "no-snapshot-task"
        orch.submit_task(
            {
                "id": task_id,
                "command": [sys.executable, "-c", "print('ok-no-snapshot')"],
                "timeout": 5,
            }
        )

        assert _wait_for_result(history_db, task_id)
        orch.stop()

        conn = sqlite3.connect(str(history_db))
        c = conn.cursor()
        c.execute("SELECT snapshot_commit FROM results WHERE task_id = ?", (task_id,))
        row = c.fetchone()
        conn.close()

        assert row is not None
        assert row[0] is None


def test_orchestrator_enable_snapshots_true_creates_snapshot_before_task():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        workspace = tmp_path / "workspace"
        _prepare_git_repo(workspace)
        history_db = tmp_path / "hist" / "history.sqlite3"

        orch = Orchestrator(
            workspace_root=workspace,
            history_db_path=history_db,
            enable_snapshots=True,
            fail_on_snapshot_error=True,
        )
        orch.start()
        task_id = "with-snapshot-task"
        orch.submit_task(
            {
                "id": task_id,
                "command": [sys.executable, "-c", "print('ok-with-snapshot')"],
                "timeout": 5,
            }
        )

        assert _wait_for_result(history_db, task_id)
        orch.stop()

        conn = sqlite3.connect(str(history_db))
        c = conn.cursor()
        c.execute("SELECT snapshot_commit FROM results WHERE task_id = ?", (task_id,))
        row = c.fetchone()
        conn.close()

        assert row is not None
        assert row[0] is not None
