# APOS v3.2 Protocol

Default server:

```text
ws://127.0.0.1:8765
```

All messages are UTF-8 JSON text frames.

## ping

Request:

```json
{
  "type": "ping"
}
```

Response:

```json
{
  "type": "pong",
  "message": "APOS local server alive",
  "pending_patches": 0
}
```

## propose_patch

Request:

```json
{
  "type": "propose_patch",
  "patch_id": "patch-id",
  "project_root": "C:/Users/DO/Desktop/test-project",
  "target": "workspace/active_code.py",
  "language": "python",
  "content": "def main():\n    pass\n",
  "sha256": "..."
}
```

Required fields:

- `type`: must be `propose_patch`
- `patch_id`: unique patch identifier
- `project_root`: existing local project directory
- `target`: project-relative target path
- `language`: source language
- `content`: full final file content
- `sha256`: SHA-256 of `content`

Successful response:

```json
{
  "type": "validation_passed",
  "patch_id": "patch-id",
  "target": "workspace/active_code.py",
  "zone": "direct_candidate",
  "message": "Validation passed. Waiting for human sign-off."
}
```

Validation failure:

```json
{
  "type": "validation_failed",
  "patch_id": "patch-id",
  "error_kind": "python_syntax_error",
  "stderr": "...",
  "retry_allowed": true
}
```

Protected write redirect:

```json
{
  "type": "protected_write_redirected",
  "patch_id": "patch-id",
  "target": "specifications/core_direction.md",
  "zone": "protected",
  "message": "Protected write blocked. Proposal was appended to workspace/scratchpad.md.",
  "scratchpad": "C:/Users/DO/Desktop/test-project/workspace/scratchpad.md"
}
```

## commit_patch

Request:

```json
{
  "type": "commit_patch",
  "patch_id": "patch-id"
}
```

Successful response:

```json
{
  "type": "commit_succeeded",
  "patch_id": "patch-id",
  "target": "workspace/active_code.py"
}
```

Failure when the patch is absent, expired, already committed, or never validated:

```json
{
  "type": "error",
  "patch_id": "patch-id",
  "error_kind": "patch_not_found",
  "message": "No validated pending patch found for patch_id",
  "retry_allowed": false
}
```

## Error Rules

The server returns explicit errors for:

- invalid JSON
- non-object payloads
- unknown message type
- missing `patch_id`
- missing `project_root`
- missing `target`
- missing `sha256`
- SHA-256 mismatch
- path traversal
- absolute target paths
- null bytes
- project root escape
- unsupported language
- Python syntax failure
- duplicate patch IDs

Silent failure is not allowed.
