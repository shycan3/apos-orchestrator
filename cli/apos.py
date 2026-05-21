#!/usr/bin/env python3
"""
APOS v3.2 Pure Shell CLI.

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
""",
        project_root / ".apos" / "session_state.md": """# APOS Session State

Current state is intentionally minimal.
Update this file only through explicit human direction.
""",
        project_root / ".apos" / "risk_vector.json": '{\n  "risk_level": "low",\n  "active_risks": []\n}\n',
        project_root / ".codex" / "APOS_INSTRUCTIONS.md": codex_prompt(),
        project_root / "specifications" / "core_direction.md": """# Core Direction

Describe the project objective, non-goals, and long-term direction here.
""",
        project_root / "specifications" / "architecture.md": """# Architecture

Human-authored architecture notes belong outside the Machine Facts block.

## Machine Facts

""" + facts_block + "\n",
        project_root / "context" / "decisions.md": """# Decisions

Record durable project decisions here.
""",
        project_root / "workspace" / "current_tasks.md": """# Current Tasks

- Define the next APOS-guided task.
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
Do not modify specifications/, context/, .apos/, or .codex/ directly.
Use workspace/scratchpad.md for protected-area proposals.
"""


def print_codex_prompt() -> None:
    print(codex_prompt())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="APOS v3.2 Pure Shell CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    apply_parser = subparsers.add_parser("apply", help="create APOS static structure")
    apply_parser.add_argument("-y", "--yes", action="store_true", help="confirm project initialization")
    apply_parser.add_argument("project_path")

    refresh_parser = subparsers.add_parser("refresh", help="append a Machine Facts drift report")
    refresh_parser.add_argument("project_path")

    summarize_parser = subparsers.add_parser("summarize", help="summarize APOS project state")
    summarize_parser.add_argument("project_path")

    subparsers.add_parser("codex", help="print APOS Codex handoff instruction")
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

    abort(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
