---
name: se
description: requirements.md의 FR 항목에서 화면 목록을 추출하고 graph/screen-list.md 초안을 생성한다.
triggers:
  - "se"
  - "screen extract"
  - "extract screens"
phase: any
effort: low
model: haiku
user-invocable: true
---

## ⚠ Phase 5 변경 — 화면 트랙 폐기 / Cluster §2 흡수 (5I)

> **Track A (Full Product) 의 cluster 아키텍처 도입 후**, 별도 screen WO 트랙은
> 폐기되고 cluster draft 의 §2 화면 설계 섹션이 화면설계서(D3) 산출을 책임진다.
> 본 SKILL 은 **Track B/C 와 cluster 미도입 레거시 경로에서만 유효**.

### Track 별 적용 여부

| Track | 본 SKILL 사용 | 화면 분리 단위 | D3 산출 경로 |
|---|---|---|---|
| **A — Full Product (cluster)** | ✗ 폐기 | cluster §2 가 책임 | render `transpose()` → cluster §2 들 어셈블 (publication-map.md) |
| **B — Single Deliverable** | ✓ 단일 D3 작성 시 | 본 SKILL 의 SCR-NNN 분리 그대로 | 단일 페이지 직접 publish |
| **C — Template Copy** | ✓ 단일 D3 작성 시 | 본 SKILL + extracted template | 단일 페이지 직접 publish |
| **Legacy (cluster 미도입 기존 제품)** | ✓ 유지 | 본 SKILL 의 SCR-NNN | 기존 fanout 흐름 |

### 폐기 사유 (사양 토론 결과)

- Cluster + Screen 의 **곱연산** 이 draft 분리 폭증의 핵심 원인 (40~50건 → 14~16건 감소)
- 정책 ↔ UI 결정은 PM 인지상 결합 — 동일 cluster 내 §1+§2 로 다루는 것이 자연스러움
- 화면설계서(D3) 산출은 cluster §2 transpose 로 충분 + 공통 셸은 별도 부록 (publication-map.md §8)

### Cluster 도입 후 화면 ID 부여
- Cluster §2 안에서 SCR-NNN 형식 그대로 유지 (재사용 가능)
- 공통 셸은 `G2-COMMON-{NN}` cluster 의 §2 에서 정의 (D3 부록 어셈블)

### 본 SKILL 이 여전히 호출되는 케이스
- Track B 의 단일 D3 작성 진입 시 (cluster 우회 경로)
- 기존 제품 (cluster 미도입) 의 graph-gen / fanout 흐름 유지
- screen-list.md SSoT 가 필요한 검증 / 보조 작업


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

1. `inputs/requirements.md`가 존재하는지 확인한다.
   없으면 `/draft-req {product}` 실행을 안내하고 중단한다.

2. requirements.md에서 Layer 1 FR 항목이 존재하는지 확인한다.
   없으면 requirements.md 품질 확인을 요청하고 중단한다.

3. `graph/screen-list.md`가 이미 존재하면 두 가지 모드 중 하나를 선택한다:
   - **갱신 모드**: 기존 screen-list.md와 requirements.md를 비교해 누락/추가 화면만 반영
   - **재생성 모드**: screen-list.md를 requirements.md 기준으로 전체 재생성
   PM에게 모드를 확인한다.


## 실행 단계

### 단계 1 — FR 항목에서 화면 단위 분리

requirements.md의 Layer 1 FR 항목 전체를 읽는다.
각 FR 항목을 다음 기준으로 화면 단위로 분리한다:

**화면 분리 기준:**
- 사용자가 직접 진입하거나 전환하는 독립적인 UI 상태
- 하나의 FR이 여러 화면에 걸쳐 있으면 각 화면을 개별 항목으로 분리
- 단순 다이얼로그 / 모달은 부모 화면의 하위 상태로 처리
  (별도 screen_id 대신 부모 screen_id + 상태명으로 표기)

**Screen ID 부여 규칙:**
- 형식: `SCR-NNN` (001부터 순번)
- 기존 screen-list.md가 있으면 기존 ID 체계를 유지하고 신규 항목만 번호를 이어서 부여


### 단계 2 — 디자인 화면 매핑 (선택)

`design` 커넥터(예: Figma — CONNECTORS.md 탐지 프로토콜)가 사용 가능한 경우:
디자인 프로젝트 파일에서 기존 화면 프레임을 조회해
screen-list.md의 각 항목에 디자인 링크를 매핑한다.

매핑 기준:
- 화면명 키워드 일치
- 디자인 프레임 이름에 REQ ID 포함 여부

매핑 불가 항목은 디자인 링크 셀을 `[미매핑]`으로 표기한다.
커넥터 부재·연결 실패 시 `[design 연동 없음 — 탐색 생략]`을 기록하고 계속 진행한다.


### 단계 3 — graph/screen-list.md 작성

```markdown
# 화면 목록 — {product}

> 추출 기준: requirements.md Layer 1 FR
> 생성 기준일: {날짜}
> 총 화면 수: {N}개

| Screen ID | 화면명 | 목적 | 연관 REQ-NNN | 디자인 링크 | 현황 |
|---|---|---|---|---|---|
| SCR-001 | {화면명} | {목적 한 줄} | REQ-NNN | {링크 또는 미매핑} | 신규 / 기존 / 개편 |

## 부모-자식 화면 관계

| 부모 화면 | 하위 상태 (모달/다이얼로그) | 연관 REQ |
|---|---|---|

## 화면 없는 FR 항목

다음 FR 항목은 화면 단위로 분리되지 않는 시스템/백그라운드 동작입니다:

| REQ-NNN | 설명 | 비고 |
|---|---|---|
```

"현황" 항목 분류:
- 신규: product-audit 기존 기능 목록에 없는 화면
- 기존: existing-features.md에 이미 존재하는 화면
- 개편: 기존 화면이지만 요구사항 변경으로 수정 필요


### 단계 4 — 검증: screen-list.md 이미 존재하는 경우

`graph/graph.json`이 존재하면 screen-list.md와 graph.json의 screen 노드를 비교한다:

| 항목 | 기준 | 결과 |
|---|---|---|
| requirements.md FR 대비 화면 수 | 모든 FR에 화면 1개 이상 | PASS / 누락 목록 |
| graph.json screen 노드 대비 화면 수 | screen-list.md = graph.json screen | PASS / 불일치 목록 |
| 고아 화면 (FR 없는 화면) | 0건 | PASS / 목록 |

불일치 항목이 있으면 open-issues.md에 P1으로 등록하고
`/graph-gen {product}` 재실행 여부를 PM에게 확인한다.


### 단계 5 — PM 확인 요청

screen-list.md 요약을 출력하고 PM에게 확인을 요청한다:

```
화면 목록 추출 완료: {product}

  총 화면 수: {N}개
    신규: {N}개
    기존: {N}개
    개편: {N}개
  화면 없는 FR: {N}개
  디자인 링크 미매핑: {N}개

확인 요청:
  1. 누락된 화면이 있으면 알려주세요.
  2. 화면명 또는 목적 수정이 필요하면 알려주세요.
  3. 확인 완료 후 /graph-gen 또는 /fanout을 실행하세요.
```


### 단계 6 — session-log.md 기록

```markdown
- {날짜} /se: 화면 {N}개 추출 (신규 {N} / 기존 {N} / 개편 {N}) / FR 미매핑 {N}건
```


## 결과 파일 목록

| 파일 | 내용 |
|---|---|
| `graph/screen-list.md` | 화면 목록 + REQ 연결 + 디자인 링크 + 현황 |
| `open-issues.md` | graph.json 불일치 시 P1 등록 |
| `session-log.md` | 화면 추출 기록 |


## 다음 단계

screen-list.md PM 확인 완료 후:
- graph.json 미존재: `/graph-gen {product}` (screen-list.md가 참조 입력으로 사용됨)
- graph.json 존재 + 불일치 없음: `/fanout {product}` 바로 진행 가능
- graph.json 존재 + 불일치 있음: `/graph-gen {product}` 재실행 권장
