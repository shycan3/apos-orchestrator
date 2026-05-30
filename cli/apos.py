#!/usr/bin/env python3
"""
APOS v3.2 + Bridge Protocol Pure Shell CLI.

This CLI creates the static APOS project structure, records observable
machine facts, and writes drift reports to workspace/scratchpad.md without
silently modifying protected permanent documents during refresh.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cli.context_pack import add_context_arguments, execute_context_pack
from apos_core.prompt_builder import PromptBuilder
from apos_core.recovery_prompt_builder import RecoveryPromptBuilder
from apos_core.report_builder import ReportBuilder
from apos_core.orchestrator import Orchestrator
from apos_core.plan_flow import PlanStepManager

try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11 fallback message.
    tomllib = None  # type: ignore[assignment]


FACTS_START = "<!-- APOS_FACTS_START -->"
FACTS_END = "<!-- APOS_FACTS_END -->"

APOS_DIRS = (
    ".apos",
    ".codex",
    "specifications",
    "context",
    "workspace",
    "archives",
    "archives/completed_tasks",
    "archives/resolved_risks",
    "archives/rejected_proposals",
)

PROTECTED_DIRS = ("specifications", "context", ".apos", ".codex")


@dataclass(frozen=True)
class FactsBlock:
    before: str
    body: str
    after: str


def abort(message: str, code: int = 2) -> None:
    print(f"APOS abort: {message}", file=sys.stderr)
    raise SystemExit(code)


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def resolve_project_root(raw_path: str, create: bool = False) -> Path:
    if "\x00" in raw_path:
        abort("project path contains a null byte")

    root = Path(raw_path).expanduser().resolve()
    if create:
        root.mkdir(parents=True, exist_ok=True)

    if not root.exists():
        abort(f"project path does not exist: {root}")

    if not root.is_dir():
        abort(f"project path is not a directory: {root}")

    return root


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        abort(f"failed to read UTF-8 text from {path}: {exc}")


def write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        abort(f"JSON parsing failed for {path}: {exc}")

    if not isinstance(data, dict):
        abort(f"JSON root must be an object in {path}")

    return data


def read_toml(path: Path) -> Dict[str, Any]:
    if tomllib is None:
        abort("Python 3.11+ is required to parse TOML machine facts")

    try:
        return tomllib.loads(read_text(path))
    except tomllib.TOMLDecodeError as exc:  # type: ignore[union-attr]
        abort(f"TOML parsing failed for {path}: {exc}")


def collect_machine_facts(project_root: Path) -> Dict[str, Any]:
    package_json = project_root / "package.json"
    pyproject = project_root / "pyproject.toml"
    requirements = project_root / "requirements.txt"

    facts: Dict[str, Any] = {
        "project_name": project_root.name,
        "project_root": str(project_root),
        "git_repo": (project_root / ".git").is_dir(),
        "files": {
            "package_json": package_json.exists(),
            "pyproject_toml": pyproject.exists(),
            "requirements_txt": requirements.exists(),
            "package_lock_json": (project_root / "package-lock.json").exists(),
            "pnpm_lock_yaml": (project_root / "pnpm-lock.yaml").exists(),
            "yarn_lock": (project_root / "yarn.lock").exists(),
            "uv_lock": (project_root / "uv.lock").exists(),
        },
        "counts": count_source_files(project_root),
        "node": {},
        "python": {},
        "framework_hints": [],
    }

    if package_json.exists():
        package = read_json(package_json)
        dependencies = package.get("dependencies", {})
        dev_dependencies = package.get("devDependencies", {})

        if not isinstance(dependencies, dict):
            abort("package.json dependencies must be an object")
        if not isinstance(dev_dependencies, dict):
            abort("package.json devDependencies must be an object")

        facts["node"] = {
            "name": package.get("name", ""),
            "type": package.get("type", ""),
            "scripts": sorted((package.get("scripts") or {}).keys())
            if isinstance(package.get("scripts") or {}, dict)
            else [],
            "dependencies": sorted(dependencies.keys()),
            "dev_dependencies": sorted(dev_dependencies.keys()),
        }

    if pyproject.exists():
        pyproject_data = read_toml(pyproject)
        project = pyproject_data.get("project", {})
        if project and not isinstance(project, dict):
            abort("pyproject.toml [project] must be a table")

        facts["python"]["pyproject"] = {
            "name": project.get("name", "") if isinstance(project, dict) else "",
            "dependencies": project.get("dependencies", []) if isinstance(project, dict) else [],
        }

    if requirements.exists():
        facts["python"]["requirements"] = [
            line.strip()
            for line in read_text(requirements).splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    facts["framework_hints"] = detect_framework_hints(facts)
    return facts


def count_source_files(project_root: Path) -> Dict[str, int]:
    ignored_parts = {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".apos",
        ".codex",
        "specifications",
        "context",
        "workspace",
        "archives",
    }
    extensions = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "jsx",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".json": "json",
        ".md": "markdown",
    }
    counts = {name: 0 for name in extensions.values()}

    for path in project_root.rglob("*"):
      # Keep this loop intentionally simple and deterministic.
        if not path.is_file():
            continue
        if any(part in ignored_parts for part in path.parts):
            continue
        key = extensions.get(path.suffix.lower())
        if key:
            counts[key] += 1

    return counts


def detect_framework_hints(facts: Dict[str, Any]) -> List[str]:
    packages = set()
    node = facts.get("node") or {}
    packages.update(node.get("dependencies") or [])
    packages.update(node.get("dev_dependencies") or [])

    python_reqs = " ".join((facts.get("python") or {}).get("requirements") or []).lower()
    hints = []

    for package_name, hint in (
        ("next", "nextjs"),
        ("react", "react"),
        ("vue", "vue"),
        ("svelte", "svelte"),
        ("express", "express"),
        ("vite", "vite"),
    ):
        if package_name in packages:
            hints.append(hint)

    for marker, hint in (
        ("fastapi", "fastapi"),
        ("django", "django"),
        ("flask", "flask"),
        ("pytest", "pytest"),
    ):
        if marker in python_reqs:
            hints.append(hint)

    return sorted(set(hints))


def render_facts_block(facts: Dict[str, Any]) -> str:
    rendered_json = json.dumps(facts, ensure_ascii=False, indent=2, sort_keys=True)
    return "\n".join(
        [
            FACTS_START,
            "```json",
            rendered_json,
            "```",
            FACTS_END,
        ]
    )


def extract_facts_block(text: str, path: Path) -> FactsBlock:
    start_count = text.count(FACTS_START)
    end_count = text.count(FACTS_END)
    if start_count != 1 or end_count != 1:
        abort(
            f"Machine Facts token parsing failed for {path}; "
            f"expected exactly one start and one end token, got {start_count}/{end_count}"
        )

    start = text.index(FACTS_START)
    end = text.index(FACTS_END)
    if end <= start:
        abort(f"Machine Facts token order is invalid in {path}")

    before = text[:start]
    body = text[start : end + len(FACTS_END)]
    after = text[end + len(FACTS_END) :]
    return FactsBlock(before=before, body=body, after=after)


def create_static_structure(project_root: Path) -> List[str]:
    created = []
    for directory in APOS_DIRS:
        path = project_root / directory
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(str(path.relative_to(project_root)))
    return created


def default_files(project_root: Path, facts_block: str) -> Dict[Path, str]:
    return {
        project_root / ".apos" / "system_core.md": """# APOS System Core

APOS is a file-based collaboration layer.

Core rule:
Web LLMs propose, local APOS validates, humans approve.
Bridge Layer converts design output into executable patch instructions.
""",
    project_root / ".apos" / "preference_layer.md": """# Preference Layer

Record durable project preferences here.
Keep this file focused on stable collaboration preferences, not task notes.
""",
        project_root / ".apos" / "session_state.md": """# APOS Session State

Current state is intentionally minimal.
Update this file only through explicit human direction.
""",
    project_root / ".apos" / "risk_vector.json": '{\n  "protocol": "APOS Risk Queue",\n  "max_queue_limit": 5,\n  "overflow_policy": "archive_resolved_then_request_approval",\n  "active_pending_risks": []\n}\n',
        project_root / ".codex" / "APOS_INSTRUCTIONS.md": codex_prompt(),
        project_root / "specifications" / "core_direction.md": """# Core Direction

Describe the project objective, non-goals, and long-term direction here.
""",
        project_root / "specifications" / "architecture.md": """# Architecture

## Human Notes

Human-authored architecture notes belong here.

---

## Machine Facts

""" + facts_block + "\n",
    project_root / "specifications" / "immutable_rules.md": """# Immutable Rules

These rules define the non-negotiable project boundaries.
Do not change them through automated drift handling.
""",
    project_root / "specifications" / "glossary.md": """# Glossary

Define project-specific terms here so human and machine language stays aligned.
""",
        project_root / "context" / "decisions.md": """# Decisions

Record durable project decisions here.
""",
    project_root / "context" / "project_history.md": """# Project History

Track major milestones, reversions, and completed transitions here.
""",
        project_root / "workspace" / "current_tasks.md": """# Current Tasks

- Define the next APOS-guided task.
""",
    project_root / "workspace" / "active_code.py": """# Active Code

def main() -> None:
    pass


if __name__ == "__main__":
    main()
""",
    project_root / "workspace" / "active_draft.md": """# Active Draft

Use this file for in-progress human or machine drafting.
""",
        project_root / "workspace" / "scratchpad.md": """# Scratchpad

Protected-area proposals and drift reports are appended here.
""",
    }


def apply(project_path: str, yes: bool) -> None:
    if not yes:
        abort("apply requires -y to avoid accidental project initialization")

    project_root = resolve_project_root(project_path, create=True)
    facts = collect_machine_facts(project_root)
    facts_block = render_facts_block(facts)
    created_dirs = create_static_structure(project_root)
    created_files = []

    architecture = project_root / "specifications" / "architecture.md"
    if architecture.exists() and read_text(architecture).strip():
        extract_facts_block(read_text(architecture), architecture)

    for path, content in default_files(project_root, facts_block).items():
        if write_if_missing(path, content):
            created_files.append(str(path.relative_to(project_root)))

    print("APOS apply complete")
    print(f"Project: {project_root}")
    print(f"Created directories: {len(created_dirs)}")
    print(f"Created files: {len(created_files)}")
    for item in created_dirs + created_files:
        print(f"- {item}")


def refresh(project_path: str) -> None:
    project_root = resolve_project_root(project_path)
    architecture = project_root / "specifications" / "architecture.md"
    if not architecture.exists():
        abort(f"missing architecture file: {architecture}")

    current_text = read_text(architecture)
    current_block = extract_facts_block(current_text, architecture).body.strip()
    new_block = render_facts_block(collect_machine_facts(project_root)).strip()

    added, removed = diff_lines(current_block, new_block)
    report = render_drift_report(project_root, added, removed, current_block, new_block)
    scratchpad = project_root / "workspace" / "scratchpad.md"
    scratchpad.parent.mkdir(parents=True, exist_ok=True)
    with scratchpad.open("a", encoding="utf-8", newline="\n") as file:
        file.write("\n" + report.strip() + "\n")

    print("APOS refresh complete")
    print("Protected documents were not modified.")
    print(f"Drift report appended to: {scratchpad}")
    print(f"Added lines: {len(added)}")
    print(f"Removed lines: {len(removed)}")


def diff_lines(old: str, new: str) -> Tuple[List[str], List[str]]:
    old_lines = set(old.splitlines())
    new_lines = set(new.splitlines())
    added = sorted(new_lines - old_lines)
    removed = sorted(old_lines - new_lines)
    return added, removed


def render_drift_report(
    project_root: Path,
    added: Iterable[str],
    removed: Iterable[str],
    current_block: str,
    new_block: str,
) -> str:
    added = list(added)
    removed = list(removed)
    status = "No drift detected." if not added and not removed else "Drift detected."
    return f"""
## APOS Drift Report

Generated: {now_iso()}
Project: {project_root}
Status: {status}

Protected files were not modified. Review this report manually before updating specifications/architecture.md.

### Added

{render_bullets(added)}

### Removed

{render_bullets(removed)}

### Current Machine Facts

{current_block}

### Observed Machine Facts

{new_block}
"""


def render_bullets(lines: Iterable[str]) -> str:
    materialized = list(lines)
    if not materialized:
        return "- None"
    return "\n".join(f"- `{line}`" for line in materialized)


def summarize(project_path: str) -> None:
    project_root = resolve_project_root(project_path)
    print("APOS summary")
    print(f"Project: {project_root}")
    print("")
    print("Required directories:")
    for directory in APOS_DIRS[:6]:
        path = project_root / directory
        print(f"- {directory}: {'present' if path.is_dir() else 'missing'}")

    architecture = project_root / "specifications" / "architecture.md"
    print("")
    if architecture.exists():
        block = extract_facts_block(read_text(architecture), architecture)
        print("Machine Facts block: present")
        print(block.body)
    else:
        print("Machine Facts block: missing architecture.md")


def codex_prompt() -> str:
    return """# APOS Instructions

Follow .codex/APOS_INSTRUCTIONS.md.
Use APOS STRICT MODE.
Read workspace/current_tasks.md and context/decisions.md first.
Read task-relevant specifications only.
Stop and ask before API changes, schema changes, deletions, or permanent rule changes.
Do not modify specifications/, context/, .apos/, or .codex/ directly.
Use workspace/scratchpad.md for protected-area proposals.
"""


def print_codex_prompt() -> None:
    print(codex_prompt())


def _make_plan_manager(workspace: str, history_db: str | None) -> tuple[Orchestrator, PlanStepManager]:
    workspace_root = str(Path(workspace).resolve())
    history_db_path = Path(history_db) if history_db else Path(workspace_root) / ".apos" / "history.sqlite3"
    orch = Orchestrator(workspace_root=workspace_root, history_db_path=history_db_path)
    return orch, PlanStepManager(orch)


def _print_plan_payload(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if isinstance(payload, list):
        for item in payload:
            print(item)
        return
    if isinstance(payload, dict):
        if "steps" in payload:
            print(f"task_id={payload.get('task_id')} step_count={payload.get('step_count')} plan_goal={payload.get('plan_goal', '')}")
            for step in payload.get("steps", []):
                print(
                    f"- step {step.get('step_index')}: {step.get('title')} status={step.get('status')} approved_by={step.get('approved_by') or ''}"
                )
            return
        if "task_type" in payload and payload.get("task_type") == "plan_only":
            print(
                f"task_id={payload.get('task_id')} step_count={payload.get('step_count')} pending={payload.get('pending_count', 0)} executed={payload.get('executed_count', 0)} failed={payload.get('failed_count', 0)}"
            )
            return
    print(str(payload))


def _build_plan_subparser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--workspace", default=".", help="Workspace root")
    parser.add_argument("--history-db", default=None, help="Path to history SQLite database")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    return parser


def _build_prompt_subparser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--workspace-root", default=str(PROJECT_ROOT), help="Workspace root to scan")
    parser.add_argument("--history-db", default=None, help="Path to the APOS history SQLite database")
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--max-files", type=int, default=120)
    parser.add_argument("--max-file-preview-chars", type=int, default=1200)
    parser.add_argument("--max-total-chars", type=int, default=12000)
    parser.add_argument("--goal", required=True, help="User goal to embed in the generated prompt")
    parser.add_argument("--mode", choices=("patch", "plan", "review"), default="patch")
    parser.add_argument("--output", default=None, help="Write the rendered prompt to this file")
    parser.add_argument("--copy", action="store_true", help="Best-effort copy the rendered prompt to the clipboard")
    return parser


def _build_report_subparser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--workspace", default=".", help="Workspace root")
    parser.add_argument("--history-db", default=None, help="Path to history SQLite database")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of failures or drift items to report")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Render format")
    return parser


def _build_recover_prompt_subparser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--workspace", default=".", help="Workspace root")
    parser.add_argument("--history-db", default=None, help="Path to history SQLite database")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of history items to inspect")
    parser.add_argument(
        "--mode",
        choices=("auto", "patch", "plan", "review"),
        default=None,
        help="Choose auto recommendation or override the recovery mode",
    )
    parser.add_argument("--output", default=None, help="Write the recovery prompt to this file")
    parser.add_argument("--copy", action="store_true", help="Best-effort copy the recovery prompt to the clipboard")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--failure", dest="failure_id", default=None, help="Recover from a specific failure identifier")
    source.add_argument("--latest", action="store_true", help="Recover from the latest failure")
    source.add_argument("--drift", action="store_true", help="Recover from the latest drift report")
    source.add_argument("--plan-step", nargs=2, metavar=("TASK_ID", "STEP_INDEX"), help="Recover from a plan step failure")
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="APOS v3.2 + Bridge Protocol Pure Shell CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    apply_parser = subparsers.add_parser("apply", help="create APOS static structure")
    apply_parser.add_argument("-y", "--yes", action="store_true", help="confirm project initialization")
    apply_parser.add_argument("project_path")

    refresh_parser = subparsers.add_parser("refresh", help="append a Machine Facts drift report")
    refresh_parser.add_argument("project_path")

    summarize_parser = subparsers.add_parser("summarize", help="summarize APOS project state")
    summarize_parser.add_argument("project_path")

    subparsers.add_parser("codex", help="print APOS Codex handoff instruction")

    context_parser = subparsers.add_parser("context", help="build or inspect an APOS context pack")
    context_subparsers = context_parser.add_subparsers(dest="context_command", required=True)

    build_parser = context_subparsers.add_parser("build", help="build a safe context pack")
    add_context_arguments(build_parser)

    inspect_parser = context_subparsers.add_parser("inspect", help="print a human-friendly context pack")
    add_context_arguments(inspect_parser)

    prompt_parser = subparsers.add_parser("prompt", help="build a paste-ready APOS prompt")
    prompt_subparsers = prompt_parser.add_subparsers(dest="prompt_command", required=True)

    prompt_build = prompt_subparsers.add_parser("build", help="build a paste-ready APOS prompt")
    _build_prompt_subparser(prompt_build)

    report_parser = subparsers.add_parser("report", help="generate failure and drift reports")
    report_subparsers = report_parser.add_subparsers(dest="report_command", required=True)

    report_failures = report_subparsers.add_parser("failures", help="list recent failures")
    _build_report_subparser(report_failures)

    report_failure = report_subparsers.add_parser("failure", help="show a single failure report")
    _build_report_subparser(report_failure)
    report_failure.add_argument("identifier")

    report_drift = report_subparsers.add_parser("drift", help="show drift signals")
    _build_report_subparser(report_drift)

    report_next_prompt = report_subparsers.add_parser("next-prompt", help="print the recommended next prompt")
    _build_report_subparser(report_next_prompt)

    recover_parser = subparsers.add_parser("recover", help="generate recovery prompts from failures or drift")
    recover_subparsers = recover_parser.add_subparsers(dest="recover_command", required=True)
    recover_prompt = recover_subparsers.add_parser("prompt", help="build a recovery prompt")
    _build_recover_prompt_subparser(recover_prompt)

    plans_parser = subparsers.add_parser("plans", help="manage plan_only tasks and steps")
    plans_subparsers = plans_parser.add_subparsers(dest="plans_command", required=True)

    plans_list = plans_subparsers.add_parser("list", help="list plan_only tasks")
    _build_plan_subparser(plans_list)
    plans_list.add_argument("--limit", type=int, default=None)
    plans_list.add_argument("--offset", type=int, default=None)

    plans_show = plans_subparsers.add_parser("show", help="show a recorded plan")
    _build_plan_subparser(plans_show)
    plans_show.add_argument("task_id")

    plans_steps = plans_subparsers.add_parser("steps", help="list steps for a plan")
    _build_plan_subparser(plans_steps)
    plans_steps.add_argument("task_id")

    plans_approve = plans_subparsers.add_parser("approve-step", help="approve a step")
    _build_plan_subparser(plans_approve)
    plans_approve.add_argument("task_id")
    plans_approve.add_argument("step_index", type=int)
    plans_approve.add_argument("--approved-by", default="manual")
    plans_approve.add_argument("--reason", default=None)

    plans_reject = plans_subparsers.add_parser("reject-step", help="reject a step")
    _build_plan_subparser(plans_reject)
    plans_reject.add_argument("task_id")
    plans_reject.add_argument("step_index", type=int)
    plans_reject.add_argument("--rejected-by", default="manual")
    plans_reject.add_argument("--reason", default=None)

    plans_run = plans_subparsers.add_parser("run-step", help="run an approved step")
    _build_plan_subparser(plans_run)
    plans_run.add_argument("task_id")
    plans_run.add_argument("step_index", type=int)
    plans_run.add_argument("--approved-by", default=None, help="Optional runner identifier for audit metadata")
    plans_run.add_argument("--force", action="store_true", help="Allow rerun of executed or failed steps")

    return parser


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "apply":
        apply(args.project_path, args.yes)
        return 0

    if args.command == "refresh":
        refresh(args.project_path)
        return 0

    if args.command == "summarize":
        summarize(args.project_path)
        return 0

    if args.command == "codex":
        print_codex_prompt()
        return 0

    if args.command == "context":
        output_format = "json"
        if args.context_command == "inspect":
            output_format = "markdown"
        if getattr(args, "json", False):
            output_format = "json"
        elif getattr(args, "format", None):
            output_format = args.format
        execute_context_pack(
            workspace_root=args.workspace_root,
            history_db_path=args.history_db,
            max_depth=args.max_depth,
            max_files=args.max_files,
            max_file_preview_chars=args.max_file_preview_chars,
            max_total_chars=args.max_total_chars,
            output_format=output_format,
            output_path=args.output,
        )
        return 0

    if args.command == "prompt":
        if args.prompt_command == "build":
            builder = PromptBuilder(args.workspace_root, history_db_path=args.history_db)
            try:
                prompt_text = builder.build(
                    goal=args.goal,
                    mode=args.mode,
                    max_depth=args.max_depth,
                    max_files=args.max_files,
                    max_file_preview_chars=args.max_file_preview_chars,
                    max_total_chars=args.max_total_chars,
                )
            except ValueError as exc:
                abort(str(exc))
            builder.write_output(prompt_text, args.output)
            if args.copy and not builder.copy_to_clipboard(prompt_text):
                print("APOS warning: clipboard copy failed; prompt output was still generated.", file=sys.stderr)
            print(prompt_text, end="")
            return 0

        abort(f"unknown prompt command: {args.prompt_command}")

    if args.command == "report":
        builder = ReportBuilder(args.workspace, history_db_path=args.history_db)
        try:
            if args.report_command == "failures":
                report = builder.build_failure_report(limit=args.limit)
                rendered = builder.render_markdown(report) if args.format == "markdown" else json.dumps(report, ensure_ascii=False, indent=2)
                print(rendered, end="")
                return 0

            if args.report_command == "failure":
                report = builder.build_failure_detail(args.identifier, limit=args.limit)
                rendered = builder.render_markdown(report) if args.format == "markdown" else json.dumps(report, ensure_ascii=False, indent=2)
                print(rendered, end="")
                return 0

            if args.report_command == "drift":
                report = builder.build_drift_report(limit=args.limit)
                rendered = builder.render_drift_markdown(limit=args.limit) if args.format == "markdown" else json.dumps(report, ensure_ascii=False, indent=2)
                print(rendered, end="")
                return 0

            if args.report_command == "next-prompt":
                print(builder.build_next_prompt(limit=args.limit))
                return 0

            abort(f"unknown report command: {args.report_command}")
        finally:
            builder.close()

    if args.command == "recover":
        if args.recover_command == "prompt":
            builder = RecoveryPromptBuilder(args.workspace, history_db_path=args.history_db)
            try:
                plan_step = None
                if getattr(args, "plan_step", None):
                    plan_step = (str(args.plan_step[0]), int(args.plan_step[1]))
                recovery = builder.build(
                    failure_id=args.failure_id,
                    latest=bool(args.latest),
                    drift=bool(args.drift),
                    plan_step=plan_step,
                    mode=args.mode,
                    limit=args.limit,
                )
                prompt_text = recovery["prompt_text"]
                builder.write_output(prompt_text, args.output)
                if args.copy and not builder.copy_to_clipboard(prompt_text):
                    print("APOS warning: clipboard copy failed; recovery prompt output was still generated.", file=sys.stderr)
                print(prompt_text, end="")
                return 0
            finally:
                builder.close()

        abort(f"unknown recover command: {args.recover_command}")

    if args.command == "plans":
        orch, manager = _make_plan_manager(args.workspace, args.history_db)
        try:
            if args.plans_command == "list":
                payload = manager.list_plans(limit=args.limit, offset=args.offset)
                _print_plan_payload(payload, args.json)
                return 0

            if args.plans_command == "show":
                payload = manager.get_plan(args.task_id)
                if not payload:
                    abort(f"plan not found: {args.task_id}")
                _print_plan_payload(payload, args.json)
                return 0

            if args.plans_command == "steps":
                payload = manager.list_steps(args.task_id)
                if not payload:
                    abort(f"plan not found: {args.task_id}")
                _print_plan_payload(payload, args.json)
                return 0

            if args.plans_command == "approve-step":
                payload = manager.approve_step(args.task_id, args.step_index, approved_by=args.approved_by, reason=args.reason)
                if not payload:
                    abort(f"plan step not found: {args.task_id}:{args.step_index}")
                _print_plan_payload(payload, args.json)
                return 0

            if args.plans_command == "reject-step":
                payload = manager.reject_step(args.task_id, args.step_index, rejected_by=args.rejected_by, reason=args.reason)
                if not payload:
                    abort(f"plan step not found: {args.task_id}:{args.step_index}")
                _print_plan_payload(payload, args.json)
                return 0

            if args.plans_command == "run-step":
                payload = manager.run_step(args.task_id, args.step_index, approved_by=args.approved_by, force=args.force)
                if isinstance(payload, dict) and payload.get("status") in {"not_found", "invalid_step", "invalid_task_type"}:
                    abort(f"plan step not runnable: {args.task_id}:{args.step_index} ({payload.get('status')})")
                _print_plan_payload(payload, args.json)
                return 0

            abort(f"unknown plans command: {args.plans_command}")
        finally:
            try:
                orch.stop()
            except Exception:
                pass

    abort(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
