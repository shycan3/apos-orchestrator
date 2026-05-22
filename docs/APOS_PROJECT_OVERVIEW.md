# APOS Project Overview

## 1. 문서 목적

이 문서는 APOS 프로젝트의 목적, 현재 상태, 핵심 구조, 안전 원칙, 한계, 앞으로의 개발 방향을 정리한 기준 문서다.

APOS는 단순한 코드 실행 도구가 아니다.

APOS는 웹 기반 LLM, 예를 들어 ChatGPT나 Gemini가 로컬 프로젝트를 직접 수정하거나 실행할 수 없다는 한계를 보완하기 위해 만든 **Web LLM ↔ Local Workspace 오케스트레이션 시스템**이다.

이 문서는 다음 목적을 가진다.

HTTP approve endpoint security:

The lightweight HTTP endpoint supports an optional simple token-based authentication. If the environment variable `APOS_APPROVE_TOKEN` is set when starting `server/approve_endpoint.py`, the endpoint requires requests to include the header `X-APOS-Approve-Token: <token>`. This provides basic protection for local or network-exposed approval endpoints. For production use, place the endpoint behind a secure proxy or add stronger authentication.

1. 처음 보는 사람이 APOS가 어떤 프로젝트인지 빠르게 이해할 수 있게 한다.
2. 개발자가 APOS의 핵심 철학과 안전 기준을 놓치지 않게 한다.
3. ChatGPT, Gemini, Codex, Claude Code 등 다른 AI에게 프로젝트 방향을 설명할 때 기준 문서로 사용한다.
4. 앞으로 구현할 Search & Replace, Context Pack, 브라우저 자동 감지, 자동 실행, 자동 루프 기능의 설계 기준으로 사용한다.

---

## 2. APOS 한 줄 정의

APOS는 웹 LLM이 생성한 구조화된 작업 지시 JSON을 로컬에서 검증하고 실행한 뒤, 그 결과를 다시 웹 LLM이 읽을 수 있는 JSON으로 반환하는 개인용 로컬 오케스트레이터다.

짧게 말하면:

```text
웹 LLM은 생각하고,
APOS는 로컬에서 안전하게 실행한다.
```

---

## 3. APOS가 아닌 것

APOS는 다음이 아니다.

```text
- Claude Code, Cursor, Codex의 완전한 대체재
- LLM API 호출 에이전트
- API key 기반 자동 모델 호출 시스템
- 무제한 로컬 권한을 웹 LLM에게 주는 도구
- 사용자 모르게 백그라운드에서 계속 실행되는 자동 에이전트
- 완전한 보안 샌드박스
```

APOS는 OpenAI API, Gemini API, Claude API를 직접 호출하지 않는다.

APOS는 웹 LLM이 출력한 작업 JSON을 로컬에서 검증하고 실행하는 시스템이다.

---

## 4. 왜 APOS를 만드는가

웹 ChatGPT나 Gemini는 강력한 추론 능력을 가지고 있지만, 기본적으로 사용자의 로컬 컴퓨터에 직접 접근할 수 없다.

웹 LLM은 다음을 직접 할 수 없다.

```text
- 로컬 폴더 읽기
- 파일 생성
- 파일 수정
- 파일 삭제
- 코드 실행
- 실행 결과 확인
- stdout/stderr 수집
- 실패 원인 기반 재수정
```

반면 Codex, Cursor, Claude Code 같은 로컬 개발 에이전트는 이런 작업을 이미 상당히 잘 수행한다.

따라서 APOS는 이들을 완전히 대체하려는 도구가 아니다.

APOS의 목적은 다르다.

APOS는 다음 상황을 위한 개인용 도구다.

```text
- 웹 ChatGPT/Gemini의 추론 스타일을 그대로 쓰고 싶다.
- LLM API 비용이나 API key 관리를 피하고 싶다.
- 웹 LLM이 만든 결과를 로컬에서 안전하게 실행하고 싶다.
- 모든 작업을 문서화하고 기록하면서 반복하고 싶다.
- 웹 LLM을 로컬 개발 파트너처럼 쓰고 싶다.
- 무제한 자동 권한 위임보다, 검증과 기록이 있는 자동화를 원한다.
```

즉 APOS는 웹 LLM에게 로컬 권한을 직접 주는 것이 아니라, 웹 LLM이 만든 작업 지시를 APOS가 안전하게 검증하고 대신 실행하게 만드는 시스템이다.

---

## 5. APOS가 해결하려는 문제

기존 웹 LLM 사용 방식은 다음과 같다.

```text
1. 사용자가 웹 LLM에게 코드 작성을 요청한다.
2. 웹 LLM이 코드를 출력한다.
3. 사용자가 코드를 복사한다.
4. 로컬 파일에 붙여넣는다.
5. 터미널에서 실행한다.
6. 오류가 나면 다시 복사해서 웹 LLM에게 붙여넣는다.
7. 웹 LLM이 수정안을 준다.
8. 다시 수동으로 반복한다.
```

이 방식은 다음 문제가 있다.

```text
- 반복 작업이 번거롭다.
- 파일 경로 실수가 자주 난다.
- 실행 결과를 매번 사람이 복사해야 한다.
- 웹 LLM이 현재 로컬 상태를 모른다.
- 이전 작업 맥락이 쉽게 끊긴다.
- 위험한 명령이나 경로를 사람이 직접 걸러야 한다.
- 긴 파일 수정 시 웹 LLM 출력이 길어지고 JSON이 깨지기 쉽다.
```

APOS는 이 과정을 다음과 같이 바꾸려 한다.

```text
1. 웹 LLM이 APOS task envelope JSON을 출력한다.
2. APOS가 JSON을 검증한다.
3. APOS가 안전 정책을 통과한 패치만 적용한다.
4. APOS가 허용된 명령만 실행한다.
5. APOS가 실행 결과를 result envelope JSON으로 반환한다.
6. 웹 LLM이 result envelope를 보고 다음 task envelope를 만든다.
```

---

## 6. 중요한 전제: APOS는 LLM API를 호출하지 않는다

APOS는 OpenAI API, Gemini API, Claude API 같은 LLM API를 직접 호출하지 않는다.

APOS는 API key를 요구하지 않는다.

APOS는 모델을 직접 실행하지 않는다.

APOS는 다음 구조를 따른다.

```text
웹 ChatGPT / 웹 Gemini
        ↓
APOS task envelope JSON
        ↓
로컬 APOS 실행기
        ↓
result envelope JSON
        ↓
웹 ChatGPT / 웹 Gemini
```

즉 APOS는 LLM이 아니라, 웹 LLM과 로컬 작업공간 사이를 연결하는 안전한 실행 계층이다.

---

## 7. APOS의 핵심 철학

APOS는 다음 원칙을 따른다.

---

### 7.1 웹 LLM에게 직접 권한을 주지 않는다

웹 LLM은 로컬 파일 시스템에 직접 접근하지 않는다.

웹 LLM은 오직 JSON 형태의 작업 지시만 만든다.

실제 파일 수정, 명령 실행, 기록 저장은 APOS가 담당한다.

---

### 7.2 모든 작업은 구조화된 형식으로 전달된다

웹 LLM은 자유 문장이 아니라 `task envelope` JSON을 출력해야 한다.

APOS는 실행 결과를 `result envelope` JSON으로 반환한다.

이 두 형식은 APOS의 핵심 계약이다.

```text
Task Envelope   = 웹 LLM → APOS
Result Envelope = APOS → 웹 LLM
```

---

### 7.3 실행 전 검증을 우선한다

APOS는 task envelope를 바로 실행하지 않는다.

먼저 검증한다.

```text
JSON 문법 검증
필수 필드 검증
패치 경로 검증
보호 경로 차단
명령 정책 검증
```

검증 실패 시 실행하지 않는다.

---

### 7.4 위험한 경로와 명령은 차단한다

APOS는 다음과 같은 경로를 기본 차단한다.

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

APOS는 다음과 같은 명령도 기본 차단한다.

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

---

### 7.5 결과는 항상 기록한다

APOS는 실행 결과를 사람이 읽을 수 있고, 웹 LLM도 다시 해석할 수 있는 형태로 남긴다.

기록 대상은 다음과 같다.

```text
task_id
status
exit_code
patch preview
patch applied 여부
command
stdout
stderr
policy blocked 여부
snapshot 정보
history DB 경로
```

---

## 8. APOS의 현재 MVP 상태

현재 APOS는 다음 기능을 갖춘 상태다.

```text
완료:
- task envelope JSON 검증
- validate-only 실행
- 패치 dry-run
- 안전 경로 정책
- 명령 실행 정책
- 로컬 파일 생성/수정
- 명령 실행
- stdout/stderr 수집
- result envelope 생성
- SQLite history 기록
- Git snapshot 기반 안전장치
- snapshot 조회
- 파일 단위 복구
- 웹 LLM용 task envelope prompt 문서
- result envelope guide 문서
```

현재 검증된 대표 흐름:

```text
Gemini가 task envelope JSON 출력
→ APOS validate-only 통과
→ APOS가 workspace/gemini_test.py 생성
→ APOS가 python workspace/gemini_test.py 실행
→ stdout 수집
→ result envelope 출력
→ Gemini가 result envelope를 보고 다음 수정 task envelope 생성
→ APOS가 파일을 다시 수정하고 실행
```

즉 APOS MVP는 이미 다음 루프를 성공했다.

```text
생성 → 실행 → 결과 반환 → 재수정 → 재실행
```

---

## 9. APOS의 타깃 사용자

APOS는 모든 개발자를 위한 범용 에이전트가 아니다.

APOS가 가장 유용한 사용자는 다음과 같다.

```text
- 웹 ChatGPT/Gemini를 주 작업 도구로 쓰는 사람
- Codex/Cursor/Claude Code보다 웹 LLM 인터페이스가 더 익숙한 사람
- LLM API key 없이 웹 LLM을 로컬 작업에 연결하고 싶은 사람
- 자동화는 원하지만 무제한 권한 위임은 싫은 사람
- 작업 기록, result envelope, 안전 정책을 명확히 남기고 싶은 사람
- 개인 프로젝트에서 반복적인 생성/실행/수정 루프를 줄이고 싶은 사람
```

APOS는 다음 사용자에게는 최적이 아닐 수 있다.

```text
- 이미 Claude Code, Cursor, Codex에 완전히 만족하는 개발자
- JSON, 터미널, Git 사용이 전혀 익숙하지 않은 사용자
- 완전 자동 무제한 로컬 에이전트를 기대하는 사용자
```

APOS의 핵심 포지션은 다음이다.

```text
웹 LLM을 계속 쓰고 싶은 사용자를 위한 개인용 로컬 실행 브리지
```

---

## 10. 핵심 구성요소

### 10.1 task envelope

웹 LLM이 APOS에게 전달하는 작업 지시 JSON이다.

예시:

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

---

### 10.2 result envelope

APOS가 실행 후 반환하는 결과 JSON이다.

예시:

```json
{
  "schema_version": "1.0",
  "task_id": "task-create-hello",
  "status": "success",
  "exit_code": 0,
  "patch_applied": true,
  "patch_blocked": false,
  "command": ["python", "workspace/hello.py"],
  "command_allowed": true,
  "policy_blocked": false,
  "stdout": "hello from APOS\n",
  "stderr": ""
}
```

웹 LLM은 이 result envelope를 보고 다음 행동을 결정한다.

---

### 10.3 PatchPolicy

패치 대상 경로가 안전한지 검사한다.

허용 경로 예시:

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

차단 예시:

```text
hello.py
.env
.git/config
.apos/history.sqlite3
private_key.pem
```

중요한 기준:

```text
Allowed demo target: workspace/hello.py
Blocked root target: root hello.py
```

루트의 `hello.py`는 기본 차단된다.

---

### 10.4 CommandPolicy

실행 명령이 안전한지 검사한다.

허용 예시:

```json
["python", "workspace/hello.py"]
["python", "-m", "pytest", "-q"]
["node", "workspace/example.js"]
```

차단 예시:

```text
rm -rf .
del /s /q *
curl http://example.com
powershell -EncodedCommand ...
python file.py && del important.txt
```

---

### 10.5 SnapshotManager

Git 기반 스냅샷을 만든다.

역할:

```text
작업 전 상태 저장
스냅샷 커밋 생성
변경 파일 조회
특정 파일만 이전 스냅샷으로 복구
```

주의:

```text
git reset --hard 기반 전체 롤백은 기본 워크플로우가 아니다.
APOS는 파일 단위 복구를 우선한다.
```

---

### 10.6 Recorder

SQLite history DB에 작업 결과를 기록한다.

기본 기록 위치 예시:

```text
.apos/history.sqlite3
```

Git에는 포함하지 않는다.

`.gitignore`에 포함되어야 한다.

```gitignore
.apos/history.sqlite3
*.sqlite3
examples/current_task.json
```

---

### 10.7 Orchestrator

APOS의 중앙 실행 흐름을 담당한다.

흐름:

```text
task envelope 수신
→ 검증
→ patch dry-run
→ snapshot 생성
→ patch 적용
→ command policy 검사
→ command 실행
→ result envelope 생성
→ recorder 저장
```

---

### 10.8 Context Pack

Context Pack은 웹 LLM에게 현재 로컬 프로젝트 상태를 안전하게 전달하기 위한 요약 정보다.

웹 LLM은 로컬 파일 시스템을 직접 볼 수 없으므로, 작업 품질을 높이려면 현재 워크스페이스 요약이 필요하다.

Context Pack은 다음 정보를 포함한다.

```text
- 프로젝트 루트
- 허용된 작업 경로
- 제외된 보호 경로
- 현재 주요 파일 목록
- 최근 task/result 요약
- 현재 안전 정책 요약
- 웹 LLM에게 줄 주의사항
```

Context Pack은 전체 프로젝트를 덤프하는 기능이 아니다.

Context Pack은 웹 LLM에게 보여줘도 되는 **작업 가능 지도**다.

중요한 원칙:

```text
PatchPolicy에서 차단되는 경로는 Context Pack에서도 제외한다.
```

따라서 다음 경로는 Context Pack 파일 목록에서 제외한다.

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

Context Pack에 포함할 기본 범위는 다음과 같다.

```text
workspace/
src/
app/
cli/
apos_core/
tests/
docs/
README.md
examples/
```

권장 제한:

```text
max_depth = 4
max_files = 120
max_file_preview_chars = 1200
max_total_chars = 12000
```

예상 명령:

```powershell
python cli/context_pack.py
python cli/context_pack.py --json
python cli/context_pack.py --max-files 80
```

Context Pack은 브라우저 확장보다 먼저 만들어도 유용하고, 나중에 브라우저 확장/자동 루프에도 그대로 재사용할 수 있다.

---

## 11. 현재 수동 사용 흐름

현재 안정적으로 검증된 수동 사용 방식은 다음과 같다.

---

### 11.1 웹 LLM에게 프롬프트 제공

웹 ChatGPT 또는 Gemini에 다음 문서를 붙여넣는다.

```text
docs/task_envelope_prompt.md
```

그리고 작업을 요청한다.

예:

```text
workspace/todo_app.py 파일을 만들고,
실행하면 간단한 TODO 목록 예시를 출력하게 해줘.
APOS task envelope JSON만 출력해.
```

---

### 11.2 task envelope 저장

웹 LLM이 출력한 JSON을 다음 파일에 저장한다.

```text
examples/current_task.json
```

---

### 11.3 실행 전 검증

```powershell
.\.venv\Scripts\python.exe cli\run_task.py examples\current_task.json --validate-only --json
```

성공 예시:

```json
{
  "status": "success",
  "exit_code": 0,
  "validation_errors": []
}
```

---

### 11.4 실제 실행

```powershell
.\.venv\Scripts\python.exe cli\run_task.py examples\current_task.json --json
```

---

### 11.5 result envelope를 웹 LLM에게 전달

실행 결과 JSON을 웹 LLM에게 전달하고 다음 요청을 한다.

예:

```text
위 APOS result envelope를 분석해.
성공했다면 다음 개선 작업을 위한 APOS task envelope JSON만 출력해.
실패했다면 오류를 수정하는 APOS task envelope JSON만 출력해.
설명하지 말고 JSON 객체 하나만 출력해.
```

---

## 12. 현재 수동 방식의 한계

현재 방식은 안전하지만 번거롭다.

반복 과정:

```text
웹 LLM JSON 복사
→ current_task.json에 저장
→ 터미널에서 검증
→ 터미널에서 실행
→ result envelope 복사
→ 웹 LLM에 붙여넣기
```

이 과정은 APOS의 최종 목표인 “불편함 없이 사용”과는 아직 거리가 있다.

따라서 다음 단계는 두 갈래로 나뉜다.

```text
1. Search & Replace로 JSON 길이와 파싱 오류를 줄인다.
2. Context Pack으로 웹 LLM의 입력 품질을 개선한다.
3. 브라우저 확장으로 복사/붙여넣기 UX를 제거한다.
```

---

## 13. 다음 핵심 개발 목표 1: Search & Replace Patch Support

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

## 14. APOS Context Pack

Search & Replace와 함께 이미 구현한 핵심 기능이다.

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

## 15. 핵심 개발 목표 3: Plan Only Mode

복잡한 작업을 한 번에 실행하지 않고 단계별 계획으로 나누기 위한 기능이다.

현재는 `plan_only` task type의 기본 검증과 계획 요약 반환 경로를 구현했다.

또한 **Plan Step 실행용 CLI**(`cli/plan_step.py`)를 추가하여 `meta.plan_steps` 내부의 특정 단계만 선택적으로 실행할 수 있다. 이 CLI는 선택한 단계의 패치를 동기적으로 적용하고(패치 정책 준수), 첫 명령을 실행한 뒤 `result_envelope`를 기록한다.

간단 사용 예:

```bash
python cli/plan_step.py /path/to/plan.json --step 0 --json
```

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

추가 워크플로우 — 승인 기반 실행:

Plan Only Mode는 수동 혹은 반자동 승인 워크플로우를 지원하도록 확장할 수 있다. 두 가지 보조 도구를 제공합니다:

- `cli/plan_step.py`: 파일 기반 `plan_only` JSON에서 특정 단계를 즉시 실행(디버그용).
- `cli/plan_approve.py`: 이미 `workspace/.apos/history.sqlite3`에 기록된 `plan_only` 작업의 `task_id`를 조회하여 특정 단계를 승인·실행(감사 기록용).

일반 승인 흐름:

1. 웹 LLM 또는 자동화가 `plan_only` envelope를 생성하고 워크스페이스의 history DB에 기록한다.
2. 운영자가 계획을 검토한다(또는 자동 정책 검토).
3. 운영자가 `plan_approve`로 특정 단계(index)를 승인하면 APOS는 해당 단계를 동기적으로 실행하고 `result_envelope`를 기록한다.

예시 명령(승인 후 실행, JSON 출력):

```
python cli/plan_approve.py plan-123 --workspace /path/to/project --step 0 --approved-by alice --json
```

이 방식은 감사(audit)와 승인 이력을 남기기 좋으며, 자동 루프와 연동할 때 안전하게 단계별 진행을 제어하는 데 유용합니다.

---

## 16. 다음 핵심 개발 목표 4: Browser Auto Loop

앞으로 구현할 핵심 UX 기능은 브라우저 자동 감지 및 제한된 자동 루프다.

목표 흐름:

```text
Gemini/ChatGPT가 APOS task envelope JSON 출력
→ 브라우저 확장이 JSON 감지
→ 로컬 APOS 서버로 전송
→ APOS가 validate
→ 브라우저에 실행 여부 표시
→ 승인 또는 모드 설정에 따라 실행
→ result envelope를 브라우저에 표시
→ result envelope를 웹 LLM 입력창에 자동 삽입
→ 필요 시 자동 전송
→ 다음 task envelope 감지
→ 반복
```

---

## 17. 브라우저 확장 자동 감지의 현실성

브라우저 확장 자동 감지는 APOS의 핵심 UX이지만, 가장 깨지기 쉬운 부분이기도 하다.

ChatGPT와 Gemini의 DOM 구조는 언제든 변경될 수 있다.

따라서 APOS 확장은 특정 CSS selector나 DOM 계층에 강하게 의존하면 안 된다.

나쁜 접근:

```javascript
document.querySelector(".some-fixed-chat-response-class > div:nth-child(3)")
```

권장 접근:

```text
DOM 구조가 아니라 task envelope 스키마에 의존한다.
```

즉 확장은 다음 기준으로 APOS task를 감지한다.

```text
1. 페이지의 새 텍스트 변화를 감지한다.
2. JSON 후보를 추출한다.
3. JSON.parse를 시도한다.
4. APOS task envelope 필수 필드를 검사한다.
5. 통과한 JSON만 APOS task로 인정한다.
```

APOS task envelope로 인정하려면 최소한 다음 필드를 포함해야 한다.

```text
schema_version
task_id
task_type
created_by
workspace_root
patches
commands
options
meta
```

---

## 18. 브라우저 감지 세부 설계

### 18.1 MutationObserver + debounce

ChatGPT와 Gemini는 답변을 스트리밍한다.

따라서 MutationObserver만 사용하면 JSON이 완성되기 전에 중간 상태를 감지할 수 있다.

예:

```json
{
  "schema_version": "1.0",
  "task_id": "task-
```

이 상태에서 `JSON.parse`를 시도하면 실패한다.

따라서 APOS 확장은 DOM 변경이 생길 때마다 즉시 파싱하지 않고, debounce 기반 안정화 대기 시간을 둔다.

권장 방식:

```text
1. MutationObserver가 새 응답 텍스트 변화를 감지한다.
2. 마지막 변경 시각을 기록한다.
3. 텍스트 변화가 일정 시간 동안 멈추면 응답이 안정화된 것으로 본다.
4. 그때 JSON 후보 추출을 시도한다.
```

권장 기본값:

```text
response_stable_delay_ms = 1200
max_parse_retry = 3
```

즉 마지막 텍스트 변경 후 약 1.2초 동안 추가 변화가 없을 때만 task envelope 감지를 시도한다.

---

### 18.2 코드블록 JSON 추출

ChatGPT와 Gemini는 JSON을 순수 텍스트로 출력하지 않고 코드블록으로 감싸는 경우가 많다.

예:

````text
```json
{
  "schema_version": "1.0",
  "task_id": "task-example"
}
```
`````

따라서 APOS 확장은 JSON 파싱 전에 다음 전처리를 수행해야 한다.

````text
1. ```json ... ``` 코드블록이 있으면 내부 내용만 추출한다.
2. ``` ... ``` 코드블록도 JSON 후보로 처리한다.
3. 코드블록이 없으면 전체 텍스트에서 JSON 객체 후보를 찾는다.
4. 백틱, 언어 태그, 앞뒤 설명 문구를 제거한다.
5. JSON.parse를 시도한다.
6. 파싱 성공 후 APOS task envelope 필수 필드를 검사한다.
````

---

### 18.3 감지 파이프라인

브라우저 확장 v0.1의 감지 파이프라인은 다음과 같다.

```text
DOM mutation detected
→ debounce timer reset
→ response stable delay passed
→ visible response text collected
→ code block extraction
→ JSON candidate extraction
→ JSON.parse
→ task envelope schema check
→ duplicate task_id check
→ APOS panel 표시
```

중복 실행을 방지하기 위해 이미 감지한 `task_id`는 세션 내에서 기억한다.

```text
detected_task_ids = Set()
```

같은 `task_id`가 다시 감지되면 자동 실행하지 않고 무시하거나 “이미 감지됨”으로 표시한다.

---

## 19. 자동 감지 실패에 대한 fallback

자동 감지는 100% 신뢰할 수 없다.

따라서 APOS 확장은 fallback 경로를 제공해야 한다.

권장 fallback:

```text
1순위: 자동 감지
2순위: 사용자가 선택한 텍스트 감지
3순위: 클립보드에서 task envelope 읽기
4순위: 수동 JSON 파일 실행
```

즉 APOS의 목표는 “절대 깨지지 않는 브라우저 자동화”가 아니다.

APOS의 목표는 다음이다.

```text
웹 LLM 출력에서 task envelope를 최대한 편하게 감지하고,
실패 시 안전하게 수동 fallback으로 돌아갈 수 있는 개인용 자동화 계층
```

---

## 20. APOS 권한 모드 설계

Codex처럼 APOS도 자동화 수준을 모드로 나눈다.

APOS의 권한 모드는 웹 LLM에게 직접 권한을 주는 것이 아니라, APOS가 웹 LLM이 만든 task envelope를 어디까지 자동 처리할지 결정하는 설정이다.

---

### 20.1 Safe Mode

가장 안전한 기본 모드.

동작:

```text
자동 감지 O
자동 검증 O
자동 실행 X
실행 전 사용자 승인 O
result envelope 표시 O
자동 전송 X
```

사용자가 버튼을 눌러야 실행된다.

추천 기본값이다.

---

### 20.2 Auto Review Mode

정책상 안전한 작업은 자동 실행하는 모드.

동작:

```text
자동 감지 O
자동 검증 O
patch policy 통과 시 자동 실행 O
command policy 통과 시 자동 실행 O
result envelope 자동 삽입 O
자동 전송은 선택
위험 상태면 자동 중단
```

중단 조건:

```text
validation_failed
patch_blocked
command_blocked
snapshot_failed
internal_error
```

---

### 20.3 Auto Loop Mode

웹 LLM과 APOS가 반복 작업을 자동으로 이어가는 모드.

동작:

```text
자동 감지 O
자동 검증 O
자동 실행 O
result envelope 자동 삽입 O
자동 전송 O
다음 task envelope 자동 감지 O
반복 O
```

필수 제한:

```text
기본 OFF
사용자가 명시적으로 시작
최대 반복 횟수 제한
STOP 버튼 필수
차단 상태 발생 시 자동 중단
같은 실패 2회 반복 시 자동 중단
새로고침 시 자동 루프 OFF
```

권장 기본값:

```text
max_loop_count = 3
auto_submit = false by default
stop_on_blocked = true
stop_on_validation_failed = true
stop_on_command_blocked = true
```

---

## 21. Auto Loop에서 반드시 지켜야 할 안전 원칙

Auto Loop는 편리하지만 위험할 수 있다.

따라서 다음 원칙을 반드시 지킨다.

```text
1. PatchPolicy는 절대 자동으로 끄지 않는다.
2. CommandPolicy는 절대 자동으로 끄지 않는다.
3. 보호 경로 수정은 항상 차단한다.
4. 위험 명령은 항상 차단한다.
5. 자동 루프는 기본 OFF다.
6. 사용자가 명시적으로 시작해야 한다.
7. 최대 반복 횟수를 둔다.
8. STOP 버튼을 항상 노출한다.
9. 실패/차단 상태는 자동으로 웹 LLM에게 전달하되, 반복 제한을 둔다.
10. full auto mode에서도 완전 무제한 실행은 허용하지 않는다.
```

---

## 22. 브라우저 확장 단계별 목표

### 22.1 Browser Extension v0.1: Safe Mode

```text
1. ChatGPT/Gemini 페이지에서 APOS task envelope JSON 감지
2. 감지된 task_id, target, command 요약 표시
3. 코드블록 JSON 추출
4. 스트리밍 안정화 debounce
5. 중복 task_id 방지
6. [Validate] 버튼 제공
7. [Run] 버튼 제공
8. result envelope 표시
9. [Copy Result] 버튼 제공
10. [Insert Result Into Chat] 버튼 제공
```

v0.1에서는 자동 전송까지는 필수가 아니다.

---

### 22.2 Browser Extension v0.2: Assisted Mode

```text
1. Auto Review Mode 추가
2. 안전 정책 통과 시 자동 실행
3. result envelope 입력창 자동 삽입
4. 사용자가 Enter 또는 Send 버튼으로 전송
5. 실패/차단 시 자동 중단
```

---

### 22.3 Browser Extension v0.3: Auto Loop Mode

```text
1. Auto Loop Mode 추가
2. 최대 반복 횟수 설정
3. 자동 전송 옵션
4. STOP 버튼
5. 반복 로그 표시
6. 같은 실패 반복 감지
7. 탭 새로고침 시 루프 자동 OFF
```

---

### 22.4 In-chat Overlay

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

---

## 23. 보안 모델의 한계

APOS는 안전 정책을 제공하지만, 완전한 샌드박스는 아니다.

특히 중요한 한계는 다음과 같다.

---

### 23.1 실행되는 코드 내부 행위는 완전히 막을 수 없다

CommandPolicy는 명령 자체를 검사한다.

예를 들어 다음 명령은 차단할 수 있다.

```text
rm -rf .
python file.py && del important.txt
```

하지만 Python 파일 내부에 다음과 같은 코드가 들어 있으면, 단순 CommandPolicy만으로는 완전히 탐지하기 어렵다.

```python
import os
os.system("rm -rf .")
```

즉 APOS는 현재 “명령 실행 정책”은 제공하지만, “실행되는 코드의 모든 내부 행위 분석”까지 보장하지 않는다.

따라서 Auto Loop Mode에서도 다음 원칙이 필요하다.

```text
- 보호 경로 차단
- 작업 전 snapshot
- 파일 단위 복구
- 최대 반복 횟수 제한
- 위험 작업에서 사용자 승인 요구
```

장기적으로는 컨테이너 또는 제한된 실행 환경이 필요할 수 있다.

---

### 23.2 브라우저 확장은 보안 계층이 아니다

브라우저 확장은 task envelope를 감지하고 전달하는 UX 계층이다.

최종 검증은 반드시 로컬 APOS 서버에서 수행해야 한다.

```text
브라우저 확장:
감지, 표시, 전달

로컬 APOS:
검증, 정책 판단, 실행, 기록
```

---

### 23.3 Context Pack도 안전 필터를 반드시 적용해야 한다

Context Pack은 웹 LLM에게 프로젝트 정보를 제공하는 기능이지만, 전체 파일 시스템을 그대로 보여주면 안 된다.

다음 정보는 Context Pack에 포함하지 않는다.

```text
- 보호 경로
- history DB
- 환경 변수 파일
- 비밀키 파일
- 대형 의존성 폴더
- 빌드 산출물
```

Context Pack은 PatchPolicy의 차단 경로를 상속해야 한다.

---

## 24. APOS가 하지 않는 것

APOS는 다음을 하지 않는다.

```text
- LLM API 직접 호출
- API key 관리
- OpenAI/Gemini/Claude SDK 기반 자동 호출
- 웹 LLM에게 로컬 파일 시스템 직접 권한 부여
- 보호 경로 무제한 수정
- 무제한 자동 실행
- 사용자 모르게 백그라운드 작업 수행
- 프로젝트 전체 파일 내용을 무제한으로 웹 LLM에게 전달
```

APOS는 항상 로컬 정책과 기록을 중심으로 동작한다.

---

## 25. APOS의 최종 목표

APOS의 최종 목표는 사용자가 웹 LLM을 로컬 개발 파트너처럼 사용할 수 있게 하는 것이다.

최종 경험은 다음에 가깝다.

```text
사용자가 웹 Gemini/ChatGPT에게 작업을 요청한다.
웹 LLM이 APOS task envelope를 출력한다.
APOS가 자동으로 감지한다.
APOS가 안전하게 검증하고 실행한다.
APOS가 결과를 웹 LLM에게 돌려준다.
웹 LLM이 다음 작업을 제안한다.
사용자는 필요한 순간에만 승인하거나 중단한다.
```

즉 APOS는 다음을 목표로 한다.

```text
웹 LLM의 추론 능력
+
로컬 실행 능력
+
Search & Replace 기반 짧은 패치
+
Context Pack 기반 현재 상태 전달
+
정확한 문서화
+
안전한 권한 제어
+
반복 가능한 작업 기록
```

---

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
```

---

## 27. 개발자가 기억해야 할 핵심 문장

APOS는 웹 LLM에게 로컬 권한을 주는 시스템이 아니다.

APOS는 웹 LLM이 만든 작업 지시를 로컬에서 안전하게 검증하고 실행하는 시스템이다.

APOS는 LLM API를 호출하지 않는다.

APOS의 핵심 계약은 다음 두 가지다.

```text
Task Envelope: Web LLM -> APOS
Result Envelope: APOS -> Web LLM
```

APOS의 핵심 안전장치는 다음 세 가지다.

```text
PatchPolicy
CommandPolicy
SnapshotManager
```

APOS의 다음 품질 개선 장치는 다음 두 가지다.

```text
Search & Replace Patch Support (implemented)
Context Pack
```

APOS의 다음 UX 목표는 다음이다.

```text
브라우저 확장 기반 자동 감지와 제한된 자동 루프
```

