"""Lightweight HTTP endpoint to approve and execute a plan step.

POST /approve
Content-Type: application/json
{
  "task_id": "plan-123",
  "workspace": "./workspace",
  "step": 0,
  "approved_by": "alice",
  "json": true
}

Response: 200 JSON result_envelope on success, 4xx on error.

This is intentionally minimal and uses the built-in wsgiref.simple_server + Flask-like routing
without external dependencies to keep the repo lightweight.
"""
from __future__ import annotations

import json
from wsgiref.simple_server import make_server
from urllib.parse import parse_qs
from typing import Tuple
from pathlib import Path
import sys
import os

# ensure project root is on sys.path when run as script
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apos_core.orchestrator import Orchestrator

# Optional token for simple auth: set APOS_APPROVE_TOKEN in environment to require
# clients include header `X-APOS-Approve-Token: <token>` when calling /approve.
REQUIRED_TOKEN = os.environ.get("APOS_APPROVE_TOKEN")


def _read_json_from_environ(environ) -> Tuple[dict, int]:
    try:
        length = int(environ.get('CONTENT_LENGTH') or 0)
    except Exception:
        length = 0
    body = environ['wsgi.input'].read(length) if length else b''
    if not body:
        return {}, 400
    try:
        payload = json.loads(body.decode('utf-8'))
    except Exception:
        return {}, 400
    return payload, 200


def app(environ, start_response):
    path = environ.get('PATH_INFO', '/')
    method = environ.get('REQUEST_METHOD', 'GET')

    if path == '/approve' and method == 'POST':
        # simple token check (optional)
        if REQUIRED_TOKEN:
            # WSGI exposes headers as HTTP_<HEADER_NAME>
            supplied = environ.get('HTTP_X_APOS_APPROVE_TOKEN')
            if supplied != REQUIRED_TOKEN:
                start_response('401 Unauthorized', [('Content-Type', 'application/json')])
                return [json.dumps({'error': 'unauthorized'}).encode('utf-8')]

        payload, code = _read_json_from_environ(environ)
        if code != 200:
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'invalid_json'}).encode('utf-8')]

        task_id = payload.get('task_id')
        workspace = payload.get('workspace')
        step = payload.get('step', 0)
        approved_by = payload.get('approved_by')

        if not task_id or not workspace:
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'task_id_and_workspace_required'}).encode('utf-8')]

        try:
            orch = Orchestrator(workspace_root=workspace, history_db_path=f"{workspace}/.apos/history.sqlite3")
            result = orch.execute_plan_step(task_id, int(step), approved_by=approved_by)
            # close recorder
            try:
                orch.stop()
            except Exception:
                pass
            start_response('200 OK', [('Content-Type', 'application/json')])
            return [json.dumps(result, ensure_ascii=False).encode('utf-8')]
        except Exception as exc:
            start_response('500 Internal Server Error', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'internal_error', 'message': str(exc)}).encode('utf-8')]

    # basic health
    if path == '/health':
        start_response('200 OK', [('Content-Type', 'application/json')])
        return [json.dumps({'ok': True}).encode('utf-8')]

    start_response('404 Not Found', [('Content-Type', 'application/json')])
    return [json.dumps({'error': 'not_found'}).encode('utf-8')]


if __name__ == '__main__':
    with make_server('127.0.0.1', 8081, app) as httpd:
        print('Approve endpoint listening on http://127.0.0.1:8081')
        httpd.serve_forever()
