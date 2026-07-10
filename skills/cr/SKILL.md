---
name: cr
description: |
  v1.0-frozen 확정 draft 의 Confluence 페이지 계층 구성 + 레이블·메타데이터 적용.
  본문 업로드는 /render --push (publication 변환 거친 클린본) 가 담당하므로
  본 스킬은 페이지 계층·레이블·인덱스 페이지·session-log 기록에 집중한다.
  원격 호출은 wiki 커넥터(사용자가 연결한 MCP 도구 — 예: Confluence·Notion 등)를
  CONNECTORS.md 탐지 프로토콜로 확인해 수행한다.
  --local-only 플래그 사용 시 wiki 커넥터 없이 로컬 Markdown 저장만 수행.
triggers:
  - "cr"
  - "confluence upload"
  - "upload policy"
phase: 4
effort: medium
user-invocable: true
---

## 책임 분리 (Source/Publication 아키텍처)

| 영역 | 담당 |
|---|---|
| 본문 publication 변환 (prefilter·LLM 어투·fact-check) | `/render --push` |
| 본문 Markdown → Storage Format XML 변환 | `/render --push` |
| 본문 Confluence 페이지 update API 호출 | `/render --push` |
| Confluence 페이지 계층 (parent_page_id 하위 배치) | **본 스킬** |
| 페이지 레이블 (`v1-frozen`, `policy`, `screen` 등) | **본 스킬** |
| 인덱스 페이지 본문 생성/갱신 | **본 스킬** |
| session-log/metrics 기록 | **본 스킬** |

`/confirm` 진입 시 단계 3-5 에서 `/render --push` 가 먼저 실행되어 본문이
정본화된 상태로 Confluence 에 올라가 있다. 본 스킬은 그 위에 페이지 구조와
메타데이터만 덮어쓴다 (본문 재push 금지 — publication 변환이 무효화됨).

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

1. `CONTEXT/layer-config.md`에서 다음 값을 읽는다:
   - `confluence_space_key`: 업로드 대상 스페이스 키
   - `confluence_parent_page_id`: 프로젝트 루트 상위 페이지 ID
   미존재 시 PM에게 값 입력을 요청하고 중단한다.

2. `drafts/*.draft.md`에서 `**version**: \`v1.0-frozen\`` 태그가 없는 파일을 탐지한다.
   존재 시 목록을 출력하고 업로드 대상에서 제외한다.
   frozen draft가 0건이면 "업로드할 확정 draft가 없습니다" 안내 후 중단한다.

3. `--local-only` 플래그 여부를 확인한다.
   플래그가 있으면 wiki 커넥터 없이 단계 4만 실행하고 종료한다.

4. wiki 커넥터(사용자가 연결한 MCP 도구 — 예: Confluence·Notion 등)를
   CONNECTORS.md 탐지 프로토콜로 확인한다. `CONTEXT/connectors.md` 매핑 우선,
   없으면 자동 탐지. 커넥터 부재 또는 연결 실패 시 CONNECTORS.md 의 안내문을
   출력하고 `--local-only` 모드로 전환할지 PM에게 묻는다.


## 실행 단계

### 단계 1 — 업로드 대상 분류 (작성 모델 분기)

먼저 작성 모델을 판정한다 (fix-plan-dossier-publish):
- **dossier 모델 (Track A)**: `work-orders/cluster_index.json` 존재(운영 게이트) +
  dossier draft(`type: cluster_draft`, `wo_id: {PREFIX}-K-{cluster_id}`, fanout cluster-mode
  산출) → **dossier 모드**. `graph/project-mode.json` 의 `publication_mode` 로 다시 분기:
  - `dossier-page` (기본/키 없음) → **1-D** (기능정의서 1개 = 페이지 1개).
  - `split-deliverable` → **1-D-split** (D2 정책정의서 / D3 화면설계서 2개 페이지).
- **legacy 모델**: 그 외 → 기존 policy/screen 그룹 분리(아래 1-L).

#### 1-D. dossier 모드 (dossier-page) — 기능정의서 1개 = 페이지 1개

`work-orders/cluster_index.json` 의 `clusters[]` 를 페이지 대상으로 로드한다.
**페이지 계층 (transpose 분할 없음 — D2/D3 정책/화면 분리 폐기):**

```
{product} 기획 v1.0 (루트, 단계 2)
├─ 기능정의서/ (그룹 페이지)
│   ├─ {dossier 1}   ← cluster_index.clusters[0]  (draft_path 클린본 본문)
│   ├─ {dossier 2}
│   └─ … (cluster_id 순)
├─ D1 요구사항정의서   (inputs/requirements.md)
├─ D4 회의록          (meetings/)
└─ D5 타사조사         (inputs/research.md)
```

각 dossier 페이지의 본문은 `/render --push` 가 `reports/render/{WO_ID}.complete.md`
(클린본)에서 이미 업로드한다. 본 스킬은 **페이지 계층·레이블·per-dossier meta.json**
에 집중한다.

**per-dossier meta.json 생성** — 각 dossier 1개 = `confluence-source/{WO_ID}.meta.json`:
```json
{ "id": "{생성된 page_id 또는 {{PLACEHOLDER}}}",
  "title": "{capability} 기능정의서",
  "wo_id": "{WO_ID}", "doc_id": "{cluster_id}",
  "_sync": { "last_published_version": 0, "last_published_at": null } }
```
이 파일이 render_sync_check·sync_emit 의 per-dossier 상태 키다. 페이지 생성 전이면
`id` 를 `{{PLACEHOLDER}}` 로 두며 sync 상태는 PENDING 으로 노출된다.

> **Confluence 미접근 시**: 페이지 생성·page_id 확보는 보류. meta.json 은
> placeholder 로 선생성 가능(`--local-only`). 실제 페이지 생성은 접근 복구 후.

#### 1-D-split. dossier 모드 (split-deliverable) — D2/D3 2개 페이지

`publication_mode: split-deliverable` 일 때. dossier 정본은 **D2 정책정의서 /
D3 화면설계서 2개 deliverable 페이지로 투영**된다(기능정의서 그룹 페이지 없음).

```
{product} 기획 v1.0 (루트, 단계 2)
├─ 정책정의서        ← dossier §1 → transpose D2 (reports/render/02-policy.assembled.md)
├─ 화면설계서        ← dossier §2 → transpose D3, 화면 단위 (03-screen-design.assembled.md)
├─ D1 요구사항정의서   (inputs/requirements.md)   ← 무변경
├─ D4 회의록          (meetings/)                 ← 무변경
└─ D5 타사조사         (inputs/research.md)        ← 무변경
```

본문 push 는 `/render --push` 의 split 경로(단계 3-A-split)가 담당한다. 본 스킬은
**페이지 계층·레이블·인덱스·per-deliverable meta** 만 구성한다.

**per-deliverable meta.json 생성** (2개):
```json
// confluence-source/02-policy-{product}.meta.json
{ "id": "{page_id 또는 {{PLACEHOLDER}}}", "title": "[정책정의서] {product}",
  "deliverable": "D2", "_sync": { "last_published_version": 0, "last_published_at": null } }
// confluence-source/03-screen-design-{product}.meta.json
{ "id": "{page_id 또는 {{PLACEHOLDER}}}", "title": "[화면설계서] {product}",
  "deliverable": "D3", "_sync": { "last_published_version": 0, "last_published_at": null } }
```

페이지 부트스트랩 양식: `templates/standard/02-policy.md` /
`templates/standard/03-screen-design.md`. meta.json 은 별도 템플릿 없이 위
**per-deliverable meta.json 생성** 블록대로 본 스킬이 인라인으로 작성한다. 레이블:
`{product},policy,v1-frozen` / `{product},screen,v1-frozen`.

이 2개 meta 가 render_sync_check·sync_emit 의 per-deliverable 상태 키다(SOURCE-ONLY
dossier 와 구분). 페이지 생성 전이면 `id` 를 `{{PLACEHOLDER}}` 로 둔다.

#### 1-L. legacy 모드 — policy/screen 그룹 (기존)

`drafts/*.draft.md`를 직접 스캔해 draft 목록을 로드한다(기본 경로).
`reports/integration-input.json`은 존재할 경우에만 참조하는 legacy 선택 입력이며
필수가 아니다(integrate/integrator 는 draft frontmatter 를 직접 스캔한다).
draft를 두 그룹으로 분리한다:
- `policy` 그룹: type=policy인 WO draft
- `screen` 그룹: type=screen인 WO draft

업로드 순서: policy 전체 완료 후 screen 처리.
(screen 페이지가 policy 페이지 ID를 내부 링크로 참조하므로 순서가 중요하다.)


### 단계 2 — 프로젝트 루트 페이지 생성 또는 조회

wiki 커넥터의 조회(get/search) 작업으로 `confluence_parent_page_id` 하위에
`{product} 정책서 v1.0` 제목의 페이지가 있는지 조회한다.
존재하면 page_id를 재사용한다.
없으면 새 페이지를 생성하고 page_id를 기록한다.

루트 페이지 본문에 다음 항목을 포함한다:
- 프로젝트명, frozen_at 타임스탬프
- graph.json 해시
- policy WO 수 / screen WO 수
- 생성될 하위 페이지 링크 목록 (업로드 완료 후 갱신)


### 단계 3 — policy WO 페이지 메타데이터 적용

> **본문은 /render --push 가 이미 업로드** 한 상태. 본 단계는 페이지 계층·
> 제목·레이블·draft frontmatter 핀만 처리.

policy 그룹의 각 draft 에 대해 순서대로 처리한다.

wiki 커넥터로 다음 작업을 수행한다.

**우선 커넥터 스키마 점검 — 본문 재push 가 publication 변환을 무효화하므로 필수:**

발견한 wiki 도구의 스키마를 읽어, 본문(body)을 건드리지 않고 제목·상위 페이지·
레이블만 갱신할 수 있는 작업(메타데이터 전용 update)을 지원하는지 확인한다.

분기:

1. **본문 미수정 메타데이터 갱신 지원** — 해당 작업을 스키마에 맞춰 호출한다.
   전달할 도메인 정보:
   - 대상 페이지: `{page_id}`
   - 제목: `{WO_ID} — {섹션 제목}`
   - 상위 페이지: `{root_page_id}`
   - 레이블: `{product}`, `policy`, `{WO_ID}`, `v1-frozen`

2. **미지원 (본문 포함 update 만 가능)** — `/render --push` 가 이미 본문 + 제목을 모두 정확히 업로드한
   상태이므로 본 단계 전체 skip. 레이블·parent 변경 필요 시 PM 에게:
   ```
   [cr] WARN: 연결된 wiki 커넥터가 본문 미수정 메타 갱신을 지원하지 않습니다.
        본문 재push 위험을 피하기 위해 메타데이터 적용을 skip 합니다.
        레이블·parent 변경이 필요하면 wiki UI 에서 직접 적용해주세요.
        page_id={page_id}, 적용 권고 항목: title, parent, labels
   ```
   안내 후 reports/cr-error.log 에 INFO 레벨로 기록.

**금지**: raw source(`drafts/{WO}.draft.md`)를 본문으로 하는 페이지 update 호출 —
이는 publication 변환을 거치지 않은 raw source 를 wiki 정본 페이지에 덮어쓰므로
HTML 주석·자기검증·DEC 마커가 정본 페이지에 노출됨. 어떤 경우에도 사용 금지.

성공 시 해당 draft 파일에 다음 필드를 추가한다 (frontmatter 가 아닌 본문
하단 메타블록 — publication prefilter 가 자동 제거함):
```
**confluence_page_id**: `{page_id}`
**confluence_url**: `{page_url}`
**uploaded_at**: `{UTC 타임스탬프}`
```

실패 시 `reports/cr-error.log`에 다음 형식으로 기록하고 다음 파일로 진행:
```
[FAIL] {WO_ID} | {오류 코드} | {오류 메시지} | {UTC 타임스탬프}
```


### 단계 4 — screen WO 페이지 메타데이터 적용

screen 그룹 처리 — 단계 3 과 동일 패턴이되 다음 차이:

페이지 제목: `{WO_ID} — {화면명} ({Screen ID})`
레이블: `{product}`, `screen`, `{Screen ID}`, `v1-frozen`

연관 policy 페이지 링크는 publication 변환 단계에서 본문에 이미 포함되어 있다
(`[[POL §X-Y]]` 마커 → Confluence 내부 링크). 본 단계에서 별도 본문 수정 불필요.


### 단계 5 — 인덱스 페이지 갱신

루트 페이지 본문을 업데이트한다.
업로드 완료된 모든 페이지의 제목 + URL을 policy / screen 섹션으로 분리해 삽입한다.
실패 건은 `[업로드 실패]` 표시와 함께 포함한다.


### 단계 6 — local-only 저장 (--local-only 또는 Confluence 전체 실패 시)

`reports/confluence-export/` 디렉토리를 생성한다.
각 draft를 그대로 복사하고 파일명에 타임스탬프를 추가한다:
`{WO_ID}_{YYYYMMDD}.draft.md`
`reports/confluence-export/index.md`에 전체 파일 목록을 작성한다.


### 단계 7 — session-log.md 기록

업로드 결과 요약을 `session-log.md`에 추가한다:
```
- {날짜} /cr 완료: 성공 {N}건 / 실패 {N}건, 루트 페이지: {URL}
```

실패 건이 있으면 `open-issues.md`에 P2로 등록한다.


## 결과 파일 목록

| 파일 | 변경 내용 |
|---|---|
| `drafts/*.draft.md` | confluence_page_id + confluence_url + uploaded_at 추가 |
| `session-log.md` | 업로드 결과 요약 기록 |
| `reports/cr-error.log` | 실패 건 기록 (실패 시에만 생성) |
| `reports/confluence-export/` | local-only 모드 시 파일 복사본 |


## 실패 처리 원칙

- 개별 파일 실패는 로그 기록 후 계속 진행한다.
- wiki 커넥터 연결이 전체 실패하면 local-only 모드 전환을 제안한다.
- 루트 페이지 생성 실패 시 즉시 중단하고 PM에게 권한 확인을 요청한다.
