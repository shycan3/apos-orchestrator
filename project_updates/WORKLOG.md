# APOS 작업 저널

최종 업데이트: 2026-05-22

## 목적
- 이 폴더는 APOS 오케스트레이터의 작업 이력과 다음 계획을 추적하기 위한 기록 공간이다.
- 새로운 기여자가 봐도 지금까지 한 일과 앞으로 할 일을 바로 파악할 수 있도록 유지한다.

## 오늘 완료한 작업

### 1) Search & Replace 패치 지원 구현
- `Executor.preview_patch()`와 `Executor.apply_patch()`에 `search_and_replace` intent 추가
- 검색 문자열이 정확히 1회 매칭될 때만 파일을 수정하도록 적용
- 0회/다중 매칭/빈 검색어/대상 파일 없음/정책 차단 시 실제 파일 변경을 막도록 정리
- task envelope 검증과 validate-only 경로에 `search_and_replace` 허용 규칙 추가
- README, `docs/task_envelope_prompt.md`, `docs/APOS_PROJECT_OVERVIEW.md`에 구현 상태와 사용 예시 반영
- 신규 테스트로 preview, apply, 차단, validate-only 흐름을 덧붙임

### 1) 워크스페이스 정리 확인
- `.vscode/` 폴더 필요 여부를 점검했지만 현재 워크스페이스에는 존재하지 않음을 확인
- README에 `.vscode/`는 APOS 운영에 필요하지 않다는 점과 현재 삭제 대상이 없었다는 사실을 기록

### 2) APOS v3.2 + Bridge Protocol 정렬
- CLI 기본 생성 구조를 Bridge Protocol 기준으로 확장하도록 정리
- `.apos/preference_layer.md`, `.apos/risk_vector.json`, `.codex/APOS_INSTRUCTIONS.md` 기본 생성 항목 추가
- `specifications/architecture.md`를 Human Notes + Machine Facts 분리 구조로 갱신
- `specifications/immutable_rules.md`, `specifications/glossary.md`, `context/project_history.md`, `workspace/active_code.py`, `workspace/active_draft.md` 기본 파일 추가

### 3) 문서 기준선 갱신
- `README.md`를 APOS v3.2 + Bridge Protocol 기준으로 설명 보강
- `docs/PROTOCOL.md`에 Layer 1/Layer 2, 역할 분리, human/machine separation 규칙 추가
- `docs/SECURITY_MODEL.md`에 Bridge Layer, risk queue, human/machine isolation 규칙 추가
- `docs/SERVICE_OVERVIEW.md`에 Bridge Layer 설명과 CLI 생성 구조 반영

### 4) 서버 보안/견고성 개선
- sha256 불일치 응답에서 상세 해시를 클라이언트 에러 메시지에 노출하지 않도록 변경
- patch_id 형식 제한 추가 (`^[A-Za-z0-9_-]{1,128}$`)
- 보호 영역 scratchpad 기록 시 마크다운 안전화 처리 추가
- 코드 펜스 언어 값 정규화/길이 제한 추가
- 코드 내용에 백틱이 있어도 안전하게 렌더링되도록 동적 fenced block 생성
- Python 검증 시 `.pyc` 임시 파일도 명시적으로 정리
- 커밋된 patch id 저장소에 만료 처리 추가
- 이벤트 루프 시간 참조를 running loop 기반으로 정리

### 5) 확장 기능 보완
- `window.__APOS_V32__.commit(patchId)` 함수 추가
- retry prompt에서 `project_root/target/language/patch_id` 하드코딩 제거
- metadata(또는 metadataText)에서 실제 기본값을 읽어 prompt 생성

### 6) 문서 보완
- 서버 재시작 시 pending patch 소멸 경고 추가
- DevTools 콘솔 커밋 예시 추가
- README 문서 트리에 SERVICE_OVERVIEW.md 누락 항목 반영

## 다음 작업 예정
- `docs/USAGE.md`와 `examples/`의 APOS v3.2 + Bridge Protocol 용어 정리
- Search & Replace 사용 예시를 examples 쪽에도 추가할지 검토
- Gemini DOM 기반 작성자/메시지 스코프 판별 호환성 개선
- extension queue/sentKeys/retryCounts 메모리 관리 정책 보강
- pending patch 목록 확인용 최소 UI 또는 API 설계안 정리

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
