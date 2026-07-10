---
name: extract-template
description: |
  위키 페이지(URL_A — 예: Confluence) 에서 구조 패턴(heading tree, panel pattern, table convention,
  terminology) 을 추출해 동적 템플릿으로 변환한다. Track C (Template-Copy) 의 URL_A
  옵션 입력에서만 발동. 내장 양식(templates/standard/) 이 기본 — 본 스킬은 override.

  추출 항목:
    1. Heading 구조 (§N 패턴 + 깊이)
    2. Panel 사용 패턴 (style 분포, section 명명 규약)
    3. Table 컬럼 컨벤션 (자주 등장하는 컬럼명 + 너비)
    4. Terminology (자주 등장하는 도메인 용어)
    5. 매크로 사용 분포 (info/warning/expand 빈도)
triggers:
  - "이 양식으로"
  - "이 양식 보고"
  - "URL_A"
  - "이 URL 처럼"
  - "이런 형식으로 작성"
  - "양식 추출"
phase: any
effort: medium
user-invocable: true
---

## 0. 위치 — Track C / Template-Copy 경로의 옵션 단계

```
[PM 발화]  "URL_A 양식 보고 URL_B 에 작성해줘"
   │
   ├─ from-url(URL_A, --as-template)   ← 선행 (페이지 pull → inputs/confluence-pulls/{ID}.md)
   │
   ├─ extract-template                 ← 본 스킬 (구조 추출 → templates/extracted/{ID}.template.md)
   │      └─ PM 확인 게이트
   │
   ├─ from-url(URL_B, --target D2, --template-from pages/A)
   │
   └─ render / write / cluster draft   ← 후속 (extracted template 을 base 로 사용)
```

**기본 동작은 본 스킬 비호출** — 내장 양식(`orange-pm-plugin/templates/standard/D*.md`) 이 SSoT.
사용자가 명시적으로 URL_A 를 양식 원본으로 지정한 경우에만 본 스킬이 활성화된다.

---

## 1. 진입 조건

| 조건 | 필수 / 선택 | 비고 |
|---|---|---|
| 사용자가 URL_A(양식 원본) 를 **명시적으로** 지정 | 필수 | "이 양식 보고", "이 URL 처럼", "--template-from" |
| from-url 스킬이 URL_A 를 이미 pull 완료 | 필수 | `inputs/confluence-pulls/{page_id}.md` 존재 |
| URL_A 의 본문 길이 / heading 개수 ≥ 임계값 | 선택(권고) | heading <3 이면 추출 가치 낮음 — §7 참고 |
| intent-router 에서 "Track C / Template-Copy" 로 라우팅 | 필수 | 비명시 호출 금지 |

**금지 시나리오** (본 스킬을 자동 호출하지 말 것):
- Track A (cluster 기반 작성) 의 일반 작성 흐름
- Track B 단일 정의서 작성에서 URL_A 미지정
- 내장 양식만으로 충분한 통상 작성 요청

---

## 2. 전제조건 (Preflight)

1. **from-url 선행**: `inputs/confluence-pulls/{page_id}.md` 가 존재해야 함.
   - 없으면: 본 스킬은 작업을 중단하고 PM 에게 from-url 선행을 안내한다.
     ```
     URL_A 가 아직 pull 되지 않았습니다.
     먼저 `/from-url <URL_A> --as-template` 로 페이지를 가져오세요.
     ```
2. **publication-syntax 표준 호환 점검**: 풀된 MD 가 fenced div(`::: {.panel}` 등) 를 사용하고 있어야
   고정밀 추출이 가능. 비표준이면 §7 의 부분 추출 모드로 fallback.
3. **출력 디렉터리**: `orange-pm-plugin/templates/extracted/` 가 없으면 생성한다.

---

## 3. 추출 절차

전체 추출은 5단계로 결정적 수행. 각 단계는 독립적이며 실패 시 해당 항목만 누락 처리하고 계속 진행.

### 3-A. Heading 구조 추출

- 입력: `inputs/confluence-pulls/{page_id}.md` 의 본문
- 정규식: `^(#+)\s+(.+)$`
- `§N` / `§N-M` 패턴 인식 (한글 `§` + 숫자, 하위는 `-` 구분)
- 산출:
  - heading tree (depth + 텍스트 + 등장 순서)
  - §N 시퀀스 (시작 번호, 끝 번호, 결번 여부)

```
예시 추출 결과:
H2  §1 정책 개요          (line 22)
H3  §1-1 목적             (line 27)
H3  §1-2 적용 범위        (line 35)
H2  §2 공통 정책          (line 54)
...
```

### 3-B. Panel pattern 추출

- 정규식: `^:::\s*\{\.panel\s+section="([^"]+)"\s*(.*?)\}$`
- 추출 필드:
  - `section` 값 (전체 panel section 이름 목록)
  - `style` attribute (없으면 `common` 으로 정규화)
- 통계:
  - style 별 빈도 (`common`/`product`/`tbd`/`warning`/`info`)
  - section 명명 컨벤션 (§N 접두? 한글? 영문 혼용?)

### 3-C. Table convention 추출

- 표 헤더 행 추출 (직전 라인 `|...|`, 다음 라인 `|---|---|`)
- 표 직전 HTML 주석 `<!-- col-widths: ... -->` 매칭
- 통계:
  - 표 개수
  - 평균 컬럼 수, 최대/최소
  - 자주 등장하는 컬럼명 (예: "항목/내용", "FR ID/우선순위", "결정/담당/기한")
  - col-widths directive 사용 비율

### 3-D. Terminology 추출

- 빈도순 명사구 (간단 휴리스틱):
  - 한글 2~6자 명사구 추출 (조사/어미 제거)
  - 영문/약어 (예: `SLA`, `API`, `DBaaS`) 별도 수집
  - 자사 도메인 사전(`CONTEXT/glossary.md` 가 있으면 cross-reference)
- 상위 N(=20) 개를 결과로 저장
- 영문/한글 혼용 패턴 (예: "DBaaS 인스턴스") 별도 표기

### 3-E. 매크로 분포

- 호출 횟수:
  - `::: {.info}`, `{.warning}`, `{.note}`, `{.tip}`, `{.expand}` 각 빈도
  - 사용 위치 분류 (panel 내부 / 본문 직접)
- 코드블록 언어 분포 (`mermaid`, `python`, `bash`, ...)
- 인라인 매크로: `{{toc}}`, `{{change_history N}}`, `[[page:...]]` 등장 횟수

---

## 4. 출력 형태

### 4.1 파일 위치

```
orange-pm-plugin/templates/extracted/{page_id}.template.md
```

기존 파일 존재 시: PM 에게 덮어쓸지 / suffix 추가(`.v2.template.md`) 할지 묻는다.

### 4.2 파일 구조 (반(半) 양식 — placeholder 골격)

```markdown
---
extracted_from:
  page_id: "{ID}"
  title: "{원본 페이지 제목}"
  extracted_at: YYYY-MM-DD
  source_pull: inputs/confluence-pulls/{page_id}.md

publication:
  header:
    style: info
    body: |
      **{{PRODUCT_NAME}} 정의서 (URL_A 양식 기반)**

      doc_id: {{DOC_ID}} 버전: {{VERSION}} 최종 수정: {{DATE}}
  meta:
    layout: two_equal          # 원본의 meta layout 추론 결과
    cells:
      - panel:
          title: "참고 자료"
          body: |
            - [[page:{{LINK_PLACEHOLDER}}]]
      - change_history: 3
---

<!-- ============================================ -->
<!-- HEADING TREE (원본에서 추출, placeholder 화) -->
<!-- ============================================ -->

::: {.panel section="§1 {SECTION_1_NAME}"}
## §1 {SECTION_1_NAME}

### §1-1 {SUBSECTION_1_1_NAME}

{{본문 작성}}

### §1-2 {SUBSECTION_1_2_NAME}

<!-- col-widths: {COL_WIDTHS_HINT} -->
| {COL_1_NAME} | {COL_2_NAME} |
|---|---|
| {{내용}} | {{내용}} |
:::

::: {.panel section="§2 {SECTION_2_NAME}"}
## §2 {SECTION_2_NAME}
...
:::

<!-- ============================================ -->
<!-- 추출 통계 (PM 검토용 — 발행 시 제거됨) -->
<!-- ============================================ -->
<!-- heading: H2=N, H3=M, max_depth=D -->
<!-- panel:  common=X, product=Y, tbd=Z, warning=W, info=V -->
<!-- table:  count=N, avg_cols=X, freq_cols=[항목,내용,...] -->
<!-- macro:  info=N, warning=M, expand=K, code_blocks=L -->
<!-- term:   top20=[SLA, DBaaS, 인스턴스, ...] -->
```

**원칙**:
- 모든 자유 텍스트는 `{{...}}` placeholder 로 치환 (lint L5 WARN — 양식 의도이므로 수용).
- 섹션/컬럼 명도 `{...}` 로 표시하여 PM 이 수정 가능함을 명시.
- 통계는 HTML 주석 (`<!-- ... -->`) 으로 보존 — publication-prefilter 가 제거.

---

## 5. PM 확인 게이트

추출 결과 요약을 PM 에게 제시하고 진행 여부를 확인받는다. 자동 진행 금지.

```
URL_A "{원본 페이지 제목}" 추출 완료.

  Heading:   H2 = 5, H3 = 14, 최대 깊이 = 3
  Panel:     common = 4, tbd = 1, info = 0  (총 5)
  Table:     8 개 (평균 3 컬럼). 빈출 컬럼: 항목/내용, FR ID/우선순위/내용
  매크로:    info = 2, warning = 1, expand = 3, code = 0
  용어:      상위 — SLA, DBaaS, 인스턴스, 백업, 복구, ...

→ templates/extracted/{page_id}.template.md 생성됨.

이 골격으로 URL_B 작성 진행할까요?
  (y) 진행
  (e) 수정사항 알려주세요 — heading 추가/삭제, style 조정 등
  (n) 중단 — 내장 양식으로 전환
```

PM 수정 입력 예시 처리:
- "§3 추가" → template 에 `::: {.panel section="§3 {SECTION_3_NAME}"}` 삽입
- "style tbd → warning" → panel attribute 일괄 변경
- "테이블 컬럼명 정리" → 사용자 입력 컬럼명으로 치환

---

## 6. 후속 라우팅

PM 승인 후, 다음 스킬에 본 템플릿을 인계한다.

| 후속 스킬 | 인계 방법 |
|---|---|
| `from-url` (URL_B pull) | `--template-from pages/{page_id}` 플래그로 본 template 경로 전달 |
| `write` / cluster draft | `--template templates/extracted/{page_id}.template.md` |
| `render` | 동일 — `--template` 플래그 |

후속 스킬은 본 template 을 **내장 양식 대신** base 로 사용. publication-syntax 검증은 동일하게 적용된다.

---

## 7. 추출 실패 / 부분 추출 케이스

| 상황 | 동작 |
|---|---|
| URL_A 가 fenced div 미사용 (구버전 storage XML 만 존재) | heading + table 만 추출, panel 통계는 "n/a". PM 에게 "비표준 영역 — 골격만 제공" 안내 |
| heading 개수 < 3 | "양식 추출 가치 낮음. 내장 양식(`templates/standard/D*.md`) 권장" 안내 후 본 스킬 중단 |
| from-url pull 실패 (권한 / 404) | from-url 스킬에서 이미 오류 → 본 스킬은 진입 자체 거부 |
| 빈 페이지 / 본문 0자 | "URL_A 가 비어있어 추출 불가" 명시적 오류 |
| publication-syntax lint FAIL 다수 (panel section 누락 등) | 부분 추출 + 경고 출력. PM 이 수동 보완 |

---

## 8. 워크플로 연결

```
선행 (필수):
  /from-url <URL_A> --as-template
     → inputs/confluence-pulls/{page_id}.md

본 스킬:
  /extract-template <page_id 또는 URL_A>
     → templates/extracted/{page_id}.template.md
     → PM 확인 게이트

후속 (택1):
  /from-url <URL_B> --target D2 --template-from pages/{page_id}
  /write   --template templates/extracted/{page_id}.template.md
  /render  --template templates/extracted/{page_id}.template.md [--push]
```

---

## 9. 사용 예시

### 9.1 표준 흐름 (URL_A → URL_B)

```bash
# 1. URL_A 양식 페이지 pull
/from-url https://wiki.example.com/pages/123456 --as-template

# 2. 양식 추출 (본 스킬)
/extract-template 123456
# → templates/extracted/123456.template.md 생성, PM 확인 게이트

# 3. PM 승인 후 URL_B 페이지 pull + 양식 적용
/from-url https://wiki.example.com/pages/789012 --target D2 \
         --template-from pages/123456

# 4. 최종 render + push
/render --push
```

### 9.2 PM 수정 시나리오

```bash
/extract-template 123456
# PM 확인 게이트에서:
#   "§3 의 panel style 을 tbd → warning 으로 바꾸고
#    §5 (운영 정책) 섹션을 추가해주세요"
# → template 수정 적용 후 다시 확인 게이트

# 승인 후 후속 작업 진행
```

### 9.3 비표준 페이지 (부분 추출)

```bash
/from-url https://wiki.example.com/pages/000111 --as-template
# 풀된 MD 가 panel fenced div 미사용 (구버전)
/extract-template 000111
# → "비표준 — heading + table 만 추출됨. panel 골격은 수동 보완 필요"
# → templates/extracted/000111.template.md (부분)
```

---

## 10. 제약 / 금지

- **COMMIT / PUSH 금지** — 본 스킬은 추출 결과를 로컬 파일로만 생성. 원격 작업 없음.
- 추출된 template 을 `templates/standard/` 에 덮어쓰지 말 것 — 내장 양식과 분리 보존.
- 추출 통계는 HTML 주석으로만 유지 — frontmatter 에 통계 필드 추가 금지 (publication 화이트리스트 위반).
- 색상 span (`{.color-green}` 등) 은 추출 단계에서 모두 제거 — Phase 3 cycling 은 발행 시점에 자동 재주입.
- PM 확인 게이트를 건너뛰는 자동 진행 금지.

---

## 11. 참조

- 사양 SSoT: `orange-pm-plugin/skills/render/publication-syntax.md`
- 양식 작성 가이드: `orange-pm-plugin/templates/standard/_macros.md`
- 선행 스킬: `orange-pm-plugin/skills/from-url/SKILL.md`
- 비교 대상 (내장 양식): `orange-pm-plugin/templates/standard/D*.md`
- 검증: `scripts/lint_publication_syntax.py` (추출 결과에도 동일 적용)
