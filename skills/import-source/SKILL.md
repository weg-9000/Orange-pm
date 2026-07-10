---
name: import-source
description: |
  외부 소스(Confluence / GitLab / Notion / 로컬 파일)에서 임의 마크다운을 끌어와
  분석·정규화 후 reference-docs/{ACTIVE_PREFIX}/{A,B,C} 로 수용하는 멀티소스
  진입점이다. 멀티테넌트 SaaS 의 "첫 사용자 진입 1순위 = 외부 소스 임포트" 를
  구현한다. from-url(Confluence 전용)을 일반화한 상위 스킬이다.

  파이프라인: 페치 → import_normalize(레코드화) → frontmatter_detect(메타 정규화)
    → layer_classify(A/B/C 자동 분류) → term_extract(용어 후보 큐)
    → dependency_infer(의존성 후보 엣지) → PM 확인 게이트 → 승격.

  본 스킬은 외부 문서를 **읽기/분석만** 한다. reference-docs 정본 승격과
  glossary terms.yml 반영은 PM 확인 후에만 수행한다(자동 강제 금지).
triggers:
  - "임포트"
  - "가져와"
  - "이 문서 분석"
  - "이 문서 들여와"
  - "gitlab"
  - "notion"
  - "노션"
  - "외부 문서"
  - "import-source"
phase: any
effort: medium
model: direct
user-invocable: true
---

## Bootstrap 캐시 가드

세션 첫 진입 시 `CONTEXT/_session-bootstrap.md` 를 1회만 로드한다(재독 금지).
캐시가 없거나 stale 이면 갱신 후 진행:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```


## 1. 진입 조건

- 사용자가 외부 소스(Confluence/GitLab/Notion URL, 또는 로컬 .md)를 제시하며
  "임포트/가져와/분석/수용" 등 동사를 동반
- intent-router 가 임포트 의도를 라우팅
- PM 이 `/import-source <URL|경로> --product <p>` 로 직접 호출

Confluence 단일 URL 의 단순 환류는 기존 `/from-url` 로도 가능하다. 본 스킬은
**다소스 + 자동 분석(분류·용어·의존성)** 이 필요할 때 사용한다.


## 2. 소스 판별

| 소스 | 신호 | 페치 방법 |
|---|---|---|
| `confluence` | `confluence.../pages/{id}` | wiki 커넥터(Confluence 계열)의 조회(get) → snapshot JSON → `storage_to_md.py --from-snapshot` 로 MD 변환 |
| `gitlab` | `gitlab.../-/raw/.../*.md`, `.md` repo 경로 | repo 커넥터 또는 raw URL fetch — **MD 네이티브, 변환 불필요** |
| `notion` | `notion.so/...`, 페이지 ID | wiki 커넥터(Notion 계열)의 페이지 fetch → 마크다운 — **MD 네이티브** |
| `file` | 로컬 경로 / 붙여넣기 | 그대로 사용 |

`{id}` 는 소스별 안정 식별자(page_id / repo-path-slug / notion-page-id / 파일 stem).
`{product}` 미지정 시 PM 에게 어느 `PROJECTS/{product}` 로 수용할지 확인.


## 3. 페치 (모델/도구 책임)

인증·외부 호출은 모델이 도구로 수행한다(스크립트는 분석만 — from-url 과 동일 분리).
소스별 커넥터는 CONNECTORS.md 탐지 프로토콜로 확인한다(`CONTEXT/connectors.md`
매핑 우선, 없으면 자동 탐지).

- **Confluence 계열 wiki**: wiki 커넥터의 조회(get) 작업으로 page_id `{ID}` 페이지를
  가져와 id·title·version·본문(storage XML)을 포함한 snapshot JSON 으로
  `/tmp/{ID}.snapshot.json` 에 저장한 뒤, 로컬 변환:

  ```bash
  python ${CLAUDE_PLUGIN_ROOT}/scripts/storage_to_md.py \
    --input /tmp/{ID}.snapshot.json --from-snapshot --output /tmp/{ID}.md
  ```

- **GitLab**: repo 커넥터 또는 raw URL fetch 로 `.md` 본문을 취득해 `/tmp/{ID}.md` 로 저장.
- **Notion 계열 wiki**: wiki 커넥터의 페이지 fetch 결과(마크다운)를 `/tmp/{ID}.md` 로 저장.
- **file**: 입력 경로를 그대로 사용.

페치 실패(401/403/네트워크)는 명확히 보고하고, 수동 export → `--input` 우회를 안내한다.


## 4. 레코드화 (import_normalize)

페치된 MD 를 표준 임포트 레코드로 적재한다(본문 무손실, frontmatter 정규화):

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/import_normalize.py \
  --hub-root . --product {product} --source {source} --id {ID} \
  --input /tmp/{ID}.md --source-url "{URL}" --intent context
```

산출:
- `PROJECTS/{product}/inputs/imports/{source}/{ID}.md` (reference frontmatter + 본문)
- `PROJECTS/{product}/inputs/imports/{source}/{ID}.meta.json`

기존 meta.json 은 덮어쓰지 않는다(content 변동 시 경고만).


## 5. 분석 파이프라인

레코드 MD 를 입력으로 3종 분석을 실행하고 **제안 리포트**를 만든다.

```bash
REC=PROJECTS/{product}/inputs/imports/{source}/{ID}.md

# 5-A. 계층 자동 분류 (A/B/C, 저신뢰는 unknown → PM 확인)
python ${CLAUDE_PLUGIN_ROOT}/scripts/layer_classify.py --input $REC --json

# 5-B. 용어 추출 → 후보 큐 (terms.yml 직접 수정 금지)
python ${CLAUDE_PLUGIN_ROOT}/scripts/term_extract.py \
  --hub-root . --input $REC --source {source} --write-candidates

# 5-C. 의존성 추론 → 후보 엣지
python ${CLAUDE_PLUGIN_ROOT}/scripts/dependency_infer.py \
  --hub-root . --input $REC --doc-id {ID} \
  --out PROJECTS/{product}/inputs/imports/{source}/{ID}.edges.json
```

분류가 `unknown` 이거나 confidence 가 낮으면(임계 0.34 미만) 추측하지 말고
PM 에게 계층을 한 줄로 되묻는다. 복잡한 경계 판단이 필요하면 advisor 에 위임한다
(CLAUDE.md 라우팅 — 분류는 batch, 경계 판단만 advisor).


## 6. PM 확인 게이트 → 승격

리포트를 다음 형식으로 제시하고 PM 확정을 받는다(자동 승격 금지):

```
[import-source 제안 — {ID}]
- 계층: B (confidence 0.82) · 신호: 정책표현 9회, 공통참조 2회
- 신규 용어 후보: 3건 (term-candidates.yml)
- 의존성 후보: SELF → inherits_from → G2-B-002 (high)
- 제안 위치: CONTEXT/reference-docs/{ACTIVE_PREFIX}/B/{ID}.md
승인하시겠습니까? (계층 수정 가능)
```

PM 승인 후:
1. 레코드 MD 를 `CONTEXT/reference-docs/{ACTIVE_PREFIX}/{layer}/{ID}.md` 로 이동.
2. `master-id-map.yml` 에 `{ID}: {stem}` 등록(필요 시).
3. 캐시 재생성: `build_b_cache` / `build_b_index` / `build_a_index` / `build_c_index`.
4. 용어 후보(term-candidates.yml)·의존성 엣지는 PM 검토 후 `terms.yml`·graph 에 반영.


## 7. 사용 예시

```bash
# GitLab raw 마크다운 임포트 → 분석
/import-source https://gitlab.example.com/x/-/raw/main/policy.md --product dbaas

# Notion 페이지 임포트
/import-source https://www.notion.so/팀/계정정책-abc123 --product dbaas

# 로컬 파일 분석만
/import-source ./inbox/legacy-policy.md --product dbaas --source file
```


## 8. 주의사항

- **자동 강제 금지**: 계층 승격·용어 등재·엣지 확정은 모두 PM 확인 게이트 통과 후.
- **무손실**: import_normalize 는 본문을 수정하지 않는다(메타만 부착).
- **폐쇄 glossary 완화**: 신규 용어는 `term-candidates.yml` 스테이징 + `unknown_terms.log`
  누적. 정본 `terms.yml` 은 PM 승인 후 수동 반영.
- **PREFIX 스코프**: 승격 위치는 항상 `ACTIVE_PREFIX` 하위. 타 PREFIX 로 수용하려면
  `layer-config.md` 의 `ACTIVE_PREFIX` 전환 후 진행.


## 9. 워크플로 연결

```
[외부 소스] ─→ /import-source ─→ import_normalize ─→ frontmatter_detect
                                      ↓
        layer_classify ─ term_extract ─ dependency_infer ─→ 제안 리포트
                                      ↓ (PM 확인)
        reference-docs/{ACTIVE_PREFIX}/{A,B,C}/  +  캐시 재생성
```

- **선행**: `intent-router`(임포트 의도 감지) 또는 PM 직접 호출
- **관련**: `/from-url`(Confluence 단순 환류), `/ingest`(신규 product 선행)
- **재사용 스크립트**: `storage_to_md.py`, `migrate_draft_frontmatter.py`(파싱),
  `build_a_index.extract_terms`, `drift_scan`/`master-id-map`(엣지 해소)


## 10. 출력 파일 목록

| 파일 | 생성 조건 | 내용 |
|---|---|---|
| `inputs/imports/{source}/{ID}.md` | 항상 | reference frontmatter + 본문(무손실) |
| `inputs/imports/{source}/{ID}.meta.json` | 신규 임포트 | source/url/intent/content_sha |
| `inputs/imports/{source}/{ID}.edges.json` | 분석 5-C | 의존성 후보 엣지 |
| `CONTEXT/glossary/term-candidates.yml` | 분석 5-B | 용어 후보 큐(PM 승인 전) |
