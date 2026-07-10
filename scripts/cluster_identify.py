#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cluster Identification (Phase 5A).

graph.json 의 policy 노드에 capability + cluster_id 를 부여한다.
publication-map.md §1 의 4축 + D2/D3 정합성 = 5축 가중 점수 (≥0.55 → 결합) 로
군집을 산출하고, 안정 ID 매핑(cluster_map.json) 으로 재실행 시 동일 결과를 보장한다.

사용 시점:
    /graph-gen 직후 또는 /fanout --cluster-mode 의 사전 단계.

입력:
    PROJECTS/{product}/graph/graph.json (policy 노드 + edges)
    PROJECTS/{product}/inputs/requirements.md (선택 — FR 메타에서 cluster 힌트 추출)

씨앗(seed) — P2 (docs/fr-cluster-alignment.md):
    요구사항 태그(capability / cluster_hint)를 union-find 초기 파티션으로 사전 결합한다.
    점수(5축·threshold)는 그 위에서 추가 병합하므로 조절 레버는 유지된다(seed-not-lock).
    cluster_lock: true 노드는 점수 병합에서 제외(씨앗 경계 고정). --ignore-seed 로 순수 점수 군집.

출력:
    PROJECTS/{product}/graph/graph.clustered.json
        — 각 policy 노드에 capability / cluster_id / cluster_name + cluster_provenance 추가
    PROJECTS/{product}/graph/cluster_map.json
        — 안정 ID 매핑(canonical_to_id) + FR 권위 인덱스(fr_index: FR→{capability,cluster_id})
    PROJECTS/{product}/reports/cluster-summary.md
        — PM 검토용 요약 (capability 별 cluster 수, 결합 점수, 씨앗 검증 kept/overridden)

CLI:
    python cluster_identify.py --graph PROJECTS/{p}/graph/graph.json \
        --output PROJECTS/{p}/graph/graph.clustered.json \
        [--cluster-map PROJECTS/{p}/graph/cluster_map.json] \
        [--threshold 0.55]                  # 결합 임계 (publication-map.md §1)
        [--summary PROJECTS/{p}/reports/cluster-summary.md]

종료 코드: 0 성공 / 1 입력 오류 / 2 graph 구조 오류
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


# 5축 가중치 (publication-map.md §1)
WEIGHTS = {
    "decision_domain": 0.30,   # policy_axis 일치
    "domain_object":   0.20,   # data 객체 공유
    "screen_surface":  0.20,   # primary_screen 일치
    "dependency_cone": 0.15,   # inherits_from 50%+ 중복
    "publication_fit": 0.15,   # D2/D3 챕터 정합성 (heuristic)
}
DEFAULT_THRESHOLD = 0.55


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_project_mode(graph_dir: Path, cluster_count: int) -> Path:
    """영속 트랙 마커 graph/project-mode.json 을 기록한다 (fix-plan-track-routing P1).

    cluster_identify 가 실행됐다는 것은 이 프로젝트가 cluster(dossier) 모델
    = Track A 임을 뜻한다. 이를 기계가독 SSoT 로 박아 fanout 의 fail-closed
    가드(_detect_cluster_signals)·plan-audit·lc 가 트랙을 추론하지 않고 읽게 한다.

    기존 파일이 있으면 PM 이 설정한 decided_by(DEC) / section_wo_retired /
    publication_mode 는 보존하고 카운트·타임스탬프만 갱신한다.

    publication_mode (fix-plan-dossier-publish-split):
        "dossier-page"      — 기능정의서 1개 = Confluence 페이지 1개 (기본)
        "split-deliverable" — dossier §1/§2 를 D2 정책정의서 / D3 화면설계서로
                              transpose 분할 발행
    값이 없으면 기존 동작(dossier-page) 으로 폴백한다 — dbaas 등 기존
    프로젝트 무변경 보장. split 전환은 /fanout --publication-mode 가 기록한다.
    """
    path = graph_dir / "project-mode.json"
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    mode = {
        "track": "A",
        "model": "dossier",
        "decided_by": existing.get("decided_by"),
        "section_wo_retired": existing.get("section_wo_retired", True),
        "publication_mode": existing.get("publication_mode", "dossier-page"),
        "cluster_count": cluster_count,
        "source": "cluster_identify",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    _save_json(path, mode)
    return path


# ── 4+1축 점수 계산 ───────────────────────────────────────────────────────
def _set_overlap(a: list[str], b: list[str]) -> float:
    """Jaccard 유사도 — 두 집합의 교집합 비율."""
    sa, sb = set(a or []), set(b or [])
    if not sa and not sb:
        return 0.0
    union = sa | sb
    return len(sa & sb) / len(union) if union else 0.0


def _score_decision_domain(n1: dict, n2: dict) -> float:
    """policy_axis 공유도."""
    return _set_overlap(n1.get("policy_axis") or [], n2.get("policy_axis") or [])


def _score_domain_object(n1: dict, n2: dict) -> float:
    """domain_object 공유도."""
    return _set_overlap(n1.get("domain_object") or [], n2.get("domain_object") or [])


def _score_screen_surface(n1: dict, n2: dict) -> float:
    """primary_screen 일치 — 단일 값 비교 (1.0 또는 0.0)."""
    ps1, ps2 = n1.get("primary_screen"), n2.get("primary_screen")
    if ps1 and ps2 and ps1 == ps2:
        return 1.0
    return 0.0


def _score_dependency_cone(
    n1_key: str, n2_key: str, dep_map: dict[str, set[str]]
) -> float:
    """inherits_from 의존성 집합 Jaccard. 50% 이상이면 결합 시그널."""
    deps1 = dep_map.get(n1_key, set())
    deps2 = dep_map.get(n2_key, set())
    return _set_overlap(list(deps1), list(deps2))


def _score_publication_fit(n1: dict, n2: dict) -> float:
    """D2/D3 챕터 정합성 — heuristic.

    두 노드가 같은 deliverable_targets 를 가지고 (예: 모두 D2 + D3),
    sections 명명이 비슷한 형태이면 한 챕터로 묶이기 자연스러움.
    """
    targets1 = set(n1.get("deliverable_targets") or ["D2"])
    targets2 = set(n2.get("deliverable_targets") or ["D2"])
    if not targets1 & targets2:
        return 0.0
    # 같은 deliverable 공유 비율
    return len(targets1 & targets2) / len(targets1 | targets2)


def cluster_score(
    n1_key: str, n1: dict,
    n2_key: str, n2: dict,
    dep_map: dict[str, set[str]],
) -> tuple[float, dict[str, float]]:
    """두 노드 간 결합 점수 (0~1) + 축별 breakdown."""
    breakdown = {
        "decision_domain": _score_decision_domain(n1, n2) * WEIGHTS["decision_domain"],
        "domain_object":   _score_domain_object(n1, n2) * WEIGHTS["domain_object"],
        "screen_surface":  _score_screen_surface(n1, n2) * WEIGHTS["screen_surface"],
        "dependency_cone": _score_dependency_cone(n1_key, n2_key, dep_map) * WEIGHTS["dependency_cone"],
        "publication_fit": _score_publication_fit(n1, n2) * WEIGHTS["publication_fit"],
    }
    return sum(breakdown.values()), breakdown


# ── 군집 알고리즘 (점수 기반 union-find) ──────────────────────────────────
class _UnionFind:
    def __init__(self, keys: list[str]) -> None:
        self.parent = {k: k for k in keys}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # 작은 ID 가 부모 (결정성)
            if ra < rb:
                self.parent[rb] = ra
            else:
                self.parent[ra] = rb


def _build_dep_map(edges: list[dict]) -> dict[str, set[str]]:
    """node → 직접 의존하는 노드 집합 (inherits_from)."""
    dep_map: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e.get("type") == "inherits_from":
            dep_map[e["source"]].add(e["target"])
    return dep_map


# ── 씨앗(seed) 헬퍼 — 요구사항 태그를 군집 씨앗으로 사용 (P2) ────────────────
def _seed_capability(node: dict) -> str | None:
    """노드의 씨앗 capability (요구사항 태그). seed_capability 우선, 없으면 capability."""
    cap = node.get("seed_capability") or node.get("capability")
    return str(cap) if cap else None


def _cluster_hint(node: dict) -> str | None:
    """노드의 cluster_hint (씨앗 멤버십 키). 비어있으면 None."""
    h = node.get("cluster_hint")
    return str(h).strip() if h and str(h).strip() else None


def _is_locked(node: dict) -> bool:
    """cluster_lock 옵트인 — 점수 기반 cross-cluster 병합에서 제외(씨앗 경계 고정)."""
    return bool(node.get("cluster_lock"))


def cluster_nodes(
    nodes: dict[str, dict],
    edges: list[dict],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    ignore_seed: bool = False,
) -> tuple[dict[str, str], list[tuple[str, str, float, dict]]]:
    """policy 노드들을 cluster 로 군집.

    P2(seed-not-lock): 동일 (capability, cluster_hint) 노드를 union-find 초기
    파티션으로 사전 결합한다(씨앗). 점수(5축·threshold)는 그 위에서 추가 병합하므로
    조절 레버는 그대로 유지된다. cluster_lock 노드는 점수 병합에서 제외(씨앗 경계 고정).
    ignore_seed=True 면 순수 점수 군집(씨앗 무시).

    Returns:
        - assignments: node_key → cluster_canonical_id (union-find root)
        - merge_log: [(node_a, node_b, score, breakdown)] — 임계 초과 결합 기록
    """
    policy_keys = sorted(
        k for k, n in nodes.items() if n.get("node_type") != "screen"
    )
    if not policy_keys:
        return {}, []

    dep_map = _build_dep_map(edges)
    uf = _UnionFind(policy_keys)
    merge_log: list[tuple[str, str, float, dict]] = []

    # P2 — 씨앗 사전 결합: 동일 (capability, cluster_hint) 노드를 미리 union
    if not ignore_seed:
        by_seed: dict[tuple[str | None, str], list[str]] = defaultdict(list)
        for k in policy_keys:
            hint = _cluster_hint(nodes[k])
            if hint:
                by_seed[(_seed_capability(nodes[k]), hint)].append(k)
        for group in by_seed.values():
            for other in group[1:]:
                uf.union(group[0], other)

    # 점수 기반 결합 (locked 노드는 cross-cluster 병합 제외)
    for i, ka in enumerate(policy_keys):
        for kb in policy_keys[i + 1 :]:
            if _is_locked(nodes[ka]) or _is_locked(nodes[kb]):
                continue
            score, breakdown = cluster_score(ka, nodes[ka], kb, nodes[kb], dep_map)
            if score >= threshold:
                uf.union(ka, kb)
                merge_log.append((ka, kb, round(score, 3), breakdown))

    assignments = {k: uf.find(k) for k in policy_keys}
    return assignments, merge_log


# ── ID 채번 (안정 매핑) ──────────────────────────────────────────────────
def _capability_of(node: dict, default: str = "Default") -> str:
    """노드의 capability 추출 — 메타에서 명시 또는 default."""
    cap = node.get("capability") or default
    # 정규화: 알파벳 + 숫자만, 공백 제거
    return "".join(c for c in str(cap) if c.isalnum() or c == "-") or default


def _capability_prefix(capability: str, used: set[str]) -> str:
    """capability → cluster_id prefix (대문자 2자, used 와 충돌 방지).

    전략 (안정성 + 유일성):
      1. 첫 2 글자 (예: Provisioning → PR)
      2. 충돌 시 첫 + 3번째 (Provisioning → PO)
      3. 충돌 시 첫 + 첫 대문자 자음 (Provisioning → PV — Pr-oV-isioning)
      4. 충돌 시 첫 + 끝 글자 (Provisioning → PG)
      5. 충돌 지속 시 hash 기반 fallback (예: P0, P1, ...)
    """
    letters = [c.upper() for c in capability if c.isalpha()] or ["X", "X"]

    candidates = []
    # 1
    if len(letters) >= 2:
        candidates.append(letters[0] + letters[1])
    # 2
    if len(letters) >= 3:
        candidates.append(letters[0] + letters[2])
    # 3 — 자음 (vowel 제외)
    vowels = set("AEIOU")
    for c in letters[1:]:
        if c not in vowels:
            cand = letters[0] + c
            if cand not in candidates:
                candidates.append(cand)
            break
    # 4 — 끝 글자
    if len(letters) >= 1:
        candidates.append(letters[0] + letters[-1])

    for c in candidates:
        if c not in used:
            return c

    # 5 — fallback: 첫 글자 + 숫자
    for i in range(10):
        cand = f"{letters[0]}{i}"
        if cand not in used:
            return cand
    return "XX"


def assign_cluster_ids(
    nodes: dict[str, dict],
    assignments: dict[str, str],
    cluster_map: dict[str, Any],
) -> dict[str, dict]:
    """canonical id → (capability, cluster_id, cluster_name) 매핑.

    cluster_map (안정 매핑) 을 우선 참조 — 재실행 시 동일 cluster_id 유지.
    """
    # canonical 별 capability + 멤버 수집
    by_canonical: dict[str, list[str]] = defaultdict(list)
    for node_key, canonical in assignments.items():
        by_canonical[canonical].append(node_key)

    # capability 별 cluster 순번 (안정 매핑 우선)
    cap_to_seq: dict[str, int] = defaultdict(int)
    persistent_map = cluster_map.get("canonical_to_id", {})
    # capability → prefix 매핑도 persistent (안정성)
    capability_prefix_map: dict[str, str] = cluster_map.get("capability_to_prefix", {})
    used_prefixes: set[str] = set(capability_prefix_map.values())

    # cap_to_seq 복원 — 기존 매핑에서 capability 별 마지막 순번
    for cid in persistent_map.values():
        if "-" in cid:
            p, num = cid.rsplit("-", 1)
            try:
                seq = int(num)
                cap_of_prefix = next(
                    (c for c, pr in capability_prefix_map.items() if pr == p), None
                )
                if cap_of_prefix:
                    cap_to_seq[cap_of_prefix] = max(cap_to_seq[cap_of_prefix], seq)
            except ValueError:
                pass

    result: dict[str, dict] = {}

    # 안정성 보장: canonical 정렬 후 처리
    for canonical in sorted(by_canonical.keys()):
        members = sorted(by_canonical[canonical])
        # capability 결정 — 멤버들의 capability 중 가장 흔한 것 (단순)
        caps = [_capability_of(nodes[k]) for k in members]
        capability = max(set(caps), key=caps.count) if caps else "Default"

        # capability 별 unique prefix (안정 매핑 우선)
        if capability in capability_prefix_map:
            prefix = capability_prefix_map[capability]
        else:
            prefix = _capability_prefix(capability, used_prefixes)
            capability_prefix_map[capability] = prefix
            used_prefixes.add(prefix)

        # cluster_id 결정 — 안정 매핑 우선
        if canonical in persistent_map:
            cluster_id = persistent_map[canonical]
        else:
            cap_to_seq[capability] += 1
            cluster_id = f"{prefix}-{cap_to_seq[capability]:02d}"
            persistent_map[canonical] = cluster_id

        # cluster_name 결정 — 첫 멤버의 sections 또는 node_name 기반
        first_node = nodes[members[0]]
        cluster_name = (
            first_node.get("cluster_name")
            or first_node.get("display_name")
            or members[0].replace("_", "")
        )

        result[canonical] = {
            "capability": capability,
            "cluster_id": cluster_id,
            "cluster_name": cluster_name,
            "members": members,
        }

    cluster_map["canonical_to_id"] = persistent_map
    cluster_map["capability_to_prefix"] = capability_prefix_map
    return result


# ── 씨앗 검증(provenance) + FR 인덱스 (P2) ───────────────────────────────
def compute_provenance(
    nodes: dict[str, dict],
    assignments: dict[str, str],
    cluster_info: dict[str, dict],
) -> dict[str, str]:
    """노드별 씨앗 검증 결과.

    - "computed"          : 씨앗(capability/cluster_hint) 없음 — 순수 계산 군집
    - "seed_kept"         : 최종 cluster capability == 씨앗 capability
    - "seed_overridden:…" : 점수 병합으로 다른 capability 군집에 흡수됨(사유)
    """
    canon_cap = {canon: info["capability"] for canon, info in cluster_info.items()}
    prov: dict[str, str] = {}
    for k, canon in assignments.items():
        node = nodes[k]
        seed_cap = node.get("seed_capability") or node.get("capability")
        hint = _cluster_hint(node)
        if not seed_cap and not hint:
            prov[k] = "computed"
            continue
        final_cap = canon_cap.get(canon)
        if seed_cap and final_cap and str(final_cap) != str(seed_cap):
            prov[k] = f"seed_overridden:capability {seed_cap}→{final_cap}"
        else:
            prov[k] = "seed_kept"
    return prov


def build_fr_index(
    nodes: dict[str, dict],
    assignments: dict[str, str],
    cluster_info: dict[str, dict],
) -> dict[str, dict]:
    """FR → {capability, cluster_id} 권위 매핑 (cluster_map.json 에 보관).

    노드의 fr_refs 를 cluster 멤버십으로 역인덱싱한다. D1 발행이 capability 별
    FR 묶음(파생 뷰)을 그릴 때 cluster_ref 주입 키로 사용한다(DEC-A/C).
    """
    fr_index: dict[str, dict] = {}
    for k, canon in assignments.items():
        info = cluster_info.get(canon)
        if not info:
            continue
        for fr in nodes[k].get("fr_refs") or []:
            fr_index[str(fr)] = {
                "capability": info["capability"],
                "cluster_id": info["cluster_id"],
            }
    return fr_index


# 횡단 모듈 참조로 보는 엣지 타입 (graph-schema.json edges.type)
_MODULE_EDGE_TYPES = {"inherits_from", "includes", "references"}


def build_module_index(
    nodes: dict[str, dict],
    edges: list[dict],
    assignments: dict[str, str],
    cluster_info: dict[str, dict],
) -> dict[str, list[dict]]:
    """횡단(cross-cutting) 모듈 → 이를 참조하는 cluster 역인덱스 (DEC-F).

    이메일·SMS 발송 모듈처럼 여러 capability 가 공유하는 관심사는 capability 로
    쪼개 인라인하지 않고 한 곳(모듈/전용 capability)에 두고 각 기능이 참조한다.
    그 참조(엣지)를 역인덱싱하면 "어느 기능이 이 모듈을 쓰나"를 한꺼번에 보는
    **횡단 트리거 매트릭스**가 된다(발행 P3 파생 뷰의 입력).

    모듈 판정: 대상이 군집 대상 policy 노드가 아니거나(reference/외부) node_type==reference,
    또는 role=='cross-cutting'.
    """
    node_info = {k: cluster_info.get(c) for k, c in assignments.items()}
    module_index: dict[str, list[dict]] = defaultdict(list)
    seen: set[tuple[str, str, str]] = set()
    for e in edges:
        if e.get("type") not in _MODULE_EDGE_TYPES:
            continue
        src, tgt = e.get("source"), e.get("target")
        if not src or not tgt:
            continue
        info = node_info.get(src)  # source 가 군집된 기능 노드일 때만(기능→모듈 방향)
        if not info:
            continue
        tgt_node = nodes.get(tgt, {})
        is_module = (
            tgt not in assignments
            or tgt_node.get("node_type") == "reference"
            or tgt_node.get("role") == "cross-cutting"
        )
        if not is_module:
            continue
        key = (tgt, info["cluster_id"], src)
        if key in seen:
            continue
        seen.add(key)
        module_index[tgt].append({
            "cluster_id": info["cluster_id"],
            "capability": info["capability"],
            "source": src,
            "via": e.get("type"),
            "section": e.get("source_section"),
        })
    # 결정성: cluster_id 정렬
    return {
        k: sorted(v, key=lambda r: (r["capability"], r["cluster_id"], r["source"]))
        for k, v in sorted(module_index.items())
    }


# ── 노드 메타 어노테이션 ──────────────────────────────────────────────────
def annotate_graph(
    graph: dict,
    assignments: dict[str, str],
    cluster_info: dict[str, dict],
    provenance: dict[str, str] | None = None,
) -> dict:
    """graph 의 각 policy 노드에 cluster 메타(+씨앗 provenance) 부여."""
    nodes = graph["graph"]["nodes"]
    for node_key, canonical in assignments.items():
        info = cluster_info.get(canonical)
        if not info:
            continue
        node = nodes[node_key]
        node["capability"] = info["capability"]
        node["cluster_id"] = info["cluster_id"]
        node["cluster_name"] = info["cluster_name"]
        if provenance and node_key in provenance:
            node["cluster_provenance"] = provenance[node_key]
    return graph


# ── 요약 보고서 ──────────────────────────────────────────────────────────
def make_summary(
    cluster_info: dict[str, dict],
    merge_log: list[tuple[str, str, float, dict]],
    threshold: float,
    provenance: dict[str, str] | None = None,
) -> str:
    """PM 검토용 markdown 요약."""
    lines = ["# Cluster Identification 요약\n"]
    lines.append(f"**임계값**: 결합 점수 ≥ {threshold} (publication-map.md §1)\n")

    # P2 — 씨앗 검증 요약 (seed_kept / seed_overridden)
    if provenance:
        kept = sum(1 for v in provenance.values() if v == "seed_kept")
        overridden = {k: v for k, v in provenance.items() if v.startswith("seed_overridden")}
        computed = sum(1 for v in provenance.values() if v == "computed")
        lines.append(
            f"**씨앗 검증**: seed_kept {kept} · seed_overridden {len(overridden)} · computed {computed}\n"
        )
        if overridden:
            lines.append("| 노드 | 씨앗 override 사유 |")
            lines.append("|---|---|")
            for k in sorted(overridden):
                lines.append(f"| {k} | {overridden[k].split(':', 1)[1].strip()} |")
            lines.append("")

    lines.append(f"**Capability 별 cluster 수**:\n")

    cap_clusters: dict[str, list[dict]] = defaultdict(list)
    for canonical, info in cluster_info.items():
        cap_clusters[info["capability"]].append(info)

    lines.append("| Capability | Cluster 수 | Cluster IDs | 총 노드 수 |")
    lines.append("|---|---|---|---|")
    for cap in sorted(cap_clusters.keys()):
        clusters = cap_clusters[cap]
        ids = ", ".join(c["cluster_id"] for c in clusters)
        total = sum(len(c["members"]) for c in clusters)
        lines.append(f"| {cap} | {len(clusters)} | {ids} | {total} |")

    lines.append("\n## 결합 이벤트 (임계 초과 쌍)\n")
    if not merge_log:
        lines.append("- 결합 이벤트 없음 (모든 노드가 독립 cluster).")
    else:
        lines.append("| Node A | Node B | 총 점수 | 도메인 | 객체 | 화면 | 의존성 | 발행정합 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for a, b, score, bd in sorted(merge_log, key=lambda x: -x[2]):
            lines.append(
                f"| {a} | {b} | {score} | "
                f"{round(bd['decision_domain'], 3)} | "
                f"{round(bd['domain_object'], 3)} | "
                f"{round(bd['screen_surface'], 3)} | "
                f"{round(bd['dependency_cone'], 3)} | "
                f"{round(bd['publication_fit'], 3)} |"
            )

    lines.append("\n## 권장 검토")
    lines.append("- 점수 0.55~0.70 (경계 결합) 의 쌍은 PM 검토 권장")
    lines.append("- Cluster 가 1 노드뿐인 항목은 capability 라벨링 보강 검토")
    lines.append("- 후속: /fanout --cluster-mode 로 WO 생성")
    lines.append(
        "  (graph/project-mode.json 에 track=A 기록됨 — legacy /fanout 은 "
        "fail-closed 로 차단되며 --force-legacy 로만 우회 가능)"
    )

    return "\n".join(lines) + "\n"


# ── 메인 ─────────────────────────────────────────────────────────────────
def identify_clusters(
    graph_path: Path,
    output_path: Path,
    *,
    cluster_map_path: Path | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    ignore_seed: bool = False,
) -> tuple[dict, dict[str, dict], list]:
    """graph.json 로드 → cluster 식별 → 어노테이션 → 저장."""
    graph = _load_json(graph_path)
    nodes = graph.get("graph", {}).get("nodes", {})
    edges = graph.get("graph", {}).get("edges", [])

    if not nodes:
        raise ValueError(f"graph 의 nodes 가 비어 있음: {graph_path}")

    # cluster_map 로드 (안정 매핑)
    cluster_map: dict = {}
    if cluster_map_path and cluster_map_path.is_file():
        cluster_map = _load_json(cluster_map_path)
    if "canonical_to_id" not in cluster_map:
        cluster_map["canonical_to_id"] = {}

    # 군집 (씨앗 사전결합 + 점수)
    assignments, merge_log = cluster_nodes(
        nodes, edges, threshold=threshold, ignore_seed=ignore_seed
    )

    # ID 부여
    cluster_info = assign_cluster_ids(nodes, assignments, cluster_map)

    # P2 — 씨앗 검증 + FR 권위 인덱스 + 횡단 모듈 인덱스(DEC-F)
    provenance = compute_provenance(nodes, assignments, cluster_info)
    cluster_map["fr_index"] = build_fr_index(nodes, assignments, cluster_info)
    cluster_map["module_index"] = build_module_index(nodes, edges, assignments, cluster_info)

    # graph 어노테이션 (+provenance)
    annotated = annotate_graph(graph, assignments, cluster_info, provenance)

    # 저장
    _save_json(output_path, annotated)
    if cluster_map_path:
        _save_json(cluster_map_path, cluster_map)

    # P1 — 영속 트랙 마커 기록 (Track A / dossier 모델을 기계가독 SSoT 로 박음).
    # fanout fail-closed 가드·plan-audit·lc 가 이 파일을 읽어 트랙을 강제한다.
    write_project_mode(output_path.parent, len(cluster_info))

    return annotated, cluster_info, merge_log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cluster_identify",
        description="graph.json policy 노드에 capability/cluster_id 부여 (Phase 5A)",
    )
    parser.add_argument("--graph", type=Path, required=True, help="입력 graph.json")
    parser.add_argument("--output", type=Path, required=True, help="출력 graph.clustered.json")
    parser.add_argument(
        "--cluster-map",
        type=Path,
        default=None,
        help="안정 매핑 cluster_map.json (재실행 시 동일 ID 보장)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"결합 임계 (default {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="요약 보고서 markdown 출력 경로",
    )
    parser.add_argument(
        "--ignore-seed",
        action="store_true",
        help="요구사항 씨앗(cluster_hint) 무시 — 순수 점수 군집(레버만)",
    )
    args = parser.parse_args(argv)

    if not args.graph.is_file():
        print(f"[cluster_identify] ERROR: graph 파일 없음: {args.graph}", file=sys.stderr)
        return 1

    try:
        annotated, cluster_info, merge_log = identify_clusters(
            args.graph,
            args.output,
            cluster_map_path=args.cluster_map,
            threshold=args.threshold,
            ignore_seed=args.ignore_seed,
        )
    except (ValueError, KeyError) as exc:
        print(f"[cluster_identify] ERROR: {exc}", file=sys.stderr)
        return 2

    if args.summary:
        # annotated 노드에서 provenance 회수 (요약에 씨앗 검증 표기)
        prov = {
            k: n["cluster_provenance"]
            for k, n in annotated.get("graph", {}).get("nodes", {}).items()
            if "cluster_provenance" in n
        }
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(
            make_summary(cluster_info, merge_log, args.threshold, prov),
            encoding="utf-8",
        )

    print(
        f"[cluster_identify] OK: {len(cluster_info)} clusters / "
        f"{len(merge_log)} merge events / threshold {args.threshold} → {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
