#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graph_emit — graph.json(raw schema) → 정규화 graph 계약 (01-data-contract §1)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import _emit_common as C

# 엣지 type → 시각 style (계약 §1 고정 규칙)
_STYLE = {
    "inherits_from": "solid",
    "includes": "solid-thick",
    "과금대상": "danger",
}


def _edge_style(etype: str) -> str:
    # inherits_from→solid · includes→solid-thick · 과금대상→danger · 그 외(references/*기준)→dashed (계약 §1)
    return _STYLE.get(etype, "dashed")


def transform_graph(raw: dict, product: str = "") -> dict:
    """raw graph.json → 계약. raw 는 {graph:{...}} 또는 평면 모두 허용."""
    g = raw.get("graph", raw)
    meta = g.get("metadata", {})
    raw_nodes = g.get("nodes", {})
    items = raw_nodes.items() if isinstance(raw_nodes, dict) else (
        (n.get("doc_id", ""), n) for n in raw_nodes)

    nodes = []
    for nid, n in items:
        node = {
            "id": n.get("doc_id", nid),
            "layer": n.get("layer", ""),
            "nodeType": n.get("node_type", "reference"),
            "title": n.get("title", ""),
            "role": n.get("role", "unknown"),
            "status": n.get("status", "Draft"),
            "weight": n.get("weight", 0),
            "isWorkOrderTarget": bool(n.get("is_work_order_target", False)),
            "deltaRequired": bool(n.get("delta_required", False)),
            "confluencePageId": n.get("confluence_page_id"),
            "inheritsFrom": n.get("inherits_from", []),
            "summary": n.get("summary", ""),
            "sectionCount": len(n.get("sections", {}) or {}),
        }
        # cluster_identify.py 가 붙인 클러스터 메타데이터 — 있을 때만 통과 (back-compat)
        for raw_key, contract_key in (
            ("capability", "capability"),
            ("cluster_id", "clusterId"),
            ("cluster_name", "clusterName"),
            ("cluster_provenance", "clusterProvenance"),
        ):
            if raw_key in n:
                node[contract_key] = n[raw_key]
        nodes.append(node)

    edges = []
    for i, e in enumerate(g.get("edges", []), start=1):
        etype = e.get("type", "references")
        edges.append({
            "id": e.get("id", f"E-{i:03d}"),
            "source": e.get("source", ""),
            "sourceSection": e.get("source_section", ""),
            "target": e.get("target", ""),
            "targetSection": e.get("target_section", ""),
            "type": etype,
            "crossLayer": bool(e.get("cross_layer", False)),
            "description": e.get("description", ""),
            "style": _edge_style(etype),
        })

    return {
        "version": "",
        "product": meta.get("product_code", product) or product,
        "kind": "graph",
        "metadata": {
            "prefix": meta.get("prefix", ""),
            "total_nodes": len(nodes),
            "total_edges": len(edges),
        },
        "nodes": nodes,
        "edges": edges,
    }


def main(argv: list[str]) -> int:
    args = C.make_parser("graph").parse_args(argv)
    if args.from_fixture:
        return C.emit(C.load_fixture(args.from_fixture))
    if not (args.hub_root and args.product):
        sys.stderr.write("--hub-root, --product 필요\n")
        return 2
    path = C.product_dir(args.hub_root, args.product) / "graph" / "graph.json"
    if not path.exists():
        sys.stderr.write(f"graph.json 없음: {path}\n")
        return C.emit({"version": "empty", "product": args.product, "kind": "graph",
                       "metadata": {}, "nodes": [], "edges": []}) or 1
    raw = json.loads(path.read_text(encoding="utf-8"))
    return C.emit(transform_graph(raw, args.product))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
