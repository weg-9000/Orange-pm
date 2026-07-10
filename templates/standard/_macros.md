# 매크로 어노테이션 Reference (templates/standard/ 작성자 가이드)

> **목적**: `templates/standard/D*.md` 양식 작성·확장 시 사용 가능한 매크로 어노테이션을 한곳에 모은 실용 가이드.
> **사양 SSoT**: `orange-pm-plugin/skills/render/publication-syntax.md` (본 문서는 그 요약·실용 발췌).
> **검증**: `scripts/lint_publication_syntax.py` (L1~L7).

## 0. 기본 원칙

1. Markdown 정본 — XML 직접 작성 금지
2. 모든 매크로는 fenced div (`::: {.클래스}`) 또는 frontmatter 로 표현
3. 발행 시점에 `md_to_storage.py` 가 결정적 변환
4. 검증: 작성 후 `lint_publication_syntax.py --input <file>` 실행 권장

---

## 1. Frontmatter 표준 구조

```yaml
---
title: "[D1 제목] {{PRODUCT_NAME}}"     # Confluence 페이지 제목
wo_id: G2-DIRECT-D1                    # 또는 Track A 의 cluster ID (Phase 5 활성)
type: requirements                     # requirements|policy|screen|meetings|research|etc
layer: DIRECT                          # B(공통)|C(제품)|DIRECT(Track B/C 단일)
version: 1.0
last_updated: 2026-05-30

publication:
  # 상단 info macro (옵션)
  header:
    style: info                        # info|warning|note|tip
    body: |
      **{{PRODUCT_NAME}} 정의서**

      doc_id: {{DOC_ID}} 버전: {{VERSION}} 최종 수정: {{DATE}}

  # 메타 영역 — 참고자료/목차/change-history 등 (옵션)
  meta:
    layout: two_equal                  # single|two_equal|three_equal
    cells:
      - panel:
          title: "참고 자료"
          body: |
            - [[page:[정책정의서] {{PRODUCT_NAME}}]]
      - change_history: 5

  # Phase 3 색상 상태 (자동 — 수동 설정 금지)
  color_state: null
---
```

**화이트리스트 (publication.* 외 추가 필드)**: `title`, `wo_id`, `type`, `layer`, `version`, `last_updated`.  
**제거 (prefilter)**: 작성 메타, 자기검증 섹션, 금지사항, Workflow Connections 등.

---

## 2. 본문 매크로

### 2.1 Panel — 섹션 컨테이너 (가장 자주 사용)

```markdown
::: {.panel section="§N 섹션 제목"}
## §N 섹션 제목

### §N-1 소제목
본문 ...
:::
```

**Style 매핑** (`style=` attribute):

| style | 색상 (border / title) | 용도 |
|---|---|---|
| `common` (기본, 생략 가능) | `#24FE00` / `#002FD5` | 공통/제품 정책 표준 |
| `product` | `#0050E5` / `#FFFFFF` | 제품 고유 강조 |
| `tbd` | `#FF4D4F` / `#FFFFFF` | TBD/검토 필요 |
| `warning` | `#FAAD14` / `#FFFFFF` | 경고 |
| `info` | `#1890FF` / `#FFFFFF` | 정보성 |

**필수**: `section="..."` (lint L2). **선택**: `style="..."` (lint L3 — 허용 값만).

### 2.2 콜아웃 — info / warning / note / tip

```markdown
::: {.info}
정보성 메시지
:::

::: {.warning}
주의 사항
:::
```

→ `<ac:structured-macro ac:name="info|warning|note|tip">`. Layout 래퍼 없이 본문 흐름에 배치.

### 2.3 Expand — 접이식 영역

```markdown
::: {.expand title="상세 내용"}
숨겨질 본문
:::
```

### 2.4 코드블록

```markdown
​```python
def foo():
    return 42
​```
```

→ `<ac:structured-macro ac:name="code">` + `<ac:plain-text-body><![CDATA[...]]>`.  
언어 fence 지정 권장 (lint L4 — 알려진 언어): `python`, `bash`, `json`, `yaml`, `sql`, `javascript`, `typescript`, `markdown`, `xml`, `html`, `css`, `text`, `mermaid`, `plantuml`, `diff` 등.

---

## 3. 인라인 매크로

### 3.1 페이지 링크 — 다른 Confluence 페이지 참조

```markdown
[[page:[정책정의서] {{PRODUCT_NAME}}]]
```

→ `<ac:link><ri:page ri:content-title="..."/></ac:link>`.  
title 패턴은 일관성을 위해 `[D유형] {{PRODUCT_NAME}}` 형식 권장.

### 3.2 자동 매크로

| MD | XML 출력 | 용도 |
|---|---|---|
| `{{toc}}` | `<ac:structured-macro ac:name="toc"/>` | 본문 목차 자동 생성 |
| `{{change_history N}}` | `<ac:structured-macro ac:name="change-history">` + limit N | 최근 N건 변경 이력 |

### 3.3 Placeholder — 발행 시점 치환

| 표기 | 치환 시점 | 출처 |
|---|---|---|
| `{{PRODUCT_NAME}}` | publish 단계 | 제품 메타 |
| `{{DOC_ID}}` | publish 단계 | frontmatter |
| `{{VERSION}}` | publish 단계 | frontmatter |
| `{{DATE}}` | publish 단계 | 발행 일자 |
| `{{WO_ID}}` | publish 단계 | frontmatter |

위 5개는 lint L5 WARN 의 허용 목록. 다른 `{{...}}` 사용 시 WARN 발생 → 양식 의도일 경우 무시 가능.

---

## 4. 표 작성

```markdown
| 항목 | 내용 |
|---|---|
| **목적** | 본 정책서의 목적 |
| **범위** | 전체 |
```

→ `<table class="relative-table wrapped" style="width: 90%;">` + colgroup (기본 균등).

**컬럼 너비 명시** — HTML 주석 directive:

```markdown
<!-- col-widths: 15%, 85% -->
| 항목 | 내용 |
|---|---|
| 목적 | 본 정책서의 목적 |
```

**검증**: 헤더와 본문 행의 컬럼 수가 동일해야 함 (lint L7).

---

## 5. Phase 3 — 색상 Cycling (예약)

색상 cycling 활성 시 자동 산출. **양식 작성자가 수동 사용 X**.

```markdown
[변경된 텍스트]{.color-green}      ← 최신 변경 (#00B050)
[직전 변경 텍스트]{.color-blue}    ← 직전 변경 (#0050E5)
일반 텍스트                        ← 기본 (검정, span 미적용)
```

자동 cycling 메커니즘은 Phase 3 활성 시 `md_to_storage.py` + `diff_blocks.py` 가 발행 시점에 주입.

---

## 6. 양식 작성 체크리스트

새 deliverable 양식 추가 시 (예: D6, Dα_new):

1. **파일 위치**: `orange-pm-plugin/templates/standard/{D유형}_{이름}.md`
2. **Frontmatter**:
   - [ ] `title` 패턴 (`[D유형] {{PRODUCT_NAME}}`)
   - [ ] `type` 카테고리 (`requirements|policy|screen|meetings|research|etc`)
   - [ ] `layer` (`DIRECT` 기본, Track A 적용 시 `C`)
   - [ ] `publication.header` (옵션, 페이지 상단 안내가 필요할 때)
   - [ ] `publication.meta` (옵션, 참고자료/목차/change-history)
3. **본문**:
   - [ ] `::: {.panel section="..."}` 단위 섹션 분리
   - [ ] 헤딩 `## §N` 패턴 일관 (panel section 과 일치)
   - [ ] 표 컬럼 수 일관 (헤더↔본문)
   - [ ] 코드블록 언어 fence 지정
   - [ ] placeholder 는 5종 표준 사용 (그 외는 양식 의도임을 README 에 메모)
4. **검증**:
   - [ ] `python scripts/lint_publication_syntax.py --input templates/standard/{file}.md` → FAIL 0
   - [ ] `python scripts/md_to_storage.py --input ... --output /tmp/x.xml --validate` → exit 0
   - [ ] `python scripts/round_trip_test.py` 전체 통과
5. **문서**:
   - [ ] `templates/standard/README.md` 파일 목록 표 갱신
   - [ ] 신규 deliverable 의 Confluence 페이지 제목 패턴 등록

---

## 7. 자주 묻는 패턴

### Q. 섹션 안에 추가 콜아웃을 넣고 싶다

```markdown
::: {.panel section="§3 정책"}
## §3 정책

본문 ...

::: {.warning}
이 정책은 v2.0 부터 deprecated 예정.
:::

이어지는 본문 ...
:::
```

Nested 가능 — panel 안에 info/warning 등 자유 배치.

### Q. 표 안에 여러 줄 텍스트

```markdown
| 항목 | 설명 |
|---|---|
| A | 첫 줄<br/>두 번째 줄 |
```

`<br/>` 인라인 또는 단순 공백. 다중 단락이 필요하면 panel 로 분리 권장.

### Q. 페이지 제목에 한글 + 영문 혼용

```yaml
title: "[정책정의서] DBaaS for Berkeley"
```

따옴표 내부에 한/영/공백/괄호 모두 허용. backslash escape 없음.

### Q. 양식의 placeholder 가 lint WARN 으로 떠요

L5(미해결 placeholder) 는 WARN(비차단). 양식 작성 의도이면 그대로 둠. 양식 사용자(드래프트 단계)에서 치환되어야 함.

---

## 8. 변환기 / lint 빠른 실행

```bash
# 양식 lint
python orange-pm-plugin/scripts/lint_publication_syntax.py \
   --input orange-pm-plugin/templates/standard/D1_requirements.md

# 양식 → XML 변환 (검증 포함)
python orange-pm-plugin/scripts/md_to_storage.py \
   --input orange-pm-plugin/templates/standard/D2_policy.md \
   --output /tmp/D2.xml --validate

# 양식 round-trip 안정성 (전체 양식 일괄)
python orange-pm-plugin/scripts/round_trip_test.py
```

---

## 9. 참조

- 사양 SSoT: `orange-pm-plugin/skills/render/publication-syntax.md`
- 정책: `Planning-Agent-Hub/CONTEXT/project-rules.md` (Confluence 동기화 절)
- 변환기: `scripts/md_to_storage.py`, `scripts/storage_to_md.py`
- 검증: `scripts/lint_publication_syntax.py`, `scripts/render_verify.py`
