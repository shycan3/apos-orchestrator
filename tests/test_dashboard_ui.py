import json
import tempfile
import gc
from io import BytesIO
from pathlib import Path

from apos_core.orchestrator import Orchestrator
from apos_core.task_envelope import make_task_envelope
from server.list_approvals_endpoint import app as dashboard_app
from wsgiref.util import setup_testing_defaults


def _call_wsgi(app, environ):
    setup_testing_defaults(environ)
    captured = []

    def start_response(status, headers):
        captured.append(status)
        captured.append(headers)

    body = b"".join(app(environ, start_response))
    return captured[0], dict(captured[1]), body


def _make_dashboard_plan(workspace_root: str, task_id: str = "dashboard-plan"):
    return make_task_envelope(
        task_type="plan_only",
        workspace_root=workspace_root,
        created_by="web_llm",
        task_id=task_id,
        patches=[],
        commands=[],
        meta={
            "plan_goal": "exercise dashboard controls",
            "plan_steps": [
                {
                    "title": "Successful step",
                    "task_type": "run",
                    "commands": [
                        {
                            "command": ["python", "-c", "print('step-0')"],
                            "timeout_seconds": 5,
                        }
                    ],
                },
                {
                    "title": "Rejected step",
                    "task_type": "run",
                    "commands": [
                        {
                            "command": ["python", "-c", "print('step-1')"],
                            "timeout_seconds": 5,
                        }
                    ],
                },
                {
                    "title": "Failing step",
                    "task_type": "run",
                    "commands": [
                        {
                            "command": ["python", "-c", "raise SystemExit(4)"],
                            "timeout_seconds": 5,
                        }
                    ],
                },
            ],
        },
    )


def test_dashboard_routes_and_actions():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        history_db = workspace / ".apos" / "history.sqlite3"

        payload = _make_dashboard_plan(str(workspace))
        task_id = payload["task_id"]
        orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db)
        orch.recorder.record_task(task_id, payload)
        orch.stop()

        for route in ("/", "/ui", "/ui/approvals", "/ui/plans"):
            status, headers, body = _call_wsgi(
                dashboard_app,
                {
                    "REQUEST_METHOD": "GET",
                    "PATH_INFO": route,
                    "QUERY_STRING": f"workspace={workspace.as_posix()}",
                    "wsgi.input": BytesIO(b""),
                    "HTTP_HOST": "127.0.0.1",
                },
            )
            assert status.startswith("200")
            html = body.decode("utf-8")
            assert "APOS Dashboard" in html
            assert "data-apos-view" in html
            assert "Build LLM Retry Prompt" in html
            assert "Copy Recovery Prompt" in html
            assert "recoveryPromptTextArea" in html
            assert "This does not auto-run or auto-approve." in html

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
        dashboard = json.loads(body.decode("utf-8"))
        assert dashboard["workspace"] == workspace.as_posix()
        assert dashboard["pending_approvals_count"] == 3
        assert dashboard["failed_items_count"] == 0
        assert len(dashboard["recent_plan_summaries"]) == 1
        assert dashboard["failed_items_summary"] == []

        status, headers, body = _call_wsgi(
            dashboard_app,
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/api/approvals",
                "QUERY_STRING": f"workspace={workspace.as_posix()}&status=pending",
                "wsgi.input": BytesIO(b""),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")
        approvals = json.loads(body.decode("utf-8"))
        assert len(approvals) == 3
        step0_item = next(item for item in approvals if item["step_index"] == 0)
        step1_item = next(item for item in approvals if item["step_index"] == 1)
        step2_item = next(item for item in approvals if item["step_index"] == 2)

        payload_bytes = json.dumps({
            "workspace": str(workspace),
            "item_id": step0_item["id"],
            "approved_by": "alice",
        }).encode("utf-8")
        status, headers, body = _call_wsgi(
            dashboard_app,
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/api/approvals/approve",
                "CONTENT_LENGTH": str(len(payload_bytes)),
                "wsgi.input": BytesIO(payload_bytes),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")
        approved_payload = json.loads(body.decode("utf-8"))
        assert approved_payload["item"]["status"] == "approved"

        payload_bytes = json.dumps({
            "workspace": str(workspace),
            "task_id": task_id,
            "step": 0,
            "approved_by": "alice",
        }).encode("utf-8")
        status, headers, body = _call_wsgi(
            dashboard_app,
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/api/plans/run-step",
                "CONTENT_LENGTH": str(len(payload_bytes)),
                "wsgi.input": BytesIO(payload_bytes),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")
        run_payload = json.loads(body.decode("utf-8"))
        assert run_payload["result"]["status"] == "success"

        payload_bytes = json.dumps({
            "workspace": str(workspace),
            "item_id": step1_item["id"],
            "rejected_by": "bob",
            "reason": "not needed",
        }).encode("utf-8")
        status, headers, body = _call_wsgi(
            dashboard_app,
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/api/approvals/reject",
                "CONTENT_LENGTH": str(len(payload_bytes)),
                "wsgi.input": BytesIO(payload_bytes),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")
        rejected_payload = json.loads(body.decode("utf-8"))
        assert rejected_payload["item"]["status"] == "rejected"

        payload_bytes = json.dumps({
            "workspace": str(workspace),
            "task_id": task_id,
            "step": 2,
            "approved_by": "alice",
        }).encode("utf-8")
        status, headers, body = _call_wsgi(
            dashboard_app,
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/api/plans/approve-step",
                "CONTENT_LENGTH": str(len(payload_bytes)),
                "wsgi.input": BytesIO(payload_bytes),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")

        payload_bytes = json.dumps({
            "workspace": str(workspace),
            "task_id": task_id,
            "step": 2,
            "approved_by": "alice",
        }).encode("utf-8")
        status, headers, body = _call_wsgi(
            dashboard_app,
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/api/plans/run-step",
                "CONTENT_LENGTH": str(len(payload_bytes)),
                "wsgi.input": BytesIO(payload_bytes),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")
        failed_payload = json.loads(body.decode("utf-8"))
        assert failed_payload["result"]["status"] == "failed"
        assert failed_payload["result"]["meta"]["plan_step_index"] == 2

        status, headers, body = _call_wsgi(
            dashboard_app,
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/api/approvals",
                "QUERY_STRING": f"workspace={workspace.as_posix()}&id={step0_item['id']}",
                "wsgi.input": BytesIO(b""),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")
        approval_detail = json.loads(body.decode("utf-8"))
        assert approval_detail["latest_result"]["exit_code"] == 0
        assert "step-0" in approval_detail["latest_result"]["stdout"]

        status, headers, body = _call_wsgi(
            dashboard_app,
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/api/approvals",
                "QUERY_STRING": f"workspace={workspace.as_posix()}&id={step2_item['id']}",
                "wsgi.input": BytesIO(b""),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")
        failed_detail = json.loads(body.decode("utf-8"))
        assert failed_detail["latest_result"]["exit_code"] == 4
        assert failed_detail["failure_detail"]["summary"]
        assert failed_detail["recommended_human_action"]
        assert failed_detail["recovery_prompt"]["prompt_text"]

        status, headers, body = _call_wsgi(
            dashboard_app,
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/api/plans",
                "QUERY_STRING": f"workspace={workspace.as_posix()}&id={task_id}",
                "wsgi.input": BytesIO(b""),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("200")
        plan_detail = json.loads(body.decode("utf-8"))
        assert plan_detail["steps"][0]["status"] == "executed"
        assert plan_detail["steps"][1]["status"] == "rejected"
        assert plan_detail["steps"][2]["status"] == "failed"
        assert plan_detail["steps"][0]["result"]["status"] == "success"
        assert plan_detail["steps"][2]["result"]["status"] == "failed"

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
        dashboard_after = json.loads(body.decode("utf-8"))
        assert dashboard_after["pending_approvals_count"] == 0
        assert dashboard_after["failed_items_count"] >= 1
        assert len(dashboard_after["recent_executed_items"]) >= 1
        assert dashboard_after["failed_items_summary"][0]["failure_summary"]
        assert dashboard_after["failed_items_summary"][0]["recommended_recovery_prompt"]

        status, headers, body = _call_wsgi(
            dashboard_app,
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/api/plans",
                "QUERY_STRING": f"workspace={workspace.as_posix()}&id=missing",
                "wsgi.input": BytesIO(b""),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("404")

        gc.collect()

        status, headers, body = _call_wsgi(
            dashboard_app,
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/api/approvals",
                "QUERY_STRING": f"workspace={workspace.as_posix()}&id=missing",
                "wsgi.input": BytesIO(b""),
                "HTTP_HOST": "127.0.0.1",
            },
        )
        assert status.startswith("404")
