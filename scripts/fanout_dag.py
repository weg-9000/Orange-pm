#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graph.json을 위상정렬해 Work Order 파일을 생성한다.

변경 이력:
    v1.0: 최초 구현 (policy 노드 전용)
    v2.0: policy + screen dual-track 지원 / {PREFIX}-A 체계 반영 /
          엣지 ID 채번 / index.md 트랙 분리 / WO type 필드 추가
    v2.1: index.json 동시 출력 (개선안 G — render/integrate 가
          마크다운 표 파싱 없이 WO 메타를 즉시 사용)

동작:
    1. graph.json 로드 + 엣지 ID 채번
    2. policy 섹션 노드 + screen 노드 분리 수집
    3. 전체 노드 통합 Kahn 위상정렬로 level(병렬 가능 그룹) 계산
    4. WO ID 사전 채번 (policy 우선, screen 후순)
    5. policy WO 파일 생성 (DEFAULT_POLICY_TEMPLATE)
    6. screen WO 파일 생성 (SCREEN_TEMPLATE)
    7. work-orders/index.md 생성 (트랙 분리)
    8. work-orders/index.json 생성 (기계 판독용)

exit code:
    0 = 성공
    1 = graph.json 로드·검증 실패
    2 = 사용법 오류
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


# ── 템플릿 ────────────────────────────────────────────────────────────────────

DEFAULT_POLICY_TEMPLATE = """\
# Work Order: {WO_ID} — {SECTION_TITLE}

**프로젝트**: `{PRODUCT_NAME}`
**type**: `policy`
**생성 시각**: `{GENERATED_AT}`
**graph.json 해시**: `{GRAPH_HASH}`
**level**: {LEVEL} (위상정렬 병렬 가능 그룹)

---

## 1. 할당 범위

- **문서명**: `{NODE_NAME}` (role: `{NODE_ROLE}`)
- **섹션 번호**: `{SECTION_ID}`
- **섹션 제목**: `{SECTION_TITLE}`
- **작성 모드**: `NEW`
- **출력 파일**: `drafts/{WO_ID}.draft.md`

---

## 2. 불변 입력

- **decisions.md 스냅샷 해시**: `{DECISIONS_HASH}`
- **graph.json 해시**: `{GRAPH_HASH}`

---

## 3. 참조 계약

### 3.1 이 섹션이 **참조하는** 엣지 (precondition, frozen)

{OUTGOING_EDGES}

### 3.2 이 섹션이 **참조 받는** 엣지

{INCOMING_EDGES}

### 3.3 연관 screen WO 목록

{RELATED_SCREEN_WOS}

---

## 4. 작업 지시

### 4.1 섹션 요약

{SECTION_SUMMARY}

### 4.2 전제 완료 조건

{LEVEL_DEPS}

---

## 5. 자기 검증 체크리스트

- [ ] `decisions.md` DEC 표 정본(`승인=✅`) 위반 없음 (미승인 `⬜` 충돌은 WARN — CONTEXT/dec-schema 참조)
- [ ] 참조 계약의 frozen 값을 그대로 반영
- [ ] 용어가 `{PREFIX_VAL}-A` 어휘 기준서와 일치
- [ ] TBD 항목은 `open-issues.md`에 등록
- [ ] 자기완결성 (이 섹션만 읽어도 의미 통함)
- [ ] 계층 경계 미침범
- [ ] 연관 screen WO와의 용어·규칙 일관성 확인

---

## 6. 금지 사항

- 참조 계약에 없는 새 의존 추가 금지
- 계층 경계 침범 금지
- 타 WO draft 편집 금지
- `decisions.md` DEC 표 직접 수정 금지 (DEC 등재는 /write·/su·/sc 등 등재 스킬, 승인은 /dec-approve 전용 — CONTEXT/dec-schema §5)

---

## 7. 완료 후 절차

1. `drafts/{WO_ID}.draft.md` 저장
2. `/review drafts/{WO_ID}.draft.md`
3. `/lc {PRODUCT_NAME}` → `/sc {PRODUCT_NAME}`

---

## Workflow Connections

<!-- wikilinks:start -->
[WIKILINKS_PLACEHOLDER]
<!-- wikilinks:end -->
"""

SCREEN_TEMPLATE = """\
# Work Order: {WO_ID} — {SCREEN_NAME}

**프로젝트**: `{PRODUCT_NAME}`
**type**: `screen`
**생성 시각**: `{GENERATED_AT}`
**graph.json 해시**: `{GRAPH_HASH}`
**level**: {LEVEL} (위상정렬 병렬 가능 그룹)

---

## 1. 할당 범위

- **Screen ID**: `{SCREEN_ID}`
- **화면명**: `{SCREEN_NAME}`
- **목적**: {PURPOSE}
- **연결 요구사항 ID**: `{REQ_ID}`
- **연관 policy WO ID**: {POLICY_WO_ID}
- **출력 파일**: `drafts/{WO_ID}.draft.md`

---

## 2. 불변 입력

- **decisions.md 스냅샷 해시**: `{DECISIONS_HASH}`
- **graph.json 해시**: `{GRAPH_HASH}`

---

## 3. 참조 계약

### 3.1 연관 policy WO implements 엣지

{IMPLEMENTS_EDGES}

### 3.2 인접 screen 의존 엣지

{SCREEN_EDGES}

---

## 4. 작업 지시

### 4.1 인터랙션 시퀀스 작성 요구사항

다음 4개 상태를 모두 정의한다:
- **idle**: 초기 진입 상태 (UI 구성 + 진입 조건)
- **loading**: 비동기 처리 중 상태 (스피너·스켈레톤 등 UI 변화)
- **success**: 정상 완료 상태 (결과 표시 + 다음 액션)
- **error**: 오류 발생 상태 (오류 메시지 + 오류코드)

이탈·취소·뒤로가기 처리를 별도 항목으로 정의한다.

### 4.2 마이크로카피 작성 요구사항

- 버튼 레이블 (동일 화면 내 중복 금지)
- 입력 필드 플레이스홀더 + 안내 문구
- 성공·오류·경고 메시지 (`{PREFIX_VAL}-A` 오류코드 포함)
- 툴팁 및 빈 상태(empty state) 문구

### 4.3 전제 완료 조건

{LEVEL_DEPS}

---

## 5. 자기 검증 체크리스트

- [ ] `screen-list.md`의 `{SCREEN_ID}` 항목과 화면명·목적 일치
- [ ] idle·loading·success·error 4개 상태 정의 완료
- [ ] 이탈·취소·뒤로가기 처리 정의
- [ ] 연관 policy WO 핵심 규칙 반영 여부 확인
- [ ] `brand-voice.md` 기준 위반 없음
- [ ] `{PREFIX_VAL}-A` 등재 어휘 사용 (오류코드 포함)
- [ ] `decisions.md` DEC 표 정본(`승인=✅`) 위반 없음 (미승인 `⬜` 충돌은 WARN — CONTEXT/dec-schema 참조)
- [ ] TBD 항목은 `open-issues.md`에 등록

---

## 6. 금지 사항

- 연관 policy WO draft 직접 편집 금지
- `decisions.md` DEC 표 직접 수정 금지 (DEC 등재는 /write·/su·/sc 등 등재 스킬, 승인은 /dec-approve 전용 — CONTEXT/dec-schema §5)
- 타 WO draft 편집 금지

---

## 7. 완료 후 절차

1. `drafts/{WO_ID}.draft.md` 저장
2. `/review drafts/{WO_ID}.draft.md`
3. `/lc {PRODUCT_NAME}` → `/sc {PRODUCT_NAME}`

---

## Workflow Connections

<!-- wikilinks:start -->
[WIKILINKS_PLACEHOLDER]
<!-- wikilinks:end -->
"""

INDEX_TEMPLATE = """\
# Work Orders 인덱스

**프로젝트**: `{PRODUCT_NAME}`
**생성 시각**: `{GENERATED_AT}`
**graph.json 해시**: `{GRAPH_HASH}`
**총 Work Order 수**: {TOTAL_WO} (policy: {TOTAL_POLICY} / screen: {TOTAL_SCREEN})
**총 레벨 수**: {TOTAL_LEVELS}

---

## 실행 순서 주의사항

다음 Work Order는 전제조건 엣지가 있으므로 선행 WO의 draft가 완성된 이후에 시작해야 합니다.

{PRECONDITION_NOTES}

---

## 정책서 Work Order (type: policy)

각 레벨 내 Work Order는 병렬로 실행 가능합니다. 레벨 N+1은 레벨 N이 완료된 후 시작합니다.

{POLICY_LEVEL_GROUPS}

---

## 화면설계 Work Order (type: screen)

각 레벨 내 Work Order는 병렬로 실행 가능합니다. 레벨 N+1은 레벨 N이 완료된 후 시작합니다.

{SCREEN_LEVEL_GROUPS}

---

## 요약 카드

{SUMMARY_CARDS}
"""


# ── 마커 ─────────────────────────────────────────────────────────────────────

WIKILINKS_START = "<!-- wikilinks:start -->"
WIKILINKS_END = "<!-- wikilinks:end -->"
WO_MAP_FILENAME = ".fanout-wo-map.json"
WO_MAP_SCHEMA_VERSION = 1


# ── 예외 ──────────────────────────────────────────────────────────────────────

class FanoutError(Exception):
    pass


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def _load(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        raise FanoutError(f"graph.json 로드 실패: {exc}") from exc


def _hash_file(path: Path) -> str:
    if not path.exists():
        return "n/a"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:12]


def _assign_edge_ids(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """id 필드가 없는 엣지에 E-{NN} 형식으로 채번한다."""
    result = []
    for idx, edge in enumerate(edges, start=1):
        e = dict(edge)
        if not e.get("id"):
            e["id"] = f"E-{idx:02d}"
        result.append(e)
    return result


# ── 노드 이터레이터 ───────────────────────────────────────────────────────────

def _iter_section_nodes(
    graph: dict[str, Any],
) -> Iterator[tuple[str, dict[str, Any], str, dict[str, Any]]]:
    """sections 키를 가진 policy 노드를 순회한다."""
    nodes = graph["graph"]["nodes"]
    for node_name, node in nodes.items():
        if node.get("node_type") == "screen":
            continue
        sections = node.get("sections") or {}
        for section_id, section in sections.items():
            yield node_name, node, section_id, section


def _iter_screen_nodes(
    graph: dict[str, Any],
) -> Iterator[tuple[str, dict[str, Any]]]:
    """node_type이 screen인 노드를 순회한다."""
    nodes = graph["graph"]["nodes"]
    for node_name, node in nodes.items():
        if node.get("node_type") == "screen":
            yield node_name, node


# ── Phase 5C — Cluster 모드 노드 이터레이터 ──────────────────────────────
def _iter_cluster_nodes(
    graph: dict[str, Any],
) -> Iterator[tuple[str, str, str, list[tuple[str, dict[str, Any]]]]]:
    """policy 노드들을 (capability, cluster_id) 별로 묶어 순회.

    각 cluster 그룹은 cluster_identify.py 가 부여한 메타 (capability + cluster_id
    + cluster_name) 를 가지며, 같은 cluster 의 모든 policy 노드를 멤버로 수집.

    Yields:
        (capability, cluster_id, cluster_name, [(node_name, node), ...])

    cluster_id 가 없는 노드는 capability="Default" 의 단독 cluster 로 처리
    (cluster_identify.py 미실행 시 fallback).
    """
    nodes = graph["graph"]["nodes"]
    by_cluster: dict[tuple[str, str], dict] = {}

    for node_name, node in nodes.items():
        if node.get("node_type") == "screen":
            continue
        capability = node.get("capability") or "Default"
        cluster_id = node.get("cluster_id")
        cluster_name = node.get("cluster_name") or node_name

        # cluster_id 미부여 시: 각 노드가 독립 fallback cluster (DX-{node_name})
        if not cluster_id:
            cluster_id = f"DX-{node_name[:16]}"
            cluster_name = node_name

        key = (capability, cluster_id)
        if key not in by_cluster:
            by_cluster[key] = {
                "capability": capability,
                "cluster_id": cluster_id,
                "cluster_name": cluster_name,
                "members": [],
            }
        by_cluster[key]["members"].append((node_name, node))

    # 결정적 순서 — capability + cluster_id 정렬 (publication-map.md §2)
    for key in sorted(by_cluster.keys()):
        ci = by_cluster[key]
        yield ci["capability"], ci["cluster_id"], ci["cluster_name"], ci["members"]


def _generate_cluster_draft_content(
    capability: str,
    cluster_id: str,
    cluster_name: str,
    members: list[tuple[str, dict[str, Any]]],
    *,
    product_name: str,
    graph_hash: str,
    now_iso: str,
    prefix_val: str,
) -> str:
    """cluster 한 개에 대한 cluster-draft.md 양식 본문 생성.

    멤버 노드들의 sections / fr_refs / domain_object / policy_axis / primary_screen 을
    집계해 frontmatter 와 §1 정책 결정 / §2 화면 설계 본문에 반영.
    """
    # 메타 집계
    fr_refs: list[str] = []
    domain_objects: set[str] = set()
    policy_axes: set[str] = set()
    primary_screens: set[str] = set()
    inherits: set[str] = set()
    research_refs: set[str] = set()
    related_screens: set[str] = set()
    deliverable_targets: set[str] = set()
    section_summaries: list[tuple[str, str, str]] = []  # (node_name, section_id, title)

    for node_name, node in members:
        for fr_id in (node.get("fr_refs") or []):
            if fr_id not in fr_refs:
                fr_refs.append(fr_id)
        for d in (node.get("domain_object") or []):
            domain_objects.add(d)
        for p in (node.get("policy_axis") or []):
            policy_axes.add(p)
        if node.get("primary_screen"):
            primary_screens.add(node["primary_screen"])
        for t in (node.get("deliverable_targets") or ["D2", "D3"]):
            deliverable_targets.add(t)
        for ih in (node.get("inherits_from") or []):
            inherits.add(ih)
        for rr in (node.get("research_refs") or []):
            research_refs.add(rr)
        for rs in (node.get("related_screens") or []):
            related_screens.add(rs)
        # sections 요약 수집
        sections = node.get("sections") or {}
        for sid, sec in sections.items():
            section_summaries.append((node_name, sid, sec.get("title", sid)))

    # WO ID (cluster 단위, publication-map.md §7 명명)
    cap_prefix = "".join(
        c.upper() for c in capability if c.isalpha()
    )[:2] or "XX"
    wo_id = f"{prefix_val or 'PX'}-K-{cluster_id}"

    # 공통 셸 판정 (GAP1 — fix-plan-dossier-publish-split):
    # split-deliverable 발행 시 render_transpose 가 본 플래그로 일반 챕터 vs D3
    # 공통 셸 부록을 라우팅한다. cluster_id 가 COMMON 으로 시작하거나 capability 가
    # Common(횡단 셸) 이면 공통 셸로 본다. dossier-page 모드는 본 필드를 무시.
    is_common_shell = (
        cluster_id.upper().startswith("COMMON")
        or capability.strip().lower() == "common"
    )

    # frontmatter (cluster-draft.md 와 정합)
    yaml_block = (
        f"---\n"
        f"title: \"Cluster {capability} / {cluster_id} — {cluster_name}\"\n"
        f"wo_id: {wo_id}\n"
        f"type: cluster_draft\n"
        f"layer: C\n"
        f"version: 1.0\n"
        f"status: empty\n"          # 안 A 라이프사이클 진입점 (empty→ai-draft→human-reviewed→frozen)
        f"last_updated: {now_iso[:10]}\n"
        f"\n"
        f"cluster:\n"
        f"  capability: \"{capability}\"\n"
        f"  cluster_id: \"{cluster_id}\"\n"
        f"  cluster_name: \"{cluster_name}\"\n"
        f"\n"
        f"fr_refs: {json.dumps(sorted(fr_refs), ensure_ascii=False)}\n"
        f"domain_objects: {json.dumps(sorted(domain_objects), ensure_ascii=False)}\n"
        f"policy_axes: {json.dumps(sorted(policy_axes), ensure_ascii=False)}\n"
        f"primary_screen: "
        f"{json.dumps(sorted(primary_screens)[0] if primary_screens else None, ensure_ascii=False)}\n"
        f"\n"
        f"inherits_from: {json.dumps(sorted(inherits), ensure_ascii=False)}\n"
        f"related_screens: {json.dumps(sorted(related_screens), ensure_ascii=False)}\n"
        f"research_refs: {json.dumps(sorted(research_refs), ensure_ascii=False)}\n"
        f"\n"
        f"deliverable_targets: {json.dumps(sorted(deliverable_targets), ensure_ascii=False)}\n"
        f"is_common_shell: {str(is_common_shell).lower()}\n"
        f"\n"
        f"color_state: null\n"
        f"graph_hash: \"{graph_hash[:12]}\"\n"
        f"members: {json.dumps([m[0] for m in members], ensure_ascii=False)}\n"
        f"---\n"
    )

    # §1 정책 결정 — section_summaries 를 표로
    section_rows = "\n".join(
        f"| {sid} | {nname} | {title} |"
        for nname, sid, title in section_summaries
    ) or "| _(섹션 없음)_ | | |"

    body = f"""
::: {{.panel section="§1 정책 결정 (D2 → 정책정의서로 transpose)"}}
## §1 정책 결정

> 본 cluster 의 정책 결정. publish 시 D2 정책정의서의 cluster 챕터로 어셈블.

### §1-1 정책 범위 / 적용 조건

본 cluster ({cluster_id}) 의 정책이 적용되는 조건·경계.

| 항목 | 내용 |
|---|---|
| **적용 대상** | {{대상 — 예: {', '.join(sorted(domain_objects)) or '(미정)'}}} |
| **예외** | {{예외 사례}} |
| **우선순위** | {{상충 시 결정 원칙}} |

### §1-2 정책 섹션 목록 (graph.json 출처)

| Section ID | 출처 노드 | 제목 |
|---|---|---|
{section_rows}

### §1-3 핵심 규칙

<!-- col-widths: 20%, 30%, 50% -->
| 규칙 ID | 조건 | 정책 |
|---|---|---|
| POL-{{N}} | {{조건}} | {{규칙 본문 — graph 의 sections summary 참조}} |

### §1-4 상태 / 라이프사이클

| 상태 | 정의 | 진입 조건 | 다음 상태 |
|---|---|---|---|
| {{상태명}} | {{정의}} | {{조건}} | {{전이}} |

### §1-5 오류 / 예외 처리

| 오류 코드 | 발생 조건 | 처리 |
|---|---|---|
| ERR-{{N}} | {{조건}} | {{처리 정책}} |

:::

::: {{.panel section="§2 화면 설계 (D3 → 화면설계서로 transpose)"}}
## §2 화면 설계

> Phase 5I 이후 본 섹션이 D3 화면설계서 산출을 책임 (별도 screen WO 트랙 폐기).

### §2-1 주요 화면

| Screen ID | 화면명 | 진입 동선 | 비고 |
|---|---|---|---|
{chr(10).join(f"| {s} | {{화면명}} | {{진입}} | |" for s in sorted(related_screens)) or "| {{SCR-NNN}} | {{화면명}} | {{}} | |"}

### §2-2 화면 구성 / 컴포넌트

각 화면의 핵심 컴포넌트·필드·동작:

```
{sorted(related_screens)[0] if related_screens else '{{SCR-NNN}}'}
├─ 헤더: {{타이틀 / 액션 버튼}}
├─ 본문: {{입력 폼 / 목록 / 상세}}
└─ 푸터: {{보조 액션}}
```

### §2-3 정책 ↔ UI 연결

| 화면 영역 | 정책 참조 | 노출 방식 |
|---|---|---|
| {{영역}} | POL-{{N}} | {{메시지/필드 상태/버튼 enable}} |

:::

::: {{.panel section="§3 데이터 / 의존성 (내부용, publish 제외)"}}
## §3 데이터 / 의존성

> publication_prefilter 가 본 섹션을 제거 — D2/D3 에 포함되지 않음.

### §3-1 데이터 객체

{chr(10).join(f"- `{d}`" for d in sorted(domain_objects)) or "- _(graph 미지정)_"}

### §3-2 의존성 (graph.json 출처)

**inherits_from**:
{chr(10).join(f"- `{ih}`" for ih in sorted(inherits)) or "- _(없음)_"}

### §3-3 cluster 멤버 노드

{chr(10).join(f"- `{name}`" for name, _ in members)}

:::

::: {{.panel section="§4 Open Questions / Upstream Feedback (내부용, publish 제외)" style="tbd"}}
## §4 Open Questions / Upstream Feedback

> /integrate 가 UPSTREAM_GAP BLOCK 으로 분류 → /draft-req --upstream-feedback 으로
> D1/D5 v++ 리비전 트리거.

### §4-1 Open Questions

| OQ ID | 질문 | 담당 | 목표일 |
|---|---|---|---|
| OQ-{{N}} | {{질문}} | {{담당}} | {{날짜}} |

### §4-2 Upstream Feedback

#### REQ_MISSING — 누락 FR (D1 추가 후보)
- [ ] {{누락 요구사항}}

#### POLICY_CONFLICT — 정책 충돌
- [ ] {{상충 사항}}

#### RESEARCH_GAP — 타사조사 부족
- [ ] {{보강 필요 항목}}

#### TERM_AMBIGUOUS — 용어 모호
- [ ] {{용어}}

:::
"""
    return yaml_block + body




# ── 위상정렬 ──────────────────────────────────────────────────────────────────

def _topological_levels(
    all_keys: list[tuple[str, str]],
    edges: list[dict[str, Any]],
) -> dict[tuple[str, str], int]:
    """전제조건 엣지 기반으로 레벨을 계산한다. 순환이 있으면 예외를 발생시킨다."""
    in_deg: dict[tuple[str, str], int] = {key: 0 for key in all_keys}
    graph_out: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)

    for edge in edges:
        if edge.get("type") != "전제조건":
            continue
        src = (edge["source"], edge.get("source_section", ""))
        tgt = (edge["target"], edge.get("target_section", ""))
        if src not in in_deg or tgt not in in_deg:
            continue
        graph_out[src].append(tgt)
        in_deg[tgt] += 1

    queue: deque[tuple[str, str]] = deque(
        [k for k, d in in_deg.items() if d == 0]
    )
    level: dict[tuple[str, str], int] = {k: 0 for k in queue}
    visited = 0

    while queue:
        node = queue.popleft()
        visited += 1
        for nxt in graph_out[node]:
            in_deg[nxt] -= 1
            level[nxt] = max(level.get(nxt, 0), level[node] + 1)
            if in_deg[nxt] == 0:
                queue.append(nxt)

    if visited != len(all_keys):
        raise FanoutError("전제조건 엣지에 순환이 존재합니다.")
    return level


# ── 렌더링 헬퍼 ──────────────────────────────────────────────────────────────

def _render_edge_row(edge: dict[str, Any]) -> str:
    return (
        f"| `{edge['id']}` | {edge['type']} | "
        f"`{edge['source']}.§{edge.get('source_section', '')}` | "
        f"`{edge['target']}.§{edge.get('target_section', '')}` | "
        f"{edge.get('description', '')} |"
    )


def _edges_table(rows: list[str]) -> str:
    if not rows:
        return "_(없음)_"
    header = "| 엣지 ID | 타입 | source | target | 설명 |\n|---|---|---|---|---|"
    return header + "\n" + "\n".join(rows)


def _level_deps_text(level: int) -> str:
    if level == 0:
        return "_없음 (최상위 레벨, 즉시 시작 가능)_"
    return f"_레벨 {level - 1}의 모든 WO draft 완성 후 시작_"


def _level_group_text(groups: dict[int, list[str]]) -> str:
    if not groups:
        return "_(없음)_"
    return "\n".join(
        f"**레벨 {lvl}** ({len(wos)}개): " + ", ".join(wos)
        for lvl, wos in sorted(groups.items())
    )


def _policy_summary_card(
    wo_id: str,
    node_name: str,
    section_id: str,
    section_title: str,
    summary: str,
    edges: list[dict[str, Any]],
) -> str:
    edge_lines = [
        f"  - [{e['type']}] {e['id']}: "
        f"{e['source']}.§{e.get('source_section', '')} → "
        f"{e['target']}.§{e.get('target_section', '')}"
        for e in edges[:3]
    ]
    edge_block = "\n".join(edge_lines) if edge_lines else "  - _(엣지 없음)_"
    return (
        f"### {wo_id} `policy` — {node_name}.§{section_id} · {section_title}\n"
        f"- **요약**: {summary}\n"
        f"- **핵심 엣지 (최대 3)**:\n{edge_block}\n"
        f"- **출력**: `drafts/{wo_id}.draft.md`\n"
    )


def _screen_summary_card(
    wo_id: str,
    screen_id: str,
    screen_name: str,
    purpose: str,
    policy_wo_text: str,
    edges: list[dict[str, Any]],
) -> str:
    edge_lines = [
        f"  - [{e['type']}] {e['id']}: {e['source']} → {e['target']}"
        for e in edges[:3]
    ]
    edge_block = "\n".join(edge_lines) if edge_lines else "  - _(엣지 없음)_"
    return (
        f"### {wo_id} `screen` — {screen_id} · {screen_name}\n"
        f"- **목적**: {purpose}\n"
        f"- **연관 policy WO**: {policy_wo_text}\n"
        f"- **핵심 엣지 (최대 3)**:\n{edge_block}\n"
        f"- **출력**: `drafts/{wo_id}.draft.md`\n"
    )


# ── 메인 로직 ─────────────────────────────────────────────────────────────────

def _init_draft_frontmatter(wo_id: str, wo_type: str, layer: str, level: int, graph_hash: str) -> str:
    """안 A: 신규 draft 파일의 표준 frontmatter 생성 (status: empty)."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return f"""---
wo_id: {wo_id}
status: empty
type: {wo_type}
layer: {layer}
referenced_policies: []
referenced_master: []
referenced_screens: []
related_decisions: []
delta_required: true
last_updated: "{now}"
created_by: fanout_dag.py
review_status: ai-draft
reviewed_by: ""
reviewed_at: ""
level: {level}
graph_hash: "{graph_hash}"
---

"""


def _check_existing_draft_status(draft_path) -> str:
    """안 A idempotency: 기존 draft의 status를 읽어 반환. 없으면 'absent'."""
    if not draft_path.exists():
        return "absent"
    try:
        text = draft_path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return "no-frontmatter"
        end = text.find("---", 3)
        if end < 0:
            return "no-frontmatter"
        fm = text[3:end]
        for line in fm.splitlines():
            line = line.strip()
            if line.startswith("status:"):
                return line.split(":", 1)[1].strip()
        return "no-status"
    except Exception:
        return "read-error"


def _inject_status_field(text: str, status: str) -> str:
    """frontmatter 에 status 라인이 없으면 외과적으로 1줄만 삽입(본문·기타 필드 보존).

    cluster draft 의 중첩 YAML(cluster:)·JSON 배열을 재렌더하지 않으려는 안전 마이그레이션.
    frontmatter 가 없으면 원문 그대로 반환(상위에서 별도 처리)."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end < 0:
        return text
    head, rest = text[:end], text[end:]
    if re.search(r"(?m)^\s*status\s*:", head):
        return text  # 이미 존재 — 보존
    # type 라인 다음(없으면 frontmatter 첫 줄 다음)에 삽입
    lines = head.splitlines()
    insert_at = next((i + 1 for i, ln in enumerate(lines)
                      if ln.strip().startswith("type:")), 1)
    lines.insert(insert_at, f"status: {status}")
    return "\n".join(lines) + rest


# ── 안정 채번 (영속 WO 매핑) ─────────────────────────────────────────────────

def _canonical_key(node_type: str, node_name: str, section_id: str) -> str:
    """노드의 안정적 식별 키. graph.json 순회 순서와 무관하게 동일 노드는 동일 키.

    policy: policy::{node_name}::{section_id}
    screen: screen::{node_name}
    """
    if node_type == "screen":
        return f"screen::{node_name}"
    return f"policy::{node_name}::{section_id}"


def _load_wo_map(output_dir: Path) -> dict[str, Any]:
    """영속 WO 매핑 로드. 없거나 손상되면 빈 매핑 반환."""
    path = output_dir / WO_MAP_FILENAME
    if not path.exists():
        return {"version": WO_MAP_SCHEMA_VERSION, "next_counter": 1, "map": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "map" not in data:
            raise ValueError("invalid schema")
        data.setdefault("version", WO_MAP_SCHEMA_VERSION)
        data.setdefault("next_counter", 1)
        data.setdefault("map", {})
        return data
    except Exception as exc:
        print(
            f"[fanout] WARN: {WO_MAP_FILENAME} 로드 실패 ({exc}). 새 매핑으로 시작합니다.",
            file=sys.stderr,
        )
        return {"version": WO_MAP_SCHEMA_VERSION, "next_counter": 1, "map": {}}


def _save_wo_map(output_dir: Path, wo_map: dict[str, Any]) -> None:
    """영속 WO 매핑 저장 — atomic (MEDIUM #15: tmp + os.replace)."""
    import os
    path = output_dir / WO_MAP_FILENAME
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(wo_map, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(str(tmp_path), str(path))


def _assign_wo_ids_stable(
    policy_keys: list[tuple[str, str]],
    screen_keys: list[tuple[str, str]],
    wo_map: dict[str, Any],
    now_iso: str,
) -> dict[tuple[str, str], str]:
    """영속 매핑을 사용해 안정적으로 WO ID를 채번한다.

    - 기존 매핑에 있는 노드 → 기존 wo_id 재사용
    - 신규 노드 → next_counter부터 순서대로 새 wo_id 할당
    - 사라진 노드 → removed:true 로 tombstone (wo_id 재사용 금지)
    """
    canonical_to_key: dict[str, tuple[str, str]] = {}
    for key in policy_keys:
        canonical_to_key[_canonical_key("policy", key[0], key[1])] = key
    for key in screen_keys:
        canonical_to_key[_canonical_key("screen", key[0], key[1])] = key

    current_canonical = set(canonical_to_key.keys())
    prior_map: dict[str, dict[str, Any]] = dict(wo_map.get("map", {}))

    # 사용 중인 모든 번호 수집 (tombstone 포함) — 재사용 방지
    used_numbers: set[int] = set()
    for entry in prior_map.values():
        wo_id = entry.get("wo_id", "")
        if wo_id.startswith("WO-"):
            try:
                used_numbers.add(int(wo_id[3:]))
            except ValueError:
                pass

    key_to_wo: dict[tuple[str, str], str] = {}

    # 1단계: 기존 매핑에 있는 현재 노드 → 기존 wo_id 재사용 + tombstone 해제
    for canonical, key in canonical_to_key.items():
        if canonical in prior_map:
            entry = prior_map[canonical]
            key_to_wo[key] = entry["wo_id"]
            entry["removed"] = False
            entry["last_seen_at"] = now_iso

    # 2단계: 신규 노드 → 다음 사용 가능한 번호 할당
    next_counter = max(wo_map.get("next_counter", 1), 1)
    # 결정적 순서: policy 우선, 그 다음 screen, 각 그룹 내 입력 순서
    new_order: list[tuple[str, tuple[str, str], str]] = []
    for key in policy_keys:
        canonical = _canonical_key("policy", key[0], key[1])
        if canonical not in prior_map:
            new_order.append((canonical, key, "policy"))
    for key in screen_keys:
        canonical = _canonical_key("screen", key[0], key[1])
        if canonical not in prior_map:
            new_order.append((canonical, key, "screen"))

    for canonical, key, node_type in new_order:
        while next_counter in used_numbers:
            next_counter += 1
        wo_id = f"WO-{next_counter:02d}"
        used_numbers.add(next_counter)
        key_to_wo[key] = wo_id
        prior_map[canonical] = {
            "wo_id": wo_id,
            "type": node_type,
            "first_seen_at": now_iso,
            "last_seen_at": now_iso,
            "removed": False,
        }
        next_counter += 1

    # 3단계: 사라진 노드 → tombstone
    for canonical in list(prior_map.keys()):
        if canonical not in current_canonical:
            entry = prior_map[canonical]
            if not entry.get("removed"):
                entry["removed"] = True
                entry["removed_at"] = now_iso

    wo_map["map"] = prior_map
    wo_map["next_counter"] = next_counter
    wo_map["version"] = WO_MAP_SCHEMA_VERSION

    return key_to_wo


# ── delta_required 처리 ─────────────────────────────────────────────────────

def _node_no_delta(node: dict[str, Any]) -> bool:
    """policy 노드가 공통 정책을 완전 적용하는지 (WO 생성 제외 대상)."""
    return node.get("delta_required") is False


def _write_no_delta_list(
    output_dir: Path,
    no_delta_sections: list[tuple[str, dict, str, dict]],
    prefix: str,
    generated_at: str,
) -> None:
    """delta_required: false 노드 목록을 work-orders/no-delta-list.md 에 기록."""
    path = output_dir / "no-delta-list.md"
    lines = [
        "# No-Delta 노드 목록",
        "",
        f"생성: {generated_at}",
        "",
        f"다음 노드는 `{prefix}-B` 공통 정책을 완전 적용하며 별도 WO가 생성되지 않습니다.",
        "Confluence 업로드 시 \"[{doc_id} 기본 정책 완전 적용]\" 으로 자동 기록됩니다.",
        "",
    ]
    if not no_delta_sections:
        lines.append("_(no-delta 노드 없음 — 모든 policy 노드가 Delta 작성 대상)_")
    else:
        lines.extend([
            "| 노드명 | 섹션 ID | 섹션 제목 | inherits_from |",
            "|---|---|---|---|",
        ])
        for node_name, node, section_id, section in no_delta_sections:
            inherits = ", ".join(node.get("inherits_from", [])) or "_(미지정)_"
            title = section.get("title", section_id)
            lines.append(
                f"| `{node_name}` | `{section_id}` | {title} | {inherits} |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── 본문 wikilinks dangling 감사 ─────────────────────────────────────────────

WIKILINK_WO_PATTERN = re.compile(r"\[\[(WO-\d+)\]\]")


DRAFT_FILENAME_PATTERN = re.compile(r"^(WO-\d+)\.draft\.md$")


def _scan_wikilinks_dangling(
    drafts_dir: Path,
    wo_map: dict[str, Any],
) -> list[dict[str, str]]:
    """draft 본문의 [[WO-XX]] 링크와 draft 파일 자체를 활성 매핑과 대조해 보고.

    본문 참조 분류:
    - active: 활성 WO 매핑에 존재 (정상, 보고 제외)
    - tombstoned: 매핑에 있으나 removed:true (삭제된 노드 참조)
    - dangling: 매핑에 없음 (LLM 임의 작성 또는 옛 채번 잔존)
    - *-orphan-file: 위 두 케이스 중 drafts/WO-XX.draft.md 파일이 실제 존재

    파일 자체 분류 (draft="<filename>", ref="-"):
    - orphan-file-tombstoned: 파일은 있으나 노드가 삭제되어 tombstone
    - orphan-file-unknown: 파일은 있으나 매핑에 등재되지 않음
    """
    findings: list[dict[str, str]] = []
    if not drafts_dir.is_dir():
        return findings

    active_wo_ids = {
        e["wo_id"]
        for e in wo_map.get("map", {}).values()
        if not e.get("removed") and "wo_id" in e
    }
    tombstoned_wo_ids = {
        e["wo_id"]
        for e in wo_map.get("map", {}).values()
        if e.get("removed") and "wo_id" in e
    }

    for draft_path in sorted(drafts_dir.glob("*.draft.md")):
        # 본문 참조 스캔
        try:
            text = draft_path.read_text(encoding="utf-8")
        except Exception:
            continue
        refs = sorted(set(WIKILINK_WO_PATTERN.findall(text)))
        for wo_id in refs:
            if wo_id in active_wo_ids:
                continue
            target_file = drafts_dir / f"{wo_id}.draft.md"
            if wo_id in tombstoned_wo_ids:
                kind = "tombstoned-orphan-file" if target_file.exists() else "tombstoned"
            else:
                kind = "dangling-orphan-file" if target_file.exists() else "dangling"
            findings.append({
                "draft": draft_path.name,
                "ref": wo_id,
                "kind": kind,
            })
        # 파일 자체가 활성 매핑에 없는지 검사 (고아 파일)
        m = DRAFT_FILENAME_PATTERN.match(draft_path.name)
        if m:
            file_wo_id = m.group(1)
            if file_wo_id not in active_wo_ids:
                kind = "orphan-file-tombstoned" if file_wo_id in tombstoned_wo_ids else "orphan-file-unknown"
                findings.append({
                    "draft": draft_path.name,
                    "ref": "-",
                    "kind": kind,
                })
    return findings


def _write_wikilinks_audit(
    output_dir: Path,
    findings: list[dict[str, str]],
    generated_at: str,
) -> None:
    """wikilinks-audit.md 작성."""
    path = output_dir / "wikilinks-audit.md"
    if not findings:
        path.write_text(
            "# Wikilinks 감사 보고\n\n"
            f"생성: {generated_at}\n\n"
            "✅ 모든 `[[WO-XX]]` 링크가 활성 WO 매핑과 일치합니다.\n",
            encoding="utf-8",
        )
        return

    action_map = {
        "tombstoned": "삭제된 노드 참조 — 본문에서 제거 권고",
        "tombstoned-orphan-file": "tombstoned + 고아 draft 파일 잔존 — 본문 제거 + 고아 파일 정리",
        "dangling": "활성 매핑에 없는 WO 참조 — 본문에서 제거 권고",
        "dangling-orphan-file": "매핑에 없으나 파일 존재 — 본문 제거 + 파일 정리 검토",
        "orphan-file-tombstoned": "draft 파일 자체가 고아 — 노드 삭제된 상태. 보관 또는 수동 삭제 검토",
        "orphan-file-unknown": "draft 파일이 매핑에 등재되지 않음 — 수동 파일 또는 옛 fanout 잔존. 정리 검토",
    }
    lines = [
        "# Wikilinks 감사 보고",
        "",
        f"생성: {generated_at}",
        "",
        f"⚠️ {len(findings)}건의 dangling/tombstoned 참조 발견:",
        "",
        "| draft | 참조 WO | 분류 | 처리 권고 |",
        "|---|---|---|---|",
    ]
    for f in findings:
        action = action_map.get(f["kind"], "확인 필요")
        lines.append(f"| `{f['draft']}` | `{f['ref']}` | `{f['kind']}` | {action} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── 본문 wikilinks 재동기화 (마커 기반) ──────────────────────────────────────

def _replace_wikilinks_block(text: str, new_inner: str) -> str:
    """본문의 wikilinks 마커 블록 사이를 새 내용으로 교체한다.

    마커가 없으면(레거시 draft) `## Workflow Connections` 섹션 *본문만* 교체하고
    그 다음 H2 섹션(있다면) 이후 내용은 그대로 보존한다.
    섹션 자체가 없으면 파일 끝에 새로 추가한다.
    """
    s_idx = text.find(WIKILINKS_START)
    e_idx = text.find(WIKILINKS_END)
    if s_idx >= 0 and e_idx > s_idx:
        before = text[: s_idx + len(WIKILINKS_START)]
        after = text[e_idx:]
        return f"{before}\n{new_inner}\n{after}"

    # CRITICAL #3: 레거시 draft fallback — 다음 H2 까지만 교체, 이후 본문 보존
    workflow_idx = text.rfind("## Workflow Connections")
    new_block = (
        f"## Workflow Connections\n\n{WIKILINKS_START}\n{new_inner}\n{WIKILINKS_END}\n"
    )
    if workflow_idx >= 0:
        # 다음 H2 (또는 EOF) 까지가 기존 섹션 영역
        next_h2_match = re.search(r"^##\s+(?!Workflow\s+Connections)", text[workflow_idx + 1:], re.MULTILINE)
        section_end = workflow_idx + 1 + next_h2_match.start() if next_h2_match else len(text)
        before = text[:workflow_idx].rstrip()
        trailing = text[section_end:]
        # before + new_block + trailing (이후 모든 PM 작성 섹션 보존)
        result = (before + "\n\n" if before else "") + new_block
        if trailing.strip():
            result = result.rstrip() + "\n\n" + trailing.lstrip()
        else:
            result = result + trailing
        return result
    return text.rstrip() + "\n\n" + new_block


def _detect_cluster_signals(
    graph_path: Path, graph: dict[str, Any], output_dir: Path
) -> list[str]:
    """이 프로젝트가 cluster(dossier) 모델(Track A)인지 나타내는 신호를 수집한다.

    하나라도 감지되면 legacy section-WO fanout 은 fail-closed 되어야 한다
    (P0 — fanout fail-closed 가드, fix-plan-track-routing). 반환값은 사람이
    읽는 신호 설명 목록이며, 비어 있으면 legacy 진입이 안전하다고 본다.
    """
    signals: list[str] = []
    graph_dir = graph_path.parent
    drafts_dir = output_dir.parent / "drafts"

    # ① 영속 트랙 마커 (P1 — cluster_identify / plan-audit 가 기록)
    mode_path = graph_dir / "project-mode.json"
    if mode_path.exists():
        try:
            mode = json.loads(mode_path.read_text(encoding="utf-8"))
        except Exception:
            mode = {}
        if str(mode.get("track", "")).upper() == "A" or mode.get("model") == "dossier":
            signals.append(
                f"project-mode.json (track={mode.get('track')}, model={mode.get('model')})"
            )

    # ② cluster_identify.py 산출물 (cluster 토폴로지가 이미 구성됨)
    if (graph_dir / "cluster_map.json").exists():
        signals.append("graph/cluster_map.json")
    if (graph_dir / "graph.clustered.json").exists():
        signals.append("graph/graph.clustered.json")

    # ③ graph 노드에 capability/cluster_id 메타 존재
    nodes = graph.get("graph", {}).get("nodes", {})
    if any(n.get("capability") or n.get("cluster_id") for n in nodes.values()):
        signals.append("graph 노드에 capability/cluster_id 부여됨")

    # ④ 이미 작성된 dossier(cluster) draft — 이번 사고의 핵심 신호
    if drafts_dir.exists():
        dossiers = sorted(drafts_dir.glob("cluster_*.draft.md"))
        if dossiers:
            signals.append(
                f"drafts/ 에 dossier draft {len(dossiers)}건 (cluster_*.draft.md)"
            )

    return signals


VALID_PUBLICATION_MODES = ("dossier-page", "split-deliverable")


def _apply_publication_mode(graph_dir: Path, publication_mode: str | None) -> None:
    """graph/project-mode.json 에 publication_mode 를 read-modify-write 한다.

    fix-plan-dossier-publish-split — cluster fanout 직후 발행 모드를 영속 마커에
    박는다. 다른 키(track/decided_by/section_wo_retired …)는 보존한다. None 이면
    무변경(기존 값/기본 dossier-page 유지) — dbaas 등 기존 프로젝트 회귀 가드.
    """
    if not publication_mode:
        return
    if publication_mode not in VALID_PUBLICATION_MODES:
        raise FanoutError(
            f"무효한 publication_mode: {publication_mode!r}. "
            f"허용: {list(VALID_PUBLICATION_MODES)}"
        )
    path = graph_dir / "project-mode.json"
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["publication_mode"] = publication_mode
    data.setdefault("track", "A")
    data.setdefault("model", "dossier")
    data["updated_at"] = datetime.utcnow().isoformat() + "Z"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def fanout(
    graph_path: Path,
    output_dir: Path,
    product_name: str,
    prefix: str = "",
    *,
    cluster_mode: bool = False,
    force_legacy: bool = False,
    publication_mode: str | None = None,
) -> None:
    """Work Order 생성 진입.

    cluster_mode=True (Phase 5C — Track A Full Product):
        graph.json 의 capability/cluster_id 메타로 정책 노드를 cluster 단위
        WO 로 생성. 각 cluster = 1 draft (templates/standard/cluster-draft.md 양식).
        Screen WO 트랙은 폐기 (Phase 5I) — cluster §2 가 D3 산출 책임.

    cluster_mode=False (default — Track B/C/Legacy):
        기존 동작 — section 단위 policy WO + screen 단위 screen WO.
        단, cluster(dossier) 모델 신호가 감지되면 fail-closed 로 중단한다
        (force_legacy=True 로만 우회 가능 — fix-plan-track-routing P0).
    """
    graph = _load(graph_path)
    graph_hash = _hash_file(graph_path)
    decisions_hash = _hash_file(graph_path.parent.parent / "decisions.md")

    # Phase 5C — cluster mode 분기 (Track A)
    if cluster_mode:
        return _fanout_cluster_mode(
            graph, output_dir, product_name, prefix, graph_hash,
            publication_mode=publication_mode,
        )

    # P0 — fail-closed 가드: cluster(dossier) 모델 신호가 있는데 legacy 로 진입하려
    # 하면 중단한다. Track A 프로젝트에 legacy fanout 을 돌려 빈 WO 셸을 양산하고
    # 기존 dossier 를 고아화한 사고의 재발 방지 (fix-plan-track-routing).
    cluster_signals = _detect_cluster_signals(graph_path, graph, output_dir)
    if cluster_signals and not force_legacy:
        signal_lines = "\n".join(f"      - {s}" for s in cluster_signals)
        raise FanoutError(
            "이 프로젝트는 cluster(dossier) 모델(Track A)로 식별됩니다. "
            "legacy section-WO 생성을 중단합니다.\n"
            f"    감지된 신호:\n{signal_lines}\n"
            "    → cluster WO 생성 의도이면: --cluster-mode 를 추가하세요.\n"
            "    → 정말 legacy 강제 의도이면: --force-legacy 를 명시하세요 "
            "(기존 dossier 옆에 section/screen WO 셸이 함께 생성됩니다)."
        )

    raw_edges = graph["graph"].get("edges", [])
    edges = _assign_edge_ids(raw_edges)

    # ── 노드 수집 ──────────────────────────────────────────────────────────────
    policy_sections_all = list(_iter_section_nodes(graph))
    screen_nodes = list(_iter_screen_nodes(graph))

    # delta_required: false 인 policy 노드는 WO 생성 대상에서 제외하고
    # no-delta-list.md 에 기록한다 (screen 노드는 delta_required 무관).
    policy_sections = [t for t in policy_sections_all if not _node_no_delta(t[1])]
    no_delta_sections = [t for t in policy_sections_all if _node_no_delta(t[1])]

    if not policy_sections and not screen_nodes:
        raise FanoutError("graph.json에 처리할 노드가 없습니다.")

    # ── 통합 키 목록 구성 ──────────────────────────────────────────────────────
    # policy 키: (node_name, section_id)
    # screen 키: (node_name, "")
    policy_keys = [(n, sid) for (n, _, sid, _) in policy_sections]
    screen_keys = [(n, "") for (n, _) in screen_nodes]
    all_keys = policy_keys + screen_keys

    # ── 위상정렬 ────────────────────────────────────────────────────────────────
    levels = _topological_levels(all_keys, edges)

    # ── WO ID 사전 채번 (영속 매핑 기반 — 재실행 시 동일 노드는 동일 WO ID) ───
    output_dir.mkdir(parents=True, exist_ok=True)
    wo_map = _load_wo_map(output_dir)
    now_iso = datetime.utcnow().isoformat() + "Z"
    key_to_wo = _assign_wo_ids_stable(policy_keys, screen_keys, wo_map, now_iso)

    # ── 엣지 인덱스 구성 ──────────────────────────────────────────────────────
    outgoing: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    incoming: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for e in edges:
        src = (e["source"], e.get("source_section", ""))
        tgt = (e["target"], e.get("target_section", ""))
        outgoing[src].append(e)
        incoming[tgt].append(e)
        if e.get("type") == "양방향참조":
            outgoing[tgt].append(e)
            incoming[src].append(e)

    # implements 엣지 기반 상호 참조 맵
    # screen → 연관 policy WO ID 목록
    screen_to_policy_wo: dict[str, list[str]] = defaultdict(list)
    # policy 섹션 키 → 연관 screen WO ID 목록
    policy_to_screen_wo: dict[tuple[str, str], list[str]] = defaultdict(list)
    for e in edges:
        if e.get("type") != "implements":
            continue
        s_key = (e["source"], "")
        p_key = (e["target"], e.get("target_section", ""))
        # 양쪽 모두 활성 WO 매핑에 있을 때만 cross-ref 등록
        # (no-delta 노드 또는 graph 변경 직후 dangling 엣지 대비)
        if s_key in key_to_wo and p_key in key_to_wo:
            screen_to_policy_wo[e["source"]].append(key_to_wo[p_key])
            policy_to_screen_wo[p_key].append(key_to_wo[s_key])

    # ── 출력 디렉토리 준비 (output_dir은 채번 단계에서 이미 생성됨) ────────────
    (output_dir.parent / "drafts").mkdir(parents=True, exist_ok=True)

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    prefix_val = prefix or "PREFIX"
    summary_cards: list[str] = []
    precondition_notes: list[str] = []
    policy_level_groups: dict[int, list[str]] = defaultdict(list)
    screen_level_groups: dict[int, list[str]] = defaultdict(list)
    # 개선안 G — index.json 기계 판독용 레코드 (CONTEXT_OPTIMIZATION.md)
    wo_records: list[dict[str, Any]] = []

    # ── policy WO 파일 생성 ────────────────────────────────────────────────────
    for node_name, node, section_id, section in policy_sections:
        key = (node_name, section_id)
        wo_id = key_to_wo[key]
        lvl = levels[key]
        policy_level_groups[lvl].append(f"`{wo_id}` ({node_name}.§{section_id})")

        out_rows = [_render_edge_row(e) for e in outgoing[key]]
        in_rows = [_render_edge_row(e) for e in incoming[key]]

        related_screens = policy_to_screen_wo.get(key, [])
        related_screen_text = (
            "\n".join(f"- `{wid}`" for wid in related_screens)
            if related_screens
            else "_(없음)_"
        )

        content = DEFAULT_POLICY_TEMPLATE.format(
            WO_ID=wo_id,
            SECTION_TITLE=section.get("title", section_id),
            PRODUCT_NAME=product_name,
            GENERATED_AT=now,
            GRAPH_HASH=graph_hash,
            LEVEL=lvl,
            NODE_NAME=node_name,
            NODE_ROLE=node.get("role", "unknown"),
            SECTION_ID=section_id,
            DECISIONS_HASH=decisions_hash,
            OUTGOING_EDGES=_edges_table(out_rows),
            INCOMING_EDGES=_edges_table(in_rows),
            RELATED_SCREEN_WOS=related_screen_text,
            SECTION_SUMMARY=section.get("summary", "_(graph.json에 summary 없음)_"),
            LEVEL_DEPS=_level_deps_text(lvl),
            PREFIX_VAL=prefix_val,
        )
        # Wikilinks: collect related WO IDs then replace placeholder
        linked_wo_ids: set[str] = set(related_screens)
        for e in incoming[key]:
            if e.get("type") == "전제조건":
                pred_key = (e["source"], e.get("source_section", ""))
                if pred_key in key_to_wo:
                    linked_wo_ids.add(key_to_wo[pred_key])
        for e in outgoing[key]:
            if e.get("type") == "전제조건":
                tgt_key = (e["target"], e.get("target_section", ""))
                if tgt_key in key_to_wo:
                    linked_wo_ids.add(key_to_wo[tgt_key])
        wikilinks_lines = [f"- 연결된 WO: [[{wid}]]" for wid in sorted(linked_wo_ids)]
        wikilinks_str = "\n".join(wikilinks_lines) or "_(연결 WO 없음)_"
        content = content.replace("[WIKILINKS_PLACEHOLDER]", wikilinks_str)
        # 안 A: drafts/{WO_ID}.draft.md로 직접 생성, idempotency 보장
        draft_path = output_dir.parent / "drafts" / f"{wo_id}.draft.md"
        existing_status = _check_existing_draft_status(draft_path)
        if existing_status in ("ai-draft", "human-reviewed", "frozen"):
            # 본문 보존 + wikilinks 마커 블록만 결정적으로 재동기화 (dangling 방지)
            existing_text = draft_path.read_text(encoding="utf-8")
            new_text = _replace_wikilinks_block(existing_text, wikilinks_str)
            if new_text != existing_text:
                draft_path.write_text(new_text, encoding="utf-8")
        else:
            # 신규 또는 empty/no-frontmatter: 전체 덮어쓰기
            frontmatter = _init_draft_frontmatter(wo_id, "policy", "C", lvl, graph_hash[:12])
            draft_path.write_text(frontmatter + content, encoding="utf-8")
        # work-orders/{WO_ID}.md 생성 코드 제거 (안 A)

        summary_cards.append(_policy_summary_card(
            wo_id, node_name, section_id,
            section.get("title", section_id),
            section.get("summary", "-"),
            outgoing[key] + incoming[key],
        ))

        wo_records.append({
            "wo_id": wo_id,
            "type": "policy",
            "level": lvl,
            "node_name": node_name,
            "section_id": section_id,
            "section_title": section.get("title", section_id),
            "node_role": node.get("role", "unknown"),
            "delta_required": node.get("delta_required"),
            "inherits_from": node.get("inherits_from", []),
            "includes": node.get("includes", []),
            "related_screen_wos": list(related_screens),
            "linked_wos": sorted(linked_wo_ids),
            "draft_path": f"drafts/{wo_id}.draft.md",
        })

        for e in outgoing[key]:
            if e.get("type") == "전제조건":
                tgt_key = (e["target"], e.get("target_section", ""))
                tgt_wo = key_to_wo.get(tgt_key, "?")
                precondition_notes.append(
                    f"- `{wo_id}` → `{tgt_wo}` "
                    f"({e['target']}.§{e.get('target_section', '')}) 대기"
                )

    # ── screen WO 파일 생성 ────────────────────────────────────────────────────
    for node_name, node in screen_nodes:
        key = (node_name, "")
        wo_id = key_to_wo[key]
        lvl = levels[key]
        screen_level_groups[lvl].append(f"`{wo_id}` ({node_name})")

        impl_rows = [
            _render_edge_row(e)
            for e in edges
            if e.get("type") == "implements" and e["source"] == node_name
        ]
        screen_edge_rows = [
            _render_edge_row(e)
            for e in outgoing[key] + incoming[key]
            if e.get("type") != "implements"
        ]

        policy_wo_ids = screen_to_policy_wo.get(node_name, [])
        policy_wo_text = (
            ", ".join(f"`{p}`" for p in policy_wo_ids)
            if policy_wo_ids
            else "`TBD`"
        )

        content = SCREEN_TEMPLATE.format(
            WO_ID=wo_id,
            SCREEN_ID=node_name,
            SCREEN_NAME=node.get("screen_name", node_name),
            PURPOSE=node.get("purpose", "_(graph.json에 purpose 없음)_"),
            REQ_ID=node.get("req_id", "TBD"),
            POLICY_WO_ID=policy_wo_text,
            PRODUCT_NAME=product_name,
            GENERATED_AT=now,
            GRAPH_HASH=graph_hash,
            LEVEL=lvl,
            DECISIONS_HASH=decisions_hash,
            IMPLEMENTS_EDGES=_edges_table(impl_rows),
            SCREEN_EDGES=_edges_table(screen_edge_rows),
            LEVEL_DEPS=_level_deps_text(lvl),
            PREFIX_VAL=prefix_val,
        )
        # Wikilinks: collect related WO IDs then replace placeholder
        linked_screen_wo_ids: set[str] = set(policy_wo_ids)
        for e in outgoing[key] + incoming[key]:
            if e.get("type") == "implements":
                continue
            for candidate_key in [(e["source"], ""), (e["target"], "")]:
                if candidate_key != key and candidate_key in key_to_wo:
                    linked_screen_wo_ids.add(key_to_wo[candidate_key])
        wikilinks_screen_lines = [f"- 연결된 WO: [[{wid}]]" for wid in sorted(linked_screen_wo_ids)]
        wikilinks_screen_str = "\n".join(wikilinks_screen_lines) or "_(연결 WO 없음)_"
        content = content.replace("[WIKILINKS_PLACEHOLDER]", wikilinks_screen_str)
        # 안 A: drafts/{WO_ID}.draft.md로 직접 생성, idempotency 보장
        draft_path = output_dir.parent / "drafts" / f"{wo_id}.draft.md"
        existing_status = _check_existing_draft_status(draft_path)
        if existing_status in ("ai-draft", "human-reviewed", "frozen"):
            # 본문 보존 + wikilinks 마커 블록만 결정적으로 재동기화 (dangling 방지)
            existing_text = draft_path.read_text(encoding="utf-8")
            new_text = _replace_wikilinks_block(existing_text, wikilinks_screen_str)
            if new_text != existing_text:
                draft_path.write_text(new_text, encoding="utf-8")
        else:
            frontmatter = _init_draft_frontmatter(wo_id, "screen", "C", lvl, graph_hash[:12])
            draft_path.write_text(frontmatter + content, encoding="utf-8")
        # work-orders/{WO_ID}.md 생성 코드 제거 (안 A)

        summary_cards.append(_screen_summary_card(
            wo_id, node_name,
            node.get("screen_name", node_name),
            node.get("purpose", "-"),
            policy_wo_text,
            outgoing[key] + incoming[key],
        ))

        wo_records.append({
            "wo_id": wo_id,
            "type": "screen",
            "level": lvl,
            "node_name": node_name,
            "screen_name": node.get("screen_name", node_name),
            "purpose": node.get("purpose"),
            "req_id": node.get("req_id"),
            "related_policy_wos": list(policy_wo_ids),
            "implements": [e["target"] for e in edges
                           if e.get("type") == "implements" and e["source"] == node_name],
            "linked_wos": sorted(linked_screen_wo_ids),
            "draft_path": f"drafts/{wo_id}.draft.md",
        })

        for e in outgoing[key]:
            if e.get("type") == "전제조건":
                tgt_key = (e["target"], e.get("target_section", ""))
                tgt_wo = key_to_wo.get(tgt_key, "?")
                precondition_notes.append(
                    f"- `{wo_id}` → `{tgt_wo}` ({e['target']}) 대기"
                )

    # ── index.md 생성 ──────────────────────────────────────────────────────────
    all_levels = set(policy_level_groups) | set(screen_level_groups)
    pre_text = (
        "\n".join(precondition_notes)
        if precondition_notes
        else "_(전제조건 엣지 없음 — 모든 WO 동시 시작 가능)_"
    )

    index_text = INDEX_TEMPLATE.format(
        PRODUCT_NAME=product_name,
        GENERATED_AT=now,
        GRAPH_HASH=graph_hash,
        TOTAL_WO=len(policy_sections) + len(screen_nodes),
        TOTAL_POLICY=len(policy_sections),
        TOTAL_SCREEN=len(screen_nodes),
        TOTAL_LEVELS=len(all_levels),
        PRECONDITION_NOTES=pre_text,
        POLICY_LEVEL_GROUPS=_level_group_text(policy_level_groups),
        SCREEN_LEVEL_GROUPS=_level_group_text(screen_level_groups),
        SUMMARY_CARDS="\n".join(summary_cards),
    )
    (output_dir / "index.md").write_text(index_text, encoding="utf-8")

    # 개선안 G — 기계 판독용 index.json 동시 출력 (CONTEXT_OPTIMIZATION.md)
    index_payload = {
        "_meta": {
            "product": product_name,
            "generated_at": now,
            "graph_hash": graph_hash,
            "decisions_hash": decisions_hash,
            "totals": {
                "wo": len(policy_sections) + len(screen_nodes),
                "policy": len(policy_sections),
                "screen": len(screen_nodes),
                "levels": len(set(policy_level_groups) | set(screen_level_groups)),
            },
        },
        "wo": wo_records,
    }
    (output_dir / "index.json").write_text(
        json.dumps(index_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 개선안 C — graph.json 분할 파일 생성 (CONTEXT_OPTIMIZATION.md)
    _write_split_graph(graph_path.parent, graph)

    # 영속 WO 매핑 저장 (재실행 시 동일 노드 → 동일 WO ID 보장)
    _save_wo_map(output_dir, wo_map)

    # no-delta 노드 목록 (SKILL.md 단계 2 사양)
    _write_no_delta_list(output_dir, no_delta_sections, prefix_val, now)

    # 본문 wikilinks dangling 감사 (LLM 임의 작성·옛 채번 잔존 탐지)
    audit = _scan_wikilinks_dangling(output_dir.parent / "drafts", wo_map)
    _write_wikilinks_audit(output_dir, audit, now)

    tombstoned = sum(1 for e in wo_map.get("map", {}).values() if e.get("removed"))
    print(
        f"[fanout] 완료 — "
        f"policy WO: {len(policy_sections)}개 / "
        f"screen WO: {len(screen_nodes)}개 / "
        f"no-delta: {len(no_delta_sections)}개 / "
        f"tombstone: {tombstoned}개 / "
        f"wikilinks-audit: {len(audit)}건 → {output_dir}"
    )


def _write_split_graph(graph_dir: Path, graph_doc: dict) -> None:
    """graph.json을 node_type별·엣지별로 4개 파일로 분할 저장한다."""
    g = graph_doc.get("graph", {})
    all_nodes: dict = g.get("nodes", {})
    all_edges: list = g.get("edges", [])
    metadata: dict = g.get("metadata", {})

    policy_nodes = {k: v for k, v in all_nodes.items() if v.get("node_type") != "screen"}
    screen_nodes = {k: v for k, v in all_nodes.items() if v.get("node_type") == "screen"}

    # inherits_from 참조를 refs로 수집
    refs: list[dict] = []
    for node_name, node in all_nodes.items():
        for ref in node.get("inherits_from", []):
            refs.append({"from": node_name, "to": ref})

    (graph_dir / "graph.policy.json").write_text(
        json.dumps({"graph": {"metadata": metadata, "nodes": policy_nodes}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (graph_dir / "graph.screen.json").write_text(
        json.dumps({"graph": {"metadata": metadata, "nodes": screen_nodes}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (graph_dir / "graph.edges.json").write_text(
        json.dumps({"graph": {"edges": all_edges}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (graph_dir / "graph.refs.json").write_text(
        json.dumps({"graph": {"refs": refs}},
                   ensure_ascii=False, indent=2), encoding="utf-8")


# ── Phase 5C — Cluster mode 메인 ─────────────────────────────────────────
def _fanout_cluster_mode(
    graph: dict[str, Any],
    output_dir: Path,
    product_name: str,
    prefix: str,
    graph_hash: str,
    *,
    publication_mode: str | None = None,
) -> None:
    """Cluster 단위 WO 생성 (Track A — Full Product).

    graph.json 의 각 cluster (capability + cluster_id) 당 1 draft 생성:
        drafts/cluster_{cluster_id}.draft.md

    cluster_identify.py 가 사전 실행되어 노드 메타에 capability/cluster_id 가
    부여되어 있어야 함. 미부여 노드는 DX-{node_name} fallback cluster.
    """
    cluster_groups = list(_iter_cluster_nodes(graph))
    if not cluster_groups:
        raise FanoutError("graph.json 에 처리할 policy 노드가 없습니다 (cluster mode).")

    output_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir = output_dir.parent / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    now_iso = datetime.utcnow().isoformat() + "Z"
    prefix_val = prefix or "PX"
    cluster_records: list[dict[str, Any]] = []

    for capability, cluster_id, cluster_name, members in cluster_groups:
        draft_path = drafts_dir / f"cluster_{cluster_id}.draft.md"
        wo_id = f"{prefix_val}-K-{cluster_id}"

        # 기존 draft 라이프사이클 처리 (안 A status 정합)
        existing_status = _check_existing_draft_status(draft_path)
        record_status = existing_status

        if existing_status in ("ai-draft", "human-reviewed", "frozen"):
            # 작성/검토 진행 중 — 내용 보존(idempotency). 멤버 변경 갱신은 향후 5D.
            pass
        elif existing_status in ("no-status", "no-frontmatter"):
            # 구버전(status 없는) 기존 draft — 내용 보존하며 status 만 외과적 주입.
            # 이미 작성됐을 수 있으므로 ai-draft 로 간주(역추론, migrate 규칙과 동일).
            existing_text = draft_path.read_text(encoding="utf-8")
            draft_path.write_text(_inject_status_field(existing_text, "ai-draft"),
                                  encoding="utf-8")
            record_status = "ai-draft"
        else:
            # absent / empty / read-error: 빈 셸 신규 생성 (status: empty 내장)
            content = _generate_cluster_draft_content(
                capability=capability,
                cluster_id=cluster_id,
                cluster_name=cluster_name,
                members=members,
                product_name=product_name,
                graph_hash=graph_hash,
                now_iso=now_iso,
                prefix_val=prefix_val,
            )
            draft_path.write_text(content, encoding="utf-8")
            record_status = "empty"

        cluster_records.append({
            "wo_id": wo_id,
            "type": "cluster",
            "capability": capability,
            "cluster_id": cluster_id,
            "cluster_name": cluster_name,
            "members": [m[0] for m in members],
            "draft_path": str(draft_path.relative_to(output_dir.parent)),
            "status": record_status,
        })

    # cluster_index.json — 후속 단계 (render transpose 등) 의 입력
    index_path = output_dir / "cluster_index.json"
    index_path.write_text(
        json.dumps(
            {
                "product": product_name,
                "generated_at": now_iso,
                "graph_hash": graph_hash[:12],
                "clusters": cluster_records,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    # 발행 모드 영속화 (fix-plan-dossier-publish-split) — read-modify-write.
    # graph/project-mode.json 에 박아 render/cr/sync 가 트랙을 추론하지 않고 읽게 한다.
    _apply_publication_mode(output_dir.parent / "graph", publication_mode)

    print(
        f"[fanout] cluster mode: {len(cluster_records)} clusters → {drafts_dir}"
        + (f" (publication_mode={publication_mode})" if publication_mode else ""),
        file=sys.stderr,
    )


# ── CLI 진입점 ────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="graph.json을 위상정렬해 Work Order 파일을 생성한다."
    )
    parser.add_argument("graph", type=Path, help="graph/graph.json 경로")
    parser.add_argument("--output", type=Path, required=True, help="work-orders/ 출력 디렉토리")
    parser.add_argument("--product", type=str, default="unknown", help="프로젝트명")
    parser.add_argument("--prefix", type=str, default="", help="{PREFIX} 값 (예: CLOUD)")
    parser.add_argument(
        "--cluster-mode",
        action="store_true",
        help="Phase 5C — cluster 단위 WO 생성 (Track A Full Product). graph 에 "
             "capability/cluster_id 가 부여되어 있어야 함 (cluster_identify.py 선행).",
    )
    parser.add_argument(
        "--force-legacy",
        action="store_true",
        help="cluster(dossier) 모델 신호가 감지돼도 legacy section/screen WO 생성을 "
             "강제한다. fail-closed 가드(P0)를 명시적으로 우회 — 기존 dossier 옆에 "
             "WO 셸이 함께 생성되므로 의도를 확인한 경우에만 사용한다.",
    )
    parser.add_argument(
        "--publication-mode",
        choices=list(VALID_PUBLICATION_MODES),
        default=None,
        help="발행 모드 (cluster-mode 전용, fix-plan-dossier-publish-split). "
             "dossier-page(기본): 기능정의서 1개 = 페이지 1개. "
             "split-deliverable: dossier §1/§2 를 D2 정책정의서/D3 화면설계서로 "
             "transpose 분할 발행. graph/project-mode.json 에 영속 기록된다. "
             "미지정 시 기존 값(없으면 dossier-page) 보존.",
    )
    parser.add_argument(
        "--delta",
        type=Path,
        default=None,
        help="(미구현) decisions.md 변경 기반 선택적 재생성",
    )
    parser.add_argument(
        "--regenerate",
        type=str,
        default=None,
        help="(미구현) 특정 WO만 재생성 (예: WO-07)",
    )
    args = parser.parse_args()

    if not args.prefix:
        print("[fanout] WARN: --prefix 미지정. 템플릿 내 {PREFIX}-A 가 'PREFIX-A'로 출력됩니다.", file=sys.stderr)

    if args.delta or args.regenerate:
        print(
            "[fanout] WARN: --delta / --regenerate 는 현재 전체 재생성과 동일하게 동작합니다.",
            file=sys.stderr,
        )

    try:
        fanout(
            args.graph,
            args.output,
            args.product,
            prefix=args.prefix,
            cluster_mode=args.cluster_mode,
            force_legacy=args.force_legacy,
            publication_mode=args.publication_mode,
        )
    except FanoutError as exc:
        print(f"[fanout] FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
