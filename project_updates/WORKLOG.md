# APOS 작업 저널

최종 업데이트: 2026-05-21

## 목적
- 이 폴더는 APOS 오케스트레이터의 작업 이력과 다음 계획을 추적하기 위한 기록 공간이다.
- 새로운 기여자가 봐도 지금까지 한 일과 앞으로 할 일을 바로 파악할 수 있도록 유지한다.

## 오늘 완료한 작업

### 1) 서버 보안/견고성 개선
- sha256 불일치 응답에서 상세 해시를 클라이언트 에러 메시지에 노출하지 않도록 변경
- patch_id 형식 제한 추가 (`^[A-Za-z0-9_-]{1,128}$`)
- 보호 영역 scratchpad 기록 시 마크다운 안전화 처리 추가
- 코드 펜스 언어 값 정규화/길이 제한 추가
- 코드 내용에 백틱이 있어도 안전하게 렌더링되도록 동적 fenced block 생성
- Python 검증 시 `.pyc` 임시 파일도 명시적으로 정리
- 커밋된 patch id 저장소에 만료 처리 추가
- 이벤트 루프 시간 참조를 running loop 기반으로 정리

### 2) 확장 기능 보완
- `window.__APOS_V32__.commit(patchId)` 함수 추가
- retry prompt에서 `project_root/target/language/patch_id` 하드코딩 제거
- metadata(또는 metadataText)에서 실제 기본값을 읽어 prompt 생성

### 3) 문서 보완
- 서버 재시작 시 pending patch 소멸 경고 추가
- DevTools 콘솔 커밋 예시 추가
- README 문서 트리에 SERVICE_OVERVIEW.md 누락 항목 반영

## 다음 작업 예정
- 문서의 절대 경로 하드코딩 정리 (README/USAGE/examples)
- Gemini DOM 기반 작성자/메시지 스코프 판별 호환성 개선
- extension queue/sentKeys/retryCounts 메모리 관리 정책 보강
- pending patch 목록 확인용 최소 UI 또는 API 설계안 정리

## 운영 규칙
- 코드 변경을 수행할 때마다 이 문서의 `오늘 완료한 작업`과 `다음 작업 예정`을 갱신한다.
- 계획이 바뀌면 이유를 함께 남긴다.
- 큰 변경은 관련 파일 경로를 함께 기록한다.

## GitHub 업로드 상태
- 현재 상태: 진행 중
- 완료 조건:
  - 로컬 git 초기화
  - 변경사항 커밋
  - 원격 저장소 연결
  - main 브랜치 push
