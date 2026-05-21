"""Run or validate APOS task envelope JSON files."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apos_core.orchestrator import Orchestrator


SUPPORTED_SCHEMA_VERSION = "1.0"
ALLOWED_TASK_TYPES = {"run", "patch_and_run", "preview_patch", "restore_file"}
ALLOWED_CREATED_BY = {"user", "web_llm", "local_agent"}


def validate_task_envelope(envelope: dict[str, Any]) -> list[str]:
    """Validate a task envelope without applying patches or running commands."""
    errors: list[str] = []

    required_fields = [
        "schema_version",
        "task_id",
        "task_type",
        "created_by",
        "workspace_root",
        "patches",
        "commands",
        "options",
        "meta",
    ]

    for field in required_fields:
        if field not in envelope:
            errors.append(f"Missing required field: {field}")

    schema_version = envelope.get("schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        errors.append(
            f"Unsupported schema_version: {schema_version!r}. "
            f"Expected {SUPPORTED_SCHEMA_VERSION!r}."
        )

    task_type = envelope.get("task_type")
    if task_type not in ALLOWED_TASK_TYPES:
        errors.append(
            f"Invalid task_type: {task_type!r}. "
            f"Allowed values: {sorted(ALLOWED_TASK_TYPES)}."
        )

    created_by = envelope.get("created_by")
    if created_by not in ALLOWED_CREATED_BY:
        errors.append(
            f"Invalid created_by: {created_by!r}. "
            f"Allowed values: {sorted(ALLOWED_CREATED_BY)}."
        )

    if not isinstance(envelope.get("task_id"), str) or not envelope.get("task_id"):
        errors.append("task_id must be a non-empty string.")

    if not isinstance(envelope.get("workspace_root"), str) or not envelope.get("workspace_root"):
        errors.append("workspace_root must be a non-empty string.")

    patches = envelope.get("patches")
    if not isinstance(patches, list):
        errors.append("patches must be a list.")
    else:
        for index, patch in enumerate(patches):
            if not isinstance(patch, dict):
                errors.append(f"patches[{index}] must be an object.")
                continue

            target = patch.get("target")
            if not isinstance(target, str) or not target:
                errors.append(f"patches[{index}].target must be a non-empty string.")

            content = patch.get("content")
            if content is not None and not isinstance(content, str):
                errors.append(f"patches[{index}].content must be a string when provided.")

            intent = patch.get("intent")
            if intent is not None and intent not in {"create", "update", "overwrite"}:
                errors.append(
                    f"patches[{index}].intent must be one of create, update, overwrite."
                )

    commands = envelope.get("commands")
    if not isinstance(commands, list):
        errors.append("commands must be a list.")
    else:
        for index, command_item in enumerate(commands):
            if not isinstance(command_item, dict):
                errors.append(f"commands[{index}] must be an object.")
                continue

            command = command_item.get("command")
            if not isinstance(command, (str, list)):
                errors.append(f"commands[{index}].command must be a string or a list.")
            elif isinstance(command, list):
                if not command:
                    errors.append(f"commands[{index}].command list must not be empty.")
                elif not all(isinstance(part, str) and part for part in command):
                    errors.append(
                        f"commands[{index}].command list must contain only non-empty strings."
                    )

            timeout_seconds = command_item.get("timeout_seconds")
            if timeout_seconds is not None and not isinstance(timeout_seconds, (int, float)):
                errors.append(f"commands[{index}].timeout_seconds must be a number when provided.")

    if not isinstance(envelope.get("options"), dict):
        errors.append("options must be an object.")

    if not isinstance(envelope.get("meta"), dict):
        errors.append("meta must be an object.")

    return errors


def make_validation_result(envelope: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    """Build a lightweight validation result envelope."""
    ok = not errors

    return {
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "task_id": envelope.get("task_id"),
        "status": "success" if ok else "validation_failed",
        "exit_code": 0 if ok else -6,
        "validation_errors": errors,
        "meta": {
            "mode": "validate_only",
            "executed": False,
            "patch_applied": False,
            "command_executed": False,
        },
    }


def print_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(
        f"task_id={result.get('task_id')} "
        f"status={result.get('status')} "
        f"exit_code={result.get('exit_code')}"
    )

    errors = result.get("validation_errors") or []
    if errors:
        print("validation_errors:")
        for error in errors:
            print(f"- {error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run APOS task envelope JSON")
    parser.add_argument("task_file", help="Path to task envelope JSON file")
    parser.add_argument("--json", action="store_true", help="Print result envelope as JSON")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the task envelope without applying patches or running commands.",
    )
    args = parser.parse_args()

    task_path = Path(args.task_file)
    if not task_path.exists():
        print(f"Task file not found: {task_path}")
        return 1

    try:
        envelope = json.loads(task_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result = {
            "schema_version": SUPPORTED_SCHEMA_VERSION,
            "task_id": None,
            "status": "validation_failed",
            "exit_code": -6,
            "validation_errors": [f"Invalid JSON: {exc}"],
            "meta": {
                "mode": "validate_only" if args.validate_only else "run",
                "executed": False,
            },
        }
        print_result(result, args.json)
        return 1

    if not isinstance(envelope, dict):
        result = {
            "schema_version": SUPPORTED_SCHEMA_VERSION,
            "task_id": None,
            "status": "validation_failed",
            "exit_code": -6,
            "validation_errors": ["Task envelope root must be a JSON object."],
            "meta": {
                "mode": "validate_only" if args.validate_only else "run",
                "executed": False,
            },
        }
        print_result(result, args.json)
        return 1

    if args.validate_only:
        errors = validate_task_envelope(envelope)
        result = make_validation_result(envelope, errors)
        print_result(result, args.json)
        return 0 if not errors else 1

    workspace = envelope.get("workspace_root") or str(PROJECT_ROOT)
    history_db_path = Path(workspace) / ".apos" / "history.sqlite3"

    orch = Orchestrator(workspace_root=workspace, history_db_path=history_db_path)
    try:
        orch.start()
        result = orch.run_task_envelope(envelope)
    finally:
        orch.stop()

    print_result(result, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())