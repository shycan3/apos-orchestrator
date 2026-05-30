import json
from io import BytesIO
from pathlib import Path
from wsgiref.util import setup_testing_defaults

from apos_core.recorder import Recorder
from apos_core.recovery_prompt_builder import RecoveryPromptBuilder
from cli.apos import main as apos_main
from server.list_approvals_endpoint import app as dashboard_app


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


def _seed_workspace(root: Path) -> Path:
    _write_text(root / "README.md", "# Recovery Prompt Demo\n")
    _write_text(root / "workspace" / "existing.py", "print('ok')\n")
    _write_text(root / "workspace" / "secret_note.txt", "api_key = sk-test-12345\npassword = hunter2\n")
    _write_text(root / "project_updates" / "WORKLOG.md", "# Worklog\n\n- recovery prompt demo\n")
    history_db = root / ".apos" / "history.sqlite3"
    recorder = Recorder(db_path=history_db)
    try:
        recorder.record_task(
            "patch-failure",
            {
                "id": "patch-failure",
                "task_type": "patch_and_run",
                "patches": [{"target": "workspace/missing.py", "language": "python", "intent": "update", "content": "print('x')\n"}],
                "commands": [],
            },
        )
        recorder.record_result(
            "result-patch-failure",
            "patch-failure",
            -4,
            "",
            "target file does not exist",
            {"task_type": "patch_and_run"},
            result_envelope={
                "schema_version": "1.0",
                "task_id": "patch-failure",
                "status": "patch_blocked",
                "exit_code": -4,
                "patch_blocked": True,
                "patch_blocked_reason": "target file does not exist",
                "policy_blocked": False,
                "blocked_reason": "target file does not exist",
            },
        )

        recorder.record_task(
            "command-failure",
            {
                "id": "command-failure",
                "task_type": "run",
                "patches": [],
                "commands": [["python", "-m", "pytest"]],
            },
        )
        recorder.record_result(
            "result-command-failure",
            "command-failure",
            1,
            "",
            "assertion failed",
            {"task_type": "run"},
            result_envelope={
                "schema_version": "1.0",
                "task_id": "command-failure",
                "status": "failed",
                "exit_code": 1,
                "patch_blocked": False,
                "policy_blocked": False,
                "blocked_reason": "",
            },
        )

        recorder.record_task(
            "envelope-failure",
            {
                "id": "envelope-failure",
                "task_type": "patch_and_run",
                "patches": [],
                "commands": [],
            },
        )
        recorder.record_result(
            "result-envelope-failure",
            "envelope-failure",
            2,
            "",
            "task envelope validation failed",
            {"task_type": "patch_and_run"},
            result_envelope={
                "schema_version": "1.0",
                "task_id": "envelope-failure",
                "status": "validation_failed",
                "exit_code": 2,
                "patch_blocked": False,
                "policy_blocked": True,
                "blocked_reason": "task_envelope_validation_failed: missing required field",
            },
        )

        recorder.record_task(
            "plan-recover-demo",
            {
                "id": "plan-recover-demo",
                "task_type": "plan_only",
                "patches": [],
                "commands": [],
                "meta": {
                    "plan_goal": "Fix a flaky step",
                    "plan_steps": [
                        {
                            "title": "Fix flaky step",
                            "task_type": "patch_and_run",
                            "patches": [{"target": "workspace/existing.py", "language": "python", "intent": "update", "content": "print('step')\n"}],
                            "commands": [["python", "-m", "pytest"]],
                        }
                    ],
                },
            },
        )
        recorder.record_result(
            "result-plan-recover-demo-step-0",
            "plan-recover-demo-step-0",
            1,
            "",
            "command failed",
            {"task_type": "plan_only", "plan_parent": "plan-recover-demo", "plan_step_index": 0},
            result_envelope={
                "schema_version": "1.0",
                "task_id": "plan-recover-demo-step-0",
                "status": "failed",
                "exit_code": 1,
                "plan_parent": "plan-recover-demo",
                "plan_step_index": 0,
                "stdout": "",
                "stderr": "command failed",
            },
        )
    finally:
        recorder.close()
    return history_db


def test_recovery_prompt_latest_writes_output_and_prefers_plan(tmp_path: Path):
    workspace = tmp_path / "workspace"
    history_db = _seed_workspace(workspace)
    output_path = tmp_path / "recovery_prompt.md"

    builder = RecoveryPromptBuilder(workspace, history_db_path=history_db)
    try:
        recovery = builder.build(latest=True, limit=10)
        prompt_text = recovery["prompt_text"]
        assert recovery["mode"] == "plan"
        assert "## Recovery Goal" in prompt_text
        assert "## Failure Summary" in prompt_text
        assert "## Likely Cause" in prompt_text
        assert "## Affected Files" in prompt_text
        assert "## Relevant Context" in prompt_text
        assert "## Constraints" in prompt_text
        assert "## Required LLM Output" in prompt_text
        assert "## Recommended Mode: plan" in prompt_text
        assert "## Safety Reminder" in prompt_text
        assert "plan_only" in prompt_text
        assert "meta.plan_steps" in prompt_text
        assert "plan-recover-demo-step-0" in prompt_text or "execution_failed" in prompt_text or "test_failed" in prompt_text
        assert "sk-test-12345" not in prompt_text
        assert "hunter2" not in prompt_text

        builder.write_output(prompt_text, output_path)
        assert output_path.exists()
        assert output_path.read_text(encoding="utf-8").startswith("# APOS Recovery Prompt")
    finally:
        builder.close()


def test_recovery_prompt_auto_mode_recommends_modes_by_cause(tmp_path: Path):
    workspace = tmp_path / "workspace"
    history_db = _seed_workspace(workspace)

    builder = RecoveryPromptBuilder(workspace, history_db_path=history_db)
    try:
        missing_file = builder.build(failure_id="patch-failure", mode="auto", limit=10)
        assert missing_file["mode"] == "review"
        assert missing_file["recommended_mode"] == "review"
        assert "Do not produce file-edit JSON" in missing_file["prompt_text"]

        command_failure = builder.build(failure_id="command-failure", mode="auto", limit=10)
        assert command_failure["mode"] == "plan"
        assert command_failure["recommended_mode"] == "plan"
        assert "plan_only" in command_failure["prompt_text"]
        assert "independently reviewable" in command_failure["prompt_text"]

        envelope_failure = builder.build(failure_id="envelope-failure", mode="auto", limit=10)
        assert envelope_failure["mode"] == "review"
        assert envelope_failure["recommended_mode"] == "review"
        assert "Do not produce file-edit JSON" in envelope_failure["prompt_text"]
    finally:
        builder.close()


def test_recovery_prompt_specific_failure_recommends_patch(tmp_path: Path):
    workspace = tmp_path / "workspace"
    history_db = _seed_workspace(workspace)

    builder = RecoveryPromptBuilder(workspace, history_db_path=history_db)
    try:
        recovery = builder.build(failure_id="patch-failure", limit=10)
        prompt_text = recovery["prompt_text"]
        assert recovery["mode"] == "patch"
        assert recovery["source_kind"] == "failure"
        assert recovery["source_identifier"] == "patch-failure"
        assert "## Recommended Mode: patch" in prompt_text
        assert "workspace/missing.py" in prompt_text
        assert "sk-test-12345" not in prompt_text
        assert "hunter2" not in prompt_text
    finally:
        builder.close()


def test_recovery_prompt_drift_recommends_review(tmp_path: Path):
    workspace = tmp_path / "workspace"
    history_db = _seed_workspace(workspace)
    builder = RecoveryPromptBuilder(workspace, history_db_path=history_db)
    try:
        context_pack = builder.report_builder.context_builder.build(max_recent_history=5, max_pending_approvals=5)
        _write_text(workspace / "workspace" / "existing.py", "print('changed')\n")
        recovery = builder.build(drift=True, limit=5)
        prompt_text = recovery["prompt_text"]
        assert recovery["mode"] == "review"
        assert recovery["source_kind"] == "drift"
        assert recovery["recommended_mode"] == "review"
        assert "## Recommended Mode: review" in prompt_text
        assert "Refresh the Context Pack" in prompt_text or "drift" in prompt_text.lower()
        assert recovery["relevant_context"]
        assert context_pack["generated_at"]
    finally:
        builder.close()


def test_recovery_prompt_auto_drift_stays_review(tmp_path: Path):
    workspace = tmp_path / "workspace"
    history_db = _seed_workspace(workspace)
    builder = RecoveryPromptBuilder(workspace, history_db_path=history_db)
    try:
        recovery = builder.build(drift=True, mode="auto", limit=5)
        assert recovery["mode"] == "review"
        assert recovery["recommended_mode"] == "review"
        assert "## Required LLM Output" in recovery["prompt_text"]
    finally:
        builder.close()


def test_recovery_prompt_plan_step_failure_recommends_plan(tmp_path: Path):
    workspace = tmp_path / "workspace"
    history_db = _seed_workspace(workspace)

    builder = RecoveryPromptBuilder(workspace, history_db_path=history_db)
    try:
        recovery = builder.build(plan_step=("plan-recover-demo", 0), limit=10)
        prompt_text = recovery["prompt_text"]
        assert recovery["mode"] == "plan"
        assert recovery["source_kind"] == "plan_step_failure"
        assert recovery["source_identifier"] == "plan-recover-demo-step-0"
        assert "## Recommended Mode: plan" in prompt_text
        assert "plan_only" in prompt_text
        assert "meta.plan_steps" in prompt_text
        assert recovery["likely_cause"] in {"execution_failed", "test_failed", "unknown"}
    finally:
        builder.close()


def test_recovery_prompt_cli_copy_failure_still_succeeds(tmp_path: Path, monkeypatch, capsys):
    workspace = tmp_path / "workspace"
    history_db = _seed_workspace(workspace)
    output_path = tmp_path / "cli_recovery_prompt.md"

    monkeypatch.setattr(
        "apos_core.recovery_prompt_builder.RecoveryPromptBuilder.copy_to_clipboard",
        lambda self, prompt_text: False,
    )

    exit_code = apos_main(
        [
            "recover",
            "prompt",
            "--latest",
            "--workspace",
            str(workspace),
            "--history-db",
            str(history_db),
            "--output",
            str(output_path),
            "--copy",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "# APOS Recovery Prompt" in captured.out
    assert "clipboard copy failed" in captured.err
    assert output_path.exists()


def test_recovery_prompt_cli_auto_mode_selects_prompt_shape(tmp_path: Path, capsys):
    workspace = tmp_path / "workspace"
    history_db = _seed_workspace(workspace)

    auto_review = apos_main(
        [
            "recover",
            "prompt",
            "--failure",
            "patch-failure",
            "--mode",
            "auto",
            "--workspace",
            str(workspace),
            "--history-db",
            str(history_db),
        ]
    )
    assert auto_review == 0
    captured = capsys.readouterr()
    assert "## Recommended Mode: review" in captured.out
    assert "Do not produce file-edit JSON" in captured.out

    auto_plan = apos_main(
        [
            "recover",
            "prompt",
            "--latest",
            "--mode",
            "auto",
            "--workspace",
            str(workspace),
            "--history-db",
            str(history_db),
        ]
    )
    assert auto_plan == 0
    captured = capsys.readouterr()
    assert "## Recommended Mode: plan" in captured.out
    assert "plan_only" in captured.out


def test_recovery_prompt_dashboard_summary_is_exposed(tmp_path: Path):
    workspace = tmp_path / "workspace"
    history_db = _seed_workspace(workspace)
    builder = RecoveryPromptBuilder(workspace, history_db_path=history_db)
    try:
        recovery = builder.build(latest=True, limit=10)
        assert recovery["summary"]
        assert recovery["recommended_mode"] in {"patch", "plan", "review"}
    finally:
        builder.close()

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
    assert payload["recommended_recovery_mode"] in {"patch", "plan", "review"}
    assert payload["recommended_recovery_summary"]
