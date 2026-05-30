# APOS Service Overview

작성일: 2026-05-21

## 서비스 한 줄 정의

이 문서는 APOS v0.3 기준선과 그 이후 이미 커밋된 runtime / bridge 확장을 함께 설명하는 현재 서비스 개요다.

`Bridge Protocol`은 APOS 전체 버전명이 아니라 browser-local integration layer를 가리키는 subsystem 이름으로 사용한다.

APOS는 ChatGPT나 Gemini 같은 웹 기반 LLM의 코드 제안을 로컬 프로젝트 파일로 연결하되, 그 제안을 절대 바로 신뢰하지 않고 로컬 검증 서버와 인간 승인 단계를 통과하게 만드는 안전한 파일 기반 협업 서비스다.

짧게 말하면:

```text
웹 LLM은 제안하고, 로컬 APOS는 검증하며, 인간이 승인한다.
```

## Earlier Stabilized Baseline (v0.1)

아래 흐름은 earlier stabilized baseline을 설명하는 요약이며, 현재 canonical line은 v0.3과 committed post-v0.3 runtime/bridge work를 기준으로 본다.

```text
Context Pack / Prompt Builder
- `--mode auto`는 failure cause를 보고 patch / plan / review 중 하나를 추천하지만, 웹 LLM으로 자동 전송하지 않는다.
→ task envelope 또는 apos-patch proposal
→ APOS Core validation and execution
→ Recorder / approval_items / result_envelope / report_builder
→ CLI / dashboard / reports
```

핵심 컴포넌트는 다음과 같다.

- `apos_core.context_pack`: 안전한 작업 맥락 생성
- `apos_core.prompt_builder`: patch/plan/review 프롬프트 생성
- `apos_core.plan_flow`: plan_only step 상태 관리
- `apos_core.report_builder`: failure / drift analysis와 next-prompt 생성
- `apos_core.recorder`: task, result, approval item 기록
- `server/list_approvals_endpoint.py`: approval queue, plan, dashboard JSON과 UI 제공
- `server/apos_server.py`: apos-patch proposal 검증과 commit_patch 처리

## 대표 사용 흐름

APOS에서 처음 소개할 때는 아래 세 흐름을 함께 보여주면 된다.

1. `examples/validate_only_demo.json`을 `cli/run_task.py --validate-only --json`으로 검증한다.
2. `examples/preview_patch_demo.json`을 `cli/run_task.py --json`으로 미리보기한다.
3. `examples/apos_patch_demo.md`의 `apos-patch` 코드블록을 브라우저 확장과 `server/apos_server.py`로 받아서 `validation_passed` 후 `commit_patch`로 반영한다.

task envelope 경로는 `workspace/.apos/history.sqlite3`에 result envelope를 남기고, Bridge 경로는 검증된 패치를 `commit_patch`로 실제 파일에 쓴다.

## 왜 필요한가

웹 LLM은 강력하지만 브라우저 밖의 로컬 파일 시스템을 직접 다룰 수 없다. 반대로 로컬 자동화 도구는 파일을 다룰 수 있지만, 웹 LLM의 출력은 신뢰할 수 없는 외부 입력이다.

APOS는 이 둘 사이에 검증 게이트를 둔다.

```text
ChatGPT/Gemini의 패치 제안
↓
Chrome Extension이 코드블록 감지
↓
Local WebSocket Server가 경로/해시/문법/보호 영역 검증
↓
검증 통과 시 pending buffer에 보관
↓
인간 승인 후 commit_patch
↓
로컬 파일에 반영
```

이 구조 덕분에 웹 LLM의 생산성을 쓰면서도, 위험한 자동 쓰기와 조용한 실패를 피할 수 있다.

## 이 서비스가 하는 일

현재 APOS service structure는 크게 네 가지 일을 한다.

1. 프로젝트에 APOS 정적 구조를 만든다.
2. 프로젝트의 관찰 가능한 기술 사실을 수집하고 Drift Report를 남긴다.
3. 웹 LLM 답변에서 APOS 패치 봉투를 감지한다.
4. 로컬 서버가 패치를 검증하고, 인간 승인 후 파일을 쓴다.

## 이 서비스가 하지 않는 일

APOS는 다음을 하지 않는다.

```text
AI API 호출
백그라운드 자율 에이전트 루프
웹 LLM 출력의 무조건 신뢰
외부 서버로 프로젝트 파일 전송
DB 저장
보호 영역 직접 수정
인간 승인 없는 커밋
웹 출력으로 임의 shell command 실행
```

즉, APOS는 “자동 개발 에이전트”라기보다는 “웹 LLM 출력과 로컬 파일 시스템 사이의 안전 검문소”다.

## 구성 요소

현재 구현된 프로젝트 경로:

```text
C:\Users\DO\Documents\apos-orchestrator
```

구성:

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

### CLI

파일:

```text
cli/run_task.py
cli/plan_approve.py
cli/approvals.py
cli/list_approvals.py
cli/apos.py
```

역할:

- `cli/run_task.py`: validate-only, preview_patch, patch_and_run, restore_file 작업 실행 및 result envelope 기록
- `cli/plan_approve.py`: 기록된 plan_only step 승인 후 실행
- `cli/approvals.py`: pending approval 큐의 list/show/approve/reject 관리
- `cli/list_approvals.py`: legacy task_id 기준 승인 이벤트 조회
- 실제 프로젝트에 APOS 기본 폴더 생성
- `.apos/`, `.codex/`, `specifications/`, `context/`, `workspace/`, `archives/` 생성
- `specifications/architecture.md`에 Human Notes와 Machine Facts 분리 구조 생성
- refresh 시 보호 문서를 직접 수정하지 않고 `workspace/scratchpad.md`에 Drift Report 작성
- Codex에게 넘길 APOS STRICT MODE 문장 출력
- browser-local bridge protocol layer용 `.codex/APOS_INSTRUCTIONS.md` 생성
- Context Pack JSON/Markdown 생성 및 `apos context build|inspect` 실행

### Plan Step Flow

Plan step 관리는 APOS가 웹 LLM의 계획을 안전한 작은 실행 단위로 나누는 지점이다. `PlanStepManager`가 상태 전이를 담당하고, 사용자는 `cli/apos.py plans ...`를 통해 표준적으로 접근한다.

흐름:

1. `plan_only` envelope를 생성하고 history DB에 기록한다.
2. `cli/apos.py plans list|show|steps`로 상태를 확인한다.
3. `approve-step` 또는 `reject-step`으로 step 상태를 바꾼다.
4. `run-step`으로 승인된 step을 실행하고 `result_envelope`를 받는다.
5. `executed`와 `failed` step은 기본 재실행이 막히며 `--force`가 필요하다.

호환용 래퍼:

- `cli/plan_step.py`: 파일 기반 plan_only step 단독 실행
- `cli/plan_approve.py`: 기록된 plan_only step 승인 후 실행

주요 명령:

```bash
python cli/apos.py apply -y <project_path>
python cli/apos.py refresh <project_path>
python cli/apos.py summarize <project_path>
python cli/apos.py codex
python cli/apos.py context build --json
python cli/apos.py context inspect --format markdown
python cli/context_pack.py --json
```

### Context Pack

Context Pack은 웹 LLM에게 제공할 안전한 작업 맥락을 만든다.

역할:

- 허용된 루트와 보호 경로를 분리해 보여준다
- `.env`, secret/token/key/password 유사 값과 큰 파일 본문을 제외하거나 마스킹한다
- `project_updates/WORKLOG.md`, 최근 결과 기록, 승인 큐 요약을 작게 요약한다
- Markdown 출력은 ChatGPT/Gemini에 바로 붙여넣을 수 있게 구성한다

주요 명령:

```bash
python cli/apos.py context build --json
python cli/apos.py context inspect --format markdown --output context_pack.md
```

### Prompt Builder

Prompt Builder는 Context Pack과 사용자 목표를 합쳐 웹 LLM에 바로 붙여넣는 프롬프트를 만든다.

역할:

- 현재 Context Pack을 안전하게 재사용한다
- patch, plan, review 모드별 출력 계약을 명시한다
- 웹 LLM이 로컬 파일을 직접 수정하지 못하도록 안전 규칙을 함께 전달한다

주요 명령:

```bash
python cli/apos.py prompt build --goal "작업 목표" --mode patch --output prompt.md
python cli/apos.py prompt build --goal "작업 목표" --mode plan
python cli/apos.py prompt build --goal "작업 목표" --mode review
```

### Failure / Drift Report

Failure / Drift Report는 Recorder와 Context Pack을 함께 읽어서 실패 원인, 오래된 컨텍스트 신호, 다음 행동을 정리한다.

역할:

- 최근 실패 결과와 승인 거부를 모아 cause summary를 만든다
- file mtime, old pending approval, recent failure hotspot으로 drift warning을 계산한다
- `report failures|failure|drift|next-prompt` CLI와 `/api/dashboard` payload를 같은 코어 로직으로 맞춘다
- 대시보드에는 최근 failed approval item과 drift warning banner를 보여준다

주요 명령:

```bash
python cli/apos.py report failures --workspace /path/to/workspace --format markdown
python cli/apos.py report drift --workspace /path/to/workspace --format markdown
python cli/apos.py report next-prompt --workspace /path/to/workspace
```

### Dashboard Recovery UX

대시보드는 `report_builder`와 `recovery_prompt_builder`를 재사용해 failed item 요약, drift banner, recovery prompt preview/copy를 보여준다.

표시 항목:

- failed item count와 recent failed item cards
- failure summary, likely cause, affected files, stdout/stderr/exit_code
- recommended human action과 recovery prompt textarea
- drift warning banner와 recovery guidance

### Recovery Prompt Loop

Recovery Prompt Loop is a read-only helper on top of the report builder and prompt builder.

역할:

- `report_builder`가 failure / drift signal을 수집한다
- `prompt_builder`가 patch / plan / review 출력 계약과 안전 문구를 재사용한다
- `recover prompt`가 사용자가 다시 웹 LLM에 붙여넣을 Markdown recovery prompt를 만든다
- automatic execute, approve, or web sending은 하지 않는다

주요 명령:

```bash
python cli/apos.py recover prompt --latest --workspace /path/to/workspace --output recovery_prompt.md --copy
python cli/apos.py recover prompt --failure patch-failure --workspace /path/to/workspace
python cli/apos.py recover prompt --drift --workspace /path/to/workspace
```

### Local WebSocket Server

파일:

```text
server/apos_server.py
server/approve_endpoint.py
server/list_approvals_endpoint.py
```

역할:

- `server/apos_server.py`: `ws://127.0.0.1:8765`에서 `apos-patch`를 검증하고 commit_patch를 기다림
- `server/approve_endpoint.py`: approval queue item의 approve/reject와 plan_only step 실행을 처리하는 HTTP 엔드포인트
- `server/list_approvals_endpoint.py`: approval queue item의 목록/상세 조회 HTTP 엔드포인트
- localhost 연결만 허용
- `propose_patch`, `commit_patch`, `ping` 처리
- `target` 경로 보안 검사
- `sha256` 검증
- Python 문법 검사
- 보호 영역 직접 쓰기 차단
- 검증 통과 패치를 pending buffer에 저장
- `commit_patch`가 들어와야 실제 파일 쓰기
- 보호 영역 요청은 `workspace/scratchpad.md`로 리다이렉트

### Local Dashboard

파일:

```text
server/list_approvals_endpoint.py
server/approvals_ui.html
```

역할:

- `server/list_approvals_endpoint.py`: 승인 큐, plan 목록, 대시보드 요약, approve/reject/run JSON API와 HTML UI를 함께 제공
- `server/approvals_ui.html`: 로컬 브라우저에서 여는 최소 조회 UI
- `GET /`, `GET /ui`, `GET /ui/approvals`, `GET /ui/plans`: 대시보드 진입점
- `GET /api/dashboard`: pending / failed / recent executed / recent plans 요약
- `GET /api/approvals`, `GET /api/plans`: 승인 큐와 plan 상태 조회
- `POST /api/approvals/approve`, `POST /api/approvals/reject`, `POST /api/plans/approve-step`, `POST /api/plans/reject-step`, `POST /api/plans/run-step`: 최소 승인/거절/실행 액션
- UI는 DB를 직접 수정하지 않고, 모든 액션을 Orchestrator와 PlanStepManager 정책으로 통과시킨다

### Chrome Extension

파일:

```text
extension/manifest.json
extension/contentScript.js
```

역할:

- ChatGPT와 Gemini 페이지에서 실행
- `document.querySelectorAll("pre code")` 기반으로 코드블록 탐색
- 첫 번째 `apos-patch` 코드블록과 바로 다음 코드블록을 페어링
- source code block의 `textContent`만 사용
- `innerHTML`, `innerText` 사용 금지
- source content의 SHA-256 계산
- 로컬 서버로 `propose_patch` 전송
- `validation_failed` 수신 시 최대 2회 자동 재질의 프롬프트 삽입

### Bridge Layer

Bridge Layer는 설계형 AI 출력과 실행형 AI 작업 명세 사이의 변환 규칙을 담는다.

역할:

- 설계형 출력에서 실행 가능한 patch envelope만 추출
- 보호 영역 대상 제안은 수정 대신 scratchpad 제안으로 전환
- 인간이 읽는 메모와 머신이 읽는 facts 블록을 분리

대상 사이트:

```text
https://chatgpt.com/*
https://gemini.google.com/*
```

### Examples

파일:

```text
examples/validate_only_demo.json
examples/preview_patch_demo.json
examples/apos_patch_demo.md
examples/valid_patch_example.md
examples/invalid_patch_example.md
```

역할:

- `validate_only_demo.json`: task envelope 검증 전용 예제
- `preview_patch_demo.json`: patch preview 예제
- `apos_patch_demo.md`: 웹 LLM `apos-patch` 승인/실행 예제
- 정상 패치 예시
- Python 문법 오류 실패 예시
- 확장 프로그램과 서버를 수동 테스트할 때 사용

## 패치 봉투 형식

웹 LLM은 정확히 두 개의 인접한 fenced code block을 출력해야 한다.

첫 번째 코드블록은 metadata envelope다.

```apos-patch
{
  "patch_id": "patch-001",
  "project_root": "C:/Users/DO/Desktop/test-project",
  "target": "workspace/active_code.py",
  "language": "python",
  "sha256": "..."
}
```

두 번째 코드블록은 실제 파일 content다.

```python
def main():
    print("hello")
```

확장 프로그램은 두 번째 코드블록의 전체 `textContent`를 `content`로 삼고, SHA-256을 계산해 서버에 보낸다.

서버에 실제로 전송되는 메시지는 다음 형태다.

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

## 성공 흐름

1. 웹 LLM이 두 코드블록을 출력한다.
2. Extension이 `apos-patch` 블록을 찾는다.
3. Extension이 바로 다음 코드블록을 source content로 읽는다.
4. Extension이 SHA-256을 계산한다.
5. Extension이 `propose_patch`를 로컬 서버에 보낸다.
6. 서버가 path, hash, language validation을 수행한다.
7. 서버가 pending buffer에 저장한다.
8. 서버가 `validation_passed`를 반환한다.
9. 인간 승인 후 `commit_patch`가 전송된다.
10. 서버가 실제 파일을 쓴다.

성공 응답 예:

```json
{
  "type": "validation_passed",
  "patch_id": "patch-001",
  "target": "workspace/active_code.py",
  "zone": "direct_candidate",
  "message": "Validation passed. Waiting for human sign-off."
}
```

커밋 성공 예:

```json
{
  "type": "commit_succeeded",
  "patch_id": "patch-001",
  "target": "workspace/active_code.py"
}
```

## 실패 흐름

실패할 수 있는 대표 상황:

- JSON 파싱 실패
- `sha256` 불일치
- 절대경로 target
- `../` 경로 탈출
- null byte
- project root 밖으로 탈출
- 보호 영역 직접 수정 시도
- Python 문법 오류
- 지원하지 않는 language
- 중복 patch_id

Python 문법 오류 응답 예:

```json
{
  "type": "validation_failed",
  "patch_id": "patch-invalid-python-001",
  "error_kind": "python_syntax_error",
  "stderr": "...",
  "retry_allowed": true
}
```

Extension은 이 응답을 받으면 웹 LLM 입력창에 재질의 프롬프트를 넣을 수 있다.

Retry 규칙:

```text
1회 실패 -> 자동 재질의
2회 실패 -> 자동 재질의
3회 실패 -> 중단, 인간 개입 필요
```

## 보호 영역 정책

보호 영역:

```text
specifications/
context/
.apos/
.codex/
```

이 영역은 프로젝트의 방향, 결정, 시스템 규칙, AI 지침을 담는다.

따라서 APOS 서버는 이 영역을 직접 쓰지 않는다. 보호 영역으로 들어온 패치는 실제 target 파일에 쓰지 않고, 다음 파일에 제안서로 남긴다.

```text
workspace/scratchpad.md
```

보호 영역 응답 예:

```json
{
  "type": "protected_write_redirected",
  "patch_id": "patch-protected-001",
  "target": "specifications/core_direction.md",
  "zone": "protected",
  "message": "Protected write blocked. Proposal was appended to workspace/scratchpad.md.",
  "scratchpad": "C:/Users/DO/Desktop/test-project/workspace/scratchpad.md"
}
```

## 직접 수정 후보 영역

검증 후 커밋 가능한 영역:

```text
workspace/
src/
app/
scripts/
tests/
```

단, 이 영역도 즉시 쓰지 않는다.

반드시:

```text
propose_patch
-> validation_passed
-> pending buffer
-> human sign-off
-> commit_patch
-> write
```

순서를 거친다.

## APOS CLI의 Machine Facts / Drift Report

CLI는 프로젝트의 기술적 사실을 관찰한다.

예:

- `package.json` 존재 여부
- `pyproject.toml` 존재 여부
- `requirements.txt` 존재 여부
- 주요 dependency 이름
- framework hint
- source file count

`apply`는 `specifications/architecture.md`에 Machine Facts 블록을 만든다.

토큰:

```html
<!-- APOS_FACTS_START -->
<!-- APOS_FACTS_END -->
```

`refresh`는 이 블록을 직접 수정하지 않는다. 대신 새로 관찰된 facts와 기존 facts의 차이를 `workspace/scratchpad.md`에 Drift Report로 남긴다.

이유:

```text
영구 사양서는 인간이 승인해서 수정해야 한다.
자동 refresh가 프로젝트 방향 문서를 몰래 바꾸면 안 된다.
```

## 사용자 역할

### Human Architect

최종 결정권자다.

- 패치 승인
- 보호 영역 수정 여부 판단
- APOS 규칙 변경 승인
- 위험한 변경 허가

### ChatGPT

코드 설계 및 패치 생성 담당이다.

- 구현 전략 제안
- APOS 패치 코드블록 작성
- 오류 리포트 기반 수정

### Gemini

비판 및 피드백 담당이다.

- 설계 허점 지적
- 반례 제시
- UX 개선점 제안
- 보안 모델 검토

### Codex

실제 로컬 구현 담당이다.

- 파일 생성
- 코드 수정
- 테스트 실행
- 결과 보고

## 현재 구현 완료 상태

구현된 것:

- APOS current project structure
- Pure Shell CLI
- Local WebSocket validation server
- Manifest v3 Chrome extension
- `apos-patch` + source block 페어링
- SHA-256 계산
- Python syntax validation
- protected write redirect
- pending buffer + commit flow
- 최대 2회 retry injection
- protocol/security/usage 문서
- valid/invalid 예제

검증된 것:

- Python `py_compile`
- Extension JavaScript syntax
- Manifest JSON parsing
- CLI `apply`, `refresh`, `summarize`, `codex`
- 서버 `propose_patch -> validation_passed`
- 서버 `commit_patch -> commit_succeeded`
- 보호 영역 `protected_write_redirected`
- Extension에서 금지된 `innerHTML`, `innerText` 미사용

## 아직 개선할 수 있는 것

현재 버전은 실행 가능한 최소 안전 구현이다. 다음 개선이 가능하다.

- Extension popup으로 pending patch 목록 표시
- commit 버튼 UI 제공
- `list_patches` 서버 API 추가
- project_root 저장 옵션 추가
- 여러 프로젝트 프로필 지원
- Chrome storage 기반 설정 화면
- source block hash를 사용자가 쉽게 확인하는 UX
- Gemini UI DOM 변화에 대한 추가 실측 테스트

## 결론

APOS의 bridge/browser-local integration layer는 웹 LLM을 로컬 프로젝트에 연결하는 자동화 도구가 아니라, 신뢰할 수 없는 웹 출력을 검증 가능한 로컬 패치 제안으로 바꾸는 안전 계층이다.

현재 구현은 다음 최소 제품 기준을 만족한다.

```text
패치 제안 감지
-> 로컬 검증
-> 보호 영역 차단
-> pending 저장
-> 인간 승인 커밋
-> 로컬 파일 반영
```

이제 이 문서를 Gemini에게 보여주면, Gemini는 서비스 목적, 안전 모델, 현재 구현 상태, 다음 개선 방향을 한 번에 이해할 수 있다.
