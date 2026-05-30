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
import time
import hmac
import hashlib

# ensure project root is on sys.path when run as script
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apos_core.orchestrator import Orchestrator

# Optional token for auth: set APOS_APPROVE_TOKEN in environment to require
# clients either present header `X-APOS-Approve-Token: <token>` OR a
# timestamped HMAC signature using that token as the shared secret.
# Signature scheme: HMAC_SHA256(token, timestamp + '.' + raw_body) hex
# and include headers `X-APOS-Timestamp` and `X-APOS-Signature`.
REQUIRED_TOKEN = os.environ.get("APOS_APPROVE_TOKEN")
SIGNATURE_WINDOW = int(os.environ.get("APOS_APPROVE_SIGNATURE_WINDOW", "300"))


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


def _resolve_item_id(payload: dict) -> str:
    item_id = str(payload.get('item_id') or payload.get('id') or payload.get('patch_id') or '').strip()
    if item_id:
        return item_id
    task_id = str(payload.get('task_id') or '').strip()
    step = payload.get('step')
    if task_id and step is not None:
        return f'{task_id}:step:{int(step)}'
    return ''


def app(environ, start_response):
    path = environ.get('PATH_INFO', '/')
    method = environ.get('REQUEST_METHOD', 'GET')

    if path == '/approve' and method == 'POST':
        # read raw body first for signature verification
        try:
            length = int(environ.get('CONTENT_LENGTH') or 0)
        except Exception:
            length = 0
        raw_body = environ['wsgi.input'].read(length) if length else b''

        # auth: if token required, accept either direct token header or HMAC signature
        if REQUIRED_TOKEN:
            supplied_token = environ.get('HTTP_X_APOS_APPROVE_TOKEN')
            if supplied_token and supplied_token == REQUIRED_TOKEN:
                auth_ok = True
            else:
                # check HMAC signature
                ts = environ.get('HTTP_X_APOS_TIMESTAMP')
                sig = environ.get('HTTP_X_APOS_SIGNATURE')
                auth_ok = False
                if ts and sig:
                    try:
                        ts_i = int(ts)
                        now = int(time.time())
                        if abs(now - ts_i) <= SIGNATURE_WINDOW:
                            msg = ts.encode('utf-8') + b'.' + raw_body
                            expected = hmac.new(REQUIRED_TOKEN.encode('utf-8'), msg, hashlib.sha256).hexdigest()
                            if hmac.compare_digest(expected, sig):
                                auth_ok = True
                    except Exception:
                        auth_ok = False

            if not auth_ok:
                start_response('401 Unauthorized', [('Content-Type', 'application/json')])
                return [json.dumps({'error': 'unauthorized'}).encode('utf-8')]

        # parse JSON from raw_body
        if not raw_body:
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'invalid_json'}).encode('utf-8')]
        try:
            payload = json.loads(raw_body.decode('utf-8'))
        except Exception:
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'invalid_json'}).encode('utf-8')]

        task_id = payload.get('task_id')
        workspace = payload.get('workspace')
        step = payload.get('step', 0)
        approved_by = payload.get('approved_by')
        item_id = _resolve_item_id(payload)

        if not item_id and (not task_id or not workspace):
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'task_id_workspace_or_item_id_required'}).encode('utf-8')]
        if item_id and not workspace:
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'workspace_required_for_item_id'}).encode('utf-8')]

        try:
            orch = Orchestrator(workspace_root=workspace, history_db_path=f"{workspace}/.apos/history.sqlite3")
            if task_id and workspace and payload.get('step') is not None:
                orch.approve_plan_step(task_id, int(step), approved_by=approved_by, reason=payload.get('reason'))
                result = orch.run_plan_step(task_id, int(step), approved_by=approved_by, force=bool(payload.get('force')))
            else:
                item = orch.approve_pending_approval(item_id, approved_by=approved_by, reason=payload.get('reason'))
                if not item:
                    try:
                        orch.stop()
                    except Exception:
                        pass
                    start_response('404 Not Found', [('Content-Type', 'application/json')])
                    return [json.dumps({'error': 'approval_item_not_found', 'id': item_id}).encode('utf-8')]
                result = {
                    'type': 'approval_recorded',
                    'item': item,
                }
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

    if path == '/reject' and method == 'POST':
        try:
            length = int(environ.get('CONTENT_LENGTH') or 0)
        except Exception:
            length = 0
        raw_body = environ['wsgi.input'].read(length) if length else b''

        if REQUIRED_TOKEN:
            supplied_token = environ.get('HTTP_X_APOS_APPROVE_TOKEN')
            if supplied_token and supplied_token == REQUIRED_TOKEN:
                auth_ok = True
            else:
                ts = environ.get('HTTP_X_APOS_TIMESTAMP')
                sig = environ.get('HTTP_X_APOS_SIGNATURE')
                auth_ok = False
                if ts and sig:
                    try:
                        ts_i = int(ts)
                        now = int(time.time())
                        if abs(now - ts_i) <= SIGNATURE_WINDOW:
                            msg = ts.encode('utf-8') + b'.' + raw_body
                            expected = hmac.new(REQUIRED_TOKEN.encode('utf-8'), msg, hashlib.sha256).hexdigest()
                            if hmac.compare_digest(expected, sig):
                                auth_ok = True
                    except Exception:
                        auth_ok = False

            if not auth_ok:
                start_response('401 Unauthorized', [('Content-Type', 'application/json')])
                return [json.dumps({'error': 'unauthorized'}).encode('utf-8')]

        if not raw_body:
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'invalid_json'}).encode('utf-8')]
        try:
            payload = json.loads(raw_body.decode('utf-8'))
        except Exception:
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'invalid_json'}).encode('utf-8')]

        item_id = _resolve_item_id(payload)
        task_id = payload.get('task_id')
        workspace = payload.get('workspace')
        step = payload.get('step', 0)
        if not item_id and (not task_id or not workspace):
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'task_id_workspace_or_item_id_required'}).encode('utf-8')]
        if item_id and not workspace:
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'workspace_required_for_item_id'}).encode('utf-8')]

        try:
            orch = Orchestrator(workspace_root=workspace, history_db_path=f"{workspace}/.apos/history.sqlite3")
            if task_id and workspace and payload.get('step') is not None:
                item_id = f'{task_id}:step:{int(step)}'
            item = orch.reject_pending_approval(item_id, rejected_by=payload.get('rejected_by') or payload.get('approved_by'), reason=payload.get('reason'))
            if not item:
                try:
                    orch.stop()
                except Exception:
                    pass
                start_response('404 Not Found', [('Content-Type', 'application/json')])
                return [json.dumps({'error': 'approval_item_not_found', 'id': item_id}).encode('utf-8')]
            try:
                orch.stop()
            except Exception:
                pass
            start_response('200 OK', [('Content-Type', 'application/json')])
            return [json.dumps({'type': 'approval_recorded', 'item': item}, ensure_ascii=False).encode('utf-8')]
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
