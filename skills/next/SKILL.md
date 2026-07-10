---
name: next
description: 진행 중 작업 상태(큐·status·DEC·산출물)를 모아 다음 행동을 결정적으로 랭킹해 보여준다. 선형 happy-path 가 아니라 비선형 — 차단 해소(fix)·상위 산출물 역류(backward)·전진(forward)을 함께 제시한다. PM 이 /lc 를 반복 호출하며 수동 체이닝하던 부담을 줄이는 작업 관제 진입점. 모델이 라우팅을 추측하지 않고 next_emit.py 결정 결과를 보고한다.
triggers:
  - "next"
  - "다음 뭐"
  - "다음 작업"
  - "뭐 하지"
  - "관제"
  - "what next"
phase: any
effort: low
model: haiku
user-invocable: true
---

## 설계 원칙 — 결정적 추천 (자율 실행 아님)

본 skill 은 **결정적 추천기**다. `next_emit.py` 가 큐·status·DEC·산출물 존재를
모아 다음 행동을 랭킹한다(모델 라우팅·추측 금지 — 게이트/스캐너와 동일 결정적 철학).
**행동을 자동 실행하지 않는다** — PM 이 각 이동을 명시적으로 승인·호출한다.

랭킹 우선순위:
1. **fix** — 차단 게이트(drift / policy-impact / mtg / bdd-coverage BLOCK) 해소
2. **fix** — 미승인 DEC(⬜) 정리 (`/dec-approve`)
3. **backward** — integrate UPSTREAM_GAP → 상위(D1/D5) 리비전 (`/draft-req --upstream-feedback`)
4. **forward** — phase·status 전진 (graph→fanout→write/flow/write-cluster→review→confirm→render)

> 작업은 단방향이 아니다. 본 skill 은 "지금 막힌 것 + 되돌아갈 것 + 전진할 것"을
> 한 번에 보여줘 비선형 루프(draft↔review, 정책변경→재화면, 공통↑→재render,
> DEC 번복→재작성)를 능동 안내한다.


## 실행 단계

### 단계 1 — 추천 산출 (결정적)

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/next_emit.py --hub-root . --product {product} --emit-json
```

산출 계약(요약만 인지 — 원문 큐 재인용 금지):
```json
{ "kind": "next-actions", "phase": 2, "phaseName": "Draft", "blockers": 2,
  "statusCounts": { "empty": 1, "ai-draft": 0, ... },
  "actions": [ { "rank": 1, "direction": "fix|backward|forward",
                 "severity": "BLOCK|WARN|INFO", "label": "...", "cmd": "/bdd",
                 "arg": "{product}", "reason": "...", "source": "bdd-coverage" } ] }
```

### 단계 2 — 보고

```
작업 관제 — {product}  (phase {N} {이름} · 차단 {blockers})

  status: empty {N} · ai-draft {N} · reviewed {N} · frozen {N}

  다음 행동:
   [1] 🔧 해소  {cmd} {arg}  — {reason}      (source: {게이트/큐})
   [2] ↩ 역류  {cmd} {arg}  — {reason}
   [3] →  전진  {cmd} {arg}  — {reason}

  ※ 자동 실행 아님 — 실행할 행동을 지정하세요.
```

`blockers = 0` 이면 "막힌 작업 없음 — 전진 가능" 으로 보고한다.
viz 작업 보드 좌측 **작업 관제** 탭에 동일 추천이 상시 노출된다(원클릭 실행).


## 다른 스킬과의 관계

- `/lc` — 게이트 **전수 검증·대시보드**(상세). `/next` 는 그 결과를 **다음 행동 1~N개로
  압축**한 경량 진입점. 깊은 게이트 분석이 필요하면 `/lc`.
- `/intent-router` — **신규 진입**(자유발화→Track 결정). `/next` 는 **진행 중** 작업의
  다음 수(手). 진입은 intent-router, 운영 중 관제는 next.
- 본 skill 은 결정만 — 실제 작업은 추천된 후속 스킬이 수행한다.


## 결과 파일
없음 (읽기 전용 추천 — 파일 미생성).


## 다음 단계
추천된 행동 중 하나를 PM 이 선택해 실행. 실행 후 `/next` 재호출로 갱신된 다음 수 확인.
