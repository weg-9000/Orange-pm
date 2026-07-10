---
name: promote
description: sketches/{screen_id}.sketch.md를 정식 draft로 전환한다. graph.json에서 해당 화면과 연결되는 WO를 찾아 매핑하고 drafts/{WO_ID}.draft.md로 변환한다. 스케치 내용을 4-state 구조로 재구성하며, PM이 각 항목을 확인한다.
triggers:
  - "promote"
  - "스케치 확정"
  - "sketch to draft"
  - "스케치 전환"
phase: any
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


## 공통 참조 가드 (C0·C-PIN — gates/master-derivation-gate.md SSoT)

스케치 → draft 전환 시 적용. 상세는 `CONTEXT/gates/master-derivation-gate.md`.

1. 공통 대조: 전환 결과 draft 가 G2-A/B 정책을 재작성하지 않는지 확인 —
   재작성분은 `[{doc_id} §X] 참조` 링크로 대체(B-headings-index 후보 §만).
2. 전환 self-check: 스케치의 placeholder 링크를 실제 POL §앵커 /
   `[[spec-catalog 변수ID]]` 로 해소한다(미해소 placeholder 잔존 금지).
3. C-PIN: 전환 draft frontmatter `referenced_master: [{핀ID}@{version}]` 를
   채운다(master-id-map.yml 권위 ID). 비우면 opt-out → decisions.md 근거 필수.
4. PM 확인은 기존 항목 확인 단계에 통합(직렬 프롬프트 추가 금지).


## 전제조건 검사

1. `sketches/{screen_id}.sketch.md` 가 존재하는지 확인한다.
   없으면 유효한 sketch 파일 목록을 출력하고 중단한다.

2. 파일 헤더의 `promoted: false` 여부를 확인한다.
   이미 `promoted: true` 이면 "이미 전환된 스케치입니다" 를 출력하고 중단한다.

3. `PROJECTS/{product}/graph/graph.json` 이 존재하는지 확인한다.
   없으면 정식 전환에 필요한 graph.json 생성을 안내하고 중단한다.
   (`/graph-gen {product}` 실행 또는 graph.json 없이 WO를 직접 지정하는 방법 안내)

4. `PROJECTS/{product}/work-orders/index.md` 가 존재하는지 확인한다.
   없으면 `/fanout {product}` 실행을 안내하고 중단한다.


## 실행 단계

### 단계 1 — WO 매핑

`{screen_id}` 가 `SCR-NNN` 형식이면 graph.json의 screen 노드에서 직접 찾는다.
`SKT-NNN` 형식(임시 ID)이면 PM에게 연결할 SCR-NNN 또는 WO ID를 입력받는다.

매핑 결과를 출력한다:
```
스케치 → WO 매핑
  스케치 ID:  {screen_id}
  연결 WO:    {WO_ID} ({화면명})
  연결 REQ:   {REQ-NNN}

이 WO로 전환하시겠습니까? (Y / 다른 WO 지정)
```

PM 확인 없이 다음 단계로 진행하지 않는다.


### 단계 2 — 스케치 내용 분석 및 구조 매핑 제안

`sketches/{screen_id}.sketch.md` 내용을 읽고
4-state(idle / loading / success / error) 구조로 분류를 시도한다.

분류 제안 표를 출력한다:
```
스케치 내용 → 4-state 매핑 제안

┌─────────────────────────────────────────────────────┐
│ idle 상태로 분류된 내용:                              │
│  · (스케치에서 추출한 항목)                           │
│  · [미분류] 항목 있으면 표시                          │
├─────────────────────────────────────────────────────┤
│ loading 상태로 분류된 내용:                           │
│  · (스케치에서 추출한 항목)                           │
├─────────────────────────────────────────────────────┤
│ success 상태로 분류된 내용:                           │
│  · (스케치에서 추출한 항목)                           │
├─────────────────────────────────────────────────────┤
│ error 상태로 분류된 내용:                             │
│  · (스케치에서 추출한 항목)                           │
├─────────────────────────────────────────────────────┤
│ [미분류] — 어느 상태에도 해당하지 않는 내용:          │
│  · (항목 목록)                                       │
│  → 삭제 / idle / 별도 open-issue 중 선택 필요        │
└─────────────────────────────────────────────────────┘
```

PM이 분류를 수정하거나 미분류 항목을 처리한 후 확인하면 단계 3으로 진행한다.


### 단계 3 — 정식 draft 파일 생성

`work-orders/{WO_ID}.md` 템플릿 구조를 기반으로
`drafts/{WO_ID}.draft.md` 를 생성한다.

파일 헤더:
```markdown
---
doc_id: {WO_ID}
type: screen
version: draft
written_at: {UTC 타임스탬프}
screen_id: {SCR-NNN}
promoted_from: sketches/{screen_id}.sketch.md
promoted_at: {UTC 타임스탬프}
reviewed: false
---
```

내용 구성:
- 단계 2에서 확정된 4-state 분류 내용을 각 상태 섹션에 배치한다.
- B-정책 참조 항목은 `[{PREFIX}-B-NNN] §N.N 참조` 형식의 플레이스홀더로 표기한다.
  (정식 B-정책 로드는 `/flow` 정상 실행 또는 PM이 직접 수행)
- 미확정 항목은 `[TBD]` 태그로 표기하고 open-issues.md에 P1 등록한다.

자기 검증 체크리스트를 미완성 상태로 생성한다:
```markdown
## 자기 검증 체크리스트
- [ ] 4-state 전체 정의 완료 (스케치 전환 — 보완 필요 항목 있을 수 있음)
- [ ] {PREFIX}-B 공통 정책 검토 및 참조 링크 정비 필요
- [ ] {PREFIX}-A 어휘 기준 검토 필요
- [ ] decisions.md 위반 항목 없음
- [ ] TBD 항목 open-issues.md 등록 완료
```


### 단계 4 — 스케치 파일 상태 갱신

`sketches/{screen_id}.sketch.md` 헤더를 업데이트한다:
```markdown
promoted: true
promoted_to: drafts/{WO_ID}.draft.md
promoted_at: {UTC 타임스탬프}
```

파일 내용은 보존한다 (삭제하지 않음).


### 단계 5 — 완료 보고 및 session-log 기록

```
/promote 완료 — {screen_id}

  스케치:    sketches/{screen_id}.sketch.md
  draft:     drafts/{WO_ID}.draft.md
  TBD 항목:  {N}건 (open-issues.md P1 등록)
  보완 필요: B-정책 참조 링크 {N}건

권장 다음 단계:
  /flow {product} {SCR-NNN}  — B-정책 참조 링크 정비 및 마이크로카피 보완
  /review drafts/{WO_ID}.draft.md  — 현재 상태 검증 (보완 전 미리 확인)
```

session-log.md에 추가한다:
```markdown
- {날짜} /promote {screen_id}: sketches → drafts/{WO_ID}.draft.md 전환 / TBD {N}건
```


## 결과 파일 목록

| 파일 | 내용 |
|---|---|
| `drafts/{WO_ID}.draft.md` | 스케치 기반 정식 draft (보완 필요 항목 포함) |
| `sketches/{screen_id}.sketch.md` | promoted: true 로 상태 갱신 |
| `open-issues.md` | TBD 항목 P1 등록 |
| `session-log.md` | promote 완료 기록 |


## 다음 단계

```
B-정책 정비:  /flow {product} {SCR-NNN}
draft 검증:   /review drafts/{WO_ID}.draft.md
```
