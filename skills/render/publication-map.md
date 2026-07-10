# Publication Map — Dossier ↔ Page 매핑 규약 (v2.1)

> ## ⚠️ v2.1 — 발행 모드 2종 (fix-plan-dossier-publish-split)
>
> 발행 단위는 `graph/project-mode.json` 의 **`publication_mode`** 로 결정된다
> (파일/키 없으면 `dossier-page`):
>
> | publication_mode | 발행 단위 | transpose | 적용 § |
> |---|---|---|---|
> | **`dossier-page`** (기본) | 기능정의서 1개 = 페이지 1개 | 미호출 | §0 |
> | **`split-deliverable`** | D2 정책정의서 / D3 화면설계서 2개 | **재활성** | §0-bis, §1~§9 |
>
> - `dossier-page` 는 v2.0 정본(§0). DEC-BDB-008(작성 정본=Capability Dossier).
> - `split-deliverable` 는 dossier §1→D2 / §2→D3 transpose 를 **재활성**한다.
>   따라서 아래 §1~§9 transpose 매트릭스는 **`split-deliverable` 모드에서 유효**하고,
>   `dossier-page` 모드에서는 DEPRECATED(미호출)다 — *조건부 활성*.
> - §3-A 파생 뷰(D1 capability 인덱스·횡단 매트릭스)는 **두 모드 모두** 유효
>   (링크 대상만 모드별로 dossier 페이지 / D2·D3 페이지).
> - 입력형(D1 요구사항·D5 타사조사)·누적형(D4 회의록)은 모드 무관 변동 없음.
>
> **`graph/project-mode.json` 작성 규약** (감사 2026-06-11 갭5 — 미문서화 해소):
> ```jsonc
> {
>   "track": "A",                              // A(cluster fanout) | legacy
>   "publication_mode": "split-deliverable"    // "dossier-page"(기본) | "split-deliverable"
> }
> ```
> - 작성 주체: `/fanout --cluster-mode` 또는 PM 수동. 변경은 발행 전이어야 한다
>   (모드 전환 시 기존 페이지 계층은 `/cr` 로 재구성).
> - 소비 주체(단일 소스 `_emit_common.read_publication_mode`): render SKILL ·
>   `render_sync_check.py` · `sync_emit.py`. 파일/키 부재 시 모두 `dossier-page` 가정.
> - 동기화 최신성: split 모드의 D2/D3 는 assembled.md frontmatter `source_clusters`
>   (render_transpose 기록)의 기여 cluster 만으로 OUTDATED 를 판별한다.

## §0. 정본 매핑 (v2.0 — dossier = page)

| Work 산출물 | → Publication | 방식 | 페이지 |
|---|---|---|---|
| 각 dossier `cluster_{cluster_id}.draft.md` (`type: cluster_draft`, `wo_id: {PREFIX}-K-{cluster_id}`) | **기능정의서 페이지** | render_assemble→prefilter→md_to_storage (transpose 없음) | dossier 1개 = 페이지 1개 |
| `inputs/requirements.md` | D1 요구사항정의서 | 직접 변환 | 1 |
| `inputs/research.md` | D5 타사조사 | 직접 변환 | 1 |
| `meetings/*.md` | D4 회의록 | 시간순 누적 | 1 |

- 페이지 계층: `{product} 기획 / 기능정의서/ {dossier ...} + D1 + D4 + D5` (/cr 구성).
- 챕터 명명·정렬: capability 알파벳 → cluster_id 자연 순 (cluster_index.json 순서).
- 색상 cycling: dossier **페이지** 단위(안정 WO_ID 기반 — 챕터 재정렬 위험 해소).
- 선택 발행: `/render --push {product} --only {WO_ID[,WO_ID]}` (viz 체크박스 백엔드).

---

## §0-bis. split-deliverable 매핑 (publication_mode: split-deliverable)

| Work 산출물 | → Publication | 방식 | 페이지 |
|---|---|---|---|
| 모든 dossier 의 §1 (정책 결정) | **D2 정책정의서** | render_transpose --deliverable D2 → prefilter→md_to_storage | 1 |
| 모든 dossier 의 §2 (화면 설계) | **D3 화면설계서** | render_transpose --deliverable D3 (+`--common-shell`) | 1 |
| `inputs/requirements.md` / `inputs/research.md` / `meetings/*.md` | D1 / D5 / D4 | §0 과 동일 | 각 1 |

- 어셈블 산출물: `reports/render/02-policy.assembled.md` / `03-screen-design.assembled.md`.
- meta 명명: `confluence-source/02-policy-{product}.meta.json` /
  `03-screen-design-{product}.meta.json` (per-deliverable — /cr 1-D-split 생성).
- D3 는 dossier `related_screens` 합집합으로 **화면 단위 챕터**를 우선 시도하고,
  §2 화면 태깅(`### §2-1 {SCR-ID}`)이 없으면 cluster 단위로 fallback(WARN).
- `is_common_shell: true` dossier 는 D3 §부록 A(공통 셸)로 분리(§8).
- 선택 발행: `/render --push {product} --only D2|D3`.
- ⚠️ §0/§5/§6 은 D2/D3 미반영(정책 §1 self-contained 전제). dossier 가
  `deliverable_targets` 에서 D2/D3 를 빼면 해당 cluster 가 누락된다.

---

## (이하 §1~§9 — transpose 모델 · `split-deliverable` 에서 활성 / `dossier-page` 에서 DEPRECATED)

> **목적**: Track A 의 cluster work 산출물을 D2/D3 등으로 transpose 하는 규약.
> `publication_mode: split-deliverable` 에서 **활성**(render_transpose.py::transpose),
> `dossier-page` 에서는 미호출(§3-A 파생 뷰만 유효, 링크 대상=dossier 페이지).

---

## 1. 두 축 분리 (Work vs Publication)

```
                          Publication 축 (Confluence)
                                  ↓
                ┌──────────────────────────────────────┐
                │ D1 요구사항 │ D2 정책 │ D3 화면 │ D4 회의록 │ D5 타사조사 │ Dα etc │
                ├──────────────────────────────────────┤
   Work 축      │  (입력형)    │ (출력형) │(출력형)│ (누적형) │  (입력형)   │(출력형)│
   (Cluster)    ├──────────────────────────────────────┤
   ─ Cluster_1  │     ─        │   §1     │   §2   │   ─      │     ─       │  §α   │
   ─ Cluster_2  │     ─        │   §1     │   §2   │   ─      │     ─       │  §α   │
   ─ Cluster_N  │     ─        │   §1     │   §2   │   ─      │     ─       │  §α   │
                └──────────────────────────────────────┘
```

- **Cluster 4 sections** (`cluster-draft.md`):
  - §1 정책 결정 → **D2 정책정의서 transpose 대상**
  - §2 화면 설계 → **D3 화면설계서 transpose 대상**
  - §3 데이터/의존성 → **publish 제외** (publication_prefilter 가 제거)
  - §4 Open Questions / Upstream Feedback → **publish 제외** (`/integrate` 입력)
- **Deliverable 분류**:
  - **입력형** (D1, D5): Phase -1 산출물. transpose 없음. 그대로 publish.
  - **출력형** (D2, D3, Dα): Phase 4 transpose 대상. cluster 섹션들을 어셈블.
  - **누적형** (D4): 시간 축. `meetings/*.md` 시간순 어셈블 + cluster 태그 인덱스.

---

## 2. Transpose 매트릭스 (정본 매핑 표)

| Cluster Section | → Deliverable | 어셈블 방식 | 챕터 구조 |
|---|---|---|---|
| **§1 정책 결정** (각 cluster) | **D2 정책정의서** | cluster_id 순 어셈블 | "Capability {name} / Cluster {id} {cluster_name}" 챕터 |
| **§2 화면 설계** (각 cluster) | **D3 화면설계서** | cluster_id 순 어셈블 + 공통 셸 부록 | "Capability {name} / Cluster {id}" 챕터 + 부록 |
| **§α (있는 cluster 만)** | **Dα etc 카테고리** | type 별 별도 페이지 | 예: API 챕터, DB 챕터, 마이그레이션 챕터 |
| §3, §4 | **publish 제외** | — | — |

**어셈블 순서 (deterministic)**:
1. capability 알파벳 순 (Pricing < Provisioning < ...)
2. 같은 capability 내에서는 cluster_id 자연 순 (PR-01 < PR-02 < ...)
3. 공통 셸 (G2-COMMON-*) 은 D3 부록 섹션으로 별도

---

## 3. 입력형 / 누적형 처리

### D1 요구사항정의서 (입력형 — Phase -1)
- 원본: `inputs/requirements.md` (draft-req 산출)
- publish: `md_to_storage` 직접 변환, transpose 없음
- 업데이트 시점: Phase -1 또는 UPSTREAM_GAP 환류 (`/draft-req --upstream-feedback`)
- cluster 참조: D1 의 각 FR 에 `cluster_ref` 메타로 어느 cluster 가 다루는지 cross-link

### D5 타사조사 (입력형 — Phase -1)
- 원본: `inputs/research.md` (draft-req 산출, research-auto 가 자동 채움)
- publish: 그대로 변환
- cluster 참조: cluster §1·§2 에서 `research_refs:` frontmatter 로 인용

### D4 회의록 (누적형 — Phase 2~3 rolling)
- 원본: `meetings/*.md` + `mtg-ledger.md`
- publish: 시간 역순 어셈블 + cluster 태그 기반 인덱스 panel
- 회의록 frontmatter `cluster_refs: [...]` 가 인덱스 생성 키

---

## 3-A. P3 파생 뷰 — cluster_map.json 인덱스에서 자동 합성 (DEC-C / DEC-F)

아래 두 뷰는 **손으로 작성하지 않는다.** `graph/cluster_map.json` 의 `fr_index` /
`module_index` (SSoT — DEC-D) 에서 `render_transpose.py` 의 순수·결정적 함수로
자동 합성된다. 재군집(threshold 조절/`/fanout`)으로 인덱스가 바뀌면 뷰가 자동
추종(수기 0). 산문 고정 TOC 없음.

### (1) D1 capability group-by 뷰 (DEC-C)

`fr_index` ({`FR-id`: {`capability`, `cluster_id`}}) 를 capability 별로 묶어
각 FR → 해당 기능정의서(cluster_id) 앵커로 cross-link.

```python
render_fr_capability_view(fr_index: dict[str, dict]) -> str
```

정렬: capability 알파벳 순 → FR 자연 순. 샘플:

```
::: {.panel section="§D1 capability별 FR 묶음 (cluster_map.fr_index 파생)"}
## §D1 capability별 FR 묶음 (cluster_map.fr_index 파생)

### Pricing

- **FR-101** → [기능정의서 PR-01](#PR-01)
- **FR-103** → [기능정의서 PR-01](#PR-01)
:::
```

### (2) 횡단 관심사 매트릭스 뷰 (DEC-F)

`module_index` ({`모듈DocId`: [{`cluster_id`, `capability`, `source`, `via`,
`section`}, …]}) 에서 **공유 모듈마다** "어느 기능(cluster)이 이 모듈을 참조하나"를
매트릭스 테이블로 합성. **어떤 모듈에도 일반적으로 동작**(이메일·로깅·인증 등 —
특정 모듈 하드코딩 없음). 규칙(포맷·재시도·옵트아웃)은 모듈/알림 dossier 1곳,
매트릭스는 트리거 역인덱스 파생 뷰.

```python
render_cross_cutting_matrix(
    module_index: dict[str, list[dict]],
    node_titles: dict[str, str] | None = None,
) -> str
```

정렬: 모듈 docId 알파벳 순 → 행은 capability → cluster_id 자연 순 → source → via.
샘플:

```
::: {.panel section="§횡단 관심사 매트릭스 (cluster_map.module_index 파생)"}
## §횡단 관심사 매트릭스 (cluster_map.module_index 파생)

### 이메일·SMS 발송 모듈 (DOC-EMAIL)

| capability | cluster_id | source | via | section |
|---|---|---|---|---|
| Account | PR-01 | NODE-A | references | §1 |
| Backup | PR-02 | NODE-B | references | §2 |
:::
```

테스트: `render_transpose_test.py` `TP3FrCapabilityView` / `TP3CrossCuttingMatrix`
(그룹핑·결정적 정렬·빈 입력·다중 모듈).

---

## 4. transpose() 함수 인터페이스 (구현 완료 — render_transpose.py)

`scripts/render_transpose.py` (실제 시그니처 — 아래 의사코드는 사양 요약):

```python
def transpose(
    cluster_drafts: list[Path],     # drafts/cluster_*.draft.md 목록
    deliverable_type: str,           # "D2" | "D3" | "Dα_{type}"
    *,
    common_shell_clusters: list[Path] = None,  # G2-COMMON-* (D3 어셈블 시)
) -> str:
    """
    cluster draft 들에서 해당 deliverable 섹션을 추출 → 단일 MD deliverable 생성.

    동작:
      1. 각 cluster_draft 의 frontmatter 검사 → deliverable_targets 에 포함되는지
      2. 해당 cluster 의 매핑 섹션 추출:
         - D2 → §1
         - D3 → §2 + (D3 인 경우 공통 셸 부록)
         - Dα → §α
      3. capability + cluster_id 순 정렬
      4. D{N} 양식 (templates/standard/D2_policy.md 등) 의 골격에 챕터로 끼워 넣기
      5. frontmatter 갱신 (title, version, last_updated)
      6. 결과 MD 반환 (md_to_storage 가 XML 로 변환할 입력)

    Returns:
      str — 어셈블된 MD source
    """
```

---

## 5. cluster_draft frontmatter 의 transpose 메타

`cluster-draft.md` frontmatter 의 다음 필드가 transpose 의 결정 입력:

```yaml
cluster:
  capability: "Pricing"       # transpose 시 챕터 그룹화 키
  cluster_id: "PR-01"         # 챕터 순서 키
  cluster_name: "PlanMatrix"  # 챕터 제목 일부

deliverable_targets:
  - D2     # §1 → D2 어셈블
  - D3     # §2 → D3 어셈블
  - Da_api # §α → Dα_api 어셈블

related_screens:
  - "SCR-001"  # D3 어셈블 시 부록 인덱스
  - "SCR-002"

fr_refs:
  - "FR-101"   # D1 의 어느 FR 을 다루는지 (D1 → cluster 역참조에 사용)
  - "FR-103"
```

---

## 6. Track 분기 시 publication-map 적용

Track A 만 publication-map 적용. Track B/C 는 단일 deliverable 직선 경로.

| Track | publication-map 적용 | 비고 |
|---|---|---|
| A — Full Product | ✓ 전체 적용 | cluster_drafts/ → D1~D5+α transpose |
| B — Single Deliverable | ✗ 우회 | 단일 draft → 단일 deliverable 직접 publish |
| C — Template Copy | ✗ 우회 | 양식 추출 + 직접 publish |

→ render SKILL.md 의 Track 자동 감지 (Phase 4 R6) 가 publication-map 발동 여부 결정.

---

## 7. 챕터 명명 컨벤션 (D2/D3 어셈블 시)

각 cluster 챕터는 다음 형식으로 명명 — TOC 생성·검색 일관성:

```
§{N} {Capability} / {ClusterName} ({cluster_id})

예:
§1 Pricing / PlanMatrix (G2-K-PR-01)
§2 Pricing / PriceCalculator (G2-K-PR-02)
§3 Provisioning / InstanceCatalog (G2-K-PV-01)
...
```

§N 은 transpose 시 deliverable 내부 자연 순서 (위 §2 정렬 규칙). cluster_id 가
변경되지 않는 한 챕터 번호 안정성 유지 (색상 cycling 의 path 안정성에도 영향).

---

## 8. 공통 셸 (G2-COMMON-*) 처리

D3 화면설계서에는 공통 셸 (NavShell / AuthFlow 등) 이 별도 부록으로 배치:

```
D3 화면설계서
├─ Capability 1 / Cluster 1.1
├─ Capability 1 / Cluster 1.2
├─ ...
├─ Capability N / Cluster N.M
└─ 부록 A — 공통 셸
   ├─ NavShell (G2-COMMON-01)
   ├─ AuthFlow (G2-COMMON-02)
   └─ ...
```

공통 셸은 `deliverable_targets: [D3]` + `is_common_shell: true` frontmatter 표시.

---

## 9. 챕터 순서 변경 시 색상 cycling 영향

⚠ **주의**: cluster 군집 알고리즘 v2 등으로 챕터 순서가 재정렬되면 색상 cycling 의 path 가 모두 바뀌어 "전체 이동" 으로 보일 위험 (사양 §3.3).

**완화 정책**:
- cluster_id 는 1회 부여 후 안정성 유지 (군집 결과가 달라져도 ID 재사용)
- 알고리즘 변경 시 PM 명시 `/render --color-reset` 권고 — 신규 baseline 으로 시작
- 챕터 순서 정렬 키는 `capability + cluster_id` 로 고정 (사람 정렬 의도 아닌 자동 안정)

---

## 10. 구현 현황 / 남은 갭

Phase 5F (`transpose()` — `render_transpose.py`) + Phase 5C (`fanout_dag.py
_iter_cluster_nodes`) 완성으로 본 매핑은 **실행 가능**하다.

완료:
- ✓ 매핑 규약 SSoT 확정 (§2 transpose 매트릭스)
- ✓ cluster_draft 4-section 양식 (5E) 와 정합
- ✓ Phase 4 R6 의 Track 자동 감지와 일관
- ✓ transpose() 코드 구현 (`render_transpose.py`, 테스트 `render_transpose_test.py`)
- ✓ /render 단계 3-A 배선 (D2/D3 실행 + md_to_storage)

- ✓ **§α → Dα 어셈블 활성화**: `cluster-draft.md` 에 §α-API / §α-DB / §α-MIG
  **선택 패널** 추가 → 기술 deliverable 이 있는 cluster 가 §α 를 작성하고
  `deliverable_targets` 에 `Da_api|Da_db|Da_migration` 등재하면 type 별 별도
  페이지로 어셈블된다(render_transpose_test 가드). §α 없는 cluster 는 exit 2
  안전 skip — D2/D3 와 독립.

---

## 11. 변경 이력

| 버전 | 일자 | 변경 |
|---|---|---|
| 1.0 | 2026-05-30 | Phase 5G — cluster ↔ deliverable 매핑 SSoT 수립 |
