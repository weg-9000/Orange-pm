---
name: explore
description: >-
  query를 파싱해 로컬 파일과 사용자가 연결한 커넥터(chat·design·tasks — 예: Mattermost·Figma·Jira 등)에서 맥락을 수집하고 교차 검증된 구조화 보고서를 생성한다. Discovery, draft 작성, 검토 단계 어디서든 독립적으로 호출 가능하다.
triggers:
  - "explore"
  - "search context"
  - "find info"
agent: explorer
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

1. `{query}`가 비어 있으면 탐색 목적을 PM에게 질문한다.
   예시 형식을 제시한다:
   - 기능 관련: `/explore 결제 취소 정책 범위`
   - 정책 관련: `/explore {PREFIX}-B 환불 기준`
   - UI 관련: `/explore 주문 목록 화면 레이아웃`
   - 이슈 관련: `/explore WO-07 미결 사유`

2. 현재 프로젝트 컨텍스트를 확인한다.
   `CONTEXT/layer-config.md`에서 활성 프로젝트 PREFIX를 읽는다.
   확인 불가 시 전체 스코프 탐색으로 진행한다.


## 실행 단계

### 단계 1 — 쿼리 분류

`{query}` 텍스트를 분석해 탐색 의도를 분류한다:

| 의도 유형 | 판단 기준 | 우선 탐색 소스 |
|---|---|---|
| 기능 요구사항 | 기능명, 동작, 사용자 행동 포함 | requirements.md → competitor/ → wiki |
| 정책·규칙 | 정책, 기준, 제한, 금지 포함 | decisions.md → CONTEXT/reference-docs/{ACTIVE_PREFIX}/B/ 로컬 파일 |
| 화면·UX | 화면, 레이아웃, 버튼, 상태 포함 | screen-list.md → design → drafts/ |
| 이슈·의사결정 | WO ID, 이슈, 미결, 번복 포함 | open-issues.md → session-log.md → chat |
| 일정·담당 | 일정, 마감, 담당자 포함 | tasks → chat |
| 전체 탐색 | 분류 불가 | 전체 소스 순차 탐색 |

분류 결과를 탐색 시작 전 한 줄로 출력한다.


### 단계 2 — 로컬 파일 탐색

다음 파일을 query 키워드로 검색한다. 탐색 우선순위 순서:

```
1. PROJECTS/{product}/inputs/requirements.md
2. PROJECTS/{product}/decisions.md
3. PROJECTS/{product}/open-issues.md
4. PROJECTS/{product}/inputs/research.md
5. PROJECTS/{product}/graph/screen-list.md
6. PROJECTS/{product}/drafts/*.draft.md
7. PROJECTS/{product}/inputs/discovery/**/*.md
8. CONTEXT/layer-config.md
```

각 파일에서 발견된 항목을 다음 태그로 분류한다:
- `[확정]`: decisions.md에 등재되거나 v1.0-frozen draft에 있음
- `[초안]`: draft에 있으나 미확정
- `[번복 이력]`: 동일 키워드가 decisions.md에서 변경된 흔적 있음


### 단계 3 — 로컬 reference-docs 탐색

`CONTEXT/reference-docs/{ACTIVE_PREFIX}/A|B|C/` 디렉토리에서
query와 관련된 파일을 로드한다.
파일 미존재 시 `[해당 계층 파일 없음 — 로컬 결과만 사용]`
안내를 표시하고 계속 진행한다.
이 단계에서 wiki 커넥터는 호출하지 않는다.


### 단계 4 — chat 커넥터 탐색

chat 커넥터(사용자가 연결한 MCP 도구 — 예: Slack·Mattermost 등)를 CONNECTORS.md
탐지 프로토콜로 확인하고, 프로젝트 관련 채널에서 `{query}` 키워드를 검색한다.
검색 범위: 최근 90일 메시지.
커넥터 부재 또는 연결 실패 시 건너뛰고 `[chat 탐색 생략]`을 기록한다.

의사결정 관련 메시지 발견 시 `[팀 논의]` 태그를 부착한다.
decisions.md에 없는 결정 사항이 발견되면 `open-issues.md` P2 등록을 권고한다.


### 단계 5 — design 커넥터 탐색 (의도 유형이 화면·UX인 경우만)

design 커넥터(사용자가 연결한 MCP 도구 — 예: Figma·Zeplin 등)를 CONNECTORS.md
탐지 프로토콜로 확인하고, 프로젝트 디자인 파일에서 `{query}` 관련 프레임을 검색한다.
커넥터 부재 또는 연결 실패 시 건너뛰고 `[design 탐색 생략]`을 기록한다.

발견된 프레임의 이름, 컴포넌트 목록, 디자인 파일 URL을 출처로 명시한다.


### 단계 6 — tasks 커넥터 탐색 (의도 유형이 일정·담당인 경우만)

tasks 커넥터(일정·업무 도구 — 예: Jira·그룹웨어 등)를 CONNECTORS.md
탐지 프로토콜로 확인하고, 관련 프로젝트 태스크와 담당자를 검색한다.
커넥터 부재 또는 연결 실패 시 건너뛰고 `[tasks 탐색 생략]`을 기록한다.


### 단계 7 — 교차 검증 및 결과 구성

소스별 발견 항목을 교차 검증한다:

- 동일 항목이 여러 소스에서 일치하면 `[다중 소스 확인]` 태그 부착
- 소스 간 내용이 상충하면 `[소스 간 충돌]` 태그 부착 + 충돌 내용 병기

탐색 결과가 0건이면 "발견된 항목 없음 — 쿼리를 구체화하거나 소스를 직접 확인하세요"를
출력하고 관련 스킬을 안내한다.


### 단계 8 — 보고서 출력 및 저장

**인라인 출력 형식:**
```markdown
## /explore 결과: {query}

**탐색 의도**: {분류 결과}
**탐색 소스**: {탐색한 소스 목록}
**발견 항목**: {N}건

### 주요 발견 사항

1. {항목 내용} [`{태그}`] — 출처: {파일명 또는 URL}
2. ...

### 소스 간 충돌 항목

{없으면 "없음"}

### 미발견 항목 (탐색 공백)

{query와 관련하여 어떤 소스에도 없는 정보가 있으면 명시}

### 권고 후속 조치

- {예: open-issues.md에 P2 등록 권고}
- {예: /stakeholder {product} 재실행으로 요구사항 보완 권고}
```

**파일 저장:**
`reports/explore-{YYYYMMDD-HHMM}.md`에 위 보고서를 저장한다.


## 결과 파일 목록

| 파일 | 변경 내용 |
|---|---|
| `reports/explore-{YYYYMMDD-HHMM}.md` | 탐색 결과 보고서 |
| `open-issues.md` | 충돌·미등재 결정 사항 발견 시 P1/P2 자동 등록 |
