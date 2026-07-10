---
name: integrate
description: 모든 {PREFIX}-C draft를 graph 분할 파일(graph.edges.json·graph.policy.json) 기준으로 통합 검증한다. SSoT 위반 / 어휘 위반 / 계층 모순 / 드래프트 간 충돌을 BLOCK으로 관리하며 3라운드 내 BLOCK 0건 달성 시 Phase 4 진입을 허가한다.
triggers:
  - "integrate"
  - "final check"
  - "validate all"
agent: integrator
phase: 3
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

1. **WO 목록 로드 (개선안 G — CONTEXT_OPTIMIZATION.md)**:
   `work-orders/index.json` 이 존재하면 `wo[]` 배열에서 전체 WO 목록을 읽는다.
   미존재 시에만 `index.md` 표 파싱으로 fallback. 본문 인용 금지.
   `drafts/` 하위에 해당 WO 의 draft 파일이 모두 존재하는지 확인한다.
   누락된 draft 가 있으면 목록을 출력하고 중단한다.
   `/write {WO_ID}` 또는 `/flow {product}` 실행을 안내한다.

2. **draft frontmatter 검증 (개선안 H)**:
   다음 명령으로 모든 draft 의 표준 frontmatter 존재를 확인한다:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/migrate_draft_frontmatter.py \
       --hub-root . --product {product} --check
   ```
   exit code 1 (누락 존재) 이면 누락 파일 목록을 출력하고 중단.
   `--check` 제외 명령으로 자동 보강 후 재시도하도록 안내한다.

3. `open-issues.md` 에서 P0 항목 수를 확인한다.
   P0 가 1건 이상이면 목록을 출력하고 중단한다.

4. `graph/graph.edges.json` + `graph/graph.policy.json` (개선안 C 분할 파일)이 존재하는지 확인한다.
   분할 파일 미존재 시 `graph/graph.json` 단일본으로 fallback한다.
   둘 다 없으면 `/graph-gen {product}` + `/fanout {product}` 재실행을 안내하고 중단한다.

5. **컨텍스트 캐시 검증 (개선안 A·B)**:
   `CONTEXT/.template-cache/B-summary.md` 와
   `CONTEXT/.template-cache/B-headings-index.json` 존재 여부 확인.
   둘 중 하나라도 없거나 stale (`reference-docs/{ACTIVE_PREFIX}/B/*.md` 보다 오래됨) 이면
   `python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_cache.py --hub-root .` 와
   `python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_index.py --hub-root .` 을
   먼저 실행하도록 안내한다.

6. `session-log.md` 에서 현재 integrate 라운드 수를 계산한다.
   `[integrate]` 항목 수를 카운트한다.
   3라운드 초과 시 PM 에게 상황을 보고하고 강제 진행 여부를 확인한다.


## 실행 단계

### 단계 1 — integrator 에이전트 기동

> 개선안 H (CONTEXT_OPTIMIZATION.md) — 본문 로드 전 frontmatter 만 1차 스캔.

integrator 에이전트에 다음 컨텍스트를 전달한다:

```
입력 파일:
  - drafts/*.draft.md (frontmatter 1차 스캔 → 후보군 좁힌 뒤에만 본문 로드)
  - work-orders/index.json (개선안 G — 마크다운 표 대신 JSON)
  - graph/graph.edges.json + graph/graph.policy.json (개선안 C — 분할 파일 직접 사용)
  - CONTEXT/.template-cache/B-summary.md (개선안 A — 캐시 우선)
  - CONTEXT/.template-cache/B-headings-index.json (개선안 B — 발췌 위치)
  - decisions.md
  - open-issues.md

검증 지시:
  - 1차 패스: drafts/*.draft.md 의 frontmatter (wo_id, type, layer,
    referenced_policies, referenced_screens, status) 만 스캔하여
    검증 대상 후보를 그룹화한다 (개선안 H).
  - 2차 패스부터 본문 로드. BLOCK 기준 4개 적용 (단계 2 참조)
  - WARN 기준 3개 적용 (단계 2 참조)
  - INFO 기준 2개 적용 (단계 2 참조)
  - 드래프트 간 충돌은 WO ID 쌍으로 기록
  - 영향도 분석: graph.edges.json 의 implements / precondition 엣지 기준 전파
```


### 단계 2 — 검증 기준 분류

**BLOCK 조건 (Phase 4 진입 불가):**

| ID | 조건 | 판단 기준 |
|---|---|---|
| BLK-01 | SSoT 위반 | {PREFIX}-B 내용을 draft에서 직접 재정의 (Link 미사용) |
| BLK-02 | 계층 모순 | {PREFIX}-C 내용이 {PREFIX}-B 규칙과 논리적으로 상충. 단, `decisions.md` DEC 표에서 해당 항목 DEC 행의 `승인` 셀이 `✅` 인 행이 있으면 BLOCK 제외 → INFO 기록. `⬜`·`🟡` 인 미승인 DEC만 존재하면 BLOCK 유지 (PM 승인 필요). [[CONTEXT/dec-schema]] §4 승인 게이트 참조. |
| BLK-03 | 어휘 위반 | {PREFIX}-A 미등재 상태명·오류코드·용어 사용 |
| BLK-04 | 드래프트 간 충돌 | 두 WO draft가 동일 대상에 상반된 규칙을 정의 |
| **BLK-05 (Phase 5H)** | **UPSTREAM_GAP** | cluster draft 의 §4 (Open Questions / Upstream Feedback) 에 누락된 FR (REQ_MISSING) / 정책 충돌 (POLICY_CONFLICT) / 타사조사 부족 (RESEARCH_GAP) / 용어 모호 (TERM_AMBIGUOUS) 가 1건 이상. 해소 경로: `/draft-req --upstream-feedback` 으로 D1/D5 v++ 리비전 후 재실행. **Track A 전용** — Track B/C 는 본 BLOCK 미적용. |
| **BLK-06 (P4)** | **FR↔cluster trace mismatch** | `fr_cluster_check.py` 가 fr_index ↔ cluster draft `fr_refs` 불일치(mismatch, 양방향)를 1건 이상 산출(`reports/fr-cluster-trace-queue.md` 헤더 `BLOCK: N` > 0, exit 2). orphan·unmapped 는 WARN(비차단). 해소: 해당 cluster draft `fr_refs` 보강/정정 또는 `cluster_identify` 재군집 후 재실행. ([[CONTEXT/gates/fr-cluster-trace-gate]]) |

**WARN 조건 (Phase 4 진입 가능, PM 확인 필요):**

| ID | 조건 | 판단 기준 |
|---|---|---|
| WRN-01 | 의존성 불일치 | WO-A draft가 참조한 기능이 WO-B draft에 미정의 |
| WRN-02 | 영향도 전파 오류 | policy WO 변경이 implements 연결 screen WO에 미반영 |
| WRN-03 | 누락 의존 관계 | graph.edges.json에 엣지 없으나 draft 내용상 선후관계 존재 |

**INFO 조건 (기록만, 진행 무관):**

| ID | 조건 |
|---|---|
| INF-01 | 톤앤매너 / 문체 불일치 |
| INF-02 | 마이크로카피 빈 상태 누락 |
| INF-03 | BLK-02 제외 항목 — DEC 표 승인(`✅`) 행 (내용: DEC-ID + 항목명 + 승인자 + 일자) |
| INF-04 | 미승인 DEC 잔존 — `승인=⬜` 또는 `🟡` 인 DEC 행 수 (Phase 4 진입은 가능. `/confirm` 진입 직전 0건 필수 — [[CONTEXT/dec-schema]] §4-3) |


### 단계 3 — 산출물 생성

**reports/integration-summary.md:**
```markdown
generated_at: {ISO8601}
# 통합 검증 요약 — Round {N}

**실행 시각**: {UTC}
**검증 대상**: policy WO {N}개 / screen WO {N}개
**결과**: BLOCK {N}건 / WARN {N}건 / INFO {N}건

| 분류 | 건수 | Phase 4 영향 |
|---|---|---|
| BLOCK | {N} | 진입 불가 |
| WARN | {N} | PM 확인 후 진입 가능 |
| INFO | {N} | 영향 없음 |
```

> `generated_at:` 은 파일 **1행** 에 반드시 기재한다. `/lc` 의 master-derivation-gate STALE 판정 기준이다.
> 형식: `generated_at: 2026-05-24T09:30:00Z` (ISO 8601 UTC, 소수점 이하 생략).
> ⚠ 파일 앞에 `---` (YAML frontmatter 구분선) 없이 `generated_at:` 이 1행 그대로 오도록 한다 — YAML 파서 혼동 방지.
> `generated_at:` 없이 파일만 존재하면 `/lc` 는 STALE 로 판정하고 integrate 재실행을 요구한다.

**reports/conflict-report.md:**
BLOCK 항목별 다음 내용을 상세 기록한다:
```markdown
## BLK-NN — {BLOCK ID} / {드래프트 파일명}

**조건**: {BLK-01 ~ BLK-04}
**위반 내용**: {구체적 내용}
**참조 소스**: {위반 기준 문서 및 항목}
**해소 방법**: {수정해야 할 내용과 방향}
**담당 스킬**: `/write {WO_ID}` 또는 `/flow {product} {screen_id}`
```

**reports/impact-map.md:**
graph.edges.json 의 implements / precondition 엣지를 기준으로
변경 영향이 전파되는 WO 연결 경로를 기록한다:
```markdown
## 영향도 맵

| 변경 WO | 영향 WO | 엣지 타입 | 반영 여부 |
|---|---|---|---|
```


### 단계 4 — 라운드별 처리

**BLOCK 0건:**
- Phase 4 진입을 허가한다.
- decisions.md DEC 표에 자동기록 행을 추가한다 (스키마: [[CONTEXT/dec-schema]]):
  ```markdown
  | DEC-{NNN} | {MM-DD} | 🤖 | /integrate Round {N} 통과 · BLOCK 0건 · Phase 4 허가 | - | ✅ system | /integrate R{N} |
  ```
  - 자동기록(`🤖`) 도메인은 PM 승인 없이 `✅ system` 등재 ([[CONTEXT/dec-schema]] §5 등재 권한 매트릭스)
- 미승인(`⬜`·`🟡`) DEC이 남아있으면 INF-04로 통합 보고서에 기재하고 PM에게 `/dec-approve` 안내
- 단계 5로 진행한다.

**BLOCK 1건 이상:**
- conflict-report.md를 출력하고 PM에게 보고한다.
- 각 BLOCK 항목별 담당 WO ID와 수정 스킬을 목록으로 제시한다.
- PM이 수정 완료 후 `/integrate {product}`를 재실행한다 (Round N+1).
- WARN 항목은 PM에게 목록을 제시하고 수용 여부를 확인한다.
  수용 시 open-issues.md에 P2로 등록하고 계속 진행.
  미수용 시 해당 draft 수정 후 재실행.

**3라운드 후 BLOCK 존재:**
- BLOCK 항목을 open-issues.md에 P0으로 격상 등록한다.
- PM에게 다음 선택지를 제시한다:
  - 해당 WO를 제외하고 partial publish 진행
  - 추가 라운드 진행 (Round 4+)
  - 해당 WO를 TBD 상태로 동결 후 다음 배포 주기로 이관


### 단계 5 — session-log.md 기록

```markdown
| 3 (Integrate) | {UTC 타임스탬프} | /integrate Round {N} | BLOCK {N}건 / WARN {N}건 / {통과 또는 미통과} |
```

BLOCK 0건 시 Phase를 4로 기록한다.


## 결과 파일 목록

| 파일 | 내용 |
|---|---|
| `reports/integration-summary.md` | 검증 결과 요약 + 라운드 이력 |
| `reports/conflict-report.md` | BLOCK/WARN 상세 + 해소 방법 |
| `reports/impact-map.md` | WO 간 영향도 전파 맵 |
| `open-issues.md` | WARN 수용 시 P2 / 3라운드 초과 BLOCK P0 등록 |
| `decisions.md` | 통과 시 Phase 4 허가 기록 |
| `session-log.md` | Round N 기록 |


## 다음 단계

BLOCK 0건 + WARN 수용 완료:
- `/confirm {product}`: v1.0-frozen 확정 → Confluence 업로드 → GitLab MR → 공지
