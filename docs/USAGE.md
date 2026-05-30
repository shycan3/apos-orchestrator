# APOS Usage Guide

This guide describes the current APOS usage baseline for the v0.3 release line plus the runtime and bridge capabilities already committed after v0.3.

APOS connects web LLM output to a local project through a local validation gate.

The Bridge Protocol section in this guide refers to the browser-local integration path, not the product version name.

It does not give the web LLM direct write access. The web LLM proposes, the local server validates, and a human-approved `commit_patch` writes the file.

## Recommended Work Order

For the earlier minimal stabilized flow, use this order:

1. Start the local server or dashboard server.
2. Build a Context Pack.
3. Build a prompt with Prompt Builder.
4. Collect the web LLM response as a task envelope or `apos-patch` proposal.
5. Check the approval queue.
6. Use plan steps when the work is `plan_only`.
7. Open the dashboard to inspect queue state, plans, and recent failures.
8. Use Failure / Drift Report when the workspace looks stale or a task fails.

## Standard Demo Flow

Use these three examples when you want to show the normal APOS path end to end.

```text
1. examples/validate_only_demo.json
  -> cli/run_task.py --validate-only --json
2. examples/preview_patch_demo.json
  -> cli/run_task.py --json
3. examples/apos_patch_demo.md
  -> server/apos_server.py -> validation_passed -> commit_patch
```

The first two examples produce or preview a `result_envelope` through `cli/run_task.py`.
The third example demonstrates the browser bridge path for `apos-patch` code blocks.

## Install

Install the Python WebSocket dependency:

```bash
python -m pip install websockets
```

## Apply APOS to a Project

```bash
python C:/Users/DO/Documents/apos-orchestrator/cli/apos.py apply -y C:/Users/DO/Desktop/test-project
```

This creates:

```text
.apos/
.codex/
specifications/
context/
workspace/
archives/
```

`specifications/architecture.md` receives a Machine Facts block delimited by:

```html
<!-- APOS_FACTS_START -->
<!-- APOS_FACTS_END -->
```

If a pre-existing Machine Facts block cannot be parsed, the CLI aborts instead of guessing.

The generated project also includes `specifications/architecture.md` with a Human Notes section, plus `.codex/APOS_INSTRUCTIONS.md` for Codex handoff.

## Refresh Machine Facts

```bash
python C:/Users/DO/Documents/apos-orchestrator/cli/apos.py refresh C:/Users/DO/Desktop/test-project
```

Refresh does not edit protected documents. It appends a Drift Report to:

```text
workspace/scratchpad.md
```

## Summarize Project State

```bash
python C:/Users/DO/Documents/apos-orchestrator/cli/apos.py summarize C:/Users/DO/Desktop/test-project
```

## Print Codex Handoff Prompt

```bash
python C:/Users/DO/Documents/apos-orchestrator/cli/apos.py codex
```

## Start Local Server

```bash
python C:/Users/DO/Documents/apos-orchestrator/server/apos_server.py
```

Expected output:

```text
APOS local websocket server listening on ws://127.0.0.1:8765
```

Warning:

- Pending validated patches are held in server memory.
- Restarting the server clears pending patches that were not committed yet.

## Load Chrome Extension

1. Open `chrome://extensions`
2. Enable Developer mode
3. Click Load unpacked
4. Select `C:/Users/DO/Documents/apos-orchestrator/extension`
5. Refresh ChatGPT or Gemini

## Patch Format

The web LLM must output exactly two adjacent fenced code blocks.

First block:

```apos-patch
{
  "patch_id": "patch-001",
  "project_root": "C:/Users/DO/Desktop/test-project",
  "target": "workspace/active_code.py",
  "language": "python",
  "sha256": "..."
}
```

Second block:

```python
def main():
    print("hello")
```

The extension reads `pre code` blocks, finds `apos-patch`, pairs it with the immediately following code block, computes SHA-256, and sends a `propose_patch` message.

The extension only accepts assistant/model-authored message scopes, ignores user-authored or editable composer blocks, deduplicates proposals by `patch_id + sha256`, and keeps retry state bounded.

If `sha256` is empty or a placeholder such as `...`, the extension fills the computed hash. If a real hash is supplied and mismatches the source block, the extension requests a correction. Automatic retry prompts are capped and the queue is pruned so stale entries do not grow without bound.

## Commit Flow

The server validates a proposal and stores it in a pending buffer:

```json
{
  "type": "validation_passed",
  "patch_id": "patch-001",
  "target": "workspace/active_code.py",
  "zone": "direct_candidate",
  "message": "Validation passed. Waiting for human sign-off."
}
```

After human approval, send:

```json
{
  "type": "commit_patch",
  "patch_id": "patch-001"
}
```

Only then does the server write the file.

If you use the extension content script directly, you can send commit requests from DevTools console:

```javascript
window.__APOS_V32__.commit("patch-001");
```

## Plan Only Mode and `apos plans`

`plan_only` tasks are the standard way to move through a plan one step at a time.

Start by recording a `plan_only` envelope into the workspace history DB. The example below uses the existing demo payload:

```powershell
@'
import json
from apos_core.orchestrator import Orchestrator
with open('examples/plan_approve_demo_plan.json', 'r', encoding='utf-8') as handle:
    payload = json.load(handle)

workspace = payload['workspace_root']
orch = Orchestrator(workspace_root=workspace, history_db_path=f"{workspace}/.apos/history.sqlite3")
orch.recorder.record_task(payload['task_id'], payload)
print('recorded', payload['task_id'])
'@ | .\.venv\Scripts\python.exe -
```

Then use the canonical CLI:

```bash
python cli/apos.py plans list --workspace /path/to/project --json
python cli/apos.py plans show plan-123 --workspace /path/to/project --json
python cli/apos.py plans steps plan-123 --workspace /path/to/project --json
python cli/apos.py plans approve-step plan-123 0 --workspace /path/to/project --approved-by alice --json
python cli/apos.py plans reject-step plan-123 1 --workspace /path/to/project --rejected-by bob --reason "not needed" --json
python cli/apos.py plans run-step plan-123 0 --workspace /path/to/project --approved-by alice --json
```

What the commands do:

- `plans list` shows recorded `plan_only` tasks.
- `plans show` shows one plan with step statuses and summary metadata.
- `plans steps` returns the step list for a plan.
- `approve-step` moves one step to approved.
- `reject-step` moves one step to rejected.
- `run-step` executes an approved step and returns a result envelope.

Execution result:

- `success` means the step ran successfully.
- `failed` means a command or patch failed during execution.
- `skipped` means the step was not runnable under the current state.

Rerun policy:

- `pending` and `rejected` steps do not execute; `run-step` returns `skipped`.
- `executed` and `failed` steps do not rerun unless you pass `--force`.
- Invalid `task_id` or invalid step index values cause the CLI to fail.

Compatibility wrappers remain available:

- `cli/plan_step.py` runs a single step from a file-based `plan_only` envelope.
- `cli/plan_approve.py` approves and runs a recorded plan step from history.

The documented flow is backed by [tests/test_plan_management.py](../tests/test_plan_management.py).

For a copy-paste walkthrough, see [examples/plan_step_demo.md](../examples/plan_step_demo.md).

If you need the generic approval queue surface, keep using `cli/approvals.py`; it manages approval items, not plan step lifecycle directly.

## Local Dashboard

The lightweight browser dashboard runs on the approval-list server and reads the same workspace history DB.

```bash
python server/list_approvals_endpoint.py
```

Open one of these routes in a browser:

```text
http://127.0.0.1:8082/
http://127.0.0.1:8082/ui
http://127.0.0.1:8082/ui/approvals
http://127.0.0.1:8082/ui/plans
```

Use the workspace field in the header to point the dashboard at the project you want to inspect. If `APOS_APPROVE_TOKEN` is set, paste the token into the dashboard token field before refreshing.

The dashboard exposes these same-origin endpoints for read and action flows:

- `GET /api/dashboard`
- `GET /api/approvals`
- `GET /api/plans`
- `POST /api/approvals/approve`
- `POST /api/approvals/reject`
- `POST /api/plans/approve-step`
- `POST /api/plans/reject-step`
- `POST /api/plans/run-step`

The browser actions still route through `Orchestrator` and `PlanStepManager` policy checks; the UI does not modify SQLite directly.

For a step-by-step browser walkthrough, see [examples/ui_demo.md](../examples/ui_demo.md) and [docs/UI_OVERVIEW.md](UI_OVERVIEW.md).

Approval Queue
--------------

You can inspect and manage pending approval items with the CLI:

```bash
python cli/approvals.py list --workspace /path/to/workspace --status pending
python cli/approvals.py show <item_id> --workspace /path/to/workspace
python cli/approvals.py approve <item_id> --workspace /path/to/workspace --approved-by alice
python cli/approvals.py reject <item_id> --workspace /path/to/workspace --rejected-by bob
```

This queue includes recorded `plan_only` steps and bridge patch proposals when they are persisted.

HTTP Approval API
-----------------

You can also run lightweight HTTP endpoints that expose the approval queue API. Start them with:

```bash
python server/approve_endpoint.py
python server/list_approvals_endpoint.py
```

Then POST JSON to `http://127.0.0.1:8081/approve` to approve or execute an item, or `http://127.0.0.1:8081/reject` to reject it. You can also query `http://127.0.0.1:8082/approvals` to list queue items and `http://127.0.0.1:8082/approvals?id=<item_id>` to show one item.

Example using `curl` to execute a recorded plan step:

```bash
curl -X POST http://127.0.0.1:8081/approve \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"plan-approve-demo","workspace":"./workspace","step":0,"approved_by":"alice"}'
```

Example using `curl` to reject a queue item:

```bash
curl -X POST http://127.0.0.1:8081/reject \
  -H 'Content-Type: application/json' \
  -d '{"workspace":"./workspace","item_id":"approval-item-id","rejected_by":"bob","reason":"not needed"}'
```

`POST /approve` returns a `result_envelope` for recorded `plan_only` steps and an approval item object for queue-only approvals. `POST /reject` returns the updated approval item.

Context Pack
------------

Use the Context Pack when you want to give ChatGPT or Gemini a safe summary of the current workspace instead of raw files.

```bash
python cli/apos.py context build --json
python cli/apos.py context inspect --format markdown --output context_pack.md
python cli/context_pack.py --json
```

The JSON output is machine-oriented. The Markdown output is paste-friendly and includes Project Snapshot, Current Safe Working Scope, Recent Changes, Approval Queue Summary, Relevant Files, Known Warnings, and Recommended Next Prompt.

See [examples/context_pack_demo.md](examples/context_pack_demo.md) for a paste-ready Markdown example.

Context Pack excludes protected paths, large-file bodies, and secret-like values.

## Prompt Builder

Prompt Builder는 현재 Context Pack, 사용자 목표, APOS 출력 규칙을 합쳐 ChatGPT 또는 Gemini에 바로 붙여넣을 수 있는 마크다운 프롬프트를 만든다.

프롬프트는 항상 "웹 LLM은 제안자이고 APOS는 검증/실행자"라는 역할 분리를 먼저 강조하고, 사람용 요약과 APOS용 구조화 블록을 분리하도록 요구한다.

주요 모드:

- `patch`: 단일 `apos-patch` 제안용
- `plan`: `plan_only` 계획용
- `review`: 변경 없이 분석/리스크/다음 작업 제안용

patch 모드는 정확히 하나의 `apos-patch` 코드블록과 하나의 source 블록을 요구한다. plan 모드는 독립적으로 승인 가능한 step 분리를 요구하고, review 모드는 파일 수정 JSON을 만들지 않는다.

주요 명령:

```bash
python cli/apos.py prompt build --goal "작업 목표" --mode patch --output prompt.md
python cli/apos.py prompt build --goal "작업 목표" --mode plan
python cli/apos.py prompt build --goal "작업 목표" --mode review --copy
```

`--copy`는 가능하면 클립보드로도 복사하지만, 실패해도 프롬프트 생성 자체는 계속 성공하도록 설계되어 있다.

예시 워크스루는 [examples/prompt_builder_demo.md](../examples/prompt_builder_demo.md)를 보면 된다.

## Failure / Drift Report

Failure / Drift Report는 실패한 task와 오래된 컨텍스트 신호를 함께 묶어 다음 행동을 안내한다.

주요 명령:

```bash
python cli/apos.py report failures --workspace /path/to/workspace --format markdown
python cli/apos.py report failure task-id --workspace /path/to/workspace --format markdown
python cli/apos.py report drift --workspace /path/to/workspace --format markdown
python cli/apos.py report next-prompt --workspace /path/to/workspace
```

이 보고서는 recent failure, approval rejection, affected files, drift warning, recommended human action, recommended LLM prompt를 함께 반환한다.
Failed item cards now include failure summary, likely cause, affected files, and a recovery prompt preview that can be copied manually or from the copy button in the dashboard detail panel.
The failed-item card also points you to the detail panel when you want the full recovery prompt text.

## Recovery Prompt Loop

Recovery Prompt Loop는 보고서나 실패 항목을 바탕으로 웹 LLM에 다시 붙여넣을 복구용 마크다운 프롬프트를 만든다.

주요 명령:

```bash
python cli/apos.py recover prompt --latest --workspace /path/to/workspace --output recovery_prompt.md --copy
python cli/apos.py recover prompt --failure patch-failure --workspace /path/to/workspace
python cli/apos.py recover prompt --drift --workspace /path/to/workspace
python cli/apos.py recover prompt --plan-step plan-recover-demo 0 --workspace /path/to/workspace
python cli/apos.py recover prompt --failure patch-failure --mode auto --workspace /path/to/workspace
```

동작 규칙:

- 자동 approve 또는 execute를 하지 않는다.
- `--mode auto`는 failure cause를 보고 patch / plan / review 중 하나를 추천할 뿐이며, 전송이나 실행을 수행하지 않는다.
- 복구 프롬프트는 항상 사람이 복사해 검토할 수 있는 Markdown이어야 한다.
- command 실패는 plan 모드를 우선 추천하고, 단일 파일 patch 실패는 patch 모드를 추천할 수 있다.
- 원인이 불분명하면 review 모드를 추천한다.
- `--mode patch|plan|review`로 추천 모드를 명시적으로 override할 수 있다.

Authentication (optional):

To require a simple approval token, set the environment variable `APOS_APPROVE_TOKEN` before starting the server. Clients must then include the header `X-APOS-Approve-Token: <token>` in their requests.

Example (start server requiring token):

```bash
export APOS_APPROVE_TOKEN=secret-token
python server/approve_endpoint.py
```

Example `curl` with token:

```bash
curl -X POST http://127.0.0.1:8081/approve \
  -H 'Content-Type: application/json' \
  -H 'X-APOS-Approve-Token: secret-token' \
  -d '{"task_id":"plan-approve-demo","workspace":"./workspace","step":0}'
```

Better: use a timestamped HMAC signature to avoid sending a static token in plaintext headers.

Example HMAC usage (bash):

```bash
TOKEN=secret-token
BODY='{"task_id":"plan-approve-demo","workspace":"./workspace","step":0}'
TS=$(date +%s)
SIG=$(python - <<PY
import hmac,hashlib,sys
tok=sys.argv[1].encode()
ts=sys.argv[2].encode()
body=sys.argv[3].encode()
print(hmac.new(tok, ts+b'.'+body, hashlib.sha256).hexdigest())
PY
$TOKEN $TS "$BODY")

curl -X POST http://127.0.0.1:8081/approve \
  -H 'Content-Type: application/json' \
  -H "X-APOS-Timestamp: $TS" \
  -H "X-APOS-Signature: $SIG" \
  -d "$BODY"
```

## Failure Test

Send a Python block with a syntax error:

```python
def main()
    print("missing colon")
```

Expected response:

```json
{
  "type": "validation_failed",
  "error_kind": "python_syntax_error",
  "retry_allowed": true
}
```

The extension can inject a retry prompt into the web LLM input up to two times.

## Debugging Checklist

1. Is the server running on `ws://127.0.0.1:8765`?
2. Is the extension loaded from the `extension/` folder?
3. Did you refresh ChatGPT or Gemini after loading the extension?
4. Is the first code block language `apos-patch`?
5. Is the source block immediately after the metadata block?
6. Does `target` stay under an allowed area?
7. Does the Python code pass `py_compile`?
8. Did the server return `validation_passed` before `commit_patch`?

Chrome DevTools logs use:

```text
[APOS] Content script initialized
[APOS Debug] Raw blocks
[APOS Debug] Parsed metadata
[APOS Debug] Sending
[APOS] Server response
```
