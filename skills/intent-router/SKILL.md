---
name: intent-router
description: |
  자연어 의도 + URL 개수 + 컨텍스트로 Track A / B / C 를 결정하고 후속 스킬을
  라우팅한다. 사용자가 URL 1~2개 + 자유 발화로 작업을 요청할 때 진입점이 된다.

  Track 모델:
    Track A — Full Product (cluster fanout 전체)
              신제품 처음부터 + 모든 deliverable (D1~D5+α)
    Track B — Single Deliverable (cluster 우회)
              URL 1개 + "이 페이지에 D{N} 작성" → 단일 deliverable
    Track C — Template Copy (URL_A 양식으로 URL_B)
              URL 2개 + "양식 보고 작성" → 1~3 deliverable

  Track A 만 cluster fanout 사용. B/C 는 단일 deliverable 직선 경로.

triggers:
  - "이 URL 에"
  - "이 페이지에"
  - "양식 보고"
  - "처음부터 작성"
  - "신제품 정책"
  - "타사조사 후 작성"
  - "라우팅"
  - "어떻게 할까"

phase: any
effort: low
model: haiku
user-invocable: true
---

## 0. 역할

본 스킬은 **결정 라우터**다. 직접 작업을 수행하지 않고, 사용자 의도를 파싱한
뒤 적절한 후속 스킬에 위임한다. 모호하면 PM 에게 명확화 질문을 던진다.

후속 스킬 분류:
- `from-url` — URL pull 진입 (Track B/C 공통 선행)
- `extract-template` — URL_A 양식 추출 (Track C 전용)
- `research-auto` — 자동 타사조사 (Track A/B Phase -1)
- `draft-req` — requirements.md 생성 (Track A Phase -1)
- `graph-gen` + `fanout` — cluster 군집 (Track A 만)
- `render` — 발행 (모든 Track 종착)
- `write` / `flow` — cluster draft 본문 작성 (Track A)

## 1. Track 결정 매트릭스 (SSoT)

사용자 발화 + URL 개수 → Track 결정:

| 발화 의도 (키워드) | URL 개수 | 결정 Track | deliverable 범위 |
|---|---|---|---|
| "처음부터", "신제품", "전체 문서", "모든 deliverable" | 0~1 | **A — Full Product** | D1~D5 + α |
| "타사조사 후 + 요구사항", "이 URL 에 D1/D5", "이 페이지 작성" (단일 D 명시) | 1 | **B — Single Deliverable** | 명시된 D 1~2건 |
| "URL_A 양식으로 URL_B 작성", "이 형식으로", "동일 양식" | 2 | **C — Template Copy** | 명시된 D 1~3건 |
| URL 만 던지고 의도 불명 | 1+ | **모호 → 명확화 질문** | — |
| URL 없음 + "전체 작성" | 0 | A — Full Product | D1~D5 + α |
| URL 없음 + "타사조사만" | 0 | B — Single (D5) | D5 |

## 2. 명확화 질문 매트릭스

모호한 경우 PM 에게 결정 위임:

| 모호 상황 | 질문 |
|---|---|
| URL 1개 + 의도 불명 | "이 URL 에 무엇을 하실까요? (a) 새 deliverable 작성 (b) 기존 페이지 보강 (c) 양식 원본으로 참고만 (d) context 입력으로만" |
| URL 2개 + 어느 게 template / target 불명 | "URL_A({short_A}) 가 양식이고 URL_B({short_B}) 에 작성, 맞을까요? 또는 두 페이지 모두 작성 대상?" |
| 작성 대상 deliverable 불명 | "어느 deliverable 을 작성할까요? D1(요구사항)/D2(정책)/D3(화면)/D4(회의록)/D5(타사조사)/Dα(API/DB/마이그레이션)" |
| Track A 인데 제품명 없음 | "제품명을 알려주세요 (예: dbaas). PROJECTS/{제품명}/ 하위에 작업이 진행됩니다." |
| "타사조사 후 작성" — D1 만? D5 만? 둘 다? | "(a) D5 타사조사만 (b) D1 요구사항도 함께 (c) 전체 (Track A 로 전환)" |

질문은 한 번에 **최대 1개**만. 응답 후 다음 모호점 발견 시 추가 질문.

## 3. 결정 출력 (구조화)

라우팅 결정을 다음 구조로 출력 (모델 내부 사용 + PM 확인용):

```yaml
routing_decision:
  track: A | B | C
  product: dbaas | "..."
  urls:
    - role: target | template | context  # 역할
      page_id: "12345"                    # URL → 추출
      short_title: "..."
  deliverables:
    - D1 | D2 | D3 | D4 | D5 | Da_api | Da_db | Da_migration
  upstream_actions:                       # Phase -1 자동화
    - research-auto                       # 타사조사 자동
    - draft-req                           # requirements 합성
  next_skill: from-url | extract-template | research-auto | draft-req | render
  confirmation_required: true | false      # 비가역 동작이면 true
  notes: "(추가 사항)"
```

## 4. Track 별 후속 스킬 흐름

### Track A — Full Product (cluster fanout)
```
1. (필요 시) research-auto  → inputs/discovery/competitor/
2. draft-req               → requirements.md (D1) + research.md (D5)
3. graph-gen + fanout       → cluster WO 12~14개
4. write / flow             → cluster draft 본문
5. integrate                → 3 라운드 BLOCK 관리
6. render --push            → Phase 4 transpose → D2/D3 + α
```

### Track B — Single Deliverable
```
1. from-url URL --target D{N}  → 위키 페이지 pull + meta.json 생성
2. (D5 인 경우) research-auto  → 자동 타사조사
3. (D1 인 경우) draft-req      → 자동 요구사항 추출
4. write D{N}                  → 양식 채움
5. render D{N} --push          → 발행 (cluster 우회)
```

### Track C — Template Copy
```
1. from-url URL_A --as-template  → 양식 원본 pull
2. extract-template URL_A         → templates/extracted/{id}.template.md
3. from-url URL_B --target D{N} --template-from URL_A
4. write D{N} (추출 양식으로)     → 양식 채움
5. render D{N} --push             → 발행
```

## 5. 진입 시 처리 절차 (모델 행동 지침)

스킬 진입 시 다음을 **순서대로** 수행:

1. **메시지 파싱**:
   - URL 추출 (위키 페이지 URL 패턴 — 예: `pages/(\d+)` 포함 URL)
   - 명시적 deliverable 키워드 (D1/D2/D3/D4/D5/Dα) 추출
   - 의도 키워드 (위 §1 매트릭스 기반) 추출

2. **Track 결정**:
   - 매트릭스 적용 → A/B/C 선택
   - 모호 시 §2 질문 우선 1개 던지고 정지

3. **결정 출력**:
   - §3 구조로 `routing_decision` 생성
   - PM 에게 확인 (특히 `confirmation_required: true` 인 경우)

4. **후속 스킬 호출**:
   - §4 흐름표에 따라 next_skill 위임
   - 본 스킬은 결정만 — 실제 작업은 후속 스킬

5. **확인 게이트**:
   - 비가역 행동 (--push, --apply-inbox, 실제 위키 write) 직전엔 항상 한 줄 확인
   - 읽기 전용 (URL pull, lint, verify) 은 확인 없이 진행

## 6. 다른 스킬과의 결합

### 강한 결합 (반드시 본 스킬 결정 거침)
- `from-url`: URL 의 role (target/template/context) 결정 필요
- `extract-template`: Track C 외에는 발동 X
- `research-auto`: PM 의도가 "타사조사 자동" 일 때만

### 느슨한 결합 (PM 직접 호출 시 본 스킬 우회 가능)
- `render` — PM 이 `/render --push` 직접 호출 시 본 스킬 미경유
- `lint_publication_syntax` — 검증 도구, 본 스킬 무관
- `verify` — 검증 도구, 본 스킬 무관

### intent-router 가 명시적 라우팅하지 않는 경우
- 사용자가 명시 플래그 (`/render --push`, `/write WO-05`) 사용 시 → 그대로 통과
- 본 스킬은 **명시 플래그 없는 자유 발화** 진입에서만 활성

## 7. 사용 예시

### 예 1 — Track A 라우팅
```
PM: "DBaaS for Berkeley 정책 문서 처음부터 다 만들어줘"

intent-router:
  routing_decision:
    track: A
    product: dbaas-berkeley
    deliverables: [D1, D2, D3, D4, D5, Da_api, Da_db, Da_migration]
    upstream_actions: [research-auto, draft-req]
    next_skill: research-auto
    confirmation_required: true
    notes: "Full Product — Phase -1 부터 시작. 신규 제품 PROJECTS/dbaas-berkeley/ 생성 필요."

  → PM 확인: "신제품 dbaas-berkeley 로 전체 문서 작성 시작할까요?
            예상 산출: cluster 12~14개 + 위키 8 페이지."
```

### 예 2 — Track B 라우팅
```
PM: "https://wiki.example.com/pages/12345 에 DBaaS 타사조사 후 요구사항정의서 작성"

intent-router:
  routing_decision:
    track: B
    product: dbaas
    urls:
      - role: target
        page_id: "12345"
    deliverables: [D1, D5]
    upstream_actions: [research-auto]
    next_skill: from-url
    confirmation_required: false  # pull 은 읽기 전용
    notes: "D5 타사조사 → D1 요구사항정의서 순. cluster fanout 우회."

  → 후속: from-url 12345 --target D1 → research-auto dbaas → write D1
```

### 예 3 — Track C 라우팅
```
PM: "https://wiki.../pages/A 양식 보고 https://wiki.../pages/B 에
      정책정의서 동일 양식으로 작성"

intent-router:
  routing_decision:
    track: C
    urls:
      - role: template
        page_id: "A"
      - role: target
        page_id: "B"
    deliverables: [D2]
    upstream_actions: []
    next_skill: from-url
    confirmation_required: false
    notes: "URL_A 양식 추출 → URL_B 에 D2 작성."

  → 후속: from-url A --as-template → extract-template A → from-url B --target D2 --template-from A
```

### 예 4 — 명확화 필요
```
PM: "https://wiki.../pages/X"  (URL 만, 의도 없음)

intent-router:
  → 질문: "이 URL 에 무엇을 하실까요?
          (a) 새 deliverable 작성   (b) 기존 페이지 보강
          (c) 양식 원본으로 참고만  (d) context 입력으로만 사용"
```

## 8. 주의사항

- 본 스킬은 **결정만** — 실제 위키 호출 / repo 쓰기 / push 금지
- 모호 시 추측 금지 — PM 명확화 질문 1개씩
- Track 결정 후 후속 스킬에 **전체 컨텍스트** 위임 (URL/deliverable/upstream_actions 포함)
- 사용자 메시지에 Track 명시 (`Track A` / `Track B` 등) 가 있으면 매트릭스 무시하고 그대로 따름
- 위키 직접 편집 금지 정책 (project-rules.md) 위반 의도 감지 시 안내 후 본 스킬 결정 거부

## 9. 워크플로 연결

- 선행: 없음 (진입점)
- 후속: from-url / extract-template / research-auto / draft-req / render
- 우회 가능: 명시 플래그 사용 시 (`/render --push`, `/write WO-05`)

## 10. 변경 이력

| 버전 | 일자 | 변경 |
|---|---|---|
| 1.0 | 2026-05-30 | Phase 4 R1 — Track A/B/C 라우팅 매트릭스 + 명확화 질문 + 후속 스킬 흐름 |
