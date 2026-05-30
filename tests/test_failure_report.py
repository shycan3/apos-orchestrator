import json
import subprocess
import sys
import tempfile
from pathlib import Path

from apos_core.recorder import Recorder
from apos_core.report_builder import ReportBuilder
from server.list_approvals_endpoint import app as dashboard_app
from wsgiref.util import setup_testing_defaults
from io import BytesIO


REPO_ROOT = Path(__file__).resolve().parent.parent


def _call_wsgi(app, environ):
    setup_testing_defaults(environ)
    captured = []

    def start_response(status, headers):
        captured.append(status)
        captured.append(headers)

    body = b"".join(app(environ, start_response))
    return captured[0], dict(captured[1]), body


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_task_result(recorder: Recorder, task_id: str, payload: dict, result_envelope: dict, *, stdout: str = "", stderr: str = "") -> None:
    recorder.record_task(task_id, payload)
    recorder.record_result(
        f"result-{task_id}",
        task_id,
        result_envelope.get("exit_code"),
        stdout,
        stderr,
        {"task_type": payload.get("task_type", "")},
        result_envelope=result_envelope,
    )


def _build_workspace(root: Path) -> Path:
    _write_text(root / "README.md", "# Failure Report Demo\n")
    _write_text(root / "workspace" / "existing.py", "print('ok')\n")
    _write_text(root / "project_updates" / "WORKLOG.md", "# Worklog\n\n- failure report demo\n")
    history_db = root / ".apos" / "history.sqlite3"
    recorder = Recorder(db_path=history_db)
    try:
        _seed_task_result(
            recorder,
            "invalid-task",
            {"id": "invalid-task", "task_type": "patch_and_run", "patches": [], "commands": []},
            {
                "schema_version": "1.0",
                "task_id": "invalid-task",
                "status": "validation_failed",
                "exit_code": -6,
                "patch_blocked": False,
                "policy_blocked": False,
                "blocked_reason": "",
            },
            stderr="task_envelope_validation_failed",
        )
        _seed_task_result(
            recorder,
            "policy-task",
            {
                "id": "policy-task",
                "task_type": "run",
                "patches": [],
                "commands": [["curl", "https://example.invalid"]],
            },
            {
                "schema_version": "1.0",
                "task_id": "policy-task",
                "status": "rejected",
                "exit_code": 0,
                "patch_blocked": False,
                "policy_blocked": True,
                "blocked_reason": "policy blocked by rule",
            },
            stderr="policy blocked by rule",
        )
        recorder.record_approval_item(
            "policy-approval",
            "policy-task",
            "bridge_patch",
            "Policy approval rejected",
            {"target": "workspace/existing.py", "patch_id": "policy-approval"},
            patch_id="policy-approval",
            workspace_root=str(root),
            target="workspace/existing.py",
            status="rejected",
            decision_reason="policy blocked by rule",
        )
        _seed_task_result(
            recorder,
            "command-task",
            {
                "id": "command-task",
                "task_type": "run",
                "patches": [],
                "commands": [["python", "-m", "pytest"]],
            },
            {
                "schema_version": "1.0",
                "task_id": "command-task",
                "status": "command_blocked",
                "exit_code": -3,
                "patch_blocked": False,
                "policy_blocked": True,
                "blocked_reason": "command policy blocked",
            },
            stderr="command policy blocked",
        )
        _seed_task_result(
            recorder,
            "missing-file-task",
            {
                "id": "missing-file-task",
                "task_type": "patch_and_run",
                "patches": [{"target": "workspace/missing.py", "language": "python", "intent": "update", "content": "print('x')\n"}],
                "commands": [],
            },
            {
                "schema_version": "1.0",
                "task_id": "missing-file-task",
                "status": "patch_blocked",
                "exit_code": -4,
                "patch_blocked": True,
                "patch_blocked_reason": "target file does not exist",
                "policy_blocked": False,
                "blocked_reason": "target file does not exist",
            },
            stderr="target file does not exist",
        )
        _seed_task_result(
            recorder,
            "stale-task",
            {
                "id": "stale-task",
                "task_type": "patch_and_run",
                "patches": [{"target": "workspace/existing.py", "language": "python", "intent": "update", "content": "print('y')\n"}],
                "commands": [],
            },
            {
                "schema_version": "1.0",
                "task_id": "stale-task",
                "status": "failed",
                "exit_code": 0,
                "patch_blocked": False,
                "policy_blocked": False,
                "blocked_reason": "",
            },
            stderr="stale context suspected",
        )
        _seed_task_result(
            recorder,
            "test-task",
            {
                "id": "test-task",
                "task_type": "run",
                "patches": [],
                "commands": [["python", "-m", "pytest"]],
            },
            {
                "schema_version": "1.0",
                "task_id": "test-task",
                "status": "failed",
                "exit_code": 1,
                "patch_blocked": False,
                "policy_blocked": False,
                "blocked_reason": "",
            },
            stdout="==================\nFAIL: test\n",
            stderr="assertion failed",
        )
        recorder.record_approval_item(
            "approval-pending-old",
            "approval-task",
            "bridge_patch",
            "Review bridge patch",
            {"target": "workspace/existing.py", "patch_id": "approval-pending-old"},
            patch_id="approval-pending-old",
            workspace_root=str(root),
            target="workspace/existing.py",
            status="pending",
        )
    finally:
        recorder.close()
    return history_db


def test_failure_report_classifies_and_summarizes_failures(tmp_path: Path):
    history_db = _build_workspace(tmp_path)
    builder = ReportBuilder(tmp_path, history_db_path=history_db)
    try:
        report = builder.build_failure_report(limit=10)
        causes = set(report["likely_causes"])
        assert "invalid_envelope (1)" in causes or any(item.startswith("invalid_envelope") for item in causes)
        assert any(item.startswith("policy_denied") for item in causes)
        assert any(item.startswith("command_denied") for item in causes)
        assert any(item.startswith("missing_file") for item in causes)
        assert any(item.startswith("stale_context_possible") for item in causes)
        assert any(item.startswith("test_failed") for item in causes)
        assert report["summary"]
        assert report["recommended_human_action"]
        assert report["recommended_llm_prompt"]

        markdown = builder.render_markdown(report)
        assert "## Summary" in markdown
        assert "## Recent Failures" in markdown
        assert "## Likely Causes" in markdown
        assert "## Affected Files" in markdown
        assert "## Stale Context Signals" in markdown
        assert "## Recommended Human Action" in markdown
        assert "## Recommended LLM Prompt" in markdown
        assert "task_envelope_validation_failed" in markdown
        assert "command policy blocked" in markdown
        assert "stale context suspected" in markdown
    finally:
        builder.close()


def test_failure_report_cli_and_next_prompt(tmp_path: Path):
    history_db = _build_workspace(tmp_path)
    output_md = tmp_path / "failure_report.md"

    proc = subprocess.run(
        [
            sys.executable,
            "cli/apos.py",
            "report",
            "failures",
            "--workspace",
            str(tmp_path),
            "--history-db",
            str(history_db),
            "--limit",
            "10",
            "--format",
            "markdown",
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "# APOS Failure / Drift Report" in proc.stdout
    assert "## Recent Failures" in proc.stdout
    assert "## Recommended LLM Prompt" in proc.stdout

    output_md.write_text(proc.stdout, encoding="utf-8")
    assert output_md.read_text(encoding="utf-8").startswith("# APOS Failure / Drift Report")

    prompt_proc = subprocess.run(
        [
            sys.executable,
            "cli/apos.py",
            "report",
            "next-prompt",
            "--workspace",
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
    assert prompt_proc.returncode == 0, prompt_proc.stderr
    assert prompt_proc.stdout.strip()
    assert "Please" in prompt_proc.stdout or "review" in prompt_proc.stdout.lower()


def test_drift_report_detects_changed_files_and_pending_items(tmp_path: Path):
    history_db = _build_workspace(tmp_path)
    builder = ReportBuilder(tmp_path, history_db_path=history_db)
    try:
        context_pack = builder.context_builder.build(max_recent_history=5, max_pending_approvals=5)
        _write_text(tmp_path / "workspace" / "existing.py", "print('changed')\n")
        drift = builder.build_drift_report(context_pack=context_pack, limit=5)
        assert isinstance(drift["drift_warning"], bool)
        assert drift["drift_warning"] is True
        assert drift["stale_context_signals"]
        assert drift["recommended_human_action"]
        assert drift["recommended_llm_prompt"]

        markdown = builder.render_drift_markdown(limit=5)
        assert "# APOS Drift Report" in markdown
        assert "## Summary" in markdown
        assert "## Recent Failures" in markdown
        assert "## Likely Causes" in markdown
        assert "## Affected Files" in markdown
        assert "## Stale Context Signals" in markdown
        assert "## Recommended Human Action" in markdown
        assert "## Recommended LLM Prompt" in markdown
    finally:
        builder.close()


def test_dashboard_payload_exposes_failed_summary_and_drift_warning():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = workspace / ".apos" / "history.sqlite3"
        recorder = Recorder(db_path=history_db)
        try:
            recorder.record_task(
                "dashboard-failure",
                {
                    "id": "dashboard-failure",
                    "task_type": "patch_and_run",
                    "patches": [{"target": "workspace/missing.py", "language": "python", "intent": "update", "content": "print('x')\n"}],
                    "commands": [],
                },
            )
            recorder.record_result(
                "result-dashboard-failure",
                "dashboard-failure",
                -4,
                "",
                "target file does not exist",
                {"task_type": "patch_and_run"},
                result_envelope={
                    "schema_version": "1.0",
                    "task_id": "dashboard-failure",
                    "status": "patch_blocked",
                    "exit_code": -4,
                    "patch_blocked": True,
                    "patch_blocked_reason": "target file does not exist",
                    "policy_blocked": False,
                    "blocked_reason": "target file does not exist",
                },
            )
            recorder.record_approval_item(
                "dashboard-pending",
                "dashboard-task",
                "bridge_patch",
                "Review bridge patch",
                {"target": "workspace/existing.py", "patch_id": "dashboard-pending"},
                patch_id="dashboard-pending",
                workspace_root=str(workspace),
                target="workspace/existing.py",
                status="pending",
            )
            recorder.record_approval_item(
                "dashboard-failed",
                "dashboard-task",
                "bridge_patch",
                "Review bridge patch",
                {"target": "workspace/missing.py", "patch_id": "dashboard-failed"},
                patch_id="dashboard-failed",
                workspace_root=str(workspace),
                target="workspace/missing.py",
                status="failed",
                decision_reason="target file does not exist",
            )
        finally:
            recorder.close()

        status, headers, body = _call_wsgi(
            dashboard_app,
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/api/dashboard",
                "QUERY_STRING": f"workspace={workspace.as_posix()}",
                "wsgi.input": BytesIO(b""),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")
        payload = json.loads(body.decode("utf-8"))
        assert payload["failed_items_count"] >= 1
        assert isinstance(payload["drift_warning"], bool)
        assert "failed_items_summary" in payload
        assert payload["failed_items_summary"]
