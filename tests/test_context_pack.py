import json
import subprocess
import sys
import tempfile
from pathlib import Path

from apos_core.context_pack import ContextPackBuilder
from apos_core.recorder import Recorder


REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_history(db_path: Path, task_id: str, *, status: str = "success") -> None:
    recorder = Recorder(db_path=db_path)
    try:
        task_payload = {
            "id": task_id,
            "task_type": "patch_and_run",
            "patches": [
                {
                    "target": "workspace/hello.py",
                    "language": "python",
                    "intent": "create",
                    "content": "print('hello')\n",
                }
            ],
            "commands": [],
        }
        recorder.record_task(task_id, task_payload)
        recorder.record_result(
            f"result-{task_id}",
            task_id,
            0 if status == "success" else -4,
            "stdout text",
            "stderr text" if status != "success" else "",
            {"task_type": "patch_and_run"},
            result_envelope={
                "schema_version": "1.0",
                "task_id": task_id,
                "status": status,
                "exit_code": 0 if status == "success" else -4,
                "patch_blocked": False,
                "policy_blocked": False,
                "blocked_reason": "",
            },
        )
    finally:
        recorder.close()


def _seed_approval_item(db_path: Path, item_id: str, task_id: str, target: str) -> None:
    recorder = Recorder(db_path=db_path)
    try:
        recorder.record_approval_item(
            item_id,
            task_id,
            "bridge_patch",
            "Review bridge patch",
            {"target": target, "patch_id": item_id},
            patch_id=item_id,
            workspace_root=str(db_path.parent.parent),
            target=target,
            status="pending",
        )
    finally:
        recorder.close()


def _build_demo_pack(root: Path) -> tuple[dict, Path]:
    _write_text(root / "README.md", "# APOS\n")
    _write_text(root / "workspace" / "hello.py", "print('hello')\n")
    _write_text(root / "workspace" / "secret_note.txt", "api_key = sk-test-12345\npassword = hunter2\n")
    _write_text(root / "workspace" / "large.txt", "line\n" * 12000)
    _write_text(root / "docs" / "notes.md", "docs note\n")
    _write_text(root / "project_updates" / "WORKLOG.md", "# APOS 작업 저널\n\n최종 업데이트: 2026-05-29\n\n### Browser Bridge 안정화\n- 브리지 검증 완료\n- 전체 테스트 63 passed\n")
    _write_text(root / "server" / "apos_server.py", "print('server')\n")
    _write_text(root / "extension" / "contentScript.js", "console.log('bridge')\n")
    _write_text(root / "random" / "ignore.py", "print('ignored')\n")
    _write_text(root / ".env", "SECRET=1\n")

    history_db = root / ".apos" / "history.sqlite3"
    _seed_history(history_db, "ctx-task-1", status="validation_failed")
    _seed_approval_item(history_db, "approval-item-1", "ctx-task-1", "workspace/hello.py")

    pack = ContextPackBuilder(root, history_db_path=history_db).build(max_depth=4, max_files=80)
    return pack, history_db


def _required_schema_keys(pack: dict) -> None:
    required_keys = {
        "schema_version",
        "project_name",
        "project_root",
        "project_root_visible",
        "generated_at",
        "allowed_roots",
        "protected_roots",
        "recent_worklog_summary",
        "available_flows",
        "approval_queue_summary",
        "recent_history_summary",
        "relevant_files",
        "file_summaries",
        "known_warnings",
        "next_recommended_actions",
    }
    assert required_keys.issubset(pack.keys())
    assert isinstance(pack["allowed_roots"], list)
    assert isinstance(pack["protected_roots"], list)
    assert isinstance(pack["relevant_files"], list)
    assert isinstance(pack["file_summaries"], list)
    assert isinstance(pack["known_warnings"], list)
    assert isinstance(pack["next_recommended_actions"], list)
    assert isinstance(pack["recent_worklog_summary"], dict)
    assert isinstance(pack["available_flows"], list)
    assert isinstance(pack["approval_queue_summary"], dict)
    assert isinstance(pack["recent_history_summary"], dict)


def test_context_pack_standard_schema_masks_and_filters():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pack, _ = _build_demo_pack(root)

        _required_schema_keys(pack)
        assert pack["project_name"] == root.name
        assert pack["project_root"] == str(root.resolve())
        assert pack["project_root_visible"] is True
        assert any(flow["name"] == "context_pack" for flow in pack["available_flows"])
        assert pack["recent_worklog_summary"]["entries"]
        assert pack["approval_queue_summary"]["pending_count"] == 1
        assert pack["recent_history_summary"]["status_counts"]["validation_failed"] == 1
        assert any("review" in action.lower() for action in pack["next_recommended_actions"])
        assert any("safe map" in warning.lower() for warning in pack["known_warnings"])

        relevant_paths = set(pack["relevant_files"])
        assert "README.md" in relevant_paths
        assert "workspace/hello.py" in relevant_paths
        assert "server/apos_server.py" in relevant_paths
        assert "extension/contentScript.js" in relevant_paths
        assert "random/ignore.py" not in relevant_paths
        assert ".env" not in relevant_paths

        summaries = {item["path"]: item for item in pack["file_summaries"]}
        assert summaries["workspace/secret_note.txt"]["summary"].count("<redacted>") >= 1
        assert summaries["workspace/large.txt"]["content_mode"] == "metadata_only"
        assert summaries["workspace/large.txt"]["preview_char_count"] == 0
        assert summaries["README.md"]["content_mode"] == "preview"
        assert "api_key" not in summaries["workspace/secret_note.txt"]["summary"].lower()


def test_context_pack_cli_build_and_inspect_output(tmp_path: Path):
    pack, history_db = _build_demo_pack(tmp_path)
    output_json = tmp_path / "context_pack.json"
    output_md = tmp_path / "context_pack.md"

    build_proc = subprocess.run(
        [
            sys.executable,
            "cli/apos.py",
            "context",
            "build",
            "--json",
            "--workspace-root",
            str(tmp_path),
            "--history-db",
            str(history_db),
            "--output",
            str(output_json),
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert build_proc.returncode == 0, build_proc.stderr
    payload = json.loads(build_proc.stdout)
    assert payload["project_root"] == str(tmp_path.resolve())
    assert output_json.exists()
    assert json.loads(output_json.read_text(encoding="utf-8"))["project_name"] == tmp_path.name

    inspect_proc = subprocess.run(
        [
            sys.executable,
            "cli/apos.py",
            "context",
            "inspect",
            "--format",
            "markdown",
            "--workspace-root",
            str(tmp_path),
            "--history-db",
            str(history_db),
            "--output",
            str(output_md),
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert inspect_proc.returncode == 0, inspect_proc.stderr
    markdown = inspect_proc.stdout
    assert "# APOS Context Pack" in markdown
    assert "## Project Snapshot" in markdown
    assert "## Current Safe Working Scope" in markdown
    assert "## Recent Changes" in markdown
    assert "## Approval Queue Summary" in markdown
    assert "## Relevant Files" in markdown
    assert "## Known Warnings" in markdown
    assert "## Recommended Next Prompt" in markdown
    assert output_md.exists()
    assert "APOS Context Pack" in output_md.read_text(encoding="utf-8")


def test_context_pack_cli_legacy_wrapper_json_output(tmp_path: Path):
    _, history_db = _build_demo_pack(tmp_path)

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
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["project_root"] == str(tmp_path.resolve())
    assert payload["recent_history_summary"]["total_count"] == 1
    assert any(path == "workspace/hello.py" for path in payload["relevant_files"])
