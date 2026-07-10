---
name: from-url
description: |
  Confluence URL 을 진입점으로 받아 페이지 본문을 repo MD 정본으로 변환·환류한다.
  사용자가 "이 URL 에 타사조사 후 작성", "이 URL_A 양식으로 URL_B 작성" 같은
  의도를 표현했을 때 호출됨 (intent-router 가 라우팅하거나 PM 직접 호출).

  주요 동작:
    1. URL 에서 page_id 추출 (https://confluence.../pages/{id} 패턴)
    2. wiki 커넥터 조회(get) → snapshot JSON 수집
    3. storage_to_md.py 로 MD 변환 (publication-syntax.md 역방향 사양)
    4. inputs/confluence-pulls/{page_id}.md 에 저장 (정본 환류 입구)
    5. meta.json 자동 생성 (page_id, title, version, _color_state.baseline=true)
    6. URL 의도(target / template / context) 분기 후 후속 스킬 권고

  본 스킬은 Confluence 페이지 본문을 **읽기만** 한다. 발행/편집은
  render --push 가 담당한다 (Confluence 직접 편집 금지 정책 — project-rules.md).
triggers:
  - "URL 던지면"
  - "이 페이지"
  - "Confluence URL"
  - "https://confluence"
  - "양식 보고"
  - "이 url 에"
  - "이 url 로"
  - "이 페이지에 작성"
  - "이 양식으로 작성"
  - "from-url"
phase: any
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


## 1. 진입 조건

다음 중 하나에 해당하면 본 스킬이 활성화된다:

- 사용자 메시지에 `https://confluence...` URL 이 1~2개 포함되고,
  "작성/보고/양식/참고" 등 동작 동사가 함께 등장
- 자연어 트리거: "이 URL 에 작성", "이 페이지 보고", "이 양식으로",
  "URL_A 형식대로 URL_B 작성"
- intent-router 가 URL 진입 의도를 감지하여 본 스킬로 라우팅
- PM 이 `/from-url <URL>` 로 직접 호출

URL 이 없고 단순히 "page_id 12345" 같이 ID 만 제시된 경우에도
**단계 2** 부터 동일하게 동작한다 (URL 파싱 단계 skip).


## 2. URL 파싱

Confluence URL 에서 다음 정보를 결정적으로 추출한다:

| 정보 | 정규식 | 예시 |
|---|---|---|
| `page_id` | `pages/(\d+)` | `pages/12345` → `12345` |
| `spaceKey` | `spaces/([^/]+)/pages` | `spaces/TEAMX/pages/...` → `TEAMX` |
| `title slug` | `pages/\d+/([^/?#]+)` | URL 끝의 슬러그 (선택) |

지원 URL 형태:
- `https://confluence.example.com/wiki/spaces/{SPACE}/pages/{PAGE_ID}/{TITLE}`
- `https://confluence.example.com/pages/viewpage.action?pageId={PAGE_ID}`
- `https://confluence.example.com/display/{SPACE}/{TITLE}` — 이 형태는
  page_id 가 URL 에 없으므로 PM 에게 page_id 를 직접 확인 요청한다.

추출 실패 시 PM 에게 page_id 를 직접 입력하도록 1줄 안내 후 중단.


## 3. 전제조건 검사

1. **wiki 커넥터 가용성**: wiki 커넥터(사용자가 연결한 MCP 도구 — 예: Confluence 등)를
   CONNECTORS.md 탐지 프로토콜로 확인한다. `CONTEXT/connectors.md` 매핑 우선,
   없으면 자동 탐지. 발견한 도구가 페이지 본문(storage XML)·version 을 포함한
   조회(get)를 지원해야 snapshot JSON shape 를 구성할 수 있다.

   커넥터 부재 또는 미지원 시 본 스킬은 동작하지 않는다 (snapshot JSON
   shape 가 필요). CONNECTORS.md 의 안내문을 출력하고
   "수동 export → `--xml-file` 옵션으로 우회 가능" 안내.

2. **PM Confluence 권한**: 해당 페이지 read 가능 여부. `get` 시도가 401/403
   으로 실패하면 권한 문제 안내 + 대안 (수동 export → 본 스킬 `--xml-file`
   옵션으로 우회) 제시.

3. **사용자 의도 분기** (intent-router 또는 PM 발화로 결정):

   | 의도 | 의미 | 후속 스킬 |
   |---|---|---|
   | **target URL** | 작성 대상 (비어 있거나 새로 작성할 페이지) | `/render --push` |
   | **template URL** | 양식 원본 (구조만 참고, 본문은 버림) | `/extract-template` |
   | **context URL** | 참고용 자료 (타사조사·요구분석 입력) | `/draft-req` 또는 `/research` |

   의도 분류는 사용자 발화로 결정:

   - "여기에 작성" / "이 페이지를 채워" → **target**
   - "이 양식대로" / "이거 보고 똑같이" → **template**
   - "이거 참고해서" / "이거 보고 분석" → **context**

   모호하면 추측하지 말고 PM 에게 한 줄로 되묻는다.

4. **product context**: `{product}` 가 미지정이면 PM 에게 어느 PROJECTS 하위에
   환류할지 확인. 신규 product 이면 `/ingest {product}` 선행 권고.


## 4. 변환 단계

### 4-A. snapshot 수집 (모델 책임)

외부 호출은 wiki 커넥터의 도구 호출로만 수행한다 — 스크립트는 로컬 파일 처리
전용이다 (인증·도구 분리 원칙, CONNECTORS.md — `/render` 와 동일 패턴):

```bash
mkdir -p Planning-Agent-Hub/PROJECTS/{product}/inputs/confluence-pulls
```

발견한 wiki 도구의 스키마에 맞춰 페이지 조회(get) 작업을 호출한다 —
대상: page_id `{PAGE_ID}`. 응답에서 id·title·version·본문(storage XML)을
추출해 아래 shape 의 JSON 으로 `/tmp/{PAGE_ID}.snapshot.json` 에 저장한다.

snapshot JSON 기대 shape (storage_to_md 가 다음 키만 사용):

```json
{
  "id": "12345",
  "version": {"number": 7, "when": "2026-05-28T..."},
  "title": "...",
  "body": {"storage": {"value": "<xml>...</xml>"}}
}
```

### 4-B. snapshot → MD 역변환

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/storage_to_md.py \
  --input /tmp/{PAGE_ID}.snapshot.json --from-snapshot \
  --output Planning-Agent-Hub/PROJECTS/{product}/inputs/confluence-pulls/{PAGE_ID}.md
```

변환기는 `publication-syntax.md` §8 round-trip 사양을 따른다 — 본문·표·코드블록·
패널은 100% 보존, Confluence 직접 편집된 사용자 정의 매크로는 텍스트 보존만.

종료 코드 1 (XML 파싱 실패) 또는 2 (미지원 매크로 경고) 발생 시 PM 에게
보고만 하고 다음 단계는 계속 진행 (텍스트는 보존됨).


## 5. meta.json 자동 생성

환류 직후 같은 디렉토리에 `{PAGE_ID}.meta.json` 을 생성한다.
snapshot JSON 의 `id` / `title` / `version.number` 를 가져와 다음 구조로 저장:

```json
{
  "id": "12345",
  "title": "원본 페이지 제목",
  "source_url": "https://confluence.../pages/12345",
  "pulled_at": "2026-05-30T...",
  "pulled_version": 7,
  "intent": "target | template | context",
  "_sync": {
    "last_published_version": null,
    "last_published_at": null
  },
  "_color_state": {
    "publish_round": 0,
    "previous_source_hash": null,
    "previous_green_regions": [],
    "baseline": true
  }
}
```

`_color_state.baseline = true` 는 Phase 3 색상 cycling 의 첫 라운드를
보장한다 (publication-syntax.md §6.4).

기존 `{PAGE_ID}.meta.json` 이 있으면 **덮어쓰지 않는다** — PM 에게 기존 메타와의
충돌을 알리고 `pulled_version` 만 갱신할지 확인.


## 6. 분기 후속 안내

저장 완료 후 의도별로 후속 스킬을 권고한다:

| 의도 | 권고 |
|---|---|
| **target** | 빈 페이지면 양식 적용 후 `/render {product} --push` 로 작성·발행. 기존 본문 있으면 단계 8 "덮어쓰기 게이트" 적용. |
| **template** | `/extract-template inputs/confluence-pulls/{PAGE_ID}.md` 로 양식 추출 → `templates/standard/{name}.md` 또는 `templates/render/custom/{name}.md` 등재. |
| **context** | `/draft-req {product}` (요구사항 작성 입력) 또는 `/research {product}` (조사 입력) 의 source 로 등재. PM 에게 어느 워크오더에 입력할지 확인. |

권고는 1줄 안내로 출력하고 자동 실행하지 않는다.


## 7. 사용 예시

```bash
# (1) 신규 작성 — 빈 페이지에 양식 적용 후 채워넣기
/from-url https://confluence.example.com/wiki/spaces/G/pages/12345 --target D2
# → inputs/confluence-pulls/12345.md (빈 본문)
# → 후속: /render dbaas WO-POL-001 --push

# (2) 양식 추출 — URL_A 보고 URL_B 에 작성
/from-url https://confluence.../pages/A --as-template
# → inputs/confluence-pulls/A.md + intent=template
# → 후속: /extract-template inputs/confluence-pulls/A.md
/from-url https://confluence.../pages/B --target D2 --template-from A
# → B.md 골격에 A 양식 적용

# (3) 타사조사 참고 — context 의도
/from-url https://confluence.../pages/77777 --as-context
# → inputs/confluence-pulls/77777.md + intent=context
# → 후속: /research dbaas (이 URL 을 source 로 등재)

# (4) 기존 페이지 보강 — 환류 후 sync check 안내
/from-url https://confluence.../pages/12345 --augment
# → 기존 meta.json 충돌 감지 → PM 확인 후 pulled_version 만 갱신

# (5) page_id 만 알 때
/from-url 12345 --product dbaas --target D1
```


## 8. 주의사항

- **Confluence 직접 편집 금지 정책 (project-rules.md §Confluence 동기화)**:
  본 스킬은 페이지 본문을 환류만 한다. PM 이 Confluence WebUI 에서 본문을
  편집했다면 REMOTE-DRIFT 로 처리되어야 하며, 본 스킬이 아니라
  `/render --check-sync --with-remote` + `--apply-inbox` 로 흡수한다.
  본 스킬은 **새 입력 자료**의 환류 입구일 뿐이다.

- **URL 권한 부족** (`401/403`): 명확한 오류 메시지 + 대안 안내
  ("Confluence WebUI 에서 export → XML 파일 경로로 `--xml-file` 옵션 사용").

- **기존 페이지 콘텐츠가 있으면 덮어쓰기 게이트**:
  target 의도이고 페이지 본문이 비어 있지 않으면 PM 에게 명시적으로 확인:
  - 덮어쓰기: 기존 본문 폐기, 새 양식 적용
  - 병합: 기존 본문 + 새 섹션 추가 (수동 병합)
  - 부록 추가: 기존 본문 보존, 끝에 신규 섹션 append

  세 옵션 중 하나가 명확히 선택될 때까지 render --push 권고를 보류한다.

- **storage_to_md 미지원 매크로**: 텍스트만 보존되고 매크로 구조는 손실됨.
  PM 에게 손실 항목을 보고하고 수동 보강 권장.

- **page_id 충돌**: 두 product 가 동일 URL 을 환류하면 `meta.json.id` 가
  중복된다. 본 스킬은 product 별 디렉토리 격리로 우회하지만, render --push
  단계에서 SSoT 위반으로 차단될 수 있음 (`CONTEXT/ssot-boundary.yml` 참조 —
  `/init-hub` 가 스캐폴딩한다). 단, 이 파일이 없거나 owner 가 비어 있으면
  render --check-ssot 는 경고만 하고 통과한다(hard-fail 없음, graceful degrade) —
  본 스킬의 환류 자체는 ssot-boundary.yml 유무와 무관하게 항상 수행된다.


## 9. 워크플로 연결

```
              ┌─── target  ──→  /render --push (단계 6-1 publication 변환)
              │
[Confluence URL] ──→ /from-url ──┼─── template ──→  /extract-template
              │                        ↓
              │                  templates/standard/ 또는
              │                  templates/render/custom/ 등재
              │
              └─── context ──→  /draft-req | /research
                                  (URL 을 입력 source 로 등재)
```

- **선행**: `intent-router` (URL 진입 감지 → 본 스킬 라우팅)
- **선행 (직접 호출 시)**: 없음 — PM 발화 직접 진입
- **후속 (의도별)**:
  - target → `/render` 또는 `/render --push`
  - template → `/extract-template`
  - context → `/draft-req` / `/research` / `/research-auto`
- **사양 참조**:
  - `publication-syntax.md` (storage_to_md 산출 MD 의 문법)
  - `project-rules.md` §Confluence 동기화 (정본 정책)


## 10. 출력 파일 목록

| 파일 | 생성 조건 | 내용 |
|---|---|---|
| `inputs/confluence-pulls/{PAGE_ID}.md` | 항상 | snapshot 본문의 MD 환류본 |
| `inputs/confluence-pulls/{PAGE_ID}.meta.json` | 신규 환류 시 | page_id/title/version + `_color_state.baseline=true` |
| `/tmp/{PAGE_ID}.snapshot.json` | 항상 (임시) | wiki 커넥터 조회(get) 원본 JSON |
| `inputs/confluence-pulls/{PAGE_ID}.warnings.log` | storage_to_md 경고 시 | 미지원 매크로·파싱 경고 목록 |
