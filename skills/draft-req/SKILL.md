---
name: draft-req
description: Discovery 3개 스트림을 synthesizer 에이전트에 전달해 requirements.md와 research.md를 생성하고 discovery-exit-gate를 검증한다.
triggers:
  - "draft-req"
  - "synthesize requirements"
  - "make requirements"
agent: synthesizer
phase: -1
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

requirements·spec-catalog 합성 시 적용. 상세는 `CONTEXT/gates/master-derivation-gate.md`.

1. 공통 대조: G2-A/B 에 이미 있는 정책·용어는 requirements/spec-catalog 에
   재작성 금지 — `[{doc_id} §X] 참조` 링크로만(B-headings-index 후보 §만,
   원문 전체 로드 금지).
2. spec-catalog 출처 분류: 모든 입력 변수 행의 `출처` 는
   `G2-B §X | 제품 Delta | [확인필요:사유]` 중 하나. **추정·환각 채움 금지**
   (원천 미확보 변수는 [확인필요] + open-issues 등록).
3. PM 확인은 단계 2(생성 결과 수신)에 통합(직렬 프롬프트 추가 금지).

## 전제조건 검사

### 1. 스트림 파일 존재 여부 확인

다음 6개 파일의 존재 여부를 확인한다:
- `inputs/discovery/competitor/overview.md`
- `inputs/discovery/competitor/*.md` (1개 이상)
- `inputs/discovery/stakeholder/overview.md`
- `inputs/discovery/stakeholder/*.md` (1개 이상)
- `inputs/discovery/product-audit/overview.md`
- `inputs/discovery/product-audit/*.md` (1개 이상)

파일이 없는 스트림이 있으면 해당 스킬(`/research`, `/stakeholder`, `/product-audit`)
실행을 안내하고 중단한다.


### 2. 스트림 최소 품질 임계값 확인

각 파일을 읽어 다음 기준을 충족하는지 확인한다:

| 스트림 | 최소 요구사항 |
|---|---|
| competitor | 비교 매트릭스 행 3개 이상 / `[미입력]` 셀이 전체의 50% 미만 |
| stakeholder | 이해관계자 2명 이상 등록 / 요구사항 항목 5개 이상 |
| product-audit | 기존 기능 목록 1개 이상 / pain point 1개 이상 |

미달 스트림이 있으면 구체적인 미달 내용을 출력하고 PM에게 계속 진행 여부를 묻는다.
PM이 강제 진행을 선택하면 해당 스트림에 `[품질 미달 — 강제 진행]` 경고를 붙이고 계속한다.


### 3. open-issues.md P0 항목 확인

P0 항목이 1건 이상이면 목록을 출력하고 중단한다.


### 4. {PREFIX}-B 공통 정책 접근 가능 여부 확인

`CONTEXT/layer-config.md`에서 `{PREFIX}-B` 문서 링크(wiki)를 읽는다.
링크가 없거나 wiki 커넥터(사용자가 연결한 MCP 도구 — 예: Confluence·Notion 등,
CONNECTORS.md 탐지 프로토콜로 확인) 부재·연결 실패 시 open-issues.md에 P2로 등록하고
{PREFIX}-B 없이 합성을 계속 진행한다.
(이 경우 requirements.md의 {PREFIX}-B 중복 항목은 Link 처리 없이 전문 작성된다.)


## 실행 단계

### 단계 1 — synthesizer 에이전트 기동

synthesizer 에이전트에 다음 컨텍스트를 전달해 기동한다:

```
입력 파일:
  - inputs/discovery/competitor/ (전체)
  - inputs/discovery/stakeholder/ (전체)
  - inputs/discovery/product-audit/ (전체)

설정값:
  - PREFIX: {PREFIX} (layer-config.md에서 로드)
  - {PREFIX}-B 문서 링크(wiki): {URL 또는 N/A}

출력 대상:
  - PROJECTS/{product}/inputs/requirements.md
  - PROJECTS/{product}/inputs/requirements.seeds.yml  (capability 씨앗 사이드카)
  - PROJECTS/{product}/inputs/research.md
  - PROJECTS/{product}/inputs/spec-catalog.md  (templates/standard/spec-catalog-template.md 기준)

합성 우선순위: 이해관계자 요구사항 1순위
상충 요구사항 처리: 삭제 금지, open-issues.md에 기록
{PREFIX}-B 중복 항목: requirements.md·spec-catalog 에 Link로만 표기 (재작성 금지)
spec-catalog 출처 규칙: 모든 입력 변수 행 `출처` = G2-B §X | 제품 Delta |
  [확인필요:사유] 중 하나. 원천 미확보 변수는 [확인필요]+open-issues 등록.
  **추정·환각 채움 절대 금지** (값 미상이면 빈칸이 아니라 [확인필요]).
mode: 요금 산식형이면 calculation, 콘솔형이면 console 로 frontmatter 기재.
FR capability 씨앗 (P1 — docs/fr-cluster-alignment.md DEC-A/B): requirements.md 와 같은
  디렉토리에 사이드카 `requirements.seeds.yml` 을 함께 생성/갱신한다. FR 표 본문에는
  인라인 셀을 넣지 않는다(D1 FR 표는 깨끗한 4열 유지). 사이드카는 FR ID 를 키로 하는
  top-level 맵이며, 각 FR 당 `capability` 가설을 1개씩 부여한다:
  ```yaml
  "FR-101":
    capability: "Provisioning"
    cluster_hint: "PR-01"   # 선택
    lock: false             # 선택, 기본 false
  "FR-102":
    capability: "[확인필요]"
  ```
  - `cluster_hint`·`lock` 은 선택. **씨앗=가설(seed)이지 고정 경계 아님(DEC-B)** —
    최종 경계는 cluster_identify(5축·threshold)가 확정하므로 FR 을 capability 산문
    섹션으로 하드 그룹핑 금지. capability 불명확 시 추정 금지 →
    `capability: "[확인필요]"` 로 기입하고 open-issues P1 등록.
  - 무태그 제품은 `cluster_seed_backfill` 으로 사이드카를 사후 부트스트랩할 수 있다(P5).
```

synthesizer는 내부적으로 discovery-exit-gate 자기 검증을 수행한다.
(세부 합성 절차는 `agents/synthesizer.md` 참조)


### 단계 2 — 생성 결과 수신 및 기록

synthesizer 완료 후 다음 항목을 확인한다:

- `inputs/requirements.md` 생성 여부
- `inputs/requirements.seeds.yml` 생성 여부 (사이드카 — capability 씨앗)
- `inputs/research.md` 생성 여부
- `inputs/spec-catalog.md` 생성 여부 + 출처 미태깅(빈칸) 행 0건 / [확인필요] 행 수
- Layer 1~5 항목 수 (synthesizer 자기 검증 결과 수신)
- **FR capability 씨앗 현황** (P1): 사이드카 `requirements.seeds.yml` 에 각 FR ID 키
  존재 여부 / capability 미부여(무키) FR 수 / `[확인필요]` capability FR 수.
  무키 FR 이 남으면 synthesizer 보강하거나, 사후 `cluster_seed_backfill`
  부트스트랩(P5) 으로 사이드카를 채울 수 있음을 안내한다. `[확인필요]` 는 open-issues 등록 확인.
- open-issues.md 신규 등록 항목 수

#### Phase 5B — requirements.md FR 메타 확장 (Track A cluster 군집 입력)

Track A (Full Product) 의 cluster_identify.py 와 fanout 의 cluster mode 가 사용
하기 위해, FR 레코드에 다음 메타 필드를 추가한다 (후방 호환 — 없어도 동작).

```yaml
- id: FR-103
  layer: 1
  title: "DBaaS 인스턴스 생성 정책"
  priority: P0
  # ── Phase 5B 신규 필드 ──
  domain_object: ["Instance", "InstanceSpec"]   # 객체 공유 축
  policy_axis: ["인스턴스 라이프사이클", "자원 한도"]  # 정책 도메인 축
  primary_screen: "SCR-001"                      # 화면 표면 축
  cluster_ref: null                              # 채워질 예정 (cluster_identify 후)
  capability_hint: "Provisioning"                # capability 후보 (옵션)
```

활용:
- **cluster_identify.py** — 4축 점수 산정 입력 (publication-map.md §1)
- **fanout --cluster-mode** — cluster 단위 WO 생성 (cluster-draft.md 양식 적용)
- **cluster draft frontmatter** — `fr_refs` / `domain_objects` / `policy_axes` /
  `primary_screen` 의 SSoT 출처

미지정 시 동작:
- `cluster_identify.py` 가 default 값 + heuristic 으로 진행
- `domain_object/policy_axis` 누락 시 결합 점수 낮음 → 노드별 독립 cluster
- `capability_hint` 누락 시 default `"Default"` capability

PM 작성 권장 순서:
1. Track A 시작 시 FR 목록을 먼저 작성 (기본 필드)
2. `/cluster-identify {product}` 실행 → 산출 cluster summary 검토
3. 결과가 만족스럽지 않으면 위 5축 필드 보강 → 재실행 (동일 cluster_id 유지 — 안정 매핑)
4. 확정 후 `/fanout --cluster-mode` 진입

결과를 session-log.md에 기록한다:
```markdown
| 0 (Requirements) | {UTC 타임스탬프} | /draft-req | FR {N}개 / NFR {N}개 / open-issues 신규 {N}건 |
```


### 단계 3 — open-issues.md Discovery 항목 종결

`open-issues.md`에서 다음 항목을 완료 처리한다:
- `[DISC-01]` 경쟁사 분석 미완료
- `[DISC-02]` 이해관계자 요구사항 수집 미완료
- `[DISC-03]` 자사 제품 현황 파악 미완료

완료 처리 형식: `- [x] [DISC-0N] ~~원래 내용~~ → /draft-req 완료`


### 단계 4 — discovery-exit-gate 검증

`/lc {product}`를 실행한다.

exit-gate 검증 기준:

| 항목 | 기준 | 미달 시 조치 |
|---|---|---|
| Layer 1 FR | 10개 이상 | synthesizer 재실행 |
| Layer 2 NFR | 5개 이상 | product-audit 재탐색 후 보완 |
| Layer 4 액터 정의 | 완료 | stakeholder 재참조 |
| Layer 5 외부 연동 | 목록 존재 | TBD 처리 + P1 등록 |
| FR 화면 단위 분리 | 전수 확인 | 해당 항목 분리 재작성 |
| spec-catalog 출처 분류 | 전 변수 행 출처 태깅(빈칸 0) | 빈칸 행 [확인필요] 보강 |
| open-issues P0 | 0건 | PM 보고 후 중단 |

exit-gate 통과 시 Phase를 0으로 업데이트하고 다음 단계를 안내한다.
exit-gate 미통과 시 미충족 항목 목록을 출력하고 synthesizer 재실행 여부를 묻는다.


## 결과 파일 목록

| 파일 | 변경 내용 |
|---|---|
| `inputs/requirements.md` | Layer 1~5 구조, REQ-NNN ID, 우선순위 포함 (FR 표는 깨끗한 4열) |
| `inputs/requirements.seeds.yml` | capability 씨앗 사이드카 (FR ID → capability 가설, 선택 cluster_hint/lock) |
| `inputs/spec-catalog.md` | 입력 변수 SSoT (7열+출처, calc/console mode). 추정 금지·[확인필요] 추적 |
| `inputs/research.md` | 경쟁사 분석 요약 + FR 매핑 + 경쟁력 근거 |
| `open-issues.md` | DISC-01~03 완료 처리 / 신규 상충·TBD 항목 추가 |
| `session-log.md` | Phase 0 진입 기록 |


## Upstream Feedback 환류 (Phase 4 R5 — cluster work → discovery 리비전)

> Track A (Full Product) 의 Phase 2~3 cluster 작성 중에 `/integrate` 가
> `UPSTREAM_GAP` BLOCK 으로 분류한 항목 → Phase -1 산출물 (requirements.md /
> research.md / decisions.md) 의 리비전이 필요한 신호.

### 트리거 조건
다음 중 하나로 `--upstream-feedback` 모드 진입:
- `/integrate {product}` 실행 시 `UPSTREAM_GAP` BLOCK 발견 → 본 스킬 재호출 권고
- PM 명시 호출: `/draft-req {product} --upstream-feedback`
- cluster draft §4 `Open Questions / Upstream Feedback` 섹션에 기록된 항목이 있음

### 처리 절차
1. **수집**: 다음 위치에서 feedback 항목 수집
   - `reports/integrate/{product}.upstream-gap.md` (integrate 산출)
   - 각 cluster_draft 의 §4 섹션 (수동 PM 기재 포함)

2. **분류**:
   - **REQ_MISSING** — 누락된 FR (requirements.md 추가 필요)
   - **POLICY_CONFLICT** — 정책 충돌 (decisions.md 신규 DEC 후보)
   - **RESEARCH_GAP** — 타사조사 부족 (research.md 보강 필요, research-auto 재실행 검토)
   - **TERM_AMBIGUOUS** — 용어 모호 (terms.yml / spec-catalog.md 추가)

3. **PM 승인 게이트**:
   - 자동 리비전 금지 — 모든 환류는 PM 승인 1건씩
   - "다음 항목을 D1 요구사항정의서에 추가할까요? [y/n]" 식 명시 확인
   - 승인된 항목만 v{n+1} 리비전에 반영

4. **버전 증가**:
   - requirements.md `version: X.Y` → `X.(Y+1)` (minor bump)
   - research.md / decisions.md 도 동일 정책
   - 변경 이력 표에 환류 출처 기록 (cluster_id + UPSTREAM_GAP item ID)

5. **영향 cluster 재방문 안내**:
   - 리비전 후 영향받은 cluster (`feedback.affected_clusters`) 에
     `/lc {cluster_id}` 실행 권고 (lifecycle 검증 재실행)

### 산출물
- `inputs/requirements.md` (v++) — REQ 추가/수정 시
- `inputs/research.md` (v++) — RESEARCH_GAP 환류 시
- `decisions.md` (DEC 신규 행) — POLICY_CONFLICT 환류 시
- `reports/upstream-feedback/{date}.applied.md` — 환류 처리 결과 archive

### Track B/C 와의 차이
- Track B/C 는 단일 deliverable 직선 경로 — `UPSTREAM_GAP` 발생 가능성 낮음 (cluster 없음)
- 발생 시 별도 single-deliverable 양식 안에서 직접 수정 (별도 환류 절차 불요)


## 다음 단계

discovery-exit-gate 통과 시:
- `/graph-gen {product}`: graph.json 생성 및 노드·엣지 설계
