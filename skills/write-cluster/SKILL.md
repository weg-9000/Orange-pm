---
name: write-cluster
description: >-
  cluster draft(Track A · type cluster_draft)의 4패널(§1 정책결정 / §2 화면설계 / §3 데이터·의존성 / §4 Open Questions)을 무손실 원칙으로 작성한다. 패널 골격은 고정(transpose 라우팅 계약 §1→D2 정책정의서·§2→D3 화면설계서), 패널 내부 내용은 원문 사실 전수 가변. publication-syntax 준수(`::: {.panel}`·색상 cycling 자동)와 lint·round-trip 검증을 거친다. node policy WO 는 /write, screen WO 는 /flow 를 사용한다.
triggers:
  - "write cluster"
  - "cluster 작성"
  - "클러스터 초안"
  - "write-cluster"
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


## 적용 범위 — Track A cluster 작업 단위

본 skill 은 `type: cluster_draft` 인 `drafts/cluster_{cluster_id}.draft.md` 한 개를
in-place 작성한다. cluster 모드는 screen WO 트랙을 폐기(Phase 5I)하고 §2 가 화면
설계를 책임지므로, **한 cluster draft 가 정책(§1)·화면(§2)을 함께** 담는다.

- 양식 SSoT: `orange-pm-plugin/templates/standard/cluster-draft.md`,
  `orange-pm-plugin/skills/render/publication-syntax.md`,
  `orange-pm-plugin/skills/render/publication-map.md`(transpose 매핑).
- node policy WO(`type: policy`)는 `/write`, node screen WO(`type: screen`)는 `/flow`.


## 설계 원칙 — 고정 골격 + 가변 내용 (가장 중요)

| 층위 | 고정/가변 | 규칙 |
|---|---|---|
| 양식(syntax) | **고정** | `::: {.panel section="..."}` 펜스드 div. 색상 span 수기 금지(자동 cycling). lint 강제 |
| 골격(핵심 4패널) | **고정** | §1 정책결정 / §2 화면설계 / §3 데이터·의존성 / §4 OQ. transpose 라우팅 계약(§1→D2·§2→D3·§3§4 publish 제외)이라 절대 변경 금지 |
| §α 기술 패널 | **선택** | §α-API/§α-DB/§α-MIG → Dα. 해당 기술 deliverable 있을 때만 추가, 없으면 삭제(유일하게 추가·삭제 허용되는 패널) |
| 목차(deliverable TOC) | 파생 | D2/D3 챕터는 publication-map 이 cluster 구성에서 자동 조립(capability 알파벳→cluster_id 순). 본 skill 이 손대지 않음 |
| 내용(패널 내부) | **가변** | doc-layer-schema 무손실 재구성 원칙. 하위 섹션(§1-1 등)은 권장 기본값일 뿐, 원문 정책/화면 사실 분량만큼 가변 확장. 빈 표 억지 채움·사실 생략 금지 |

> **무손실 원칙(최우선)**: 원문/입력의 모든 정책 사실·수치·케이스·예외·UI 문구·표를
> 하나도 버리지 않는다. 어디에도 안 맞는 사실은 §3 말미 `### 미분류 원문 사실` 에 원문
> 그대로 보존. 창작 금지 → `[확인 필요: {무엇}]`. 원문 모순 → `[정책 충돌 — {항목}]` 양쪽 보존.


## 공통 참조 가드 (C0·C-PIN·C-PIMPACT — gates/master-derivation-gate.md SSoT)

작성 전 적용한다.

1. **B 재작성 금지**: G2-A/B 에 이미 있는 정책은 `B-headings-index.json` 으로 후보 §만
   식별(원문 전체 로드 금지). 이미 있으면 `[{doc_id} §X] 참조` 링크로만. 본문 재출력은
   render_assemble(C-RENDER)가 완전판에서 인라인 전개한다.
2. **A 어휘 준수**: `CONTEXT/reference-docs/{ACTIVE_PREFIX}/A/` G2-A-001 용어 사전 기준. 미등재 어휘는
   `[TBD:{어휘}]` 태그(작성 후 open-issues.md P1).
3. **수치·산식 비재기재**: 단가·요율·임계값은 `inputs/spec-catalog.md` 변수ID 참조
   (`[[spec-catalog {변수ID}]]`). 산식은 G2-B 상품요금결제정책 §파생 — 구조만, §링크 병기.
4. **C-PIN**: frontmatter `inherits_from` / (있으면) `referenced_master` 에 Delta 기준
   공통 핀. master-id-map.yml 권위 ID.
5. **C-PIMPACT**: §1 정책 §를 §2 화면이 참조할 때 `[[POL §X-Y]]` 표준 마커만 사용.


## 입출력

- **입력**: `PROJECTS/{product}/drafts/cluster_{cluster_id}.draft.md`
  (fanout --cluster-mode 가 만든 셸 — frontmatter `status: empty`, `type: cluster_draft`,
  본문에 `::: {.panel}` 4패널 스캐폴딩 + `{{...}}` placeholder 포함)
- **출력**: 동일 파일 in-place 수정 (`status: empty → ai-draft`, placeholder 를 실제
  내용으로 치환, 패널 골격·`section=` 속성 보존)


## 전제조건 검사

1. `drafts/cluster_{cluster_id}.draft.md` 존재 확인. 없으면
   `/fanout {product} --cluster-mode`(+ 선행 `cluster_identify.py`) 안내 후 중단.

2. frontmatter `type` 확인:
   - `type: cluster_draft` → 진행.
   - `type: policy` → `/write {WO_ID}` 안내 후 중단.
   - `type: screen` → `/flow {product} {screen_id}` 안내 후 중단.

3. **status 분기 (안 A 라이프사이클 — /write 와 동일 규칙):**
   - `empty` → 정상 진입. 작성 후 `ai-draft` 전환.
   - `ai-draft` → 재작성 경고 후 (Y/N).
     ```
     ⚠️ 이 cluster draft 는 이미 ai-draft 입니다. 재작성 시 본문이 덮어쓰여집니다. (Y/N)
     ```
   - `human-reviewed` → `--force` 없으면 거부.
   - `frozen` → 거부(새 DEC + 새 버전 필요).
   - status 누락 → `/fanout --cluster-mode` 재실행(셸이 status: empty 포함)으로 갱신 안내.

4. `decisions.md` 존재 확인(DEC 충돌 대조용). 없으면 생성 요청 후 중단.

5. `CONTEXT/layer-config.md` PREFIX + `CONTEXT/reference-docs/{ACTIVE_PREFIX}/A|B/` 로드(캐시·발췌 우선,
   /write 단계 1 의 B-summary·B-headings-index 규칙 동일 적용).


## 단계 1 — cluster 컨텍스트 수집

frontmatter 의 graph-gen 산출 메타를 읽는다(수동 수정 금지):
- `cluster.capability` / `cluster_id` / `cluster_name`, `members`(소속 policy 노드)
- `fr_refs`(D1 요구사항 인용 — link only), `domain_objects`, `policy_axes`
- `primary_screen` / `related_screens`(§2 화면 설계 기준)
- `inherits_from`(상위 B 공통·상위 cluster), `research_refs`(D5 — link only)
- `deliverable_targets`(보통 D2·D3, Dα 있으면 §α)

members 각 policy 노드의 원천(requirements.md FR, decisions.md 결정, 회의 위임)을 수집해
무손실 작성 입력으로 삼는다.


## 단계 2 — Delta/내용 범위 PM 확인 (단일 체크포인트)

다음 표를 출력하고 PM 확인을 받는다(직렬 프롬프트 추가 금지 — 한 번에):

```
Cluster 작성 범위 — {capability}/{cluster_id} {cluster_name}

┌─ §1 정책결정 (→D2) — B 상속(재작성 금지·링크) / 이 cluster Delta 정책 ─┐
│  상속: {inherits_from §요약}  →  [{doc_id} §X 참조]                       │
│  Delta: {requirements·decisions 기반 cluster 고유 정책 후보, [TBD] 포함}  │
├─ §2 화면설계 (→D3) — primary/related_screens 4-state·마이크로카피 ───────┤
│  화면: {primary_screen, related_screens}                                  │
└──────────────────────────────────────────────────────────────────────────┘
```

PM 확인 없이 단계 3 진행 금지.


## 단계 3 — 4패널 작성 (골격 고정 · 내용 무손실)

`::: {.panel section="..."}` 펜스드 div 와 `## §N` 헤딩, `section=` 속성을 **보존**하고
패널 내부의 `{{...}}` placeholder 와 예시 표를 실제 내용으로 치환한다. 하위 섹션은
원문 분량만큼 가변 확장(고정 개수 아님). 패널을 추가·삭제·재배치하지 않는다.

### §1 정책 결정 (→ D2 정책정의서)
- `### §1-1 정책 범위/적용 조건`, `### §1-2 핵심 규칙`(POL-N 표), `### §1-3 상태/라이프사이클`,
  `### §1-4 오류/예외` 를 기본 골격으로, 원문 정책 수만큼 하위섹션 확장.
- 상태×액션은 §1-3 에 매트릭스로(전 상태 커버 — critique AXIS-09). 이 매트릭스는
  추후 `/bdd` 가 수용 기준(.feature)으로 결정적 변환하므로 셀을 비우지 말 것.
- B 공통은 `[{doc_id} §X 참조]`, 수치는 `[[spec-catalog {변수ID}]]`. A 어휘 준수.
- 케이스 분기 전수: 정상/실패/취소/타임아웃/0개/중복/동시(AXIS-03).

### §2 화면 설계 (→ D3 화면설계서)
- `### §2-1 주요 화면/ID`, `### §2-2 화면 구성/컴포넌트`, `### §2-3 인터랙션/정책 연결`,
  `### §2-4 빈상태/오류 화면`, `### §2-5 디자인 토큰(공통 셸 참조)`.
- 화면별 4-state(idle/loading/success/error) + 마이크로카피 실제 문구(플레이스홀더 토큰 금지).
- §1 정책이 화면에 어떻게 노출되는지 `[[POL §X-Y]]` 마커로 결합(§2-3).
- 디자인 토큰 재정의 금지 — 공통 셸 cluster(G2-COMMON-*) 참조만(SSoT 경계).

### §α 기술 산출물 (선택 — API/DB/마이그레이션 있는 cluster 만 → Dα)
- 이 cluster 가 API 노출/신규 스키마/데이터 이행을 가질 때만 작성. 없으면 §α 패널을
  **통째로 삭제**(빈 placeholder 잔존 금지 — lint L5).
- `::: {.panel section="§α-API ..."}` / `§α-DB` / `§α-MIG` — section 라벨은 `§α` 로
  시작하고 type 키워드(API/DB/마이그레이션)를 포함해야 render_transpose 가 Dα 별
  페이지로 추출한다(템플릿 라벨 그대로 사용).
- 작성 시 frontmatter `deliverable_targets` 에 대응 `Da_api`/`Da_db`/`Da_migration`
  를 추가한다(없으면 발행 대상 제외).
- §α 는 **발행 정본**, §3 데이터 모델은 **내부 스케치** — 스키마 정본은 §α-DB 에만
  두고 §3 은 참조(SSoT 중복 금지).

### §3 데이터/의존성 (내부용 · publish 제외)
- 데이터 모델(mermaid classDiagram), 외부 의존(다른 cluster·API·인프라), 성능 고려.
- 무손실 잔여: 어디에도 안 맞는 원문 사실은 `### 미분류 원문 사실` 에 원문 그대로 보존.

### §4 Open Questions / Upstream Feedback (내부용 · publish 제외)
- `### §4-1 Open Questions`(OQ-N 표, 자체 해결 가능).
- `### §4-2 Upstream Feedback` — `/integrate` 가 자동 인식하는 BLOCK 카테고리로 분류:
  `#### REQ_MISSING`(D1 추가) / `#### POLICY_CONFLICT`(DEC 신규) /
  `#### RESEARCH_GAP`(D5 보강) / `#### TERM_AMBIGUOUS`(terms/spec-catalog).
- `### §4-3 결정 trail` — cluster 작성 중 PM 결정. DEC 등재 대상은 decisions.md DEC 표에
  `⬜` 후보 행 등재(스키마 [[CONTEXT/dec-schema]], 승인은 /dec-approve).

**색상/placeholder 규칙**: 색상 span(`[..]{.color-*}`) 수기 작성 금지 — publish 시
apply_color_cycling.py 자동 산출. `{{...}}` placeholder 는 전수 치환(미치환 시 lint L5 WARN).


## 단계 4 — 검증 (lint → storage 변환 → split 점검)

작성 직후 순서대로 실행한다.

1. **Publication 문법 lint** (FAIL=차단):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lint_publication_syntax.py --input drafts/cluster_{cluster_id}.draft.md
   ```
   - L1 panel 클래스 허용목록 / L2 panel `section=` 필수 / L3 style 허용 / L6 색상 span
     nested 금지 / L7 표 컬럼 일관성 = **FAIL 이면 수정 후 재실행**. L4/L5 는 WARN.

2. **Storage 변환 + lint 게이트** (FAIL=차단):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/md_to_storage.py --input drafts/cluster_{cluster_id}.draft.md --output /tmp/cluster_{cluster_id}.xml --validate
   ```
   - MD → storage XML 변환을 수행하고, `--validate` 가 입력 MD 에 publication-lint
     를 다시 실행한다(1단계와 동일 규칙). exit 1=변환 실패 / exit 2=lint FAIL.
   - 실패 시 해당 위치를 수정 후 재실행한다.

3. **분할 임계 점검** (권고 — 비차단):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lazy_split_check.py --drafts drafts/cluster_{cluster_id}.draft.md
   ```
   본문 >1500줄 / §1+§2 항목 >8 / R2 BLOCK 누적 >5 초과 시 child cluster 분할 권고
   (`G2-K-{id}-a/-b`). PM 승인 후 처리.

> round-trip 골든(`round_trip_test.py`)은 변환기 회귀 테스트(CI)다 — 개별 draft 작성
> 단계가 아니라 변환기 변경 시 실행한다.


## 단계 5 — 자기 검증 체크리스트

- [ ] 무손실: 원문 정책·화면 사실 전수 매핑(누락 0, 미분류는 §3 보존, 모순은 [정책 충돌] 양쪽)
- [ ] 핵심 4패널(§1~§4) 골격·`section=` 속성 보존, 재배치 없음 (§α 만 선택적 추가/삭제)
- [ ] §α 작성 시 frontmatter `deliverable_targets` 에 Da_* 등재 / 미작성 시 §α 패널 삭제
- [ ] §1-3 상태×액션 매트릭스 전 상태 커버(빈 셀 없음 — /bdd 변환 대비)
- [ ] §2 4-state·마이크로카피 실제 문구(플레이스홀더 토큰 0)
- [ ] B 재작성 0 — `[{doc_id} §X 참조]` 링크만 / 수치는 [[spec-catalog]] 변수ID
- [ ] A 어휘 준수(이탈 시 [TBD:] + open-issues P1)
- [ ] `[[POL §X-Y]]` 표준 마커만(§2-3 정책 결합)
- [ ] `{{...}}` placeholder 전수 치환(lint L5 WARN 0)
- [ ] lint FAIL 0 · md_to_storage --validate 통과
- [ ] §4 Upstream Feedback 카테고리 분류 / 결정은 DEC 후보 등재
- [ ] decisions.md 정본(`승인=✅`) 위반 없음


## 단계 6 — frontmatter status 전환 (안 A)

자기 검증 통과 후 in-place 갱신:
- `status: empty` → `status: ai-draft` (재작성 케이스는 ai-draft 유지)
- `last_updated: {YYYY-MM-DD}` 갱신
- cluster 메타(capability/cluster_id/members 등)·`color_state: null` 은 수정 금지.


## 단계 7 — 완료 보고 및 session-log

```
/write-cluster 완료 — {capability}/{cluster_id}

  draft: drafts/cluster_{cluster_id}.draft.md  (status: ai-draft)
  §1 정책 규칙: {N}건 / §2 화면: {N}개
  lint: FAIL 0 / storage --validate: OK / split: {권고 유무}
  TBD: {N} (open-issues P1) · 정책충돌: {N} (P0) · DEC 후보: {N}
  Upstream Feedback: REQ_MISSING {N}·POLICY_CONFLICT {N}·RESEARCH_GAP {N}·TERM_AMBIGUOUS {N}

다음 단계: /integrate {product} (R1~R3) → /bdd {product}(수용 기준) → /render --push(transpose)
```

session-log.md 에 추가:
```markdown
- {날짜} /write-cluster {cluster_id}: §1 {N}규칙 / §2 {N}화면 / lint OK / TBD {N} / 충돌 {N}
```


## 결과 파일 목록

| 파일 | 내용 |
|---|---|
| `drafts/cluster_{cluster_id}.draft.md` | 4패널 작성본 (status: empty → ai-draft, 골격 보존·내용 무손실) |
| `decisions.md` | §4-3 결정 trail 의 DEC `⬜` 후보 행 |
| `open-issues.md` | TBD(P1) / 정책충돌(P0) / 의미 B 신호(RE 인계 추적) |
| `session-log.md` | 작성 요약 |


## 다음 단계

```
/integrate {product}        # R1~R3 BLOCK 해소 + UPSTREAM_GAP 분류
/bdd {product}              # §1-3 매트릭스·§2 4-state → 수용 기준(.feature)
/render --push {product}    # §1→D2·§2→D3 transpose 후 Confluence 발행
```
