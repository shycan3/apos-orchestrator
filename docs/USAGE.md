# APOS v3.2 + Bridge Protocol Usage

APOS connects web LLM output to a local project through a local validation gate.

The Bridge Protocol keeps design-oriented AI output separated from execution-oriented patch instructions.

It does not give the web LLM direct write access. The web LLM proposes, the local server validates, and a human-approved `commit_patch` writes the file.

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

If `sha256` is empty or a placeholder such as `...`, the extension fills the computed hash. If a real hash is supplied and mismatches the source block, the extension requests a correction.

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

## Execute a Single Plan Step (Plan Only Mode)

When you have a `plan_only` task envelope and want to run a single step from the plan, use the `plan_step` CLI.

This command constructs a standalone task for the selected step, applies patches synchronously (using the same patch policy checks), runs the first command in the step if present, and records a `result_envelope` to the workspace history DB.

Example (run step 0 and print JSON result):

```bash
python cli/plan_step.py /path/to/plan.json --step 0 --json
```

Notes:

- The CLI will validate the `plan_only` envelope before executing the step.
- Patch validation and command policy are enforced the same way as normal tasks.
- The command runs synchronously and writes a minimal `result_envelope` to `workspace/.apos/history.sqlite3`.
- Use this for manual approval or debugging of individual plan steps before wiring up automated loops.

## Approve and Execute a Recorded Plan Step

If a `plan_only` envelope has been recorded to the workspace history DB (for example, by a server or by calling `orch.recorder.record_task(...)`), you can approve and execute a specific step using the `plan_approve` CLI. This looks up the recorded task by `task_id`, validates the plan, applies patches and runs the first command of the step synchronously, and records a `result_envelope` into the same history DB.

Example (approve step 0 for recorded task `plan-123` in workspace `/path/to/project`):

```bash
python cli/plan_approve.py plan-123 --workspace /path/to/project --step 0 --approved-by alice --json
```

Quick way to record a plan task into history for a local demo (runs in the workspace root where `plan.json` exists):

```bash
# record the plan.json payload into the workspace history DB
python - <<'PY'
import json
from apos_core.orchestrator import Orchestrator
payload = json.load(open('examples/plan_approve_demo_plan.json','r',encoding='utf-8'))
workspace = payload.get('workspace_root')
orch = Orchestrator(workspace_root=workspace, history_db_path=f"{workspace}/.apos/history.sqlite3")
orch.recorder.record_task(payload['task_id'], payload)
print('recorded', payload['task_id'])
PY

Then run the `plan_approve` command with the printed task id.

HTTP Approve Endpoint

You can also run a lightweight HTTP endpoint that exposes an approve API. Start it with:

```bash
python server/approve_endpoint.py
```

Then POST JSON to `http://127.0.0.1:8081/approve` with keys: `task_id`, `workspace`, `step`, `approved_by` (optional). Example using `curl`:

```bash
curl -X POST http://127.0.0.1:8081/approve \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"plan-approve-demo","workspace":"./workspace","step":0,"approved_by":"alice"}'
```

The endpoint returns the `result_envelope` JSON on success.

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
