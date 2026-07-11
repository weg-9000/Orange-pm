#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cluster_emit — graph/cluster_map.json → normalized cluster-map contract (FR<->cluster B2/B3).

Converts the cluster_map.json (fr_index/module_index) produced by cluster_identify
into the viz contract.
- capabilities: derived view grouping fr_index by capability -> cluster -> FR (B2 traceability)
- modules:      module_index (cross-cutting concerns) -> per-module referenced cluster matrix (B3)
Read-only. Emits an empty skeleton if cluster_map is missing/corrupt (graceful, 01-data-contract).
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import _emit_common as C


def _fr_key(fr: str) -> list:
    """FR natural sort key (FR-2 < FR-10)."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(fr))]


def transform_cluster_map(cmap: dict, product: str = "") -> dict:
    """cluster_map.json → cluster-map contract (capabilities + modules). Deterministic sort."""
    fr_index = cmap.get("fr_index") if isinstance(cmap, dict) else None
    module_index = cmap.get("module_index") if isinstance(cmap, dict) else None
    fr_index = fr_index if isinstance(fr_index, dict) else {}
    module_index = module_index if isinstance(module_index, dict) else {}

    # capabilities: capability → {clusterId → [FR...]}
    cap_map: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for fr, info in fr_index.items():
        if not isinstance(info, dict):
            continue
        cap = str(info.get("capability") or "(unspecified)")
        cid = str(info.get("cluster_id") or "")
        cap_map[cap][cid].append(str(fr))
    capabilities = [
        {
            "capability": cap,
            "clusters": [
                {"clusterId": cid, "frs": sorted(frs, key=_fr_key)}
                for cid, frs in sorted(clusters.items())
            ],
        }
        for cap, clusters in sorted(cap_map.items())
    ]

    # modules: moduleId → refs[] (cross-cutting matrix)
    modules = []
    for mid, refs in sorted(module_index.items()):
        rows = [
            {
                "capability": str(r.get("capability") or ""),
                "clusterId": str(r.get("cluster_id") or ""),
                "source": str(r.get("source") or ""),
                "via": str(r.get("via") or ""),
            }
            for r in (refs or [])
            if isinstance(r, dict)
        ]
        modules.append({"moduleId": str(mid), "refs": rows})

    return {
        "version": "",
        "product": product,
        "kind": "cluster-map",
        "capabilities": capabilities,
        "modules": modules,
    }


def _empty(product: str) -> dict:
    return {"version": "", "product": product, "kind": "cluster-map", "capabilities": [], "modules": []}


def main(argv: list[str]) -> int:
    args = C.make_parser("cluster-map").parse_args(argv)
    if args.from_fixture:
        return C.emit(C.load_fixture(args.from_fixture))
    if not (args.hub_root and args.product):
        sys.stderr.write("--hub-root, --product required\n")
        return 2
    path = C.product_dir(args.hub_root, args.product) / "graph" / "cluster_map.json"
    if not path.is_file():
        return C.emit(_empty(args.product))
    try:
        cmap = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return C.emit(_empty(args.product))
    return C.emit(transform_cluster_map(cmap, args.product))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
