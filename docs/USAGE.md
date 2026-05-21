# APOS v3.2 Web-Local Orchestrator Usage

APOS connects web LLM output to a local project through a local validation gate.

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

The extension reads `pre code` blocks, finds `language-apos-patch`, pairs it with the immediately following code block, computes SHA-256, and sends a `propose_patch` message.

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
