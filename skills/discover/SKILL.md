---
name: discover
description: 프로젝트 전체 디렉토리 구조를 생성하고 Discovery 단계(Phase -1)를 초기화한다. 신규 프로젝트의 첫 번째 실행 스킬이다.
triggers:
  - "discover"
  - "new project"
  - "init project"
phase: -1
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

1. `CONTEXT/layer-config.md`를 읽어 `{product}`가 이미 등록된 PREFIX와 충돌하는지 확인한다.
   충돌 시 PM에게 다른 이름 사용을 안내한다.

2. `PROJECTS/{product}/` 디렉토리가 이미 존재하는지 확인한다.
   존재 시 다음 두 가지 선택지를 제시한다:
   - 기존 프로젝트 이어서 진행 (`SessionStart` 흐름으로 안내)
   - 완전 초기화 (PM 명시적 확인 후 진행)


## 실행 단계

### 단계 1 — PREFIX 등록

PM에게 이 프로젝트의 PREFIX 값을 입력받는다.
입력 예: `CLOUD`, `DBAAS`, `BILLING`
입력값이 없으면 `{product}` 대문자를 기본값으로 사용하고 PM에게 확인한다.

`CONTEXT/layer-config.md`에 다음 항목을 추가한다:
```markdown
## {product}
- PREFIX: {PREFIX}
- created_at: {UTC 타임스탬프}
- phase: -1
```


### 단계 2 — 전체 디렉토리 구조 생성

다음 디렉토리를 일괄 생성한다:

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
```

CONTEXT/ 디렉토리가 없으면 함께 생성한다.


### 단계 3 — 핵심 파일 초기화

**session-log.md**:
```markdown
# {product} Session Log

- PREFIX: {PREFIX}
- created_at: {UTC 타임스탬프}

## Phase History

| Phase | 진입 시각 | 진입 스킬 | 비고 |
|---|---|---|---|
| -1 (Discovery) | {UTC 타임스탬프} | /discover | 프로젝트 초기화 |
```

**decisions.md**:
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

**open-issues.md**:
```markdown
# {product} Open Issues

## P0 — 즉시 해소 필요

_(없음)_

## P1 — Discovery 필수 수집 항목

- [ ] [DISC-01] 경쟁사 분석 최소 3개사 미완료 → `/research {product}` 실행
- [ ] [DISC-02] 이해관계자 요구사항 수집 미완료 → `/stakeholder {product}` 실행
- [ ] [DISC-03] 자사 제품 현황 파악 미완료 → `/product-audit {product}` 실행
- [ ] [DISC-04] `{PREFIX}-B` 공통 정책 문서 Confluence 링크 미등록

## P2 — 권장 수집 항목

- [ ] [DISC-05] 법적·규제 제약 조건 확인
- [ ] [DISC-06] 연동 대상 외부 시스템 목록 초안 작성
```


### 단계 4 — Discovery 서브디렉토리 템플릿 생성

**inputs/discovery/competitor/overview.md**:
```markdown
# 경쟁사 분석 개요

## 분석 대상

| 경쟁사 | 분석 완료 | 담당 | 비고 |
|---|---|---|---|
| (미입력) | | | |

## 기능 비교 매트릭스

| 기능 항목 | 자사 | 경쟁사 A | 경쟁사 B | 경쟁사 C |
|---|---|---|---|---|
| (미입력) | | | | |

## 주요 발견 사항

_(분석 완료 후 작성)_
```

**inputs/discovery/stakeholder/overview.md**:
```markdown
# 이해관계자 요구사항 개요

## 이해관계자 목록

| 이름 | 직책 | 관심 영역 | 인터뷰 완료 |
|---|---|---|---|
| (미입력) | | | |

## 요구사항 요약

_(인터뷰 완료 후 작성)_

## 미결 요구사항

_(작성 전)_
```

**inputs/discovery/product-audit/overview.md**:
```markdown
# 자사 제품 현황 개요

## 기존 기능 목록

| 기능명 | 구현 상태 | 개선 필요 여부 | 비고 |
|---|---|---|---|
| (미입력) | | | |

## 반복 문제 (Pain Points)

| 항목 | 유형 (성능/UX/보안) | 빈도 | 우선순위 |
|---|---|---|---|
| (미입력) | | | |

## 기술 제약 사항

_(작성 전)_
```


### 단계 5 — session-log.md 완료 기록

```markdown
| -1 (Discovery) | {UTC 타임스탬프} | /discover 완료 | 디렉토리 구조 생성, 템플릿 초기화 |
```


## 결과 파일 목록

| 파일 / 디렉토리 | 내용 |
|---|---|
| `CONTEXT/layer-config.md` | PREFIX 등록 |
| `PROJECTS/{product}/` | 전체 8개 디렉토리 생성 |
| `session-log.md` | Phase -1 진입 기록 |
| `decisions.md` | 초기 템플릿 (freeze: false) |
| `open-issues.md` | Discovery 필수 수집 6개 P1/P2 항목 |
| `inputs/discovery/competitor/overview.md` | 비교 매트릭스 템플릿 |
| `inputs/discovery/stakeholder/overview.md` | 이해관계자 목록 템플릿 |
| `inputs/discovery/product-audit/overview.md` | 현황 파악 템플릿 |


## 다음 단계

Discovery 3개 스킬을 병렬로 실행할 수 있다:
- `/research {product}`: 경쟁사 분석
- `/stakeholder {product}`: 이해관계자 요구사항 수집
- `/product-audit {product}`: 자사 제품 현황 파악

3개 스킬 완료 후 → `/draft-req {product}`
