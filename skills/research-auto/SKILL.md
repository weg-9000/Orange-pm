---
name: research-auto
description: |
  웹 검색 + LLM 요약으로 자동 타사조사 수행. inputs/discovery/competitor/*.md
  + research.md (D5 양식) 초안 생성. 사실 정확성 보장 안 됨 — 항상 PM 승인 게이트.

  사용 시점:
    - 신제품 Phase -1 discovery 자동화
    - Track B 의 "타사조사 후 D1/D5 작성" 진입
    - 기존 research.md 보강 (--augment)
triggers:
  - "타사조사 후"
  - "경쟁사 조사"
  - "자동 리서치"
  - "타사조사 해줘"
  - "research-auto"
phase: -1
effort: high
model: opus
user-invocable: true
---

## 1. 진입 조건

본 스킬은 다음 중 하나일 때 실행된다:

- 사용자가 명시적으로 **"타사조사"** 키워드 + 제품/주제 키워드를 지정
- `intent-router` 가 라우팅: `"{제품} 타사조사 후 작성"` → `research-auto` → `draft-req`
- 기존 `inputs/discovery/competitor/` 보강 요청 (`--augment` 플래그)

진입 시 PM 에게 다음을 1회 확인한다:

```
타사조사 자동 실행 — 다음 정보 확인:
  - 제품 / 주제: {product}
  - 도메인 키워드: {domain}
  - 조사 대상 지역: {국내 / 글로벌 / 양쪽}
  - 기존 inputs/discovery/competitor/ 처리: [augment / replace]
```

---

## 2. 전제조건

### 2-1. 도구 가용성

| 도구 | 용도 | 필수 |
|---|---|---|
| `WebSearch` | 시드 검색 / 경쟁사 식별 | 필수 |
| `WebFetch` | 경쟁사 공식 페이지 상세 수집 | 필수 |

도구 미가용 시 즉시 중단하고 PM 에게 보고. 우회·추정 채움 절대 금지.

### 2-2. 제품 / 주제 모호성 검증

제품명이 일반명사이거나 동음이의 가능성이 있으면 PM 에게 보완 키워드를 받는다.
(예: "DB" → "DBaaS / 관리형 데이터베이스 / 자사 DBaaS" 중 어느 쪽인지)

### 2-3. 기존 파일 존재 분기

`Planning-Agent-Hub/PROJECTS/{product}/inputs/discovery/competitor/` 존재 시:

| 플래그 | 동작 |
|---|---|
| `--augment` | 기존 파일 보존 + 신규 경쟁사 추가 |
| `--replace` | 기존 파일 백업 (`.bak`) 후 신규 작성 |
| (없음) | PM 에게 분기 선택 요청 |

---

## 3. 조사 절차

### 3-A. 시드 검색 (WebSearch)

다음 키워드 조합으로 상위 10~20개 결과를 수집한다:

- `{제품} 경쟁사`
- `{제품} alternatives`
- `{제품} comparison vs`
- `{도메인} market share`
- `{도메인} pricing 2025`
- `{도메인} top providers`
- `{제품} 한국 시장` (국내 조사 포함 시)

각 검색 결과의 (제목, URL, snippet, 검색 일자) 를 메모리 버퍼에 보존한다.

### 3-B. 경쟁사 식별

수집한 시드 결과에서 다음을 추출한다:

- 회사명 + 제품명
- 도메인 분류 (예: 글로벌 클라우드 / 한국 IDC / SaaS 전문 등)
- 빈도 (몇 개 결과에서 언급되었는지)

빈도순으로 정렬 후 **상위 3~5개** 경쟁사를 선정한다.
PM 이 특정 경쟁사를 사전에 지정한 경우 해당 경쟁사를 우선 포함한다.

### 3-C. 경쟁사별 상세 fetch (WebFetch)

각 경쟁사에 대해 다음 페이지를 순차 fetch:

1. 공식 사이트 메인 / 제품 페이지 — 회사·제품 개요
2. 가격 (Pricing) 페이지 — 요금제 표
3. 기능 (Features) 페이지 — 핵심 기능 / 차별점
4. SLA / 약관 / 통합 페이지 (가용 시)

⚠ **출처 URL + 수집 일자(UTC) 를 반드시 보존**. 모든 인용 값에 `[REF-NN]` ID 부여.

수집 실패 시 (404 / robots 차단 / 비공개) 해당 행을 `[미확인:사유]` 로 표기.
추정 채움 금지.

### 3-D. 시장 개요 fetch

다음 항목을 별도 fetch:

- TAM / SAM / SOM (가능한 한 수치 + 출처) — Gartner / IDC / 한국 KISDI 등 1·2차 자료
- 시장 트렌드 3~5개 (수요 / 가격 / 기술 축)
- 진입 장벽 / 차별화 포인트 (규제 / 자본 / 기술)

수치 미확보 항목은 `[확인필요]` 로 표기.

---

## 4. 출력 파일

```
Planning-Agent-Hub/PROJECTS/{product}/
├── inputs/discovery/competitor/
│   ├── overview.md          # 시장 개요 + 비교 매트릭스
│   ├── {competitor_1}.md    # 경쟁사 1 상세
│   ├── {competitor_2}.md
│   └── {competitor_3}.md
└── drafts/
    └── D5.draft.md          # research.md (D5 양식) 자동 채움 초안
```

### 4-1. 파일 frontmatter (필수)

각 자동 생성 파일에 다음 frontmatter 를 삽입한다:

```yaml
---
generated_by: research-auto
generated_at: YYYY-MM-DD
product: {product}
sources:
  - id: REF-01
    url: https://...
    fetched_at: YYYY-MM-DD
    title: "..."
    reliability: 1차 | 2차 | 3차
status: draft  # PM 승인 전까지 draft 고정
approved_by: null
approved_at: null
---
```

### 4-2. overview.md 본문 구조

draft-req SKILL.md 의 competitor 임계값 (비교 매트릭스 행 3개 이상 / `[미입력]` 셀 50% 미만) 을 충족하도록 작성한다:

- §1 시장 정의 (TAM/SAM/SOM)
- §2 시장 트렌드 (3~5개)
- §3 진입 장벽 / 차별화 포인트
- §4 경쟁사 비교 매트릭스 (행 3개 이상)

### 4-3. 경쟁사별 파일 본문 구조

D5 §3~§5 와 동일 구조:

- 회사 / 제품 개요
- 가격 정책 (요금제 표)
- 핵심 기능 / 차별점
- 약점 / 제약
- 출처 ID 매핑

---

## 5. D5 양식 채워 넣기

`templates/standard/D5_research.md` 를 `Planning-Agent-Hub/PROJECTS/{product}/drafts/D5.draft.md` 로 복사 후 다음 placeholder 를 자동 치환한다:

| Placeholder | 치환 값 |
|---|---|
| `{{PRODUCT_NAME}}` | 제품명 |
| `{{DOC_ID}}` | 자동 생성 (예: `RES-{product}-001`) |
| `{{VERSION}}` | `1.0-draft` |
| `{{DATE}}` | 생성 일자 (YYYY-MM-DD) |
| `{{TAM}} / {{SAM}} / {{SOM}}` | 추출 수치 (없으면 `[확인필요]`) |
| `{{COMPETITOR_1~3}}` | 추출 경쟁사명 |
| `{{REF}} / {{REF_1~3}}` | 출처 URL (REF-NN ID 와 §7-1 출처 목록 연동) |
| `{{T-01~03}}` | 트렌드 (없으면 `[확인필요]`) |

⚠ 추정·환각 채움 금지. 미확보 영역은 `[확인필요]` 또는 `[미확인:사유]` 로 명시.

---

## 6. PM 승인 게이트 (필수 — 우회 금지)

자동 생성 결과는 **draft 상태로 stop**. 다음 안내를 출력한 뒤 다음 스킬 (draft-req / render) 로 자동 전이하지 않는다:

```
✋ 자동 타사조사 완료 — PM 승인 필요

생성 파일:
  - inputs/discovery/competitor/overview.md (시장 개요)
  - inputs/discovery/competitor/{N}.md (경쟁사 {N}개)
  - drafts/D5.draft.md (D5 양식 자동 채움)

수집 통계:
  - 시드 검색 결과: {NN} 건
  - 경쟁사 fetch 성공: {N}/{M}
  - [확인필요] 셀 수: {N}
  - 1차 출처 비율: {NN}%

다음 단계:
  1. 각 파일 검토 — 특히 가격/기능 수치 정확성
  2. 인용 URL 확인 (frontmatter sources)
  3. [확인필요] 셀 PM 수기 보강
  4. PM 승인 후 다음 명령 실행:
     - /draft-req {product}     (3 discovery 스트림 종합)
     - /render {product} --push (D5 발행)

승인 명령:   /research-auto --approve {product}
재생성:     /research-auto {product} --regenerate
부분 보강:   /research-auto {product} --augment
```

PM 승인 (`--approve`) 시점에 frontmatter 의 `status: draft` → `status: approved`, `approved_by` / `approved_at` 기록한다.

---

## 7. fact-check 안전망

자동 생성 결과는 `scripts/fact_preservation_check.py` (있는 경우) 호환 형식을 보장한다:

- **숫자/단위 보존**: "월 $0.018/GB" 등 단가 표기를 변환 없이 원문 그대로 보존
- **표 형식 보존**: D5 양식의 `<!-- col-widths: ... -->` 주석 유지
- **출처 인용 보존**: 모든 수치·인용 셀에 `[REF-NN]` ID 필수
- **원문 인용은 큰따옴표**: 공식 문서 인용 시 따옴표 + 출처 명시

`project-rules.md` 의 결정 관리 / 미결 항목 / Confluence 동기화 정책에 따라:

- 자동 생성 시 PM 결정이 필요한 모든 항목은 `open-issues.md` 에 `[RA-NN]` ID 로 등록
- Confluence 동기화는 PM 승인 후 `/render --push` 단계에서만 수행 (research-auto 자체는 push 금지)

---

## 8. 한계 사항

| 한계 | 대응 |
|---|---|
| 웹 정보 최신성 (검색 시점 기준) | frontmatter `fetched_at` 명시 + 분기 재실행 권장 |
| 비공개 가격 / 협상 단가 | `[미확인:비공개]` 표기 — PM 수기 보강 |
| 한국 시장 특수 정보 부족 | `--augment` 로 PM 보강 분리 |
| LLM hallucination 위험 | 모든 수치는 출처 URL 필수 / 미확보는 `[확인필요]` |
| 동적 페이지 / SPA fetch 실패 | `[미확인:fetch-fail]` 표기 |

**자동 발행 절대 금지**. PM 승인 게이트 우회는 본 스킬의 무결성을 깨뜨린다.

---

## 9. 워크플로 연결

```
intent-router
    ↓ ("{제품} 타사조사 후 작성")
research-auto  ← 본 스킬
    ↓ (PM 승인 게이트)
draft-req      ← 3 discovery 스트림 종합 (competitor / stakeholder / product-audit)
    ↓
render --push  ← D5 / D1 발행
```

- **선행**: `intent-router` (라우팅 분기)
- **후속**:
  - `draft-req` — competitor 스트림을 stakeholder / product-audit 와 종합
  - `render --push` — D5 발행 (PM 승인 필수)

---

## 10. 사용 예시

```bash
# 신제품 자동 타사조사 (전체 신규 생성)
/research-auto dbaas
# → inputs/discovery/competitor/ + drafts/D5.draft.md 생성

# 기존 조사 보강 (신규 경쟁사 추가)
/research-auto dbaas --augment
# → 기존 파일 보존 + 신규 경쟁사 .md 만 추가

# 전체 재생성 (기존 백업 후 새로 작성)
/research-auto dbaas --regenerate
# → inputs/discovery/competitor/*.md → *.md.bak 백업 후 신규 작성

# PM 승인 (frontmatter status → approved)
/research-auto dbaas --approve

# 승인 후 D5 발행
/draft-req dbaas
/render dbaas --push
```

---

## 11. session-log 기록

본 스킬 실행 시 `session-log.md` 에 다음 형식으로 1행 추가:

```markdown
| -1 (Discovery / Auto) | {UTC 타임스탬프} | /research-auto | 경쟁사 {N}개 / 시드 검색 {NN}건 / [확인필요] {N}건 / status: draft |
```

PM 승인 시 동일 형식으로 별도 행 추가 (`status: approved`).
