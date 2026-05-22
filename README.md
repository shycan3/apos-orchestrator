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

## APOS Roadmap

Current MVP status:

- Task envelope validation works.
- Patch dry-run works.
- Safe path policy works.
- Command policy works.
- Local file creation/update works.
- Command execution works.
- Result envelope output works.
- Manual Web LLM → APOS → Web LLM loop has been verified.

Next development priorities:

1. Search & Replace Patch Support
2. APOS Context Pack
3. Plan Only Mode
4. Browser Extension Safe Mode
5. Browser Extension Assisted Mode
6. Auto Review Mode
7. Auto Loop Mode
8. In-chat Overlay

### 1. Search & Replace Patch Support

Goal:

Reduce token usage and JSON breakage when modifying long files.

Current patch mode usually sends full file content through `content`.

This works for small files, but becomes inefficient for large files.

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
````

Safety rules:

* `search` must match exactly once.
* If `search` matches zero times, the patch must fail.
* If `search` matches multiple times, the patch must fail.
* APOS must preview the replacement before applying it.
* PatchPolicy still applies to the target path.

Status:

```text
Planned. Not implemented yet.
```

### 2. APOS Context Pack

Goal:

Give the web LLM a compact, safe summary of the local workspace.

Context Pack should include:

* allowed working areas
* excluded protected areas
* current important files
* recent task/result summaries
* safety reminders

Context Pack must not dump the whole project.

It must inherit PatchPolicy exclusions.

Excluded examples:

* `.git/`
* `.venv/`
* `node_modules/`
* `.apos/`
* `*.sqlite3`
* `.env`
* `secrets.*`
* `private_key.*`

Status:

```text
Planned.
```

### 3. Plan Only Mode

Goal:

Split complex work into safer smaller steps.

Planned task type:

```json
"task_type": "plan_only"
```

This allows the web LLM to first output a plan instead of immediately producing a large patch.

Status:

```text
Planned.
```

### 4. Browser Extension Safe Mode

Goal:

Detect APOS task envelope JSON directly inside ChatGPT/Gemini and send it to the local APOS server.

Safe Mode behavior:

* Detect task envelope automatically.
* Validate automatically.
* Require user approval before running.
* Show result envelope in the browser.
* Do not auto-submit responses.

Status:

```text
Planned.
```

### 5. Auto Review / Auto Loop

Goal:

Reduce manual copy/paste further.

Auto Review Mode:

* Automatically run tasks that pass policy checks.
* Stop on blocked or failed states.

Auto Loop Mode:

* Automatically send result envelope back to the web LLM.
* Detect the next task envelope.
* Repeat with strict loop limits.

Required safety limits:

* default OFF
* user must explicitly start
* max loop count
* STOP button
* stop on validation_failed
* stop on patch_blocked
* stop on command_blocked
* stop on repeated failure

Status:

```text
Future.
```

````

---

## 2. `docs/APOS_PROJECT_OVERVIEW.md`의 개발 우선순위 교체

문서 아래쪽의 **“현재 개발 우선순위”** 부분을 아래로 바꿔.

```markdown
## 26. 현재 개발 우선순위

현재 기준 다음 개발 우선순위는 다음과 같다.

```text
1. Search & Replace Patch Support
2. APOS Context Pack v0.1
3. Plan Only Mode
4. Browser extension Safe Mode
5. Browser extension Assisted Mode
6. Auto Review Mode
7. Auto Loop Mode
8. In-chat Overlay
````

---

### 26.1 Search & Replace Patch Support

가장 먼저 구현할 기능이다.

현재 APOS는 주로 파일 전체 내용을 `content`에 담아 생성/수정한다.

작은 파일에서는 문제가 없지만, 긴 파일에서는 다음 문제가 생긴다.

```text
- JSON 출력이 길어진다.
- 웹 LLM 출력이 중간에 끊길 수 있다.
- 따옴표/줄바꿈 오류가 늘어난다.
- 한 줄 수정에도 전체 파일을 다시 보내야 한다.
- 불필요한 토큰을 많이 사용한다.
```

따라서 `intent: "search_and_replace"`를 도입한다.

예상 patch 형식:

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

안전 원칙:

```text
1. search는 정확히 한 번만 매칭되어야 한다.
2. 0번 매칭이면 실패한다.
3. 2번 이상 매칭이면 실패한다.
4. 적용 전 preview를 생성한다.
5. PatchPolicy는 그대로 적용한다.
6. 보호 경로는 여전히 차단한다.
```

이 기능은 웹 LLM의 JSON 파싱 오류와 토큰 낭비를 줄이는 데 직접적으로 기여한다.

---

### 26.2 APOS Context Pack

Search & Replace 다음으로 구현할 기능이다.

Context Pack은 웹 LLM에게 현재 로컬 프로젝트 상태를 안전하게 전달하는 요약 정보다.

Context Pack은 전체 파일 덤프가 아니다.

Context Pack은 PatchPolicy의 보호 경로를 상속해야 한다.

기본 제외 경로:

```text
.git/
.venv/
node_modules/
__pycache__/
.pytest_cache/
.apos/
*.sqlite3
.env
secrets.*
private_key.*
.codex/
specifications/
context/
dist/
build/
```

Context Pack은 다음 정보를 포함한다.

```text
- 프로젝트 루트
- 허용된 작업 경로
- 제외된 보호 경로
- 현재 주요 파일 목록
- 최근 task/result 요약
- 안전 정책 요약
- 웹 LLM에게 줄 주의사항
```

권장 제한:

```text
max_depth = 4
max_files = 120
max_file_preview_chars = 1200
max_total_chars = 12000
```

---

### 26.3 Plan Only Mode

복잡한 작업을 한 번에 실행하지 않고 단계별 계획으로 나누기 위한 기능이다.

예상 task type:

```json
"task_type": "plan_only"
```

목표:

```text
1. 웹 LLM이 먼저 작업 계획만 출력한다.
2. APOS 또는 사용자가 계획을 확인한다.
3. 각 단계를 작은 task envelope로 나누어 실행한다.
4. Auto Loop에서 단계별 진행이 가능해진다.
```

Plan Only Mode는 Auto Loop의 안정성을 높이는 기반 기능이다.

---

### 26.4 Browser Extension Safe Mode

브라우저 확장 v0.1의 목표다.

기능:

```text
- ChatGPT/Gemini 응답에서 APOS task envelope JSON 감지
- 코드블록 JSON 추출
- 스트리밍 안정화 debounce
- task envelope schema 검사
- 중복 task_id 방지
- Validate 버튼
- Run 버튼
- result envelope 표시
- Copy Result 버튼
```

Safe Mode에서는 자동 실행하지 않는다.

사용자가 명시적으로 실행해야 한다.

---

### 26.5 Auto Review Mode

정책상 안전한 작업은 자동 실행하는 모드다.

동작:

```text
- task envelope 자동 감지
- validate 자동 수행
- patch policy / command policy 통과 시 자동 실행
- result envelope 자동 삽입
- 실패/차단 상태에서는 중단
```

---

### 26.6 Auto Loop Mode

웹 LLM과 APOS가 제한된 횟수 안에서 반복 실행하는 모드다.

필수 제한:

```text
- 기본 OFF
- 사용자가 명시적으로 시작
- 최대 반복 횟수 제한
- STOP 버튼
- 같은 실패 반복 시 중단
- patch_blocked / command_blocked / validation_failed 발생 시 중단
```

Auto Loop는 APOS의 최종 UX 목표지만, Search & Replace, Context Pack, Plan Only Mode 이후에 구현한다.

---

### 26.7 In-chat Overlay

브라우저 확장 안정화 이후 구현할 UX 기능이다.

목표:

```text
- Gemini/ChatGPT 답변 하단에 APOS 실행 결과 표시
- 성공/실패 상태를 인라인 카드로 표시
- 로그 보기
- 결과 복사
- 결과 삽입
```

초기 구현은 floating panel이 우선이며, In-chat Overlay는 후순위다.

````

---

## 3. `docs/task_envelope_prompt.md`에 주의 문구 추가

아직 `search_and_replace`가 구현되지 않았으니까, 이 문구를 **Patch Rules 근처**에 추가해.

```markdown
## Currently Supported Patch Intents

Currently supported patch intents are:

- `create`
- `update`
- `overwrite`

Do not output `search_and_replace` yet.

`search_and_replace` is a planned APOS feature, but it is not available until the local APOS executor implements it.

Until then, use `create`, `update`, or `overwrite`.
````


