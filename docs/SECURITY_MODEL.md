# APOS Security Model

This document describes the current APOS security baseline for the v0.3 release line and the committed post-v0.3 runtime and bridge behavior.

The browser bridge and dashboard flow are approval-oriented, while the task-envelope CLI flow may still perform policy-checked direct apply/run operations locally.

APOS follows this operating sentence:

```text
Web LLMs propose, local APOS validates, humans approve.
```

The web LLM is never trusted as an authority.

APOS does not try to eliminate failure. It makes failure traceable and recoverable.

## Role Separation

- Web LLM: proposal author only
- APOS Core: validation and execution authority
- User: approval authority for queue items, plans, and bridge commits
- Web Controller / external browser automation: experimental future work only

## Layer Model

- Project Memory Layer stores project state, decisions, and task context.
- AI Bridge Layer translates design output into execution-ready patch instructions.

## Trust Boundaries

Trusted:

- local APOS CLI
- local APOS WebSocket server
- human approval

Design output from ChatGPT, Gemini, or Claude is treated as advisory only.

Untrusted:

- ChatGPT output
- Gemini output
- web page DOM content
- copied code blocks

## Localhost Only

The server binds to:

```text
127.0.0.1:8765
```

Non-local WebSocket clients are rejected.

## Protected Areas

The following paths are protected:

```text
specifications/
context/
.apos/
.codex/
```

They store durable project direction, decisions, system rules, and AI instructions.

Direct writes to these areas are forbidden. A proposal targeting a protected area is appended to:

```text
workspace/scratchpad.md
```

The actual protected file is not modified by the server.

## Direct Candidate Areas

The following areas may be written after validation and human sign-off:

```text
workspace/
src/
app/
scripts/
tests/
```

Even in these areas, `propose_patch` does not write files. It only validates and stores a pending patch. `commit_patch` is required to write.

## Human and Machine Isolation

`specifications/architecture.md` is split into human notes and machine facts.

Refresh flows may update only the machine facts block and must leave human notes untouched.

## Risk Queue

`risk_vector.json` follows the APOS Risk Queue contract:

```json
{
	"protocol": "APOS Risk Queue",
	"max_queue_limit": 5,
	"overflow_policy": "archive_resolved_then_request_approval",
	"active_pending_risks": []
}
```

Unresolved risks are not deleted automatically. Moving them out of the queue requires approval.

## Forbidden Target Paths

The server rejects:

- absolute target paths
- paths containing null bytes
- `../` traversal
- paths resolving outside `project_root`
- targets outside protected or direct-candidate policy

## Content Validation

The server verifies:

- content is a string
- content size is below the configured maximum
- SHA-256 matches the supplied `sha256`
- `language: python` passes `py_compile.compile(..., doraise=True)`

Unsupported languages fail explicitly.

## Context Pack Safety

Context Pack은 웹 LLM에게 주는 안전한 작업 맥락만 담는다.

다음은 포함하지 않는다.

- `.env` 같은 환경 변수 비밀값
- `secret`, `token`, `key`, `password`, `private key` 계열의 민감 문자열 본문
- `.git`, `.venv`, `node_modules`, build output, cache output
- protected roots의 파일 본문
- 대용량 파일의 전체 본문

Context Pack은 파일 경로와 작은 요약만 제공하고, 실행 권한이나 원본 비밀값을 전달하지 않는다.

## Failure / Drift Reports

Failure / Drift Report도 read-only다.

보안 규칙:

- 실패 기록, 승인 거부, drift signal을 요약할 뿐 파일을 수정하지 않는다
- 다음 프롬프트 제안은 참고용이며 실행 권한을 부여하지 않는다
- report CLI와 dashboard는 기존 Recorder와 Context Pack 데이터만 읽는다
- secret/token/key/password/private key 본문은 보고서에도 그대로 노출하지 않는다

## Recovery Prompt Loop

Recovery Prompt Loop는 복구용 Markdown을 만들 뿐 자동화를 부여하지 않는다.

보안 규칙:

- `recover prompt` 결과는 사람이 복사해서 검토한 뒤에만 웹 LLM에 붙여넣는다
- `--copy`는 단순한 로컬 clipboard 보조일 뿐 자동 전송이 아니다
- `--mode auto`는 추천 모드만 고를 뿐 자동 전송이나 자동 실행 경로를 만들지 않는다
- command 실패와 drift 신호를 요약해도 실행 권한은 부여하지 않는다
- protected roots의 파일 본문은 recovery prompt에 직접 노출되지 않는다
- mode override는 추천 출력 계약만 바꾸며 승인/실행 경계를 바꾸지 않는다

## Prompt Builder Safety

Prompt Builder는 Context Pack을 그대로 재전송하는 도구가 아니라, 안전하게 정제된 markdown 프롬프트를 만든다.

보안 규칙:

- 로컬 파일 수정이나 명령 실행 권한을 부여하지 않는다
- protected roots는 여전히 쓰기 금지다
- secret/token/key/password/private key 값은 마스킹된 Context Pack만 반영한다
- mode가 불분명하면 patch 대신 review 또는 plan을 권한다
- auto recommendation is still advisory; the human must review the selected mode before copying the prompt
- 생성된 프롬프트는 user summary와 APOS payload를 분리하도록 요구한다
- 사용자가 요청하지 않은 숨은 명령이나 부수효과를 만들지 않는다
- 로컬 상태는 Context Pack으로만 판단하고 추측은 추측이라고 표시한다

## Retry Limit

The extension may inject an automatic retry prompt for `validation_failed`.

Maximum retry count:

```text
2
```

After that, human intervention is required.

## Non-Goals

APOS does not do the following:

- call AI APIs
- run an autonomous background agent loop
- send project files to external servers
- use a database
- modify protected areas directly
- commit without human sign-off
- execute arbitrary shell commands from web output
