---
name: product-audit
description: 사용자가 연결한 wiki·design·repo 커넥터(CONNECTORS.md)를 통해 자사 제품 현황을 분석하고 기존 기능 목록, 페인 포인트, 개선 기회를 구조화한다. Discovery 3개 스트림 중 product-audit 스트림을 완성한다.
triggers:
  - "product-audit"
  - "audit product"
  - "analyze product"
phase: -1
effort: medium
user-invocable: true
---

## Bootstrap 캐시 가드 (개선안 F — CONTEXT_OPTIMIZATION.md)

세션 첫 진입 시 `CONTEXT/_session-bootstrap.md` 를 1회만 로드한다.
이미 같은 세션에서 본 파일을 읽었다면 재독을 금지한다.
캐시가 없거나 stale 이면 다음 명령으로 갱신한 뒤 진행한다:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```

본 가드는 layer-config / about-pm / project-rules / brand-voice /
doc-layer-schema / team-members 6개 원본 파일 재로드를 대체한다.
원본 파일 직접 Read 는 본 skill 의 핵심 작업에 필수인 경우에만 허용된다.

## 전제조건 검사

1. `CONTEXT/layer-config.md`에서 PREFIX를 읽는다.
   미존재 시 `/ingest {product}` 실행을 안내한다.

2. `inputs/discovery/product-audit/` 디렉토리가 존재하는지 확인한다.
   없으면 생성한다.

3. 기존 파일이 존재하면 덮어쓰기 전 PM에게 확인한다.


## 실행 단계

### 단계 1 — 문서 조회 (`wiki` 커넥터)

`wiki` 커넥터(예: Confluence, Notion — CONNECTORS.md 탐지 프로토콜)를 사용해 다음 항목을 조회한다:

**조회 대상:**
- 현재 서비스 기능 명세 페이지 (Approved 문서 우선)
- 이전 개발 주기 PRD / 기획서
- API 연동 명세 문서
- 알려진 이슈 / 버그 기록 페이지

**수집 항목:**
- 기능명, 기능 설명, 현재 상태 (운영 중 / 개발 중 / 중단)
- 기능별 관련 레이어 (정책 / 화면 / 시스템)
- 문서화된 고객 불만 또는 한계 사항

커넥터 부재·연결 실패 시 `[wiki 연동 없음 — 탐색 생략]`을 기록하고 계속 진행한다.


### 단계 2 — 디자인 조회 (`design` 커넥터)

`design` 커넥터(예: Figma — CONNECTORS.md 탐지 프로토콜)를 사용해 현재 제품 디자인 파일을 조회한다.

**수집 항목:**
- 화면 목록 (프레임 이름 기준)
- 화면별 상태 (현행 UI / 개편 예정 / Deprecated)
- 주요 컴포넌트 및 반복 패턴
- 화면 흐름 (프로토타입 연결 기준)

커넥터 부재·연결 실패 시 `[design 연동 없음 — 탐색 생략]`을 기록하고 계속 진행한다.


### 단계 3 — 저장소 조회 (`repo` 커넥터)

`repo` 커넥터(예: GitLab, GitHub — CONNECTORS.md 탐지 프로토콜)를 사용해 다음 항목을 조회한다:

**조회 대상:**
- 최근 90일 Closed 이슈 제목 + 레이블
- 최근 90일 Merged MR 제목
- README 또는 CHANGELOG

**수집 항목:**
- 최근 변경된 기능 범위
- 반복적으로 등장하는 버그 패턴
- 기술 부채 관련 레이블 (tech-debt, hotfix 등)

커넥터 부재·연결 실패 시 `[repo 연동 없음 — 탐색 생략]`을 기록하고 계속 진행한다.


### 단계 4 — existing-features.md 작성

수집된 데이터를 기반으로 작성한다.

**작성 기준:**
- 각 기능을 운영·개발·중단 상태로 분류한다.
- 기능 단위는 화면 또는 API 기준으로 분리한다.
- 디자인 화면명과 문서 기능명이 일치하지 않으면 양쪽을 병기한다.

**파일 형식:**
```markdown
# 기존 기능 목록 — {product}

> 수집 기준일: {날짜}
> 출처: wiki / design / repo 커넥터 (탐색 성공 소스만 기재)

## 운영 중 기능

| 기능명 | 설명 | 관련 화면 | 문서 출처 | 비고 |
|---|---|---|---|---|

## 개발 중 기능

| 기능명 | 설명 | 예상 완료 | 출처 | 비고 |
|---|---|---|---|---|

## 중단 / Deprecated

| 기능명 | 중단 사유 | 대체 기능 |
|---|---|---|

## 탐색 공백 (출처 미확인 기능)

| 기능명 | 공백 사유 |
|---|---|
```

"탐색 공백" 항목이 3개 이상이면 open-issues.md에 P2로 등록한다.


### 단계 5 — pain-points.md 작성

수집된 이슈, 불만, 한계 사항을 유형별로 분류한다.

**분류 기준:**

| 유형 | 정의 |
|---|---|
| UX | 사용자 흐름 불편, 이해 어려움, 피드백 부재 |
| 성능 | 응답 지연, 오류율, 처리 한계 |
| 비즈니스 로직 | 정책 불일치, 예외 미처리, 엣지케이스 오류 |
| 연동 | 외부 시스템 연결 불안정, API 불일치 |
| 운영 | 관리 도구 부재, 모니터링 불가, 수동 처리 필요 |

**파일 형식:**
```markdown
# 페인 포인트 — {product}

> 수집 기준일: {날짜}
> 출처: wiki / repo 이슈 / chat 커넥터 (탐색 성공 소스만 기재)

## UX 페인 포인트

| 항목 | 설명 | 출처 | 심각도 (H/M/L) |
|---|---|---|---|

## 성능 페인 포인트

...

## 비즈니스 로직 페인 포인트

...

## 연동 페인 포인트

...

## 운영 페인 포인트

...
```

심각도 H 항목이 존재하면 open-issues.md에 P1으로 등록한다.


### 단계 6 — overview.md 작성

existing-features.md와 pain-points.md를 교차 분석해 작성한다.

**파일 형식:**
```markdown
# 제품 현황 요약 — {product}

## 현황 스냅샷

| 항목 | 수치 |
|---|---|
| 운영 중 기능 수 | {N}개 |
| 개발 중 기능 수 | {N}개 |
| 페인 포인트 총계 | {N}건 (H: {N} / M: {N} / L: {N}) |
| 탐색 공백 수 | {N}건 |

## 개선 기회 도출

{pain-points.md 심각도 H/M 항목을 기반으로 개선이 필요한 영역 서술}

### 요구사항 연결 가능성

| 개선 기회 | 예상 요구사항 레이어 | 우선순위 |
|---|---|---|
| {개선 항목} | Layer 1 FR / Layer 2 NFR | H / M / L |

## 기존 기능 재사용 가능성

| 기능명 | 재사용 범위 | 비고 |
|---|---|---|

## 탐색 공백 및 미확인 항목

{탐색 불가했던 소스와 이유를 기록}
```


### 단계 7 — 품질 최소 임계값 확인

다음 기준을 충족하지 못하면 PM에게 보완 여부를 확인한다:

| 항목 | 기준 |
|---|---|
| existing-features.md 기능 수 | 운영 중 기능 1개 이상 |
| pain-points.md 항목 수 | 총 1개 이상 |
| overview.md 개선 기회 | 1개 이상 |
| 탐색 공백 비율 | 전체 기능 수의 50% 미만 |

미달 항목이 있으면 `[품질 미달]` 경고를 표시하고
/draft-req에서 synthesizer가 강제 진행 여부를 판단하도록 기록한다.


### 단계 8 — session-log.md 및 open-issues.md 갱신

session-log.md에 추가한다:
```markdown
- {날짜} /product-audit: 기능 {N}개 / 페인포인트 {N}건 (H: {N}) / 탐색공백 {N}건
```

open-issues.md에서 `[DISC-03]` 항목을 완료 처리한다:
```markdown
- [x] [DISC-03] ~~자사 제품 현황 파악 미완료~~ → /product-audit 완료
```

심각도 H 페인 포인트별 P1 항목을 추가한다.


## 결과 파일 목록

| 파일 | 내용 |
|---|---|
| `inputs/discovery/product-audit/existing-features.md` | 기능 현황 + 상태 분류 |
| `inputs/discovery/product-audit/pain-points.md` | 유형별 페인 포인트 + 심각도 |
| `inputs/discovery/product-audit/overview.md` | 현황 요약 + 개선 기회 + 요구사항 연결 |
| `open-issues.md` | DISC-03 완료 / 탐색 공백 P2 / 심각도 H P1 등록 |
| `session-log.md` | product-audit 완료 기록 |


## 다음 단계

3개 Discovery 스트림 완료 후:
- `/draft-req {product}`: requirements.md 초안 생성
