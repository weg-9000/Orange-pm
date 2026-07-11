#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cluster Identification (Phase 5A).

Assigns capability + cluster_id to policy nodes in graph.json.
Clusters are computed from publication-map.md §1's 4 axes + D2/D3 alignment,
combined into a 5-axis weighted score (≥0.55 → merge), and a stable ID
mapping (cluster_map.json) guarantees identical results on rerun.

When to run:
    Right after /graph-gen, or as a pre-step of /fanout --cluster-mode.

Input:
    PROJECTS/{product}/graph/graph.json (policy nodes + edges)
    PROJECTS/{product}/inputs/requirements.md (optional — extracts cluster hints from FR metadata)

Seed — P2 (docs/fr-cluster-alignment.md):
    Requirement tags (capability / cluster_hint) are pre-merged as the initial
    union-find partition (seed). Scoring (5-axis · threshold) merges further on
    top of that, so the tuning lever is preserved (seed-not-lock).
    Nodes with cluster_lock: true are excluded from score-based merging (locks
    the seed boundary). Use --ignore-seed for pure score-based clustering.

Output:
    PROJECTS/{product}/graph/graph.clustered.json
        — each policy node gets capability / cluster_id / cluster_name + cluster_provenance added
    PROJECTS/{product}/graph/cluster_map.json
        — stable ID mapping (canonical_to_id) + FR authority index (fr_index: FR→{capability,cluster_id})
    PROJECTS/{product}/reports/cluster-summary.md
        — summary for PM review (cluster count per capability, merge scores, seed validation kept/overridden)

CLI:
    python cluster_identify.py --graph PROJECTS/{p}/graph/graph.json \
        --output PROJECTS/{p}/graph/graph.clustered.json \
        [--cluster-map PROJECTS/{p}/graph/cluster_map.json] \
        [--threshold 0.55]                  # merge threshold (publication-map.md §1)
        [--summary PROJECTS/{p}/reports/cluster-summary.md]

Exit codes: 0 success / 1 input error / 2 graph structure error
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


# 5-axis weights (publication-map.md §1)
WEIGHTS = {
    "decision_domain": 0.30,   # policy_axis match
    "domain_object":   0.20,   # shared data objects
    "screen_surface":  0.20,   # primary_screen match
    "dependency_cone": 0.15,   # inherits_from 50%+ overlap
    "publication_fit": 0.15,   # D2/D3 chapter alignment (heuristic)
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
    """Records the persistent track marker graph/project-mode.json (fix-plan-track-routing P1).

    Running cluster_identify means this project uses the cluster(dossier)
    model = Track A. This is stamped as a machine-readable SSoT so fanout's
    fail-closed guard (_detect_cluster_signals), plan-audit, and lc read the
    track instead of inferring it.

    If an existing file is present, decided_by(DEC) / section_wo_retired /
    publication_mode set by the PM are preserved, and only the count/timestamp
    are updated.

    publication_mode (fix-plan-dossier-publish-split):
        "dossier-page"      — 1 feature spec = 1 Confluence page (default)
        "split-deliverable" — dossier §1/§2 are transposed and published as
                              separate D2 policy doc / D3 screen design spec
    Falls back to existing behavior (dossier-page) when no value is present —
    guarantees no change for existing projects like dbaas. The split
    transition is recorded by /fanout --publication-mode.
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


# ── 4+1-axis score computation ─────────────────────────────────────────────
def _set_overlap(a: list[str], b: list[str]) -> float:
    """Jaccard similarity — intersection ratio of two sets."""
    sa, sb = set(a or []), set(b or [])
    if not sa and not sb:
        return 0.0
    union = sa | sb
    return len(sa & sb) / len(union) if union else 0.0


def _score_decision_domain(n1: dict, n2: dict) -> float:
    """policy_axis overlap ratio."""
    return _set_overlap(n1.get("policy_axis") or [], n2.get("policy_axis") or [])


def _score_domain_object(n1: dict, n2: dict) -> float:
    """domain_object overlap ratio."""
    return _set_overlap(n1.get("domain_object") or [], n2.get("domain_object") or [])


def _score_screen_surface(n1: dict, n2: dict) -> float:
    """primary_screen match — single-value comparison (1.0 or 0.0)."""
    ps1, ps2 = n1.get("primary_screen"), n2.get("primary_screen")
    if ps1 and ps2 and ps1 == ps2:
        return 1.0
    return 0.0


def _score_dependency_cone(
    n1_key: str, n2_key: str, dep_map: dict[str, set[str]]
) -> float:
    """Jaccard of inherits_from dependency sets. 50%+ overlap is a merge signal."""
    deps1 = dep_map.get(n1_key, set())
    deps2 = dep_map.get(n2_key, set())
    return _set_overlap(list(deps1), list(deps2))


def _score_publication_fit(n1: dict, n2: dict) -> float:
    """D2/D3 chapter alignment — heuristic.

    If two nodes share the same deliverable_targets (e.g. both D2 + D3) and
    their sections are named similarly, it's natural for them to be grouped
    into the same chapter.
    """
    targets1 = set(n1.get("deliverable_targets") or ["D2"])
    targets2 = set(n2.get("deliverable_targets") or ["D2"])
    if not targets1 & targets2:
        return 0.0
    # shared deliverable ratio
    return len(targets1 & targets2) / len(targets1 | targets2)


def cluster_score(
    n1_key: str, n1: dict,
    n2_key: str, n2: dict,
    dep_map: dict[str, set[str]],
) -> tuple[float, dict[str, float]]:
    """Merge score between two nodes (0-1) + per-axis breakdown."""
    breakdown = {
        "decision_domain": _score_decision_domain(n1, n2) * WEIGHTS["decision_domain"],
        "domain_object":   _score_domain_object(n1, n2) * WEIGHTS["domain_object"],
        "screen_surface":  _score_screen_surface(n1, n2) * WEIGHTS["screen_surface"],
        "dependency_cone": _score_dependency_cone(n1_key, n2_key, dep_map) * WEIGHTS["dependency_cone"],
        "publication_fit": _score_publication_fit(n1, n2) * WEIGHTS["publication_fit"],
    }
    return sum(breakdown.values()), breakdown


# ── Clustering algorithm (score-based union-find) ───────────────────────────
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
            # smaller ID becomes the parent (determinism)
            if ra < rb:
                self.parent[rb] = ra
            else:
                self.parent[ra] = rb


def _build_dep_map(edges: list[dict]) -> dict[str, set[str]]:
    """node → set of directly dependent nodes (inherits_from)."""
    dep_map: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e.get("type") == "inherits_from":
            dep_map[e["source"]].add(e["target"])
    return dep_map


# ── Seed helpers — use requirement tags as cluster seeds (P2) ───────────────
def _seed_capability(node: dict) -> str | None:
    """Node's seed capability (requirement tag). Prefers seed_capability, falls back to capability."""
    cap = node.get("seed_capability") or node.get("capability")
    return str(cap) if cap else None


def _cluster_hint(node: dict) -> str | None:
    """Node's cluster_hint (seed membership key). None if empty."""
    h = node.get("cluster_hint")
    return str(h).strip() if h and str(h).strip() else None


def _is_locked(node: dict) -> bool:
    """cluster_lock opt-in — excludes from score-based cross-cluster merging (locks the seed boundary)."""
    return bool(node.get("cluster_lock"))


def cluster_nodes(
    nodes: dict[str, dict],
    edges: list[dict],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    ignore_seed: bool = False,
) -> tuple[dict[str, str], list[tuple[str, str, float, dict]]]:
    """Cluster policy nodes.

    P2 (seed-not-lock): nodes sharing the same (capability, cluster_hint) are
    pre-merged as the initial union-find partition (seed). Scoring (5-axis ·
    threshold) merges further on top of that, so the tuning lever is fully
    preserved. Nodes with cluster_lock are excluded from score-based merging
    (locks the seed boundary). If ignore_seed=True, clustering is purely
    score-based (seeds ignored).

    Returns:
        - assignments: node_key → cluster_canonical_id (union-find root)
        - merge_log: [(node_a, node_b, score, breakdown)] — merges above threshold
    """
    policy_keys = sorted(
        k for k, n in nodes.items() if n.get("node_type") != "screen"
    )
    if not policy_keys:
        return {}, []

    dep_map = _build_dep_map(edges)
    uf = _UnionFind(policy_keys)
    merge_log: list[tuple[str, str, float, dict]] = []

    # P2 — seed pre-merge: union nodes sharing the same (capability, cluster_hint) upfront
    if not ignore_seed:
        by_seed: dict[tuple[str | None, str], list[str]] = defaultdict(list)
        for k in policy_keys:
            hint = _cluster_hint(nodes[k])
            if hint:
                by_seed[(_seed_capability(nodes[k]), hint)].append(k)
        for group in by_seed.values():
            for other in group[1:]:
                uf.union(group[0], other)

    # Score-based merging (locked nodes excluded from cross-cluster merges)
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


# ── ID assignment (stable mapping) ──────────────────────────────────────────
def _capability_of(node: dict, default: str = "Default") -> str:
    """Extract node's capability — from metadata or default."""
    cap = node.get("capability") or default
    # normalize: alnum only, strip whitespace
    return "".join(c for c in str(cap) if c.isalnum() or c == "-") or default


def _capability_prefix(capability: str, used: set[str]) -> str:
    """capability → cluster_id prefix (2 uppercase letters, avoids collisions with used).

    Strategy (stability + uniqueness):
      1. First 2 letters (e.g. Provisioning → PR)
      2. On collision, 1st + 3rd letter (Provisioning → PO)
      3. On collision, 1st + first uppercase consonant (Provisioning → PV — Pr-oV-isioning)
      4. On collision, 1st + last letter (Provisioning → PG)
      5. On persistent collision, hash-based fallback (e.g. P0, P1, ...)
    """
    letters = [c.upper() for c in capability if c.isalpha()] or ["X", "X"]

    candidates = []
    # 1
    if len(letters) >= 2:
        candidates.append(letters[0] + letters[1])
    # 2
    if len(letters) >= 3:
        candidates.append(letters[0] + letters[2])
    # 3 — consonant (excluding vowels)
    vowels = set("AEIOU")
    for c in letters[1:]:
        if c not in vowels:
            cand = letters[0] + c
            if cand not in candidates:
                candidates.append(cand)
            break
    # 4 — last letter
    if len(letters) >= 1:
        candidates.append(letters[0] + letters[-1])

    for c in candidates:
        if c not in used:
            return c

    # 5 — fallback: first letter + digit
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
    """Map canonical id → (capability, cluster_id, cluster_name).

    Prefers cluster_map (stable mapping) — keeps the same cluster_id across reruns.
    """
    # collect capability + members per canonical
    by_canonical: dict[str, list[str]] = defaultdict(list)
    for node_key, canonical in assignments.items():
        by_canonical[canonical].append(node_key)

    # cluster sequence per capability (stable mapping takes priority)
    cap_to_seq: dict[str, int] = defaultdict(int)
    persistent_map = cluster_map.get("canonical_to_id", {})
    # capability → prefix mapping is also persistent (stability)
    capability_prefix_map: dict[str, str] = cluster_map.get("capability_to_prefix", {})
    used_prefixes: set[str] = set(capability_prefix_map.values())

    # restore cap_to_seq — last sequence number per capability from existing mapping
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

    # ensure stability: process after sorting canonicals
    for canonical in sorted(by_canonical.keys()):
        members = sorted(by_canonical[canonical])
        # determine capability — most common among members' capabilities (simple)
        caps = [_capability_of(nodes[k]) for k in members]
        capability = max(set(caps), key=caps.count) if caps else "Default"

        # unique prefix per capability (stable mapping takes priority)
        if capability in capability_prefix_map:
            prefix = capability_prefix_map[capability]
        else:
            prefix = _capability_prefix(capability, used_prefixes)
            capability_prefix_map[capability] = prefix
            used_prefixes.add(prefix)

        # determine cluster_id — stable mapping takes priority
        if canonical in persistent_map:
            cluster_id = persistent_map[canonical]
        else:
            cap_to_seq[capability] += 1
            cluster_id = f"{prefix}-{cap_to_seq[capability]:02d}"
            persistent_map[canonical] = cluster_id

        # determine cluster_name — based on first member's sections or node_name
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


# ── Seed validation (provenance) + FR index (P2) ────────────────────────────
def compute_provenance(
    nodes: dict[str, dict],
    assignments: dict[str, str],
    cluster_info: dict[str, dict],
) -> dict[str, str]:
    """Per-node seed validation result.

    - "computed"          : no seed (capability/cluster_hint) — purely computed cluster
    - "seed_kept"         : final cluster capability == seed capability
    - "seed_overridden:…" : absorbed into a different capability cluster by score merge (reason)
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
    """FR → {capability, cluster_id} authority mapping (stored in cluster_map.json).

    Reverse-indexes each node's fr_refs by cluster membership. Used as the
    cluster_ref injection key when D1 publication renders per-capability FR
    groupings (derived views) (DEC-A/C).
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


# Edge types treated as cross-cutting module references (graph-schema.json edges.type)
_MODULE_EDGE_TYPES = {"inherits_from", "includes", "references"}


def build_module_index(
    nodes: dict[str, dict],
    edges: list[dict],
    assignments: dict[str, str],
    cluster_info: dict[str, dict],
) -> dict[str, list[dict]]:
    """Cross-cutting module → reverse index of clusters referencing it (DEC-F).

    Concerns shared across multiple capabilities — like an email/SMS sending
    module — aren't split inline per capability; they live in one place
    (a module / dedicated capability) that each feature references. Reverse-
    indexing those references (edges) produces a **cross-cutting trigger
    matrix** showing "which features use this module" all at once (input for
    the publication P3 derived view).

    Module determination: target is not a clustering-target policy node
    (reference/external), or node_type==reference, or role=='cross-cutting'.
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
        info = node_info.get(src)  # only when source is a clustered feature node (feature→module direction)
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
    # determinism: sort by cluster_id
    return {
        k: sorted(v, key=lambda r: (r["capability"], r["cluster_id"], r["source"]))
        for k, v in sorted(module_index.items())
    }


# ── Node metadata annotation ────────────────────────────────────────────────
def annotate_graph(
    graph: dict,
    assignments: dict[str, str],
    cluster_info: dict[str, dict],
    provenance: dict[str, str] | None = None,
) -> dict:
    """Attach cluster metadata (+ seed provenance) to each policy node in the graph."""
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


# ── Summary report ───────────────────────────────────────────────────────────
def make_summary(
    cluster_info: dict[str, dict],
    merge_log: list[tuple[str, str, float, dict]],
    threshold: float,
    provenance: dict[str, str] | None = None,
) -> str:
    """Markdown summary for PM review."""
    lines = ["# Cluster Identification Summary\n"]
    lines.append(f"**Threshold**: merge score ≥ {threshold} (publication-map.md §1)\n")

    # P2 — seed validation summary (seed_kept / seed_overridden)
    if provenance:
        kept = sum(1 for v in provenance.values() if v == "seed_kept")
        overridden = {k: v for k, v in provenance.items() if v.startswith("seed_overridden")}
        computed = sum(1 for v in provenance.values() if v == "computed")
        lines.append(
            f"**Seed validation**: seed_kept {kept} · seed_overridden {len(overridden)} · computed {computed}\n"
        )
        if overridden:
            lines.append("| Node | Seed Override Reason |")
            lines.append("|---|---|")
            for k in sorted(overridden):
                lines.append(f"| {k} | {overridden[k].split(':', 1)[1].strip()} |")
            lines.append("")

    lines.append(f"**Cluster Count per Capability**:\n")

    cap_clusters: dict[str, list[dict]] = defaultdict(list)
    for canonical, info in cluster_info.items():
        cap_clusters[info["capability"]].append(info)

    lines.append("| Capability | Cluster Count | Cluster IDs | Total Nodes |")
    lines.append("|---|---|---|---|")
    for cap in sorted(cap_clusters.keys()):
        clusters = cap_clusters[cap]
        ids = ", ".join(c["cluster_id"] for c in clusters)
        total = sum(len(c["members"]) for c in clusters)
        lines.append(f"| {cap} | {len(clusters)} | {ids} | {total} |")

    lines.append("\n## Merge Events (pairs above threshold)\n")
    if not merge_log:
        lines.append("- No merge events (all nodes are independent clusters).")
    else:
        lines.append("| Node A | Node B | Total Score | Domain | Object | Screen | Dependency | Pub. Fit |")
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

    lines.append("\n## Recommended Review")
    lines.append("- Pairs scoring 0.55–0.70 (borderline merges) should get PM review")
    lines.append("- Review capability labeling for clusters with only 1 node")
    lines.append("- Next: generate WOs via /fanout --cluster-mode")
    lines.append(
        "  (track=A is recorded in graph/project-mode.json — legacy /fanout is "
        "fail-closed blocked and can only be bypassed with --force-legacy)"
    )

    return "\n".join(lines) + "\n"


# ── Main ─────────────────────────────────────────────────────────────────────
def identify_clusters(
    graph_path: Path,
    output_path: Path,
    *,
    cluster_map_path: Path | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    ignore_seed: bool = False,
) -> tuple[dict, dict[str, dict], list]:
    """Load graph.json → identify clusters → annotate → save."""
    graph = _load_json(graph_path)
    nodes = graph.get("graph", {}).get("nodes", {})
    edges = graph.get("graph", {}).get("edges", [])

    if not nodes:
        raise ValueError(f"graph has no nodes: {graph_path}")

    # load cluster_map (stable mapping)
    cluster_map: dict = {}
    if cluster_map_path and cluster_map_path.is_file():
        cluster_map = _load_json(cluster_map_path)
    if "canonical_to_id" not in cluster_map:
        cluster_map["canonical_to_id"] = {}

    # cluster (seed pre-merge + score)
    assignments, merge_log = cluster_nodes(
        nodes, edges, threshold=threshold, ignore_seed=ignore_seed
    )

    # assign IDs
    cluster_info = assign_cluster_ids(nodes, assignments, cluster_map)

    # P2 — seed validation + FR authority index + cross-cutting module index (DEC-F)
    provenance = compute_provenance(nodes, assignments, cluster_info)
    cluster_map["fr_index"] = build_fr_index(nodes, assignments, cluster_info)
    cluster_map["module_index"] = build_module_index(nodes, edges, assignments, cluster_info)

    # annotate graph (+provenance)
    annotated = annotate_graph(graph, assignments, cluster_info, provenance)

    # save
    _save_json(output_path, annotated)
    if cluster_map_path:
        _save_json(cluster_map_path, cluster_map)

    # P1 — record persistent track marker (stamps Track A / dossier model as machine-readable SSoT).
    # fanout's fail-closed guard, plan-audit, and lc read this file to enforce the track.
    write_project_mode(output_path.parent, len(cluster_info))

    return annotated, cluster_info, merge_log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cluster_identify",
        description="Assign capability/cluster_id to policy nodes in graph.json (Phase 5A)",
    )
    parser.add_argument("--graph", type=Path, required=True, help="Input graph.json")
    parser.add_argument("--output", type=Path, required=True, help="Output graph.clustered.json")
    parser.add_argument(
        "--cluster-map",
        type=Path,
        default=None,
        help="Stable mapping cluster_map.json (guarantees same IDs on rerun)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Merge threshold (default {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="Output path for markdown summary report",
    )
    parser.add_argument(
        "--ignore-seed",
        action="store_true",
        help="Ignore requirement seeds (cluster_hint) — pure score-based clustering (lever only)",
    )
    args = parser.parse_args(argv)

    if not args.graph.is_file():
        print(f"[cluster_identify] ERROR: graph file not found: {args.graph}", file=sys.stderr)
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
        # retrieve provenance from annotated nodes (for seed validation display in summary)
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
