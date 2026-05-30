#!/usr/bin/env python3
"""Generate a safe APOS context pack for the current workspace."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apos_core.context_pack import ContextPackBuilder


def add_context_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--workspace-root", default=str(PROJECT_ROOT), help="Workspace root to scan")
    parser.add_argument("--history-db", default=None, help="Path to the APOS history SQLite database")
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--max-files", type=int, default=120)
    parser.add_argument("--max-file-preview-chars", type=int, default=1200)
    parser.add_argument("--max-total-chars", type=int, default=12000)
    parser.add_argument("--output", default=None, help="Write the rendered context pack to this file")
    parser.add_argument("--format", choices=("json", "markdown"), default=None, help="Render format")
    parser.add_argument("--json", action="store_true", help="Compatibility flag for JSON output")
    return parser


def _resolve_format(command: str, explicit_format: str | None, json_flag: bool) -> str:
    if json_flag:
        return "json"
    if explicit_format:
        return explicit_format
    return "markdown" if command == "inspect" else "json"


def build_context_pack(
    workspace_root: str | Path,
    history_db_path: str | Path | None = None,
    *,
    max_depth: int = 4,
    max_files: int = 120,
    max_file_preview_chars: int = 1200,
    max_total_chars: int = 12000,
) -> dict[str, Any]:
    builder = ContextPackBuilder(workspace_root, history_db_path=history_db_path)
    return builder.build(
        max_depth=max_depth,
        max_files=max_files,
        max_file_preview_chars=max_file_preview_chars,
        max_total_chars=max_total_chars,
    )


def render_context_pack(pack: dict[str, Any], output_format: str = "json") -> str:
    builder = ContextPackBuilder(pack.get("project_root") or ".")
    return builder.write_output(pack, output_format=output_format)


def execute_context_pack(
    *,
    workspace_root: str | Path,
    history_db_path: str | Path | None = None,
    max_depth: int = 4,
    max_files: int = 120,
    max_file_preview_chars: int = 1200,
    max_total_chars: int = 12000,
    output_format: str = "json",
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    pack = build_context_pack(
        workspace_root,
        history_db_path=history_db_path,
        max_depth=max_depth,
        max_files=max_files,
        max_file_preview_chars=max_file_preview_chars,
        max_total_chars=max_total_chars,
    )
    rendered = render_context_pack(pack, output_format=output_format)
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return pack


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an APOS context pack")
    parser.add_argument("command", nargs="?", choices=("build", "inspect"), default="build")
    add_context_arguments(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_format = _resolve_format(args.command, args.format, args.json)
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


if __name__ == "__main__":
    raise SystemExit(main())
