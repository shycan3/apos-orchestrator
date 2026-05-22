import json
import subprocess
import sys
import os
import tempfile
import time
from pathlib import Path

import urllib.request
import urllib.error
import urllib.parse

from apos_core.task_envelope import make_task_envelope
from apos_core.orchestrator import Orchestrator


def _make_plan_only_envelope(workspace_root: str, task_id: str = "plan-approve-ep"):
    return make_task_envelope(
        task_type="plan_only",
        workspace_root=workspace_root,
        created_by="web_llm",
        task_id=task_id,
        patches=[],
        commands=[],
        meta={
            "plan_goal": "create approve demo file via endpoint",
            "plan_steps": [
                {
                    "title": "Write approve endpoint demo file",
                    "task_type": "patch_and_run",
                    "patches": [
                        {
                            "target": "workspace/approve_ep_demo.py",
                            "language": "python",
                            "intent": "update",
                            "content": "print('approved ep step')\n",
                        }
                    ],
                    "commands": [],
                }
            ],
        },
    )


def test_approve_endpoint_executes_step(tmp_path):
    # start endpoint server as subprocess
    server_py = Path('server/approve_endpoint.py')
        # set a token to test auth enforcement
    token = 'test-token-123'
    env = os.environ.copy()
    env['APOS_APPROVE_TOKEN'] = token
    proc = subprocess.Popen([sys.executable, str(server_py)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        # wait for server to start (poll /health)
        started = False
        for _ in range(20):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8081/health', timeout=0.5) as r:
                    if r.status == 200:
                        started = True
                        break
            except Exception:
                time.sleep(0.1)
        if not started:
            raise AssertionError('approve endpoint server did not start')
        workspace = tmp_path / 'workspace'
        workspace.mkdir()

        payload = _make_plan_only_envelope(str(workspace))
        task_id = payload.get('task_id')

        # record plan
        orch = Orchestrator(workspace_root=str(workspace), history_db_path=workspace / '.apos' / 'history.sqlite3')
        orch.recorder.record_task(task_id, payload)
        orch.stop()

        # call endpoint
        url = 'http://127.0.0.1:8081/approve'
        payload = json.dumps({
            'task_id': task_id,
            'workspace': str(workspace),
            'step': 0,
            'approved_by': 'tester',
            'json': True,
        }).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'X-APOS-Approve-Token': token}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode('utf-8')
                data = json.loads(body)
        except urllib.error.HTTPError as err:
            body = err.read().decode('utf-8')
            raise AssertionError(f'HTTP error: {err.code} {body}')
        assert data.get('status') == 'success'
        target = workspace / 'workspace' / 'approve_ep_demo.py'
        assert target.exists()
    finally:
        proc.terminate()
        proc.wait(timeout=2)
