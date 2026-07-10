---
name: init-hub
description: Planning-Agent-Hub 작업 디렉토리 구조를 초기화하거나 현재 상태를 진단한다. 플러그인 최초 설치 후 가장 먼저 실행해야 하는 스킬이다. 잘못된 작업 디렉토리에서 실행된 경우 올바른 설정 방법을 안내한다.
triggers:
  - "init-hub"
  - "hub 초기화"
  - "초기 설정"
  - "setup hub"
  - "initialize hub"
phase: init
effort: low
model: haiku
user-invocable: true
---

## 단계 1 — 작업 디렉토리 검증

현재 작업 디렉토리에서 다음 항목의 존재 여부를 확인한다.

**Hub 식별 마커 검사:**

| 마커 | 경로 | 존재 여부 |
|---|---|---|
| CONTEXT 디렉토리 | `./CONTEXT/` | 확인 |
| PROJECTS 디렉토리 | `./PROJECTS/` | 확인 |
| layer-config | `./CONTEXT/layer-config.md` | 확인 |
| CLAUDE.md | `./.claude/CLAUDE.md` | 확인 |

**판정 기준:**

- 마커 3개 이상 존재 → Hub 디렉토리에서 실행 중 (정상) → 단계 2로 진행
- 마커 1~2개 존재 → 부분 초기화 상태 → 단계 2에서 누락 항목 보완
- 마커 0개이고 현재 디렉토리 이름이 `orange-pm-plugin`이거나 `skills/` 등 플러그인 내부 경로 → **오류 안내** 출력 후 종료


## 단계 1-E — 잘못된 작업 디렉토리 안내 (오류 경로)

마커가 0개이고 Hub 디렉토리가 아닌 것으로 판단된 경우 다음을 출력한다:

```
⚠️ 잘못된 작업 디렉토리입니다.

현재 위치: {현재 디렉토리 절대 경로}

orange-pm 플러그인은 반드시 Planning-Agent-Hub 디렉토리를
작업 디렉토리로 설정한 상태에서 실행해야 합니다.

올바른 실행 방법:
  1. Claude Code를 종료합니다.
  2. Planning-Agent-Hub 디렉토리에서 Claude Code를 다시 엽니다.
     - VS Code:     code /path/to/Planning-Agent-Hub
     - 터미널:      cd /path/to/Planning-Agent-Hub && claude
     - Claude 앱:   File → Open Folder → Planning-Agent-Hub 선택
  3. 다시 /init-hub 를 실행합니다.

Planning-Agent-Hub 디렉토리가 없는 경우:
  - 빈 디렉토리를 만들고 그 안에서 Claude Code를 열면
    /init-hub 가 전체 구조를 자동으로 생성합니다.
```

종료한다. 이후 단계를 실행하지 않는다.


## 단계 2 — Hub 구조 진단

현재 Hub의 초기화 상태를 점검한다.

**CONTEXT/ 항목 검사:**

| 파일 | 존재 여부 | 비고 |
|---|---|---|
| `CONTEXT/layer-config.md` | 확인 | PREFIX 설정 |
| `CONTEXT/about-pm.md` | 확인 | PM 프로필 |
| `CONTEXT/project-rules.md` | 확인 | 기획 원칙 |
| `CONTEXT/brand-voice.md` | 확인 | 문서 톤 |
| `CONTEXT/team-members.md` | 확인 | 이해관계자 |
| `CONTEXT/ssot-boundary.yml` | 확인 | SSoT 경계 (render --check-ssot) |
| `CONTEXT/connectors.md` | 확인 | 외부 연동 매핑 (선택) |
| `CONTEXT/gates/discovery-exit-gate.md` | 확인 | Phase 게이트 |
| `CONTEXT/gates/policy-entry-gate.md` | 확인 | Phase 게이트 |
| `CONTEXT/gates/graph-exit-gate.md` | 확인 | Phase 게이트 |
| `CONTEXT/gates/draft-complete-gate.md` | 확인 | Phase 게이트 |
| `CONTEXT/gates/integration-exit-gate.md` | 확인 | Phase 게이트 |

**templates/ 항목 검사:**

| 파일 | 존재 여부 | 비고 |
|---|---|---|
| `templates/graph-schema.json` | 확인 | 그래프 스키마 |
| `templates/work-order-template.md` | 확인 | WO 포맷 |

**PROJECTS/ 항목 검사:**

| 항목 | 내용 |
|---|---|
| 등록된 프로젝트 수 | `PROJECTS/` 하위 디렉토리 수 |
| 각 프로젝트 Phase | `session-log.md` 마지막 행의 Phase |


## 단계 3 — 누락 구조 생성

단계 2에서 누락으로 확인된 항목을 생성한다.
이미 존재하는 파일은 절대 덮어쓰지 않는다.

### 3-A. 디렉토리 생성

누락된 디렉토리를 생성한다:

```
CONTEXT/
└── gates/
PROJECTS/
templates/
.claude/
```

### 3-B. CONTEXT 파일 생성

**`CONTEXT/layer-config.md`** (없는 경우에만):

```markdown
# 계층 아키텍처 설정

## 부서 Prefix 설정 (멀티-PREFIX)
# PREFIX 별로 A/B/C 를 완전 독립 보유한다. ACTIVE_PREFIX 가 현재 작업 대상.
PREFIXES:
  - id: (설정 필요)
    label: (설정 필요)
# 부서/제품군 추가 예: PA(제품군A) / PB(제품군B) / SaaS / OSS

ACTIVE_PREFIX: (설정 필요)

# 레거시 호환: 단일 PREFIX 만 읽는 구버전 도구용. ACTIVE_PREFIX 와 동기 유지.
PREFIX: (설정 필요)

## 외부 연동
# 위키·메신저·디자인툴 등 외부 연동 매핑은 CONTEXT/connectors.md 에 선언한다.
# (연동 없이도 전체 워크플로우는 로컬로 동작한다 — CONNECTORS.md 규약 참조)

## {PREFIX}-A: 공통 정의
| doc_id | 문서 제목 | 상태 |
|---|---|---|
| {PREFIX}-A-001 | 용어 사전 | Draft |
| {PREFIX}-A-002 | 상태 레퍼런스 | Draft |
| {PREFIX}-A-003 | 오류 코드 정의 | Draft |
| {PREFIX}-A-004 | 네이밍 컨벤션 | Draft |

## {PREFIX}-B: 공통 정책
| doc_id | 문서 제목 | 상태 |
|---|---|---|
| {PREFIX}-B-001 | 계정·그룹·프로젝트 정책 | Draft |
| {PREFIX}-B-002 | 서비스 신청·해지 정책 | Draft |
| {PREFIX}-B-003 | 자원·한도 정책 | Draft |
| {PREFIX}-B-004 | 상품 기본 정책 | Draft |
| {PREFIX}-B-005 | 요금 계산 정책 | Draft |
| {PREFIX}-B-006 | 청구서 정책 | Draft |
| {PREFIX}-B-007 | 결제 방식 정책 | Draft |
| {PREFIX}-B-008 | 할인 플랜 | Draft |

## {PREFIX}-C: 재사용 블록
| doc_id | 문서 제목 | 상태 |
|---|---|---|
| {PREFIX}-C-001 | LNB 공통 모듈 | Draft |
| {PREFIX}-C-002 | 이메일·SMS 발송 모듈 | Draft |
| {PREFIX}-C-003 | 로그인 페이지 모듈 | Draft |
| {PREFIX}-C-004 | OTP 공통 인증 모듈 | Draft |

## 가중치 규칙
Approved: 1.0 / Draft: 0.3 / Deprecated: 0 (색인 제외)

## doc_id 생성 규칙
형식: {PREFIX}-C-{PRODUCT_CODE}-{SEQ:003d}
예시: {PREFIX}-C-DBAAS-001
```

`layer-config.md`가 새로 생성된 경우, PM에게 다음 항목 입력을 요청한다:
1. PREFIXES — 작업할 제품군 목록 (id + label). 단일이면 1개만. 예: `PA/제품군A`, `PB/제품군B`
2. ACTIVE_PREFIX — 현재 세션 작업 대상 (PREFIXES 중 하나). PREFIX 라인도 동일하게 설정.
3. 외부 시스템 연동을 사용할 경우 — `CONTEXT/connectors.md`의 capability 매핑 (선택)

**`CONTEXT/about-pm.md`** (없는 경우에만):

```markdown
# PM 프로필

## 기본 정보
- 이름: (입력 필요)
- 소속: (입력 필요)
- 역할: Product Manager

## 작업 스타일
- (입력 필요)

## 선호 사항
- (입력 필요)
```

**`CONTEXT/project-rules.md`** (없는 경우에만):

```markdown
# 기획 원칙

## 버전 관리 원칙
- 모든 정책 문서는 v0.x (초안) → v1.0 (확정) 순으로 진행한다.
- v1.0 확정 후 변경 시 decisions.md에 이유를 기록한다.

## 결정 원칙
- decisions.md에 기록된 항목은 번복하지 않는다.
- 번복 필요 시 새 항목 추가.

## 동기화 원칙
- /cr 실행 후 위키(wiki 커넥터)와 로컬 파일을 항상 동기화한다.
- /su 실행 후 팀 메신저(chat 커넥터) 이해관계자 공지를 완료한다.
```

**`CONTEXT/brand-voice.md`** (없는 경우에만):

```markdown
# 문서 톤 기준

## 기본 원칙
- 간결하고 명확하게 작성한다.
- 기술적 용어는 {PREFIX}-A-001 용어 사전을 기준으로 한다.
- 수동태보다 능동태를 사용한다.

## 금지 표현
- (입력 필요)

## 권장 표현
- (입력 필요)
```

**`CONTEXT/team-members.md`** (없는 경우에만):

```markdown
# 이해관계자 목록

| 이름 | 소속 / 역할 | 담당 프로젝트 | 연락처 |
|---|---|---|---|
| (입력 필요) | | | |
```

**`CONTEXT/ssot-boundary.yml`** (없는 경우에만):

```yaml
# SSoT 경계 선언 (Single Source of Truth boundary)
#
# 어떤 doc 유형이 어떤 값의 "원본(SSoT)"을 소유하는지 선언한다.
# render --check-ssot 가 이 파일을 읽어, 제품 Delta({PREFIX}-C)가
# 다른 doc 유형이 소유한 값을 재정의하면 SSoT 위반으로 차단한다.
#
# - design_tokens: HEX/px 등 디자인 토큰의 SSoT (보통 화면설계 doc/D2·D3)
# - policy_values: 한도·요금·정책 값의 SSoT (보통 공통 정책 {PREFIX}-B)
# 값이 비어 있거나 파일이 없으면 --check-ssot 는 경고만 하고 통과한다(graceful).

design_tokens:
  owner: ""        # 예: D2 (화면설계서) — HEX/px 디자인 토큰 원본
  patterns:        # SSoT 로 간주할 값 패턴 (정규식, 선택)
    - "#[0-9A-Fa-f]{6}"
    - "\\d+px"

policy_values:
  owner: ""        # 예: {PREFIX}-B (공통 정책) — 한도·요금 등 정책 값 원본
  patterns: []
```

**`CONTEXT/connectors.md`** (없는 경우에만):

```markdown
# Connector 매핑

외부 시스템 연동은 사용자가 Claude Code에 연결한 MCP 서버/커넥터를 자동 탐지해 사용한다.
같은 capability의 도구가 여럿이거나 특정 도구를 강제하려면 아래 표에 선언한다.
비워 두면 자동 탐지, 도구가 없으면 해당 단계는 생략되고 로컬로 진행된다.
(규약 상세: 플러그인 CONNECTORS.md)

| capability | 도구/서버 이름 | 비고 |
|---|---|---|
| wiki   | | 게시 대상 스페이스/상위 페이지: |
| chat   | | 기본 채널: |
| design | | |
| repo   | | |
| tasks  | | |
```

### 3-C. Gates 파일 생성

**`CONTEXT/gates/discovery-exit-gate.md`** (없는 경우에만):

```markdown
# Discovery Exit Gate

검증 시점: /research · /stakeholder · /product-audit 완료 → /draft-req 실행 허가

| 항목 | 기준 |
|---|---|
| inputs/discovery/competitor/ | 파일 1개 이상 + overview.md 매트릭스 행 3개 이상 |
| inputs/discovery/stakeholder/ | 파일 1개 이상 + overview.md 이해관계자 2명 이상 / 요구사항 5개 이상 |
| inputs/discovery/product-audit/ | 파일 1개 이상 |
| open-issues.md P0 | 0건 |
```

**`CONTEXT/gates/policy-entry-gate.md`** (없는 경우에만):

```markdown
# Policy Entry Gate

검증 시점: /draft-req 완료 → /graph-gen 실행 허가

| 항목 | 기준 |
|---|---|
| requirements.md Layer 1 (FR) | 10개 이상 |
| requirements.md Layer 2 (NFR) | 5개 이상 |
| requirements.md Layer 4 (액터) | 정의 완료 |
| requirements.md Layer 5 (외부 연동) | 목록 존재 |
| FR 항목 화면 단위 분리 가능 여부 | 전수 확인 완료 |
| {PREFIX}-A/B URL | layer-config.md에 등록 |
| open-issues.md P0 | 0건 |
```

**`CONTEXT/gates/graph-exit-gate.md`** (없는 경우에만):

```markdown
# Graph Exit Gate

검증 시점: /graph-gen 완료 → /fanout 실행 허가

| 항목 | 기준 |
|---|---|
| graph/graph.json | 파일 존재 |
| graph/screen-list.md | 파일 존재 |
| validate_graph.py 결과 | PASS 기록 존재 (session-log 또는 decisions) |
| PM 승인 기록 | decisions.md에 /graph-gen 완료 기록 |
| open-issues.md P0 | 0건 |
```

**`CONTEXT/gates/draft-complete-gate.md`** (없는 경우에만):

```markdown
# Draft Complete Gate

검증 시점: Phase 2 전체 WO 초안 완성 → /integrate 실행 허가

| 항목 | 기준 |
|---|---|
| drafts/ policy WO | index.md 전체 policy WO에 draft 파일 존재 |
| drafts/ screen WO | index.md 전체 screen WO에 draft 파일 존재 |
| open-issues.md P0 | 0건 |
```

**`CONTEXT/gates/integration-exit-gate.md`** (없는 경우에만):

```markdown
# Integration Exit Gate

검증 시점: /integrate PASS → /confirm 실행 허가

| 항목 | 기준 |
|---|---|
| reports/integration-summary.md | 파일 존재 |
| BLOCK 건수 | 0건 |
| decisions.md Phase 4 허가 기록 | 존재 |
| open-issues.md P0 | 0건 |
```

### 3-D. templates/ 파일 생성

**`templates/graph-schema.json`** (없는 경우에만):

> **정합 주의 (감사 2026-06-08 H5):** 본 스키마는 `validate_graph.py` 의 실제
> 검증 계약과 **반드시 일치**해야 한다. 정본 graph.json 은 `{ "graph": { "metadata",
> "nodes": {객체}, "edges": [배열] } }` envelope 이며, `nodes` 는 노드명→노드 객체의
> **딕셔너리**(배열 아님), `node_type` 은 `policy | screen`, 엣지는 `source`/`target`/
> `type`(+ 선택 `source_section`/`target_section`)을 쓴다. 아래 스키마는 그 형상을
> 따른다. (validate_graph.py: `VALID_NODE_TYPES`·`VALID_EDGE_TYPES`·`_minimal_schema_check`)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "PM Planning Graph Schema",
  "type": "object",
  "required": ["graph"],
  "properties": {
    "graph": {
      "type": "object",
      "required": ["metadata", "nodes", "edges"],
      "properties": {
        "metadata": { "type": "object" },
        "nodes": {
          "type": "object",
          "description": "노드명 → 노드 객체 매핑 (배열 아님)",
          "additionalProperties": {
            "type": "object",
            "properties": {
              "node_type": { "type": "string", "enum": ["policy", "screen"] },
              "sections": {
                "type": "object",
                "description": "policy 노드: 섹션ID → {title, summary, ...}. screen 노드는 미보유.",
                "additionalProperties": { "type": "object" }
              },
              "inherits_from": { "type": "array", "items": { "type": "string" } },
              "fr_refs": { "type": "array", "items": { "type": "string" } },
              "capability": { "type": "string" },
              "cluster_id": { "type": "string" },
              "screen_name": { "type": "string" },
              "purpose": { "type": "string" },
              "req_id": { "type": "string" }
            }
          }
        },
        "edges": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["source", "target", "type"],
            "properties": {
              "source": { "type": "string" },
              "target": { "type": "string" },
              "source_section": { "type": "string" },
              "target_section": { "type": "string" },
              "type": {
                "type": "string",
                "enum": [
                  "전제조건", "양방향참조", "중복정의", "기능연동",
                  "이벤트정의", "보안기준", "implements",
                  "용어기준", "UX기준", "과금대상", "운영절차"
                ]
              }
            }
          }
        }
      }
    }
  }
}
```

**`templates/work-order-template.md`** (없는 경우에만):

```markdown
# Work Order — {PREFIX}-C-{PRODUCT}-{SEQ}

## Section 0. 문서 식별

| 항목 | 값 |
|---|---|
| doc_id | {PREFIX}-C-{PRODUCT}-{SEQ} |
| 유형 | policy / screen |
| 상태 | Draft |
| 생성일 | {UTC 날짜} |

### 0-1. 상속 관계

| 관계 유형 | 대상 doc_id |
|---|---|
| inherits_from | |
| includes | |

### 0-2. Delta 범위

공통 정책({PREFIX}-B)과 다른 예외 사항만 기술한다.
예외 없으면 "기본 정책 완전 적용" 한 줄로 처리한다.

## Section 1. 범위 및 목적
## Section 2. 입력 조건
## Section 3. 계약 조건
## Section 4. 작업 항목
- [ ]
## Section 5. 검증 기준
## Section 6. 금지 사항
```

### 3-E. `.claude/CLAUDE.md` 생성

**`.claude/CLAUDE.md`** (없는 경우에만):

```markdown
# Global Instructions

## 역할 선언
이 에이전트는 PM 기획팀의 파트너다.
{PREFIX}-C (제품 명세) 계층 문서를 작성하는 것이 역할이다.
{PREFIX}-A/B/C 상위 계층 문서는 읽기만 하고 수정하지 않는다.

## decisions.md 절대 규칙
decisions.md에 기록된 항목은 수정을 제안하지 않는다.
번복이 필요한 경우 PM이 직접 삭제 후 지시한다.

## SSoT 원칙
{PREFIX}-B에 있는 내용을 {PREFIX}-C에 재작성하지 않는다.
중복 정의 발견 시 즉시 PM에게 보고한다.

---
# Folder Instructions

## 작업 진입 규칙
세션 시작 시 아래 순서로 파일을 읽는다.
1. CONTEXT/layer-config.md       → PREFIX 값 추출
2. CONTEXT/about-pm.md           → PM 작업 스타일 로드
3. CONTEXT/project-rules.md      → 기획 원칙 로드
4. CONTEXT/brand-voice.md        → 문서 톤 기준 로드
5. CONTEXT/team-members.md       → 이해관계자 목록 로드
6. CONTEXT/connectors.md         → 외부 연동 매핑 로드 (있는 경우)
7. PROJECTS/{프로젝트명}/session-log.md, decisions.md, open-issues.md

## Phase별 허용 스킬
Phase -1: /discover /research /stakeholder /product-audit /draft-req
Phase  0: /ingest /graph-gen
Phase  1: /fanout
Phase  2: /explore /write /flow /screen-detail /review /render
Phase  3: /integrate
Phase  4: /confirm → /cr → /su
언제든지: /se /sc /lc /plan-audit /render /init-hub

## 운영 규칙
1. PREFIX 확인 우선
2. SSoT 준수
3. Delta 원칙 — 공통 정책 예외 사항만 기술
4. decisions.md 절대 규칙
5. 3라운드 수렴 원칙
6. 세션 단위 원칙 — Work Order 1건 = 1 세션, 완료 후 /sc 실행
```


## 단계 4 — PREFIX 설정 안내

`CONTEXT/layer-config.md`에 PREFIX가 `(설정 필요)` 상태인 경우 PM에게 입력을 요청한다:

1. **PREFIX** — 부서/제품군 코드 (예: `PA`, `PB`, `S1`)


## 단계 5 — 외부 연동(커넥터) 상태 안내

현재 세션에서 사용 가능한 MCP 도구를 capability별로 점검하고 결과를 출력한다
(탐지 기준: 플러그인 CONNECTORS.md 규약):

```
외부 연동 상태 (선택 사항 — 없어도 전체 워크플로우는 로컬로 동작합니다)

  wiki   (문서 게시·조회)   : {탐지된 도구 또는 "미연결"}
  chat   (메신저 조회·알림) : {탐지된 도구 또는 "미연결"}
  design (디자인 파일 조회) : {탐지된 도구 또는 "미연결"}
  repo   (MR/이슈)          : {탐지된 도구 또는 "미연결"}
  tasks  (일정·업무)        : {탐지된 도구 또는 "미연결"}

연동을 추가하려면 Claude Code에 MCP 서버를 연결하세요:
  claude mcp add <name> ...      (또는 Claude 설정 → Connectors)
특정 도구를 강제하려면 CONTEXT/connectors.md 에 매핑을 선언하세요.

미연결 시 영향: /cr(원격 게시)·/su 는 안내 후 중단, 그 외 스킬은
해당 소스 탐색만 생략하고 진행합니다.
```


## 단계 5-B — 컨텍스트 캐시 생성 (개선안 A·B·F — CONTEXT_OPTIMIZATION.md)

세션 첫 진입 시 모든 skill 이 동일한 컨텍스트를 반복 로드하지 않도록
다음 캐시를 생성한다. PREFIX 가 설정된 경우에만 실행하며, 캐시는
ACTIVE_PREFIX 기준으로 네임스페이스(`{PREFIX}-...`)된다.

```bash
# F. CONTEXT 6개 파일 → _session-bootstrap.md 통합본
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .

# A. {ACTIVE_PREFIX}-B 공통 정책 요약 캐시 (.template-cache/{PREFIX}-b-summary.md)
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_cache.py --hub-root .

# B. {ACTIVE_PREFIX}-B 헤딩 인덱스 (.template-cache/{PREFIX}-b-headings-index.json)
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_index.py --hub-root .

# A-idx. {ACTIVE_PREFIX}-A 용어 역인덱스 (.template-cache/{PREFIX}-a-terms-index.json)
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_a_index.py --hub-root .

# C-idx. 전 PREFIX C 서비스 마스터 인덱스 (.template-cache/c-master-index.json)
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_c_index.py --hub-root .
```

각 스크립트는 멱등하다. 원본보다 mtime 이 오래된 캐시만 재생성하므로
반복 실행해도 비용이 거의 없다. `reference-docs/{ACTIVE_PREFIX}/B/` 가 비어 있으면 A·B는
경고 후 건너뛰고 진행한다. PREFIX 전환 시 `ACTIVE_PREFIX` 변경 후 위 캐시를 재생성한다.
(`build_b_*` 는 하위호환을 위해 무네임스페이스 `B-summary.md`·`B-headings-index.json`
미러도 함께 기록한다.)

생성 결과:

| 캐시 파일 | 용도 |
|---|---|
| `CONTEXT/_session-bootstrap.md` | 모든 skill 의 세션 1회 컨텍스트 로드 진입점 |
| `CONTEXT/.template-cache/B-summary.md` | `/write`, `/flow`, `/integrate` 의 {PREFIX}-B 캐시 우선 로드 |
| `CONTEXT/.template-cache/B-headings-index.json` | 섹션별 발췌 로드 (line_start/line_end) |

> 이 캐시는 `.template-cache/` 디렉토리에 있어 git 추적에서 제외하는 것을 권장한다.
> 필요 시 `.gitignore` 에 `Planning-Agent-Hub/CONTEXT/.template-cache/` 추가.


## 단계 6 — 최종 진단 출력

```
Planning-Agent-Hub 초기화 완료

  디렉토리:      {현재 작업 디렉토리}
  PREFIX:        {PREFIX 값 또는 "(설정 필요)"}
  커넥터:        {연결된 capability 목록 또는 "없음 (로컬 전용)"}

  CONTEXT 파일:
    layer-config.md        {존재 / 새로 생성}
    about-pm.md            {존재 / 새로 생성}
    project-rules.md       {존재 / 새로 생성}
    brand-voice.md         {존재 / 새로 생성}
    team-members.md        {존재 / 새로 생성}
    ssot-boundary.yml      {존재 / 새로 생성}
    connectors.md          {존재 / 새로 생성}
    gates/ (5개 파일)       {존재 / 새로 생성}

  templates/:
    graph-schema.json      {존재 / 새로 생성}
    work-order-template.md {존재 / 새로 생성}

  .claude/CLAUDE.md:       {존재 / 새로 생성}

  컨텍스트 캐시 (개선안 A·B·F):
    _session-bootstrap.md          {생성 / 최신}
    .template-cache/B-summary.md   {생성 / 최신 / N/A}
    .template-cache/B-headings-index.json {생성 / 최신 / N/A}

  등록된 프로젝트:
    {프로젝트 목록 또는 "없음"}

다음 단계:
  {PREFIX 미설정}     → layer-config.md 에서 PREFIX 입력 (연동은 connectors.md — 선택)
  {프로젝트 없음}     → /discover {product명} 으로 첫 프로젝트를 시작하세요
  {프로젝트 있음}     → /lc {product명} 으로 현재 Phase를 확인하세요
```


## 다음 단계

Hub 초기화 완료 후 첫 프로젝트를 시작하려면:

```
/discover {product}
```
