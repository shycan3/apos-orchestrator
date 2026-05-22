"""Task envelope schema and validation for APOS."""
from __future__ import annotations

import uuid
from typing import Any, Dict


TASK_SCHEMA_VERSION = "1.0"

ALLOWED_TASK_TYPES = {"run", "patch_and_run", "preview_patch", "restore_file"}
ALLOWED_CREATED_BY = {"user", "web_llm", "local_agent"}
ALLOWED_PATCH_INTENTS = {"create", "update", "overwrite", "search_and_replace"}


def default_options() -> Dict[str, Any]:
    return {
        "enable_snapshots": False,
        "enable_patch_dry_run": True,
        "enable_command_policy": True,
        "fail_on_snapshot_error": True,
        "stop_on_first_failure": True,
    }


def make_task_envelope(
    *,
    task_type: str,
    workspace_root: str,
    created_by: str = "user",
    task_id: str | None = None,
    patches: list | None = None,
    commands: list | None = None,
    options: dict | None = None,
    meta: dict | None = None,
) -> Dict[str, Any]:
    merged_options = default_options()
    if options:
        merged_options.update(options)

    return {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task_id or str(uuid.uuid4()),
        "task_type": task_type,
        "created_by": created_by,
        "workspace_root": workspace_root,
        "patches": patches or [],
        "commands": commands or [],
        "options": merged_options,
        "meta": meta or {},
    }


def validate_task_envelope(envelope: dict) -> Dict[str, Any]:
    errors: list[str] = []
    required = [
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

    if not isinstance(envelope, dict):
        return {"ok": False, "errors": ["envelope_must_be_dict"], "normalized": None}

    for key in required:
        if key not in envelope:
            errors.append(f"missing_required_field:{key}")

    if errors:
        return {"ok": False, "errors": errors, "normalized": None}

    if envelope.get("schema_version") != TASK_SCHEMA_VERSION:
        errors.append("unsupported_schema_version")

    if envelope.get("task_type") not in ALLOWED_TASK_TYPES:
        errors.append("invalid_task_type")

    if envelope.get("created_by") not in ALLOWED_CREATED_BY:
        errors.append("invalid_created_by")

    if not isinstance(envelope.get("patches"), list):
        errors.append("patches_must_be_list")

    if not isinstance(envelope.get("commands"), list):
        errors.append("commands_must_be_list")

    if not isinstance(envelope.get("options"), dict):
        errors.append("options_must_be_dict")

    if not isinstance(envelope.get("meta"), dict):
        errors.append("meta_must_be_dict")

    if not isinstance(envelope.get("workspace_root"), str):
        errors.append("workspace_root_must_be_string")

    for i, patch in enumerate(envelope.get("patches", [])):
        if not isinstance(patch, dict):
            errors.append(f"patch_{i}_must_be_dict")
            continue
        target = patch.get("target")
        if not isinstance(target, str):
            errors.append(f"patch_{i}_target_must_be_string")
        intent = patch.get("intent")
        if intent not in ALLOWED_PATCH_INTENTS:
            errors.append(f"patch_{i}_invalid_intent")
        if not isinstance(patch.get("content", ""), str):
            errors.append(f"patch_{i}_content_must_be_string")
        if intent == "search_and_replace":
            if not isinstance(target, str) or not target.strip():
                errors.append(f"patch_{i}_target_must_be_non_empty_string")
            search = patch.get("search")
            if not isinstance(search, str) or not search:
                errors.append(f"patch_{i}_search_must_be_non_empty_string")
            if not isinstance(patch.get("replace"), str):
                errors.append(f"patch_{i}_replace_must_be_string")

    for i, cmd in enumerate(envelope.get("commands", [])):
        if not isinstance(cmd, dict):
            errors.append(f"command_{i}_must_be_dict")
            continue
        command_value = cmd.get("command")
        if not isinstance(command_value, (str, list)):
            errors.append(f"command_{i}_command_must_be_str_or_list")
        timeout = cmd.get("timeout_seconds", 30)
        if not isinstance(timeout, int) or timeout <= 0:
            errors.append(f"command_{i}_timeout_seconds_must_be_positive_int")

    if errors:
        return {"ok": False, "errors": errors, "normalized": None}

    normalized = dict(envelope)
    merged_options = default_options()
    merged_options.update(normalized.get("options", {}))
    normalized["options"] = merged_options

    return {"ok": True, "errors": [], "normalized": normalized}


def envelope_to_task(normalized_envelope: dict) -> dict:
    patches = []
    for p in normalized_envelope.get("patches", []):
        intent = p.get("intent")
        action = "modify"
        if intent == "create":
            action = "create"
        elif intent == "overwrite":
            action = "create"
        elif intent == "update":
            action = "modify"
        elif intent == "search_and_replace":
            action = "search_and_replace"

        patch = {
            "path": p.get("target"),
            "action": action,
            "content": p.get("content", ""),
        }
        if intent == "search_and_replace":
            patch["search"] = p.get("search", "")
            patch["replace"] = p.get("replace", "")

        patches.append(patch)

    commands = normalized_envelope.get("commands", [])
    command = commands[0].get("command") if commands else None
    timeout = commands[0].get("timeout_seconds", 30) if commands else 30

    return {
        "id": normalized_envelope.get("task_id"),
        "patches": patches,
        "command": command,
        "timeout": timeout,
        "task_type": normalized_envelope.get("task_type"),
        "meta": normalized_envelope.get("meta", {}),
    }
