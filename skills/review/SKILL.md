---
name: review
description: >-
  {PREFIX}-C 초안의 품질을 reviewer 에이전트로 독립 검증한다. {draft_file} 지정 시 단일 파일 검토, --all 시 전체 draft 일괄 검토. FAIL 항목이 있으면 수정 후 재검토한다. Phase 2에서 실행한다.
triggers:
  - "review"
  - "check draft"
  - "validate draft"
agent: reviewer
phase: 2
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

1. `{draft_file}` 인수를 확인한다.
   - 단일 파일 경로인 경우: 해당 파일이 `drafts/` 하위에 존재하는지 확인한다.
   - `--all` 옵션인 경우: `drafts/*.draft.md` 전체를 처리 대상으로 설정한다.
   - 둘 다 없는 경우: PM에게 파일 경로 또는 `--all` 옵션을 입력하도록 요청한다.

2. `CONTEXT/.template-cache/`에 {PREFIX}-A / {PREFIX}-B 캐시 파일이 존재하는지 확인한다.
   없으면 `[캐시 없음 — 어휘·정합성 검증 불가]` 경고를 출력하고 PM에게 계속 진행 여부를 확인한다.

3. `graph/graph.json`이 존재하는지 확인한다.
   없으면 `[graph.json 없음 — inherits_from 검증 불가]` 경고를 출력한다.


## 실행 단계

### 단계 1 — reviewer 에이전트 기동

reviewer 에이전트에 다음 컨텍스트를 전달한다:

```
검토 대상: {draft_file 또는 drafts/*.draft.md}

참조 파일:
  - CONTEXT/.template-cache/{PREFIX}-A-*.cache.md
  - CONTEXT/.template-cache/{PREFIX}-B-*.cache.md
  - graph/integration-contract.md (frozen edge value 참조 — reviewer 는 graph.json 을 직접 읽지 않음)
  - decisions.md
  - brand-voice.md (존재 시)

WO 타입 판별:
  draft 헤더의 type 필드를 읽어 policy / screen 으로 분기
```


### 단계 2 — WO 타입별 검증 기준

검토 대상 draft의 헤더에서 WO 타입을 확인한다.
타입에 따라 다음 기준을 적용한다.

#### policy WO 공통 기준

| ID | 항목 | 기준 | 등급 |
|---|---|---|---|
| RV-P01 | {PREFIX}-A 어휘 위반 | {PREFIX}-A 미등재 상태명·오류코드 사용 | FAIL |
| RV-P02 | SSoT 위반 | {PREFIX}-B 내용을 직접 재정의 (Link 미사용) | FAIL |
| RV-P03 | inherits_from 모순 | 상위 계층 정책과 내용이 상충 | FAIL |
| RV-P04 | decisions.md 위반 | 프로젝트 확정 결정 사항과 불일치 | FAIL |
| RV-P05 | frozen edge 위반 | integration-contract.md 동결된 엣지 값과 불일치 (reviewer V-02) | FAIL |
| RV-P06 | TBD 미처리 | TBD 항목이 있고 P1 미등록 상태 | WARN |
| RV-P07 | 섹션 구조 불완전 | WO 템플릿 필수 섹션 누락 | WARN |
| RV-P08 | 보안 제약 위반 | 개인정보·인증 관련 규칙 누락 | WARN |
| RV-P09 | 문체 일관성 | 서술 방식 혼재 (명사형 / 동사형 혼용) | INFO |
| RV-P10 | FR↔cluster 추적성 | `fr_cluster_check.py` mismatch(=fr_index↔cluster draft fr_refs 불일치) → FAIL/BLOCK. orphan·unmapped 는 WARN. ([[CONTEXT/gates/fr-cluster-trace-gate]]) | FAIL |

#### screen WO 추가 기준

| ID | 항목 | 기준 | 등급 |
|---|---|---|---|
| RV-S01 | 4-state 누락 | idle / loading / success / error 중 미정의 | FAIL |
| RV-S02 | 오류코드 형식 | {PREFIX}-A 오류코드 형식 미준수 | FAIL |
| RV-S03 | 마이크로카피 누락 | 버튼 레이블 / 오류메시지 / 빈 상태 미작성 | WARN |
| RV-S04 | 버튼 레이블 중복 | 동일 화면 내 버튼 레이블 중복 | WARN |
| RV-S05 | brand-voice 미준수 | brand-voice.md 기준 위반 (존재 시) | WARN |
| RV-S06 | 연관 policy WO 미참조 | implements 연결 policy WO draft 내용 미반영 | WARN |

#### 등급 정의

| 등급 | 정의 | /integrate 영향 |
|---|---|---|
| FAIL | 정합성·정책 위반으로 반드시 수정 필요 | BLOCK 등록 |
| WARN | 품질 저하 요소. 수정 권장 | PM 확인 후 허용 가능 |
| INFO | 스타일·가독성 개선 제안 | 영향 없음 |


### 단계 3 — 검토 결과 출력

각 draft 파일에 대해 다음 형식으로 출력한다:

```
검토 결과: {draft_file}
WO 타입:   {policy / screen}

FAIL: {N}건
WARN: {N}건
INFO: {N}건

FAIL 항목:
  [RV-P02] SSoT 위반 — 3절 "취소 정책" 내용이 {PREFIX}-B-012를 직접 재서술.
            수정 방법: Link 처리로 교체. `/write WO-03`으로 재작성.

WARN 항목:
  [RV-S03] 마이크로카피 누락 — error 상태 오류메시지 미작성.

INFO 항목:
  [RV-P09] 문체 혼용 — 2절은 명사형, 4절은 동사형.
```

> **검토 귀속 정본 필드 (C-ATTEST · reviewer V-16 · wo_emit work-board SSoT):**
> draft 라이프사이클 정본은 `review_status`(enum `empty→ai-draft→human-reviewed→frozen`)
> 이다. `wo_emit.py`(work-board 어댑터)는 `review_status` 를 우선 판독하고, reviewer
> V-16 은 `review_status: human-reviewed` + `reviewed_by` + `reviewed_at` 를 요구한다.
> 따라서 PASS 확정 시 **반드시 `review_status` 를 전이**시킨다. 과거의 bare
> `reviewed: true/false` 는 하위호환 브리지로만 함께 남긴다(신규 판독 근거 아님).

**FAIL 0건 + WARN 0건:**
draft 헤더를 다음으로 갱신한다 — `review_status: human-reviewed`, `reviewed_by: {ORANGE_PM_ID}`,
`reviewed_at: {UTC ISO 8601}` (+ 하위호환 `reviewed: true`).
`reports/review-{WO_ID}.md`를 생성한다.

**FAIL 1건 이상:**
draft 헤더의 `review_status` 를 `ai-draft` 로 유지한다(+ 하위호환 `reviewed: false`).
각 FAIL 항목에 수정 방법과 담당 스킬을 명시한다.

**WARN 1건 이상 (FAIL 0건):**
PM에게 WARN 항목 목록을 제시하고 수용 여부를 확인한다.
수용 시: `review_status: human-reviewed` + `reviewed_by` + `reviewed_at` 기재(+ `reviewed: true`),
open-issues.md에 P2 등록.
미수용 시: 수정 후 재검토.


### 단계 4 — reports/review-{WO_ID}.md 생성

FAIL 0건인 경우에만 생성한다:

```markdown
# review — {WO_ID}

**검토 시각**: {UTC}
**WO 타입**: {policy / screen}
**결과**: PASS (FAIL 0건 / WARN {N}건)

## 검토 항목 결과

| ID | 항목 | 결과 |
|---|---|---|

## 수용된 WARN 항목

| ID | 항목 | open-issues 등록 |
|---|---|---|
```


### 단계 5 — open-issues.md 갱신

FAIL 항목이 있으면 해당 항목을 open-issues.md에 P1으로 등록한다:
```markdown
- [ ] [RV-{WO_ID}-FAIL] {WO_ID} FAIL: {항목명} — 수정 후 /review 재실행 필요
```

수용된 WARN 항목은 P2로 등록한다.


### 단계 6 — session-log.md 기록

```markdown
- {날짜} /review {WO_ID}: FAIL {N}건 / WARN {N}건 / {PASS 또는 FAIL}
```

`--all` 옵션 사용 시:
```markdown
- {날짜} /review --all: 검토 {N}개 / PASS {N}개 / FAIL 존재 {N}개
```


## 결과 파일 목록

| 파일 | 내용 |
|---|---|
| `reports/review-{WO_ID}.md` | PASS 확정 시 검토 결과 기록 |
| `drafts/{WO_ID}.draft.md` 헤더 | PASS 시 `review_status: human-reviewed` + `reviewed_by` + `reviewed_at` 갱신 (+ 하위호환 `reviewed: true`) / FAIL 시 `review_status: ai-draft` 유지 |
| `open-issues.md` | FAIL P1 / WARN 수용 P2 등록 |
| `session-log.md` | 검토 결과 기록 |


## 다음 단계

단일 WO PASS 후:
- 다음 WO 계속 검토: `/review drafts/{다음_WO_ID}.draft.md`

전체 WO PASS 후:
- `/integrate {product}`: 통합 검증 시작
