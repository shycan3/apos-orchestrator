import asyncio
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from server import apos_server


REPO_ROOT = Path(__file__).resolve().parent.parent


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def _extract_apos_patch_example() -> tuple[dict, str]:
    text = (REPO_ROOT / "examples" / "apos_patch_demo.md").read_text(encoding="utf-8")
    match = re.search(r"```apos-patch\s*(\{.*?\})\s*```\s*```python\s*(.*?)\s*```", text, re.S)
    assert match is not None
    metadata = json.loads(match.group(1))
    source = match.group(2)
    return metadata, source


def test_validate_only_demo_example_validates_cleanly():
    proc = _run_cli(["cli/run_task.py", "examples/validate_only_demo.json", "--validate-only", "--json"])

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "success"
    assert payload["exit_code"] == 0


def test_preview_patch_demo_example_generates_preview_without_writing():
    proc = _run_cli(["cli/run_task.py", "examples/preview_patch_demo.json", "--json"])

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "success"
    assert payload["patch_applied"] is False
    assert isinstance(payload.get("patch_preview"), list)
    assert payload["patch_preview"][0]["operation"] == "create"


def test_apos_patch_demo_round_trip_validates_and_commits():
    metadata, source = _extract_apos_patch_example()
    assert metadata["project_root"] == "C:/Users/DO/Documents/apos-orchestrator"
    assert metadata["target"] == "workspace/approved_demo.py"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "workspace").mkdir(parents=True, exist_ok=True)

        apos_server.PENDING_PATCHES.clear()
        apos_server.COMMITTED_PATCH_IDS.clear()

        payload = dict(metadata)
        payload["project_root"] = str(root)
        payload["content"] = source
        payload["sha256"] = hashlib.sha256(source.encode("utf-8")).hexdigest()
        payload["type"] = "propose_patch"

        response = asyncio.run(apos_server.handle_message(json.dumps(payload)))
        response_payload = json.loads(response)
        assert response_payload["type"] == "validation_passed"

        commit_response = asyncio.run(
            apos_server.handle_message(json.dumps({"type": "commit_patch", "patch_id": metadata["patch_id"]}))
        )
        commit_payload = json.loads(commit_response)
        assert commit_payload["type"] == "commit_succeeded"

        written = root / "workspace" / "approved_demo.py"
        assert written.exists()
        assert written.read_text(encoding="utf-8") == source
        bridge_recorder = apos_server.PROJECT_RECORDERS.get(str(root.resolve()))
        if bridge_recorder:
            bridge_recorder.close()
        apos_server.PROJECT_RECORDERS.clear()