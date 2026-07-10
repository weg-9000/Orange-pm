# 외부 연동 규약 (Connector Convention)

이 플러그인은 **자체 MCP 서버나 특정 벤더 연동 도구를 번들하지 않는다.**
외부 시스템 연동은 전부 **사용자가 자신의 환경에 연결한 MCP 서버 / Claude 커넥터**를
런타임에 탐지해 사용한다. 연동이 없으면 모든 워크플로우는 로컬 파일만으로 동작한다.

## Capability 정의

스킬과 에이전트는 벤더명이 아니라 아래 capability 라벨로 연동을 요청한다.

| capability | 용도 | 예시 서비스 (사용자가 연결) |
|---|---|---|
| `wiki` | 문서 게시(publish)·조회(read)·계층 구성 | Confluence, Notion, GitHub Wiki 등 |
| `chat` | 팀 메신저 메시지 조회·알림 발송 | Slack, Mattermost, Teams 등 |
| `design` | 디자인 파일·프레임 조회 | Figma, Zeplin 등 |
| `repo` | 코드 저장소 MR/PR·이슈 조회·생성 | GitLab, GitHub 등 |
| `tasks` | 일정·업무·담당자 조회 | Jira, Asana, 그룹웨어 등 |

## 탐지 프로토콜 (스킬 공통)

capability가 필요한 단계에서 스킬은 다음 순서를 따른다:

1. **매핑 확인** — Hub의 `CONTEXT/connectors.md`에 해당 capability의 선호 도구가
   선언되어 있으면 그 도구를 우선 사용한다.
2. **자동 탐지** — 현재 세션에서 사용 가능한 MCP 도구 목록(또는 ToolSearch)에서
   capability에 맞는 도구를 찾는다.
   - `wiki`: confluence / notion / wiki / page 키워드
   - `chat`: slack / mattermost / message / channel 키워드
   - `design`: figma / design / frame 키워드
   - `repo`: gitlab / github / merge_request / pull_request / issue 키워드
   - `tasks`: jira / task / calendar 키워드
3. **호출** — 발견한 도구의 스키마에 맞춰 호출한다. 벤더별 파라미터 차이는
   도구 스키마를 읽고 적응한다.
4. **부재 시 graceful degradation** —
   - **선택 의존 단계**: `[{capability} 연동 없음 — 탐색 생략]`을 기록하고 로컬로 진행한다.
   - **필수 의존 스킬** (`/su`, `/cr` 원격 게시, `/from-url`): 아래 안내를 출력하고
     중단하거나 `--local-only` 대안을 제시한다.

```
이 단계는 {capability} 커넥터가 필요합니다.
Claude Code에 MCP 서버를 연결하면 자동으로 사용됩니다:
  claude mcp add <name> ...     (또는 Claude 설정 → Connectors)
연결 후 다시 실행해 주세요. 로컬 전용으로 진행하려면 --local-only 를 사용하세요.
```

## Hub 매핑 파일 — `CONTEXT/connectors.md`

자동 탐지가 모호한 환경(같은 capability 도구가 여럿)에서는 사용자가
Hub의 `CONTEXT/connectors.md`에 명시 매핑을 선언할 수 있다. `/init-hub`가 템플릿을 생성한다.

```markdown
# Connector 매핑
| capability | 도구/서버 이름 | 비고 |
|---|---|---|
| wiki   | (예: mcp__confluence__*) | 게시 대상 스페이스: XXX |
| chat   | (예: mcp__slack__*)      | 기본 채널: #product |
| design | (예: mcp__figma__*)      | |
| repo   | (예: mcp__github__*)     | |
| tasks  |                          | 미사용 |
```

## 원칙

- **스크립트는 네트워크를 모른다** — `scripts/*.py`는 로컬 파일 처리 전용이다.
  외부 I/O는 항상 모델의 도구 호출로만 수행한다 (인증·전역 도구 분리 원칙).
- **벤더명은 예시로만** — SKILL.md 본문에 특정 벤더를 전제한 호출 경로를 하드코딩하지 않는다.
- **실패 무해** — 외부 호출 실패가 로컬 산출물 상태를 바꾸지 않는다.
