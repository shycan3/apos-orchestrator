import json
import time
import tempfile
from pathlib import Path
import hmac
import hashlib
import os

from wsgiref.validate import validator
from wsgiref.util import setup_testing_defaults

from server.list_approvals_endpoint import app


def _call_app(environ):
    setup_testing_defaults(environ)
    body = []

    def start_response(status, headers):
        body.append(status)
        body.append(headers)

    resp = b"".join(app(environ, start_response))
    return body[0], dict(body[1]), resp


def test_list_approvals_endpoint_returns_approvals():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "workspace"
        ws.mkdir(parents=True)
        # set token for auth
        os.environ['APOS_APPROVE_TOKEN'] = 'testtoken'

        # create recorder and record an approval
        from apos_core.recorder import Recorder

        db = ws / '.apos' / 'history.sqlite3'
        rec = Recorder(db_path=db)
        rec.record_approval('a1', 'task-x', 0, 'tester', {'note': 'ok'})
        # close recorder to release DB file for endpoint reader
        try:
            rec.close()
        except Exception:
            pass

        qs = 'task_id=task-x&workspace=%s' % (ws.as_posix(),)
        from io import BytesIO
        environ = {
            'REQUEST_METHOD': 'GET',
            'PATH_INFO': '/approvals',
            'QUERY_STRING': qs,
            'wsgi.input': BytesIO(b''),
            'HTTP_X_APOS_APPROVE_TOKEN': 'testtoken',
        }

        status, headers, resp = _call_app(environ)
        assert status.startswith('200')
        arr = json.loads(resp.decode('utf-8'))
        assert isinstance(arr, list)
        assert any(a.get('approved_by') == 'tester' for a in arr)


def test_list_approvals_endpoint_paging():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "workspace"
        ws.mkdir(parents=True)
        os.environ['APOS_APPROVE_TOKEN'] = 'testtoken'
        from apos_core.recorder import Recorder
        db = ws / '.apos' / 'history.sqlite3'
        rec = Recorder(db_path=db)
        # create 5 approvals
        for i in range(5):
            rec.record_approval(f'a{i}', 'task-p', i, f'user{i%2}', {'i': i})
        rec.close()

        qs = 'task_id=task-p&workspace=%s&limit=2' % (ws.as_posix(),)
        from io import BytesIO
        environ = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/approvals', 'QUERY_STRING': qs, 'wsgi.input': BytesIO(b''), 'HTTP_X_APOS_APPROVE_TOKEN': 'testtoken', 'HTTP_HOST': '127.0.0.1'}
        status, headers, resp = _call_app(environ)
        assert status.startswith('200')
        assert 'Link' in headers
        arr = json.loads(resp.decode('utf-8'))
        assert len(arr) == 2
