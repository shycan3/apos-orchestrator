# Implementation Summary (LLM-friendly)

이 문서는 최근 APOS 리포지터리에 적용된 변경사항과 구현 세부를 다른 LLM이나 개발자가 즉시 이해하고 재현할 수 있도록 기계-친화적으로 정리한 문서입니다.

## 핵심 변경 사항 (요약)

- `search_and_replace` 패치 인텐트 지원: `Executor` 내 preview/apply 로직 추가. 정확히 한 번 매치되어야 적용.
- `plan_only` 및 단계 실행: `Orchestrator.execute_plan_step(task_id, step_index, approved_by)` 구현 — 단계의 패치 적용 및 첫 명령을 동기적으로 실행.
- 승인 워크플로: `/approve` POST 엔드포인트 및 `cli/plan_approve.py` 구현.
- 승인 감사: `Recorder`에 `approvals` 테이블 추가 및 `record_approval()` 와 `get_approvals(..., approver, start_ts, end_ts, limit, offset)` 구현.
- 승인 조회: `cli/list_approvals.py` 및 `/approvals` GET 엔드포인트 추가 (ISO/epoch 파싱, 페이징(Link 헤더)).
- 간단 UI: `server/approvals_ui.html` — 정적 페이지를 통해 승인 목록 확인 가능.

## 파일 & 진입점 (빠른 참조)

- `apos_core/orchestrator.py` — Orchestrator 핵심 메서드: `execute_plan_step`, `list_approvals`, `approval_report`.
- `apos_core/executor.py` — 패치 적용 및 preview 로직 (search_and_replace 포함).
- `apos_core/recorder.py` — DB 스키마(approvals 포함) 및 `record_approval`, `get_approvals`.
- `server/approve_endpoint.py` — POST /approve 엔드포인트, 토큰/HMAC 인증.
- `server/list_approvals_endpoint.py` — GET /approvals 엔드포인트, ISO 파싱 및 페이징.
- `cli/plan_approve.py`, `cli/plan_step.py`, `cli/list_approvals.py` — CLI 도구들.
- `server/approvals_ui.html` — 간단한 정적 UI.

## 엔드포인트 스펙

### POST /approve
- 입력: JSON body
  - `task_id` (string, required)
  - `workspace` (string, required)
  - `step` (int, optional, default 0)
  - `approved_by` (string, optional)
- 인증 (선택): `APOS_APPROVE_TOKEN`이 설정된 경우 클라이언트는 다음 둘 중 하나를 제공해야 함
  - Header `X-APOS-Approve-Token: <token>` OR
  - `X-APOS-Timestamp` (epoch seconds) 및 `X-APOS-Signature` 헤더:
    - 서명: HMAC-SHA256(token, timestamp + '.' + raw_body)
    - 서버는 `abs(now - timestamp) <= SIGNATURE_WINDOW` (기본 300s)인지 확인함
- 응답: 200 OK + `result_envelope` JSON, 실패 시 4xx/5xx

Python 서명 예시:
```python
import time, hmac, hashlib, requests
token = 'shared-secret'
raw = b'{"task_id":"plan-1","workspace":"./workspace","step":0}'
ts = str(int(time.time()))
sig = hmac.new(token.encode(), ts.encode() + b'.' + raw, hashlib.sha256).hexdigest()
headers = {'X-APOS-Timestamp': ts, 'X-APOS-Signature': sig}
resp = requests.post('http://127.0.0.1:8081/approve', data=raw, headers=headers)
```

---

### GET /approvals
- Query params:
  - `task_id` (required)
  - `approver` (optional)
  - `start` / `end` (optional): epoch seconds OR ISO 8601 (e.g. `2026-05-22T12:00:00Z`)
  - `limit` / `offset` (optional)
  - `workspace` (optional)
- 응답: approval 객체 배열. `limit` 사용 시 `Link` 헤더에 next 페이지 링크 포함.

Approval object:
```json
{ "id": "...", "task_id": "...", "step_index": 0, "approved_by": "alice", "timestamp": 1680000000.0, "meta": {...} }
```

## Recorder DB 스키마 (요점)
- 위치: `workspace/.apos/history.sqlite3`
- 주요 테이블:
  - `tasks(id, created_at, payload)`
  - `results(...)` (여러 컬럼 포함, `result_envelope` JSON 포함)
  - `suggestions(id, task_id, timestamp, suggestion)`
  - `approvals(id, task_id, step_index, approved_by, timestamp, meta)`

중요: Windows에서 파일 락 이슈가 빈번하므로, 테스트/스크립트에서 `recorder.close()` 또는 `orch.stop()`을 호출해 DB 핸들을 닫아야 함.

## Orchestrator 주요 메서드 (시그니처 요약)
- `Orchestrator(workspace_root, history_db_path, ...)`
- `execute_plan_step(task_id: str, step_index: int, approved_by: Optional[str] = None) -> dict` — step 실행 후 `result_envelope` 반환
- `list_approvals(task_id: str) -> list` — recorder의 `get_approvals` 래퍼
- `approval_report(task_id: str, limit: int = 100) -> dict` — `{task_id, count, approvers, last}`

## CLI 요약
- `cli/plan_step.py` — 로컬 plan.json에서 특정 단계 실행
- `cli/plan_approve.py` — 기록된 plan의 단계 승인 및 실행 (`task_id` 필요)
- `cli/list_approvals.py TASK_ID --workspace . --approver alice --start 2026-05-22T00:00:00Z --limit 50 --pretty`

## 테스트
- 위치: `tests/` 디렉토리
- 실행: 가상환경 활성화 후 `python -m pytest -q`
- 최근 테스트 결과: 전체 테스트 통과 (56 passed)

## 운영 권고
- Production: 엔드포인트는 반드시 HTTPS 리버스 프록시 뒤에서 실행하고, `APOS_APPROVE_TOKEN`을 길고 안전한 비밀로 설정하세요.
- 서명 사용 시 클라이언트와 서버의 시간 동기화를 보장하세요 (NTP 추천).
- 토큰 로테이션 스케줄과 비밀 저장(예: 환경 변수 관리자 또는 Vault) 사용을 권장.

## 재현 가이드 (빠른 체크리스트)
1. 가상환경 활성화: `.\.venv\Scripts\Activate.ps1` (Windows PowerShell)
2. 모든 테스트 실행: `python -m pytest -q`
3. 로컬 approve 서버 시작: `python server/approve_endpoint.py` (개발용, 포트 8081)
4. approve 요청 전송: 위의 Python 예시 참고
5. approvals 조회: `curl 'http://127.0.0.1:8082/approvals?task_id=plan-123&limit=10' --header 'X-APOS-Approve-Token: <token>'`

---

추가로 이 문서를 기반으로 함수별 상세 시그니처 문서나 자동화된 API 스펙(OpenAPI 등)을 생성하길 원하면 이어서 생성해드리겠습니다.
