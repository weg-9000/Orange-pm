---
name: bdd
description: policy WO 의 상태 × 액션 매트릭스와 screen WO 의 4-state 인터랙션 시퀀스를 Gherkin .feature 수용 기준으로 결정적 변환하고, 커버리지(화면 필수 4-state·feature stale)를 검증한다. 모델이 시나리오를 창작하지 않고 draft 표 셀을 그대로 Given/When/Then 으로 사상한다(SSoT). [[POL §X-Y]] 마커와 referenced_policy 핀을 Gherkin 태그로 보존해 개발팀 테스트까지 정책 추적을 연결한다. {WO_ID} 지정 시 해당 WO 만 단독 처리한다.
triggers:
  - "bdd"
  - "acceptance"
  - "수용 기준"
  - "gherkin"
  - "feature 파일"
phase: 2
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


## 설계 원칙 — 결정적 컴파일 (C-BDD)

본 skill 은 시나리오를 **창작하지 않는다**. C-RENDER(완전판) 와 동일하게,
draft 의 행위 명세 표를 스크립트가 **결정적으로** Gherkin 으로 변환할 뿐이다.

- 변환 주체: `bdd_assemble.py` (모델 미관여). 모델은 결과 요약만 읽는다.
- 산출물(`reports/bdd/*.feature`)은 **수기 수정 금지** — 이중 작성 = SSoT 붕괴.
  수정이 필요하면 소스 draft(`/write`·`/flow`)를 고치고 `/bdd` 를 재실행한다.
- 사상 규칙:
  - policy `상태 × 액션 매트릭스` 비공백 셀 → `Given 상태 / When 액션 / Then 값`
  - screen `4-state 인터랙션 시퀀스` 행 → `Given 화면 상태(+조건) / When 사용자 액션 / Then UI 표시`
  - **cluster_draft → §1 매트릭스(정책) + §2 4-state(화면) 둘 다 추출**해 한 `.feature` 에
    합본(`@type:cluster`, `# ── §1/§2 ──` 섹션 구분). 커버리지도 §1 density(WARN) +
    §2 4-state 완전성(UNCOVERED) 양쪽 검증.
- 추적: 셀·행의 `[[POL §X-Y]]` 마커 → 시나리오 태그 `@POL-§…`,
  frontmatter `referenced_policy` 핀 → feature 태그. 정책 §변경이 어느
  수용 기준에 영향 주는지 개발팀 테스트까지 추적된다.


## 전제조건 검사

1. `PROJECTS/{product}/drafts/` 디렉토리가 존재하는지 확인한다.
   없으면 `/fanout {product}` 재실행을 안내하고 중단한다.

2. 대상 draft 의 frontmatter `status` 가 `ai-draft` 이상인지 확인한다.
   `status: empty` 인 draft 는 행위 명세가 비어 있으므로 건너뛴다
   (`/write` 또는 `/flow` 선행 안내).

3. `{WO_ID}` 인수가 있으면 `drafts/{WO_ID}.draft.md` 존재를 확인한다.
   없으면 유효한 WO 목록을 출력하고 중단한다.


## 실행 단계

### 단계 1 — 수용 기준(.feature) 결정적 생성

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/bdd_assemble.py --hub-root . --product {product} [--wo {WO_ID}] [--all]
```

- `{WO_ID}` 미지정 시 전체 draft 처리. `--all` 시 `{product}.all.feature` 통합본 추가 생성.
- 산출: `PROJECTS/{product}/reports/bdd/{WO_ID}.feature`
- stdout 의 WO 별 `시나리오 N건` 요약을 수집한다. 본문 `.feature` 전체 재로드 금지.

### 단계 2 — 커버리지 검증

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/bdd_coverage_scan.py --hub-root . --product {product}
```

- 산출: `PROJECTS/{product}/reports/bdd-coverage-queue.md`
- 큐 **헤더 행** (`UNCOVERED: N · STALE: N · WARN: N`) 만 읽는다.
- 판정 기준은 `CONTEXT/gates/bdd-coverage-gate.md` 가 SSoT. 본 skill 은 기준을 내장하지 않는다.

### 단계 3 — 결과 보고

```
BDD 수용 기준 생성 — {product}

생성: {N}개 draft → 시나리오 {총 N}건
  | WO | 유형 | 시나리오 | 커버리지 |

커버리지 게이트 (bdd-coverage-gate):
  UNCOVERED: {N}건   {0이면 ✅ / 1+ 이면 ❌ FAIL}
  STALE:     {N}건   {0이면 ✅ / 1+ 이면 ❌ FAIL}
  WARN:      {N}건   {매트릭스 미정의 셀 — 비차단}
```

FAIL(UNCOVERED·STALE > 0) 시 `bdd-coverage-gate.md` 의 "FAIL 시 처리" 표에 따라
복귀 스킬(`/flow`·`/write`)을 안내한다.

### 단계 4 — session-log 기록

`session-log.md` 에 추가한다:
```markdown
- {날짜} /bdd: {product} 수용 기준 {N} feature / 시나리오 {N}건 / UNCOVERED {N} · STALE {N}
```


## 결과 파일 목록

| 파일 | 내용 |
|---|---|
| `reports/bdd/{WO_ID}.feature` | WO 별 Gherkin 수용 기준 (결정적 생성 — 수기 수정 금지) |
| `reports/bdd/{product}.all.feature` | 전체 통합본 (`--all` 시) |
| `reports/bdd-coverage-queue.md` | 커버리지 검증 결과 (UNCOVERED·STALE·WARN) |
| `session-log.md` | 생성 요약 기록 |


## 다음 단계

- 커버리지 FAIL 해소: `/flow {product} {screen_id}` 또는 `/write {WO_ID}` 후 `/bdd {product}` 재실행
- 전체 게이트 현황: `/lc {product}` (bdd-coverage-gate 포함)
- PASS 후: `reports/bdd/*.feature` 를 개발팀에 인계 (Cucumber/Behave 실행 가능)
