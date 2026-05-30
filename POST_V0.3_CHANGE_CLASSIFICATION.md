# Post v0.3 Change Classification

## 결과 요약

- 현재 테스트 상태: full pytest 85 passed
- 현재 working tree 요약: 34 tracked modifications, 다수의 untracked non-cache 파일, 일부 tracked .pyc가 D(삭제) 상태
- v0.3 본선 포함 후보 수: 8 (파일 기준, 아래 목록 참조)
- v0.4 runtime 후보 수: 11 (파일 기준, 아래 목록 참조)
- bridge/Web Controller 실험군 후보 수: 6 (파일 기준, 아래 목록 참조)
- 보류/검토 필요 항목 수: 20+ (문서·예시·테스트 일부 — 아래 섹션에 상세)

## v0.3 본선 포함 후보

이 그룹은 v0.3 Semi-auto Recovery의 핵심 기능(복구 프롬프트 준비 + 대시보드 문구/복구 UX)을 바로 설명하거나 구현하는 파일들입니다. 본선에 포함할 후보로 분류했습니다. (참고: 이 단계에서는 커밋/삭제/브랜치 생성하지 않습니다 — 단순 분류)

- `cli/apos.py` (tracked)
  - 변경 목적: `recover prompt` 서브커맨드와 `--mode auto` 플래그 관련 CLI 배선 및 사용자 노출
  - 포함 이유: 사용자-visible CLI 동작으로 v0.3의 핵심 사용자 흐름과 직접 연관됨
  - 위험도: medium

- `apos_core/prompt_builder.py` (untracked)
  - 변경 목적: recovery/prompt 템플릿과 출력 계약 제공 (PromptBuilder.required_output_lines 등)
  - 포함 이유: recovery prompt 출력 계약은 v0.3 안전 경계의 핵심; 문서화 및 검증에 필요
  - 위험도: low→medium (문서/계약 변경이므로 검토 필요)

- `apos_core/recovery_prompt_builder.py` (untracked)
  - 변경 목적: failure/drift/plan-step 기반 recovery prompt 생성 및 `--mode auto` 권장 로직
  - 포함 이유: `--mode auto` 동작을 구현/설명하는 핵심 모듈
  - 위험도: medium

- `server/list_approvals_endpoint.py` (tracked)
  - 변경 목적: Dashboard API에서 recovery payload와 `mode="auto"` 제공, 실패 항목 보강
  - 포함 이유: 대시보드가 recovery prompt를 보여주고 복사/표시하는 흐름에 직접적 연관
  - 위험도: medium

- `server/approvals_ui.html` (tracked)
  - 변경 목적: UI 문구(`Build LLM Retry Prompt`, `Copy Recovery Prompt`, `This does not auto-run or auto-approve.`) 반영
  - 포함 이유: 사용자 온보딩 문구와 경계를 명확히 하여 v0.3 안전 모델을 지지함
  - 위험도: low

- `tests/test_recovery_prompt.py` (untracked)
  - 변경 목적: `--mode auto` 권장 로직, contract reuse 검증 등 focused 테스트
  - 포함 이유: v0.3 핵심 동작 검증을 위해 필요
  - 위험도: low

- `tests/test_prompt_builder.py` (untracked)
  - 변경 목적: PromptBuilder.required_output_lines 재사용 등 계약 테스트
  - 포함 이유: 출력 계약 검증은 v0.3 릴리즈 안전 맥락에서 중요
  - 위험도: low

- `RELEASE_NOTES_v0.3.md` / `USABILITY_REVIEW_v0.3_candidate.md` / `docs/SEMI_AUTO_RECOVERY.md` (already created & committed)
  - 변경 목적: 릴리즈 요약, 사용성 검토, 설계 메모(온보딩 문구 포함)
  - 포함 이유: 릴리즈 문서 및 온보딩 문구는 v0.3 공개에 필수
  - 위험도: n/a (문서)

## B 그룹: v0.4 runtime 후보

이 그룹은 런타임 수준(core, orchestrator, recorder 등) 변경으로, v0.3 본선에 섞지 말고 `feature/v0.4-runtime-candidate`로 분리할 것을 권장합니다.

- `apos_core/context_pack.py` (tracked)
  - 역할: ContextPack 처리 로직(데이터 모델/시리얼라이저 등)
  - v0.3 제외 이유: 런타임 리팩터/기능 확장 가능성이 있어 안정성 검토 및 별도 통합 필요

- `apos_core/orchestrator.py` (tracked)
  - 역할: 오케스트레이션 상태머신/실행 경로 핵심
  - v0.3 제외 이유: 오케스트레이터 변경은 동작 범위를 넓힐 수 있어 추가 검증 필요

- `apos_core/recorder.py` (tracked)
  - 역할: 승인 항목/레코드 영속성 변경
  - v0.3 제외 이유: persistence 레이어 변화는 위험도가 높아 별도 분리 권장

- `apos_core/result_envelope.py` (tracked)
  - 역할: 결과/실행 봉투 구조 변경
  - v0.3 제외 이유: 데이터 계약 변화 가능성

- `apos_core/__init__.py` (tracked)
  - 역할: 패키지 exports 변경
  - v0.3 제외 이유: API 표면 변화는 별도 검토 필요

- `cli/context_pack.py`, `cli/plan_approve.py`, `cli/plan_step.py` (tracked)
  - 역할: CLI 서브커맨드 변경(플로우 확장)
  - v0.3 제외 이유: CLI 런타임 동작 확장은 v0.4 후보

- `server/apos_server.py` (tracked)
  - 역할: 서버 런타임 / transport 변경
  - v0.3 제외 이유: 런타임 서버 변경은 안정성 영향이 커 별도 검증 권장

- `server/approve_endpoint.py` (tracked)
  - 역할: 승인 엔드포인트 로직 변경
  - v0.3 제외 이유: 권한/승인 흐름 민감도 때문에 분리 권장

- (권장 브랜치) `feature/v0.4-runtime-candidate`

## C 그룹: 문서 변경 분류

문서 변경은 v0.3 릴리즈 노트·온보딩 문구처럼 바로 포함할 항목과, 설계·실험 노트로 나눌 필요가 있습니다.

- 포함(즉시 v0.3에 반영 권장):
  - `RELEASE_NOTES_v0.3.md` (커밋 완료)
  - `docs/SEMI_AUTO_RECOVERY.md` (온보딩 문구 추가, 커밋 완료)
  - `POST_V0.3_WORKTREE_REVIEW.md`, `POST_V0.3_CLEANUP_PLAN.md` (작업 기록)

- v0.4 분리 또는 보류(별도 커밋/브랜치 권장):
  - `docs/PROTOCOL.md` (tracked) — 설계 문서, v0.4로 보류 권장
  - `docs/SECURITY_MODEL.md` (tracked) — 보류(보안 정책 변경이면 별도 PR 권장)
  - `docs/SERVICE_OVERVIEW.md`, `docs/USAGE.md` (tracked) — 사용자 문서지만 범위가 넓으면 별도 커밋 권장
  - `docs/KNOWN_LIMITATIONS.md`, `docs/UI_OVERVIEW.md`, `docs/WEB_CONTROLLER_EXPERIMENT.md` (untracked) — 실험/한계 노트, 보류 또는 v0.4 문서로 이동
  - examples/* (untracked) — 데모/예제는 별도 정리 권장

## D 그룹: 테스트 변경 분류

테스트는 v0.3의 검증 자산으로 포함해야 할 것과, B 그룹 런타임과 묶어야 할 것을 구분합니다.

- v0.3 테스트(본선 포함 후보):
  - `tests/test_recovery_prompt.py` (untracked) — recover prompt 핵심 검증
  - `tests/test_prompt_builder.py` (untracked) — 출력 계약 검증
  - `tests/test_list_approvals_endpoint.py` (tracked) — 대시보드 API 검증

- v0.4 테스트(런타임 후보와 결합):
  - `tests/test_context_pack.py` (tracked) — ContextPack 런타임 관련
  - `tests/test_plan_approve.py` (tracked) — plan approval 흐름(런타임 의존)
  - `tests/test_plan_management.py`, `tests/test_standard_demo_flows.py` 등 (untracked) — 광범위한 시나리오, v0.4와 결합 권장

- debug/helper 스크립트(삭제 금지, 보류):
  - `tests/debug_plan_direct.py` (untracked)
  - `tests/debug_plan_runner.py` (untracked)

## F 그룹: bridge/Web Controller 실험군

이 그룹은 APOS Core의 안전 경계를 넘어 브라우저 확장/컨트롤러 실험을 포함합니다. 보안·안정성·정책상 본선에 포함할 수 없으므로 반드시 격리해야 합니다.

- 후보 파일 (보류/격리 대상):
  - `extension/contentScript.js` (tracked)
    - 역할: 브라우저 확장 content script — extension↔APOS bridge 동작
    - 삭제 금지 사유: 실험/브리지 코드로, 보안·권한 이슈가 있어 본선 포함 불가
  - `extension/manifest.json` (tracked)
    - 역할: 확장 매니페스트
    - 삭제 금지 사유: 실험적 확장 설정 — 본선 불가
  - `extension/bridgeUtils.js` (untracked)
    - 역할: 확장 브리지 헬퍼 라이브러리
    - 삭제 금지 사유: 실험 자산
  - `docs/WEB_CONTROLLER_EXPERIMENT.md` (untracked)
    - 역할: 웹 컨트롤러 실험 메모
    - 삭제 금지 사유: 실험 설계 및 보안 메모
  - `tests/bridge_extension_runtime_test.js`, `tests/test_bridge_extension_runtime.py` (untracked)
    - 역할: 브리지/확장 런타임 테스트
    - 삭제 금지 사유: 실험 검증 자산

- 권장 브랜치: `experiment/web-controller-bridge` (격리 권장, 본 작업에서는 생성 금지)

## 삭제하면 안 되는 항목

- 모든 `*.py` 소스 파일 (debug/helper 포함)
- extension/bridge 및 Web Controller 관련 파일
- v0.4 runtime 후보 파일
- 문서 및 테스트 소스

## 다음 권장 작업

1. v0.3 본선 포함 후보만 별도 커밋/PR로 배포할지 결정한다.
2. `feature/v0.4-runtime-candidate` 브랜치로 B 그룹을 분리(사용자 지시 시 실행).
3. `experiment/web-controller-bridge` 브랜치로 F 그룹을 분리(사용자 지시 시 실행).
4. C/D 그룹 중 문서·테스트의 세부 보존/커밋 정책을 확정한다.

---

파일 목록과 분류는 현재 `git status`/`git ls-files --others` 결과를 기반으로 작성했습니다. 이 문서는 분류 작업용이며, 본문에 열거된 어떤 파일도 이 문서 작성 과정에서 수정/삭제/커밋되지 않았습니다.
