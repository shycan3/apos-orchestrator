# APOS v3.2 Web-Local Orchestrator

APOS is a safety layer between web-based LLMs and a local project.

It lets ChatGPT or Gemini propose file changes, but those changes must pass a local validation gate and wait for human sign-off before any file is written.

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
