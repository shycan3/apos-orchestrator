# APOS — Web LLM ↔ Local Workspace Orchestrator

APOS is a personal local orchestration layer that lets web-based LLMs such as ChatGPT or Gemini safely create, modify, and run local project files through structured JSON task envelopes.

APOS does **not** call OpenAI API, Gemini API, Claude API, or any model API.

```text
Web LLM generates task envelope JSON
→ APOS validates it locally
→ APOS applies safe patches
→ APOS runs allowed commands
→ APOS returns result envelope JSON
→ Web LLM uses the result to continue
```

APOS does not give a web LLM direct access to your local filesystem.  
The web LLM only produces JSON. APOS performs validation, policy checks, execution, and logging locally.

---

## Standard Demo Flow

APOS currently has two stable demo paths.

### 1. Task Envelope Flow

Use this for validation, preview, execution, and result recording.

```text
web LLM output JSON task envelope
→ cli/run_task.py --validate-only or --json
→ APOS validates / previews / applies / runs
→ APOS writes result_envelope to workspace/.apos/history.sqlite3
```

### 2. apos-patch Bridge Flow

Use this for the browser extension path.

```text
web LLM emits apos-patch + source code blocks
→ extension/contentScript.js detects the assistant/model pair, deduplicates by patch_id + sha256, and bounds retry state
→ server/apos_server.py validates path, hash, and Python syntax
→ server returns validation_passed or validation_failed
→ human sends commit_patch
→ server writes the file
```

Representative examples:

- Validate-only: [examples/validate_only_demo.json](examples/validate_only_demo.json)
- Preview patch: [examples/preview_patch_demo.json](examples/preview_patch_demo.json)
- apos-patch approval and execute: [examples/apos_patch_demo.md](examples/apos_patch_demo.md)

### Approval Queue

Use the approval queue when you want to inspect or change status without immediately executing a plan step.

```bash
python cli/approvals.py list --workspace . --status pending
python cli/approvals.py show approval-item-id --workspace .
python cli/approvals.py approve approval-item-id --workspace . --approved-by alice
python cli/approvals.py reject approval-item-id --workspace . --rejected-by bob
```

`cli/plan_approve.py` still exists for executing a recorded `plan_only` step after approval.

For the canonical step lifecycle, use `python cli/apos.py plans ...` to list, inspect, approve, reject, and run plan steps. The main flow is covered by [tests/test_plan_management.py](tests/test_plan_management.py).

See [examples/plan_step_demo.md](examples/plan_step_demo.md) for a full walkthrough.

For a browser-based local dashboard, open `http://127.0.0.1:8082/ui` after starting `python server/list_approvals_endpoint.py`.

See [docs/UI_OVERVIEW.md](docs/UI_OVERVIEW.md) and [examples/ui_demo.md](examples/ui_demo.md) for the dashboard routes and walkthrough.

To inspect failures and drift from the same workspace history DB, use the report subcommands:

```bash
python cli/apos.py report failures --workspace . --format markdown
python cli/apos.py report drift --workspace . --format markdown
python cli/apos.py report next-prompt --workspace .
```

The dashboard also surfaces recent failed approval items and drift warnings from the same report builder.
Failed item cards now include a failure summary, likely cause, affected files, and a copyable recovery prompt preview so you can move from dashboard review into recovery prompt generation without leaving the page.

See [examples/failure_report_demo.md](examples/failure_report_demo.md) for a short walkthrough.

For a paste-ready recovery prompt based on a failure, drift report, or plan-step failure, use:

```bash
python cli/apos.py recover prompt --latest --workspace . --output recovery_prompt.md --copy
python cli/apos.py recover prompt --failure patch-failure --workspace .
python cli/apos.py recover prompt --drift --workspace .
python cli/apos.py recover prompt --plan-step plan-recover-demo 0 --workspace . --mode review
```

See [examples/recovery_prompt_demo.md](examples/recovery_prompt_demo.md) for a short walkthrough.

## Known Limitations

APOS v0.1 is intentionally bounded. See [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) for the current limits, including the lack of direct automatic message forwarding to the web LLM, the absence of external browser automation and automatic loops, the need for manual approval queue review, and the fact that DOM-driven bridge flows can drift.

APOS currently targets `websockets` 16.x and the modern `websockets.asyncio` server API. The local bridge server uses `websockets.asyncio.server.ServerConnection` and `serve`, so older legacy-only releases are not the supported baseline.

For the v0.1 release snapshot, see [RELEASE_NOTES_v0.1.md](RELEASE_NOTES_v0.1.md).

For the v0.2 release snapshot, see [RELEASE_NOTES_v0.2.md](RELEASE_NOTES_v0.2.md).

For the v0.2.1 release snapshot, see [RELEASE_NOTES_v0.2.1.md](RELEASE_NOTES_v0.2.1.md).

For the v0.3 semi-auto recovery design memo, see [docs/SEMI_AUTO_RECOVERY.md](docs/SEMI_AUTO_RECOVERY.md).
It describes prompt-preparation automation only; it does not add auto-send, auto-approve, or auto-execute behavior.

For the v0.3 release snapshot, see [RELEASE_NOTES_v0.3.md](RELEASE_NOTES_v0.3.md).

---

## Quick Start

The shortest path to a working APOS session is:

1. Start the approval/dashboard server when you want to inspect queue state or use the local UI.

```bash
python server/list_approvals_endpoint.py
```

2. Generate a safe Context Pack from the current workspace.

```bash
python cli/apos.py context build --json
python cli/apos.py context inspect --format markdown --output context_pack.md
```

3. Build a paste-ready prompt before sending anything back to the web LLM.

```bash
python cli/apos.py prompt build --goal "Add a new status summary command" --mode patch --output prompt.md
python cli/apos.py prompt build --goal "Plan a staged refactor" --mode plan
python cli/apos.py prompt build --goal "Review the workspace for risks" --mode review
```

4. Use the task-envelope demos for validate-only and preview flows.

```bash
python cli/run_task.py examples/validate_only_demo.json --validate-only --json
python cli/run_task.py examples/preview_patch_demo.json --json
```

5. Run the browser bridge only when you want the `apos-patch` extension flow.

```bash
python server/apos_server.py
```

6. Inspect approval queue state, plan steps, and report output from the same history DB.

```bash
python cli/apos.py plans list --workspace . --json
python cli/apos.py report failures --workspace . --format markdown
python cli/apos.py report drift --workspace . --format markdown
```

7. Run the full test suite before treating the release as stable.

```bash
python -m pytest
```

If you use the project virtual environment on Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

---

## Normal Web LLM Workflow

1. Start from [docs/task_envelope_prompt.md](docs/task_envelope_prompt.md) or [examples/apos_patch_demo.md](examples/apos_patch_demo.md).
2. For task envelope work, save the JSON as:

```text
examples/current_task.json
```

3. Validate first:

```powershell
.\.venv\Scripts\python.exe cli\run_task.py examples\current_task.json --validate-only --json
```

4. If validation succeeds, preview or execute:

```powershell
.\.venv\Scripts\python.exe cli\run_task.py examples\current_task.json --json
```

5. Paste the result envelope JSON back into the web LLM.
6. For the Bridge Flow, keep the `apos-patch` metadata block and the source block adjacent, let the extension propose the patch, then approve the `commit_patch` request.

---

## Key Concepts

### Task Envelope

A task envelope is the JSON input generated by the web LLM.

Example:

```json
{
  "schema_version": "1.0",
  "task_id": "task-create-hello",
  "task_type": "patch_and_run",
  "created_by": "web_llm",
  "workspace_root": ".",
  "patches": [
    {
      "target": "workspace/hello.py",
      "language": "python",
      "content": "print('hello from APOS')\n",
      "intent": "create",
      "description": "Create hello script"
    }
  ],
  "commands": [
    {
      "command": ["python", "workspace/hello.py"],
      "description": "Run hello script",
      "expected_result": "Print hello from APOS",
      "timeout_seconds": 10
    }
  ],
  "options": {
    "enable_snapshots": false,
    "enable_patch_dry_run": true,
    "enable_command_policy": true,
    "fail_on_snapshot_error": true,
    "stop_on_first_failure": true
  },
  "meta": {
    "source": "web_llm"
  }
}
```

Required fields:

- `schema_version`
- `task_id`
- `task_type`
- `created_by`
- `workspace_root`
- `patches`
- `commands`
- `options`
- `meta`

Supported task types:

- `run`
- `patch_and_run`
- `preview_patch`
- `restore_file`
- `plan_only`

---

### Result Envelope

A result envelope is APOS's standardized JSON output after validation or execution.

Important fields:

- `status`
- `exit_code`
- `patch_applied`
- `patch_blocked`
- `patch_preview`
- `command`
- `command_allowed`
- `policy_blocked`
- `stdout`
- `stderr`

Status values:

| status | meaning |
| --- | --- |
| `success` | command completed successfully |
| `failed` | command ran but failed |
| `patch_blocked` | patch policy blocked file changes |
| `command_blocked` | command policy blocked execution |
| `snapshot_failed` | snapshot step failed |
| `validation_failed` | task envelope validation failed |
| `internal_error` | unexpected APOS error |

Negative exit codes:

| code | meaning |
| --- | --- |
| `-3` | command policy blocked |
| `-4` | patch policy blocked |
| `-5` | snapshot failed |
| `-6` | task envelope validation failed |

For result interpretation, use:

```text
docs/result_envelope_guide.md
```

---

## Safety Model

APOS is safe by default.

### Patch Policy

APOS validates patch targets before writing files.

Allowed target areas:

```text
workspace/
src/
app/
cli/
apos_core/
tests/
docs/
README.md
```

Important rule:

```text
Allowed demo target: workspace/hello.py
Blocked root target: root hello.py
```

Protected paths are blocked by default:

```text
.git/
.venv/
node_modules/
__pycache__/
.pytest_cache/
.apos/history.sqlite3
*.sqlite3
.env
secrets.*
private_key.*
.codex/
specifications/
context/
```

### Command Policy

APOS validates commands before execution.

Allowed examples:

```json
["python", "workspace/hello.py"]
["python", "-m", "pytest", "-q"]
["node", "workspace/example.js"]
```

Blocked examples:

```text
rm
del
rmdir
format
shutdown
reboot
curl
wget
Invoke-WebRequest
Invoke-Expression
powershell -EncodedCommand
sudo
runas
chmod 777
&&
;
|
```

### Important Limitation

APOS checks patch paths and command strings, but it is not a full sandbox.

For example, APOS may block:

```text
rm -rf .
```

But it cannot fully analyze every internal behavior inside generated Python code such as:

```python
import os
os.system("rm -rf .")
```

For stronger isolation, future versions may add containerized execution.

---

## Snapshots and Restore

Run demo with Git snapshots enabled:

```bash
python cli/run_orchestrator.py --enable-snapshots
```

Snapshot behavior:

- Commit message format: `APOS snapshot before task: <task_id>`
- Snapshot failure stops execution by default.
- File-level restore is preferred over destructive full rollback.

Inspect or restore:

```bash
python cli/snapshot_tools.py check-commit --commit <snapshot_commit>
python cli/snapshot_tools.py diff --commit <snapshot_commit>
python cli/snapshot_tools.py restore-file --commit <snapshot_commit> --path src/app.py
```

APOS intentionally does not use `git reset --hard` as the default restore workflow.

---

## Files and Docs

Important docs:

```text
docs/APOS_PROJECT_OVERVIEW.md
docs/task_envelope_prompt.md
docs/result_envelope_guide.md
docs/PROTOCOL.md
docs/SECURITY_MODEL.md
```

Recommended web LLM prompting file:

```text
docs/task_envelope_prompt.md
```

Recommended result analysis file:

```text
docs/result_envelope_guide.md
```

---

## Project Layout

```text
apos-orchestrator/
├── apos_core/
│   ├── orchestrator.py
│   ├── executor.py
│   ├── recorder.py
│   ├── patch_policy.py
│   ├── command_policy.py
│   ├── snapshot.py
│   ├── task_envelope.py
│   └── result_envelope.py
├── cli/
│   ├── run_task.py
│   ├── run_orchestrator.py
│   ├── snapshot_tools.py
│   └── apos.py
├── server/
│   └── apos_server.py
├── extension/
│   ├── manifest.json
│   └── contentScript.js
├── examples/
│   └── task_patch_and_run.json
├── docs/
└── README.md
```

---

## Runtime Files

The following files should not be committed:

```gitignore
.apos/history.sqlite3
*.sqlite3
examples/current_task.json
```

The history DB is runtime state, not source code.

---

## Legacy Bridge Protocol

APOS also contains an earlier Bridge Protocol flow using a browser extension and local WebSocket server.

Legacy flow:

```text
Web LLM output
→ Chrome Extension detects APOS patch envelope
→ Local WebSocket Server validates path/hash/syntax
→ Human approves
→ commit_patch writes the file
```

Run the WebSocket server:

```bash
python server/apos_server.py
```

Expected:

```text
APOS local websocket server listening on ws://127.0.0.1:8765
```

Load the Chrome extension:

1. Open `chrome://extensions`
2. Enable Developer mode
3. Click **Load unpacked**
4. Select the `extension/` folder
5. Refresh ChatGPT or Gemini

The extension currently targets:

```text
https://chatgpt.com/*
https://gemini.google.com/*
```

---

## Roadmap

Current next priorities:

1. Plan Only Mode
2. Browser Extension Safe Mode
3. Browser Extension Assisted Mode
4. Auto Review Mode
5. Auto Loop Mode
6. In-chat Overlay

### 1. Search & Replace Patch Support

Goal: reduce token usage and JSON breakage when modifying long files.

Planned patch shape:

```json
{
  "target": "workspace/example.py",
  "language": "python",
  "intent": "search_and_replace",
  "search": "old code block",
  "replace": "new code block",
  "description": "Replace one specific block"
}
```

Safety rules:

- `search` must match exactly once.
- Zero matches fail.
- Multiple matches fail.
- PatchPolicy still applies.
- Preview must be generated before applying.

Status: implemented and supported.

Example:

```json
{
  "target": "workspace/example.py",
  "language": "python",
  "intent": "search_and_replace",
  "search": "print('hello')",
  "replace": "print('hello from APOS')",
  "description": "Update printed message"
}
```

### 2. APOS Context Pack

Goal: give the web LLM a compact, safe summary of the workspace.

Context Pack should include:

- allowed working areas
- excluded protected areas
- current important files
- recent task/result summaries
- safety reminders

The standard command is:

```bash
python cli/apos.py context build --json
```

For a paste-ready prompt summary, use Markdown:

```bash
python cli/apos.py context inspect --format markdown
```

The builder also supports `--output context_pack.json` or `--output context_pack.md`.

See [examples/context_pack_demo.md](examples/context_pack_demo.md) for a paste-ready Markdown shape.

It must inherit PatchPolicy exclusions.

Status: implemented.

Run:

```bash
python cli/context_pack.py --json
```

### 3. Plan Only Mode

Goal: split complex work into smaller steps before execution.

Core task type:

```json
"task_type": "plan_only"
```

Status: implemented as validation + plan summary flow.

### 4. Browser Extension Safe Mode

Goal: detect APOS task envelope JSON inside ChatGPT/Gemini and send it to the local APOS server.

Safe Mode:

- auto-detect task envelope
- auto-validate
- require user approval before running
- display result envelope in browser
- no auto-submit

Status: planned.

### 5. Auto Review / Auto Loop

Goal: reduce manual copy/paste.

Required limits:

- default OFF
- user must explicitly start
- max loop count
- STOP button
- stop on `validation_failed`
- stop on `patch_blocked`
- stop on `command_blocked`
- stop on repeated failure

Status: future.

---

## Development Commands

Compile key Python files:

```bash
python -m py_compile cli/apos.py server/apos_server.py
```

Check extension JavaScript:

```bash
node --check extension/contentScript.js
```

Run tests:

```bash
python -m pytest -q
```