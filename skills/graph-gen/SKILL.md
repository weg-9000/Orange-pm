---
name: graph-gen
description: >-
  {PREFIX}-A/B/C를 CONTEXT/reference-docs/ 로컬 파일에서 로드하고 graph-generator 에이전트로 graph.json + screen-list.md를 생성한다. validate_graph.py 검증 후 PM 승인을 거쳐 Phase 0을 완료한다.
triggers:
  - "graph-gen"
  - "generate graph"
  - "build graph"
agent: graph-generator
phase: 0
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

## 전제조건 검사

0. **진행 상태 감사 (fix-plan-track-routing P2 — Warm Start 보호)**
   다음 중 하나라도 존재하면 이 프로젝트는 **이미 Phase 2+ 진행 중**이다.
   graph 재생성은 작성 모델을 재시작시켜 기존 산출물을 고아화할 위험이 있다.
   - `PROJECTS/{product}/drafts/cluster_*.draft.md` (작성된 dossier)
   - `PROJECTS/{product}/graph/project-mode.json` / `cluster_map.json`
   - `PROJECTS/{product}/work-orders/index.md` 에 WO 항목이 채워져 있음

   감지되면 **즉시 graph 재생성을 진행하지 말고** `/plan-audit {product}` 를
   선행해 트랙(A/legacy)·적정 진입 Phase 를 확정한 뒤, PM 의 명시적 재생성 승인을
   받는다. 승인 시 기존 `graph/`·`work-orders/`·`drafts/` 백업은 필수다.

1. `PROJECTS/{product}/inputs/requirements.md`가 존재하는지 확인한다.
   없으면 `/draft-req {product}` 실행을 안내하고 중단한다.

2. `open-issues.md`에서 P0 항목 수를 확인한다.
   P0가 1건 이상이면 목록을 출력하고 중단한다.

3. `CONTEXT/layer-config.md`에서 다음 값을 읽는다:
   - PREFIX
   - 로컬 소스 경로 (`CONTEXT/reference-docs/{ACTIVE_PREFIX}/A|B|C/`)
   미존재 시 PM에게 확인을 요청한다.

4. `graph/graph.json`이 이미 존재하면 PM에게 재생성 여부를 확인한다.
   재생성 확인 시 기존 `graph/`, `work-orders/` 하위 파일을 백업하고 진행한다.
   백업 경로: `graph/.backup-{YYYYMMDD-HHMM}/`


## 실행 단계

### 단계 1 — policy-entry-gate 검증

`/lc {product}`를 실행해 policy-entry-gate 통과 여부를 확인한다.

policy-entry-gate 기준:

| 항목 | 기준 |
|---|---|
| requirements.md Layer 1 FR | 10개 이상 |
| requirements.md Layer 2 NFR | 5개 이상 |
| requirements.md Layer 4 액터 정의 | 완료 |
| requirements.md Layer 5 외부 연동 | 목록 존재 |
| discovery-exit-gate 통과 기록 | session-log.md Phase 0 존재 |
| open-issues.md P0 | 0건 |

미통과 항목이 있으면 목록을 출력하고 중단한다.
`/draft-req {product}` 재실행 또는 requirements.md 직접 수정을 안내한다.


### 단계 2 — 상위 계층 문서 로드

`CONTEXT/reference-docs/` 로컬 디렉토리에서 파일을 읽는다.

| 계층 | 로컬 경로 | 필수 여부 | 파일 없을 때 처리 |
|---|---|---|---|
| {PREFIX}-A | `CONTEXT/reference-docs/{ACTIVE_PREFIX}/A/` | 권장 | `[{PREFIX}-A 파일 없음 — 어휘 검증 생략]` 안내 출력 후 계속 진행 |
| {PREFIX}-B | `CONTEXT/reference-docs/{ACTIVE_PREFIX}/B/` | 권장 | `[{PREFIX}-B 파일 없음 — 공통 정책 참조 불가]` 안내 출력 후 계속 진행 |
| {PREFIX}-C | `CONTEXT/reference-docs/{ACTIVE_PREFIX}/C/` | 선택 | `[{PREFIX}-C 파일 없음 — 공통 모듈 참조 생략]` 안내 출력 후 계속 진행 |

각 디렉토리 내 `.md` 파일을 전체 읽는다. README.md는 제외한다.
파일 헤더의 `status: Deprecated`인 파일은 로드에서 제외. 발견 시 `[Deprecated 제외됨]` 경고 출력.

로드된 파일이 1건 이상이면 `CONTEXT/.template-cache/`에 병합 저장한다:
```
CONTEXT/.template-cache/{PREFIX}-A-{YYYYMMDD}.cache.md
CONTEXT/.template-cache/{PREFIX}-B-{YYYYMMDD}.cache.md
CONTEXT/.template-cache/{PREFIX}-C-{YYYYMMDD}.cache.md (존재 시)
```

파일이 하나도 없는 계층은 해당 계층 의존 검증 항목을 건너뛴다.
어떤 계층도 없어도 실행을 중단하지 않는다.


### 단계 3 — graph-generator 에이전트 기동

graph-generator 에이전트에 다음 컨텍스트를 전달한다:

```
입력 문서:
  - {PREFIX}-A 캐시 (어휘 / 원칙)
  - {PREFIX}-B 캐시 (공통 정책)
  - {PREFIX}-C 캐시 (있는 경우)
  - inputs/requirements.md
  - inputs/requirements.seeds.yml (capability 씨앗 사이드카 — 있는 경우)

출력 대상:
  - graph/graph.json
  - graph/screen-list.md
  - graph/graph-preview.md

생성 규칙:
  - {PREFIX}-C policy 노드: requirements.md Layer 1 FR 기반 섹션 단위 분리
  - {PREFIX}-C screen 노드: Layer 1 FR 화면 단위 분리 기준 적용
  - inherits_from 엣지: {PREFIX}-C → {PREFIX}-B/C 계층 방향
  - implements 엣지: screen 노드 → policy 노드
  - precondition 엣지: 논리 선후관계 있는 노드 간
  - delta_required: {PREFIX}-B와 내용이 다른 policy 노드만 true
  - 중복정의 엣지 0건 유지
  - capability 씨앗 주입: 사이드카 requirements.seeds.yml 을 읽어 각 C/work 노드의
    node.capability(+ cluster_hint)를 해당 FR 키에서 채운다. 씨앗은 가설(seed-not-lock,
    DEC-B)이므로 cluster_identify 가 union-find 초기값으로 소비해 최종 경계를 확정한다.
    사이드카가 없거나 FR 키가 없으면 capability 를 비워 둔다(cluster_identify 가 계산).
```

### 단계 3-A — capability 씨앗 사이드카 주입 (P1 → cluster_identify 연결)

graph-generator 는 `inputs/requirements.seeds.yml` (FR ID → capability 가설 맵)을 읽어
각 C/work 노드의 `capability`(및 `cluster_hint`)를 해당 FR 키에서 설정한다. 사이드카 스키마:

```yaml
"FR-101":
  capability: "Provisioning"
  cluster_hint: "PR-01"   # 선택
  lock: false             # 선택, 기본 false
"FR-102":
  capability: "[확인필요]"
```

- 씨앗은 **가설(seed-not-lock, DEC-B)** — node.capability 로 주입되어 `cluster_identify`
  가 5축·threshold 로 검증해 최종 cluster 경계를 확정한다(graph-generator 는 경계를
  고정하지 않는다).
- 사이드카가 없거나 해당 FR 키가 없으면 capability 를 비워 둔다(cluster_identify 가 계산).

에이전트가 unresolved 어휘(requirements.md와 {PREFIX}-A 간 미정의 용어)를 발견하면
`graph/unresolved-decisions.md`에 기록한다.


### 단계 4 — validate_graph.py 실행

`scripts/validate_graph.py`를 실행한다:

```
입력: graph/graph.json
옵션: --json
```

| 결과 | 조치 |
|---|---|
| PASS (WARN 0건) | 단계 5로 진행 |
| PASS (WARN 존재) | WARN 목록을 출력하고 PM 확인 후 진행 |
| FAIL | FAIL 항목 목록 출력. graph-generator 재실행 여부를 PM에게 확인 |

FAIL 항목이 있는 경우 단계 3 재실행 시 FAIL 항목만 집중 수정하도록
graph-generator에 재지시한다. 최대 2회 재실행. 2회 후에도 FAIL이면 중단.


### 단계 5 — PM 검토 요청

`graph/graph-preview.md`를 출력하고 PM에게 다음 항목을 확인받는다:

**확인 항목:**

| 항목 | 확인 내용 |
|---|---|
| 상위 계층 참조 | {PREFIX}-A/B/C Reference 노드 로드 완료 여부 |
| policy WO 목록 | {PREFIX}-C policy 노드 수 및 doc_id 목록 |
| screen WO 목록 | {PREFIX}-C screen 노드 수 및 화면명 목록 |
| 3종 세트 구성 | 각 화면에 policy 연결(implements 엣지) 존재 여부 |
| inherits_from 방향 | {PREFIX}-C → {PREFIX}-B/C 방향 일관성 |
| 중복정의 엣지 | 0건 확인 |
| unresolved-decisions | 어휘 미결 항목 수 + 목록 |
| delta_required 분포 | true 노드 수 / false 노드 수 |

PM 승인(확인) → 단계 6 진행.
PM 수정 요청 → 특정 노드/엣지 수정 후 단계 4 재실행.


### 단계 6 — session-log.md 및 decisions.md 기록

session-log.md에 추가한다:
```markdown
| 0 (Graph) | {UTC 타임스탬프} | /graph-gen | policy 노드: {N}개 / screen 노드: {N}개 / 어휘 미결: {N}건 |
```

decisions.md에 추가한다:
```markdown
- {날짜}: /graph-gen 완료. graph_hash: {12자리 해시}. {PREFIX}-B 버전: {버전}.
```

`unresolved-decisions.md`에 항목이 있으면 open-issues.md에 P2로 자동 등록한다.


## 결과 파일 목록

| 파일 | 내용 |
|---|---|
| `graph/graph.json` | 노드 + 엣지 전체 그래프 |
| `graph/screen-list.md` | screen 노드 추출 목록 + REQ 연결 |
| `graph/graph-preview.md` | PM 검토용 인간 가독 요약 |
| `graph/unresolved-decisions.md` | 어휘 미결 항목 (있는 경우) |
| `CONTEXT/.template-cache/` | {PREFIX}-A/B/C 캐시 파일 |
| `open-issues.md` | WARN / 어휘 미결 항목 자동 등록 |
| `session-log.md` | Phase 0 Graph 기록 |
| `decisions.md` | graph_hash + 버전 기록 |


## 다음 단계

PM 승인 완료 후:
- `/fanout {product}`: graph.json 기반 Work Order 생성
