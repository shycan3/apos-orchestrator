import json
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


def test_relative_path_patch_allowed_and_create_preview():
    with tempfile.TemporaryDirectory() as tmp:
        ex = Executor(workspace_root=tmp)
        previews = ex.preview_patch([
            {"path": "workspace/new_file.py", "action": "create", "content": "print('x')\n"}
        ])
        p = previews[0]
        assert p["policy_allowed"] is True
        assert p["operation"] == "create"
        assert p["exists"] is False


def test_overwrite_preview_for_existing_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "workspace" / "a.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("print('old')\n", encoding="utf-8")

        ex = Executor(workspace_root=tmp)
        previews = ex.preview_patch([
            {"path": "workspace/a.py", "action": "create", "content": "print('new')\n"}
        ])
        p = previews[0]
        assert p["policy_allowed"] is True
        assert p["operation"] == "overwrite"
        assert p["exists"] is True


def test_block_absolute_path_patch():
    with tempfile.TemporaryDirectory() as tmp:
        ex = Executor(workspace_root=tmp)
        abs_target = str((Path(tmp) / "workspace" / "abs.py").resolve())
        p = ex.preview_patch([{"path": abs_target, "action": "modify", "content": "x\n"}])[0]
        assert p["policy_allowed"] is False
        assert p["patch_blocked"] is True


def test_block_path_traversal_patch():
    with tempfile.TemporaryDirectory() as tmp:
        ex = Executor(workspace_root=tmp)
        p = ex.preview_patch([{"path": "../escape.py", "action": "modify", "content": "x\n"}])[0]
        assert p["policy_allowed"] is False
        assert p["patch_blocked"] is True


def test_block_protected_paths_env_git_sqlite():
    with tempfile.TemporaryDirectory() as tmp:
        ex = Executor(workspace_root=tmp)
        paths = [".env", ".git/config", "workspace/data.sqlite3"]
        previews = ex.preview_patch([{"path": p, "action": "modify", "content": "x\n"} for p in paths])
        assert all(not p["policy_allowed"] for p in previews)


def test_block_root_hello_patch_by_allowlist():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ex = Executor(workspace_root=tmp)

        preview = ex.preview_patch([
            {"path": "hello.py", "action": "modify", "content": "print('root')\n"}
        ])[0]
        assert preview["policy_allowed"] is False
        assert preview["blocked_reason"] == "path_not_in_allowlist"

        result = ex.apply_patch([
            {"path": "hello.py", "action": "modify", "content": "print('root')\n"}
        ])
        assert result[0]["patch_blocked"] is True
        assert not (root / "hello.py").exists()


def test_blocked_patch_does_not_write_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ex = Executor(workspace_root=tmp)
        result = ex.apply_patch([
            {"path": ".env", "action": "modify", "content": "SECRET=1\n"}
        ])
        assert result[0]["patch_blocked"] is True
        assert not (root / ".env").exists()


def test_orchestrator_records_blocked_patch_result():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        workspace = tmp_path / "ws"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = tmp_path / "hist" / "history.sqlite3"

        orch = Orchestrator(
            workspace_root=workspace,
            history_db_path=history_db,
            enable_patch_dry_run=True,
        )
        orch.start()
        task_id = "blocked-patch-task"
        orch.submit_task(
            {
                "id": task_id,
                "patches": [{"path": ".env", "action": "modify", "content": "SECRET=1\n"}],
                "command": ["python", "-c", "print('should_not_run')"],
                "timeout": 5,
            }
        )
        assert _wait_for_result(history_db, task_id)
        orch.stop()

        conn = sqlite3.connect(str(history_db))
        c = conn.cursor()
        c.execute(
            "SELECT exit_code, patch_blocked, patch_blocked_reason, patch_preview FROM results WHERE task_id = ?",
            (task_id,),
        )
        row = c.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == -4
        assert row[1] == 1
        assert row[2]
        parsed = json.loads(row[3])
        assert "items" in parsed
