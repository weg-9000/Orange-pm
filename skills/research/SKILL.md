---
name: research
description: 경쟁사 분석을 수행하고 비교 매트릭스 + 벤치마킹 인사이트를 생성한다. Discovery 3개 스트림 중 competitor 스트림을 완성한다.
triggers:
  - "research"
  - "competitor analysis"
  - "market research"
agent: researcher
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

2. `inputs/discovery/competitor/` 디렉토리가 존재하는지 확인한다.
   없으면 생성한다.

3. 기존 competitor 파일이 존재하면 덮어쓰기 전 PM에게 확인한다.


## 실행 단계

### 단계 1 — PM 조사 범위 확인

PM에게 다음 항목을 확인한다:

```
1. 분석 대상 경쟁사 목록 (최소 2개, 최대 5개 권장)
   예: "카카오 T, 쏘카, 그린카"

2. 조사 집중 영역 (복수 선택)
   [ ] 기능 구성 (Core Feature Set)
   [ ] 가격 정책 (Pricing Model)
   [ ] UX / 사용자 흐름
   [ ] 기술 제약 또는 연동
   [ ] 고객 불만 (리뷰 / 커뮤니티)

3. 조사 심도
   [ ] 빠른 스캔 (주요 특성만)
   [ ] 심층 분석 (고객 리뷰 + 비교 상세)
```

입력이 없으면 조사를 시작하지 않는다.


### 단계 2 — researcher 에이전트 기동

researcher 에이전트에 다음 컨텍스트를 전달한다:

```
분석 대상: {PM이 입력한 경쟁사 목록}
집중 영역: {PM이 선택한 영역}
조사 심도: {선택값}
제품 컨텍스트: {product} / PREFIX: {PREFIX}

정보 수집 소스 우선순위 (커넥터는 CONNECTORS.md 탐지 프로토콜로 확인,
부재 시 해당 소스는 `[{capability} 탐색 생략]` 기록 후 건너뜀):
  1. wiki 커넥터 — 내부 보유 경쟁사 자료 (예: Confluence·Notion)
  2. 웹 검색 (공식 사이트, 블로그, 앱스토어 리뷰)
  3. chat 커넥터 — 팀 내 기존 분석 메모 (예: Slack·Mattermost)

출력 대상:
  - inputs/discovery/competitor/{name}.md (경쟁사별)
  - inputs/discovery/competitor/overview.md (비교 매트릭스)
  - inputs/research.md (벤치마킹 인사이트)
```

에이전트는 각 경쟁사에 대해 단계 3의 구조로 파일을 생성한다.


### 단계 3 — 경쟁사별 분석 파일 생성

각 경쟁사에 대해 `inputs/discovery/competitor/{name}.md`를 생성한다.

**파일 형식:**
```markdown
# {경쟁사명} 분석

> 분석 기준일: {날짜}
> 출처: {내부 위키 URL 또는 웹 링크}

## 제품 포지셔닝

{핵심 가치 제안 1~2문장}

## 핵심 기능 목록

| 기능명 | 설명 | 우리 제품과 비교 |
|---|---|---|
| {기능} | {설명} | 동일 / 우위 / 열위 / 부재 |

## 가격 정책

{가격 구조 요약. 확인 불가 시 [미확인] 표기}

## UX 특성

{주요 화면 흐름 및 사용성 특이 사항}

## 고객 불만 / 약점

| 불만 항목 | 출처 | 심각도 (H/M/L) |
|---|---|---|

## 기술 제약 또는 연동

{알려진 기술적 제약 또는 외부 연동 특성}

## 시사점

{이 경쟁사 분석에서 도출한 핵심 인사이트 2~3개}
```

확인 불가한 항목은 `[미확인]`으로 표기한다. `[미확인]` 비율이 50% 이상이면
해당 경쟁사 파일에 `[정보 부족 — 낮은 신뢰도]` 경고를 추가한다.


### 단계 4 — overview.md 비교 매트릭스 작성

모든 경쟁사 파일을 읽어 비교 매트릭스를 작성한다.

**파일 형식:**
```markdown
# 경쟁사 비교 매트릭스 — {product}

> 기준일: {날짜}
> 분석 대상: {경쟁사 목록}

## 핵심 기능 비교

| 기능 | {자사} | {경쟁사A} | {경쟁사B} | {경쟁사C} |
|---|---|---|---|---|
| {기능명} | O / X / [미확인] | ... |

## 가격 정책 비교

| 항목 | {자사} | {경쟁사A} | {경쟁사B} |
|---|---|---|---|

## UX 흐름 비교

| 항목 | {자사} | {경쟁사A} | {경쟁사B} |
|---|---|---|---|

## 시장 공백 (경쟁사 전체 미지원 영역)

| 영역 | 설명 |
|---|---|

## 자사 차별화 가능 영역

| 영역 | 설명 | 우선순위 (H/M/L) |
|---|---|---|
```

비교 매트릭스 행이 3개 미만이면 품질 임계값 미달로 처리한다.


### 단계 5 — research.md 벤치마킹 인사이트 작성

overview.md의 교차 분석을 기반으로 작성한다.

**파일 형식:**
```markdown
# 벤치마킹 인사이트 — {product}

> 경쟁사 분석 기반 인사이트. /draft-req 시 synthesizer가 참조.

## 경쟁 환경 요약

{시장 전체 특성 2~3문장}

## 기능 격차 분석

| 격차 유형 | 내용 | 예상 요구사항 레이어 |
|---|---|---|
| 자사 부재 기능 | {경쟁사는 있고 우리는 없는 기능} | Layer 1 FR |
| 자사 약점 기능 | {경쟁사 대비 열위인 기능} | Layer 1 FR / Layer 2 NFR |
| 시장 공백 기회 | {경쟁사 전체 미지원 영역} | Layer 1 FR |

## 고객 불만 기반 개선 항목

{경쟁사 고객 불만에서 도출한 우리의 차별화 포인트}

## FR 매핑 예상 항목

> 이 섹션은 /draft-req에서 synthesizer가 requirements.md의 FR 항목과 연결한다.

| 인사이트 | 예상 FR 항목 | 우선순위 |
|---|---|---|
```


### 단계 6 — 품질 임계값 확인

| 항목 | 기준 |
|---|---|
| 경쟁사 파일 수 | 2개 이상 |
| 비교 매트릭스 행 | 3개 이상 |
| `[미확인]` 셀 비율 | 전체 셀의 50% 미만 |
| 시장 공백 항목 | 1개 이상 |
| FR 매핑 예상 항목 | 1개 이상 |

미달 항목이 있으면 `[품질 미달]` 경고를 표시하고
/draft-req에서 synthesizer가 강제 진행 여부를 판단하도록 기록한다.


### 단계 7 — session-log.md 및 open-issues.md 갱신

session-log.md에 추가한다:
```markdown
- {날짜} /research: 경쟁사 {N}개 분석 / 매트릭스 행 {N}개 / 시장공백 {N}개
```

open-issues.md에서 `[DISC-01]` 항목을 완료 처리한다:
```markdown
- [x] [DISC-01] ~~경쟁사 분석 미완료~~ → /research 완료
```

`[미확인]` 비율이 높은 경쟁사가 있으면 open-issues.md에 P2로 등록한다.


## 결과 파일 목록

| 파일 | 내용 |
|---|---|
| `inputs/discovery/competitor/{name}.md` | 경쟁사별 분석 파일 |
| `inputs/discovery/competitor/overview.md` | 비교 매트릭스 + 시장 공백 |
| `inputs/research.md` | 벤치마킹 인사이트 + FR 매핑 예상 |
| `open-issues.md` | DISC-01 완료 / 정보 부족 P2 등록 |
| `session-log.md` | research 완료 기록 |


## 다음 단계

3개 Discovery 스트림 완료 후:
- `/draft-req {product}`: requirements.md 초안 생성

병렬 실행 가능 스킬:
- `/stakeholder {product}`
- `/product-audit {product}`
