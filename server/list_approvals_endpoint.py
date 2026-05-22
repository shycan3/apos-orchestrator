"""Lightweight HTTP endpoint to list approvals with optional filters.

GET /approvals?task_id=...&approver=...&start=...&end=...&limit=...&offset=...

Requires same auth as `approve_endpoint.py` when `APOS_APPROVE_TOKEN` is set.
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

SIGNATURE_WINDOW = int(os.environ.get("APOS_APPROVE_SIGNATURE_WINDOW", "300"))


def _parse_qs(environ):
    qs = environ.get('QUERY_STRING', '')
    return {k: v[0] for k, v in parse_qs(qs).items()}


def _auth_ok(environ, raw_body=b''):
    REQUIRED_TOKEN = os.environ.get("APOS_APPROVE_TOKEN")
    if not REQUIRED_TOKEN:
        return True
    supplied_token = environ.get('HTTP_X_APOS_APPROVE_TOKEN')
    if supplied_token and supplied_token == REQUIRED_TOKEN:
        return True
    ts = environ.get('HTTP_X_APOS_TIMESTAMP')
    sig = environ.get('HTTP_X_APOS_SIGNATURE')
    if ts and sig:
        try:
            ts_i = int(ts)
            now = int(time.time())
            if abs(now - ts_i) <= SIGNATURE_WINDOW:
                msg = ts.encode('utf-8') + b'.' + raw_body
                expected = hmac.new(REQUIRED_TOKEN.encode('utf-8'), msg, hashlib.sha256).hexdigest()
                return hmac.compare_digest(expected, sig)
        except Exception:
            return False
    return False


def app(environ, start_response):
    path = environ.get('PATH_INFO', '/')
    method = environ.get('REQUEST_METHOD', 'GET')

    if path == '/approvals' and method == 'GET':
        if not _auth_ok(environ, b''):
            start_response('401 Unauthorized', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'unauthorized'}).encode('utf-8')]

        params = _parse_qs(environ)
        task_id = params.get('task_id')
        if not task_id:
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'task_id_required'}).encode('utf-8')]

        approver = params.get('approver')
        start = params.get('start')
        end = params.get('end')
        limit = params.get('limit')
        offset = params.get('offset')

        try:
            start_ts = float(start) if start else None
            end_ts = float(end) if end else None
            limit_i = int(limit) if limit else None
            offset_i = int(offset) if offset else None
        except Exception:
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'invalid_params'}).encode('utf-8')]

        workspace = params.get('workspace', '.')
        try:
            orch = Orchestrator(workspace_root=workspace, history_db_path=f"{workspace}/.apos/history.sqlite3")
            approvals = orch.recorder.get_approvals(task_id, approver=approver, start_ts=start_ts, end_ts=end_ts, limit=limit_i, offset=offset_i)
            try:
                orch.stop()
            except Exception:
                pass
            start_response('200 OK', [('Content-Type', 'application/json')])
            return [json.dumps(approvals, ensure_ascii=False).encode('utf-8')]
        except Exception as exc:
            start_response('500 Internal Server Error', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'internal_error', 'message': str(exc)}).encode('utf-8')]

    if path == '/health':
        start_response('200 OK', [('Content-Type', 'application/json')])
        return [json.dumps({'ok': True}).encode('utf-8')]

    start_response('404 Not Found', [('Content-Type', 'application/json')])
    return [json.dumps({'error': 'not_found'}).encode('utf-8')]


if __name__ == '__main__':
    with make_server('127.0.0.1', 8082, app) as httpd:
        print('Approvals listing endpoint listening on http://127.0.0.1:8082')
        httpd.serve_forever()
