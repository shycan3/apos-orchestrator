Running tests and demo
---------------------

Run the unit tests (requires `pytest`):

```bash
python -m pytest
```

Run the demo orchestrator script:

```bash
python cli/run_orchestrator.py
```

Print standard result envelope JSON:

```bash
python cli/run_orchestrator.py --json
```

Validate task envelope JSON without applying patches or running commands:

```bash
python cli/run_task.py examples/task_patch_and_run.json --validate-only
python cli/run_task.py examples/task_patch_and_run.json --validate-only --json
```

Run task envelope JSON file:

```bash
python cli/run_task.py examples/task_patch_and_run.json
python cli/run_task.py examples/task_patch_and_run.json --json
```

Unsafe mode (not recommended):

```bash
python cli/run_orchestrator.py --unsafe-disable-command-policy
```

Unsafe patch mode (not recommended):

```bash
python cli/run_orchestrator.py --unsafe-disable-patch-dry-run
```

Run demo with git snapshots enabled:

```bash
python cli/run_orchestrator.py --enable-snapshots
```

If snapshot creation fails and you still want to continue task execution:

```bash
python cli/run_orchestrator.py --enable-snapshots --continue-on-snapshot-error
```

SQLite DB location:

- `cli/run_orchestrator.py` explicitly uses `workspace/.apos/history.sqlite3`.
- If `history_db_path` is not provided, recorder defaults to `.apos_history.sqlite3` in the current working directory.

Snapshot behavior:

- Snapshot commit message format: `APOS snapshot before task: <task_id>`
- By default, snapshot failure stops task execution (safe default).
- Optional `--snapshot-auto-init-git` can initialize a git repo when none exists.

Snapshot inspect/restore (safe mode):

```bash
python cli/snapshot_tools.py check-commit --commit <snapshot_commit>
python cli/snapshot_tools.py diff --commit <snapshot_commit>
python cli/snapshot_tools.py restore-file --commit <snapshot_commit> --path src/app.py
```

- APOS recommends file-level restore first.
- `git reset --hard` style full rollback is intentionally not a default APOS workflow because it is destructive.

Command execution policy (safe by default):

- APOS does not allow all commands by default.
- Commands are validated by allowlist/denylist policy before execution.
- If blocked, command is not executed and the result is recorded as `policy_blocked=true`.

Allowlist examples:

- `python`
- `pytest`
- `node`
- `npm`
- `git status`
- `git diff`

Blocked examples:

- `rm`, `del`, `rmdir`, `format`, `shutdown`, `reboot`
- `curl`, `wget`, `Invoke-WebRequest`, `Invoke-Expression`
- `powershell -EncodedCommand`
- `chmod 777`, `sudo`, `runas`
- shell injection patterns such as `&&` and `;`

To run risky commands, explicitly modify the command policy or start demo with `--unsafe-disable-command-policy`.

Patch dry-run policy (safe by default):

- APOS does not immediately apply incoming patches.
- APOS first runs patch dry-run validation and preview.
- If any patch target fails policy validation, patch application is blocked.

Dry-run preview includes:

- target file path
- whether file exists
- operation type (`create`, `update`, `overwrite`, or `delete`)
- old/new size
- changed line summary
- `policy_allowed` and `blocked_reason`

Protected path examples (blocked by default):

- `.git/`
- `.venv/`
- `node_modules/`
- `__pycache__/`
- `.pytest_cache/`
- `.apos/history.sqlite3`
- `*.sqlite3`
- `.env`
- `secrets.*`
- `private_key.*`

Allowed path examples:

- `workspace/`
- `src/`
- `app/`
- `cli/`
- `apos_core/`
- `tests/`
- `docs/`
- `README.md`

If you disable patch dry-run with `--unsafe-disable-patch-dry-run`, APOS may apply patch content without preflight policy checks, which is risky.

Result envelope (for web LLM re-analysis):

- APOS normalizes each task outcome into a standard JSON result envelope.
- Web LLM integrations should parse `status` first, then inspect `exit_code` and detailed fields.
- Envelope includes patch/snapshot/command outputs and policy decisions.

Status values:

| status | meaning |
| --- | --- |
| `success` | command completed successfully |
| `failed` | command ran but failed |
| `patch_blocked` | patch dry-run/policy blocked file changes |
| `command_blocked` | command policy blocked execution |
| `snapshot_failed` | snapshot step failed before execution |
| `validation_failed` | task envelope schema/field validation failed |
| `internal_error` | unexpected orchestrator error |

Negative exit code meanings:

| exit_code | meaning |
| --- | --- |
| `-3` | command policy blocked |
| `-4` | patch policy blocked |
| `-5` | snapshot failed |
| `-6` | task envelope validation failed |

`status` should be treated as the primary interpretation field.

Task envelope (for web LLM -> APOS input):

- Web LLM should generate task envelope JSON, not free-form prose.
- APOS validates task envelope before execution.
- Task envelope is input; result envelope is standardized output.

Task envelope required fields:

- `schema_version`
- `task_id`
- `task_type` (`run`, `patch_and_run`, `preview_patch`, `restore_file`)
- `created_by` (`user`, `web_llm`, `local_agent`)
- `workspace_root`
- `patches`
- `commands`
- `options`
- `meta`

Example task envelope file:

- `examples/task_patch_and_run.json`
- Example patch target and command path are both fixed to workspace/hello.py.
- Allowed demo target: workspace/hello.py
- Blocked root target: root hello.py

Recommended web LLM roundtrip:

1. Ask the web LLM to output only task envelope JSON.
2. Save the JSON as a local file, for example `examples/current_task.json`.
3. Validate it first:

```bash
python cli/run_task.py examples/current_task.json --validate-only --json
```

4. If validation succeeds, execute it:

```bash
python cli/run_task.py examples/current_task.json --json
```

5. Paste the result envelope JSON back into the web LLM for the next task.

Checking logs/results:

- Inspect the configured history DB path (for CLI demo: `workspace/.apos/history.sqlite3`) using `sqlite3` CLI or a DB browser.
- Suggestion files are written as `.apos_suggestion_<id>.json` in the workspace root.

# APOS v3.2 + Bridge Protocol Web-Local Orchestrator

APOS is a file-based collaboration layer between web-based LLMs and a local project.

It lets ChatGPT or Gemini propose file changes, but those changes must pass a local validation gate and wait for human sign-off before any file is written.

The Bridge Protocol is the thin translation layer that turns design-oriented AI output into executable patch instructions.

```text
Web LLM output
-> Chrome Extension detects APOS patch envelope
-> Local WebSocket Server validates path/hash/syntax
-> Human approves
-> commit_patch writes the file
```

APOS does not give the web LLM autonomous local file access.

## Project Layout

```text
apos-orchestrator/
├── cli/
│   └── apos.py
├── server/
│   └── apos_server.py
├── extension/
│   ├── manifest.json
│   └── contentScript.js
├── examples/
│   ├── valid_patch_example.md
│   └── invalid_patch_example.md
├── docs/
│   ├── USAGE.md
│   ├── PROTOCOL.md
│   ├── SECURITY_MODEL.md
│   └── SERVICE_OVERVIEW.md
└── README.md
```

## Workspace Hygiene

This repository does not require a `.vscode/` folder for APOS operation.

I checked the current workspace and did not find a `.vscode/` directory to remove, so there was nothing to delete.

## Install

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

The generated project also includes the APOS human/machine split inside `specifications/architecture.md` and the Bridge instructions inside `.codex/APOS_INSTRUCTIONS.md`.

## Run the Server

```bash
python C:/Users/DO/Documents/apos-orchestrator/server/apos_server.py
```

Expected:

```text
APOS local websocket server listening on ws://127.0.0.1:8765
```

## Load the Chrome Extension

1. Open `chrome://extensions`
2. Enable Developer mode
3. Click Load unpacked
4. Select `C:/Users/DO/Documents/apos-orchestrator/extension`
5. Refresh ChatGPT or Gemini

The extension only runs on:

```text
https://chatgpt.com/*
https://gemini.google.com/*
```

## Patch Protocol Example

A valid web LLM response uses two adjacent code blocks.

```apos-patch
{
  "patch_id": "patch-001",
  "project_root": "C:/Users/DO/Desktop/test-project",
  "target": "workspace/active_code.py",
  "language": "python",
  "sha256": "..."
}
```

```python
def main():
    print("hello")
```

The extension computes SHA-256 for the second block and sends:

```json
{
  "type": "propose_patch",
  "patch_id": "patch-001",
  "project_root": "C:/Users/DO/Desktop/test-project",
  "target": "workspace/active_code.py",
  "language": "python",
  "content": "def main():\n    print(\"hello\")\n",
  "sha256": "..."
}
```

If validation passes, the server returns:

```json
{
  "type": "validation_passed",
  "patch_id": "patch-001",
  "target": "workspace/active_code.py",
  "zone": "direct_candidate",
  "message": "Validation passed. Waiting for human sign-off."
}
```

Then a human-approved client sends:

```json
{
  "type": "commit_patch",
  "patch_id": "patch-001"
}
```

## Test

Compile Python files:

```bash
python -m py_compile cli/apos.py server/apos_server.py
```

Check the extension JavaScript:

```bash
node --check extension/contentScript.js
```

Apply APOS to a disposable project, start the server, load the extension, then paste `examples/valid_patch_example.md` into ChatGPT or Gemini.

## Failure Debugging

Check browser console logs:

```text
[APOS] Content script initialized
[APOS Debug] Raw blocks
[APOS Debug] Parsed metadata
[APOS Debug] Sending
[APOS] Server response
```

Check server terminal output:

```text
APOS local websocket server listening on ws://127.0.0.1:8765
```

Common failures:

- server is not running
- extension was not reloaded after edits
- ChatGPT/Gemini tab was not refreshed
- first code block is not `apos-patch`
- source block is not immediately after metadata block
- SHA-256 mismatch
- target path is protected
- Python syntax fails `py_compile`

## Security Model

Protected areas:

```text
specifications/
context/
.apos/
.codex/
```

Direct writes to protected areas are blocked and redirected to `workspace/scratchpad.md` as proposals.

See `docs/PROTOCOL.md` for the Bridge and patch-envelope rules, and `docs/SECURITY_MODEL.md` for the trust boundaries.

Direct candidate areas:

```text
workspace/
src/
app/
scripts/
tests/
```

Even these areas require:

```text
propose_patch -> validation -> pending buffer -> human sign-off -> commit_patch -> write
```

See `docs/SECURITY_MODEL.md` for the full model.

## Web LLM Prompting

For web LLM prompting, use `docs/task_envelope_prompt.md`.

For result envelope analysis, use `docs/result_envelope_guide.md`.