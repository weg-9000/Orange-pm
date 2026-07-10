---
name: dec-approve
description: decisions.md DEC 표의 미승인(⬜) 또는 보류(🟡) 행을 PM 승인 처리한다. /dec-approve {DEC-ID,...} 다건 또는 --all-pending 옵션으로 일괄 처리. --reject 반려, --hold 보류 옵션 지원.
triggers:
  - "dec approve"
  - "결정 승인"
  - "DEC 승인"
phase: any
effort: low
model: haiku
user-invocable: true
---

## 이 스킬의 역할

`decisions.md` DEC 표의 `승인` 칼럼을 PM 권한으로 갱신한다.
표 셀 직접 편집의 대안으로, CLI 워크플로에서 일괄 처리 가능.

본 스킬은 [[CONTEXT/dec-schema]] §4 승인 워크플로의 4-2 (CLI 일괄) 진입점이다.

---

## 입력 파라미터

```
/dec-approve {DEC-ID,...}              # 다건 ✅ 승인 (콤마 구분)
/dec-approve --all-pending             # 모든 ⬜ → ✅
/dec-approve --all-hold                # 모든 🟡 → ✅
/dec-approve DEC-079 --reject "사유"   # 단건 ❌ 반려 (사유 필수)
/dec-approve DEC-080 --hold            # 단건 🟡 보류 (다음 세션까지 결정 필요)
/dec-approve --list                    # 미승인·보류 DEC 목록만 출력 (변경 없음)
```

- `--reject` 사용 시 `사유` 인자 필수 (`❌ {pm_id}: {사유}` 형식)
- `--hold` 는 명시적 보류 의사 표시 — 다음 세션 `/sc` 에서 재확인 강제
- 다건 옵션과 `--reject`/`--hold` 는 상호 배타적

---

## 전제조건 검사

1. `PROJECTS/{product}/decisions.md` 존재 확인. 없으면 PM에게 프로젝트 경로 확인 요청.

2. DEC 표 파싱 — 헤더 `| ID | 일자 | 도메인 | 핵심 결정 | 번복 | 승인 | 근거(스킬·세션) |` 가 존재하는지 확인.
   없으면 [[CONTEXT/dec-schema]] 형식으로 `decisions.md` 마이그레이션이 필요함을 안내하고 중단.

3. `freeze: true` 헤더 라인 확인. frozen 상태면 새 freeze 차수 진입 또는 `freeze: false` 해제가 선행되어야 함을 안내하고 중단.

4. PM 식별자 확인 — 환경변수 `ORANGE_PM_ID` 또는 사용자 입력으로 가져온다. 없으면 PM에게 입력 요청.

---

## 실행 단계

### 단계 1 — 표 파싱 및 대상 행 식별

`decisions.md` 의 DEC 표를 파싱해 모든 행을 메모리에 로드한다.

대상 행 결정:
- `{DEC-ID,...}` 지정: 해당 ID 행만 (미존재 ID는 경고 후 스킵)
- `--all-pending`: `승인` 셀이 `⬜` 인 모든 행
- `--all-hold`: `승인` 셀이 `🟡` 인 모든 행
- `--list`: 미승인(`⬜`) + 보류(`🟡`) 모든 행 (변경 없음, 출력만)

대상 행이 0건이면 "처리 대상 없음" 출력 후 중단.

### 단계 2 — 변경 미리보기 출력

```
승인 처리 예정: {N}건

ID         | 도메인 | 핵심 결정                          | 현재   | 변경 후         | 근거
-----------|--------|------------------------------------|--------|-----------------|----------------
DEC-077    | 🎯     | 카드 그림자 z-index +1             | ⬜     | ✅ {pm_id}      | /critique r2
DEC-078    | 💰     | 약정 30% → 35%                     | ⬜     | ✅ {pm_id}      | /su mattermost
DEC-079    | 🏗️     | 마이크로프론트엔드 도입            | ⬜     | ❌ {pm_id}: ... | /write WO-POL-01

진행하시겠습니까? [Y/n]:
```

PM `Y` 응답 시 단계 3 진행. `N` 시 변경 없이 중단.

`--list` 옵션은 단계 2까지만 수행하고 종료.

### 단계 3 — 표 행 갱신

각 대상 행의 `승인` 셀을 다음 규칙으로 갱신:

| 옵션 | 변경 |
|---|---|
| (기본) | `⬜` 또는 `🟡` → `✅ {pm_id}` |
| `--reject "사유"` | `⬜` 또는 `🟡` → `❌ {pm_id}: {사유}` |
| `--hold` | `⬜` → `🟡 보류` (이미 🟡 이면 변경 없음) |

`Edit` 도구로 `decisions.md` 의 해당 행을 원자적으로 교체한다.
표 외 다른 라인은 절대 건드리지 않는다.

### 단계 4 — 후속 트리거 안내

처리 결과 요약:
```
✅ 승인: {N}건
❌ 반려: {N}건
🟡 보류: {N}건
─────────────
미승인 잔존(⬜): {N}건
보류 잔존(🟡): {N}건
```

미승인·보류 잔존이 있으면:
- 다음 세션 `/sc` 단계 4에서 재확인됨을 안내
- `/confirm` 진입은 잔존 0건 필수임을 경고 ([[CONTEXT/dec-schema]] §4-3)

승인된 DEC 중 `번복` 칼럼에 supersede 대상이 있으면:
- 기존 DEC 행의 `핵심 결정` 셀이 `~~strikethrough~~` 처리되어 있는지 확인
- 미처리 시 자동으로 strikethrough 적용

승인된 DEC 의 `핵심 결정` 셀에 `🔒` 마커가 있으면 (= **hard DEC / 게이트 결정**):
- 이 DEC 는 단순 기록이 아니라 **게이트가 강제**하는 차단선이다
  (fix-plan-track-routing P2). `/lc` 의 track-gate 와 `/graph-gen`·`/fanout` 전제조건이
  이 행을 읽어 모순 동작을 차단한다.
- 트랙·작성모델 관련 hard DEC(예: `🔒 section WO 폐기·dossier 정본`) 승인 시,
  `graph/project-mode.json` 의 트랙 값과 일관되는지 확인하고 불일치하면 PM 에게
  고지한다(기계 마커와 결정 원장의 SSoT 일치).

### 단계 5 — session-log.md 기록

```markdown
- {날짜} /dec-approve: 승인 {N}건 / 반려 {N}건 / 보류 {N}건 / 잔존 ⬜{N}+🟡{N}
  처리 DEC: DEC-077,DEC-078,DEC-079
```

---

## 권한 경계

- 본 스킬은 `decisions.md` 의 **`승인` 칼럼만** 수정한다.
- 다른 칼럼(`ID`·`일자`·`도메인`·`핵심 결정`·`번복`·`근거`)은 절대 수정 불가.
- 표 외 섹션(헤더 메타·Freeze Records)은 읽기만 한다.
- 새 DEC 행 추가는 본 스킬 범위 밖 (등재는 각 등재 스킬 — [[CONTEXT/dec-schema]] §5 등재 권한 매트릭스).

---

## 결과 파일 목록

| 파일 | 변경 내용 |
|---|---|
| `decisions.md` | DEC 표 `승인` 칼럼만 갱신 |
| `session-log.md` | 처리 요약 1줄 추가 |

---

## Workflow Connections

- 선행 스킬 (DEC 등재): [[skills/write]], [[skills/su]], [[skills/sc]], [[skills/critique]], [[skills/integrate]]
- 동결 진입 게이트: [[skills/confirm]] (미승인·🟡 0건 필수)
- 검증 의존: [[agents/integrator]] (I-03), [[agents/reviewer]] (V-01)
- 스키마 SSoT: [[CONTEXT/dec-schema]]
- 운영 규칙: [[CONTEXT/project-rules]]
