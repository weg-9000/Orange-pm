---
name: lc
description: 프로젝트의 현재 Phase를 자동 감지하고 모든 게이트 통과 여부를 검증한다. 다른 스킬에서 특정 게이트만 확인할 때는 --gate 옵션을 사용한다. Phase 대시보드와 다음 추천 스킬을 함께 출력한다.
triggers:
  - "lc"
  - "layer check"
  - "status"
  - "gate check"
phase: any
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

## 실행 단계

### 단계 1 — 프로젝트 컨텍스트 수집

다음 파일을 읽는다. 파일이 없으면 해당 항목을 "미생성" 으로 처리한다:
- `PROJECTS/{product}/session-log.md`
- `PROJECTS/{product}/open-issues.md`
- `PROJECTS/{product}/decisions.md`
- `PROJECTS/{product}/inputs/requirements.md`
- `PROJECTS/{product}/graph/graph.json`
- `PROJECTS/{product}/work-orders/index.md`
- `PROJECTS/{product}/reports/integration-summary.md`
- `CONTEXT/layer-config.md`

session-log.md에서 현재 Phase를 읽는다.
Phase 기록이 없으면 Phase -1 (Init 미완료) 로 간주한다.

`--gate {gate_name}` 옵션이 지정된 경우 해당 게이트 단계만 실행하고 반환한다.


### 단계 2 — 게이트별 체크리스트 검증

각 게이트의 **검증 기준은 `CONTEXT/gates/` 파일이 단일 진실원**이다.
lc는 기준을 내장하지 않고 파일에서 읽는다.

#### discovery-exit-gate

`CONTEXT/gates/discovery-exit-gate.md`를 읽는다.
파일이 없으면 PM에게 게이트 파일 부재를 알리고 해당 게이트를 SKIP으로 표시한다.
"## 필수 조건" 섹션의 표 각 행을 순서대로 검증하고 PASS / FAIL을 기록한다.

#### policy-entry-gate

`CONTEXT/gates/policy-entry-gate.md`를 읽는다.
파일이 없으면 해당 게이트를 SKIP으로 표시한다.
"## 필수 조건" 섹션의 표 각 행을 순서대로 검증하고 PASS / FAIL을 기록한다.

#### graph-exit-gate

`CONTEXT/gates/graph-exit-gate.md`를 읽는다.
파일이 없으면 해당 게이트를 SKIP으로 표시한다.
"## 필수 조건" 섹션의 표 각 행을 순서대로 검증하고 PASS / FAIL을 기록한다.

#### draft-complete-gate

`CONTEXT/gates/draft-complete-gate.md`를 읽는다.
파일이 없으면 해당 게이트를 SKIP으로 표시한다.
"## 필수 조건" 섹션의 표 각 행을 순서대로 검증하고 PASS / FAIL을 기록한다.

#### integration-exit-gate

`CONTEXT/gates/integration-exit-gate.md`를 읽는다.
파일이 없으면 해당 게이트를 SKIP으로 표시한다.
"## 필수 조건" 섹션의 표 각 행을 순서대로 검증하고 PASS / FAIL을 기록한다.


### 단계 2-B — 스크립트 산출 게이트 검증

**원문(draft 본문·공통 정책 본문) 재로드 금지 — 헤더 요약만 읽는다.**
큐 파일 부재 시 `STALE` 로 표시하고 "스크립트 미실행" 권고를 출력한다 (FAIL과 구별).

#### drift-gate

`PROJECTS/{product}/reports/drift-queue.md` 의 헤더 행만 읽는다.
- 헤더 `BLOCK: N` 파싱 → N > 0 이면 **FAIL** (SOFT_BLOCK)
- N = 0 이면 **PASS**
- 파일 미존재 → **STALE** (스크립트 미실행 — `python ${CLAUDE_PLUGIN_ROOT}/scripts/drift_scan.py --hub-root . [--product {product}]` 실행 권고)

#### master-derivation-gate

`PROJECTS/{product}/reports/integration-summary.md` 의 **1행 헤더**를 먼저 읽는다.

헤더 형식 (integrator 에이전트 산출 의무):
```
generated_at: <ISO8601 timestamp>   <!-- 예: generated_at: 2026-05-24T09:30:00Z -->
```

판정 순서:
1. 파일 미존재 → **STALE** (integrate 스킬 미실행 권고)
2. 파일 존재하나 `generated_at:` 헤더 없음 → **STALE** (스크립트 미실행 — integrate 재실행 권고). 클린 상태(`FAIL=0`)와 구별 불가이므로 PASS 처리 금지.
3. 헤더 `generated_at` 값이 `drafts/` 하위 파일 중 가장 최근 mtime보다 오래됨 → **STALE** (draft 변경 후 integrate 재실행 필요)
4. 헤더 timestamp가 최신이면 본문의 reviewer V-06 / integrator I-02 FAIL 건수 확인:
   - FAIL 건수 > 0 이면 **WARN** (하드 BLOCK 아님 — 공통 파생 체인 검토 권고)
   - FAIL 건수 = 0 이면 **PASS**

> ⚠️ **WARN 등급**: 이 게이트는 차단 조건이 아니다. 다음 Phase 진입 전 해소를 권고하나, BLOCK 큐에는 WARN 등급으로만 등재된다.

#### policy-impact-gate

`PROJECTS/{product}/reports/policy-impact-queue.md` 의 헤더 행만 읽는다.
- 헤더 `IMPACT: N` 파싱 → N > 0 이면 **FAIL** (SOFT_BLOCK)
- N = 0 이면 **PASS**
- 파일 미존재 → **STALE** (스크립트 미실행 — `python ${CLAUDE_PLUGIN_ROOT}/scripts/policy_impact_scan.py --hub-root . [--product {product}]` 실행 권고)

#### bdd-coverage-gate

`PROJECTS/{product}/reports/bdd-coverage-queue.md` 의 헤더 행만 읽는다.
- 헤더 `UNCOVERED: N · STALE: N` 파싱 → 둘 다 0 이면 **PASS**
- 어느 한쪽이라도 > 0 이면 **FAIL** (SOFT_BLOCK)
- 파일 미존재 → **STALE** (스크립트 미실행 — `/bdd {product}` 실행 권고)

#### mtg-gate

`PROJECTS/{product}/reports/mtg-queue.md` 의 헤더 행만 읽는다.
- 헤더 `BLOCK: N · FAIL: N` 파싱 → 양쪽 모두 0 이면 **PASS**
- 어느 한쪽이라도 > 0 이면 **FAIL** (SOFT_BLOCK)
- 파일 미존재 → **STALE** (스크립트 미실행 — `python ${CLAUDE_PLUGIN_ROOT}/scripts/mtg_ledger_scan.py --hub-root . [--product {product}]` 실행 권고)

#### render-freshness-gate

각 `drafts/{WO_ID}.draft.md` 파일에 대해 대응하는 `reports/render/{WO_ID}.complete.md`
파일의 mtime 을 비교한다. **본문은 읽지 않는다 — mtime 만 확인.**

- complete.md 미존재 → **FAIL** (auto-assemble hook 미실행 또는 신규 draft —
  PM 에게 `python ${CLAUDE_PLUGIN_ROOT}/scripts/render_assemble.py --hub-root . --product {p} --wo {WO_ID}` 실행 권고)
- draft mtime > complete mtime → **FAIL** (complete.md stale — auto-assemble hook
  이 실행되었어야 하나 누락. 동일 명령 권고)
- 모든 draft 가 최신 complete.md 와 짝을 이루면 **PASS**

이 게이트는 PostToolUse hook (auto-assemble) 이 정상 동작했는지 검증하는 안전망이다.
hook 이 실패해도 /lc 진입 시 강제로 잡힌다.

#### sync-drift-gate

`PROJECTS/{product}/reports/sync-queue.md` 와 `reports/inbox/` 디렉토리 검사:
- `reports/inbox/*.merge-proposal.md` 가 1건 이상 존재 → **WARN** (위키(remote) drift
  미해소 — `/render --apply-inbox {WO_ID}` 권고)
- `sync-queue.md` 헤더 `OUTDATED: N` 이 > 0 → **WARN** (push 필요 — `/render --push` 권고)
- 양쪽 모두 0 또는 파일 미존재 → **PASS**

이 게이트는 Phase 진행을 차단하지 않지만 (WARN 등급) 위키(remote) ↔ Local
불일치를 시각화한다.

#### track-gate (fix-plan-track-routing P2)

작성 모델(트랙)과 실제 산출물·결정 정합을 검증한다. **본문은 읽지 않는다 —
`graph/project-mode.json` 과 파일 존재 신호, decisions.md 의 hard DEC 행만 본다.**

1. **트랙 마커 ↔ 산출물 정합**
   - `graph/project-mode.json` 이 track=A(dossier)인데 `work-orders/index.md` 가
     legacy section/screen WO 로 채워져 있으면 → **FAIL** (모델 혼선 — legacy WO 가
     dossier 트랙에 오염됨. `/plan-audit` 로 트랙 재확정 권고).
   - track=A 인데 `drafts/cluster_*.draft.md` 가 0건이고 graph 에 capability/cluster_id
     도 없으면 → **WARN** (cluster_identify 미실행 — `/fanout --cluster-mode` 전 선행).
   - project-mode.json 미존재 + cluster 신호(cluster_map.json·dossier draft)는 존재 →
     **WARN** (트랙 마커 누락 — cluster_identify 재실행 또는 수동 기록 권고).

2. **hard DEC(게이트 결정) 강제**
   - `decisions.md` 에서 `핵심 결정` 셀에 `🔒` 마커가 있고 `승인` 이 `✅` 인 행을
     **hard DEC** 로 수집한다(예: "🔒 section WO 폐기·dossier 정본").
   - 승인된 hard DEC 의 취지와 모순되는 산출물이 감지되면 → **FAIL**
     (예: dossier 정본 hard DEC 가 승인됐는데 legacy section WO 가 존재).
   - 모순 없으면 **PASS**.

세 항목 모두 정합이면 **PASS**. FAIL 은 SOFT_BLOCK 등급으로 등재한다.


### 단계 2-C — BLOCK 우선순위 정렬

단계 2 · 2-B 의 모든 게이트 결과를 수집해 BLOCK 큐를 구성하고 아래 3단계 알고리즘으로 정렬한다.

#### Severity 분류

| 등급 | 해당 조건 |
|---|---|
| **HARD_BLOCK** | ① integration-exit-gate FAIL (Phase 3→4 전진 자체 차단 — `/confirm`·`/cr` 호출 불가) ② 환경 SSoT 손상: `master-id-map.yml` 파싱 실패 또는 `graph.json` / `graph.edges.json`·`graph.policy.json` 양쪽 모두 부재 (게이트 검증 자체 불능) |
| **SOFT_BLOCK** | orange-pm Phase 진입 게이트 FAIL (integration-exit-gate 제외) / drift BLOCK / mtg BLOCK+FAIL / policy-impact IMPACT / bdd-coverage UNCOVERED·STALE / **track-gate FAIL (트랙 혼선·hard DEC 모순)** |
| **WARN** | master-derivation WARN / drift WARN·UNRESOLVED |
| **INFO** | 온톨로지 미결 · embed stale · Neo4j 미연결 |

> **HARD_BLOCK 엣지케이스 규칙**
> - HARD_BLOCK 이 하위 Phase 에서 발생한 경우에도 **Severity 절대 우선** — Phase 위상이 낮더라도 정렬 1순위.
> - 동일 Severity·동일 Phase 내 HARD_BLOCK 다건은 **effort 오름차순 (XS → XL)** 으로 처리.
> - SOFT_BLOCK은 "현 Phase 작업은 가능, 다음 Phase 진입만 차단"이나 HARD_BLOCK은 "현 Phase 작업 자체가 불가능"하므로 즉시 PM 확인 필수.

#### Phase 위상 순서 (앞 = 상위)

```
discovery-exit → policy-entry → graph-exit → draft-complete
→ [drift / policy-impact / mtg / bdd-coverage / master-derivation]
→ integration-exit
```

동일 Phase 내 스크립트 산출 게이트 순서:
`drift > policy-impact > mtg > bdd-coverage > master-derivation` (영향 범위 넓은 순)

#### effort 동점 해소

동일 Severity + 동일 Phase 내에서만 effort 오름차순 (XS → S → M → L → XL) 적용.
**우선순위 역전 금지**: effort가 낮아도 상위 Severity/Phase 항목을 추월할 수 없다.

#### 추천 출력 형식

```
★ 추천: {gate_id} — {1줄 해소 가이드}
   (이유: Severity={등급} / Phase={위상} / effort={XS|S|M|L|XL})
```

추천은 정렬 후 1위 항목 1건만 출력한다.


### 단계 3 — 결과 출력

다음 형식으로 대시보드를 출력한다:

```
프로젝트 상태: {product}
현재 Phase:   {Phase 값} ({Phase 이름})
PREFIX:        {PREFIX}

게이트 현황 (Phase 진입 게이트):
  discovery-exit-gate   [{PASS/FAIL/SKIP}]  {미충족 항목 수 또는 "완료"}
  policy-entry-gate     [{PASS/FAIL/SKIP}]  {미충족 항목 수 또는 "완료"}
  graph-exit-gate       [{PASS/FAIL/SKIP}]  {미충족 항목 수 또는 "완료"}
  draft-complete-gate   [{PASS/FAIL/SKIP}]  {미충족 항목 수 또는 "완료"}
  integration-exit-gate [{PASS/FAIL/SKIP}]  {미충족 항목 수 또는 "완료"}

게이트 현황 (스크립트 산출 게이트):
  drift-gate            [{PASS/FAIL/WARN/STALE}]  {BLOCK 건수 또는 "이상 없음"}
  policy-impact-gate    [{PASS/FAIL/WARN/STALE}]  {IMPACT 건수 또는 "이상 없음"}
  mtg-gate              [{PASS/FAIL/WARN/STALE}]  {BLOCK+FAIL 건수 또는 "이상 없음"}
  bdd-coverage-gate     [{PASS/FAIL/STALE}]       {UNCOVERED+STALE 건수 또는 "이상 없음"}
  master-derivation-gate[{PASS/WARN/STALE}]       {V-06/I-02 FAIL 건수 또는 "이상 없음"} ※WARN 전용

미결 항목:
  P0: {N}건  {N}건이면 진행 불가
  P1: {N}건
  P2: {N}건

BLOCK 우선순위 큐 (총 {N}건):           ← 10줄 이내 핵심만
  1. [{SOFT_BLOCK|WARN|INFO}] {gate_id}  {1줄 요약}
  2. ...

★ 추천: {gate_id} — {1줄 해소 가이드}
   (이유: Severity={등급} / Phase={위상} / effort={XS|S|M|L|XL})

추천 다음 스킬:
  {현재 Phase와 게이트 상태를 기반으로 1개 추천}
```

### 온톨로지 인프라 상태

- **unknown_terms.log 미결 항목 수**
  `CONTEXT/glossary/unknown_terms.log` 를 읽어 `#` 으로 시작하지 않는 줄을 집계한다.
  - 0건 → ✅
  - 1건 이상 → ⚠️ 미결 어휘 N건 (항목 목록 출력)
  - 파일 미존재 → [glossary 미초기화 — Phase 3-A 먼저 실행]

- **마지막 embed_pipeline 실행 시점**
  `PROJECTS/{product}/chunks.parquet` 의 수정 시각 기준
  - 7일 이내 → ✅ {날짜}
  - 7일 초과 → ⚠️ {날짜} — embed_pipeline 재실행 권고
  - 파일 미존재 → [임베딩 미실행 — embed_pipeline.py 를 실행하세요]

- **Neo4j 연결 상태**
  bolt://localhost:7687 로 ping
  - 성공 → ✅ 연결됨
  - 실패 → ⚠️ 미연결 (/search 벡터 모드 비활성)

#### Phase 이름 정의:

| Phase 값 | 이름 |
|---|---|
| -1 | Init 미완료 |
| Init | 초기화 완료 |
| 0 | Discovery / Requirements / Graph |
| 1 | Fanout |
| 2 | Writing |
| 3 | Integration |
| 4 | Publication |

#### 추천 스킬 결정 로직:

| 조건 | 추천 스킬 |
|---|---|
| layer-config.md 미존재 또는 PREFIX 미등록 | `/ingest {product}` |
| discovery-exit-gate FAIL | `/research`, `/stakeholder`, `/product-audit` 중 미완료 스킬 |
| policy-entry-gate FAIL | `/draft-req {product}` |
| graph-exit-gate FAIL | `/graph-gen {product}` |
| draft-complete-gate FAIL | `/fanout {product}` 또는 `/write {WO_ID}` |
| integration-exit-gate FAIL | `/integrate {product}` |
| 모든 게이트 PASS | `/confirm {product}` |


### 단계 4 — 미충족 항목 상세 출력

FAIL / WARN / STALE 게이트가 1개 이상이면 미충족 항목 목록을 출력한다.
**30초 판독 목표** — 스크립트 산출 게이트는 헤더 수치만 표시하고 원문 재인용 금지.

```
미충족 항목 상세:

━━ Phase 진입 게이트 ━━

[policy-entry-gate]
  - requirements.md Layer 1 FR: 현재 {N}개 (기준: 10개 이상)
  - ...

[draft-complete-gate]
  - 미작성 draft: WO-03.draft.md, WO-07.draft.md

━━ 스크립트 산출 게이트 ━━

[drift-gate]           {FAIL|STALE}
  - BLOCK: {N}건  →  drift-queue.md 확인 후 해소 후 재실행
  ※ STALE 시: drift_scan.py 미실행 — `python ${CLAUDE_PLUGIN_ROOT}/scripts/drift_scan.py --hub-root . [--product {product}]` 를 먼저 실행하세요

[policy-impact-gate]   {FAIL|STALE}
  - IMPACT: {N}건  →  policy-impact-queue.md 확인
  ※ STALE 시: policy_impact_scan.py 미실행 — `python ${CLAUDE_PLUGIN_ROOT}/scripts/policy_impact_scan.py --hub-root . [--product {product}]`

[mtg-gate]             {FAIL|STALE}
  - BLOCK: {N}건 · FAIL: {N}건  →  mtg-queue.md 확인
  ※ STALE 시: mtg_ledger_scan.py 미실행 — `python ${CLAUDE_PLUGIN_ROOT}/scripts/mtg_ledger_scan.py --hub-root . [--product {product}]`

[master-derivation-gate]  {WARN|STALE}
  - V-06 FAIL: {N}건 · I-02 FAIL: {N}건  →  integration-summary.md 참조
  ⚠️ WARN — 하드 BLOCK 아님. 다음 Phase 진입 전 해소 권고.
  ※ STALE 시: /integrate 스킬 미실행
```

`--gate {gate_name}` 옵션 사용 시 해당 게이트의 PASS/FAIL 결과와
미충족 항목 목록만 반환하고 종료한다.
다른 스킬에서 호출하는 경우를 위한 경량 모드이다.


## 결과 파일

| 파일 | 변경 내용 |
|---|---|
| `reports/lc-{YYYYMMDD-HHMM}.md` | 전체 게이트 체크 결과 저장 (수동 호출 시만) |

다른 스킬에서 `--gate` 옵션으로 호출된 경우에는 파일을 생성하지 않는다.
