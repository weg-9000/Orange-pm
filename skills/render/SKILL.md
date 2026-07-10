---
name: render
description: |
  {PREFIX}-B 공통 정책과 {PREFIX}-C 제품 Delta를 병합하여 완전한 제품 정책서를 조립하고
  사용자가 원하는 포맷으로 출력한다. 작성 중 언제든 호출 가능하며 내용은 수정하지 않고
  조립·포맷 변환만 수행한다.

  주요 플래그:
    --push            Confluence 업로드 (publication 변환 자동 적용)
    --only            선택 발행 — 지정 dossier(WO_ID) 만 push (예: --only G2-C-BDB-00,G2-C-BDB-03).
                      무지정 시 전체 dossier. viz 동기화 뷰의 체크박스 선택 push 백엔드.
    --style-example   LLM 어투/포맷 정규화에 참조할 예시 문서 경로 (--push 와 함께)
    --stakeholder     이해관계자 공유용 클린 뷰 (publication 변환 단축 모드)
    --check-sync      Draft ↔ Confluence 양방향 sync gap 검사
    --apply-inbox     Confluence drift 로 생성된 reports/inbox/ patch 적용
    --check-ssot      SSoT 경계(CONTEXT/ssot-boundary.yml) 위반 검사
    --parallel        독립 WO 를 병렬 렌더링 (멀티 파일 동시 처리)
    --verify          --push 후 XML 구조 품질 자동 검증
    --color-cycle     publish 직전 변경 추적 색상 cycling 적용 (옵션, 기본 off)

  자동 발동 (PM 명시 호출 없이 트리거되는 경우):
    - PostToolUse hook : drafts/*.draft.md 편집 시 render_assemble (stage 1) 만
                         silent 실행 → reports/render/{WO_ID}.complete.md 갱신
    - /lc, /integrate  : stale complete.md 검사 (필수 게이트)
    - /confirm         : publication 변환 + Confluence push 자동 (frozen 정본화)

  LLM 단계와 push 는 항상 PM 명시 트리거 (/render --push 또는 /confirm) 에서만 실행.
triggers:
  - "render"
  - "전체 정책서"
  - "완전본"
  - "export policy"
  - "정책서 출력"
  - "포맷 변환"
  - "동기화 상태 점검"
  - "sync 검사"
  - "Confluence 차이 확인"
  - "원격 수정분 반영"
  - "Confluence 변경분 가져와"
  - "병합 제안 적용"
  - "업로드본 검증"
  - "XML 표준 검증"
phase: any
effort: medium
user-invocable: true
---

## 자연어 의도 → 플래그 결정 매핑 (스킬 진입 직후 0순위 수행)

render 진입 시, PM 이 명시 플래그(`--push` 등)를 직접 적지 않았다면
아래 표로 **결정적으로** 플래그를 선택한다. 키워드는 부분일치·동의어 포함.
판단을 추측에 맡기지 말고 이 표를 SSoT 로 삼는다.

| PM 발화 의도 (키워드) | 선택 플래그 |
|---|---|
| "올려줘", "push", "Confluence 업로드", "정본화해서 올려", "확정본 반영" | `--push` |
| "공유용", "클린본", "이해관계자/디자이너 공유", "검토용 깔끔하게" | `--stakeholder` |
| "동기화 상태", "sync 점검", "로컬이랑 Confluence 차이", "어긋난 거 있는지", "gap 검사" | `--check-sync` |
| "원격 수정분 반영", "Confluence에서 바뀐 거 가져와", "drift 반영", "inbox/병합 제안 적용" | `--apply-inbox` |
| "업로드본 검증", "XML 표준 맞는지", "사내 포맷 검사", "push 후 품질 확인" | `--verify` |
| "SSoT 위반 검사", "경계 검사" | `--check-ssot` |
| "병렬로", "동시에 빨리", "한 번에 여러 WO" | `--parallel` |
| (위 어디에도 안 걸림 — "완전본/포맷 변환/미리보기") | (플래그 없음 = 로컬 조립만) |

**결정 규칙:**
1. 한 발화에 여러 의도가 섞이면 해당 플래그를 **모두** 결합한다.
   예: "검증까지 해서 올려줘" → `--push --verify`.
2. `--verify` 는 `--push` 를 전제한다. "검증"만 단독 발화면 `--push --verify` 로 보정한다.
3. `--apply-inbox` 는 원격 변경을 로컬에 되먹이는 **되돌리기 어려운** 동작이므로,
   선택 후에도 fact_preservation_check 게이트(단계 3)를 반드시 거치고
   완전 자동 적용하지 않는다.
4. `--push` / `--apply-inbox` 처럼 외부·비가역 영향이 있는 플래그는 실행 전 PM 에게
   대상·범위를 한 줄로 확인받는다. 읽기 전용(`--check-sync`·`--verify`·`--check-ssot`)은
   확인 없이 진행 가능.
5. 의도가 둘 이상으로 모호하면 추측하지 말고 PM 에게 어느 플래그인지 되묻는다.


## Track A/B/C 분기 처리 (Phase 4 R6)

> intent-router 가 결정한 Track 에 따라 render 동작이 다르다.

### Track A — Full Product (dossier 기반, v2.0 — fix-plan-dossier-publish)
- **입력**: dossier drafts. **on-disk 형상은 `drafts/cluster_{cluster_id}.draft.md`,
  `type: cluster_draft`, `wo_id: {PREFIX}-K-{cluster_id}`** (fanout cluster-mode 산출,
  fanout_dag.py). "dossier" 는 개념 명칭이고 실제 파일/타입/WO_ID 는 cluster_draft/G2-K-*
  이다. **파일명을 재도출하지 말고** `work-orders/cluster_index.json` 의 `clusters[].draft_path`
  / `wo_id` 를 목록의 SSoT 로 사용한다(감사 2026-06-08 H6).
- **처리 (발행 모드 분기 — `graph/project-mode.json` 의 `publication_mode`)**:
  1. `cluster_index.json` 의 각 dossier `draft_path` 를 순회
  2. 각 dossier → 클린본 `reports/render/{WO_ID}.complete.md` (render_assemble, 이미 생성됨)
  3. `dossier-page` (기본): transpose 미수행 — dossier 1개 = **기능정의서 페이지 1개**로
     publication 변환(prefilter→md_to_storage) 후 push
  4. `split-deliverable`: transpose 재활성 — 모든 dossier §1→D2 정책정의서 / §2→D3
     화면설계서로 합성(render_transpose) 후 **정확히 2개 페이지** push (단계 3-A-split)
- **D1·D5**: Phase -1 산출이므로 그대로 publish (변동 없음)
- **D4 회의록**: `meetings/*.md` + `mtg-ledger.md` 시간순 어셈블, cluster 태그로 인덱스
- **호출**: `/render {product} --push` (전체 dossier) 또는 `--only {WO_ID,...}` (선택 발행)
- **색상 cycling**: dossier **페이지** 단위 (안정 WO_ID 기반)

### Track B — Single Deliverable
- **입력**: 단일 deliverable draft (예: `drafts/D2.draft.md`)
- **처리**:
  1. cluster fanout 우회 (transpose 미수행)
  2. publication-syntax 적용 + md_to_storage 직접 변환
  3. 해당 페이지 1건만 push (URL_target)
- **호출**: `/render {product} --push --deliverable D2` 또는 자동 단일 페이지 모드
- **색상 cycling**: 동일 (페이지 단위)

### Track C — Template Copy
- **입력**: 단일 deliverable draft + extracted template (`templates/extracted/{page_id}.template.md`)
- **처리**:
  1. extract-template 산출 골격을 base 로 채움
  2. cluster fanout / transpose 우회
  3. target URL 페이지에 push
- **호출**: `/render {product} --push --deliverable D2 --template-from pages/A`

### Track 자동 감지
명시 플래그 (`--deliverable`, `--template-from`) 없는 경우 본 스킬 진입 시:
- `cluster_drafts/*.md` 존재 + 다수 → Track A
- 단일 `drafts/D{N}.draft.md` 만 → Track B
- `templates/extracted/*.template.md` 동반 → Track C

PM 모호 시 한 줄 확인.


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

1. `PROJECTS/{product}/` 가 존재하는지 확인한다.
   없으면 `/ingest {product}` 실행을 안내하고 중단한다.

2. `CONTEXT/.template-cache/` 에 {PREFIX}-B 캐시 파일이 존재하는지 확인한다.
   없으면 `/graph-gen {product}` 실행을 안내하고 중단한다.
   (캐시 미존재 시 라이브 Confluence 로드를 시도하고, 실패 시 중단.)

### Confluence 페이지 초기 생성 확인 (--push 시)

`--push` 플래그가 포함된 경우, 각 문서 유형별 meta.json 을 확인한다.

```
PROJECTS/{product}/confluence-source/
  01-requirements-{product}.meta.json  ← "id" 값 확인
  02-policy-{product}.meta.json
  03-screen-design-{product}.meta.json
```

**meta.json 가 없거나 `"id": "{{CONFLUENCE_PAGE_ID}}"` 플레이스홀더 상태이면:**
→ Confluence 페이지가 아직 생성되지 않은 것이다.
→ `templates/standard/` 기본 양식으로 먼저 페이지를 생성해야 한다.
   (구 `templates/confluence-xml/` 는 Phase 1F 에서 `templates/standard/` 로 이관·폐기됨.)

다음 절차를 PM에게 안내하고 실행 전 확인을 받는다:

```bash
# 1) 기본 양식 복사 (플레이스홀더 치환 포함)
#    01=요구사항정의서 / 02=정책정의서 / 03=화면설계서
cp templates/standard/01-requirements.md \
   PROJECTS/{product}/confluence-source/01-requirements-{product}.md

# 플레이스홀더 치환 (python 스크립트 또는 수동)
# {{PRODUCT_NAME}}, {{DOC_ID}}, {{VERSION}}, {{DATE}} 등
# md → Storage Format 변환은 md_to_storage.py 가 담당

# 2) Confluence에 신규 빈 페이지 생성 후 page_id 확인
# 3) meta.json 은 /cr 가 페이지 생성 시 인라인 초기화 (page_id·제목 입력).
#    별도 template 파일을 복사하지 않는다.

# 4) 기본 양식 로컬 변환 — Confluence 계열 wiki 에 게시할 때는
#    md → Storage Format XML 변환을 선행한다 (md_to_storage.py 는 로컬 처리)
python ${CLAUDE_PLUGIN_ROOT}/scripts/md_to_storage.py \
  PROJECTS/{product}/confluence-source/01-requirements-{product}.md \
  --output /tmp/01-requirements-{product}.xml
```

변환 결과는 wiki 커넥터(사용자가 연결한 MCP 도구 — 예: Confluence 등, CONNECTORS.md
탐지 프로토콜로 확인)의 페이지 update 작업을 스키마에 맞춰 호출해 push 한다.
전달할 도메인 정보: page_id `{CONFLUENCE_PAGE_ID}`, 제목 `[요구사항 정의서]
{PRODUCT_NAME}`, 본문 = 변환된 Storage Format XML.

**기본 양식 위치:** `templates/standard/`
- `01-requirements.md` — 요구사항정의서 초기 골격
- `02-policy.md` — 정책정의서 초기 골격
- `03-screen-design.md` — 화면설계서 초기 골격
- meta.json 은 `/cr` 가 페이지 생성 시 인라인으로 만든다(별도 template 파일 없음).

초기 생성이 완료되고 meta.json 에 실제 `"id"` 가 채워지면 이후 `--push` 는 기존 페이지 업데이트로 동작한다.

3. **legacy/node 모드 한정** — `work-orders/cluster_index.json` 이 없는 경우(node 모드)
   에만 `{WO_ID}` 인수에 대해 `work-orders/{WO_ID}.md` 존재 여부를 확인하고, 없으면
   유효한 WO 목록을 출력하고 중단한다. Track A(cluster 모드, `cluster_index.json` 존재)
   는 per-WO `.md` 파일을 만들지 않으므로 이 존재 검사를 적용하지 않는다(dossier WO_ID
   는 `cluster_index.json` 의 `clusters[].wo_id` 로 검증).

4. `--template` 경로가 지정된 경우 해당 파일 존재 여부를 확인한다.
   없으면 경로를 재확인하도록 안내하고 중단한다.


## 실행 단계

### 단계 1 — 렌더링 범위 결정

> 개선안 G (CONTEXT_OPTIMIZATION.md) — Track A 는 `work-orders/cluster_index.json`,
> legacy/node 모드는 `work-orders/index.json` 을 목록 SSoT 로 사용.

```
WO_ID 지정     → 해당 WO(dossier) 1건만 렌더링
WO_ID 미지정   → Track A: cluster_index.json 의 clusters[] 전체 렌더링
                  legacy/node: work-orders/index.json 의 wo[] 전체 렌더링
                  (index.json 미존재 시에만 index.md 표 파싱으로 fallback)
```

WO 메타 로드 규칙:

1. **Track A (cluster 모드)** — `work-orders/cluster_index.json` 이 존재하면
   `clusters[]` 배열을 목록 SSoT 로 사용한다. 각 항목은 `wo_id`(`{PREFIX}-K-*`),
   `cluster_id`, `draft_path` 등 dossier 발행에 필요한 메타를 포함한다.
   (legacy `index.json`/`index.md` 는 cluster 모드에서 생성되지 않으므로 참조하지 않는다.)
2. **legacy/node 모드** — `cluster_index.json` 이 없고 `work-orders/index.json` 이
   존재하면 `wo[]` 배열을 그대로 사용한다. 각 항목은 `wo_id`, `type`, `level`,
   `node_name`, `draft_path`, `inherits_from`, `related_screen_wos` 등 메타를 포함한다.
3. `index.json` 미존재 시에만 `index.md` 마크다운 표를 파싱.
   동시에 `python ${CLAUDE_PLUGIN_ROOT}/scripts/fanout_dag.py` 재실행
   (또는 `/fanout {product}`) 을 안내해 다음 호출부터 JSON 사용 가능하게 한다.
4. `index.md` 본문 자체를 컨텍스트에 인용하지 않는다 — 사람이 읽는 용도다.

렌더링 대상 WO 목록을 출력한다:

```
렌더링 시작
  제품:    {product}
  범위:    {WO_ID 또는 전체 N건}
  템플릿:  {template 경로 또는 기본값}
  출력:    reports/render/
  Confluence 업로드: {--push 여부}
```

draft가 존재하지 않는 WO는 "작성 중 (미완성)" 으로 표기하고 렌더링을 계속 진행한다.
(작성 중 호출을 허용하기 위해 미완성 WO를 막지 않는다.)


### 단계 2 — Draft ↔ Confluence 양방향 sync 검사 (--check-sync)

> `--check-sync` 플래그가 있거나 `--push`, `/sc`, `/lc` 진입 시 자동 실행된다.
> 양방향 — local→remote (push 필요) 와 remote→local (drift 감지) 모두 검사.

#### 2-A. Confluence snapshot 사전 수집 (모델 책임)

본 스크립트는 Confluence 를 직접 호출하지 않는다 (인증·전역 스킬 분리 원칙 —
`/cr` 와 동일 패턴). 대신 모델이 각 페이지의 현재 version 을 가져와 snapshot 으로
저장한 뒤 스크립트가 그것을 읽는다.

**전제 — wiki 커넥터 가용성 점검**

wiki 커넥터(사용자가 연결한 MCP 도구 — 예: Confluence·Notion 등)를 CONNECTORS.md
탐지 프로토콜로 확인한다. `CONTEXT/connectors.md` 매핑 우선, 없으면 자동 탐지.
발견한 도구가 페이지 version 정보·본문(storage)을 포함한 조회(get)를 지원하는지
스키마로 확인한다.

커넥터 부재 또는 조회 결과로 아래 snapshot shape 을 구성할 수 없으면:
- snapshot 사전 수집을 skip
- render_sync_check.py 가 자동으로 REMOTE-UNKNOWN 처리 (graceful degradation)
- PM 에게 "remote drift 감지는 wiki 커넥터 부재/미지원으로 비활성 — 수동 검토만 가능" 한 줄 안내

지원 시 다음 두 단계를 순서대로 수행:

```bash
# 1) snapshot 디렉토리 준비
mkdir -p PROJECTS/{product}/reports/.confluence-snapshot
```

2\) `confluence-source/*.meta.json` 의 `id` 필드를 순회하며, 각 page_id 에 대해
wiki 커넥터의 조회(get) 작업을 스키마에 맞춰 호출하고, 응답을 아래 JSON shape 로
`PROJECTS/{product}/reports/.confluence-snapshot/{PAGE_ID}.json` 에 저장한다.

snapshot JSON 기대 shape (스크립트가 다음 키만 사용):
```json
{
  "id": "12345",
  "version": {"number": 7, "when": "2026-05-28T..."},
  "title": "...",
  "body": {"storage": {"value": "<xml>...</xml>"}}
}
```

위 shape 과 다르면 (예: markdown 출력만 지원) snapshot 파일을 생성하지 말 것 —
빈 파일이나 다른 형식이면 스크립트가 REMOTE-UNKNOWN 으로 안전하게 분류한다.

#### 2-B. sync check 스크립트 실행

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_sync_check.py \
  --hub-root . [--product {product}] --with-remote
```

`--with-remote` 옵션 없이 호출하면 기존처럼 순방향(OUTDATED/PENDING) 만 검사.

스크립트 동작:
- **순방향** (기존): draft `updated_at` vs meta.json `_sync.last_published_at`
  - OUTDATED : draft 더 최신 → push 필요 → 경고 출력
  - PENDING  : page_id 플레이스홀더 → Confluence 초기 생성 미완료
- **역방향** (신규, `--with-remote` 시): snapshot `version.number` vs
  meta.json `_sync.last_published_version`
  - REMOTE-DRIFT : Confluence 가 더 최신 → 자동으로
    `reports/inbox/{WO_ID}.merge-proposal.md` 생성
  - REMOTE-UNKNOWN : snapshot 없음 (사전 수집 단계 미실행 또는 환경 미설정)

산출:
- `reports/sync-queue.md` (순방향+역방향 통합 상태)
- `reports/inbox/{WO_ID}.merge-proposal.md` (각 REMOTE-DRIFT 페이지마다)

각 merge-proposal.md 구조:
```markdown
# Merge Proposal — WO-05 (REMOTE-DRIFT 감지)

Confluence 페이지 v{N} (마지막 push v{M}) 와 로컬 draft 의 차이.
체크박스 선택 후 /render --apply-inbox WO-05 실행.

## 변경 chunk 1 — §2. 정책 본문
- [ ] 적용
**Confluence (현재):**
> 최근 5회 → 최근 10회로 변경됨
**Local draft (현재):**
> 최근 5회 사용한 비밀번호는 재사용 금지

## 변경 chunk 2 — §3. 표
...
```

`--check-sync` 가 없을 때는 skip. `--push` 와 함께 호출 시 PENDING 이면
**단계 0 (Confluence 초기 생성)** 절차를 재안내하고 사용자 확인 후 진행한다.
REMOTE-DRIFT 가 1건 이상이면 PM 에게 `--apply-inbox` 처리 후 push 권고.


### 단계 2-2 — Inbox patch 적용 (--apply-inbox)

> `--apply-inbox {WO_ID}` 옵션이 지정된 경우에만 실행한다.
> Confluence drift 로 생성된 merge-proposal 의 PM 결정 사항을 draft 에 반영.

PM 이 `reports/inbox/{WO_ID}.merge-proposal.md` 를 열어 다음 두 체크박스 중
하나를 선택한 뒤 본 명령 실행:

```markdown
- [x] **전체 본문 채택** (Confluence 본문으로 draft 덮어쓰기)
- [x] **수동 검토 완료** (PM 이 수동 반영, proposal archive 만)
```

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_apply_inbox.py \
  --hub-root . --product {product} --wo {WO_ID}
```

스크립트 동작:
1. proposal 의 체크박스 파싱
2. **양쪽 미체크** → NOOP (proposal 유지, 다음 sync check 에서 다시 표시)
3. **수동 검토 완료** → draft 미변경, proposal 을 `reports/inbox/archived/` 로 이동
4. **전체 본문 채택**:
   - draft 백업 → frontmatter 유지하고 본문만 Confluence 본문으로 교체
   - **fact_preservation_check 자동 실행** (원본 draft vs 신규 draft)
   - PASS → draft 갱신 + proposal archive (`.applied.md` 접미사)
   - FAIL → 차단, draft 미변경 (백업 폐기), 누락 fact 목록을
     `reports/inbox/{WO_ID}.fact-check.md` 에 저장

5. **양쪽 동시 체크는 에러** (exit 3) — 명확히 하나만 선택해야 함

이 단계는 LLM round-trip 의 lossy 특성을 PM 승인 게이트로 보완한다.
완전 자동 round-trip 은 절대 수행하지 않는다 (SSoT 안전망).


### 단계 2-1 — SSoT 경계 검사 (--check-ssot)

> `--check-ssot` 플래그가 있을 때만 실행한다.

```bash
# 현재는 모델이 직접 ssot-boundary.yml 을 읽고 판단한다
# (향후 전용 스크립트로 자동화 예정)
```

**SSoT 경계 선언 파일:** `CONTEXT/ssot-boundary.yml`
(없으면 아래 인라인 판단 기준 표로 자동 강등(degrade)해 검사를 계속한다 —
파일 부재로 hard-fail 하지 않는다.)

판단 기준:
| 위반 유형 | 수준 | 처리 |
|---|---|---|
| 화면설계서 + 정책서 양쪽에 HEX/px 이중 보유 | WARN | 경고 후 계속 |
| 정책서에 FR What 내용 재정의 | FAIL | 차단 — 소스 수정 필요 |
| 화면설계서에 POL 마커 없이 비즈니스 규칙 직접 기술 | WARN | 경고 후 계속 |

FAIL 이 있으면 렌더링을 중단하고 위반 목록을 출력한다.
`--check-ssot` 가 없으면 skip.


### 단계 3-A — Track A 발행 (발행 모드 게이트)

> **Track A 전용** — `work-orders/cluster_index.json` 존재(운영 게이트) + dossier
> draft(`type: cluster_draft`, fanout cluster-mode 산출).
> Track B/C·node 모드는 본 단계를 건너뛰고 단계 3(render_assemble)으로 진행한다.

**발행 모드 분기 (fix-plan-dossier-publish-split)** — `graph/project-mode.json`
의 `publication_mode` 키를 읽어 두 경로 중 하나로 진입한다(파일/키 없으면
`dossier-page`):

| publication_mode | 발행 단위 | 진입 |
|---|---|---|
| `dossier-page` (기본) | 기능정의서 1개 = 페이지 1개 | 단계 3-A 본문(아래) |
| `split-deliverable` | D2 정책정의서 / D3 화면설계서 2개 페이지 | 단계 3-A-split |

```bash
# 발행 모드 확인
python -c "import json,sys; p='PROJECTS/{product}/graph/project-mode.json'; \
import os; print(json.load(open(p,encoding='utf-8')).get('publication_mode','dossier-page') if os.path.exists(p) else 'dossier-page')"
```

#### 단계 3-A (dossier-page) — dossier 1개 = 페이지 1개

> **transpose 미호출** — dossier 1개 = 페이지 1개로 발행한다.

dossier 별로 클린본을 페이지 1개로 발행한다. 별도 transpose 어셈블 단계가 없다 —
`render_assemble` 이 dossier 마다 이미 `reports/render/{WO_ID}.complete.md` 를 만든다.

발행 대상 dossier 목록은 `cluster_index.json` 에서 읽는다 (`--only` 지정 시 해당
WO_ID 만):

```bash
# dossier 목록 확인 (clusters[].wo_id / draft_path)
cat PROJECTS/{product}/work-orders/cluster_index.json

# 각 dossier 클린본은 render_assemble 이 생성 (draft 편집 시 자동, 또는 수동):
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_assemble.py --hub-root . \
  --product {product} --wo {WO_ID}      # → reports/render/{WO_ID}.complete.md
```

발행 단계(각 dossier 1회 — `--only` 면 선택분만):
- 클린본 `reports/render/{WO_ID}.complete.md` → `publication_prefilter.py` →
  (옵션 색상 cycling·LLM 어투) → `md_to_storage.py` → 페이지 1개 push.
- 페이지 id 는 `confluence-source/{WO_ID}.meta.json` 에서 읽는다(없으면 `/cr` 가
  페이지 생성 후 meta 초기화 — Confluence 미접근 시 보류).
- D1·D5 는 입력형(그대로 publish). D4 회의록은 누적형 어셈블(별도).
- 파생 인덱스 뷰(D1 capability 그룹·횡단 매트릭스)는 `render_transpose.py` 의
  `render_fr_capability_view`/`render_cross_cutting_matrix` 로 합성하되 링크 대상은
  **dossier 페이지**(publication-map.md §3-A).

**exit code 처리**: 0=성공 / 2=해당 cluster 0건(Dα 없으면 정상 — 건너뜀) /
1=파싱·구조 오류(닫히지 않은 panel·cluster 메타 누락 → 해당 cluster draft 수정) /
3=IO. exit 1 은 차단 — cluster draft 의 `::: {.panel section=}` 구조를 점검한다.

> Track A 에서는 이 단계의 `{deliverable}.assembled.md` 가 단계 6-1(publication 변환)·
> 단계 7(push)의 입력이 된다(node 모드의 `{WO_ID}.complete.md` 대체). 즉 단계 3
> (render_assemble)은 Track A 에서 생략하고 본 단계 산출물을 그대로 발행 파이프라인에 태운다.


#### 단계 3-A-split (split-deliverable) — D2 정책정의서 / D3 화면설계서 2개 페이지

> `publication_mode: split-deliverable` 일 때만. dossier 페이지는 push 하지 않고,
> 모든 dossier 의 §1 을 D2 정책정의서로, §2 를 D3 화면설계서로 **transpose** 한다
> (render_transpose.py 재활성 — publication-map.md §0-bis).

a. `cluster_index.json` 에서 dossier draft 경로를 수집한다. `is_common_shell: true`
   인 dossier draft 는 D3 공통 셸(`--common-shell`)로 별도 전달한다.

```bash
DRAFTS=$(python -c "import json; d=json.load(open('PROJECTS/{product}/work-orders/cluster_index.json',encoding='utf-8')); \
print(' '.join('PROJECTS/{product}/'+c['draft_path'] for c in d['clusters']))")

# b. D2 정책정의서 (dossier §1 → 챕터)
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_transpose.py \
  --cluster-drafts $DRAFTS --deliverable D2 \
  --template ${CLAUDE_PLUGIN_ROOT}/templates/standard/D2_policy.md \
  --output PROJECTS/{product}/reports/render/02-policy.assembled.md

# c. D3 화면설계서 (dossier §2 → 화면 단위 챕터 + 공통 셸 부록)
#    공통 셸 draft 는 --common-shell 로 분리(is_common_shell: true)
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_transpose.py \
  --cluster-drafts $DRAFTS --deliverable D3 \
  --common-shell <is_common_shell=true 인 draft 들> \
  --template ${CLAUDE_PLUGIN_ROOT}/templates/standard/D3_screen.md \
  --output PROJECTS/{product}/reports/render/03-screen-design.assembled.md
```

d. 각 `{02-policy|03-screen-design}.assembled.md` 를 기존 단계 6-1(prefilter →
   [색상/LLM] → fact-check) → 단계 7(md_to_storage → push) 그대로 태운다. 입력
   파일만 다르고 **페이지는 정확히 2개**다(기능정의서 그룹 페이지 없음).
e. page-id 소스: `confluence-source/02-policy-{product}.meta.json` /
   `03-screen-design-{product}.meta.json` (`/cr` 의 1-D-split 계층이 생성).
f. per-dossier `{WO_ID}.complete.md` 페이지 루프는 **실행하지 않는다**.
g. `--only D2|D3` 로 선택 발행. 단계 8 요약에 split 행(URL 2개)을 추가한다.

> ⚠️ **주의 (transpose 범위)**: D2/D3 에는 dossier §1/§2 만 반영된다. §0/§5/§6 은
> 정책이 §1 에 self-contained 라는 전제로 미반영이다. 어떤 dossier 가
> `deliverable_targets` 에서 D2/D3 를 빼면 그 cluster 는 해당 deliverable 에서
> 누락된다 — frontmatter `deliverable_targets` 를 점검한다.
> D3 §2 가 화면 ID 태깅 헤딩(`### §2-1 {SCR-ID}`)을 쓰면 화면 단위 챕터로,
> 아니면 cluster 단위 챕터로 fallback 한다(WARN 출력).


### 단계 3 — 완전판 결정적 조립 (render_assemble.py 호출) — Track B/C·node 모드

> **C-RENDER (토큰 경계)** — 공통 인라인 전개는 **모델이 수행하지 않는다.**
> `render_assemble.py` 가 소스 draft + 공통(G2-A/B)를 결정적 텍스트 치환으로
> 조립한다(모델은 공통 텍스트 재출력 금지 — SSoT 정확성·토큰 절감).
> Track A(cluster 모드)는 단계 3-A 로 대체되므로 본 단계를 건너뛴다.

PM 에게 다음 실행을 권고한다(스킬이 직접 실행하지 않고 명령만 안내):

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_assemble.py \
  --hub-root . --product {product} [--wo {WO_ID}] [--all]
```

스크립트 동작(요약만 인지, 본문 인용 금지):
- `master-id-map.yml`(핀ID→stem) + `B-headings-index.json`(§라인범위)로
  `[{ID} §X 참조]` / `기본 정책 완전 적용 — [{ID}] 참조` 를 공통 §텍스트로
  인라인. 각 블록에 `⟦전개: {id}@{ver} … 출처⟧` 출처 태그 부여.
- G2-A 용어는 `terms.yml` 에서 본문 등장 canonical 을 "부록 A. 용어 정의"로 전개.
- 산출 frontmatter `rendered_from_master: [{id}@{ver}]` 핀 →
  `drift_scan.py` 가 완전판 stale 도 대조(version↑ 시 재-render 필요).
- 산출: `reports/render/{WO_ID}.complete.md` (`--all` 시
  `{product}.full.complete.md` 추가).

`B-headings-index.json` 미존재 시 스크립트가 경고 → PM 에게
`python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_index.py --hub-root .` 선행 권고.
draft 미존재 WO 는 스크립트가 자동 제외(작성 중 호출 허용).

미완성 draft 의 `[TBD]` 표기는 소스 그대로 완전판에 노출된다(스크립트는
내용을 수정하지 않는다 — 조립만).


### 단계 4 — 병렬 렌더링 (--parallel)

> `--parallel` 플래그 + WO_ID 미지정(전체 렌더링) 시 실행한다.
> WO 간 의존성(inherits_from, related_screen_wos)이 없는 파일은 독립적으로 처리한다.

```
--parallel 없음(기본):  WO 순차 렌더링
--parallel 있음:        의존성 없는 WO 를 동시 처리 → 렌더링 속도 향상
```

의존성 판별 기준 (`work-orders/index.json` wo[] 메타 활용):
- `inherits_from: []` 이고 `related_screen_wos: []` → 독립 WO → 병렬 가능
- inherits_from 또는 related_screen_wos 가 있는 WO → 순차 처리

병렬 처리 시 각 WO 별 `render_assemble.py` 를 독립 호출한다.
출력 파일은 동일 규칙(`reports/render/{WO_ID}.complete.md`).


### --stakeholder 플래그

이해관계자(디자이너, 개발자, 경영진 등) 공유용 클린 뷰를 생성한다.
기존 병합 로직은 동일하게 실행하며, 출력 단계에서만 다음 후처리를 적용한다.

**제거 항목 (내부 태그 전체 클린):**
- 출처 태그 전체 제거: `[공통 정책]`, `[제품 적용]`, `[제품 고유]`, `<!-- 출처: ... -->`
- HTML 주석 전체 제거

**표기 단순화:**
| 원본 표기 | --stakeholder 표기 |
|---|---|
| `📝 [작성 중 — WO-05 미완성]` | `⚠️ (검토 중)` |
| `⚠️ [{PREFIX}-B-NNN §N.N — 로드 실패]` | `⚠️ (원본 확인 필요)` |
| `[TBD — 제품 Delta 미확정]` | `⚠️ (미확정)` |

**파일명 변경:**
`{product}.full.complete.md` → `{product}.stakeholder.{날짜}.md`

**문서 헤더 추가:**
```markdown
> **검토용 문서** — {날짜} 기준 작성 중인 내용을 포함합니다.
> ⚠️ 표기 항목은 아직 확정되지 않은 내용입니다.
> 확정본은 기획팀에 문의하세요.
```

**`--push` 와 함께 사용 시:**
Confluence에 별도 페이지로 업로드한다.
페이지 제목: `[{PREFIX}-C] {product} 검토용 공유본 ({날짜})`
기존 확정본 페이지와 분리하여 생성한다.


### 단계 6 — 출력 파일 저장

렌더링 결과를 `reports/render/` 에 저장한다.

**파일명 규칙 (render_assemble.py 산출 = 정본):**

| 범위 | 파일명 |
|---|---|
| 단일 WO | `reports/render/{WO_ID}.complete.md` |
| 전체 제품 | `reports/render/{product}.full.complete.md` (`--all`) |
| 스테이크홀더 후처리 시 | `reports/render/{product}.stakeholder.{YYYYMMDD}.md` (선택) |

`*.complete.md` frontmatter 는 스크립트가 생성한다(수정 금지):
`source_doc_id` / `rendered_at` / `rendered_by` /
`rendered_from_master: [{id}@{ver}]` (drift_scan 대조 핀) /
`source_referenced_master`. 별도 헤더 추가/편집 금지.


### 단계 6-1 — Publication 변환 (--push 또는 --stakeholder 시)

> **Source vs Publication 분리** — Confluence 정본은 process metadata 가 제거된
> 클린본이어야 한다. 이 단계는 in-memory 로 실행되며 디스크 산출물을 만들지 않는다
> (검토 필요 시 `--save-published` 플래그로 명시 저장).

#### 6-1-A. Deterministic prefilter (필수, 항상 실행)

PM 에게 다음 실행을 권고한다 (스크립트가 결정적으로 처리):

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/publication_prefilter.py \
  reports/render/{WO_ID}.complete.md --output /tmp/{WO_ID}.prefiltered.md
```

제거 항목 (모두 결정적, LLM 미사용):
- HTML 주석 (`<!-- ... -->`) — render_assemble schema marker, DEC 마커 포함
- 자기 검증 체크리스트 / 금지 사항 / 완료 후 절차 / Workflow Connections 섹션
- 할당 범위 / 불변 입력 등 작성 가이드 메타블록
- 출처 태그 (`⟦전개: id@ver … 출처⟧`)
- frontmatter slim down (wo_id/type/layer/version/last_updated/title 만 유지)

치환 항목:
- `[TBD — ...]` → `(미확정)`
- `[확인 필요: ...]` → `(검토 중)`
- `[정책 충돌 — ...]` → `(검토 필요 — 양립 항목 보존)`

보존 (절대 손대지 않음): 모든 표 셀, 본문 텍스트, `[[POL §X-Y]]`, `[[WO-XX]]`,
`{PREFIX}-A` 등재 어휘.

#### 6-1-A2. 색상 cycling (`--color-cycle` 시에만 — 옵션, 기본 off)

> 변경 추적 색상(최신 변경=초록 / 직전=파랑, 2-cycle decay)을 publish 직전 자동
> 주입한다. `apply_color_cycling.py` 엔진이 직전 발행 상태(`meta.json._color_state`)와
> diff 해 결정적으로 산출(LLM 미사용). **명시하지 않으면 색상 변화 없음** — 발행물의
> 시각적 변경 표기가 필요할 때만 사용한다(publication-syntax.md §6 SSoT).

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/apply_color_cycling.py \
  --input /tmp/{WO_ID}.prefiltered.md \
  --output /tmp/{WO_ID}.colored.md \
  --meta-in  PROJECTS/{product}/confluence-source/{NN}-{type}-{product}.meta.json \
  --meta-out PROJECTS/{product}/confluence-source/{NN}-{type}-{product}.meta.json
```

- `--meta-in` 부재(최초 발행) → baseline 처리(색상 미주입, state 초기화).
- 산출 `*.colored.md` 가 단계 7(md_to_storage→push)의 입력이 된다(미사용 시 prefilter 결과 사용).
- `meta.json._color_state` 가 갱신되어 다음 발행의 cycling 기준이 된다(2-cycle 자동 만료).
- nested 색상 span 금지(lint L6) — 엔진이 결정적으로 1-depth 만 주입.

#### 6-1-B. LLM 어투/스타일 정규화 (`--style-example` 시에만)

`--style-example` 옵션이 지정된 경우, prefilter 결과에 LLM 변환을 적용한다.

입력: prefilter 결과 + `--style-example {path}` + `CONTEXT/brand-voice.md`

LLM 지시 원칙 (이 SKILL 이 시스템 프롬프트로 주입):
- 정책 사실 (숫자·상태명·오류코드·표 셀·UI 문구·POL/WO 마커) 은 **100% 보존**
- 어휘·문장 길이·헤딩 깊이·표 형식만 example 과 일치시킴
- brand-voice.md 의 능동형·주어 명시 규칙 항상 적용
- 원문에 없는 내용 창작 금지

#### 6-1-C. Fact preservation check (필수, LLM 단계가 실행된 경우)

LLM 변환 직후 즉시 검증:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/fact_preservation_check.py \
  --before /tmp/{WO_ID}.prefiltered.md \
  --after  /tmp/{WO_ID}.llm-out.md \
  --hub-root . \
  --report reports/render/{WO_ID}.fact-check.md
```

판정:
- PASS → 단계 7 진행
- FAIL → 누락 fact 목록 출력 + push 차단. 다음 중 하나 선택:
  - LLM 재시도 (다른 prompt 또는 다른 style-example)
  - `--no-llm` 플래그로 LLM 단계 건너뛰고 prefilter 결과만 사용
  - PM 이 누락 fact 를 LLM 결과에 수동 보강

`--style-example` 없이 prefilter 만 사용한 경우 fact-check 도 skip (prefilter 는 결정적이므로 변환 손실은 의도된 것).

#### 6-1-D. `--stakeholder` 단축 모드

`--stakeholder` 플래그는 다음을 자동 적용:
- prefilter 강제 실행
- 추가 치환: `📝 [작성 중 — WO-NN 미완성]` → `⚠️ (검토 중)` 등 (기존 stakeholder 규칙)
- 파일명: `reports/render/{product}.stakeholder.{날짜}.md` (별도 디스크 산출)
- `--push` 와 함께 사용 시 별도 Confluence 페이지로 업로드 (제목: `[{PREFIX}-C] {product} 검토용 공유본 ({날짜})`)


### 단계 7 — Confluence 업로드 (--push 플래그 시)

`--push` 플래그가 지정된 경우에만 실행한다.
**publication 변환 결과 (단계 6-1)** 가 XML 로 변환되어 업로드된다 (소스 draft 가 아님).

- 기존 Confluence 페이지가 있으면 업데이트, 없으면 신규 생성
- 페이지 제목: `[{PREFIX}-C] {product} 완전본 정책서 ({날짜})`
- 업로드 후 Confluence URL을 출력한다
- 업로드 성공 시 `meta.json._sync.last_published_version` 갱신 (Confluence 응답 version 사용)
- 실패 시 로컬 파일은 유지되며 오류 내용만 출력한다


### 단계 7-1 — XML 구조 품질 검증 (--verify)

> `--verify` 플래그가 있을 때, `--push` 완료 직후 실행한다.
> `--push` 없이 단독 호출 시에는 기존 confluence-source/*.xml 파일을 대상으로 실행.

PM 에게 다음 실행을 권고한다:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_verify.py \
  --hub-root . [--product {product}]

# 단일 파일만 검증 시:
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_verify.py \
  --file PROJECTS/{product}/confluence-source/02-policy-{product}.xml
```

스크립트 동작 (요약):
- F1: 패널 매크로 색상 규칙 (borderColor=#24FE00 / titleColor=#002FD5)
- F2: 코드 블록 ac:plain-text-body + CDATA (rich-text-body 금지)
- W1: FR 번호 §-base 3자리 형식
- W2: ac:layout-section 최소 1개 존재
- W3: {{...}} 플레이스홀더 잔존 없음
- 산출: `reports/verify-report.md`

FAIL 이 있으면 렌더링 요약에 경고 블록으로 포함시킨다.
WARN 은 비차단 — 요약에 목록으로 표시.
`--verify` 가 없으면 skip.


### 단계 8 — 렌더링 요약 출력

```
렌더링 완료

  출력 파일:   reports/render/{파일명}
  총 섹션:     {N}개
    [공통 정책]:  {N}개 섹션
    [제품 적용]:  {N}개 섹션
    [제품 고유]:  {N}개 섹션
    [TBD]:        {N}개 섹션
    [작성 중]:    {N}개 WO

  Sync 상태:   {OUTDATED {N}건 / 모두 SYNCED}  ← --check-sync 결과
  SSoT 검사:   {FAIL {N}건 / WARN {N}건 / PASS}  ← --check-ssot 결과
  XML 검증:    {FAIL {N}건 / WARN {N}건 / PASS}  ← --verify 결과
  Confluence:  {업로드 URL 또는 "--push 없음"}

다음 단계:
  초안 추가 작성:  /write {WO_ID} 또는 /flow {product} {screen_id}
  sync gap 해소:   /render {product} --push  (OUTDATED 문서 push)
  전체 검증:       /integrate {product}
  재렌더링:        /render {product}
```


## 결과 파일 목록

| 파일 | 생성 조건 | 내용 |
|---|---|---|
| `reports/render/{WO_ID}.complete.md` | 항상 | render_assemble.py 산출 정본 |
| `reports/render/{product}.full.complete.md` | --all 시 | 전체 제품 완전본 |
| `reports/render/{product}.stakeholder.{날짜}.md` | --stakeholder 시 | 이해관계자 공유본 |
| `reports/sync-queue.md` | --check-sync 시 | Draft↔Confluence sync 상태 |
| `reports/verify-report.md` | --verify 시 | XML 구조 품질 검증 결과 |


## 사용 예시

```bash
# 작성 중 특정 WO 완전본 확인 (기본 마크다운)
/render dbaas WO-03

# 전체 제품 정책서 완전본 출력
/render dbaas

# Confluence 업로드까지
/render dbaas --push

# 이해관계자 공유용 클린 뷰 (작성 중에도 가능)
/render dbaas --stakeholder

# 특정 WO만 디자이너에게 공유
/render dbaas WO-05 --stakeholder

# Confluence에 검토용 페이지로 바로 공유
/render dbaas --stakeholder --push

# Draft → Confluence sync gap 검사만 실행
/render dbaas --check-sync

# SSoT 경계 위반 검사 포함
/render dbaas --check-ssot

# 독립 WO 병렬 렌더링 (전체 제품, 속도 향상)
/render dbaas --parallel

# push + XML 품질 검증까지 한 번에
/render dbaas --push --verify

# 풀 파이프라인 (sync 확인 + SSoT 검사 + 병렬 렌더링 + push + 검증)
/render dbaas --check-sync --check-ssot --parallel --push --verify
```


## 주의사항

- 공통 인라인 전개는 **`render_assemble.py` 가 결정적으로 수행**한다.
  모델은 공통 텍스트를 재출력하지 않는다(C-RENDER 토큰 경계·SSoT 정확성).
- 완전판은 **참조용 뷰가 아니라 기획자 정본(후자)**이다. 단, **수기 수정 금지**
  — 소스(전자: /write·/flow)에서만 수정하고 재-render 한다(이중 작성=SSoT 붕괴).
- `--stakeholder` 는 스크립트 산출 `*.complete.md` 에 대한
  **후처리(태그 클린)**로만 적용한다(인라인 전개를 다시 하지 않는다).
- draft 미완성 WO가 있어도 중단하지 않는다 (스크립트가 자동 제외, 작성 중 허용)
- `--push` 는 명시적으로 지정할 때만 실행한다 (자동 업로드 없음)
- `--check-sync` 는 OUTDATED 발견 시 경고만 표시하고 렌더링을 중단하지 않는다.
  (중단을 원하면 sync-queue.md 확인 후 --push 실행을 우선한다)
- `--check-ssot` 의 FAIL 은 렌더링을 차단한다. WARN 은 계속 진행한다.
  SSoT 경계 선언은 `CONTEXT/ssot-boundary.yml` 이 SSoT.
- `--verify` 의 FAIL 은 요약에 경고로 포함되지만 push 결과를 롤백하지 않는다.
  (Confluence 버전은 이미 올라간 상태 — XML 수정 후 재-push 필요)
- `render_sync_check.py` / `render_verify.py` 는 **읽기 전용** — 소스 파일을 수정하지 않는다.
