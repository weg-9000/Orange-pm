---
name: screen-detail
description: >-
  실제 위키 게시 수준의 화면 상세 설명 문서를 작성한다. 출력 포맷은 화면 유형에 따라 두 가지 중 하나를 사용한다: - user-console: 사용자 콘솔 화면 (화면 N. 섹션 구조) - backoffice:   백오피스 관리자 화면 (4컬럼 표 구조) 프로젝트 디자인 시스템(Hub `CONTEXT/design-system.md`에서 로드, 없으면 일반 웹 컴포넌트 관례)은 컴포넌트 선택·검증 규칙 결정에 내부적으로 참조하며 출력 컬럼으로 노출하지 않는다.
triggers:
  - "screen-detail"
  - "화면 상세"
  - "화면 설명"
  - "화면 설계"
  - "ui 명세"
phase: 2
effort: medium
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


## 공통 참조 가드 (C0·C-PIN·C3 — gates/master-derivation-gate.md SSoT)

화면 상세 작성 전 적용. 상세는 `CONTEXT/gates/master-derivation-gate.md`.

1. 공통 대조: G2-A/B 에 이미 있는 정책은 재작성 금지 — `[{doc_id} §X] 참조`
   링크로만(B-headings-index 후보 §만, 원문 전체 로드 금지 — 토큰 경계).
2. C-PIN: Section 7 추가 시 draft frontmatter `referenced_master` 핀 유지
   (master-id-map.yml 권위 ID). 비우면 opt-out → decisions.md 근거 필수.
3. 재기재 self-check (C3): 입력 유효성·산식·약정율·정책 규칙은 화면 상세
   본문 재기재 금지 → 정책 참조는 `[[POL §X-Y]]` **표준 마커만**, 입력은
   `[[spec-catalog 변수ID]]`. 재기재 탐지 시 self-check FAIL.
4. C-PIMPACT: draft frontmatter `referenced_policy: {POL doc_id}@{version}`
   핀 유지(WP8-1 표준). 정책 §변경 → policy_impact_scan 이 §단위 영향
   화면 식별(reviewer V-17·policy-impact-gate).
5. PM 확인은 단계 4(PM 제안·확인)에 통합(직렬 프롬프트 추가 금지).


## 출력 포맷 결정

### 포맷 선택 기준

| 포맷 | 대상 화면 | 플래그 |
|---|---|---|
| `user-console` | 사용자 포털·콘솔 화면 (버튼·레이어·입력 섹션 구조) | `--type user` (기본값) |
| `backoffice` | 백오피스·관리자 화면 (항목 목록 표 구조) | `--type backoffice` |

`--type` 미지정 시: screen-list.md의 화면명 또는 WO 제목에 "백오피스·관리·admin"이 포함되면 `backoffice`, 그 외는 `user-console`로 자동 판별한다.

---

## 전제조건 검사

1. `PROJECTS/{product}/drafts/` 에서 `{screen_id}`에 해당하는
   screen WO draft 파일을 확인한다.
   없으면 `/flow {product} {screen_id}` 먼저 실행을 안내한다.
   (단, `--pre-flow` 플래그 지정 시 draft 없이도 진행 가능)

2. `PROJECTS/{product}/graph/screen-list.md` 에서
   `{screen_id}` 항목이 존재하는지 확인한다.

3. Hub의 `CONTEXT/design-system.md` 를 로드해 프로젝트 디자인 시스템
   (이름·버전·컴포넌트 카탈로그 위치)을 확인한다.
   파일이 없으면 특정 디자인 시스템 없이 일반 웹 컴포넌트 관례로 진행한다.
   컴포넌트 카탈로그가 선언된 경우 `CONTEXT/design-system/stories.json` 을
   내부 참조용으로 로드하고, 없으면 `CONTEXT/design-system/tokens.md`
   컴포넌트 목록으로 대체한다.


---

## 실행 단계

### 단계 1 — 화면 컨텍스트 수집

다음 소스에서 이 화면에 필요한 정보를 수집한다.

**screen-list.md 항목:**
- Screen ID, 화면명, 목적, URL 경로, GNB 경로

**screen WO draft (drafts/{WO_ID}.draft.md):**
- idle: 초기 UI 구성, 활성 버튼 목록
- loading: 비활성화 대상, 스피너·스켈레톤 위치
- success: 결과 표시 방식, 다음 이동 화면
- error: 오류 유형별 메시지(quoted), 복구 방법
- 마이크로카피: 버튼 레이블, 입력 placeholder, 안내 문구

**내부적으로 추출하는 항목 (출력에 컬럼으로 노출하지 않는다):**
- 버튼별 디자인 시스템 Button variant 및 활성화 조건
  (디자인 시스템 미지정 시 기본 관례: Filled·Outlined·Ghost·Danger)
- 입력 필드별 validation 규칙 및 오류 메시지
- Select·Radio·Checkbox 옵션 목록 및 기본값
- 모달·레이어 표시 조건 및 닫기 트리거

이 정보는 출력 문서 내용(버튼 동작 설명, 안내 문구, 불가 케이스 등)을 채우는 데 사용한다.


### 단계 2 — 디자인 시스템 내부 참조

수집한 화면 요소에 대해 프로젝트 디자인 시스템(`CONTEXT/design-system.md` 기준,
미지정 시 일반 웹 컴포넌트 관례) 컴포넌트를 내부적으로 매핑한다.
이 단계의 결과는 **출력 컬럼이 아니라 출력 내용(문구·규칙·조건)을 결정하는 데만 사용한다**.

**매핑 소스 우선순위:**
1. `CONTEXT/design-system/stories/` 내 `.stories.tsx` → args·argTypes에서 실제 prop 값 추출
2. `CONTEXT/design-system/stories.json` → story 이름으로 variant 확인
3. `CONTEXT/design-system/tokens.md` → 섹션 8 컴포넌트 목록·섹션 9 추천 매핑

**참조 결과 활용 방식:**
- Button variant → 버튼 동작 설명의 "주요 CTA" / "보조" / "취소" / "위험" 구분
- Input 검증 규칙 → 오류 케이스 및 안내 문구 작성
- Select options → 선택 항목 목록 명시
- Modal trigger 조건 → 레이어 활성화 조건 작성


### 단계 3 — 화면 상세 초안 작성

선택된 포맷에 따라 초안을 작성한다.

---

#### [포맷 A] user-console — 사용자 콘솔 화면

화면 단위로 섹션을 구성한다. 각 섹션은 독립적으로 열릴 수 있다.

**출력 구조:**

```
화면 {N}. {화면명}

URL: {포털 URL 경로}
GNB 경로: {GNB 1depth} > {GNB 2depth} > {화면명}

{N}.1 {섹션명 — 예: 목록, 생성 폼, 상세 정보}

  [버튼 동작 표]
  | 버튼 | 활성화 조건 | 동작 |
  |---|---|---|
  | {버튼명} | {조건 — 예: 항상 / 1개 이상 선택 시} | {동작 설명} |

  [레이어·모달이 있는 경우]
  {레이어명} 레이어
  - 활성화 조건: {조건}
  - 안내 문구: "{안내 문구 원문}"
  - 불가 케이스: {불가 케이스 설명}
  - 버튼:
    | 버튼 | 동작 |
    |---|---|
    | {버튼명} | {동작} |

  [입력 필드가 있는 경우]
  - {필드명}: {입력 규칙}
    - 오류: "{오류 메시지 원문}"
  - {필드명}: {입력 규칙}

  [목록·테이블이 있는 경우]
  표시 컬럼: {컬럼1}, {컬럼2}, {컬럼3}
  빈 상태: "{빈 상태 안내 문구}"

{N}.2 {다음 섹션명}
  ...
```

**작성 규칙:**
- 화면 번호(N)는 screen-list.md의 순서를 따른다
- 섹션 번호(N.1, N.2)는 화면 내 논리적 구역 순서로 부여한다
- 버튼 동작 표는 해당 섹션에 버튼이 2개 이상일 때만 표로 작성한다 (1개면 설명문으로)
- 레이어 섹션은 trigger 버튼 바로 아래에 배치한다
- 오류 메시지·안내 문구는 반드시 큰따옴표로 인용 표기한다
- 비어있는 항목(빈 상태, 불가 케이스 없음 등)은 "해당 없음"으로 명시한다

---

#### [포맷 B] backoffice — 백오피스 관리자 화면

페이지 전체를 단일 4컬럼 표로 구성한다.
섹션 구분이 필요한 경우 표 내부에 병합 행(구분 헤더)을 사용한다.

**출력 구조:**

```
{화면명}

| 항목명 | UI 타입 | 상세 | 비고 |
|---|---|---|---|
| {항목} | {Input / Select / Button / Table / ...} | {동작·규칙·표시 내용} | {필수여부·조건·특이사항} |
```

**UI 타입 표기 목록** (디자인 시스템 미지정 시 기본 관례 — 프로젝트 디자인 시스템이 있으면 해당 컴포넌트명으로 대응):

| 표기 | 대응 컴포넌트 |
|---|---|
| Input | Input |
| Select | Select / Combobox |
| Multi Select | MultiSelect / GroupedMultiSelect |
| Radio | Radio / RadioGroup |
| Checkbox | Checkbox |
| Switch | Switch |
| DatePicker | DatePicker / Calendar |
| Table | Table / DataTable |
| Button | Button |
| Modal | Modal |
| Tab | Tabs |
| Pagination | Pagination |
| Toast | Toast |
| 텍스트 | Text / Title |

**작성 규칙:**
- 화면 순서(위→아래, 좌→우)로 항목을 나열한다
- 섹션 구분 헤더는 `| **{섹션명}** | — | — | — |` 형식으로 삽입한다
- 상세 컬럼에 오류 메시지가 포함될 경우 큰따옴표로 인용 표기한다
- 선택지(Select·Radio) 옵션은 상세 컬럼에 슬래시 구분으로 나열한다
- 필수 입력 항목은 비고에 `필수` 표기, 조건부 필수는 조건도 명시한다

---

### 단계 4 — PM 제안 및 확인

작성한 화면 상세 초안을 PM에게 보여주고 확인을 요청한다.

```
화면 상세 제안 — {screen_id} {화면명} [{포맷}]

(초안 전문)

검토 요청:
  1. 섹션 구성이 실제 화면과 맞는지 확인해 주세요
  2. 버튼 활성화 조건·동작에 수정이 필요한 항목이 있으면 알려주세요
  3. [TBD] 항목에 대한 방향을 결정해 주세요
```

PM 확인 없이 단계 5로 진행하지 않는다.
PM이 수정을 요청하면 해당 항목만 수정 후 재제안한다.


### 단계 5 — screen WO draft에 화면 상세 섹션 추가

PM 승인 후 `drafts/{WO_ID}.draft.md` 에 섹션을 추가한다.

```markdown
---
## Section 7. 화면 상세

**작성 기준**: {디자인 시스템명} v{버전} | 포맷: {user-console | backoffice} | 작성일: {날짜}

(단계 3에서 작성한 화면 상세 전문)

### 7-N. 미결 항목

| 항목 | 내용 | 우선순위 |
|---|---|---|
| [TBD] 항목들 | ... | P1/P2 |

### 자기 검증

- [ ] 모든 화면 섹션 작성 완료
- [ ] 버튼 동작 표 활성화 조건 명시 완료
- [ ] 오류 메시지·안내 문구 큰따옴표 인용 완료
- [ ] 레이어·모달 활성화 조건·불가 케이스 명시 완료
- [ ] [TBD] 항목 open-issues.md P1 등록 완료
```

TBD 항목은 open-issues.md에 P1으로 등록한다.


### 단계 6 — 완료 보고

```
/screen-detail 완료 — {screen_id} {화면명}

  포맷:          {user-console | backoffice}
  화면 섹션:     {N}개
  버튼 동작:     {N}개 정의
  레이어/모달:   {N}개 정의
  TBD 항목:      {N}건 (open-issues.md P1)
  추가된 파일:   drafts/{WO_ID}.draft.md Section 7

다음 단계: /review drafts/{WO_ID}.draft.md
```

session-log.md에 추가한다:
```markdown
- {날짜} /screen-detail {screen_id}: 화면 상세 작성 [{포맷}] / 섹션 {N}개 / TBD {N}건
```


## 플래그

| 플래그 | 동작 |
|---|---|
| `--type user` | user-console 포맷 강제 지정 |
| `--type backoffice` | backoffice 포맷 강제 지정 |
| `--pre-flow` | /flow draft 없이 screen-list.md만으로 빈 초안 작성 |
| `--no-draft` | draft에 추가하지 않고 화면에만 출력 (검토용) |
| `--update` | 기존 Section 7 존재 시 덮어쓰기 (기본: 중단 후 확인) |


## 결과 파일 목록

| 파일 | 변경 내용 |
|---|---|
| `drafts/{WO_ID}.draft.md` | Section 7. 화면 상세 섹션 추가 |
| `open-issues.md` | TBD 항목 P1 등록 |
| `session-log.md` | screen-detail 완료 기록 |


## Phase 2 워크플로우에서의 위치

```
/flow {product} {screen_id}
    → 4-state 인터랙션 + 마이크로카피 작성
        ↓
/screen-detail {product} {screen_id}
    → 화면 상세 설명 작성 (user-console | backoffice 포맷)
        ↓
/review drafts/{WO_ID}.draft.md
    → 전체 검증
```
