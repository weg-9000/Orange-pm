---
name: plan-audit
description: Warm Start 시나리오에서 기존 산출물 완성도를 전체 스캔하고 적정 진입 Phase와 우선 실행 스킬을 판정한다.
triggers:
  - "plan-audit"
  - "warm start audit"
  - "resume project"
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


## 실행 조건

`/discover {product}` 실행 후 Warm Start 시나리오를 선택한 경우에 기동된다.
PM이 직접 `/plan-audit {product}`을 입력해도 실행된다.

Warm Start 조건: `PROJECTS/{product}/` 하위에 기존 파일이 1개 이상 존재.
Cold Start 조건: 파일이 전혀 없음 → `/discover`로 복귀.


## 실행 단계

### 단계 1 — 기존 문서 전체 스캔

다음 소스를 순서대로 탐색하고 발견된 문서 목록을 수집한다.

**소스 우선순위:**

| 소스 | 탐색 대상 | 커넥터 (CONNECTORS.md capability) |
|---|---|---|
| 로컬 inputs/ | 기존 입력 파일 전체 | — (파일 직접 읽기) |
| 문서 위키 | 요구사항·기획·정책 문서 | `wiki` (예: Confluence, Notion) |
| 디자인 도구 | 화면 프레임 목록 | `design` (예: Figma) |
| 코드 저장소 | WO 브랜치, MR, 커밋 이력 | `repo` (예: GitLab, GitHub) |

각 커넥터 부재·연결 실패 시 `[{capability} 연동 없음 — 탐색 생략]`을 기록하고 계속 진행한다.
로컬 inputs/ 탐색은 실패 없이 항상 실행한다.

외부 커넥터(wiki·design·repo)에서 발견된 문서가 로컬 파일보다 최신이면
PM에게 동기화 여부를 확인한다.


### 단계 2 — 산출물 완성도 판정

각 항목에 대해 완료 / 미완료 / 누락 3단계로 판정한다.

#### 2-1. requirements.md

| 검사 항목 | 기준 | 판정 |
|---|---|---|
| 파일 존재 | `inputs/requirements.md` 존재 | 완료 / 누락 |
| Layer 1 FR | FR 항목 1개 이상 + Must 항목 존재 | 완료 / 미완료 |
| Layer 2 NFR | NFR 항목 1개 이상 | 완료 / 미완료 |
| Layer 3~5 | 각 레이어 항목 1개 이상 | 완료 / 미완료 |
| TBD 잔존 | Layer 1 TBD 항목 0건 | 완료 / 미완료 |
| 전체 완성도 | 위 5개 항목 전부 완료 | **완성 / 미완성** |

#### 2-2. screen-list.md

| 검사 항목 | 기준 | 판정 |
|---|---|---|
| 파일 존재 | `graph/screen-list.md` 존재 | 완료 / 누락 |
| Screen ID 부여 | 전체 행에 SCR-NNN 형식 ID | 완료 / 미완료 |
| REQ 참조 | 전체 행에 REQ-NNN 연결 | 완료 / 미완료 |
| [미확인] 비율 | 전체 셀의 30% 미만 | 완료 / 미완료 |
| 전체 완성도 | 위 4개 항목 전부 완료 | **완성 / 미완성** |

#### 2-3. graph.json

| 검사 항목 | 기준 | 판정 |
|---|---|---|
| 파일 존재 | `graph/graph.json` 존재 | 완료 / 누락 |
| screen 노드 | 노드 1개 이상 | 완료 / 미완료 |
| 엣지 정의 | 엣지 1개 이상 | 완료 / 미완료 |
| 전체 완성도 | 위 3개 항목 전부 완료 | **완성 / 미완성** |

#### 2-4. work-orders/index.md

| 검사 항목 | 기준 | 판정 |
|---|---|---|
| 파일 존재 | `work-orders/index.md` 존재 | 완료 / 누락 |
| WO 항목 수 | 1개 이상 | 완료 / 미완료 |
| 타입 명시 | 전체 WO에 policy / screen 타입 | 완료 / 미완료 |
| 전체 완성도 | 위 3개 항목 전부 완료 | **완성 / 미완성** |

#### 2-5. drafts/ 초안 완료 비율

`drafts/` 하위 파일 전체를 대상으로 집계한다:

| 항목 | 집계 기준 |
|---|---|
| 전체 초안 수 | drafts/*.draft.md 파일 수 |
| policy 완료 수 | type: policy + reviewed: true 파일 수 |
| screen 완료 수 | type: screen + reviewed: true 파일 수 |
| 미완료 WO 목록 | reviewed: false 파일 ID 목록 |


#### 2-6. 트랙 판정 (fix-plan-track-routing P3 — Phase 보다 먼저)

작성 모델(트랙)을 **Phase 판정보다 먼저** 확정한다. 트랙을 모르면 잘못된 스킬
(legacy `/fanout` vs `/fanout --cluster-mode`)을 추천하게 된다.

| 신호 | 트랙 판정 |
|---|---|
| `graph/project-mode.json` track=A / model=dossier | **Track A (cluster/dossier)** |
| `drafts/cluster_*.draft.md` 존재 | **Track A** |
| `graph/cluster_map.json` · `graph.clustered.json` 존재 | **Track A** |
| `decisions.md` 에 승인된 `🔒` hard DEC (dossier 정본 등) | **Track A** |
| `work-orders/index.md` 가 section/screen WO 로 채워짐 + 위 신호 없음 | **Legacy (section)** |
| 위 신호 모두 없음 | **미정** (requirements/graph 단계) |

**혼선 감지**: Track A 신호와 legacy WO 가 **동시에** 존재하면 → 보고서에
`⚠️ 트랙 혼선` 으로 명시하고, legacy WO 는 오라우팅 산출물일 수 있음을 경고한다
(이번 사고 패턴). 트랙 마커(project-mode.json)가 없으면 Track A 확정 시
cluster_identify 재실행 또는 수동 기록을 권고한다.


### 단계 3 — 진입 Phase 판정

단계 2 판정 결과를 기반으로 적정 Phase를 결정한다.
**우선 실행 스킬은 단계 2-6 의 트랙 판정에 따라 분기한다.**

| 조건 | 판정 Phase | 우선 실행 스킬 (Legacy / Track A) |
|---|---|---|
| requirements.md **미완성** | Phase -1 (Cold Start 이어서) | `/draft-req {product}` |
| requirements.md **완성**, graph.json **누락** | Phase 0 | `/se` → `/graph-gen` (공통) |
| graph.json **완성**, WO **누락** | Phase 1 | Legacy: `/fanout` · Track A: `cluster_identify` → `/fanout --cluster-mode` |
| WO/dossier **생성**, 일부 초안 **미완료** | Phase 2 (미완료부터) | Legacy: `/write {미완료 WO_ID}` · Track A: `/write-cluster {미완료 cluster}` |
| policy 초안 **완료**, screen 초안 **미착수** | Phase 2 (화면설계 트랙) | Legacy: `/flow {첫 screen WO_ID}` · Track A: dossier §2 가 담당(별도 screen WO 없음) |

조건이 복수로 해당되면 가장 이른 Phase를 선택한다.
**트랙 혼선이 감지되면 Phase 추천보다 트랙 정리(혼선 WO 아카이브)를 우선 안내한다.**


### 단계 4 — reports/plan-audit-report.md 생성

```markdown
# plan-audit 보고서 — {product}

**스캔 시각**: {UTC 타임스탬프}
**스캔 소스**: 로컬 / {탐색 성공한 외부 소스 목록}

---

## 트랙 판정 (fix-plan-track-routing P3)

**작성 모델**: Track A (cluster/dossier) / Legacy (section) / 미정
**근거 신호**: {project-mode.json · cluster_map.json · dossier draft · hard DEC 중 감지된 것}
**혼선 여부**: 없음 / ⚠️ 트랙 혼선 ({legacy WO N건 + dossier M건 공존 — 오라우팅 의심})

---

## 산출물 완성도 요약

| 산출물 | 상태 | 상세 |
|---|---|---|
| requirements.md | 완성 / 미완성 / 누락 | {미완료 항목 요약} |
| screen-list.md | 완성 / 미완성 / 누락 | |
| graph.json | 완성 / 미완성 / 누락 | |
| project-mode.json (트랙 마커) | 존재 / 누락 | {track=A 등} |
| work-orders/index.md | 완성 / 미완성 / 누락 | |
| drafts/ 완료율 | policy {N}/{N} / screen {N}/{N} / cluster {N}/{N} | |

---

## 미완료 항목 상세

### requirements.md

{미완료 항목 목록. 없으면 "없음"}

### 미완료 WO 목록

| WO ID | 타입 | 상태 |
|---|---|---|

---

## 판정 결과

**진입 Phase**: Phase {N} — {Phase 이름}

**판정 근거**:
{조건 설명}

**우선 실행 스킬**:
1. {스킬명} — {이유}
2. {스킬명}

---
## PM 승인 요청

위 판정 결과로 Phase {N}에서 재개합니다.
진행하시겠습니까? (Y / 다른 Phase 지정)
```


### 단계 5 — PM 승인 및 Phase 진입 안내

PM에게 판정 결과를 제시하고 확인을 요청한다:

```
plan-audit 완료: {product}

판정된 진입 Phase: Phase {N}
우선 실행 스킬:
  1. {스킬명}
  2. {스킬명}

진행하시겠습니까?
  [Y] Phase {N}에서 재개
  [숫자] 다른 Phase로 직접 진입 지정
  [N] 취소 후 수동 진행
```

PM이 Y를 선택하면 우선 실행 스킬을 즉시 기동한다.
PM이 다른 Phase를 지정하면 해당 Phase의 진입 조건을 안내하고 기동한다.


### 단계 6 — session-log.md 기록

```markdown
- {날짜} /plan-audit: Warm Start / 진입 Phase {N} 판정 / PM 승인 {Y/N}
```


## 결과 파일 목록

| 파일 | 내용 |
|---|---|
| `reports/plan-audit-report.md` | 완성도 스캔 결과 + Phase 판정 + 미완료 목록 |
| `session-log.md` | audit 완료 기록 |
