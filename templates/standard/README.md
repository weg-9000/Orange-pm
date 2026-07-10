# 내장 표준 양식 (templates/standard/)

> **상태**: Phase 1F 마이그레이션 산출 (Option A — MD-only 정본)
> **이전**: `Planning-Agent-Hub/templates/confluence-xml/*.xml` (deprecated)

## 목적

새 제품의 Confluence 문서를 처음 생성할 때 사용하는 **MD 정본 양식**.
`md_to_storage.py` 가 발행 시점 XML 로 결정적·멱등 변환한다.

Track A/B/C 모두에서 — 사용자가 별도 "양식 URL"(Pattern 2 의 URL_A)을 주지
않아도 자동으로 이 양식이 적용된다 (사양: publication-syntax.md).

## 파일 목록

### 표준 5종 (D1~D5)
| 파일 | Deliverable | type | layer | Confluence 페이지 제목 패턴 | LOC |
|---|---|---|---|---|---|
| `D1_requirements.md` | 요구사항정의서 | requirements | DIRECT | `[요구사항 정의서] {{PRODUCT_NAME}}` | 156 |
| `D2_policy.md` | 정책정의서 | policy | DIRECT | `[정책정의서] {{PRODUCT_NAME}}` | 148 |
| `D3_screen.md` | 화면설계서 | screen | DIRECT | `[화면설계서] {{PRODUCT_NAME}}` | 141 |
| `D4_meetings.md` | 회의록 (rolling) | meetings | DIRECT | `[회의록] {{PRODUCT_NAME}}` | 198 |
| `D5_research.md` | 타사조사 | research | DIRECT | `[타사조사] {{PRODUCT_NAME}}` | 286 |

### etc 카테고리 (Dα — 선택적)
| 파일 | Deliverable | 사용 케이스 | LOC |
|---|---|---|---|
| `Dα_api.md` | API 스펙 | REST API 노출 제품 | 252 |
| `Dα_db.md` | DB 스키마 | DBaaS / 데이터 집약형 제품 | 226 |
| `Dα_migration.md` | 마이그레이션 플랜 | 시스템 이전 / 데이터 마이그레이션 | 245 |

### 참조 문서
- `_macros.md` — 매크로 어노테이션 reference (양식 작성자 가이드)

### split-deliverable 발행 모드에서의 D2/D3 (fix-plan-dossier-publish-split)

Track A 의 `publication_mode: split-deliverable` 에서는 D2_policy.md / D3_screen.md
가 `render_transpose.py --template` 의 **골격 frontmatter 출처**로 쓰인다(본문은
dossier §1/§2 에서 transpose 로 채움). 즉 양식은 그대로 두고, 발행 산출물
`reports/render/02-policy.assembled.md` / `03-screen-design.assembled.md` 의
frontmatter 만 이 양식에서 가져온다. `cluster-draft.md` 의 `is_common_shell` 필드가
D3 공통 셸 부록 라우팅을 결정한다.

## 비표준 placeholder 등록 (양식 의도)

표준 5종(`{{PRODUCT_NAME}}`, `{{DOC_ID}}`, `{{VERSION}}`, `{{DATE}}`, `{{WO_ID}}`) 외에 각 양식이 사용하는 placeholder. lint L5 WARN 으로 떠도 양식 의도이므로 무시 가능:

| 양식 | 주요 비표준 placeholder |
|---|---|
| D4_meetings | `{{MEETING_DATE_*}}`, `{{MEETING_TIME_*}}`, `{{MEETING_TOPIC_*}}`, `{{ATTENDEES_*}}`, `{{ABSENTEES_*}}`, `{{MEETING_VENUE_*}}`, `{{CLUSTER_REFS_*}}`, `{{YYYYMMDD_*}}` |
| D5_research | `{{COMPETITOR_1~3}}`, `{{TAM/SAM/SOM}}`, `{{REF/REF_1~3/URL}}`, `{{SLA}}`, `{{TREND_*}}`, `{{기능명}}`, `{{단가}}`, `{{요금제명}}` |
| Dα_api | `{{ENDPOINT_GROUP_1~2}}`, `{{TOKEN}}`, `{{CLIENT_ID/SECRET}}`, `{{ERROR_CODE}}`, `{{access/refresh token TTL}}` |
| Dα_db | `{{TABLE_1~2}}`, `{{TABLE_LARGE}}` (DB 종류 placeholder도 있음) |
| Dα_migration | `{{YYYYMMDD}}`, `{{SOURCE_HOST}}`, `{{TARGET_HOST}}`, `{{DB}}`, `{{USER}}`, `{{ms}}`, `{{담당}}`, `{{승인자}}`, `{{new_col}}` |

## 사용 방법

### 신규 제품 초기화 (Track A — Full Product)
```bash
# 1) 표준 양식 복사
cp orange-pm-plugin/templates/standard/D1_requirements.md \
   Planning-Agent-Hub/PROJECTS/{product}/drafts/D1.draft.md
cp orange-pm-plugin/templates/standard/D2_policy.md \
   Planning-Agent-Hub/PROJECTS/{product}/drafts/D2.draft.md
cp orange-pm-plugin/templates/standard/D3_screen.md \
   Planning-Agent-Hub/PROJECTS/{product}/drafts/D3.draft.md

# 2) placeholder 치환 (PRODUCT_NAME, DOC_ID, VERSION, DATE 등)

# 3) Confluence 페이지 생성 후 meta.json 에 page_id 입력

# 4) 발행
python orange-pm-plugin/scripts/md_to_storage.py \
   --input PROJECTS/{product}/drafts/D2.draft.md \
   --output /tmp/D2.xml --validate
# → /render --push 가 자동 호출 (publication-syntax 표준 매크로 변환)
```

### 단일 deliverable (Track B/C — Single / Template-Copy, Phase 4 활성)
```bash
# URL 진입 사용자: from-url skill (Phase 4) 이 자동으로 이 양식 적용
/render --from-url https://confluence.../pages/123 --target D2
```

## 양식의 구조 (publication-syntax.md 사양 §2~§7 준수)

- **Frontmatter**:
  - `title`, `wo_id`, `type`, `layer`, `version`, `last_updated`
  - `publication.header` — 상단 info 매크로
  - `publication.meta.layout` — 참고자료/목차/change-history 레이아웃
- **본문**:
  - `::: {.panel section="§N ..."}` 블록으로 섹션 구획
  - 기본 style은 common (#24FE00 / #002FD5) — 사양 §3.1
  - 표는 `<!-- col-widths: ... -->` directive 로 컬럼 비율 명시
  - placeholder `{{PRODUCT_NAME}}` / `{{DOC_ID}}` / `{{VERSION}}` / `{{DATE}}` 등

## 검증

```bash
# MD 단계 lint (사전 검증)
python orange-pm-plugin/scripts/lint_publication_syntax.py \
   --input orange-pm-plugin/templates/standard/D1_requirements.md

# XML 변환 + round-trip 검증
python orange-pm-plugin/scripts/md_to_storage.py \
   --input orange-pm-plugin/templates/standard/D2_policy.md \
   --output /tmp/D2.xml --validate
```

각 양식은 publication-lint L1~L7 PASS 또는 WARN(허용 placeholder)만 발생.

## Round-trip 검증 (Phase 1D)

`scripts/round_trip_test.py` 가 MD→XML→MD 멱등성과 실제 fixture XML 변환을
검증한다. 이 양식들은 1F 마이그레이션 산출이므로 round-trip 안정성 보장.
