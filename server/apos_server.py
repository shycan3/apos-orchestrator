#!/usr/bin/env python3
"""
APOS v3.2 local WebSocket validation backend.

Web LLMs propose patches. This server validates paths, hashes, language
syntax, and protection zones. It writes direct-candidate files only after a
separate commit_patch request.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import py_compile
import re
import secrets
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
except ImportError:
    print(
        "Missing dependency: websockets\nInstall with:\n  python -m pip install websockets",
        file=sys.stderr,
    )
    raise SystemExit(1)


HOST = "127.0.0.1"
PORT = 8765

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}

PROTECTED_PREFIXES = (
    "specifications/",
    "context/",
    ".apos/",
    ".codex/",
)

DIRECT_WRITE_ALLOWED_PREFIXES = (
    "workspace/",
    "src/",
    "app/",
    "scripts/",
    "tests/",
)

MAX_CONTENT_BYTES = 2_000_000
PATCH_TTL_SECONDS = 60 * 30
PATCH_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")



@dataclass(frozen=True)
class PatchRequest:
    patch_id: str
    project_root: Path
    target: str
    language: str
    content: str
    sha256: str


@dataclass(frozen=True)
class PendingPatch:
    patch_id: str
    project_root: Path
    target: str
    target_path: Path
    language: str
    content: str
    sha256: str
    zone: str
    created_at: float


PENDING_PATCHES: Dict[str, PendingPatch] = {}
COMMITTED_PATCH_IDS: Dict[str, float] = {}


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def json_response(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def error_response(
    patch_id: Optional[str],
    error_kind: str,
    message: str,
    retry_allowed: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    payload: Dict[str, Any] = {
        "type": "error",
        "patch_id": patch_id,
        "error_kind": error_kind,
        "message": message,
        "retry_allowed": retry_allowed,
    }
    if extra:
        payload.update(extra)
    return json_response(payload)


def normalize_target(target: str) -> str:
    return target.replace("\\", "/").strip()


def sanitize_project_root(project_root_raw: str) -> Path:
    if not isinstance(project_root_raw, str) or not project_root_raw.strip():
        raise ValueError("project_root is required")

    if "\x00" in project_root_raw:
        raise ValueError("Null byte in project_root is forbidden")

    project_root = Path(project_root_raw).expanduser().resolve()
    if not project_root.exists():
        raise ValueError(f"project_root does not exist: {project_root}")
    if not project_root.is_dir():
        raise ValueError(f"project_root is not a directory: {project_root}")
    return project_root


def sanitize_target_path(project_root: Path, target: str) -> Path:
    if not isinstance(target, str) or not target.strip():
        raise ValueError("target is required")

    if target.startswith("/") or target.startswith("\\"):
        raise ValueError("Absolute target paths are forbidden")

    if "\x00" in target:
        raise ValueError("Null byte in target path is forbidden")

    normalized = normalize_target(target)
    if normalized in {".", ".."}:
        raise ValueError("Invalid target path")

    if normalized.startswith("../") or "/../" in normalized:
        raise ValueError("Path traversal is forbidden")

    if normalized.startswith("./"):
        normalized = normalized[2:]

    root_resolved = project_root.resolve()
    target_resolved = (root_resolved / normalized).resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("Target path escapes project root") from exc

    return target_resolved


def classify_write_target(target: str) -> str:
    normalized = normalize_target(target)
    if normalized.startswith(PROTECTED_PREFIXES):
        return "protected"
    if normalized.startswith(DIRECT_WRITE_ALLOWED_PREFIXES):
        return "direct_candidate"
    return "not_allowed"


def compute_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def validate_sha256(content: str, expected: str) -> None:
    if not expected:
        raise ValueError("sha256 is required")
    actual = compute_sha256(content)
    if not secrets.compare_digest(actual, expected):
        print(
            f"APOS sha256 mismatch: expected={expected}, actual={actual}",
            file=sys.stderr,
        )
        raise ValueError("sha256 mismatch")


def parse_patch_request(data: Dict[str, Any]) -> PatchRequest:
    patch_id = str(data.get("patch_id", "")).strip()
    project_root_raw = data.get("project_root", "")
    target = str(data.get("target", "")).strip()
    language = str(data.get("language", "")).strip().lower()
    content = data.get("content", "")
    sha256 = str(data.get("sha256", "")).strip()

    if not patch_id:
        raise ValueError("patch_id is required")
    if not PATCH_ID_PATTERN.fullmatch(patch_id):
        raise ValueError("patch_id must match ^[A-Za-z0-9_-]{1,128}$")
    if not isinstance(content, str):
        raise ValueError("content must be a string")
    if len(content.encode("utf-8")) > MAX_CONTENT_BYTES:
        raise ValueError(f"content exceeds max size: {MAX_CONTENT_BYTES} bytes")

    project_root = sanitize_project_root(str(project_root_raw))
    validate_sha256(content, sha256)

    return PatchRequest(
        patch_id=patch_id,
        project_root=project_root,
        target=target,
        language=language,
        content=content,
        sha256=sha256,
    )


def validate_python_source(source: str) -> Dict[str, Any]:
    temp_path: Optional[str] = None
    pyc_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
            newline="\n",
        ) as temp_file:
            temp_file.write(source)
            temp_path = temp_file.name

        with tempfile.NamedTemporaryFile(suffix=".pyc", delete=False) as pyc_file:
            pyc_path = pyc_file.name

        py_compile.compile(temp_path, cfile=pyc_path, doraise=True)
        return {"ok": True}
    except py_compile.PyCompileError as exc:
        message = getattr(exc, "msg", None) or str(exc)
        if temp_path:
            message = message.replace(temp_path, "<source>")
        return {
            "ok": False,
            "error_kind": "python_syntax_error",
            "stderr": message,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error_kind": "python_validation_internal_error",
            "stderr": f"{type(exc).__name__}: {exc}",
        }
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        if pyc_path:
            try:
                os.unlink(pyc_path)
            except OSError:
                pass


def sanitize_fence_language(language: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_+-]", "", str(language or "").strip().lower())
    return sanitized[:32] or "text"


def sanitize_for_markdown_inline(value: str, max_len: int = 256) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = text.replace("`", "")
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def render_markdown_fenced_block(language: str, content: str) -> str:
    fence = "```"
    while fence in content:
        fence += "`"
    return "\n".join([f"{fence}{language}", content, fence])


def validate_content_by_language(language: str, content: str) -> Dict[str, Any]:
    if language in {"python", "py"}:
        return validate_python_source(content)
    if language in {"text", "txt", "md", "markdown", "json", "javascript", "js", "typescript", "ts", ""}:
        return {"ok": True}
    return {
        "ok": False,
        "error_kind": "unsupported_language",
        "stderr": f"Unsupported language: {language}",
    }


def append_protected_write_report(req: PatchRequest, target_path: Path, validation: Dict[str, Any]) -> Path:
    scratchpad = req.project_root / "workspace" / "scratchpad.md"
    scratchpad.parent.mkdir(parents=True, exist_ok=True)
    safe_patch_id = sanitize_for_markdown_inline(req.patch_id, max_len=128)
    safe_target = sanitize_for_markdown_inline(req.target, max_len=256)
    safe_target_path = sanitize_for_markdown_inline(str(target_path), max_len=256)
    safe_language = sanitize_fence_language(req.language)
    fenced_content = render_markdown_fenced_block(safe_language, req.content)
    report = f"""
## Protected Write Proposal

Generated: {now_iso()}
Patch ID: `{safe_patch_id}`
Target: `{safe_target}`
Resolved Target: `{safe_target_path}`
Language: `{safe_language}`
Validation: `{validation.get("ok")}`

APOS policy blocked a direct write to a protected area. Human Architect review is required.

{fenced_content}
"""
    with scratchpad.open("a", encoding="utf-8", newline="\n") as file:
        file.write("\n" + report.strip() + "\n")
    return scratchpad


def cleanup_expired_patches() -> None:
    loop_time = asyncio.get_running_loop().time()
    expired = [
        patch_id
        for patch_id, patch in PENDING_PATCHES.items()
        if loop_time - patch.created_at > PATCH_TTL_SECONDS
    ]
    for patch_id in expired:
        PENDING_PATCHES.pop(patch_id, None)

    expired_committed = [
        patch_id
        for patch_id, committed_at in COMMITTED_PATCH_IDS.items()
        if loop_time - committed_at > PATCH_TTL_SECONDS
    ]
    for patch_id in expired_committed:
        COMMITTED_PATCH_IDS.pop(patch_id, None)


async def handle_propose_patch(data: Dict[str, Any]) -> str:
    cleanup_expired_patches()

    try:
        req = parse_patch_request(data)
        target_path = sanitize_target_path(req.project_root, req.target)
        zone = classify_write_target(req.target)
    except ValueError as exc:
        return error_response(
            patch_id=str(data.get("patch_id", "") or ""),
            error_kind="bad_request",
            message=str(exc),
            retry_allowed=False,
        )

    if req.patch_id in PENDING_PATCHES or req.patch_id in COMMITTED_PATCH_IDS:
        return error_response(
            patch_id=req.patch_id,
            error_kind="duplicate_patch_id",
            message="patch_id has already been used",
            retry_allowed=False,
        )

    validation = validate_content_by_language(req.language, req.content)
    if not validation.get("ok"):
        return json_response(
            {
                "type": "validation_failed",
                "patch_id": req.patch_id,
                "error_kind": validation.get("error_kind", "validation_failed"),
                "stderr": validation.get("stderr", ""),
                "retry_allowed": True,
            }
        )

    if zone == "protected":
        scratchpad = append_protected_write_report(req, target_path, validation)
        return json_response(
            {
                "type": "protected_write_redirected",
                "patch_id": req.patch_id,
                "target": req.target,
                "zone": zone,
                "message": "Protected write blocked. Proposal was appended to workspace/scratchpad.md.",
                "scratchpad": str(scratchpad),
            }
        )

    if zone != "direct_candidate":
        return json_response(
            {
                "type": "validation_failed",
                "patch_id": req.patch_id,
                "error_kind": "target_not_allowed",
                "stderr": "target must be under workspace/, src/, app/, scripts/, or tests/",
                "retry_allowed": False,
            }
        )

    PENDING_PATCHES[req.patch_id] = PendingPatch(
        patch_id=req.patch_id,
        project_root=req.project_root,
        target=req.target,
        target_path=target_path,
        language=req.language,
        content=req.content,
        sha256=req.sha256,
        zone=zone,
        created_at=asyncio.get_running_loop().time(),
    )

    return json_response(
        {
            "type": "validation_passed",
            "patch_id": req.patch_id,
            "target": req.target,
            "zone": zone,
            "message": "Validation passed. Waiting for human sign-off.",
        }
    )


async def handle_commit_patch(data: Dict[str, Any]) -> str:
    cleanup_expired_patches()
    patch_id = str(data.get("patch_id", "")).strip()
    if not patch_id:
        return error_response(None, "bad_request", "patch_id is required", retry_allowed=False)

    pending = PENDING_PATCHES.get(patch_id)
    if not pending:
        return error_response(
            patch_id=patch_id,
            error_kind="patch_not_found",
            message="No validated pending patch found for patch_id",
            retry_allowed=False,
        )

    try:
        revalidated_path = sanitize_target_path(pending.project_root, pending.target)
        zone = classify_write_target(pending.target)
        if zone != "direct_candidate":
            PENDING_PATCHES.pop(patch_id, None)
            return error_response(
                patch_id=patch_id,
                error_kind="target_no_longer_allowed",
                message="Target is not a direct candidate at commit time",
                retry_allowed=False,
            )
        if revalidated_path != pending.target_path:
            PENDING_PATCHES.pop(patch_id, None)
            return error_response(
                patch_id=patch_id,
                error_kind="target_path_changed",
                message="Resolved target path changed between validation and commit",
                retry_allowed=False,
            )

        validation = validate_content_by_language(pending.language, pending.content)
        if not validation.get("ok"):
            PENDING_PATCHES.pop(patch_id, None)
            return json_response(
                {
                    "type": "validation_failed",
                    "patch_id": patch_id,
                    "error_kind": validation.get("error_kind", "validation_failed"),
                    "stderr": validation.get("stderr", ""),
                    "retry_allowed": True,
                }
            )

        pending.target_path.parent.mkdir(parents=True, exist_ok=True)
        pending.target_path.write_text(pending.content, encoding="utf-8", newline="\n")
        PENDING_PATCHES.pop(patch_id, None)
        COMMITTED_PATCH_IDS[patch_id] = asyncio.get_running_loop().time()

        return json_response(
            {
                "type": "commit_succeeded",
                "patch_id": patch_id,
                "target": pending.target,
            }
        )
    except Exception as exc:
        PENDING_PATCHES.pop(patch_id, None)
        return error_response(
            patch_id=patch_id,
            error_kind="commit_failed",
            message=f"{type(exc).__name__}: {exc}",
            retry_allowed=False,
        )


async def handle_message(message: str) -> str:
    try:
        data = json.loads(message)
    except json.JSONDecodeError as exc:
        return error_response(None, "invalid_json", str(exc), retry_allowed=False)

    if not isinstance(data, dict):
        return error_response(None, "invalid_payload", "Payload must be a JSON object", retry_allowed=False)

    message_type = data.get("type")
    if message_type == "propose_patch":
        return await handle_propose_patch(data)
    if message_type == "commit_patch":
        return await handle_commit_patch(data)
    if message_type == "ping":
        return json_response(
            {
                "type": "pong",
                "message": "APOS local server alive",
                "pending_patches": len(PENDING_PATCHES),
            }
        )

    return error_response(
        patch_id=str(data.get("patch_id", "") or ""),
        error_kind="unknown_message_type",
        message=f"Unknown message type: {message_type}",
        retry_allowed=False,
    )


async def websocket_handler(websocket: WebSocketServerProtocol) -> None:
    remote = websocket.remote_address
    host = remote[0] if isinstance(remote, tuple) and remote else ""
    if host not in LOCAL_HOSTS:
        await websocket.close(code=1008, reason="Non-local connections are forbidden")
        return

    async for message in websocket:
        if not isinstance(message, str):
            await websocket.send(error_response(None, "binary_payload_forbidden", "Only text JSON messages are allowed"))
            continue
        response = await handle_message(message)
        await websocket.send(response)


async def run_server(host: str, port: int) -> None:
    if host not in LOCAL_HOSTS:
        raise ValueError("APOS server may bind to localhost only")

    async with websockets.serve(websocket_handler, host, port, max_size=MAX_CONTENT_BYTES * 2):
        print(f"APOS local websocket server listening on ws://{host}:{port}")
        await asyncio.Future()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="APOS v3.2 local WebSocket validation backend")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", default=PORT, type=int)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        asyncio.run(run_server(args.host, args.port))
    except KeyboardInterrupt:
        print("APOS server stopped")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
