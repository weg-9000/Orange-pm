---
name: sc
description: 현재 세션의 작업 내용을 요약하고 session-log.md에 기록한다. RESUME.md를 생성해 다음 세션에서 컨텍스트 없이 재개할 수 있도록 한다. PM에게 보류 중인 확인 사항과 추천 다음 액션을 제시한다.
triggers:
  - "sc"
  - "save session"
  - "close session"
  - "session close"
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

### 단계 1 — 현재 프로젝트 상태 수집

다음 파일을 읽는다:
- `session-log.md`: 현재 Phase 및 이전 기록
- `open-issues.md`: 전체 미결 항목 목록
- `decisions.md`: 최근 결정 이력
- `work-orders/index.md` (존재 시): WO 진행 현황
- `reports/integration-summary.md` (존재 시): 최신 통합 검증 결과

`/lc {product}`를 실행해 현재 게이트 통과 상태를 수집한다.


### 단계 2 — 이번 세션 작업 요약 생성

이번 세션에서 실행된 스킬과 주요 변경 사항을 추출한다.
session-log.md에서 이번 세션 시작 이후 추가된 항목을 기준으로 판단한다.

다음 항목을 집계한다:

| 항목 | 내용 |
|---|---|
| 실행 스킬 | 이번 세션에서 호출된 스킬 목록 |
| 생성/수정 파일 | 이번 세션에서 생성 또는 수정된 파일 목록 |
| 새로 등록된 open-issues | P0/P1/P2 각 건수 |
| 새로 등록된 decisions | 건수 |
| Phase 변화 | 시작 Phase → 종료 Phase |


### 단계 3 — session-log.md 세션 블록 추가

다음 형식의 세션 요약 블록을 session-log.md에 추가한다:

```markdown
---
## 세션 요약 — {UTC 날짜}

**Phase**: {시작} → {종료}
**실행 스킬**: {스킬 목록}

### 완료된 작업
{완료 항목 목록}

### 이번 세션 신규 open-issues
{신규 항목 목록 또는 "없음"}

### 이번 세션 신규 decisions
{신규 항목 목록 또는 "없음"}
---
```


### 단계 4 — open-issues.md 및 decisions.md 상태 확인

**open-issues.md 확인:**
- P0 항목이 있으면 목록을 출력하고 PM에게 경고한다.
- 완료 처리(`[x]`)되었으나 내용 정리가 안 된 항목이 있으면 "완료됨" 섹션으로 이동시킨다.

**decisions.md 확인 (DEC 표 SSoT — [[CONTEXT/dec-schema]] 참조):**

1. **미승인(⬜) DEC 목록 출력**:
   - 표를 스캔해 `승인` 셀이 `⬜` 또는 `🟡` 인 행을 모두 나열한다.
   - PM에게 항목별로 `[Y] ✅ 승인 / [N] ❌ 반려 / [H] 🟡 보류 / [S] 다음 세션으로 연기` 를 묻는다.
   - PM 응답에 따라 셀을 갱신한다. (이는 `/dec-approve` 와 동일한 인터랙티브 일괄 처리)

2. **세션 중 자동 캡처 누락분 확인**:
   - 본 세션의 결정성 발화 중 어느 스킬에서도 등재되지 않은 것이 있는지 PM에게 확인한다.
   - 추가 등재 시 DEC 표에 후보 행을 추가 (`승인=⬜` 또는 PM 즉시 승인 선택 시 `✅ {pm_id}`).
   - 등재 불가 (모호한 경우) 시 open-issues.md에 P2로 등록한다.

3. **출력 형식**:
   ```
   미승인 DEC: {N}건
   ├─ DEC-077 [🎯] 카드 그림자 z-index +1 — /critique r2
   ├─ DEC-078 [💰] 약정 30% → 35% (DEC-031 번복) — /su mattermost
   └─ DEC-079 [🏗️] 마이크로프론트엔드 도입 — /write WO-POL-01

   각 항목 처리: [Y/N/H/S] →
   ```


### 단계 5 — RESUME.md 생성

`PROJECTS/{product}/RESUME.md`를 생성한다 (기존 파일 덮어쓰기).
다음 세션 시작 시 Claude Code가 이 파일을 자동으로 읽어 컨텍스트를 복원할 수 있도록 한다.

```markdown
# RESUME — {product}

> 마지막 세션: {UTC 타임스탬프}
> 다음 세션 시작 시 이 파일을 먼저 읽으세요.

## 현재 Phase

{Phase 값} — {Phase 이름}

## 프로젝트 핵심 정보

- PREFIX: {PREFIX}
- graph_hash: {최신 해시 또는 N/A}
- {PREFIX}-B 버전: {버전 또는 N/A}

## 게이트 현황

| 게이트 | 상태 |
|---|---|
| discovery-exit-gate | PASS / FAIL |
| policy-entry-gate | PASS / FAIL |
| graph-exit-gate | PASS / FAIL |
| draft-complete-gate | PASS / FAIL |
| integration-exit-gate | PASS / FAIL |

## 마지막 세션에서 완료한 작업

{완료 항목 목록}

## 현재 미결 P0 항목

{P0 목록 또는 "없음"}

## 현재 미결 P1 항목

{P1 목록 (최대 5건)}

## PM 보류 확인 사항

{이번 세션에서 PM 확인을 받지 못한 항목 목록}

## 추천 다음 액션

1. {우선순위 1 액션 — 스킬명 + 이유}
2. {우선순위 2 액션}
3. {우선순위 3 액션}

## WO 진행 현황 (Phase 1~3 해당 시)

| WO ID | 타입 | 상태 |
|---|---|---|
```

WO 진행 현황은 `work-orders/index.md`가 존재하는 경우에만 포함한다.


### 단계 6 — PM 요약 출력

세션 종료 전 다음 내용을 PM에게 출력한다:

```
세션 저장 완료: {product}

완료된 작업:
  {작업 목록}

주의 사항:
  P0 항목: {N}건 {N > 0이면 "— 즉시 해결 필요"}
  보류 중인 PM 확인: {N}건

추천 다음 액션:
  1. {스킬 또는 조치}
  2. {스킬 또는 조치}

다음 세션 재개 방법:
  PROJECTS/{product}/RESUME.md를 먼저 읽은 후 시작하세요.
```


## 결과 파일 목록

| 파일 | 내용 |
|---|---|
| `session-log.md` | 이번 세션 요약 블록 추가 |
| `RESUME.md` | 다음 세션 재개용 컨텍스트 (최신 상태로 덮어쓰기) |
| `open-issues.md` | 완료 항목 정리 / 미기록 결정 P2 등록 |
| `decisions.md` | 미기록 확정 사항 추가 (PM 확인 후) |
