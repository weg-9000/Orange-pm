---
# Cluster Draft 표준 양식 — Track A (Full Product) 작업 단위
#
# 사용:
#   1. PM 또는 /fanout 가 graph-gen 결과를 바탕으로 cluster 단위로 복제
#   2. 한 cluster 당 1 파일: drafts/cluster_{capability}_{cluster_id}.draft.md
#   3. PM 작성 (또는 /write 스킬 호출) → /integrate R1~R3 → /render --push 시 transpose
#
# 사양 SSoT:
#   - publication-syntax.md §6 (색상 cycling)
#   - publication-map.md (cluster ↔ deliverable 매핑 규약)

# ───── Cluster 식별 메타 ─────
title: "Cluster {{CAPABILITY_NAME}} / {{CLUSTER_ID}} — {{CLUSTER_NAME}}"
wo_id: G2-K-{{CAP}}-{{CL}}        # 예: G2-K-PR-01 (Provisioning / Cluster 1)
type: cluster_draft
layer: C                           # B(공통)/C(제품)/DIRECT(Track B/C 단일)
version: 1.0
status: empty                      # 안 A 라이프사이클: empty→ai-draft(/write)→human-reviewed(/review)→frozen(/confirm)
last_updated: {{DATE}}

# ───── Cluster 분류 (graph-gen 산출) ─────
cluster:
  capability: "{{CAPABILITY_NAME}}"  # 예: "Provisioning" / "Pricing" / "Operations"
  cluster_id: "{{CLUSTER_ID}}"       # 예: "PR-01" (capability prefix + 순번)
  cluster_name: "{{CLUSTER_NAME}}"   # 예: "InstanceCatalog" / "ResourceLimit"

  # 4축 군집 점수 (graph-gen capability/cluster 식별 단계 산출)
  scores:
    decision_domain: 0.30    # 결정 도메인 공유 (정책 축 일치도)
    domain_object:   0.20    # 데이터 객체 공유 (Instance/Billing/Role 등)
    screen_surface:  0.20    # 화면 표면 공유 (같은 primary_screen)
    dependency_cone: 0.15    # 의존성 cone 50%+ 중복
    publication_fit: 0.15    # D2/D3 챕터 정합성 (한 챕터로 자연스러운가)
  score_total: 0.85  # >= 0.55 면 cluster 결합 (사양 §4축 가중)

# ───── FR / 의존성 / 참조 ─────
fr_refs:                # D1 요구사항정의서에서 인용 (작성 X, link only)
  - "FR-101"
  - "FR-103"
  - "FR-108"
domain_objects: ["Instance", "InstanceSpec"]
policy_axes:    ["가격 축", "자원 한도 축"]
primary_screen: "SCR-001"  # 주된 노출 화면 (D3 어셈블 시 사용)

inherits_from:           # 상위 의존 (Phase -1 산출 / 다른 cluster)
  - "{PREFIX}-B-001"     # 공통 정책
  - "G2-K-PR-00"          # 같은 capability 의 상위 cluster

related_screens:         # 영향 화면 (D3 transpose 보조)
  - "SCR-001"
  - "SCR-002"

research_refs:           # D5 타사조사에서 인용 (작성 X, link only)
  - "research.md#aws-rds-instance-types"
  - "research.md#gcp-cloudsql-pricing"

# ───── Phase 4 transpose 출력 대상 ─────
deliverable_targets:
  - D2          # 정책정의서 (cluster §1 transpose)
  - D3          # 화면설계서 (cluster §2 transpose)
  # - Da_api      # §α-API panel 이 있을 때만 (render_transpose --deliverable Da_api)
  # - Da_db       # §α-DB panel 이 있을 때만
  # - Da_migration# §α-MIG panel 이 있을 때만

# 공통 셸 여부 (split-deliverable 발행 전용 — fix-plan-dossier-publish-split).
# true 면 D3 화면설계서의 일반 챕터에서 제외하고 §부록 A 공통 셸로 어셈블된다.
# /fanout cluster-mode 가 cluster_id(COMMON*) / capability(Common) 기준 자동 방출.
# dossier-page 발행 모드는 본 필드를 무시한다(기본 false, additive).
is_common_shell: false

# ───── Phase 3 색상 cycling 상태 ─────
# 자동 산출 — 수동 설정 금지. apply_color_cycling.py 가 publish 시 갱신.
color_state: null
---

::: {.panel section="§1 정책 결정 (D2 → 정책정의서로 transpose)"}
## §1 정책 결정

> 본 cluster 의 정책 결정. publish 시 D2 정책정의서의 cluster 챕터로 어셈블.

### §1-1 정책 범위 / 적용 조건

본 cluster 의 정책이 적용되는 조건·경계 설명.

| 항목 | 내용 |
|---|---|
| **적용 대상** | {{대상 — 예: 인스턴스 생성 시점부터 종료까지}} |
| **예외** | {{예외 사례}} |
| **우선순위** | {{상충 시 결정 원칙}} |

### §1-2 핵심 규칙

<!-- col-widths: 20%, 30%, 50% -->
| 규칙 ID | 조건 | 정책 |
|---|---|---|
| POL-{{N}} | {{조건}} | {{규칙 본문}} |
| POL-{{N+1}} | {{조건}} | {{규칙 본문}} |

### §1-3 상태 / 라이프사이클

본 cluster 가 다루는 상태 정의:

| 상태 | 정의 | 진입 조건 | 다음 상태 |
|---|---|---|---|
| {{상태명}} | {{정의}} | {{조건}} | {{전이}} |

### §1-4 오류 / 예외 처리

| 오류 코드 | 발생 조건 | 처리 |
|---|---|---|
| ERR-{{N}} | {{조건}} | {{처리 정책}} |

:::

::: {.panel section="§2 화면 설계 (D3 → 화면설계서로 transpose)"}
## §2 화면 설계

> 본 cluster 의 UI 표면. publish 시 D3 화면설계서의 cluster 챕터로 어셈블.
> 이전 별도 screen WO 트랙을 폐기하고 본 섹션이 화면설계서 산출을 책임진다.

### §2-1 주요 화면 / 화면 ID

| Screen ID | 화면명 | 진입 동선 | 비고 |
|---|---|---|---|
| SCR-{{NNN}} | {{화면명}} | {{어디서 진입}} | {{}} |

### §2-2 화면 구성 / 컴포넌트

각 화면의 핵심 컴포넌트·필드·동작:

```
SCR-{{NNN}}
├─ 헤더: {{타이틀 / 액션 버튼}}
├─ 본문: {{입력 폼 / 목록 / 상세}}
└─ 푸터: {{보조 액션}}
```

### §2-3 인터랙션 / 정책 연결

§1 정책 규칙이 화면에서 어떻게 노출되는가:

| 화면 영역 | 정책 참조 | 노출 방식 |
|---|---|---|
| {{영역}} | POL-{{N}} | {{메시지/필드 상태/버튼 enable}} |

### §2-4 빈 상태 / 오류 화면

| 상태 | 표시 | 액션 |
|---|---|---|
| 빈 목록 | {{문구}} | {{유도 액션}} |
| 권한 없음 | {{문구}} | {{대안}} |

### §2-5 디자인 토큰 (공통 셸 참조)

> 색상/타이포/간격은 공통 셸 cluster (G2-COMMON-NavShell) 의 토큰 참조.
> 본 cluster 에서는 토큰 재정의 금지 — SSoT 경계 보호.

:::

<!-- ═══ §α 기술 산출물 (선택 — 해당 cluster 에 기술 deliverable 이 있을 때만) ═══ -->
<!-- render_transpose 는 section 이 "§α" 로 시작하고 type 키워드(API/DB/마이그레이션)를 -->
<!-- 포함하는 panel 을 추출해 Dα 카테고리별 별도 페이지로 어셈블한다. 없으면 transpose -->
<!-- 시 exit 2(해당 cluster 0건) 로 안전 skip. frontmatter deliverable_targets 에 -->
<!-- 대응 Da_api / Da_db / Da_migration 를 함께 등재해야 발행 대상이 된다. -->
<!-- §3(데이터/의존성)은 내부 작업메타(publish 제외)이고, §α 는 발행 정본이다 — 중복 작성 금지. -->

::: {.panel section="§α-API API 스펙 (Dα → API 스펙으로 transpose · 선택)"}
## §α-API API 스펙

> 본 cluster 가 API 를 노출할 때만 작성. publish 시 Dα API 스펙(`Dα_api.md` 양식) 페이지로
> 어셈블된다. 미해당 cluster 는 본 panel 을 통째로 삭제한다(빈 placeholder 잔존 금지).

### §α-API-1 인증 / 공통 헤더
| 항목 | 값 |
|---|---|
| 인증 방식 | {{Bearer / API Key / OAuth}} |
| base URL | {{/api/v1/...}} |

### §α-API-2 엔드포인트
<!-- col-widths: 12%, 28%, 30%, 30% -->
| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| {{GET}} | {{/resources}} | {{쿼리/바디}} | {{200 스키마}} |

### §α-API-3 에러 코드
| 코드 | 조건 | 처리 |
|---|---|---|
| {{ERR-NN}} | {{조건}} | {{메시지/HTTP status}} |

:::

::: {.panel section="§α-DB DB 스키마 (Dα → DB 스키마로 transpose · 선택)"}
## §α-DB DB 스키마

> 본 cluster 가 신규 테이블·스키마를 정의할 때만 작성. publish 시 Dα DB 스키마
> (`Dα_db.md` 양식) 페이지로 어셈블. 스키마 정본은 본 panel 이며, §3 데이터 모델은
> 내부 의존성 스케치다(정본 중복 금지 — §3 에서는 본 panel 참조).

### §α-DB-1 테이블 — {{TABLE}}
<!-- col-widths: 22%, 18%, 12%, 48% -->
| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| {{id}} | {{bigint}} | {{PK}} | {{}} |

### §α-DB-2 인덱스 / FK
| 종류 | 대상 | 비고 |
|---|---|---|
| {{INDEX / FK}} | {{컬럼·참조}} | {{}} |

:::

::: {.panel section="§α-MIG 마이그레이션 (Dα → 마이그레이션 플랜으로 transpose · 선택)" style="warning"}
## §α-MIG 마이그레이션

> 데이터 이행·스키마 변경이 필요할 때만 작성. publish 시 Dα 마이그레이션 플랜
> (`Dα_migration.md` 양식) 페이지로 어셈블. 롤백 절차 필수.

### §α-MIG-1 단계 (Step-by-step)
| 단계 | 작업 | 검증 | 롤백 |
|---|---|---|---|
| {{S-01}} | {{}} | {{}} | {{R-01}} |

### §α-MIG-2 사전 조건 / 영향
- {{대상 테이블·다운타임·영향 범위}}

:::

::: {.panel section="§3 데이터 / 의존성 (내부용, publish 제외)"}
## §3 데이터 / 의존성

> 본 섹션은 cluster 작성 메타. publication_prefilter 가 제거하므로 D2/D3 에 포함되지 않는다.

### §3-1 데이터 모델

```mermaid
classDiagram
  class {{DomainObject1}} {
    +field1: type
    +field2: type
  }
  class {{DomainObject2}} {
    +field1: type
  }
  {{DomainObject1}} --> {{DomainObject2}}
```

### §3-2 외부 의존성

- 다른 cluster: {{cluster_id}} (§정책 / §화면 의존)
- 외부 API: {{api_endpoint}}
- 인프라: {{DB / cache / queue}}

### §3-3 성능 / 부하 고려사항

본 cluster 가 시스템 부하에 미치는 영향:

| 항목 | 예상 | 임계 | 비고 |
|---|---|---|---|
| QPS | {{}} | {{}} | {{}} |
| 응답 시간 | {{ms}} | {{ms}} | {{}} |

:::

::: {.panel section="§4 Open Questions / Upstream Feedback (내부용, publish 제외)" style="tbd"}
## §4 Open Questions / Upstream Feedback

> 본 섹션은 cluster 작성 중 발견한 의문 / 상위 산출물(D1/D5) 에 대한 환류 요청.
> publication_prefilter 가 제거하므로 D2/D3 에 포함되지 않는다.
>
> 환류 흐름: /integrate 가 UPSTREAM_GAP BLOCK 으로 분류 → /draft-req --upstream-feedback
>            으로 D1/D5 v++ 리비전.

### §4-1 Open Questions (자체 해결 가능)

| OQ ID | 질문 | 담당 | 목표일 | 비고 |
|---|---|---|---|---|
| OQ-{{N}} | {{질문 한 줄}} | {{담당}} | {{날짜}} | {{}} |

### §4-2 Upstream Feedback (D1/D5 리비전 후보)

다음 BLOCK 카테고리로 분류 — `/integrate` 가 자동 인식:

#### REQ_MISSING — 누락 FR (D1 추가 후보)
- [ ] {{cluster 작성 중 발견한 누락 요구사항}}

#### POLICY_CONFLICT — 정책 충돌 (decisions.md DEC 신규 후보)
- [ ] {{다른 cluster 또는 공통 정책과의 상충}}

#### RESEARCH_GAP — 타사조사 부족 (D5 보강 후보)
- [ ] {{타사 비교 데이터 부족 — research-auto 재실행 고려}}

#### TERM_AMBIGUOUS — 용어 모호 (spec-catalog / terms 후보)
- [ ] {{용어 정의 충돌 또는 누락}}

### §4-3 결정 trail (DEC 등재 대상)

본 cluster 작성 중 PM 결정 사항:

| 결정 | 결정자 | 일자 | 영향 cluster | DEC ID (등재 후) |
|---|---|---|---|---|
| {{결정 한 줄}} | {{PM}} | {{날짜}} | {{}} | DEC-{{}} |

:::

<!-- ────────────────────────────────────────────────────── -->
<!-- 이 아래는 cluster 작성 가이드 (publication_prefilter 가 제거) -->
<!-- ────────────────────────────────────────────────────── -->

<!--
## 작성 가이드 (publication_prefilter 가 본문에서 제거)

### 채우기 순서
1. **frontmatter cluster 메타** — graph-gen 산출 그대로 (수동 수정 금지)
2. **§1 정책 결정** — 핵심 작업, 가장 시간 들여 작성
3. **§2 화면 설계** — §1 정책이 어떻게 노출되는지 (정책 ↔ UI 결합 PM 사고)
4. **§α 기술 산출물** — API/DB/마이그레이션이 있는 cluster 만 (없으면 panel 삭제)
5. **§3 데이터/의존성** — 다른 cluster 와의 경계 확인 (내부 메타)
6. **§4 Open Questions** — 작성 중 끊임없이 추가 (자체 해결 못 하면 UPSTREAM_GAP)

### 검증 (필수)
- `python scripts/lint_publication_syntax.py --input drafts/cluster_*.draft.md`
- `python scripts/md_to_storage.py --input drafts/cluster_*.draft.md --output /tmp/x.xml --validate`
- `python scripts/round_trip_test.py`

### /integrate R1~R3 사이클
- R1: 본 draft 1차 작성 → /integrate 가 HARD/SOFT BLOCK 감지
- R2: BLOCK 해소 + UPSTREAM_GAP 분류 → /draft-req --upstream-feedback (필요 시)
- R3: 잔여 점검 → /confirm 동결

### section 의 transpose 대상
- §1 → D2 정책정의서 (cluster 챕터)
- §2 → D3 화면설계서 (cluster 챕터)
- §α-API / §α-DB / §α-MIG → Dα 카테고리별 별도 페이지 (있을 때만, type 키워드 분기)
- §3 → 비공개 (작성 메타)
- §4 → 비공개 (개발자 노트 / integrate 입력)

### 색상 cycling
publish 시 apply_color_cycling.py 가 frontmatter color_state 를 참조해 자동 산출.
PM 이 수동으로 색상 span (`[..]{.color-green}` 등) 작성 금지 — 자동 산출만.

### lazy-split 트리거
cluster draft 가 다음 임계 초과 시 child cluster 로 분할 권고 (사양 5D):
- 본문 > 1500 lines
- §1+§2 의 정책/화면 항목 수 > 8개
- R2 BLOCK 누적 (HARD+SOFT) > 5건
- PM 명시 `--split` 플래그

split 시 자식 cluster ID: 부모 + suffix (예: G2-K-PR-01-a, G2-K-PR-01-b).

### 작성 금지
- 다른 cluster 의 정책 본문 인용 X (link 만 — `[[POL §X-Y]]`)
- 공통 ({PREFIX}-B) 본문 재출력 X (render_assemble 이 인라인 전개)
- 화면 디자인 토큰 재정의 X (공통 셸 cluster 참조)
- 자체 검증 / 작성 메타를 §1/§2 안에 X (§3/§4 에 배치)
-->
