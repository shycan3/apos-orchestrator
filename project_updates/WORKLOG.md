# APOS 작업 저널

최종 업데이트: 2026-05-29

## 목적
- 이 폴더는 APOS 오케스트레이터의 작업 이력과 다음 계획을 추적하기 위한 기록 공간이다.
- 새로운 기여자가 봐도 지금까지 한 일과 앞으로 할 일을 바로 파악할 수 있도록 유지한다.

## 오늘 완료한 작업

### 21) Recovery Prompt Loop 추가
- `apos_core/recovery_prompt_builder.py`를 추가해 failure / latest / drift / plan-step failure 입력을 바탕으로 웹 LLM에 다시 붙여넣을 recovery prompt Markdown을 생성하도록 정리
- `apos_core/prompt_builder.py`에 `render_recovery_markdown()`을 추가해 patch/plan/review 공통 규칙과 안전 문구를 재사용하도록 연결
- `cli/apos.py recover prompt --failure|--latest|--drift|--plan-step` 경로와 `--mode`, `--output`, `--copy` 옵션을 추가
- `server/list_approvals_endpoint.py`와 `server/approvals_ui.html`에 recommended recovery prompt 요약을 최소 표시로 노출
- `tests/test_recovery_prompt.py`를 추가해 latest failure, specific failure id, drift, plan-step failure, mode recommendation, output 저장, copy 실패 fallback, secret-like 값 비노출, dashboard summary 노출을 검증
- `examples/recovery_prompt_demo.md`를 추가해 recovery prompt 사용 흐름을 바로 따라 할 수 있게 정리
- `server/apos_server.py`의 deprecated `websockets.server.WebSocketServerProtocol` import와 top-level `websockets` import를 `websockets.asyncio.server.ServerConnection` 및 `serve`로 교체해 warning 원인을 제거
- bridge/approval 관련 테스트와 전체 pytest를 다시 실행해 `81 passed`를 확인했고, websockets deprecation warning 2개는 더 이상 발생하지 않음

### 22) Dependency 안정화 / Experimental Web Controller 문서 정리
- 현재 설치된 `websockets` 16.0과 `websockets.asyncio.server.ServerConnection` / `serve` 기준을 README와 제한 문서에 짧게 명시
- `docs/WEB_CONTROLLER_EXPERIMENT.md`를 추가해 외부 브라우저 / Web Controller 아이디어를 실제 구현과 분리한 experimental 설계 메모로 정리
- `docs/KNOWN_LIMITATIONS.md`와 `docs/APOS_PROJECT_OVERVIEW.md`에서 Web Controller를 구현되지 않은 future work로 다시 연결
- 변경 후 bridge 관련 테스트와 전체 pytest를 다시 실행해 `81 passed`를 확인

### 23) APOS v0.1 Release Snapshot 정리
- `RELEASE_NOTES_v0.1.md`를 추가해 APOS 한 줄 정의, 핵심 사용자 흐름, 주요 기능, 보안 경계, Known Limitations 요약, Web Controller experimental 상태, 전체 pytest 결과를 릴리즈 노트로 고정
- README.md의 Known Limitations 섹션에 v0.1 릴리즈 노트 링크를 추가해 태그 전 기준 문서를 바로 찾을 수 있게 정리
- 실제 사용 명령을 빠르게 재확인한 결과 `python server/list_approvals_endpoint.py`, `python server/apos_server.py`, `python cli/apos.py prompt build ...`, `python cli/apos.py report failures ...`, `python cli/apos.py recover prompt ...`, `python cli/apos.py plans list ...` 흐름은 현재 문서와 일치함을 확인
- 릴리즈 스냅샷 추가 후 전체 pytest를 다시 실행해 `81 passed`를 확인하고 추가 warning이 없음을 재확인

### 24) v0.1 Usability Review 정리
- `docs/USAGE.md`의 plan_only 기록 예제를 Windows에서 바로 실행 가능한 PowerShell 형식으로 교체
- `USABILITY_REVIEW_v0.1.md`를 추가해 context build → prompt build → Bridge/plan example → dashboard → approve/reject/run → failure report/recovery prompt 흐름을 기준으로 사용성 점검 결과를 정리
- 확인된 유일한 사용성 문제는 POSIX heredoc 예제였고, 나머지 CLI / dashboard / report / recovery 흐름은 구현과 일치함을 기록
- 문서 수정 후 전체 pytest를 다시 실행해 기존 `81 passed` 상태를 유지하는지 확인

### 25) Dashboard Recovery UX 개선
- failed item 카드와 approval detail에 failure summary, likely cause, affected files, stdout/stderr/exit_code, recommended human action, recovery prompt textarea/copy action을 노출하도록 대시보드 API와 HTML을 보강
- `/api/approvals?id=...`와 `/api/dashboard`가 failure_detail 및 recovery_prompt payload를 내려주도록 재사용 코어를 연결
- `docs/UI_OVERVIEW.md`, `docs/SERVICE_OVERVIEW.md`, `README.md`에 Dashboard Recovery UX를 짧게 반영
- `tests/test_dashboard_ui.py`를 보강해 failed summary, recovery prompt payload, HTML copy UI 노출을 검증

### 26) v0.2 Candidate Usability Review 정리
- `USABILITY_REVIEW_v0.2_candidate.md`를 추가해 dashboard home, drift banner, failed item card, approval detail recovery prompt textarea, copy fallback, recovery prompt handoff, approve/reject/run separation을 기준으로 사용성 점검 결과를 기록
- 현재 Dashboard Recovery UX는 자동화 없이도 복구 경로를 읽을 수 있는 상태로 판단했고, release verdict를 `releaseable`로 정리
- 추가 수정 없이 전체 pytest를 다시 실행해 `81 passed`와 warning 없음 상태를 재확인

### 27) APOS v0.2 Release Snapshot 정리
- `RELEASE_NOTES_v0.2.md`를 추가해 Recovery-aware Dashboard release snapshot으로 v0.1 대비 변화, Dashboard Recovery UX, security boundary, Web Controller experimental status, usability review verdict, 테스트 결과를 요약
- README.md에 v0.2 release snapshot 링크를 추가해 v0.1과 v0.2 스냅샷을 나란히 찾을 수 있게 정리
- `docs/KNOWN_LIMITATIONS.md`에 failed item card와 detail panel의 recovery prompt 위치 차이를 짧게 기록해 후속 UX 후보를 남김
- 릴리즈 스냅샷 추가 후 전체 pytest를 다시 실행해 `81 passed`와 warning 없음 상태를 유지하는지 확인

### 28) v0.2.1 Dashboard Recovery UX polish
- failed item card에 recovery prompt 전체 본문은 detail panel에서 확인/복사할 수 있다는 짧은 안내 문구를 추가해 위치 혼동을 줄임
- approval detail의 recovery prompt textarea/copy 안내 문구를 조금 더 명확하게 다듬고, 관련 문서를 같은 표현으로 보정
- `tests/test_dashboard_ui.py`에 failed item card 안내 문구가 HTML에 포함되는지 확인하는 작은 assertion을 추가
- 전체 pytest를 다시 실행해 `81 passed`와 warning 없음 상태를 재확인

### 29) APOS v0.2.1 Release Snapshot 정리
- `RELEASE_NOTES_v0.2.1.md`를 추가해 v0.2.1을 small UX polish release로 고정하고, v0.2 대비 변경점 / 변경 없음 / verification 결과를 정리
- README.md에 v0.2.1 release snapshot 링크를 추가해 v0.1, v0.2, v0.2.1 스냅샷을 한 번에 찾을 수 있게 정리
- `docs/KNOWN_LIMITATIONS.md`에서 recovery prompt location ambiguity가 v0.2.1에서 해소되었다는 표현으로 정리
- 전체 pytest를 다시 실행해 `81 passed`와 warning 없음 상태를 유지하는지 확인 예정

### 30) APOS v0.3 Semi-auto Recovery 설계 시작
- `docs/SEMI_AUTO_RECOVERY.md`를 추가해 current Recovery Prompt Loop, 허용/금지 자동화, 안전 경계, CLI/Dashboard 후보, 실패 모드별 추천 흐름, v0.3 최소 범위, 후속 버전 이월 항목을 정리
- README.md에 v0.3 semi-auto recovery design memo 링크를 추가해 future design note를 빠르게 찾을 수 있게 정리
- `docs/KNOWN_LIMITATIONS.md`에 semi-auto recovery는 prompt-preparation automation only라는 점을 명시해 auto-send / auto-approve / auto-execute 금지를 유지
- 전체 pytest를 다시 실행해 `81 passed`와 warning 없음 상태를 확인할 예정

### 31) APOS v0.3 Semi-auto Recovery 최소 구현
- `RecoveryPromptBuilder`에 `--mode auto` 선택 경로를 추가해 failure cause를 기준으로 patch / plan / review 중 하나를 추천하고, 기존 `PromptBuilder`의 required-output 규칙을 재사용하도록 정리
- `cli/apos.py recover prompt`에서 `--mode auto`를 허용하고, latest / drift / failure 경로가 자동 추천 모드에서도 유지되도록 연결
- `server/approvals_ui.html`의 failed item 카드와 recovery detail에 `Build LLM Retry Prompt`, `Copy Recovery Prompt`, `This does not auto-run or auto-approve.` 문구를 추가해 실행 오해를 줄임
- `docs/USAGE.md`, `docs/SERVICE_OVERVIEW.md`, `docs/PROTOCOL.md`, `docs/SECURITY_MODEL.md`, `docs/SEMI_AUTO_RECOVERY.md`, `docs/KNOWN_LIMITATIONS.md`를 auto recommendation / prompt preparation only 경계에 맞게 보정
- `tests/test_recovery_prompt.py`, `tests/test_prompt_builder.py`, `tests/test_dashboard_ui.py`에 auto 추천 규칙, mode별 Required LLM Output, dashboard 문구 검증을 추가
- 전체 pytest를 다시 실행해 기존 81 passed 흐름이 유지되는지 확인 예정

### 32) APOS v0.3 Candidate Usability Review 정리
- `USABILITY_REVIEW_v0.3_candidate.md`를 추가해 `recover prompt --mode auto` 흐름, failure cause별 mode 추천, dashboard wording, recovery prompt 출력 계약, CLI/문서 일치성을 점검
- `docs/SEMI_AUTO_RECOVERY.md`와 dashboard label / copy 문구는 이미 prompt-preparation only 경계가 명확해 추가 기능 수정 없이도 releasable verdict를 낼 수 있다고 정리
- 전체 pytest를 다시 실행해 `85 passed`와 warning 없음 상태를 재확인 예정

### 33) APOS v0.3 Release Snapshot 정리
- `RELEASE_NOTES_v0.3.md`를 추가해 Semi-auto Recovery release snapshot으로 v0.3 요약, scope, safety boundary, CLI / dashboard 변화, validation 결과, minor note, release decision을 고정
- README.md에 v0.3 release snapshot 링크를 추가해 v0.3 설계 메모와 릴리즈 스냅샷을 함께 찾을 수 있게 정리
- 작업 기록은 릴리즈 스냅샷 문서화만 수행했고, 기능 변경은 추가하지 않음
- 전체 pytest를 다시 실행해 `85 passed`와 warning 없음 상태를 유지하는지 확인 예정

### 20) APOS v0.1 안정화 릴리즈 정리
- README.md의 Quick Start를 현재 구현된 주요 흐름 기준으로 다시 정리하고 Known Limitations 링크를 추가
- `docs/KNOWN_LIMITATIONS.md`를 새로 만들어 직접 자동 전송, 외부 브라우저 자동화, 자동 루프 부재, 수동 승인 확인 필요, DOM 변화 가능성을 명시
- `docs/USAGE.md`에 서버 실행 → Context Pack → Prompt Builder → 웹 LLM 응답 수집 → Approval Queue → Plan Step → Dashboard → Failure / Drift Report 순서를 명시
- `docs/SERVICE_OVERVIEW.md`, `docs/PROTOCOL.md`, `docs/SECURITY_MODEL.md`에서 envelope / approval / plan / report 용어와 안전 경계를 현재 구현 기준으로 정리
- `examples/README_APPROVE.md`를 Windows PowerShell 기준으로 다시 써서 실제 명령과 예제 경로를 맞춤
- `docs/APOS_PROJECT_OVERVIEW.md`에 v0.1 안정화 범위와 현재 한계 문서를 기준점으로 삼는다고 명시
- `examples/failure_report_demo.md`를 추가해 `report failures|failure|drift|next-prompt`의 읽기 전용 사용 흐름을 바로 따라 할 수 있게 정리
- 전체 pytest를 다시 실행해 `75 passed`를 확인했고, 남은 2개 warning은 `websockets.server.WebSocketServerProtocol` 및 `websockets.legacy` deprecation 경고로 분류함

### 19) Failure / Drift Report 추가
- `apos_core/report_builder.py`를 추가해 실패 결과, 승인 거부, 드리프트 신호를 모아 failure report / drift report / next prompt를 생성하도록 정리
- `cli/apos.py report failures|failure|drift|next-prompt` 서브커맨드를 추가해 JSON/markdown 보고서와 다음 프롬프트를 출력할 수 있게 연결
- `server/list_approvals_endpoint.py`의 `/api/dashboard` payload에 `failed_items_summary`, `drift_warning`, `drift_signals`, `drift_summary`를 추가
- `server/approvals_ui.html`에 drift warning 배너와 recent failed items 카드를 추가해 로컬 대시보드에서 바로 확인 가능하게 정리
- `tests/test_failure_report.py`를 추가해 failure cause 분류, markdown 렌더링, drift signal, dashboard payload 노출, CLI report 출력을 검증
- `apos_core/__init__.py`에 `report_builder` export를 추가하고, `tests/test_failure_report.py` 기준으로 focused pytest 4개를 통과시킴

### 17) Prompt Builder 추가
- `apos_core/prompt_builder.py`를 추가해 현재 Context Pack, 사용자 목표, APOS 출력 규칙을 합친 paste-ready markdown 프롬프트를 생성하도록 정리
- `cli/apos.py prompt build --goal ... --mode patch|plan|review` 서브커맨드를 추가하고 `--output`, `--copy` 옵션을 지원하도록 연결
- patch/plan/review 모드별 required output format과 safety constraints를 프롬프트 본문에 명시
- `tests/test_prompt_builder.py`를 추가해 기본 생성, patch/plan/review 출력, goal 누락 에러, Context Pack 포함, secret-like 값 마스킹, output 파일 저장을 검증
- README.md, docs/USAGE.md, docs/SERVICE_OVERVIEW.md, docs/PROTOCOL.md, docs/SECURITY_MODEL.md에 prompt builder 사용법과 안전 규칙을 반영
- 전체 테스트 통과 결과를 `70 passed`로 다시 확인함

### 18) Prompt Template Hardening
- `apos_core/prompt_builder.py`의 patch 템플릿에 정확히 하나의 `apos-patch` 블록, diff 금지, 다중 파일 시 plan 권장, 불확실 시 review/plan 전환 규칙을 추가
- plan 템플릿에 step별 목적, 대상 파일, 위험도, 실행 조건, 중단 조건, 상태 흐름 용어를 더 명시적으로 반영
- review 템플릿에 파일 수정 JSON 금지, 추정/가정 표시, 재사용 가능한 다음 prompt 제안 규칙을 추가
- `tests/test_prompt_builder.py`를 확장해 강화된 고정 문구와 공통 안전 규칙 포함 여부를 검증
- USAGE.md, PROTOCOL.md, SECURITY_MODEL.md, examples/prompt_builder_demo.md를 템플릿 강화 문구에 맞게 갱신
- 전체 pytest는 다시 실행 후 `70 passed` 유지 확인 예정

## 다음 작업 예정
- v0.3 설계 문서를 바탕으로 실제 구현이 아니라 문구 정리만 더 필요한지 확인하기
- websockets 의존성은 현재 경고 없이 동작하지만, 추후 업그레이드 시 `websockets.asyncio` API 변화를 다시 확인하기

### 16) 최소 조회 UI / 로컬 대시보드 추가
- `server/list_approvals_endpoint.py`를 확장해 `GET /`, `GET /ui`, `GET /ui/approvals`, `GET /ui/plans` 대시보드와 `GET /api/dashboard`, `GET /api/approvals`, `GET /api/plans` JSON 조회를 제공
- `POST /api/approvals/approve`, `POST /api/approvals/reject`, `POST /api/plans/approve-step`, `POST /api/plans/reject-step`, `POST /api/plans/run-step`를 추가해 UI에서도 기존 정책 경로를 그대로 사용
- `server/approvals_ui.html`을 APOS Dashboard로 교체해 pending count, failed count, recent executed items, recent plans, approvals, plan detail을 한 화면에서 확인 가능하게 정리
- `tests/test_dashboard_ui.py`를 추가해 UI route, approvals list, plan detail, approve/reject/run, invalid id, latest result 노출을 검증
- `docs/UI_OVERVIEW.md`와 `examples/ui_demo.md`를 추가해 브라우저 대시보드 사용 흐름을 문서화
- 전체 테스트 통과 결과를 `67 passed`로 갱신

### 15) apos plans 문서와 예시 정리
- `docs/USAGE.md`에 `apos plans list|show|steps|approve-step|reject-step|run-step` 표준 흐름을 추가하고 rerun 정책과 결과 상태를 정리
- `README.md`에 핵심 plan step 흐름만 짧게 추가하고 `tests/test_plan_management.py`와 `examples/plan_step_demo.md`를 연결
- `docs/SERVICE_OVERVIEW.md`에 plan step 기능의 서비스 내 위치와 실행 흐름을 설명
- `docs/PROTOCOL.md`에 plan step 상태 전이와 승인/실행 protocol을 추가
- `docs/APOS_PROJECT_OVERVIEW.md`의 Plan Only Mode 상태 설명을 `apos plans` 중심으로 갱신
- `examples/plan_step_demo.md`를 추가해 사용자가 그대로 따라 할 수 있는 튜토리얼을 제공

### 14) Plan Step 관리 흐름 고도화
- `apos_core/plan_flow.py`를 추가해 plan_only task의 `pending / approved / rejected / running / executed / failed / skipped` 상태 전이를 중앙화
- `apos_core/recorder.py`에 task list/latest result 조회를 추가하고 plan detail과 step result 조회가 가능하도록 정리
- `apos_core/orchestrator.py`에서 plan 조회, 승인, 거절, 실행을 `PlanStepManager`로 위임하도록 연결
- `cli/apos.py`에 `plans list|show|steps|approve-step|reject-step|run-step` 하위 명령을 추가
- `cli/plan_step.py`, `cli/plan_approve.py`, `server/approve_endpoint.py`를 새 step 승인 후 실행 흐름에 맞게 정리
- `tests/test_plan_management.py`를 추가해 list/show/steps, 승인/거절, 성공 실행, 실패 실행, rerun 정책, invalid id 처리를 검증
- 전체 테스트 통과 결과를 `66 passed`로 갱신

### 13) Context Pack 정식화
- `apos_core/context_pack.py`를 표준 JSON 구조로 재정의하고 Markdown 렌더링을 추가
- `project_name`, `project_root`, `generated_at`, `allowed_roots`, `protected_roots`, `recent_worklog_summary`, `available_flows`, `approval_queue_summary`, `recent_history_summary`, `relevant_files`, `file_summaries`, `known_warnings`, `next_recommended_actions`를 포함하도록 정리
- secret-like 문자열 마스킹, `.env`/보호 경로 제외, 대용량 파일 metadata-only 처리 정책을 추가
- `cli/apos.py context build|inspect`와 `cli/context_pack.py`의 build/inspect/markdown/output 흐름을 추가
- `tests/test_context_pack.py`를 스키마, 마스킹, large-file 처리, CLI 출력 검증으로 교체
- Context Pack 문서와 paste-ready 예시를 추가
- 전체 테스트 통과 결과를 `64 passed`로 갱신

### 12) Browser Bridge 안정화
- `extension/bridgeUtils.js`를 추가해 언어 판별, assistant/model 스코프 판별, payload 검증, bounded cleanup을 공용화
- `extension/contentScript.js`를 assistant-only 감지, `patch_id + sha256` 중복 억제, bounded retry/queue 정책으로 교체
- `extension/manifest.json`에 bridge util 로드를 추가해 content script와 테스트가 같은 로직을 공유하도록 정리
- `tests/bridge_extension_runtime_test.js`와 `tests/test_bridge_extension_runtime.py`를 추가해 apos-patch 감지, assistant-only 필터, non-apos 무시, retry limit, cleanup 정책을 검증
- Bridge Flow 문서를 assistant/model 범위와 bounded retry 정책 기준으로 갱신

### 11) Pending Patch / Approval Queue 관리 정리
- Recorder에 `approval_items` 큐 테이블을 추가하고 `pending/approved/rejected/executed/failed` 상태를 저장하도록 정리
- `server/approve_endpoint.py`, `server/list_approvals_endpoint.py`를 queue item list/show/approve/reject 흐름으로 확장
- `server/apos_server.py`가 bridge patch proposal을 approval queue에 기록하고 commit/reject 상태를 DB에 반영하도록 연결
- `cli/approvals.py`를 추가해 list/show/approve/reject 큐 관리 명령을 제공
- `tests/test_approval_queue_management.py`와 기존 demo test를 보강해 pending 목록, 단건 조회, 승인, 거절, 중복 처리, 실패 상태를 검증
- 전체 테스트 통과 결과를 `63 passed`로 갱신

### 10) 대표 사용 흐름 안정화
- README.md, docs/USAGE.md, docs/SERVICE_OVERVIEW.md의 표준 사용 흐름을 validate-only / preview_patch / apos-patch Bridge Flow로 통일
- 처음 사용하는 사람이 따라 할 수 있는 Quick Start와 대표 예제 3개를 추가
- examples/validate_only_demo.json, examples/preview_patch_demo.json, examples/apos_patch_demo.md를 추가
- validate-only, preview_patch, apos-patch propose/commit round trip을 검증하는 테스트 추가

### 1) Plan Only Mode 기본 지원 구현
- `task_type: "plan_only"`를 task envelope 검증과 CLI validate-only 경로에 추가
- `meta.plan_steps` 기반의 단계형 계획 스키마 초안 검증 추가
- `Orchestrator.run_task_envelope()`에 plan-only 분기를 넣어 실행 없이 계획 요약만 반환하도록 정리
- README, `docs/task_envelope_prompt.md`, `docs/APOS_PROJECT_OVERVIEW.md`에 Plan Only Mode 상태 반영
- Plan Only Mode 전용 테스트로 검증과 결과 반환 흐름을 확인

### 추가: Plan Step CLI 구현
- `cli/plan_step.py` 추가: `plan_only`의 특정 단계만 실행하는 명령행 도구 구현
- 단계의 패치 적용(동기) 및 첫 명령 실행 후 `result_envelope` 기록
- 관련 테스트 `tests/test_plan_step_cli.py` 추가 및 전체 테스트 통과 확인

### 2) Search & Replace 패치 지원 구현
- `Executor.preview_patch()`와 `Executor.apply_patch()`에 `search_and_replace` intent 추가
- 검색 문자열이 정확히 1회 매칭될 때만 파일을 수정하도록 적용
- 0회/다중 매칭/빈 검색어/대상 파일 없음/정책 차단 시 실제 파일 변경을 막도록 정리
- task envelope 검증과 validate-only 경로에 `search_and_replace` 허용 규칙 추가
- README, `docs/task_envelope_prompt.md`, `docs/APOS_PROJECT_OVERVIEW.md`에 구현 상태와 사용 예시 반영
- 신규 테스트로 preview, apply, 차단, validate-only 흐름을 덧붙임

### 3) Context Pack 구현
- 안전한 작업 요약을 생성하는 `apos_core/context_pack.py` 추가
- `cli/context_pack.py`로 JSON/텍스트 Context Pack 출력 가능하게 정리
- protected path 제외, allowed work root 수집, 최근 SQLite 결과 요약을 포함하도록 구현
- Context Pack 전용 테스트로 안전한 포함/제외와 CLI 출력 검증 추가

### 4) 워크스페이스 정리 확인
- `.vscode/` 폴더 필요 여부를 점검했지만 현재 워크스페이스에는 존재하지 않음을 확인
- README에 `.vscode/`는 APOS 운영에 필요하지 않다는 점과 현재 삭제 대상이 없었다는 사실을 기록

### 5) APOS v3.2 + Bridge Protocol 정렬
- CLI 기본 생성 구조를 Bridge Protocol 기준으로 확장하도록 정리
- `.apos/preference_layer.md`, `.apos/risk_vector.json`, `.codex/APOS_INSTRUCTIONS.md` 기본 생성 항목 추가
- `specifications/architecture.md`를 Human Notes + Machine Facts 분리 구조로 갱신
- `specifications/immutable_rules.md`, `specifications/glossary.md`, `context/project_history.md`, `workspace/active_code.py`, `workspace/active_draft.md` 기본 파일 추가

### 6) 문서 기준선 갱신
- `README.md`를 APOS v3.2 + Bridge Protocol 기준으로 설명 보강
- `docs/PROTOCOL.md`에 Layer 1/Layer 2, 역할 분리, human/machine separation 규칙 추가
- `docs/SECURITY_MODEL.md`에 Bridge Layer, risk queue, human/machine isolation 규칙 추가
- `docs/SERVICE_OVERVIEW.md`에 Bridge Layer 설명과 CLI 생성 구조 반영

### 7) 서버 보안/견고성 개선
- sha256 불일치 응답에서 상세 해시를 클라이언트 에러 메시지에 노출하지 않도록 변경
- patch_id 형식 제한 추가 (`^[A-Za-z0-9_-]{1,128}$`)
- 보호 영역 scratchpad 기록 시 마크다운 안전화 처리 추가
- 코드 펜스 언어 값 정규화/길이 제한 추가
- 코드 내용에 백틱이 있어도 안전하게 렌더링되도록 동적 fenced block 생성
- Python 검증 시 `.pyc` 임시 파일도 명시적으로 정리
- 커밋된 patch id 저장소에 만료 처리 추가
- 이벤트 루프 시간 참조를 running loop 기반으로 정리

### 8) 확장 기능 보완
- `window.__APOS_V32__.commit(patchId)` 함수 추가
- retry prompt에서 `project_root/target/language/patch_id` 하드코딩 제거
- metadata(또는 metadataText)에서 실제 기본값을 읽어 prompt 생성

### 9) 문서 보완
- 서버 재시작 시 pending patch 소멸 경고 추가
- DevTools 콘솔 커밋 예시 추가
- README 문서 트리에 SERVICE_OVERVIEW.md 누락 항목 반영

## 운영 규칙
- 코드 변경을 수행할 때마다 이 문서의 `오늘 완료한 작업`과 `다음 작업 예정`을 갱신한다.
- 계획이 바뀌면 이유를 함께 남긴다.
- 큰 변경은 관련 파일 경로를 함께 기록한다.

## GitHub 업로드 상태
- 현재 상태: 완료
- 저장소 URL: https://github.com/shycan3/apos-orchestrator
- 기본 브랜치: main
- 공개 여부: PUBLIC
- 완료 조건:
  - [x] 로컬 git 초기화
  - [x] 변경사항 커밋
  - [x] 원격 저장소 연결
  - [x] main 브랜치 push
