---
name: fanout
description: validate_graph.py로 graph.json을 검증한 후 fanout_dag.py를 실행해 policy WO와 screen WO를 생성하고 work-orders/index.md를 구성한다. Phase 1 시작 스킬이다.
triggers:
  - "fanout"
  - "generate work orders"
  - "make wo"
phase: 1
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

0. **트랙 감사 (fix-plan-track-routing P2 — 최우선)**
   다음 중 하나라도 존재하면 이 프로젝트는 **cluster(dossier) 모델 = Track A** 다.
   - `PROJECTS/{product}/graph/project-mode.json` (track=A / model=dossier)
   - `PROJECTS/{product}/graph/cluster_map.json` 또는 `graph.clustered.json`
   - `PROJECTS/{product}/drafts/cluster_*.draft.md` (이미 작성된 dossier)

   감지되면 **legacy fanout 을 진행하지 않는다.** `/fanout --cluster-mode` 로
   안내한다. PM 이 명시적으로 legacy 강제를 원하는 경우에만 `--force-legacy` 를
   전달한다(이 경우 기존 dossier 옆에 WO 셸이 함께 생성됨을 반드시 고지).
   판단이 서지 않으면 `/plan-audit {product}` 로 트랙을 먼저 확정한다.

   > fanout_dag.py 자체가 이 신호를 감지해 fail-closed 로 중단하므로, 본 항목을
   > 건너뛰어도 빈 WO 셸이 양산되지는 않는다. 다만 PM 에게 트랙을 먼저 안내하는
   > 것이 올바른 순서다.

1. `PROJECTS/{product}/graph/graph.json` 존재 여부를 확인한다.
   미존재 시 `/graph-gen {product}` 실행을 안내하고 중단한다.

2. `open-issues.md`의 P0 항목 수를 확인한다.
   P0가 1건 이상이면 목록을 출력하고 중단한다.

3. `CONTEXT/layer-config.md`에서 PREFIX를 읽는다.
   PREFIX 미등록 시 PM에게 입력을 요청한다.

4. `decisions.md`에서 `freeze: false` 여부를 확인한다.
   이미 frozen이면 WO 재생성 의도인지 PM에게 확인한다.


## 실행 단계

### 단계 1 — graph.json 검증

`scripts/validate_graph.py`를 실행한다:
```
validate_graph.py  PROJECTS/{product}/graph/graph.json
                   --json
```
> `--schema` 는 생략한다(감사 2026-06-08 H5). validate_graph 는 schema 미지정 시
> cwd(Hub) → graph.json 상위 → 플러그인 순으로 `templates/graph-schema.json` 을
> 자동 탐색한다. literal `--schema templates/graph-schema.json` 은 Hub cwd 에서만
> 해석되어 cwd 가 다를 때 FileNotFoundError→exit 2 로 오탐 중단된다. graph-gen 단계 4
> 와 동일하게 auto-discovery 에 위임한다.

결과를 파싱한다:
- FAIL 항목이 있으면 오류 목록을 출력하고 실행을 중단한다.
  `/graph-gen {product}` 재실행을 안내한다.
- WARN 항목이 있으면 목록을 출력하고 PM에게 계속 진행 여부를 묻는다.
- PASS이면 다음 단계로 진행한다.

검증 통계(node 수, edge 수, type별 집계)를 한 줄로 출력한다.


### 단계 2 — delta_required: false 노드 처리

graph.json의 policy 노드 중 `delta_required: false`인 노드를 수집한다.
해당 노드는 WO 생성 대상에서 제외하고
`work-orders/no-delta-list.md`에 다음 형식으로 기록한다:

```markdown
# No-Delta 노드 목록

다음 노드는 {PREFIX}-B 공통 정책을 완전 적용하며 별도 WO가 생성되지 않습니다.
Confluence 업로드 시 "[{doc_id} 기본 정책 완전 적용]" 으로 자동 기록됩니다.

| doc_id | 문서 제목 | inherits_from | 비고 |
|---|---|---|---|
| {doc_id} | {title} | {PREFIX}-B-{NNN} | delta_required: false |
```

screen 노드는 `delta_required` 필드와 무관하게 모두 WO 생성 대상이다.


### 단계 3 — fanout_dag.py 실행

`scripts/fanout_dag.py`를 실행한다:
```
fanout_dag.py  PROJECTS/{product}/graph/graph.json
               --output  PROJECTS/{product}/work-orders/
               --product {product}
               --prefix  {PREFIX}
```

**모드 플래그 (fix-plan-track-routing):**
- (없음) — **기본 = legacy**. section policy WO + screen WO 생성. 단, 전제조건 0의
  cluster 신호가 감지되면 fail-closed 로 중단된다.
- `--cluster-mode` — **Track A (Full Product)**. cluster(dossier) 단위 WO 생성.
  `cluster_identify.py` 가 선행되어 graph 에 capability/cluster_id 가 있어야 한다.
- `--force-legacy` — cluster 신호를 무시하고 legacy 를 강제(fail-closed 우회).
  기존 dossier 옆에 WO 셸이 함께 생성되므로 의도 확인 후에만 사용.
- `--publication-mode {dossier-page|split-deliverable}` — **cluster-mode 전용**
  발행 모드 (fix-plan-dossier-publish-split). `graph/project-mode.json` 에 영속
  기록되어 `/render`·`/cr`·sync 가 분기 기준으로 읽는다.
  - `dossier-page` (기본): 기능정의서 1개 = Confluence 페이지 1개.
  - `split-deliverable`: dossier §1 → D2 정책정의서 / §2 → D3 화면설계서로
    transpose 분할 발행(페이지 2개).
  - 미지정 시 기존 값(없으면 dossier-page) 보존 — 작성 동작 자체는 모드와 무관하게
    동일하다(dossier draft 양식 불변). 모드는 **발행 단위**에만 영향을 준다.

실행 결과를 수신한다:
- 성공: `[fanout] 완료 — policy WO: {N}개 / screen WO: {N}개` 메시지 확인
- 실패: 오류 메시지를 출력하고 중단한다.
  - `FAIL: 이 프로젝트는 cluster(dossier) 모델...` → fail-closed 가드. 전제조건 0을
    따라 `--cluster-mode` 또는 (의도 확인 후) `--force-legacy` 로 재실행한다.
  - 그 외 → graph.json 구조 재확인을 안내한다.


### 단계 4 — 생성 결과 요약 출력

실행 모드에 따라 읽는 산출물과 보고 항목이 다르다.

**(A) cluster-mode (Track A) — `work-orders/cluster_index.json`**

cluster-mode 는 `index.md` 를 생성하지 않는다. `work-orders/cluster_index.json` 을
읽어 capability별 dossier 생성 현황을 보고한다:

```
Dossier(cluster) 생성 완료

  dossier(cluster): {N}개
  capability별:
    {capability}: {N}개 ({cluster_id 목록, wo_id={PREFIX}-K-{cluster_id}})
    ...
  no-delta:  {N}개 (WO 미생성)
```

**(B) legacy node-mode (비 cluster) — `work-orders/index.md`**

`work-orders/index.md`를 읽어 다음 항목을 PM에게 보고한다:

```
Work Order 생성 완료

  policy WO: {N}개
  screen WO: {N}개
  no-delta:  {N}개 (WO 미생성)
  총 레벨:   {N}개

  레벨별 병렬 그룹:
  레벨 0 ({N}개): {WO ID 목록}
  레벨 1 ({N}개): {WO ID 목록}
  ...

  전제조건 주의 WO:
  {precondition 엣지가 있는 WO 목록}
```


### 단계 5 — session-log.md 갱신

Phase 1 진입을 기록한다. 실행 모드에 맞춰 요약 컬럼을 작성한다:
```markdown
# cluster-mode (Track A)
| 1 (Work Orders) | {UTC 타임스탬프} | /fanout --cluster-mode | dossier(cluster) {N}개 / no-delta {N}개 |
# legacy node-mode
| 1 (Work Orders) | {UTC 타임스탬프} | /fanout | policy WO {N}개 / screen WO {N}개 / no-delta {N}개 |
```


### 단계 6 — open-issues.md graph-gen 항목 종결

`open-issues.md`에서 `/graph-gen` 단계에서 등록된 항목 중
graph.json이 정상 생성되어 해소된 항목을 완료 처리한다.


## 결과 파일 목록

| 파일 | 변경 내용 |
|---|---|
| `work-orders/WO-NN.md` | policy + screen WO 전체 생성 |
| `work-orders/index.md` | 레벨별 병렬 그룹 + 요약 카드 |
| `work-orders/no-delta-list.md` | delta_required: false 노드 기록 |
| `session-log.md` | Phase 1 진입 기록 |
| `open-issues.md` | graph-gen 해소 항목 완료 처리 |


## 실패 처리 원칙

- validate_graph.py FAIL: 즉시 중단. `/graph-gen` 재실행 안내.
- fanout_dag.py 실패: 오류 코드 출력 후 중단. 부분 생성된 WO 파일은 삭제하지 않는다.
- no-delta-list.md 기록 실패: 경고 출력 후 계속 진행.


## 다음 단계

WO 생성 완료 후 레벨 0의 WO부터 병렬 작업 시작:
- 각 WO에 대해: `/write {WO_ID}` 또는 PM이 직접 draft 작성
- 전체 draft 완성 후: `/integrate {product}`
