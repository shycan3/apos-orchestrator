import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from apos_core.context_pack import ContextPackBuilder
from apos_core.recorder import Recorder


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_history(db_path: Path, task_id: str, status: str = "success") -> None:
    recorder = Recorder(db_path=db_path)
    try:
        recorder.record_task(task_id, {"id": task_id, "task_type": "patch_and_run", "patches": [], "commands": []})
        recorder.record_result(
            f"result-{task_id}",
            task_id,
            0,
            "stdout text",
            "",
            {"task_type": "patch_and_run"},
            result_envelope={
                "schema_version": "1.0",
                "task_id": task_id,
                "status": status,
                "exit_code": 0,
                "patch_blocked": False,
                "policy_blocked": False,
                "blocked_reason": "",
            },
        )
    finally:
        recorder.close()


def test_context_pack_excludes_protected_paths_and_includes_examples_and_history():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_text(root / "README.md", "# APOS\n")
        _write_text(root / "workspace" / "hello.py", "print('hello')\n")
        _write_text(root / "examples" / "sample.py", "print('example')\n")
        _write_text(root / "docs" / "notes.md", "docs note\n")
        _write_text(root / ".env", "SECRET=1\n")

        history_db = root / ".apos" / "history.sqlite3"
        _seed_history(history_db, "ctx-task-1", status="success")

        pack = ContextPackBuilder(root, history_db_path=history_db).build(max_depth=4, max_files=50)

        paths = [item["path"] for item in pack["current_files"]]
        assert "README.md" in paths
        assert "workspace/hello.py" in paths
        assert "examples/sample.py" in paths
        assert ".env" not in paths
        assert ".apos/history.sqlite3" not in paths

        assert pack["recent_history"]
        assert pack["recent_history"][0]["task_id"] == "ctx-task-1"
        assert pack["recent_history"][0]["status"] == "success"


def test_context_pack_cli_json_output(tmp_path: Path):
    _write_text(tmp_path / "README.md", "# APOS\n")
    _write_text(tmp_path / "workspace" / "hello.py", "print('hello')\n")
    history_db = tmp_path / ".apos" / "history.sqlite3"
    _seed_history(history_db, "ctx-task-cli", status="success")

    proc = subprocess.run(
        [
            sys.executable,
            "cli/context_pack.py",
            "--json",
            "--workspace-root",
            str(tmp_path),
            "--history-db",
            str(history_db),
        ],
        cwd=Path(__file__).resolve().parent.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["workspace_root"] == str(tmp_path.resolve())
    assert payload["recent_history"][0]["task_id"] == "ctx-task-cli"
    assert any(item["path"] == "workspace/hello.py" for item in payload["current_files"])