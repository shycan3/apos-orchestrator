import json
import subprocess
import sys
import tempfile
from pathlib import Path

from apos_core.executor import Executor
from apos_core.task_envelope import make_task_envelope, validate_task_envelope


def test_search_and_replace_preview_and_apply_success():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "workspace" / "example.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("def greet():\n    print('hello')\n", encoding="utf-8")

        ex = Executor(workspace_root=tmp)
        preview = ex.preview_patch([
            {
                "path": "workspace/example.py",
                "action": "search_and_replace",
                "search": "print('hello')",
                "replace": "print('hello from search replace')",
            }
        ])[0]

        assert preview["operation"] == "search_and_replace"
        assert preview["policy_allowed"] is True
        assert preview["patch_blocked"] is False
        assert preview["search_match_count"] == 1
        assert preview["exists"] is True
        assert preview["diff_summary"] == "search_and_replace: matches=1, old_lines=2, new_lines=2"

        result = ex.apply_patch([
            {
                "path": "workspace/example.py",
                "action": "search_and_replace",
                "search": "print('hello')",
                "replace": "print('hello from search replace')",
            }
        ])[0]

        assert result["status"] == "search_and_replace_applied"
        assert result["patch_blocked"] is False
        assert result["search_match_count"] == 1
        assert target.read_text(encoding="utf-8") == "def greet():\n    print('hello from search replace')\n"


def test_search_and_replace_blocks_zero_matches_and_does_not_write():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "workspace" / "example.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("def greet():\n    print('hello')\n", encoding="utf-8")

        ex = Executor(workspace_root=tmp)
        result = ex.apply_patch([
            {
                "path": "workspace/example.py",
                "action": "search_and_replace",
                "search": "print('missing')",
                "replace": "print('replacement')",
            }
        ])[0]

        assert result["status"] == "blocked"
        assert result["patch_blocked"] is True
        assert result["search_match_count"] == 0
        assert target.read_text(encoding="utf-8") == "def greet():\n    print('hello')\n"


def test_search_and_replace_blocks_multiple_matches():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "workspace" / "example.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("print('hello')\nprint('hello')\n", encoding="utf-8")

        ex = Executor(workspace_root=tmp)
        preview = ex.preview_patch([
            {
                "path": "workspace/example.py",
                "action": "search_and_replace",
                "search": "print('hello')",
                "replace": "print('hello from search replace')",
            }
        ])[0]

        assert preview["patch_blocked"] is True
        assert preview["search_match_count"] == 2
        assert preview["blocked_reason"] == "search matched multiple times"


def test_search_and_replace_blocks_empty_search():
    with tempfile.TemporaryDirectory() as tmp:
        ex = Executor(workspace_root=tmp)
        preview = ex.preview_patch([
            {
                "path": "workspace/example.py",
                "action": "search_and_replace",
                "search": "",
                "replace": "print('hello from search replace')",
            }
        ])[0]

        assert preview["patch_blocked"] is True
        assert preview["blocked_reason"] == "search must be a non-empty string"


def test_search_and_replace_blocks_missing_target():
    with tempfile.TemporaryDirectory() as tmp:
        ex = Executor(workspace_root=tmp)
        preview = ex.preview_patch([
            {
                "path": "workspace/missing.py",
                "action": "search_and_replace",
                "search": "print('hello')",
                "replace": "print('hello from search replace')",
            }
        ])[0]

        assert preview["patch_blocked"] is True
        assert preview["blocked_reason"] == "target file does not exist"
        assert preview["search_match_count"] == 0


def test_search_and_replace_respects_patch_policy():
    with tempfile.TemporaryDirectory() as tmp:
        ex = Executor(workspace_root=tmp)
        preview = ex.preview_patch([
            {
                "path": ".env",
                "action": "search_and_replace",
                "search": "SECRET=1",
                "replace": "SECRET=2",
            }
        ])[0]

        assert preview["policy_allowed"] is False
        assert preview["patch_blocked"] is True
        assert preview["blocked_reason"]


def test_validate_task_envelope_allows_search_and_replace_without_content():
    env = make_task_envelope(
        task_type="patch_and_run",
        workspace_root="C:/tmp/workspace",
        created_by="web_llm",
        patches=[
            {
                "target": "workspace/example.py",
                "language": "python",
                "intent": "search_and_replace",
                "search": "print('hello')",
                "replace": "print('hello from APOS')",
                "description": "Update printed message",
            }
        ],
        commands=[],
        meta={"source": "test"},
    )

    res = validate_task_envelope(env)
    assert res["ok"] is True


def test_cli_validate_only_accepts_search_and_replace(tmp_path: Path):
    task_file = tmp_path / "task.json"
    payload = make_task_envelope(
        task_type="patch_and_run",
        workspace_root=str(tmp_path),
        created_by="web_llm",
        patches=[
            {
                "target": "workspace/example.py",
                "language": "python",
                "intent": "search_and_replace",
                "search": "print('hello')",
                "replace": "print('hello from APOS')",
                "description": "Update printed message",
            }
        ],
        commands=[],
        meta={"source": "test"},
    )
    task_file.write_text(json.dumps(payload), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "cli/run_task.py", str(task_file), "--validate-only", "--json"],
        cwd=Path(__file__).resolve().parent.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["status"] == "success"