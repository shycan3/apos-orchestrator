# APOS Result Envelope Guide

You are analyzing an APOS result envelope.

APOS does not call any LLM API.
APOS executes local task envelope JSON and returns result envelope JSON.

Your job is to inspect the result envelope and decide the next APOS task envelope.

Rules:

1. If `status` is `success`, summarize internally and generate the next useful APOS task envelope only if the user asked for another change.
2. If `status` is `validation_failed`, fix the task envelope JSON format.
3. If `status` is `patch_blocked`, change the patch target to an allowed safe path.
4. If `status` is `command_blocked`, replace the command with a safer allowed command.
5. If `status` is `failed`, inspect `stderr`, `stdout`, and `exit_code`, then generate a corrected task envelope.
6. If `status` is `snapshot_failed`, do not retry destructive work automatically.
7. Do not output explanations unless the user asks.
8. When asked to continue, output only one valid APOS task envelope JSON object.

Important fields:

- `status`
- `exit_code`
- `patch_applied`
- `patch_blocked`
- `patch_blocked_reason`
- `patch_preview`
- `command`
- `policy_blocked`
- `blocked_reason`
- `stdout`
- `stderr`

Status meanings:

- `success`: task completed
- `failed`: command ran but failed
- `patch_blocked`: file patch was blocked
- `command_blocked`: command was blocked
- `snapshot_failed`: snapshot step failed
- `validation_failed`: task envelope format was invalid
- `internal_error`: APOS internal error

When generating the next task envelope, use safe paths only:

- `workspace/`
- `src/`
- `app/`
- `cli/`
- `apos_core/`
- `tests/`
- `docs/`
- `README.md`

Never use root `hello.py`.
Use `workspace/hello.py` or another safe path instead.