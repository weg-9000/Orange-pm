<!--
  spec-catalog 작성 양식 (PROJECTS/{product}/inputs/spec-catalog.md 의 원본)
  - 산출 위치: PROJECTS/{product}/inputs/spec-catalog.md (Confluence 발행 대상 아님 — 프로젝트 inputs 작업 산출물)
  - 생산자: synthesizer (/draft-req). 소비자: reviewer(V-06), write·write-cluster·flow·screen-detail([[spec-catalog 변수ID]]), formula-binding(계산형)
  - 제품의 모든 입력 변수를 이 문서에서 단 한 번 정의한다(C1 SSoT). 정책서·화면서는 변수ID 인용·링크만 한다.
  - {중괄호} placeholder 는 실제 값으로 치환하고, 빈 칸은 금지 — 미상 값은 [확인필요:사유] 로 기재 후 open-issues 등록.
-->
---
doc_id: {PREFIX}-C-{PRODUCT_CODE}-SPEC-CATALOG
title: 입력 변수 카탈로그 (SSoT)
status: draft
mode: calculation | console   # calculation=요금 산식형 / console=입력 유효성형
referenced_master: [{PREFIX}-B-002@v1.3, {PREFIX}-A-001@v1.1]
last_updated: YYYY-MM-DD
---

# 입력 변수 카탈로그 — {제품명}

> **C1 SSoT**: 제품의 모든 입력 변수는 이 문서에서 **단 한 번** 정의한다.
> 정책서·화면서는 변수ID를 인용·링크만 하며 재정의하지 않는다.
> **C5 원천 추적성**: 모든 행의 `출처`는 공통(G2-B §X) 인용 또는 `제품 Delta`
> 또는 `[확인필요:사유]` 셋 중 하나. **추정·환각 채움 금지**(빈 칸 금지).

## 사용 모드

| mode | 용도 | formula-binding |
|---|---|---|
| `calculation` | 요금 산식형 제품(예: 계산기). 변수↔산식 1:1(C2) | 필요(WP5) |
| `console` | 콘솔형 제품. 입력 유효성 단일 출처(중복 재기재 차단) | 불요 |

---

## {서비스/엔티티명 — G2-A-001 정본 용어}

| 필드명(변수ID) | 입력유형 | 기본값 | 범위/옵션 | 단위 | UI 안내문구 | 오류 메시지 | 출처 |
|---|---|---|---|---|---|---|---|
| `{variable_id}` | Number/Select/Text/Checkbox | {기본값} | {min~max 또는 옵션} | {GB/건/월/…} | "{안내}" | "{오류}" | `{PREFIX}-B-002 §B-2` |
| `{variable_id}` | Number | `[확인필요:원천없음]` | — | — | — | — | `open-issues {ISSUE-ID}` |

### 종속·플래그
- requires: [`{variable_id}`]
- suggests: [`{variable_id}`]
- 약정 대상: Y/N    · 과금 단위: 시간/일/월/건/없음

### JSON 변환 구조
```json
{ "{variable_id}": "<타입>" }
```

---

## 출처 표기 규칙 (C0·C5)

| 표기 | 의미 | 처리 |
|---|---|---|
| `{PREFIX}-B-NNN §X` | 공통 정책 파생 — 값 복사 금지, 링크 참조만 | C0 준수 |
| `제품 Delta` | 공통에 없는 이 제품 고유 정의 | decisions.md 근거 권장 |
| `[확인필요:사유]` | 원천 미확보 — 추정 금지, open-issues 등록 | source-input-gate 추적 |

## Workflow Connections
- 용어 정본: [[G2-A 용어 규칙]]
- 공통 정책: [[G2-B_상품요금결제정책]]
- 산식 바인딩(계산형): [[formula-binding-template]]
- 적용 스킬: [[draft-req]], [[write]], [[review]]
