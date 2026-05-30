"""Lightweight HTTP endpoint to list approvals with optional filters.

GET /approvals?id=...&task_id=...&patch_id=...&status=...&item_type=...&limit=...&offset=...

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
from apos_core.plan_flow import PlanStepManager
from apos_core.recovery_prompt_builder import RecoveryPromptBuilder
from apos_core.report_builder import ReportBuilder

SIGNATURE_WINDOW = int(os.environ.get("APOS_APPROVE_SIGNATURE_WINDOW", "300"))


def _parse_qs(environ):
    qs = environ.get('QUERY_STRING', '')
    return {k: v[0] for k, v in parse_qs(qs).items()}


def _parse_time_param(val: str):
    """Accept epoch seconds or ISO 8601 string. Return float seconds since epoch."""
    if not val:
        return None
    try:
        return float(val)
    except Exception:
        pass
    # try ISO parse
    try:
        # handle trailing Z
        if val.endswith('Z'):
            val = val[:-1] + '+00:00'
        from datetime import datetime

        dt = datetime.fromisoformat(val)
        return dt.timestamp()
    except Exception:
        return None


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


def _read_json_body(environ):
    try:
        length = int(environ.get('CONTENT_LENGTH') or 0)
    except Exception:
        length = 0
    raw_body = environ['wsgi.input'].read(length) if length else b''
    if not raw_body:
        return None, raw_body
    try:
        return json.loads(raw_body.decode('utf-8')), raw_body
    except Exception:
        return None, raw_body


def _workspace_from_params(params):
    return params.get('workspace', '.')


def _status_line(code: int) -> str:
    return {
        200: '200 OK',
        400: '400 Bad Request',
        401: '401 Unauthorized',
        404: '404 Not Found',
        500: '500 Internal Server Error',
    }.get(code, f'{code} OK')


def _dashboard_html() -> str:
    ui_path = Path(__file__).resolve().parent / 'approvals_ui.html'
    return ui_path.read_text(encoding='utf-8')


def _make_orchestrator(workspace: str) -> Orchestrator:
    return Orchestrator(workspace_root=workspace, history_db_path=f"{workspace}/.apos/history.sqlite3")


def _summarize_approval_item(orch: Orchestrator, item: dict) -> dict:
    summary = dict(item)
    result_task_id = None
    if item.get('item_type') == 'plan_step' and item.get('task_id') is not None and item.get('step_index') is not None:
        result_task_id = f"{item.get('task_id')}-step-{item.get('step_index')}"
    elif item.get('task_id'):
        result_task_id = str(item.get('task_id'))

    if result_task_id:
        latest = orch.recorder.get_latest_result(result_task_id)
        if latest:
            summary['latest_result'] = {
                'task_id': latest.get('task_id'),
                'status': (latest.get('result_envelope') or {}).get('status') or '',
                'exit_code': latest.get('exit_code'),
                'stdout': latest.get('stdout', ''),
                'stderr': latest.get('stderr', ''),
            }
    return summary


def _approval_result_identifier(item: dict) -> str:
    latest = item.get('latest_result') if isinstance(item.get('latest_result'), dict) else {}
    if latest.get('task_id'):
        return str(latest.get('task_id'))
    if item.get('task_id'):
        return str(item.get('task_id'))
    if item.get('id'):
        return str(item.get('id'))
    return ''


def _item_has_failure_signals(item: dict) -> bool:
    if str(item.get('status') or '').lower() == 'failed':
        return True
    latest = item.get('latest_result') if isinstance(item.get('latest_result'), dict) else {}
    result_status = str(latest.get('status') or '').lower()
    if result_status in {'failed', 'patch_blocked', 'command_blocked', 'validation_failed', 'rejected'}:
        return True
    exit_code = latest.get('exit_code')
    return exit_code not in (None, 0)


def _enrich_failure_item(
    item: dict,
    report_builder: ReportBuilder,
    recovery_builder: RecoveryPromptBuilder,
    *,
    limit: int = 5,
) -> dict:
    summary = dict(item)
    identifier = _approval_result_identifier(summary)
    failure_detail = report_builder.build_failure_detail(identifier, limit=limit) if identifier else report_builder.build_failure_report(limit=limit)
    if not failure_detail.get('recent_failures') and summary.get('task_id') and str(summary.get('task_id')) != identifier:
        alt_detail = report_builder.build_failure_detail(str(summary.get('task_id')), limit=limit)
        if alt_detail.get('recent_failures'):
            failure_detail = alt_detail
            identifier = str(summary.get('task_id'))
    recovery_prompt = recovery_builder.build(failure_id=identifier, limit=limit, mode="auto") if identifier else recovery_builder.build(latest=True, limit=limit, mode="auto")
    if not recovery_prompt.get('prompt_text'):
        recovery_prompt = recovery_builder.build(latest=True, limit=limit, mode="auto")

    recent_failures = failure_detail.get('recent_failures', []) if isinstance(failure_detail.get('recent_failures'), list) else []
    primary_failure = failure_detail.get('primary_failure', {}) if isinstance(failure_detail.get('primary_failure'), dict) else {}
    summary.update(
        {
            'failure_detail': failure_detail,
            'recovery_prompt': recovery_prompt,
            'failure_summary': failure_detail.get('summary', ''),
            'likely_cause': (failure_detail.get('likely_causes') or ['unknown'])[0] if isinstance(failure_detail.get('likely_causes'), list) else 'unknown',
            'affected_files': failure_detail.get('affected_files', []),
            'stale_context_signals': failure_detail.get('stale_context_signals', []),
            'recommended_human_action': failure_detail.get('recommended_human_action', ''),
            'recommended_llm_prompt': failure_detail.get('recommended_llm_prompt', ''),
            'recommended_recovery_mode': recovery_prompt.get('mode', ''),
            'recommended_recovery_summary': recovery_prompt.get('summary', ''),
            'recommended_recovery_prompt': recovery_prompt.get('prompt_text', ''),
            'stdout': primary_failure.get('stdout', ''),
            'stderr': primary_failure.get('stderr', ''),
            'exit_code': primary_failure.get('exit_code'),
            'recent_failure_count': len(recent_failures),
        }
    )
    return summary


def _dashboard_payload(orch: Orchestrator) -> dict:
    manager = PlanStepManager(orch)
    items = orch.recorder.list_approval_items(limit=10)
    pending = orch.recorder.list_approval_items(status='pending')
    failed = orch.recorder.list_approval_items(status='failed')
    executed = orch.recorder.list_approval_items(status='executed', limit=5)
    recent_plans = manager.list_plans(limit=5)
    recent_approval_items = [_summarize_approval_item(orch, item) for item in items[:5]]
    failed_items = []
    report_builder = ReportBuilder(orch.workspace_root, history_db_path=orch.recorder.db_path)
    drift_report = report_builder.build_drift_report(limit=5)
    recovery_builder = RecoveryPromptBuilder(orch.workspace_root, history_db_path=orch.recorder.db_path)
    try:
        for item in failed[:5]:
            failed_items.append(_enrich_failure_item(item, report_builder, recovery_builder, limit=5))
        if failed_items:
            recovery = recovery_builder.build(latest=True, limit=5, mode="auto")
        elif drift_report.get('drift_warning'):
                recovery = recovery_builder.build(drift=True, limit=5, mode="auto")
        else:
                recovery = recovery_builder.build(latest=True, limit=5, mode="auto")
    finally:
        recovery_builder.close()
        report_builder.close()
    return {
        'pending_approvals_count': len(pending),
        'failed_items_count': len(failed),
        'failed_items_summary': failed_items,
        'recent_executed_items': [_summarize_approval_item(orch, item) for item in executed],
        'recent_plan_summaries': recent_plans,
        'recent_approval_items': recent_approval_items,
        'drift_warning': drift_report.get('drift_warning', False),
        'drift_signals': drift_report.get('stale_context_signals', []),
        'drift_summary': drift_report.get('recommended_human_action', ''),
        'recommended_recovery_mode': recovery.get('mode', ''),
        'recommended_recovery_summary': recovery.get('summary', ''),
    }


def _handle_post_approval_action(orch: Orchestrator, payload: dict, action: str) -> tuple[int, dict]:
    item_id = str(payload.get('item_id') or '').strip()
    task_id = str(payload.get('task_id') or '').strip()
    step = payload.get('step')
    workspace = str(payload.get('workspace') or '.').strip()
    approved_by = payload.get('approved_by') or payload.get('rejected_by')
    reason = payload.get('reason')

    if task_id and step is not None:
        step_index = int(step)
        if action == 'approve':
            item = orch.approve_plan_step(task_id, step_index, approved_by=approved_by, reason=reason)
        else:
            item = orch.reject_plan_step(task_id, step_index, rejected_by=approved_by, reason=reason)
        if not item:
            return 404, {'error': 'plan_step_not_found', 'task_id': task_id, 'step': step_index}
        if action == 'approve':
            result = orch.run_plan_step(task_id, step_index, approved_by=approved_by, force=bool(payload.get('force')))
            return 200, {'type': 'result_envelope', 'result': result, 'item': item}
        return 200, {'type': 'approval_recorded', 'item': item}

    if not item_id and not task_id:
        return 400, {'error': 'task_id_workspace_or_item_id_required'}
    if not item_id and task_id and step is None:
        return 400, {'error': 'step_required_for_plan_action'}

    if action == 'approve':
        item = orch.approve_pending_approval(item_id, approved_by=approved_by, reason=reason)
    else:
        item = orch.reject_pending_approval(item_id, rejected_by=approved_by, reason=reason)
    if not item:
        return 404, {'error': 'approval_item_not_found', 'id': item_id}
    return 200, {'type': 'approval_recorded', 'item': item}


def app(environ, start_response):
    path = environ.get('PATH_INFO', '/')
    method = environ.get('REQUEST_METHOD', 'GET')

    if path in ('/', '/ui', '/ui/approvals', '/ui/plans', '/approvals/ui', '/approvals.html') and method == 'GET':
        try:
            html = _dashboard_html()
            start_response('200 OK', [('Content-Type', 'text/html; charset=utf-8')])
            return [html.encode('utf-8')]
        except Exception as exc:
            start_response('500 Internal Server Error', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'internal_error', 'message': str(exc)}).encode('utf-8')]

    if path == '/health':
        start_response('200 OK', [('Content-Type', 'application/json')])
        return [json.dumps({'ok': True}).encode('utf-8')]

    if path in ('/api/dashboard', '/dashboard') and method == 'GET':
        if not _auth_ok(environ, b''):
            start_response('401 Unauthorized', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'unauthorized'}).encode('utf-8')]

        params = _parse_qs(environ)
        workspace = _workspace_from_params(params)
        orch = _make_orchestrator(workspace)
        try:
            payload = _dashboard_payload(orch)
            payload['workspace'] = workspace
            start_response('200 OK', [('Content-Type', 'application/json')])
            return [json.dumps(payload, ensure_ascii=False).encode('utf-8')]
        except Exception as exc:
            start_response('500 Internal Server Error', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'internal_error', 'message': str(exc)}).encode('utf-8')]
        finally:
            try:
                orch.stop()
            except Exception:
                pass

    if path in ('/approvals', '/api/approvals') and method == 'GET':
        if not _auth_ok(environ, b''):
            start_response('401 Unauthorized', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'unauthorized'}).encode('utf-8')]

        params = _parse_qs(environ)
        item_id = params.get('id') or params.get('item_id')
        task_id = params.get('task_id')
        approver = params.get('approver')
        start = params.get('start')
        end = params.get('end')
        patch_id = params.get('patch_id')
        status = params.get('status')
        item_type = params.get('item_type')
        limit = params.get('limit')
        offset = params.get('offset')
        try:
            limit_i = int(limit) if limit else None
            offset_i = int(offset) if offset else None
        except Exception:
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'invalid_params'}).encode('utf-8')]

        workspace = _workspace_from_params(params)
        orch = None
        try:
            orch = _make_orchestrator(workspace)
            next_link = None
            if item_id:
                item = orch.get_pending_approval(item_id)
                if not item:
                    start_response('404 Not Found', [('Content-Type', 'application/json')])
                    return [json.dumps({'error': 'not_found', 'id': item_id}).encode('utf-8')]
                summary = _summarize_approval_item(orch, item)
                if _item_has_failure_signals(summary):
                    report_builder = ReportBuilder(orch.workspace_root, history_db_path=orch.recorder.db_path)
                    recovery_builder = RecoveryPromptBuilder(orch.workspace_root, history_db_path=orch.recorder.db_path)
                    try:
                        summary = _enrich_failure_item(summary, report_builder, recovery_builder, limit=5)
                    finally:
                        recovery_builder.close()
                        report_builder.close()
                try:
                    orch.stop()
                except Exception:
                    pass
                start_response('200 OK', [('Content-Type', 'application/json')])
                return [json.dumps(summary, ensure_ascii=False).encode('utf-8')]

            legacy_start_ts = _parse_time_param(start) if start else None
            legacy_end_ts = _parse_time_param(end) if end else None

            req_limit = limit_i + 1 if limit_i else None
            queue_items = orch.list_pending_approvals(
                task_id=task_id,
                patch_id=patch_id,
                status=status,
                item_type=item_type,
                limit=req_limit,
                offset=offset_i,
            )
            approvals = queue_items
            use_legacy = False
            if not (patch_id or status or item_type or item_id) and task_id:
                use_legacy = len(queue_items) == 0

            if use_legacy:
                approvals = orch.recorder.get_approvals(
                    task_id,
                    approver=approver,
                    start_ts=legacy_start_ts,
                    end_ts=legacy_end_ts,
                    limit=req_limit,
                    offset=offset_i,
                )

            if limit_i and approvals and len(approvals) > limit_i:
                next_offset = (offset_i or 0) + limit_i
                base = environ.get('wsgi.url_scheme', 'http') + '://' + (environ.get('HTTP_HOST') or '127.0.0.1') + environ.get('PATH_INFO', '/approvals')
                q = []
                for k in ('task_id', 'approver', 'start', 'end', 'patch_id', 'status', 'item_type', 'limit', 'workspace'):
                    v = params.get(k)
                    if v:
                        q.append(f"{k}={v}")
                q.append(f"offset={next_offset}")
                next_url = base + '?' + '&'.join(q)
                next_link = f"<{next_url}>; rel=\"next\""
                approvals = approvals[:limit_i]

            if orch:
                try:
                    orch.stop()
                except Exception:
                    pass
            headers = [('Content-Type', 'application/json')]
            if next_link:
                headers.append(('Link', next_link))
            start_response('200 OK', headers)
            return [json.dumps(approvals, ensure_ascii=False).encode('utf-8')]
        except Exception as exc:
            start_response('500 Internal Server Error', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'internal_error', 'message': str(exc)}).encode('utf-8')]

    if path in ('/plans', '/api/plans') and method == 'GET':
        if not _auth_ok(environ, b''):
            start_response('401 Unauthorized', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'unauthorized'}).encode('utf-8')]

        params = _parse_qs(environ)
        workspace = _workspace_from_params(params)
        plan_id = params.get('id') or params.get('task_id')
        orch = None
        try:
            orch = _make_orchestrator(workspace)
            manager = PlanStepManager(orch)
            if plan_id:
                plan = manager.get_plan(plan_id)
                if not plan:
                    start_response('404 Not Found', [('Content-Type', 'application/json')])
                    return [json.dumps({'error': 'not_found', 'task_id': plan_id}).encode('utf-8')]
                start_response('200 OK', [('Content-Type', 'application/json')])
                return [json.dumps(plan, ensure_ascii=False).encode('utf-8')]

            limit = params.get('limit')
            offset = params.get('offset')
            try:
                limit_i = int(limit) if limit else None
                offset_i = int(offset) if offset else None
            except Exception:
                start_response('400 Bad Request', [('Content-Type', 'application/json')])
                return [json.dumps({'error': 'invalid_params'}).encode('utf-8')]

            plans = manager.list_plans(limit=limit_i, offset=offset_i)
            start_response('200 OK', [('Content-Type', 'application/json')])
            return [json.dumps(plans, ensure_ascii=False).encode('utf-8')]
        except Exception as exc:
            start_response('500 Internal Server Error', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'internal_error', 'message': str(exc)}).encode('utf-8')]
        finally:
            if orch:
                try:
                    orch.stop()
                except Exception:
                    pass

    if path in ('/api/approvals/approve', '/api/approvals/reject') and method == 'POST':
        raw_payload, raw_body = _read_json_body(environ)
        if raw_payload is None:
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'invalid_json'}).encode('utf-8')]
        if not _auth_ok(environ, raw_body):
            start_response('401 Unauthorized', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'unauthorized'}).encode('utf-8')]

        workspace = str(raw_payload.get('workspace') or '.').strip()
        orch = None
        try:
            orch = _make_orchestrator(workspace)
            status_code, result = _handle_post_approval_action(orch, raw_payload, 'approve' if path.endswith('/approve') else 'reject')
            if orch:
                try:
                    orch.stop()
                except Exception:
                    pass
            start_response(_status_line(status_code), [('Content-Type', 'application/json')])
            return [json.dumps(result, ensure_ascii=False).encode('utf-8')]
        except Exception as exc:
            start_response('500 Internal Server Error', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'internal_error', 'message': str(exc)}).encode('utf-8')]

    if path in ('/api/plans/approve-step', '/api/plans/reject-step', '/api/plans/run-step') and method == 'POST':
        raw_payload, raw_body = _read_json_body(environ)
        if raw_payload is None:
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'invalid_json'}).encode('utf-8')]
        if not _auth_ok(environ, raw_body):
            start_response('401 Unauthorized', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'unauthorized'}).encode('utf-8')]

        workspace = str(raw_payload.get('workspace') or '.').strip()
        task_id = str(raw_payload.get('task_id') or '').strip()
        step = raw_payload.get('step')
        if not task_id or step is None:
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'task_id_and_step_required'}).encode('utf-8')]

        orch = None
        try:
            orch = _make_orchestrator(workspace)
            manager = PlanStepManager(orch)
            step_index = int(step)
            if path.endswith('/approve-step'):
                item = manager.approve_step(task_id, step_index, approved_by=raw_payload.get('approved_by'), reason=raw_payload.get('reason'))
                if not item:
                    start_response('404 Not Found', [('Content-Type', 'application/json')])
                    return [json.dumps({'error': 'plan_step_not_found', 'task_id': task_id, 'step': step_index}).encode('utf-8')]
                start_response('200 OK', [('Content-Type', 'application/json')])
                return [json.dumps({'type': 'approval_recorded', 'item': item}, ensure_ascii=False).encode('utf-8')]
            if path.endswith('/reject-step'):
                item = manager.reject_step(task_id, step_index, rejected_by=raw_payload.get('rejected_by'), reason=raw_payload.get('reason'))
                if not item:
                    start_response('404 Not Found', [('Content-Type', 'application/json')])
                    return [json.dumps({'error': 'plan_step_not_found', 'task_id': task_id, 'step': step_index}).encode('utf-8')]
                start_response('200 OK', [('Content-Type', 'application/json')])
                return [json.dumps({'type': 'approval_recorded', 'item': item}, ensure_ascii=False).encode('utf-8')]
            result = manager.run_step(task_id, step_index, approved_by=raw_payload.get('approved_by'), force=bool(raw_payload.get('force')))
            if isinstance(result, dict) and result.get('status') in {'not_found', 'invalid_step', 'invalid_task_type'}:
                start_response('404 Not Found', [('Content-Type', 'application/json')])
                return [json.dumps(result, ensure_ascii=False).encode('utf-8')]
            start_response('200 OK', [('Content-Type', 'application/json')])
            return [json.dumps({'type': 'result_envelope', 'result': result}, ensure_ascii=False).encode('utf-8')]
        except Exception as exc:
            start_response('500 Internal Server Error', [('Content-Type', 'application/json')])
            return [json.dumps({'error': 'internal_error', 'message': str(exc)}).encode('utf-8')]
        finally:
            if orch:
                try:
                    orch.stop()
                except Exception:
                    pass

    start_response('404 Not Found', [('Content-Type', 'application/json')])
    return [json.dumps({'error': 'not_found'}).encode('utf-8')]


if __name__ == '__main__':
    with make_server('127.0.0.1', 8082, app) as httpd:
        print('Approvals listing endpoint listening on http://127.0.0.1:8082')
        httpd.serve_forever()
