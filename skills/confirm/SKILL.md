---
name: confirm
description: 모든 WO draft를 v1.0-frozen으로 확정하고 외부 시스템에 배포한다. 실행 전 integrator PASS + P0 미결 0건 조건을 반드시 충족해야 한다.
triggers:
  - "confirm"
  - "freeze"
  - "deploy policy"
phase: 4
effort: high
model: opus
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

다음 4개 항목을 순서대로 확인한다. 하나라도 미충족이면 실행을 중단하고
해소 방법을 안내한다.

1. `reports/integration-summary.md`의 최종 판정이 PASS인지 확인한다.
   FAIL 또는 파일 미존재 시 `/integrate {product}` 재실행을 안내하고 중단한다.

2. `open-issues.md`에서 P0 항목 수를 확인한다.
   P0가 1건 이상이면 목록을 출력하고 중단한다.

3. `work-orders/index.md`에 등록된 전체 WO와 `drafts/` 실재 파일을 대조한다.
   누락 draft가 있으면 WO ID 목록을 출력하고 중단한다.

4. `decisions.md`의 freeze 상태가 false인지 확인한다.
   이미 frozen이면 이중 확정 경고를 출력하고 PM에게 의사를 재확인한다.


## 실행 단계

### 단계 1 — draft 버전 태그 삽입

`drafts/*.draft.md` 전체를 순회한다.
각 파일 헤더에 다음 두 줄을 삽입한다:

```
**version**: `v1.0-frozen`
**frozen_at**: `{UTC 타임스탬프 ISO 8601}`
```

삽입 위치: 파일 첫 번째 `---` 구분선 바로 아래.
기존 version 필드가 있으면 덮어쓴다.


### 단계 2 — decisions.md 확정 기록

`decisions.md` 최하단에 다음 블록을 추가한다:

```markdown
## Freeze Record

- **frozen_at**: {UTC 타임스탬프}
- **frozen_by**: /confirm 자동 기록
- **total_wo**: {WO 수}
- **policy_wo**: {policy WO 수}
- **screen_wo**: {screen WO 수}
- **graph_hash**: {graph.json SHA256 앞 12자리}
- **status**: FROZEN
```

`status: FROZEN` 이후 decisions.md 직접 수정을 금지한다.


### 단계 3 — session-log.md Phase 기록

`session-log.md`에 다음 항목을 추가한다:

```markdown
- {날짜} Phase 4 진입: /confirm 완료, v1.0-frozen 적용, WO {N}개
```


### 단계 3-5 — Publication 변환 + wiki push (강제 자동)

> Phase 4 진입은 frozen 정본화 시점이므로 **publication 변환을 반드시 거친 클린본** 이
> wiki(예: Confluence) 정본으로 올라가야 한다. PM 명시 호출 없이 자동 실행.

PM 에게 다음 실행을 권고한다 (`--push` 자동 포함, `--style-example` 은 선택):

```bash
/render {product} --push --check-sync --verify
```

내부 동작 (render SKILL.md 단계 6-1 참조):
1. Deterministic prefilter — process metadata 제거
2. LLM 어투 정규화 (PM 이 `--style-example` 지정한 경우만)
3. fact_preservation_check — 정책 사실 100% 보존 검증
4. markdown → wiki 게시 포맷 변환 (예: Confluence Storage Format XML)
5. wiki push — 기존 페이지 업데이트 또는 신규 생성
6. meta.json `_sync.last_published_version` 갱신

FAIL 시 (fact-check FAIL 또는 push 실패):
- 전체 /confirm 을 중단하지 않음 — 단계 5 (repo MR/PR) 는 계속 진행
- 오류는 `reports/cr-error.log` 에 기록
- PM 이 수동으로 `/render --push` 재시도 가능


### 단계 4 — (레거시) /cr 호출 — 페이지 계층 메타데이터만

`/cr {product}` 를 실행한다. 단, **본문 업로드는 단계 3-5 에서 완료된 상태** 이므로
이 단계는 다음 부수 작업만 수행:
- 프로젝트 루트 페이지 (`{product} 정책서 v1.0`) 생성 또는 조회
- 페이지 계층 (parent_page_id 하위 배치)
- 레이블 (`v1-frozen`, `policy`, `screen`) 적용
- 인덱스 페이지 본문 갱신 (전체 페이지 링크 목록)

본문 내용 자체는 단계 3-5 의 publication 결과로 이미 반영되어 있다.
`/cr` 가 본문을 다시 덮어쓰면 publication 변환이 무효화되므로 주의 — 향후 `/cr` 가
"본문 미수정 + 메타데이터만" 모드로 동작하도록 분리될 예정 (현재는 동일 본문 재push 가능).

실패 시 `reports/cr-error.log`에 오류를 기록하고 단계 5를 건너뛰지 않는다.
(repo MR/PR 생성은 wiki push 실패와 무관하게 계속 진행한다.)


### 단계 5 — repo MR/PR 생성

repo 커넥터(사용자가 연결한 MCP 도구 — 예: GitLab·GitHub 등)를 CONNECTORS.md
탐지 프로토콜로 확인하고 MR/PR을 생성한다.
부재 시 `[repo 연동 없음 — MR/PR 생성 생략]`을 기록하고 다음 단계로 진행한다.
MR/PR 제목: `[{PREFIX}-C] {product} 정책서 v1.0-frozen`
MR/PR 설명에 다음 항목을 포함한다:
- WO 전체 목록 (policy / screen 분리)
- graph.json 해시
- decisions.md freeze 타임스탬프
- wiki 페이지 링크 (업로드 성공 시)
- open-issues.md WARN 항목 수

MR/PR 생성 실패 시 오류 메시지를 출력하되 전체 프로세스를 중단하지 않는다.


### 단계 6 — chat 완료 알림

chat 커넥터(사용자가 연결한 MCP 도구 — 예: Slack·Mattermost 등)를 CONNECTORS.md
탐지 프로토콜로 확인하고 프로젝트 채널에 알림을 전송한다.
부재 시 `[chat 연동 없음 — 알림 생략]`을 기록하고 다음 단계로 진행한다.
알림 내용:
- 프로젝트명 및 frozen_at 타임스탬프
- policy WO 수 / screen WO 수
- MR/PR URL (생성 성공 시)
- wiki 업로드 결과 (성공 / 실패)

chat 전송 실패 시 콘솔에 경고만 출력하고 계속 진행한다.


### 단계 7 — metrics.md 기록

`reports/metrics.md`에 다음 KPI를 기록한다:

```markdown
## {product} v1.0-frozen KPI

| 항목 | 값 |
|---|---|
| frozen_at | {UTC 타임스탬프} |
| total_wo | {N} |
| policy_wo | {N} |
| screen_wo | {N} |
| open_issues_p1 | {N} |
| open_issues_p2 | {N} |
| confluence_upload | SUCCESS / FAIL |
| gitlab_mr_url | {URL 또는 FAIL} |
```

> **split-deliverable 발행 모드** (`graph/project-mode.json` `publication_mode:
> split-deliverable`, fix-plan-dossier-publish-split): v1.0-frozen 태깅은 dossier
> draft(정본 소스)에 적용한다 — 무변경. 파생 D2 정책정의서 / D3 화면설계서는 frozen
> dossier 의 결정적 투영이며, push 시 per-deliverable meta 의 `_sync.last_published_version`
> 이 증가한다. metrics 에 `deliverables: D2,D3` 비차단 표기를 추가한다(KPI 차단 조건 아님).


## 결과 파일 목록

| 파일 | 변경 내용 |
|---|---|
| `drafts/*.draft.md` | version: v1.0-frozen + frozen_at 삽입 |
| `decisions.md` | Freeze Record 블록 추가 |
| `session-log.md` | Phase 4 진입 기록 |
| `reports/metrics.md` | KPI 테이블 추가 |
| `reports/cr-error.log` | wiki push 오류 시에만 생성 |


## 실패 처리 원칙

- 단계 1~3 (로컬 파일 작업): 실패 시 즉시 중단. 변경 사항을 롤백하지 않고
  PM에게 수동 확인을 요청한다.
- 단계 4~6 (외부 시스템): 실패 시 오류를 기록하고 다음 단계를 계속 진행한다.
  외부 시스템 오류가 로컬 확정 상태에 영향을 주지 않는다.
- 단계 7 (metrics): 실패 시 경고 출력 후 완료 처리한다.
