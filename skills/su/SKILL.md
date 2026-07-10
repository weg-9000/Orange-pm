---
name: su
description: >-
  팀 메신저(chat 커넥터 — 예: Mattermost·Slack) 채널에서 이해관계자의 최신 메시지를 조회한다. 신규 요구사항·결정·질문을 분류하고 관련 파일에 반영 여부를 PM에게 확인한다. 기본 조회 범위는 마지막 /su 실행 이후 또는 최근 7일이다.
triggers:
  - "su"
  - "stakeholder update"
  - "messenger check"
agent: researcher
phase: 4
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
원본 파일 직접 Read 는 본 skill 의 핵심 작업에 필수인 경우에만 허용된다.

## 전제조건 검사

1. `CONTEXT/team-members.md`가 존재하는지 확인한다.
   없으면 팀 구성 파일 미존재를 안내하고 중단한다.

2. chat 커넥터(사용자가 연결한 MCP 도구 — 예: Slack·Mattermost 등)를
   CONNECTORS.md 탐지 프로토콜로 확인한다. 본 스킬은 chat 커넥터 **필수 의존**이다.
   부재 시 CONNECTORS.md의 필수 의존 안내문을 출력하고 중단한다:
   ```
   이 단계는 chat 커넥터가 필요합니다.
   Claude Code에 MCP 서버를 연결하면 자동으로 사용됩니다:
     claude mcp add <name> ...     (또는 Claude 설정 → Connectors)
   연결 후 다시 실행해 주세요.
   ```

3. `--since {날짜}` 옵션이 없으면 session-log.md에서 마지막 /su 실행 시각을 읽는다.
   마지막 실행 기록이 없으면 기본값 7일 전을 조회 시작점으로 설정한다.

4. 조회 시작점을 PM에게 안내한다:
   ```
   조회 범위: {시작일} ~ 현재 ({N}일간)
   ```


## 실행 단계

### 단계 1 — 채널 목록 수집

`CONTEXT/team-members.md`에서 `{product}` 관련 이해관계자의 메신저 채널 정보를 읽는다.

team-members.md 형식 (채널 칼럼명은 메신저 종류에 따라 다를 수 있다 — 예: Mattermost 채널):
```markdown
| 이름 | 팀 | 역할 | 메신저 채널 |
|---|---|---|---|
| {이름} | {팀} | {역할} | {채널명} |
```

채널 정보가 없으면 PM에게 채널명을 직접 입력하도록 요청한다.


### 단계 2 — 메시지 조회

전제조건 검사에서 확인한 chat 커넥터로 각 채널의 메시지를 조회한다.
벤더별 파라미터 차이는 도구 스키마를 읽고 적응한다 (CONNECTORS.md 참조).

조회 조건:
- 기간: {조회 시작점} ~ 현재
- 키워드 필터: 제한 없음 (전체 조회)
- 봇 메시지 및 시스템 메시지 제외

채널당 최대 100개 메시지. 초과 시 가장 최근 100개를 대상으로 한다.


### 단계 3 — 메시지 분류

조회된 메시지를 다음 유형으로 분류한다:

| 유형 | 정의 | 처리 우선순위 |
|---|---|---|
| REQ-NEW | 신규 기능 요청 또는 요구사항 추가 | P1 |
| REQ-CHANGE | 기존 요구사항 변경 요청 | P1 |
| DECISION | 특정 사항에 대한 확인 또는 결정 | P1 |
| QUESTION | PM 또는 개발팀에 대한 미답변 질문 | P1 |
| STATUS | 진행 상황 공유 또는 단순 업데이트 | P3 |
| BLOCKER | 진행을 막는 이슈 언급 | P0 |
| NOISE | 업무 무관 메시지 | 무시 |

분류 기준:
- "추가해주세요", "필요합니다", "되어야 합니다" → REQ-NEW
- "변경", "수정", "바꿔주세요" → REQ-CHANGE
- "확인했습니다", "결정했습니다", "진행하겠습니다" → DECISION
- "?" 또는 "어떻게", "언제", "가능한가요" → QUESTION
- "막혀있습니다", "불가합니다", "대기 중" → BLOCKER


### 단계 4 — PM 보고 출력

분류 결과를 다음 형식으로 출력한다:

```
메신저 조회 결과: {product}
조회 기간: {시작} ~ {종료}
분석 채널: {N}개 / 메시지: {N}개

-- BLOCKER ({N}건) --
[{채널명}] {발화자} ({날짜}):
  "{메시지 원문 요약}"
  → 처리 제안: open-issues P0 등록

-- REQ-NEW ({N}건) --
[{채널명}] {발화자} ({날짜}):
  "{메시지 원문 요약}"
  → 처리 제안: stakeholder/{팀명}.md 추가 또는 open-issues P1 등록

-- REQ-CHANGE ({N}건) --
...

-- DECISION ({N}건) --
[{채널명}] {발화자} ({날짜}):
  "{메시지 원문 요약}"
  → 처리 제안: decisions.md 추가

-- QUESTION ({N}건) --
[{채널명}] {발화자} ({날짜}):
  "{메시지 원문 요약}"
  → 처리 제안: open-issues P1 등록 (응답 필요)

-- STATUS ({N}건) --
{상태 업데이트 요약만 표시}

결과가 없는 유형은 출력에서 생략한다.
```


### 단계 5 — PM 처리 방식 확인

BLOCKER / REQ-NEW / REQ-CHANGE / DECISION / QUESTION 항목에 대해
PM에게 각 항목의 처리 방식을 확인한다:

```
위 항목에 대해 처리 방식을 선택해 주세요:

  각 항목별로 다음 중 선택:
  [A] 파일 반영   — 해당 파일에 즉시 반영
  [B] 이슈 등록   — open-issues.md에 등록 후 나중에 처리
  [C] 무시        — 이번 세션에서 처리하지 않음

  또는 전체 적용:
  [ALL-A] 전부 파일 반영
  [ALL-B] 전부 이슈 등록
```


### 단계 6 — PM 결정에 따른 파일 반영

**REQ-NEW / REQ-CHANGE → [A] 선택 시:**
`inputs/discovery/stakeholder/{팀명}.md`에 항목을 추가한다.
유형: FR, 우선순위: [분류 미확정], 출처: 메신저 {채널명} {날짜}

이후 stakeholder.md 변경이 있으면 PM에게 `/draft-req` 재실행을 안내한다.

**DECISION → [A] 선택 시:**
`decisions.md` DEC 표에 후보 행을 자동 등재한다 (스키마: [[CONTEXT/dec-schema]]):
```markdown
| DEC-{NNN} | {MM-DD} | {도메인} | {내용 압축 60자} | {번복 대상 또는 -} | ⬜ | /su {채널명} |
```

- `DEC-{NNN}`: 표의 가장 큰 ID + 1
- `도메인`: 채널 토픽 기반 자동 추정 (PM 정정 가능)
- `번복` 칼럼: 발화 내용이 기존 DEC 번복이면 supersede 대상 ID. 아니면 `-`
- `승인` 셀 = `⬜`. PM이 `/dec-approve {DEC-ID}` 또는 셀 직접 편집으로 승인
- 발화자(`{발화자}`)는 PM이 아닌 경우가 많으므로 승인은 별도 단계
- 연관 open-issues 항목이 있으면 완료 처리한다

**BLOCKER / QUESTION → [A] 또는 [B] 선택 시:**
`open-issues.md`에 등록한다:
```markdown
- [ ] [SU-NN] {유형}: {내용} — 출처: {채널명} {날짜} / 응답 필요: {발화자}
```
BLOCKER는 P0, QUESTION은 P1로 등록한다.


### 단계 7 — session-log.md 기록

```markdown
- {날짜} /su: 조회 {N}채널 / BLOCKER {N}건 / REQ-NEW {N}건 / DECISION {N}건 / QUESTION {N}건
```

이 기록이 다음 /su 실행 시 조회 시작점으로 사용된다.


## 결과 파일 목록 (PM 선택에 따라 조건부 생성)

| 파일 | 조건 |
|---|---|
| `inputs/discovery/stakeholder/{팀명}.md` | REQ-NEW / REQ-CHANGE [A] 선택 시 |
| `decisions.md` | DECISION [A] 선택 시 |
| `open-issues.md` | BLOCKER / QUESTION [A] 또는 [B] 선택 시 |
| `session-log.md` | 항상 기록 |


## 다음 단계

REQ-NEW / REQ-CHANGE가 반영된 경우:
- 요구사항 재합성이 필요하면 `/draft-req {product}`를 재실행한다.

BLOCKER P0이 등록된 경우:
- 즉시 PM과 해결 방안을 논의한다.
