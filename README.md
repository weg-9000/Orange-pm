# orange-pm — Claude Code 플러그인

Orange PM 기획팀을 위한 Claude Code 플러그인입니다. Discovery → Graph → Fanout → Draft → Integrate → Confirm 의 6단계 기획 워크플로우를 19개 skill과 6개 전문 agent로 자동화합니다.

---

## 필수 전제조건 — 작업 디렉토리

> ⚠️ **이 플러그인은 반드시 `Planning-Agent-Hub/` 디렉토리에서 Claude Code를 실행해야 합니다.**

플러그인의 `SessionStart` 훅과 모든 skill은 다음 경로를 **현재 작업 디렉토리 기준 상대 경로**로 참조합니다:

| 참조 경로 | 용도 |
|---|---|
| `CONTEXT/layer-config.md` | PREFIX 및 문서 게시 설정 |
| `CONTEXT/gates/*.md` | Phase 게이트 검증 기준 |
| `CONTEXT/project-rules.md`, `brand-voice.md` | 문서 작성 규칙 |
| `PROJECTS/{product}/` | 모든 산출물 저장 위치 |
| `templates/graph-schema.json` | graph.json 생성 스키마 |
| `templates/work-order-template.md` | Work Order 포맷 (Hub 루트 기준 — 실제 파일은 `Planning-Agent-Hub/templates/`) |

`orange-pm-plugin/` 디렉토리에서 실행하면 이 파일들을 찾지 못해 훅이 정상 동작하지 않습니다.

---

## 설치

### 1. Planning-Agent-Hub 준비

```bash
# Planning-Agent-Hub 디렉토리를 작업 공간으로 클론하거나 배치합니다.
# 디렉토리 구조 예시:
workspace/
├── Planning-Agent-Hub/   ← Claude Code는 이 디렉토리에서 실행
└── orange-pm-plugin/      ← 플러그인 소스 (별도 위치)
```

### 2. 플러그인 설치

Claude Code를 `Planning-Agent-Hub/` 디렉토리에서 열고, 터미널에서 실행합니다:

```
/plugins add ./path/to/orange-pm-plugin
```

또는 마켓플레이스에서:

```
/plugins add orange-pm
```

### 3. 외부 연동 — MCP 커넥터 (선택)

이 플러그인은 자체 MCP 서버나 특정 벤더 연동 도구를 번들하지 않습니다(`.mcp.json` 제거됨). 외부 연동은 **사용자가 자신의 환경에 연결한 MCP 서버/커넥터를 자동 탐지해 사용**합니다. 자세한 규약(capability 정의·탐지 프로토콜·Hub 매핑)은 [CONNECTORS.md](CONNECTORS.md)를 참조하세요. **연동이 하나도 없어도 전체 워크플로우는 로컬 파일만으로 동작합니다.**

| capability | 용도 | 예시 서비스 |
|---|---|---|
| `wiki` | 문서 게시·조회 | 예: Confluence, Notion |
| `chat` | 메신저 조회·알림 | 예: Slack, Mattermost |
| `design` | 디자인 파일 조회 | 예: Figma |
| `repo` | MR/PR·이슈 조회 | 예: GitLab, GitHub |
| `tasks` | 일정·업무 조회 | 예: Jira, Asana |

**인증은 각 MCP 서버 설정에서 구성합니다.** 플러그인이 토큰이나 환경변수를 직접 요구하지 않으며, MCP 서버를 연결하면(`claude mcp add <name> ...` 또는 Claude 설정 → Connectors) 해당 서버의 인증 설정을 그대로 사용합니다.

같은 capability의 도구가 여럿인 환경에서는 Hub의 `CONTEXT/connectors.md`에 선호 도구를 선언할 수 있습니다. 예를 들어 사내 위키가 `https://confluence.example.com/spaces/...` 형태의 Confluence라면 `wiki` capability에 해당 MCP 서버를 매핑하면 됩니다.

### 4. Hub 구조 초기화

Planning-Agent-Hub가 아직 초기화되지 않은 경우:

```
/init-hub
```

---

## 빠른 시작

```
# Claude Code를 Planning-Agent-Hub/ 에서 열기
# → SessionStart 훅이 자동으로 현재 Phase와 미결 항목을 표시합니다

/discover dbaas          # Phase -1: 새 프로젝트 시작
/research dbaas          # 경쟁사 분석
/stakeholder dbaas       # 이해관계자 요구사항 수집
/product-audit dbaas     # 자사 제품 현황 파악
/draft-req dbaas         # 요구사항 통합
/lc dbaas                # Phase 게이트 검증
/ingest dbaas            # Phase 0: 프로젝트 구조·문서 동기화
/graph-gen dbaas         # 의존성 그래프 생성
/fanout dbaas            # Phase 1: Work Order 생성
/flow dbaas S-001        # Phase 2: 화면 시퀀스 작성
/review draft.md         # 초안 검증
/critique {URL 또는 파일}  # 정책서·화면설계 비판적 평가
/integrate dbaas         # Phase 3: 교차 검증
/confirm dbaas           # Phase 4: v1.0 확정
/cr dbaas                # 위키 게시 (wiki 커넥터 · --local-only 지원)
/su dbaas                # 이해관계자 공지
```

---

## Phase 진행 구조

```
Phase -1  Discovery       /discover /research /stakeholder /product-audit /draft-req
    ↓ [discovery-exit-gate]
Phase  0  Ingest & Graph  /ingest /graph-gen
    ↓ [policy-entry-gate]
Phase  1  Fanout          /fanout
    ↓
Phase  2  Draft           /explore /flow /review /critique  (WO 1건 = 세션 1건)
    ↓
Phase  3  Integrate       /integrate  (최대 3라운드)
    ↓ [policy-exit-gate]
Phase  4  Confirm         /confirm → /cr → /su
```

Phase 전진 전 반드시 `/lc {product}` 로 게이트 조건을 검증합니다.

---

## 세션 관리

- **세션 시작**: SessionStart 훅이 현재 Phase, P0 미결 항목, 마지막 WO, 다음 실행 가능 skill을 자동 표시합니다.
- **세션 종료**: `/sc {product}` 로 session-log.md와 RESUME.md를 저장합니다.
- **세션 재개**: Claude Code 재실행 시 SessionStart 훅이 RESUME.md 기반으로 작업을 복원합니다.

---

## 요구사항

- Claude Code v1.0 이상
- Planning-Agent-Hub 디렉토리 (작업 디렉토리)
- (선택) 외부 연동용 MCP 서버/커넥터 — 예: Confluence·GitLab·Mattermost·Figma 등. 사용자가 연결한 커넥터를 자동 탐지해 사용하며, 규약은 [CONNECTORS.md](CONNECTORS.md) 참조 (§3)
- 커넥터 인증은 각 MCP 서버 설정에서 구성 (플러그인 자체 인증 설정 없음)
- 연동이 없어도 전체 워크플로우는 로컬로 동작
