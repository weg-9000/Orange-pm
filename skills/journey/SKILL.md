---
name: journey
description: 현재까지 작성된 화면을 읽어 고객 관점의 E2E 흐름 스토리보드를 생성한다. dossier 모델은 각 capability dossier 의 §2 화면 섹션을, legacy 모델은 screen-list.md + screen draft 를 소스로 한다. draft 미완성 화면은 [작성 중]으로 표기하고 계속 진행한다. 내용을 수정하지 않는 읽기 전용 스킬이다. 언제든 호출 가능하다.
triggers:
  - "journey"
  - "전체 흐름"
  - "고객 여정"
  - "스토리보드"
  - "e2e flow"
  - "user flow"
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


## 자동 생성과의 역할 분담 (journey_build.py)

표준 storyboard(화면 순서·draft 상태·전환 골격)는 **`scripts/journey_build.py` 가
PostToolUse 훅으로 draft 편집 시마다 자동 생성**해 `reports/journey-latest.md` 를
갱신한다(LLM 토큰 0, session-log 미기록). viz 프로토타입 뷰의 사용자 여정 보드는
이 파일을 상시 표시한다(journey_emit 은 mtime 최신본을 선택).

본 스킬은 자동 빌더가 못 하는 **판단 영역**을 담당한다:
- `--actor` 필터링, `--from` 부분 여정
- 핵심 행동·전환 조건·이탈 경로의 서사적 보강 (자동본은 `[자동 생성 — /journey 로 보강]` 플레이스홀더)
- 타임스탬프본(`journey-{YYYYMMDD-HHMM}.md`) 저장 + session-log 기록


## 작성 모델 분기 (dossier vs section/screen)

본 스킬은 두 모델을 지원한다. 전제조건 검사 전에 모델을 판정한다.

| 모델 | 판정 조건 | 화면 소스 |
|---|---|---|
| **dossier (Track A)** | `work-orders/cluster_index.json` 존재 **또는** `graph/screen-list.md` 에 `SUPERSEDED` 배너 존재 | `cluster_index.json` 의 `clusters[].draft_path` 가 가리키는 각 dossier draft(`cluster_{cluster_id}.draft.md`)의 **`§2 화면`(또는 `## §2`) 섹션** 화면 항목. **파일명을 하드코딩하지 말고 `draft_path` 를 따른다**(감사 2026-06-08 H6) |
| **section/screen (legacy)** | 위 조건 미충족이며 `screen-list.md` 에 SCR 행 존재 | `screen-list.md` + screen WO `drafts/{WO_ID}.draft.md` |

dossier 모델에서는 화면이 별도 screen WO/노드가 아니라 각 capability dossier 의 §2 화면 섹션에
포함된다(requirements.md FR 위임 원칙). 아래 단계의 "화면(SCR-NNN)" 표현은 dossier 모델에서
"dossier §2 화면 항목"으로 읽는다.


## 전제조건 검사

1. **모델 판정** 후 화면 소스를 확인한다.
   - dossier 모델: `work-orders/cluster_index.json` + 각 dossier 의 §2 화면 섹션이 존재하는지 확인.
     화면 섹션이 비어 있으면 해당 dossier 는 `[§2 미작성]` 으로 표기하고 계속 진행한다.
   - section/screen 모델: `graph/screen-list.md` 가 존재하는지 확인. 없으면 `/se` 또는 `/graph-gen` 안내 후 중단.
   - 둘 다 없으면 `/graph-gen {product}`(graph 생성) 또는 dossier 작성을 안내하고 중단한다.

2. `PROJECTS/{product}/inputs/requirements.md` 가 존재하는지 확인한다.
   없으면 FR 순서 기반 정렬 없이 소스 순서(dossier: cluster 순 / legacy: screen-list 행 순)를 그대로 사용한다.

3. `--from {screen_id}` 옵션이 있으면 해당 Screen ID가 screen-list.md에 존재하는지 확인한다.
   없으면 유효한 Screen ID 목록을 출력하고 중단한다.

4. `--actor {actor}` 옵션이 있으면 requirements.md Layer 4 액터 목록과 대조한다.
   미존재 액터면 경고를 출력하고 PM에게 계속 진행 여부를 확인한다.

이 스킬은 읽기 전용이다. 어떤 파일도 수정하지 않는다 (reports/ 저장 제외).


## 실행 단계

### 단계 1 — 화면 순서 재구성

- **dossier 모델**: `cluster_index.json` 의 cluster 순서(capability)대로 각 dossier draft
  (`clusters[].draft_path`, 보통 `cluster_{cluster_id}.draft.md`)의 `§2 화면` 섹션을 읽어
  화면 항목을 추출·나열한다. 화면 ID 가 없으면 `{cluster_id}-S{n}` 으로 부여한다.
- **section/screen 모델**: `screen-list.md` 전체 행을 읽는다.

**정렬 기준 (우선순위 순):**
1. requirements.md Layer 1 FR의 Must → Should → Could 순서 (FR↔화면: dossier 는 §2 항목의 FR 참조, legacy 는 screen-list REQ 컬럼)
2. FR 순서가 동일하면 소스 순서(dossier: cluster 순 / legacy: screen-list 행 순) 유지

`--from {screen_id}` 지정 시: 해당 화면부터 시작하고 이전 화면은 "선행 화면" 섹션에 요약한다.
`--actor {actor}` 지정 시: 해당 액터와 연관된 REQ-NNN을 가진 화면만 포함한다.

처리 대상 화면 수를 출력한다.


### 단계 2 — draft 상태 수집

각 화면에 대해 상태를 확인한다.

- **dossier 모델**: 화면 상태 = 소속 dossier draft(`clusters[].draft_path`) frontmatter
  `review_status`(정본) 로 판정. `human-reviewed`(또는 하위호환 `reviewed:true`)→✅ ·
  `ai-draft`+§2 화면 존재→📝 · §2 화면 미작성→⬜.
- **section/screen 모델**: 화면별 screen WO draft 로 판정(아래 표).

| 상태 | 조건 | 스토리보드 표기 |
|---|---|---|
| 완료 | `drafts/{WO_ID}.draft.md` 존재 + `reviewed: true`(또는 dossier `status: human-reviewed`) | ✅ |
| 작성 중 | draft 존재 + `reviewed: false`(또는 dossier `status: ai-draft`/`draft`) | 📝 |
| 스케치 | `sketches/{screen_id}.sketch.md` 존재 (legacy 만) | 🔲 |
| 미착수 | draft/sketch 모두 없음 (dossier: §2 화면 미작성) | ⬜ |


### 단계 3 — 화면 간 전환 조건 추출

각 화면의 전환 조건을 다음 소스에서 우선순위 순으로 읽는다:

| 우선순위 | 소스 | 추출 항목 |
|---|---|---|
| 1 | `drafts/{WO_ID}.draft.md` success 상태 | "다음 액션 목록" |
| 2 | `sketches/{screen_id}.sketch.md` | 전환 관련 서술 |
| 3 | `screen-list.md` 목적 컬럼 | 화면 목적 텍스트 |
| 4 | 없음 | `[전환 조건 미확정]` |

이탈 포인트는 각 화면의 error 상태 또는 취소·뒤로가기 흐름에서 추출한다.


### 단계 4 — 스토리보드 출력

```
고객 여정 스토리보드 — {product}
액터: {actor 또는 "전체"} / 생성 시각: {UTC}
총 {N}개 화면 ({완료 N} ✅ / {작성중 N} 📝 / {스케치 N} 🔲 / {미착수 N} ⬜)
─────────────────────────────────────────────────────────────────
```

각 화면을 다음 형식으로 출력한다:

```
[{순번}] {SCR-NNN} {화면명}  {상태 아이콘}
  진입 조건: {idle 상태 진입 조건 또는 이전 화면 전환 조건}
  핵심 행동: {이 화면에서 고객이 하는 가장 중요한 액션}
  전환:      → {다음 화면 SCR-NNN} ({전환 조건})
  이탈:      ✕ {이탈 경로} ({이탈 조건})  ← 있는 경우만
```

미착수/스케치 화면은 다음 형식으로 표기한다:
```
[{순번}] {SCR-NNN} {화면명}  ⬜ 미착수
  목적: {screen-list.md 목적 컬럼}
  REQ:  {REQ-NNN}
  전환: [미확정]
```

전체 여정 끝에 요약 섹션을 출력한다:
```
─────────────────────────────────────────────────────────────────
여정 요약
  진입점:      {첫 화면}
  핵심 경로:   {SCR-001} → {SCR-002} → ... → {마지막 화면}
  주요 이탈:   {이탈 포인트 목록}
  미확정 구간: {전환 조건 미확정 화면 목록}

작성 중 화면:
  📝 {WO_ID} {화면명} — /review drafts/{WO_ID}.draft.md 권장
  ⬜ {WO_ID} {화면명} — (dossier 모델) /write-cluster 로 §2 화면 작성 / (legacy) /flow {product} {SCR-NNN}
```


### 단계 5 — 파일 저장

`PROJECTS/{product}/reports/journey-{YYYYMMDD-HHMM}.md` 로 저장한다.

파일 헤더:
```markdown
---
generated_at: {UTC 타임스탬프}
product: {product}
actor: {actor 또는 all}
from_screen: {screen_id 또는 first}
screen_count: {N}
draft_complete: {N}
draft_in_progress: {N}
sketch_only: {N}
not_started: {N}
---
```


### 단계 6 — session-log 기록

```markdown
- {날짜} /journey: {N}개 화면 스토리보드 생성 / 완료 {N} / 미착수 {N}건
```


## 결과 파일 목록

| 파일 | 내용 |
|---|---|
| `reports/journey-{YYYYMMDD-HHMM}.md` | E2E 스토리보드 (읽기 전용 참조 뷰) |
| `session-log.md` | 생성 기록 |


## 사용 예시

```bash
# 전체 고객 여정 확인
/journey dbaas

# 특정 화면부터 확인
/journey dbaas --from SCR-003

# 특정 액터 관점으로 필터링
/journey dbaas --actor "서비스 관리자"

# Phase 2 작업 중 중간 점검
/journey dbaas
```


## 주의사항

- 이 스킬은 **내용을 수정하지 않는다** — 읽기 전용 합성 뷰다.
- 언제든 호출 가능하다 (Phase 제약 없음, `/render` 와 동급).
- draft 미완성 화면이 있어도 중단하지 않는다.
- 스토리보드 내용은 산출물이 아닌 **진행 상황 확인 도구**다.
  원본은 항상 각 draft 파일과 screen-list.md다.
