---
name: ingest
description: 프로젝트 디렉토리를 스캐폴딩하고 템플릿 파일을 초기화한다. layer-config.md를 설정하고 기존 Discovery 산출물 품질을 검증한다. 이 스킬은 프로젝트 최초 실행 또는 프로젝트 구조 복구 시 호출한다.
triggers:
  - "ingest"
  - "init project"
  - "setup project"
phase: 0
effort: low
model: haiku
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

1. `{product}` 인수가 비어 있으면 프로젝트 이름 입력을 요청한다.
   영문 소문자 + 하이픈만 허용한다 (예: `orange-cloud`).

2. `PROJECTS/{product}/`가 이미 존재하면
   재초기화(기존 파일 유지 + 누락 구조 보완) 또는
   새 초기화(전체 재생성) 여부를 PM에게 확인한다.
   재초기화 시 기존 파일은 덮어쓰지 않는다.


## 실행 단계

### 단계 1 — 디렉토리 구조 생성

다음 디렉토리를 생성한다 (이미 존재하면 건너뛴다):

```
PROJECTS/{product}/
├── inputs/
│   └── discovery/
│       ├── competitor/
│       ├── stakeholder/
│       └── product-audit/
├── graph/
├── work-orders/
├── drafts/
└── reports/

CONTEXT/
└── .template-cache/
```


### 단계 2 — 템플릿 파일 초기화

다음 파일이 없는 경우에만 생성한다 (기존 파일은 덮어쓰지 않는다):

**session-log.md:**
```markdown
# session-log — {product}

| Phase | 타임스탬프 | 실행 스킬 | 요약 |
|---|---|---|---|
| Init | {UTC 타임스탬프} | /ingest | 프로젝트 초기화 |
```

**open-issues.md:**
```markdown
# open-issues — {product}

## P0 (블로커)

## P1 (고우선순위)

- [ ] [DISC-01] 경쟁사 분석 미완료
- [ ] [DISC-02] 이해관계자 요구사항 수집 미완료
- [ ] [DISC-03] 자사 제품 현황 파악 미완료

## P2 (보통)

## P3 (낮음)

## 완료됨
```

**decisions.md:**
```markdown
# {product} Decisions

- PREFIX: {PREFIX}
- created_at: {UTC 타임스탬프}
- freeze: false

> 결정 관리 규칙: 에이전트가 결정성 발화·합의·번복을 감지하면 표에 후보 행을 자동 등재 (승인 칼럼 = `⬜`).
> PM은 「승인」 셀에 `✅ {pm_id}` 직접 기입하거나 `/dec-approve {DEC-ID,...}` 로 일괄 승인한다.
> 미승인 DEC은 정본 효력 없음 (INFO). 컬럼 정의·승인 워크플로는 [[CONTEXT/dec-schema]] 참조.

## DEC 원장 (SSoT)

| ID | 일자 | 도메인 | 핵심 결정 | 번복 | 승인 | 근거(스킬·세션) |
|---|---|---|---|---|---|---|
| _(아직 없음)_ | | | | | | |

## Freeze Records

_(아직 없음)_
```

**도메인 ENUM**: 🏗️인프라 · 🧭LNB·네비 · 🎯화면 인터랙션 · 💰결제·약정 · 📊무료·SSoT · 🔧입력 컨트롤 · 🎨용어·시각 · 🛡️종속·자원 · 📦컨테이너 · 🔗공유·연동 · 🤖자동기록

**승인 ENUM**: `⬜` 미승인 / `✅ {pm_id}` 승인 / `❌ {pm_id}: {사유}` 반려 / `🟡 보류`


### 단계 3 — CONTEXT/layer-config.md 설정

`CONTEXT/layer-config.md`가 존재하고 ACTIVE_PREFIX(또는 PREFIX)가 채워져 있으면
기존 값을 사용한다. 비어 있으면 PM에게 다음 항목을 입력받는다:

```
1. PREFIXES (작업할 제품군 id+label 목록, 단일 가능. 예: G2/민간, PG2/공공)
2. ACTIVE_PREFIX (현재 세션 작업 대상 — PREFIXES 중 하나)
3. {ACTIVE_PREFIX}-A Confluence URL (어휘 / 정책 원칙)
4. {ACTIVE_PREFIX}-B Confluence URL (공통 정책)
5. {ACTIVE_PREFIX}-C Confluence URL (선택 계층, 없으면 N/A)
6. brand-voice.md 경로 또는 Confluence URL (없으면 N/A)
```

입력받은 값으로 `CONTEXT/layer-config.md`를 생성한다:

```markdown
# layer-config

PREFIXES:
  - id: {ACTIVE_PREFIX}
    label: {label}
ACTIVE_PREFIX: {ACTIVE_PREFIX}
PREFIX: {ACTIVE_PREFIX}   # 레거시 호환 — ACTIVE_PREFIX 와 동기 유지

{ACTIVE_PREFIX}-A URL: {입력값}
{ACTIVE_PREFIX}-B URL: {입력값}
{ACTIVE_PREFIX}-C URL: {입력값 또는 N/A}

brand-voice: {입력값 또는 N/A}
```

{PREFIX}-A / {PREFIX}-B URL이 N/A이면 open-issues.md에 P0으로 등록하고
`/graph-gen` 실행 전 반드시 입력하도록 안내한다.


### 단계 4 — 기존 Discovery 산출물 검증

다음 파일이 존재하는 경우에만 품질 검증을 수행한다.
존재하지 않으면 해당 항목을 "미생성" 으로 표시하고 건너뛴다.

**inputs/requirements.md 검증:**

| 항목 | 기준 | 결과 |
|---|---|---|
| Layer 1 FR | 섹션 존재 여부 | 존재 / 미존재 |
| Layer 2 NFR | 섹션 존재 여부 | 존재 / 미존재 |
| Layer 4 액터 | 섹션 존재 여부 | 존재 / 미존재 |
| Layer 5 외부 연동 | 섹션 존재 여부 | 존재 / 미존재 |
| FR 항목 수 | 10개 이상 | {N}개 |

**inputs/research.md 검증:**

| 항목 | 기준 | 결과 |
|---|---|---|
| 경쟁사 분석 섹션 | 존재 여부 | 존재 / 미존재 |
| FR 매핑 | 존재 여부 | 존재 / 미존재 |

**discovery/ 스트림 검증:**

| 스트림 | 파일 수 | overview.md |
|---|---|---|
| competitor/ | {N}개 | 존재 / 미존재 |
| stakeholder/ | {N}개 | 존재 / 미존재 |
| product-audit/ | {N}개 | 존재 / 미존재 |


### 단계 5 — 초기 상태 진단 및 다음 단계 안내

검증 결과를 다음 형식으로 출력한다:

```
프로젝트 초기화 완료: {product}

  디렉토리 구조: 완료
  PREFIX:         {PREFIX}
  {PREFIX}-A:     {등록됨 / 미등록 (P0)}
  {PREFIX}-B:     {등록됨 / 미등록 (P0)}
  {PREFIX}-C:     {등록됨 / N/A}
  brand-voice:    {등록됨 / N/A}

Discovery 상태:
  requirements.md:   {완비 / 부분 / 미생성}
  research.md:       {존재 / 미생성}
  competitor/:       {N}개 파일
  stakeholder/:      {N}개 파일
  product-audit/:    {N}개 파일

추천 다음 단계:
  {requirements.md 없음}  → /research, /stakeholder, /product-audit 중 하나부터 시작
  {requirements.md 완비}  → /draft-req {product}
  {draft-req 완료}        → /graph-gen {product}
```


### 단계 6 — session-log.md 갱신

session-log.md의 Init 행을 최종 상태로 업데이트한다:
```markdown
| Init | {UTC 타임스탬프} | /ingest | 스캐폴딩 완료 / PREFIX: {PREFIX} / requirements: {상태} |
```


## 결과 파일 목록

| 파일 | 내용 |
|---|---|
| `PROJECTS/{product}/` | 전체 디렉토리 구조 |
| `PROJECTS/{product}/session-log.md` | Init 기록 |
| `PROJECTS/{product}/open-issues.md` | DISC-01~03 초기 등록 |
| `PROJECTS/{product}/decisions.md` | 초기화 기록 |
| `CONTEXT/layer-config.md` | PREFIX + Confluence URL + brand-voice |
| `CONTEXT/.template-cache/` | 빈 캐시 디렉토리 (실제 캐시 파일은 `/graph-gen`이 생성) |


## 다음 단계

discovery 스킬은 순서 무관하게 실행 가능하다. 세 스킬 모두 완료 후 `/draft-req`를 실행한다.

> ⚠️ `CONTEXT/.template-cache/`에 {PREFIX}-A/B/C 캐시 파일을 저장하는 것은 `/graph-gen`이 담당한다.
> `/ingest`는 디렉토리 구조만 준비하며, 캐시 파일 생성은 `/graph-gen` 단계 2에서 수행된다.

- `/research {product}`: 경쟁사 분석
- `/stakeholder {product}`: 이해관계자 요구사항 수집
- `/product-audit {product}`: 자사 제품 현황 파악
