import asyncio
import hashlib
import json
import tempfile
from io import BytesIO
from pathlib import Path

from wsgiref.util import setup_testing_defaults

from apos_core.orchestrator import Orchestrator
from apos_core.task_envelope import make_task_envelope
from server.approve_endpoint import app as approve_app
from server.list_approvals_endpoint import app as approvals_app
from server import apos_server


REPO_ROOT = Path(__file__).resolve().parent.parent


def _call_wsgi(app, environ):
    setup_testing_defaults(environ)
    captured = []

    def start_response(status, headers):
        captured.append(status)
        captured.append(headers)

    body = b"".join(app(environ, start_response))
    return captured[0], dict(captured[1]), body


def _make_plan_only_envelope(workspace_root: str, task_id: str = "approval-queue-demo"):
    return make_task_envelope(
        task_type="plan_only",
        workspace_root=workspace_root,
        created_by="web_llm",
        task_id=task_id,
        patches=[],
        commands=[],
        meta={
            "plan_goal": "exercise approval queue",
            "plan_steps": [
                {
                    "title": "Write queue demo file",
                    "task_type": "patch_and_run",
                    "patches": [
                        {
                            "target": "workspace/approval_queue_demo.py",
                            "language": "python",
                            "intent": "update",
                            "content": "print('approval queue demo')\n",
                        }
                    ],
                    "commands": [],
                },
                {
                    "title": "Run a failing command",
                    "task_type": "run",
                    "commands": [
                        {
                            "command": ["python", "-c", "import sys; sys.exit(3)"],
                            "timeout_seconds": 5,
                        }
                    ],
                },
            ],
        },
    )


def test_plan_only_queue_list_show_approve_reject_and_status_updates():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = workspace / ".apos" / "history.sqlite3"

        payload = _make_plan_only_envelope(str(workspace))
        task_id = payload["task_id"]

        orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db)
        orch.recorder.record_task(task_id, payload)
        orch.stop()

        status, headers, body = _call_wsgi(
            approvals_app,
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/approvals",
                "QUERY_STRING": f"workspace={workspace.as_posix()}&task_id={task_id}&status=pending",
                "wsgi.input": BytesIO(b""),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")
        items = json.loads(body.decode("utf-8"))
        assert len(items) == 2
        first_item = next(item for item in items if item["step_index"] == 0)
        second_item = next(item for item in items if item["step_index"] == 1)
        first_item_id = first_item["id"]
        second_item_id = second_item["id"]

        status, headers, body = _call_wsgi(
            approvals_app,
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/approvals",
                "QUERY_STRING": f"workspace={workspace.as_posix()}&id={first_item_id}",
                "wsgi.input": BytesIO(b""),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")
        item = json.loads(body.decode("utf-8"))
        assert item["id"] == first_item_id
        assert item["status"] == "pending"
        assert item["task_id"] == task_id

        status, headers, body = _call_wsgi(
            approve_app,
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/approve",
                "CONTENT_LENGTH": "0",
                "wsgi.input": BytesIO(b""),
            },
        )
        assert status.startswith("400")

        payload_bytes = json.dumps({
            "workspace": str(workspace),
            "item_id": first_item_id,
            "approved_by": "alice",
        }).encode("utf-8")
        status, headers, body = _call_wsgi(
            approve_app,
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/approve",
                "CONTENT_LENGTH": str(len(payload_bytes)),
                "wsgi.input": BytesIO(payload_bytes),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")
        approved_item = json.loads(body.decode("utf-8"))["item"]
        assert approved_item["status"] == "approved"
        assert approved_item["decided_by"] == "alice"

        payload_bytes = json.dumps({
            "workspace": str(workspace),
            "task_id": task_id,
            "step": 0,
            "approved_by": "alice",
        }).encode("utf-8")
        status, headers, body = _call_wsgi(
            approve_app,
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/approve",
                "CONTENT_LENGTH": str(len(payload_bytes)),
                "wsgi.input": BytesIO(payload_bytes),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")
        result = json.loads(body.decode("utf-8"))
        assert result["status"] == "success"
        assert result["meta"]["plan_step_index"] == 0

        payload_bytes = json.dumps({
            "workspace": str(workspace),
            "item_id": second_item_id,
            "rejected_by": "bob",
            "reason": "not needed",
        }).encode("utf-8")
        status, headers, body = _call_wsgi(
            approve_app,
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/reject",
                "CONTENT_LENGTH": str(len(payload_bytes)),
                "wsgi.input": BytesIO(payload_bytes),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")
        rejected_item = json.loads(body.decode("utf-8"))["item"]
        assert rejected_item["status"] == "rejected"
        assert rejected_item["decided_by"] == "bob"

        status, headers, body = _call_wsgi(
            approvals_app,
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/approvals",
                "QUERY_STRING": f"workspace={workspace.as_posix()}&id={second_item_id}",
                "wsgi.input": BytesIO(b""),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")
        rejected_lookup = json.loads(body.decode("utf-8"))
        assert rejected_lookup["status"] == "rejected"

        orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db)
        duplicate_reject = orch.reject_pending_approval(second_item_id, rejected_by="bob", reason="again")
        orch.stop()
        assert duplicate_reject["status"] == "rejected"

        status, headers, body = _call_wsgi(
            approvals_app,
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/approvals",
                "QUERY_STRING": f"workspace={workspace.as_posix()}&id=missing-id",
                "wsgi.input": BytesIO(b""),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("404")


def test_bridge_patch_queue_reject_and_commit_status_updates():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "workspace").mkdir(parents=True, exist_ok=True)

        apos_server.PENDING_PATCHES.clear()
        apos_server.COMMITTED_PATCH_IDS.clear()

        source = "def main():\n    print('bridge demo')\n\n\nif __name__ == '__main__':\n    main()\n"
        payload = {
            "type": "propose_patch",
            "patch_id": "bridge-demo-1",
            "project_root": str(root),
            "target": "workspace/bridge_demo.py",
            "language": "python",
            "content": source,
            "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        }

        response = asyncio.run(apos_server.handle_message(json.dumps(payload)))
        response_payload = json.loads(response)
        assert response_payload["type"] == "validation_passed"

        orch = Orchestrator(workspace_root=str(root), history_db_path=root / ".apos" / "history.sqlite3")
        recorder = orch.recorder
        item = recorder.get_approval_item("bridge-demo-1")
        assert item is not None
        assert item["status"] == "pending"

        reject_response = asyncio.run(
            apos_server.handle_message(json.dumps({"type": "reject_patch", "patch_id": "bridge-demo-1", "rejected_by": "tester"}))
        )
        reject_payload = json.loads(reject_response)
        assert reject_payload["type"] == "rejected"

        item = recorder.get_approval_item("bridge-demo-1")
        assert item["status"] == "rejected"

        commit_response = asyncio.run(
            apos_server.handle_message(json.dumps({"type": "commit_patch", "patch_id": "bridge-demo-1"}))
        )
        commit_payload = json.loads(commit_response)
        assert commit_payload["type"] == "error"
        assert commit_payload["error_kind"] == "patch_not_found" or commit_payload["error_kind"] == "patch_rejected"
        try:
            bridge_recorder = apos_server.PROJECT_RECORDERS.get(str(root.resolve()))
            if bridge_recorder:
                bridge_recorder.close()
        finally:
            apos_server.PROJECT_RECORDERS.clear()
        orch.stop()


def test_invalid_approval_item_ids_return_clean_errors():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = workspace / ".apos" / "history.sqlite3"

        orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db)
        orch.recorder.record_task(
            "invalid-id-demo",
            _make_plan_only_envelope(str(workspace), task_id="invalid-id-demo"),
        )

        assert orch.get_pending_approval("missing") is None
        assert orch.approve_pending_approval("missing", approved_by="alice") is None
        assert orch.reject_pending_approval("missing", rejected_by="bob") is None

        status, headers, body = _call_wsgi(
            approve_app,
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/reject",
                "CONTENT_LENGTH": str(len(json.dumps({"workspace": str(workspace), "item_id": "missing"}).encode("utf-8"))),
                "wsgi.input": BytesIO(json.dumps({"workspace": str(workspace), "item_id": "missing"}).encode("utf-8")),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("404")
        orch.stop()
