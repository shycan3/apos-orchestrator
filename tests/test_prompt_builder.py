import subprocess
import sys
import tempfile
from pathlib import Path

from apos_core.recorder import Recorder
from apos_core.prompt_builder import PromptBuilder


REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_history(db_path: Path, task_id: str) -> None:
    recorder = Recorder(db_path=db_path)
    try:
        task_payload = {
            "id": task_id,
            "task_type": "patch_and_run",
            "patches": [],
            "commands": [],
        }
        recorder.record_task(task_id, task_payload)
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
                "status": "success",
                "exit_code": 0,
                "patch_blocked": False,
                "policy_blocked": False,
                "blocked_reason": "",
            },
        )
    finally:
        recorder.close()


def _build_workspace(root: Path) -> Path:
    _write_text(root / "README.md", "# Prompt Builder Demo\n")
    _write_text(root / "workspace" / "hello.py", "print('hello')\n")
    _write_text(root / "workspace" / "secret_note.txt", "api_key = sk-test-12345\npassword = hunter2\n")
    _write_text(root / "project_updates" / "WORKLOG.md", "# Worklog\n\n- prompt builder demo\n")
    history_db = root / ".apos" / "history.sqlite3"
    _seed_history(history_db, "prompt-task-1")
    return history_db


def _run_prompt(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "cli/apos.py", "prompt", "build", *args],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def test_prompt_builder_cli_generates_patch_prompt_and_saves_output(tmp_path: Path):
    workspace = tmp_path / "workspace"
    history_db = _build_workspace(workspace)
    output_path = tmp_path / "prompt.md"

    proc = _run_prompt(
        "--workspace-root",
        str(workspace),
        "--history-db",
        str(history_db),
        "--goal",
        "Add a new status summary command",
        "--mode",
        "patch",
        "--output",
        str(output_path),
    )

    assert proc.returncode == 0, proc.stderr
    prompt = proc.stdout
    assert "# APOS Prompt Builder" in prompt
    assert "## APOS Role Rules" in prompt
    assert "## User Goal" in prompt
    assert "## Required Output Format" in prompt
    assert "## Safety Constraints" in prompt
    assert "## Current Context Pack" in prompt
    assert "## Recommended Response Style" in prompt
    assert "Web LLM is the proposer; APOS is the validator and executor." in prompt
    assert "```apos-patch" in prompt
    assert "exactly one fenced code block with the apos-patch language identifier" in prompt
    assert "must not contain a diff" in prompt
    assert "full final file content or the APOS-supported envelope content" in prompt
    assert "validate-only / preview_patch / propose_patch" in prompt
    assert "If multiple files need changes" in prompt
    assert "prefer review or plan mode instead" in prompt
    assert "# APOS Context Pack" in prompt
    assert "workspace/secret_note.txt" in prompt
    assert "sk-test-12345" not in prompt
    assert "hunter2" not in prompt
    assert "<redacted>" in prompt
    assert output_path.exists()
    assert "# APOS Prompt Builder" in output_path.read_text(encoding="utf-8")


def test_prompt_builder_cli_supports_plan_and_review_modes(tmp_path: Path):
    workspace = tmp_path / "workspace"
    history_db = _build_workspace(workspace)

    plan_proc = _run_prompt(
        "--workspace-root",
        str(workspace),
        "--history-db",
        str(history_db),
        "--goal",
        "Plan a staged refactor",
        "--mode",
        "plan",
    )
    assert plan_proc.returncode == 0, plan_proc.stderr
    assert "plan_only" in plan_proc.stdout
    assert "meta.plan_steps" in plan_proc.stdout
    assert "target files" in plan_proc.stdout
    assert "expected risk" in plan_proc.stdout
    assert "execution conditions" in plan_proc.stdout
    assert "stop conditions" in plan_proc.stdout
    assert "pending, approved, rejected, running, executed, failed, skipped" in plan_proc.stdout
    assert "```json" in plan_proc.stdout

    review_proc = _run_prompt(
        "--workspace-root",
        str(workspace),
        "--history-db",
        str(history_db),
        "--goal",
        "Review the current workspace for risks",
        "--mode",
        "review",
    )
    assert review_proc.returncode == 0, review_proc.stderr
    assert "analysis-only review" in review_proc.stdout
    assert "current-state summary" in review_proc.stdout
    assert "Recommended actions:" in review_proc.stdout
    assert "Next prompt:" in review_proc.stdout
    assert "estimates or assumptions" in review_proc.stdout
    assert "```apos-patch" not in review_proc.stdout


def test_prompt_builder_cli_includes_shared_safety_rules(tmp_path: Path):
    workspace = tmp_path / "workspace"
    history_db = _build_workspace(workspace)

    proc = _run_prompt(
        "--workspace-root",
        str(workspace),
        "--history-db",
        str(history_db),
        "--goal",
        "Inspect the current project safely",
        "--mode",
        "review",
    )

    assert proc.returncode == 0, proc.stderr
    prompt = proc.stdout
    assert "Web LLM is the proposer; APOS is the validator and executor." in prompt
    assert "Only APOS envelopes or plan formats are allowed" in prompt
    assert "Do not invent hidden commands or side effects" in prompt
    assert "If local state is unclear, rely only on the Context Pack" in prompt
    assert "Keep the human summary and APOS structure separate." in prompt


def test_prompt_builder_required_output_lines_are_reused():
    builder = PromptBuilder(Path(".").resolve())
    patch_lines = builder.required_output_lines("patch")
    plan_lines = builder.required_output_lines("plan")
    review_lines = builder.required_output_lines("review")

    assert any("apos-patch" in line for line in patch_lines)
    assert any("plan_only" in line for line in plan_lines)
    assert any("analysis-only review" in line for line in review_lines)


def test_prompt_builder_cli_requires_goal(tmp_path: Path):
    workspace = tmp_path / "workspace"
    history_db = _build_workspace(workspace)

    proc = subprocess.run(
        [
            sys.executable,
            "cli/apos.py",
            "prompt",
            "build",
            "--workspace-root",
            str(workspace),
            "--history-db",
            str(history_db),
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    assert "--goal" in proc.stderr
