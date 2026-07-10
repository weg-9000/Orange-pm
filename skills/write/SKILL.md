---
name: write
description: policy WO 초안을 작성한다. 작성 전 반드시 {PREFIX}-B 공통 정책을 로드하고 Delta 범위(이 제품만의 예외·확장 사항)를 PM과 확인한 뒤 작성한다. {PREFIX}-B 내용과 동일한 항목은 절대 재작성하지 않는다. screen WO 초안은 /flow 스킬을 사용한다.
triggers:
  - "write"
  - "write wo"
  - "draft policy"
  - "정책서 작성"
  - "초안 작성"
phase: 2
effort: high
model: opus
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


## 공통 참조 가드 (C0·C-PIN — gates/master-derivation-gate.md SSoT)

작성 전 적용한다. 상세 정책·판정은 `CONTEXT/gates/master-derivation-gate.md`.

1. 공통 대조: 작성 항목이 G2-A/B 에 이미 있는지 `B-headings-index.json` 으로
   후보 §섹션만 식별한다(원문 전체 로드 금지 — 토큰 경계). 이미 있으면 재작성
   금지, `[{doc_id} §X] 참조` 링크로 대체. B 무시·자체 재서술도 금지.
2. C-PIN: draft frontmatter `referenced_master: [{핀ID}@{version}]` 에 Delta
   기준 공통를 핀한다. 핀 ID 는 `CONTEXT/reference-docs/master-id-map.yml`
   권위 ID(G2-A-001 / G2-B-001~004). 비우면 공통 미참조(opt-out) →
   decisions.md 근거 필수(없으면 WARN).
3. PM 확인은 이 스킬의 기존 Delta 확인 단계(단계 2)에 통합한다
   (가드 전용 직렬 프롬프트 추가 금지 — 단일 체크포인트).


## 입출력 (안 A — WO 템플릿 ↔ draft 1-파일화)

- **입력**: `PROJECTS/{product}/drafts/{WO_ID}.draft.md`
  (fanout 단계에서 생성된 빈 셸 — frontmatter `status: empty`, 본문에 `## 1.~7.` 표준 섹션 골격 + `<!-- wikilinks:start/end -->` 블록 포함)
- **출력**: `PROJECTS/{product}/drafts/{WO_ID}.draft.md`
  (**동일 파일 수정** — `status: empty → ai-draft`, 표준 섹션 골격을 콘텐츠로 채움)

> 이전 명세(work-orders/{WO_ID}.md 읽고 drafts/{WO_ID}.draft.md 신규 생성)는 폐기되었다.
> fanout 이 빈 셸을 미리 만들어두므로 write 는 그 셸을 in-place 수정한다.


## 전제조건 검사

1. `PROJECTS/{product}/drafts/{WO_ID}.draft.md` 가 존재하는지 확인한다.
   없으면 `/fanout {product}` 실행을 안내하고 중단한다.

2. **[status 분기 — 안 A 통합 schema]**
   대상 draft 의 frontmatter `status` 값을 확인한다:

   - `status: empty` → 정상 진입. write 가 본문 채우고 `status: ai-draft` 로 전환.
   - `status: ai-draft` → 사용자 확인 후 재작성 진행. 다음 경고 출력:
     ```
     ⚠️ 이 draft 는 이미 ai-draft 상태입니다 (이전 write 결과).
        재작성하면 기존 본문이 덮어쓰여집니다. 계속하시겠습니까? (Y/N)
     ```
   - `status: human-reviewed` → 거부. PM 승인 없이 수정 금지.
     `--force` 플래그가 명시되어야 진행. 그렇지 않으면 다음 안내 후 중단:
     ```
     ❌ 이 draft 는 PM 검토 완료 상태(human-reviewed)입니다.
        수정하려면 명시적으로 --force 플래그를 사용하세요.
     ```
   - `status: frozen` → 거부. v1.0 확정본은 직접 수정할 수 없다.
     새 DEC 등재 + 새 버전으로만 수정 가능. 다음 안내 후 중단:
     ```
     ❌ 이 draft 는 v1.0 확정(frozen) 상태입니다.
        수정하려면 decisions.md 에 새 DEC 를 등재하고 새 버전 draft 를 생성해야 합니다.
     ```
   - `status` 필드 누락 → 마이그레이션 권고 후 중단:
     ```
     ⚠️ frontmatter 에 status 필드가 없습니다 (안 A schema 이전 draft).
        다음 명령으로 마이그레이션 후 재실행하세요:
        python ${CLAUDE_PLUGIN_ROOT}/scripts/migrate_draft_frontmatter.py --hub-root . --product {product}
     ```
   - 파일 자체 부재 → `/fanout {product}` 미실행 권고 후 중단.

3. draft 파일의 frontmatter `type` 값을 읽는다.
   - `type: screen` → `/flow {product} {screen_id}` 실행을 안내하고 중단한다.
   - `type: cluster_draft` → `/write-cluster {product} {cluster_id}` 실행을 안내하고 중단한다.
     (Track A cluster draft 는 4패널 양식이라 본 skill(node policy)과 본문 구조가 다르다.)
   - `type: policy` → 계속 진행한다.

4. `PROJECTS/{product}/graph/graph.json` 을 읽어
   해당 WO_ID 노드의 다음 필드를 확인한다:
   - `delta_required` 값
   - `inherits_from` 목록 (상위 {PREFIX}-B doc_id 목록)
   - `includes` 목록 (참조할 {PREFIX}-C doc_id 목록)

5. `PROJECTS/{product}/decisions.md` 가 존재하는지 확인한다.
   없으면 PM에게 생성을 요청하고 중단한다.

6. `CONTEXT/layer-config.md` 에서 PREFIX를 읽고, `CONTEXT/reference-docs/{ACTIVE_PREFIX}/B/` 경로에서
   {PREFIX}-B 파일을 로드한다.


## 단계 1 — {PREFIX}-B 공통 정책 로드 (캐시 우선·섹션 발췌)

> **개선안 A·B (CONTEXT_OPTIMIZATION.md)** — 원문 전체 로드를 금지하고
> 캐시·인덱스 기반으로 필요한 섹션만 발췌 로드한다.

**로드 우선순위 (반드시 위에서부터 순서대로):**

1. **B-summary.md 캐시 (개선안 A)**
   - `CONTEXT/.template-cache/B-summary.md` 가 존재하고
     `CONTEXT/reference-docs/{ACTIVE_PREFIX}/B/*.md` 어떤 파일보다도 mtime 이 같거나 최신이면
     캐시만 로드하고 본 단계 종료.
   - 캐시 미존재 또는 stale → 다음 명령으로 갱신 후 재시도:
     `python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_cache.py --hub-root .`

2. **헤딩 인덱스 기반 섹션 발췌 (개선안 B)**
   - `CONTEXT/.template-cache/B-headings-index.json` 을 로드.
   - `graph.json` 의 `inherits_from` 항목에서 `section: "3.2"` 같은 명시값이 있으면
     해당 doc 의 `sections[]` 에서 `id == "3.2"` 항목을 찾아 `line_start` / `line_end` 추출.
   - `Read` 도구로 `offset=line_start`, `limit=(line_end - line_start + 5)` 만큼만
     **부분 로드** 한다. 원문 전체 로드는 사용 금지.
   - 인덱스가 stale 이면 `python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_index.py --hub-root .` 으로 갱신.

3. **fallback (캐시·인덱스가 모두 없는 경우만)**
   - `CONTEXT/reference-docs/{ACTIVE_PREFIX}/B/` 원문 직접 로드. 단, PM 에게 캐시 미생성을 보고하고
     `/init-hub` 재실행을 안내한다. 정상 운영 환경에서는 본 분기에 진입하면 안 된다.
   - 파일 자체가 없으면 `[{PREFIX}-B 파일 없음]` 안내 후 계속 진행.

**로드 결과를 다음 형식으로 출력한다:**

```
{PREFIX}-B 공통 정책 로드 완료 (캐시·발췌 모드)

  소스: .template-cache/B-summary.md (캐시) + B-headings-index.json (발췌 위치)

  이 WO({WO_ID})가 상속받는 섹션 (발췌 로드):
  - {PREFIX}-B-001 §3.2 리소스 한도 계산 방식 (line 142-197, 발췌 로드)
  - {PREFIX}-B-005 §2.1 기본 과금 단위         (line 88-119,  발췌 로드)
```

`includes` 목록의 {PREFIX}-C 문서도 동일한 캐시 우선·발췌 규칙으로 로드한다.


## 단계 2 — Delta 범위 사전 확인 (PM과 협의)

`delta_required` 값에 따라 분기한다.

### 2-A. delta_required: false 인 경우

```
⚠️ 이 노드는 delta_required: false 입니다.

  {WO_ID} ({문서 제목})는 {PREFIX}-B 공통 정책을 완전 적용합니다.
  별도 초안 내용이 필요하지 않습니다.

  초안 작성 시 내용:
  "기본 정책 완전 적용 — [{PREFIX}-B-NNN 문서 제목] 참조"

  이 한 줄짜리 초안을 생성할까요? (Y/N)
```

PM이 Y → 단계 5로 건너뛰어 한 줄 초안 파일 생성.
PM이 N → 이유를 확인하고 graph.json의 delta_required 수정 여부를 PM에게 안내.

### 2-B. delta_required: true 인 경우

**{PREFIX}-B 섹션별 항목 분류표를 작성한다:**

```
Delta 범위 사전 분석 — {WO_ID}

┌─────────────────────────────────────────────────────────────────┐
│ 상속 문서: {PREFIX}-B-NNN {문서 제목}                            │
│ 섹션: §{N}.{N} {섹션명}                                          │
├─────────────────────────────────────────────────────────────────┤
│ B-정책 내용 (초안에 재작성 금지):                                 │
│  · (핵심 조항 요약 — {PREFIX}-B 원문 기반)                        │
│  · ...                                                           │
├─────────────────────────────────────────────────────────────────┤
│ Delta 후보 (이 제품에서 달라지는 항목):                           │
│  · (requirements.md, decisions.md 기반으로 추출한 예외 후보)      │
│  · (미확인 항목은 [TBD] 태그)                                     │
└─────────────────────────────────────────────────────────────────┘
```

표 출력 후 PM에게 확인을 요청한다:

```
위 Delta 후보를 검토해주세요.

  추가할 항목이 있으면 말씀해주세요.
  제거할 항목이 있으면 번호로 알려주세요.
  확인 완료 후 초안 작성을 시작합니다.
```

PM 승인 없이 단계 3으로 진행하지 않는다.


## 단계 2-C — 충돌 가능 Delta 사전 등록

단계 2-B에서 확정된 Delta 항목 중
"{PREFIX}-B 규칙과 논리적으로 상충하는 항목"을 탐지한다.

**탐지 기준:**
- Delta 항목이 B-정책의 동일 대상(동작, 조건, 제한값 등)에 대해 다른 값을 정의하는 경우
- B-정책이 "금지"하는 동작을 Delta에서 허용하려는 경우
- B-정책의 임계값(timeout, limit 등)을 이 제품에서 변경하는 경우

**충돌 미탐지 시:** 단계 3으로 바로 진행한다.

**충돌 탐지 시:** PM에게 다음을 확인한다.

```
충돌 가능 항목이 발견되었습니다.

  · {Delta 항목명}
    충돌 근거: {PREFIX}-B-NNN §N.N "{B-정책 조항 요약}"과 상충
    충돌 유형: {값 변경 / 금지 동작 허용 / 조건 역전}

이 항목은 비즈니스 판단에 의한 의도적 예외입니까?

  [Y] decisions.md에 사전 등록 후 작성 계속
  [N] Delta 항목을 재검토한다 (단계 2-B로 돌아감)
  [S] 지금 결정하지 않고 [TBD]로 표기한 뒤 계속 진행
      (open-issues.md P1 등록, /integrate 전 해소 필요)
```

**[Y] 선택 시:**
`decisions.md` DEC 표에 후보 행을 자동 등재한다 (스키마: [[CONTEXT/dec-schema]]):
```markdown
| DEC-{NNN} | {MM-DD} | {도메인} | {Delta 항목명} — {PREFIX}-B-NNN §N.N 예외 ({근거 요약 60자}) | - | ⬜ | /write {WO_ID} |
```

- `DEC-{NNN}`: 표의 가장 큰 ID + 1 (3자리 0패딩)
- `도메인`: WO 도메인 매핑에서 자동 추정 (PM이 정정 가능)
- `핵심 결정` 셀에 충돌 대상 § + 근거 압축 표기
- `승인` 셀 = `⬜` (미승인). PM이 표 직접 편집 또는 `/dec-approve` 로 승인해야 정본 효력
- **integrator 처리**: I-03 위반 탐지 시 `승인=✅` 인 행만 정본으로 인정. `⬜` 는 INFO 분류

기록 완료 후 단계 3으로 진행한다.

**[S] 선택 시:**
해당 항목에 `[TBD:충돌미결]` 태그를 붙이고 진행한다.
open-issues.md P1 등록: `[WO_ID-충돌] {항목명} — 의도적 예외 여부 미결. /integrate 전 해소 필요`


## 단계 3 — {PREFIX}-A 어휘 기준 로드

`CONTEXT/reference-docs/{ACTIVE_PREFIX}/A/` 에서 {PREFIX}-A-001 (용어 사전) 파일을 로드한다.

로드 성공 시 → 이후 작성 단계에서 용어 대조에 사용한다.
로드 실패 시 → open-issues.md P2 등록 후 계속 진행.


## 단계 4 — policy 초안 작성

단계 2에서 PM이 확인한 Delta 범위만을 초안에 작성한다.

**작성 원칙 (절대 규칙):**

| 원칙 | 행동 |
|---|---|
| {PREFIX}-B 내용 재작성 금지 | `[{doc_id} 문서 제목] §NNN 참조` 한 줄로만 표기 |
| 예외 없으면 한 줄 처리 | `기본 정책 완전 적용 — [{doc_id} 문서 제목] 참조` |
| {PREFIX}-A 미등재 어휘 사용 금지 | 사용 시 `[TBD:{어휘}]` 태그 삽입 |
| decisions.md 위반 금지 | 상충 발견 시 `[정책 충돌 — {항목명}]` 태그 삽입 |
| C-PIN 핀 기록 | frontmatter `referenced_master` 에 Delta 기준 공통 `{핀ID}@{version}` 기재 (master-id-map.yml 권위 ID) |

**미결 태그 signal_type 분류 (작성 중 발견 즉시 분류):**

작성 중 삽입하는 미결 태그는 아래 3종 signal_type 으로 분류한다.
분류 결과를 단계 6 완료 보고의 `signal_type` 항목에 명기한다.

| signal_type | 태그 형식 | 발생 조건 | 귀결 |
|---|---|---|---|
| TERM_MISSING | `[TBD:{어휘}]` | `{PREFIX}-A` 용어 사전에 미등재된 어휘 사용 | {PREFIX}-A 보완 후보. open-issues.md P1 등록. 의미 B 신호 → PM 수동 인계 대상 |
| POLICY_GAP | `[확인 필요: B 누락 — {항목}]` | `{PREFIX}-B` 공통 정책에 있어야 하는데 해당 항목이 없음 | {PREFIX}-B 보완 후보. open-issues.md P1 등록. 의미 B 신호 → PM 수동 인계 대상 |
| DEFINITION_CONFLICT | `[정책 충돌 — {항목}]` | `{PREFIX}-B` 정의가 모순되거나 양립 불가한 경우 | 양쪽 보존. open-issues.md P0 등록. 의미 B 신호 → PM 수동 인계 대상 |

> **주의**: POLICY_GAP / TERM_MISSING / DEFINITION_CONFLICT 는 공통({PREFIX}-A/B)
> 보완이 필요한 **의미 B 신호**다. PM이 해당 부서 RE 담당자에게 직접 수동 인계한다.
> **reverse-signal-queue.md 등 자동 파일 신설 절대 금지** — 부서별 1:1 인계 모델 유지.
> 단순 내부 미결(의미 A)은 `[확인 필요: {내용}]` 으로 표기하고 open-issues.md P1/P0 처리로만 종결한다.

**signal_type 분류 결정 가이드 (의미 A vs 의미 B 판단 — γ-1):**

작성 중 미결 태그를 삽입할 때, 아래 3단계 판단을 순서대로 적용한다.

```
판단 1: 이 항목은 "이 제품(C) 범위 내 결정"인가, "공통(A/B) 차원 결정"인가?
  - 이 제품 범위에서 해소 가능 (예: 내부 플로우 확인, 개발팀 협의)
    → 의미 A (내부 미결) — [확인 필요: {내용}] 태그 + open-issues.md P0/P1 처리로 종결.
  - 공통(A/B) 정의가 있어야 해소 가능한 경우
    → 판단 2로 진행.

판단 2 (공통 차원 확정): 어느 공통가 보완되어야 하는가?
  - {PREFIX}-A 용어 사전에 해당 어휘가 없음
    → TERM_MISSING — [TBD:{어휘}] 태그. {PREFIX}-A 백필 후보.
  - {PREFIX}-B에 있어야 할 공통 정책 조항이 없음
    → POLICY_GAP — [확인 필요: B 누락 — {항목}] 태그. {PREFIX}-B 보완 후보.
  - {PREFIX}-B 정의 간 모순·양립 불가 상황
    → DEFINITION_CONFLICT — [정책 충돌 — {항목}] 태그. {PREFIX}-B 정의 정정 후보.

판단 3 (경계 모호): "이 항목을 부서 RE 담당자에게 보고했다고 가정 시 받아들일 만한
  정보(공통 보완 근거)인가?"
  - YES → 의미 B (signal_type 분류 적용, open-issues.md ## RE 인계 추적 등록)
  - NO  → 의미 A (내부 미결로 처리, open-issues.md P0/P1만 등록)
```

> 경계 판단이 어려우면 판단 3을 먼저 적용한다.
> 의미 A로 처리한 항목도 이후 맥락 변화로 의미 B로 재분류 가능 — open-issues.md 수정으로 처리.

**계산형(요금 산식) 제품 추가 규칙 (C2 — master-derivation-gate):**
- 요금 산식은 G2-B 상품요금결제정책 §B(수식 처리 원칙·할인 적용 순서·무료
  트래픽 일할) **파생**이며 재정의 금지 — 산식 본문에 G2-B §링크 병기.
- 산식 변수는 `inputs/spec-catalog.md` 의 **변수ID 만** 인용한다(자유 변수명 금지).
- 초안 작성 후 `graph/formula-binding.md`(템플릿: `templates/formula-binding-template.md`)
  를 갱신: 산식 변수 ↔ spec-catalog 필드 1:1 바인딩. UNBOUND 1건이라도 있으면
  자기 BLOCK(단계 5) → spec-catalog 보강 또는 산식 정정 후 재작성.
- 콘솔형(비산식) 제품은 본 규칙·formula-binding 비대상.

**초안 구조 (무손실·가변 섹션 — 골드스탠다드/critique 9축 기준):**

> **고정 8섹션(●◐○ 패턴) 방식은 폐기되었다.** 고정 섹션·"간략 기재/생략"이 원문 정책
> 사실을 대량 누락시켰다. 이제 **무손실 재구성 + 가변 섹션 라이브러리**를 따른다.

**무손실 원칙 (최우선 — 위반이 가장 큰 결함):**
- 원문/입력의 모든 정책 사실·수치·케이스·예외·UI 문구·표를 하나도 버리지 않는다.
  요약이 아니라 **구조 재배치**다. 어디에도 안 맞는 사실은 버리지 말고 마지막
  `## 부록 Z. 미분류 원문 사실`에 원문 그대로 이관한다.
- 분량을 이유로 축약·생략 금지("간략 기재" 같은 지시는 없다 — 표·중첩으로 다 담는다).
- 원문에 없는 내용 창작 금지. 불확실하면 `[확인 필요: {무엇}]`. 원문이 모순되면 한쪽을
  고르지 말고 `[정책 충돌 — {항목}]`으로 **양쪽 다 보존**한다.

섹션은 **가변 길이**다(고정 개수 아님). 원문 분량만큼 섹션·하위섹션을 늘린다.
{PREFIX}-B(공통)와 동일한 항목은 재작성하지 않고 `[{PREFIX}-B-NNN 문서 제목] §N 참조`
한 줄로만 표기한다(Delta+링크 SSoT 유지). 단가·요율·수치는 재기재 금지 —
`inputs/spec-catalog.md` 변수ID/§참조(C-RENDER 완전판이 자동 전개).

```markdown
---
doc_id: {WO_ID}
type: policy
version: draft
written_at: {UTC 타임스탬프}
inherits_from: [{PREFIX}-B-NNN, ...]
referenced_master: [{PREFIX}-B-NNN@{version}, {PREFIX}-A-001@{version}]
includes: [{PREFIX}-C-NNN, ...]
delta_required: true
pattern: {A|B|C}
---

**태깅**
**doc_id:** {WO_ID}
**version:** {버전}
**pattern:** {A|B|C}
**status:** draft
**owner:** 기획자

---

# {문서 제목}

> 본 문서는 {제품명}을 위한 정책정의서입니다.

---

## 메타 블록 (문서 최상단)

- **문서 설명** — 1~2문장 목적
- **목차** — 전체 섹션/하위섹션 목록
- **관련 기획 문서 / 참고 문서** — 알려진 링크 (없으면 `[확인 필요: 관련 문서]`)
- **개정 이력** — | 버전 | 일자 | 변경자 | 코멘트 |

---

## 1. 정책 개요

### 1-1. 목적
### 1-2. 적용 범위
### 1-3. 핵심 원칙
### 1-4. 용어 정의 (정본 표현)

| 정본 표현 | 정의 | 비정본(사용 금지) |
|---|---|---|
| (정본) | (정의) | (금지 동의어) |

> 본 표가 SSoT. 이후 본문·표·UI 문구는 정본 표현만 사용(동의어 혼용 금지 — critique AXIS-01/02).

---

## 2. 공통 정책

### 2-1. 상태 정의

전 상태 열거+정의. 콘솔 표시명 = 내부 코드 매핑 명시.

### 2-2. 상태별 허용 액션

| 상태 \ 액션 | (액션1) | (액션2) | … |
|---|---|---|---|
| (상태) | 허용/불가 | … | |

> 모든 상태 × 모든 액션 매트릭스. 실패 복귀 케이스 세분화(critique AXIS-09).

### 2-3. 권한별 접근 제어 / 역할 정의
### 2-4. (서비스 고유 공통 규칙)

---

## 3. 생성/신청 정책

### 3-1. 진입 조건 / 입력 항목·유효성

| 구분 | 항목 | 유효성 규칙·제한 | 비고 |
|---|---|---|---|
| (구분) | (항목) | (범위·형식·예약어) | |

### 3-2. 케이스별 처리 흐름

정상/실패/취소/타임아웃/0개/중복/동시 — **분기 전수**(critique AXIS-03).

### 3-3. 완료 처리

생성완료 = 실사용 가능 상태 여부 명시 + 다음 단계 유도(critique AXIS-05).

---

## 4. 삭제/해지 정책

### 4-1. 삭제 가능 조건
### 4-2. 삭제 처리 및 데이터 정리

Cascade/연쇄, 연관 자원 영향 범위.

---

## (선택 섹션 라이브러리 — 원문에 해당 내용 있으면 반드시 섹션 생성)

> 원문 기능 수만큼 섹션·하위섹션을 **추가**한다. 해당 없는 표준 섹션은 헤딩 유지 + `해당 없음 — {사유}` 한 줄.

- `## 핵심 운영 정책` — 서비스 본연 기능별(레코드·IP·스냅샷·파라미터그룹·스케일링 등). 원문 기능 수만큼 N-x 분할
- `## 위임·연동 정책` / `## 라우팅·네트워크 연동`
- `## 보안·트래픽 정책` — 마스킹·인증·민감정보(AXIS-08)
- `## 장애·복구 정책` — 간 상태·실패 복귀 케이스 세분화
- `## 상품·요금 정책` — 단위·연산·중도가입·해지·일할·위약금. 수치는 spec-catalog §참조, 산식 구조만(AXIS-07)
- `## 이벤트 로그 정책` — | 이벤트 | 내용 | 유형 | 출처(콘솔/API/자동) | 고객노출 |
- `## 알림(이메일/SMS) 발송 정책` — 발송 이벤트 목록 + **이벤트×상태별 메일 템플릿 명세**(제목/인사말/본문/유의사항/CTA + `{변수}`, 실제 문구 전수) + 미발송 이벤트
- `## 백오피스 정책` — 리스트 페이지 정책+컬럼 / 상세 페이지(영역별). 콘솔 정책과 정합
- `## 모니터링 정책` — 집계 단위·조회 항목
- `## 추후 고도화 고려사항` — BACKLOG(v2)

> **서비스 아키타입 힌트**(선택 섹션 가중 — 구조 강제 아님): 인프라형=단계별 Validation·어드민 수동제어 / 컴퓨팅형(AutoScale·LB)=상태머신 그룹·멤버 2단계·예약/임계치 분리 / 보안신청형=플로우 다이어그램·운영포털 API·수동 절차 / 스냅샷형=원본 doc_id 라이프사이클 강결합 / 컨테이너형=플랫폼 vs 고객 자원 경계·레지스트리>이미지>아티팩트.

---

## 인터페이스 바인딩 (해당 시)

상세 API 명세는 {PREFIX}-E. 본 절은 정책 관점 URL/포털 바인딩만(해당 없으면 헤딩+사유).

---

## 의존성 & 영향 범위

Upstream/Downstream을 **doc_id 기반**으로 명시. 연관 제품 담당자와 양방향 영향 교차 검증.

---

## 미결 사항

### P1 미결 — 협의 필요

| ID | 내용 | 확인 대상 | 관련 정책 |
|---|---|---|---|
| [TBD] | (내용) | (개발팀/사업부/보안팀) | §N |

### P2 미결 — 선택적 보완

(원문에 협의 추적 있으면) `## 미결 협의 항목 현황` — | No | 섹션 | 협의 항목 | 처리 상태 | 비고 |
(미분류 원문 사실 있으면) `## 부록 Z. 미분류 원문 사실` — 원문 그대로 보존

---

## Workflow Connections

관련 문서/다음 단계 [[링크]].

---
## 자기 검증 체크리스트

- [ ] 무손실: 원문 사실 전수 매핑(누락 0, 미분류는 부록 Z, 모순은 [정책 충돌] 양쪽 보존)
- [ ] {PREFIX}-B 내용 재작성 없음 — Delta + `[{PREFIX}-B-NNN] §N 참조` 링크만
- [ ] 1-4 용어 정의(정본 표현) 표 선언 + 이후 정본 표현만 사용
- [ ] 2-2 상태×액션 매트릭스 전 상태 커버 (critique AXIS-09)
- [ ] 3-2 케이스 분기 전수: 정상/실패/취소/타임아웃/0개/중복/동시 (AXIS-03)
- [ ] 수치·단가 재기재 없음 — spec-catalog 변수ID/§참조 (계산형: formula-binding UNBOUND 0건)
- [ ] frontmatter referenced_master 핀 기재 (빈 목록이면 decisions.md opt-out 근거)
- [ ] Delta 범위 PM 확인 완료
- [ ] {PREFIX}-A 어휘 기준 준수 (이탈 시 [TBD:] + open-issues P1)
- [ ] decisions.md 위반 없음 (충돌 시 [정책 충돌] + open-issues P0)
- [ ] 의존성 doc_id 기반 양방향 명시
- [ ] 미결 P1/P2 표 작성 + open-issues.md 연동
- [ ] critique 9축 자가 점검 통과 (미통과 시 보강 후 제출)
```

**작성 중 발견 항목 처리:**
- `[TBD:{어휘}]` 발생 → 작성 완료 후 open-issues.md P1 등록
- `[정책 충돌 — {항목명}]` 발생 → open-issues.md P0 등록 후 PM에게 즉시 보고


## 단계 4-B — 섹션 채움 지침 (안 A — work-order-template.md 통합 schema)

draft 본문에는 fanout 이 미리 삽입한 표준 섹션 골격이 존재한다
(`<Hub 루트>/templates/work-order-template.md` 의 `## 1.~7.` 번호 섹션 헤딩 —
Hub 작업 디렉토리 기준 상대경로. `${CLAUDE_PLUGIN_ROOT}` 아님).
본문 하단의 `<!-- wikilinks:start -->` … `<!-- wikilinks:end -->` 블록은
fanout 이 연결 WO 링크를 자동 채우는 영역이므로 write 가 임의로 손대지 않는다.

**섹션 채움 규칙:**

- 본문 작성 시 각 `## N. {섹션 제목}` 헤딩 아래에 정확히 콘텐츠를 채운다.
- **어떤 표준 섹션도 비워두지 말 것** — fanout 이 만든 모든 섹션을 채우는 것이
  의무다. 해당 섹션 내용이 원문에 없으면 `해당 없음 — {사유}` 한 줄로 채운다.
- `{{...}}` 형태의 미치환 플레이스홀더(예: `{SECTION_SUMMARY}`)가 남으면 안 된다 —
  전수 실제 콘텐츠로 치환한다.
- 템플릿 표준 섹션 외 추가 섹션은 자유롭게 추가 가능(무손실 원칙).


## 단계 5 — 자기 검증 수행

초안 작성 완료 후 다음 항목을 순서대로 검사한다.

| 검증 항목 | 기준 | 판정 |
|---|---|---|
| {PREFIX}-B 재작성 여부 | 상속 섹션 내용을 그대로 복사한 문단 탐지 | FAIL → 해당 문단 삭제 |
| Delta 선언 존재 | Section 0-2 작성 여부 | FAIL → 작성 후 재검증 |
| C-PIN 핀 존재 | frontmatter `referenced_master` 기재 여부 | FAIL → 핀 기재 후 재검증 (빈 목록=opt-out 은 decisions.md 근거 시 통과) |
| formula-binding (계산형) | `graph/formula-binding.md` UNBOUND 0건 | FAIL → spec-catalog 보강/산식 정정 (콘솔형 N/A) |
| TBD 항목 수 | 핵심 규칙 영역의 TBD | FAIL → P1 등록 |
| decisions.md 충돌 | 충돌 태그 수 | FAIL → P0 등록 |
| {PREFIX}-A 어휘 | 미등재 어휘 수 | WARN |
| 섹션 채움 누락 (안 A) | 템플릿 표준 섹션(`## 1.~7.`) 전부 작성 + `{{...}}` 플레이스홀더 0건 | FAIL → 빈 섹션 채움 / 플레이스홀더 제거 |
| [자기 검증] signal_type 분류 일치 | 각 미결 태그가 분류 결정 가이드(판단 1-2-3)와 일치하는가? 경계 모호 항목은 PM 재확인 후 분류 확정 | WARN → 불일치 시 PM 재확인 |


## 단계 5-B — frontmatter 갱신 (안 A — status 전환)

자기 검증 통과 후, draft 의 frontmatter 를 다음과 같이 갱신한다 (동일 파일 in-place 수정):

- `status: empty` → `status: ai-draft`
- `last_updated: {현재 ISO8601 타임스탬프}` (없으면 신규 추가, 있으면 갱신)
- `review_status: ai-draft` (유지 또는 신규 추가 — human-reviewed 로 자동 승격 금지)

> 본 단계는 `drafts/{WO_ID}.draft.md` 를 신규 생성하지 않는다. fanout 이 만든 셸을
> in-place 수정하는 것이 안 A 핵심이다.


## 단계 6 — 완료 보고 및 session-log 기록

```
/write 완료 — {WO_ID}

  초안 위치: drafts/{WO_ID}.draft.md
  Delta 항목 수: {N}개
  TBD 항목: {N}건 (open-issues.md P1 등록)
  정책 충돌: {N}건 (open-issues.md P0 등록)
  {PREFIX}-B 재작성: 0건 ✅

  signal_type 요약:
    TERM_MISSING:        {N}건  → {PREFIX}-A 보완 후보 (PM 수동 인계 대상)
    POLICY_GAP:          {N}건  → {PREFIX}-B 보완 후보 (PM 수동 인계 대상)
    DEFINITION_CONFLICT: {N}건  → {PREFIX}-B 정의 정정 후보 (PM 수동 인계 대상)
    내부 미결(의미 A):    {N}건  → open-issues.md 처리로 종결

  의미 B 신호 부서 RE 인계 추적 (γ-2):
    의미 B 합계: {N}건
    {N > 0} → open-issues.md ## RE 인계 추적 섹션에 RH-NNN 행 등록 완료
    {N = 0} → 의미 B 신호 없음 (공통 정합 확인 ✅)
    ※ 실제 인계는 PM이 부서 RE 담당자에게 직접 수동 전달. 자동 sync 없음.

다음 단계: /review drafts/{WO_ID}.draft.md
```

session-log.md 에 추가한다:
```markdown
- {날짜} /write {WO_ID}: policy 초안 생성 / Delta {N}개 / TBD {N}건 / 충돌 {N}건
```


## 결과 파일 목록

| 파일 | 내용 |
|---|---|
| `drafts/{WO_ID}.draft.md` | Delta 전용 policy 초안 |
| `open-issues.md` | TBD (P1) / 정책 충돌 (P0) / {PREFIX}-B 미로드 (P1) / RE 인계 추적 (의미 B 신호) |
| `session-log.md` | 작성 요약 기록 |

**open-issues.md 표준 섹션 구조 (write 스킬 산출 기준):**

기존 P0/P1 섹션은 그대로 유지한다. 의미 B 신호가 1건 이상 발생한 /write 실행 시,
아래 섹션을 `open-issues.md` 말미에 추가(없으면 신규 생성, 있으면 행 추가)한다.

```markdown
## RE 인계 추적 (의미 B 신호)

> 이 섹션은 공통({PREFIX}-A/B) 보완이 필요한 의미 B 신호를 PM이 수동으로 추적하는 공간이다.
> 자동 sync 없음 — PM이 부서 RE 담당자에게 직접 인계 후 상태를 수기 갱신한다.
> 의미 A(내부 미결) 항목은 기존 P0/P1 섹션에서 처리하고 이 섹션에 등록하지 않는다.

| signal_id | signal_type | 발견 컨텍스트 | 공통 도메인 | 인계 상태 | 인계일 | 공통 반영 확인일 |
|---|---|---|---|---|---|---|
| RH-001 | POLICY_GAP | {WO_ID} draft §{섹션번호} | {PREFIX}-B.{도메인} | ⬜ 미인계 | - | - |
```

**signal_id 규칙**: `RH-NNN` (Reverse Handoff, 3자리 순번 — 프로젝트 전체 연번)

**인계 상태 열거형 (PM 수기 갱신):**
- `⬜ 미인계` — 아직 부서 RE에 전달하지 않은 상태 (기본값)
- `🟡 인계됨` — PM이 부서 RE 담당자에게 전달 완료 (인계일 기재)
- `✅ 공통 반영` — RE가 {PREFIX}-A/B 공통에 반영 확인 (공통 반영 확인일 기재)

의미 B 신호가 0건인 경우 이 섹션을 생성하지 않는다(또는 기존 섹션에 행 추가 없음).


## 다음 단계

```
/review drafts/{WO_ID}.draft.md
```
