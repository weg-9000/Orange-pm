---
name: flow
description: screen-list.md와 screen WO 템플릿을 기반으로 화면별 인터랙션 시퀀스(4-state)와 마이크로카피를 생성하고 screen WO draft 파일을 작성한다. 작성 전 {PREFIX}-B 공통 정책을 로드하고 Delta 범위를 PM과 확인한다. 공통 정책 내용은 재작성하지 않고 참조 링크로만 표기한다. {screen_id} 지정 시 해당 화면만 단독 처리한다. --sketch 플래그 사용 시 전제조건 검사를 생략하고 자유 스케치 모드로 실행한다.
triggers:
  - "flow"
  - "write screen"
  - "interaction sequence"
  - "스케치"
  - "sketch screen"
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


## 공통 참조 가드 (C0·C-PIN·C3 — gates/master-derivation-gate.md SSoT)

screen draft 작성 전 적용(--sketch 모드는 제외). 상세는 `CONTEXT/gates/master-derivation-gate.md`.

1. 공통 대조: G2-A/B 에 이미 있는 정책은 재작성 금지 — `[{doc_id} §X] 참조`
   링크로만(B-headings-index 후보 §만, 원문 전체 로드 금지 — 토큰 경계).
2. C-PIN: draft frontmatter `referenced_master: [{핀ID}@{version}]` 핀
   (master-id-map.yml 권위 ID). 비우면 opt-out → decisions.md 근거 필수.
3. screen 재기재 self-check (C3): 정책·산식·약정율·입력 유효성은 본문 재기재
   금지 → 정책 참조는 `[[POL §X-Y]]` **표준 마커만**(비표준 표기 금지),
   입력은 `[[spec-catalog 변수ID]]`. 재기재 탐지 시 self-check FAIL.
4. C-PIMPACT: frontmatter `referenced_policy: {POL doc_id}@{version}` 핀
   기재(WP8-1 표준). 정책 §변경 시 policy_impact_scan 이 이 핀·`[[POL §]]`
   마커로 영향 화면 §단위 식별(reviewer V-17·policy-impact-gate).
5. PM 확인은 기존 Delta/내용 확인 단계에 통합(직렬 프롬프트 추가 금지).


## 입출력 (안 A — WO 템플릿 ↔ draft 1-파일화)

- **입력**: `PROJECTS/{product}/drafts/{WO_ID}.draft.md`
  (fanout 단계에서 생성된 빈 셸 — frontmatter `status: empty`, `type: screen`,
  본문에 `## 1.~7.` 표준 섹션 골격 포함 — 작업 지시 섹션에 인터랙션 시퀀스(4-state)·마이크로카피 작성 요구사항 + `<!-- wikilinks:start/end -->` 블록)
- **출력**: `PROJECTS/{product}/drafts/{WO_ID}.draft.md`
  (**동일 파일 수정** — `status: empty → ai-draft`, 표준 섹션 골격을 콘텐츠로 채움)

> 이전 명세(work-orders/{WO_ID}.md 읽고 drafts/{WO_ID}.draft.md 신규 생성)는 폐기되었다.
> fanout 이 빈 셸을 미리 만들어두므로 flow 는 그 셸을 in-place 수정한다.
> 본 입출력 명세는 정식 실행 모드에만 적용된다 — `--sketch` 모드는 sketches/ 별도 경로 유지.


## --sketch 모드 분기

`--sketch` 플래그가 있으면 아래 전제조건 검사(1~5번) 전체를 건너뛰고
이 섹션의 절차만 실행한다.

### sketch 전제조건
`{screen_id}` 인수가 필수다. 없으면 PM에게 화면명(또는 임시 ID)을 입력받는다.
임시 ID 형식: `SKT-NNN` (001부터 순번, 기존 SCR-NNN과 충돌하지 않음)

### sketch 실행
1. `sketches/` 디렉토리가 없으면 생성한다.
2. `sketches/{screen_id}.sketch.md` 파일을 생성한다.
   - graph.json, WO, decisions.md 참조 없이 PM이 제공하는 내용만 기록한다.
   - B-정책 검증, Delta 확인, 어휘 검증을 수행하지 않는다.
3. 파일 헤더:
   ```markdown
   ---
   sketch_id: {screen_id}
   status: sketch
   promoted: false
   created_at: {UTC 타임스탬프}
   note: 이 파일은 정식 draft가 아닙니다. /promote {screen_id}로 전환하세요.
   ---
   ```
4. PM이 자유롭게 화면 아이디어, 인터랙션 흐름, 마이크로카피 초안을 작성하도록 안내한다.
   구조 강제 없음 — 4-state 형식을 따르지 않아도 된다.

### sketch 완료 안내
```
스케치 저장 완료: sketches/{screen_id}.sketch.md

이 파일은 /review, /integrate 검증 대상에서 제외됩니다.
/lc 게이트 계산 시 draft 완료율에 포함되지 않습니다.

정식 draft로 전환하려면:
  /promote {screen_id}   (graph.json과 WO가 준비된 후 실행)
```

sketch 모드는 여기서 종료한다. 이후 전제조건 검사 및 정식 실행 단계로 진행하지 않는다.

---
## 전제조건 검사

1. `PROJECTS/{product}/graph/screen-list.md`가 존재하는지 확인한다.
   없으면 `/graph-gen {product}` 재실행을 안내하고 중단한다.

2. `work-orders/index.md`에서 `type: screen`인 WO 목록을 읽는다.
   screen WO가 0건이면 `/fanout {product}` 재실행을 안내하고 중단한다.

3. `decisions.md`가 존재하는지 확인한다.
   없으면 PM에게 decisions.md 생성을 요청하고 중단한다.

4. `CONTEXT/layer-config.md`에서 PREFIX를 읽는다.
   `CONTEXT/reference-docs/{ACTIVE_PREFIX}/A/` 에서 `{PREFIX}-A` 어휘 기준서 파일을 로드한다.
   없으면 어휘 검증 없이 진행하고 open-issues.md에 P2로 등록한다.

5. `{screen_id}` 인수가 있으면 해당 Screen ID가 screen-list.md에 존재하는지 확인한다.
   없으면 유효한 Screen ID 목록을 출력하고 중단한다.

6. **[status 분기 — 안 A 통합 schema]**
   처리 대상 각 screen WO 의 `drafts/{WO_ID}.draft.md` 파일과 frontmatter `status` 값을
   다음 기준으로 판정한다 (단계 1 에서 WO 별로 적용):

   - `status: empty` → 정상 진입. flow 가 본문 채우고 `status: ai-draft` 로 전환.
   - `status: ai-draft` → 사용자 확인 후 재작성 진행. 다음 경고 출력:
     ```
     ⚠️ 이 draft 는 이미 ai-draft 상태입니다 (이전 flow 결과).
        재작성하면 기존 본문이 덮어쓰여집니다. 계속하시겠습니까? (Y/N)
     ```
   - `status: human-reviewed` → 거부. PM 승인 없이 수정 금지.
     `--force` 플래그가 명시되어야 진행. 그렇지 않으면 다음 안내 후 해당 WO 건너뜀:
     ```
     ❌ 이 draft 는 PM 검토 완료 상태(human-reviewed)입니다.
        수정하려면 명시적으로 --force 플래그를 사용하세요.
     ```
   - `status: frozen` → 거부. v1.0 확정본은 직접 수정할 수 없다.
     새 DEC 등재 + 새 버전으로만 수정 가능. 다음 안내 후 해당 WO 건너뜀:
     ```
     ❌ 이 draft 는 v1.0 확정(frozen) 상태입니다.
        수정하려면 decisions.md 에 새 DEC 를 등재하고 새 버전 draft 를 생성해야 합니다.
     ```
   - `status` 필드 누락 → 마이그레이션 권고 후 해당 WO 건너뜀:
     ```
     ⚠️ frontmatter 에 status 필드가 없습니다 (안 A schema 이전 draft).
        다음 명령으로 마이그레이션 후 재실행하세요:
        python ${CLAUDE_PLUGIN_ROOT}/scripts/migrate_draft_frontmatter.py --hub-root . --product {product}
     ```
   - 파일 자체 부재 → `/fanout {product}` 미실행 권고 후 해당 WO 건너뜀.

   단일 모드(`{screen_id}` 지정) 에서는 대상 WO 1 개만 검사 후 거부 시 중단.
   전체 모드에서는 거부된 WO 를 스킵 카운트에 추가하고 다음 WO 로 진행.


## 실행 단계

### 단계 1 — 처리 대상 screen WO 목록 확정

`{screen_id}` 지정 시 → 해당 WO 1개만 처리.
미지정 시 → `work-orders/index.md`에서 screen WO 전체를 읽는다.

**안 A 분기 적용:** 전제조건 6번의 status 분기 규칙을 WO 별로 적용해
처리 가능(`empty` 또는 사용자 승인된 `ai-draft`/`--force human-reviewed`) WO 만
실제 처리 대상으로 확정한다. 기존의 "drafts 존재 시 건너뜀" 규칙은
status 분기로 흡수되었다 (status 값으로 판정).

처리 대상 WO 수와 스킵된 WO 수(사유별)를 출력하고 PM에게 시작 확인을 받는다.


### 단계 2 — 화면별 컨텍스트 수집

각 screen WO에 대해 다음 소스에서 컨텍스트를 수집한다:

**screen-list.md 항목 읽기:**
- Screen ID, 화면명, 목적, 연결 REQ-NNN ID, 연관 policy WO ID

**연관 policy WO draft 참조:**
- `drafts/{policy_WO_ID}.draft.md`가 존재하면 내용을 읽는다.
- 해당 policy 섹션의 핵심 규칙과 제약 조건을 추출한다.
- draft 미존재 시 `work-orders/{policy_WO_ID}.md`의 섹션 요약을 대신 사용한다.

**{PREFIX}-B 공통 정책 참조 (캐시 우선·발췌 모드):**

> 개선안 A·B (CONTEXT_OPTIMIZATION.md) — 원문 전체 로드 금지.

1. 연관 policy WO 의 `inherits_from` 목록과 `section` 값을 읽는다.
2. **B-summary.md 캐시 (개선안 A)**: `CONTEXT/.template-cache/B-summary.md` 가
   원본보다 새로우면 캐시만 로드. stale / 미존재 시
   `python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_cache.py --hub-root .` 으로 갱신.
3. **헤딩 인덱스 발췌 (개선안 B)**: `CONTEXT/.template-cache/B-headings-index.json`
   에서 해당 doc_id 의 sections 중 명시된 section.id 항목의 `line_start` / `line_end` 를
   추출해 `Read offset=line_start limit=(line_end - line_start + 5)` 로 발췌 로드.
4. fallback (캐시·인덱스 모두 없음): `[{PREFIX}-B 캐시 미생성 — /init-hub 재실행 권장]`
   안내 후 `CONTEXT/reference-docs/{ACTIVE_PREFIX}/B/` 원문 로드. 파일 자체가 없으면
   `[{PREFIX}-B 파일 없음 — 공통 정책 참조 생략]` 후 진행.
5. 로드한 섹션에서 이 화면과 관련된 공통 정책 조항만 추출한다.
6. 추출한 항목은 **화면 초안에 재작성하지 않는다** — 참조 링크로만 표기.
7. 모든 경로 실패 시 open-issues.md P1 등록 후 계속 진행.

**decisions.md 관련 결정 추출:**
- 해당 화면명 또는 REQ-NNN과 관련된 결정 항목을 읽는다.

**requirements.md 해당 REQ-NNN 항목 읽기:**
- Layer 1 FR 항목에서 사용자 행동 기준 기능 단위 텍스트를 읽는다.


### 단계 2-B — Delta 사전 확인

단계 2 수집 완료 후, 화면 초안 작성 전에 Delta 범위를 PM과 확인한다.

다음 표를 출력한다:

```
Delta 사전 확인 — {Screen ID} {화면명}

┌─────────────────────────────────────────────────────────────────┐
│ 공통 정책 적용 항목 (화면 초안에 재작성 금지)                    │
│  출처: {PREFIX}-B-NNN §N.N                                       │
│  · (공통 정책 조항 요약)                                         │
│  → 초안 표기: [{PREFIX}-B-NNN] §N.N 참조                        │
├─────────────────────────────────────────────────────────────────┤
│ 이 화면 전용 Delta 항목 (초안에 직접 작성)                       │
│  · (requirements.md / decisions.md 기반 화면 고유 동작)          │
│  · [TBD] 태그: 확인이 필요한 항목                                │
└─────────────────────────────────────────────────────────────────┘
```

PM 확인 없이 단계 3으로 진행하지 않는다.
PM이 Delta 항목을 추가하거나 제거하면 표를 갱신한 뒤 작성을 시작한다.


### 단계 3 — 4-state 인터랙션 시퀀스 작성

각 화면에 대해 다음 4개 상태를 정의한다.
연관 policy WO의 규칙이 각 상태 정의에 반영되어야 한다.

**idle 상태:**
- 진입 조건 (어떤 사용자가, 어떤 경로로)
- 초기 UI 구성 (표시되는 정보, 활성화된 버튼)
- 이탈 방법 (취소, 뒤로가기, 외부 이탈)

**loading 상태:**
- 트리거 조건 (어떤 액션이 loading을 발생시키는지)
- UI 변화 (스피너, 스켈레톤, 버튼 비활성화 등)
- 타임아웃 처리 기준 (decisions.md에 있으면 그 값 사용, 없으면 TBD)

**success 상태:**
- 결과 표시 방식
- 다음 액션 목록 (다음 화면 이동, 재시작, 완료 처리)
- 성공 메시지 텍스트 (단계 4에서 마이크로카피로 작성)

**error 상태:**
- 오류 유형 목록 (인증 오류, 권한 오류, 서버 오류, 입력값 오류 등 화면 특성에 맞게)
- 각 오류 유형별 복구 방법
- 오류 메시지 텍스트 + `{PREFIX}-A` 오류코드 (단계 4에서 작성)

이탈·취소·뒤로가기 흐름을 별도 항목으로 정의한다.


### 단계 4 — 마이크로카피 작성

각 화면의 UI 텍스트 요소를 작성한다.

**작성 규칙:**
- 동일 화면 내 버튼 레이블 중복 금지
- `brand-voice.md`가 존재하면 톤앤매너 기준 적용
  (없으면 공식적·간결체 기본 적용, open-issues.md P2 등록)
- `{PREFIX}-A` 등재 어휘 사용 필수 (용어 이탈 시 TBD 태깅)

**작성 항목:**

| 요소 | 내용 |
|---|---|
| 버튼 레이블 | 주요 액션 버튼 전체 (취소·확인 포함) |
| 입력 필드 | 플레이스홀더 + 인라인 안내 문구 |
| 성공 메시지 | success 상태 피드백 텍스트 |
| 오류 메시지 | 오류 유형별 메시지 + `{PREFIX}-A` 오류코드 |
| 툴팁 | 사용자가 물음표/? 아이콘 클릭 시 표시될 설명 텍스트 |
| 빈 상태(empty state) | 데이터 없을 때 표시될 제목 + 안내 문구 |


### 단계 5 — screen WO draft 파일 본문 채움 (무손실·골드스탠다드 구조)

`drafts/{WO_ID}.draft.md` (fanout 이 만든 빈 셸)을 **in-place 수정** 한다.
신규 파일을 생성하지 않는다 — 안 A 통합 schema 핵심.

frontmatter 의 다음 필드를 갱신·확인한다 (없으면 추가, 있으면 갱신):
```markdown
version: draft
screen_id: {Screen ID}
written_at: {UTC 타임스탬프}
policy_ref: {연관 policy WO ID}
req_ref: {REQ-NNN}
binding_policy: 화면 소유 콘텐츠(레이아웃·4-state·마이크로카피·안내 문구·종속 목록)는
  실제 텍스트로 해소. 정책 수치·산식만 정책서 §X-Y / spec-catalog 참조(drift 차단).
```

> 본 단계는 `drafts/{WO_ID}.draft.md` 를 신규 생성하지 않는다. fanout 이 만든 셸을
> in-place 수정하는 것이 안 A 핵심이다. `status` 전환은 단계 6 에서 처리한다.

**draft 본문 구조 (무손실 — 원문 화면 사실 전수, 가변):**
- `## 화면 흐름 전체 구조` — 화면 간 진입·전이 흐름(텍스트 플로우/표). User Journey 시작점.
- 화면별 `# 화면 N. {화면명}` 반복(원문 화면 수만큼, 누락 금지):
  - `## N.1 레이아웃` — 영역 구성·치수(컨테이너/컬럼/헤더 등 실제 규격, 모르면 `[확인 필요:]`)·컴포넌트 배치
  - `## N.x {기능 영역}별 상세` — 동작·규칙·분기·노출 조건. 정책 수치는 `정책서 §X-Y 참조`
  - `## N.x 모달·팝업·확인창` — 각 모달 별도: 트리거·레이아웃·버튼·문구. 삭제 모달은 영향 자원·결과 명시
  - `## N.x 4-State` — idle/loading/success/error (단계 3 결과)
  - `## N.x 마이크로카피 (실제 문구)` — | 요소 | 문구 | 실제 문자열 전수(단계 4 결과, 토큰 금지)
- `# 부록 A. 정책 수치·산식 참조 인덱스` — | 참조 항목(수치/산식만) | 정본(정책서 §·spec-catalog) |
- `# 부록 B. 미결 항목` — | ID | 내용 | 담당 | (해소는 `~~ID~~` 취소선 + 해소 근거·일자)

자기 검증 체크리스트를 작성 완료 기준으로 채운다:
- 무손실: 원문 화면 사실 전수 매핑 (누락 0, 미분류는 `부록 Z`, 모순은 `[정책 충돌]` 양쪽 보존) → 확인
- screen-list.md 항목 일치 / 화면 누락 0 → 확인
- 화면 흐름 전체 구조 작성 → 확인
- 화면마다 4-state 정의 완료 → 확인
- 마이크로카피 전 항목 실제 문구 작성(플레이스홀더 토큰 금지) → 확인
- 부록 A 정책 수치·산식 참조 인덱스 / 부록 B 미결 작성 → 확인
- {PREFIX}-B 공통 정책·정책 수치 재작성 없음 (참조 링크로만 표기) → 확인
- Delta 범위 PM 확인 완료 → 확인
- 섹션 채움 누락 (안 A): 템플릿 표준 섹션(`## 1.~7.`) 전부 작성 + `{{...}}` 미치환 플레이스홀더 0건 → 확인
- 4-state 채움 의무: idle/loading/success/error 모두 채움(또는 정당한 N/A 사유 명시) → 확인
- 정책 참조 표기: 공통 정책 인용에 `[[POL §X-Y]]` 표준 마커만 사용 → 확인
- TBD 항목이 있으면 체크 해제 유지 + open-issues.md P1 등록

작성 중 decisions.md 규칙과 충돌하는 내용 발견 시
`[정책 충돌 — {decisions.md 항목명}]` 태그를 삽입하고
open-issues.md에 P1으로 등록한다.


### 단계 5-B — 섹션 채움 지침 (안 A — work-order-template.md 통합 schema)

draft 본문에는 fanout 이 미리 삽입한 표준 섹션 골격이 존재한다
(`<Hub 루트>/templates/work-order-template.md` 의 `## 1.~7.` 번호 섹션 헤딩 —
Hub 작업 디렉토리 기준 상대경로(`${CLAUDE_PLUGIN_ROOT}` 아님) —
할당 범위·참조 계약·작업 지시(인터랙션 시퀀스/마이크로카피)·자기 검증 등).
본문 하단의 `<!-- wikilinks:start -->` … `<!-- wikilinks:end -->` 블록은
fanout 이 연결 WO 링크를 자동 채우는 영역이므로 flow 가 임의로 손대지 않는다.

**섹션 채움 규칙:**

- 본문 작성 시 각 `## N. {섹션 제목}` 헤딩 아래에 정확히 콘텐츠를 채운다.
- **어떤 표준 섹션도 비워두지 말 것** — fanout 이 만든 모든 섹션을 채우는 것이
  의무다. 해당 섹션 내용이 원문에 없으면 `해당 없음 — {사유}` 한 줄로 채운다.
- `{{...}}` 형태의 미치환 플레이스홀더(예: `{PURPOSE}`)가 남으면 안 된다 —
  전수 실제 콘텐츠로 치환한다.
- 템플릿 표준 섹션 외 추가 섹션(원문 화면 수에 따른 가변 섹션)은
  자유롭게 추가 가능(무손실 원칙).

**4-state 채움 의무 (`## 4. 작업 지시` 인터랙션 시퀀스 항목):**

- idle / loading / success / error 4 개 상태를 모두 채운다.
- 화면 특성상 특정 상태가 발생하지 않는 경우(예: 비동기 호출이 없어 loading 불필요)에 한해
  `해당 없음 — {정당한 사유}` 표기를 허용한다 (예: "이 화면은 정적 표시 전용, 비동기 호출 없음").
- 4-state 미충족(상태 누락 + 사유 없음) 은 단계 6 자기 검증에서 FAIL.

**정책 참조 표기 (공통 정책 인용 항목):**

- 공통 정책 인용은 `[[POL §X-Y]]` **표준 마커만** 사용한다 (비표준 표기 금지).
- 정책 수치·산식은 본문 재기재 금지 — 정책서 §참조 또는 `[[spec-catalog 변수ID]]`.
- C-PIMPACT: frontmatter `referenced_policy: {POL doc_id}@{version}` 핀 기재(WP8-1 표준).


### 단계 5-C — frontmatter 갱신 (안 A — status 전환)

자기 검증 통과 후, draft 의 frontmatter 를 다음과 같이 갱신한다 (동일 파일 in-place 수정):

- `status: empty` → `status: ai-draft`
  (재작성 케이스에서는 `ai-draft` 유지)
- `last_updated: {현재 ISO8601 타임스탬프}` (없으면 신규 추가, 있으면 갱신)
- `review_status: ai-draft` (유지 또는 신규 추가 — human-reviewed 로 자동 승격 금지)

> 본 단계는 `drafts/{WO_ID}.draft.md` 를 신규 생성하지 않는다. fanout 이 만든 셸을
> in-place 수정하는 것이 안 A 핵심이다.


### 단계 6 — 완료 보고 및 session-log 기록

처리된 WO별 결과를 테이블로 출력한다:
```
| WO ID | Screen ID | 화면명 | TBD 항목 | 정책 충돌 | 결과 |
```

session-log.md에 추가한다:
```markdown
- {날짜} /flow: screen WO {N}개 draft 생성 / TBD {N}건 / 정책 충돌 {N}건
```


## 결과 파일 목록

| 파일 | 내용 |
|---|---|
| `drafts/{WO_ID}.draft.md` (screen 유형) | 화면 흐름·레이아웃·4-state·마이크로카피·부록 A/B 포함 draft (무손실·가변, fanout 셸 in-place 수정 — status: empty → ai-draft) |
| `open-issues.md` | TBD / 정책 충돌 / brand-voice 미등록 P1/P2 |
| `session-log.md` | screen draft 생성 요약 기록 |


## 다음 단계

각 screen draft에 대해: `/review drafts/{WO_ID}.draft.md`
전체 WO(policy + screen) 완료 시: `/integrate {product}`
