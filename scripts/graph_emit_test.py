#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graph_emit unit tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import graph_emit as M  # noqa: E402

RAW = {
    "graph": {
        "metadata": {"prefix": "G2", "product_code": "demo"},
        "nodes": {
            "G2-B-002": {"doc_id": "G2-B-002", "layer": "B", "node_type": "reference",
                         "title": "Common", "role": "core-entity", "status": "Approved",
                         "weight": 1.3, "delta_required": False,
                         "inherits_from": ["G2-A-001"], "sections": {"1.1": {}, "1.2": {}}},
            "G2-C-X": {"doc_id": "G2-C-X", "layer": "C", "node_type": "work",
                       "title": "Delta", "status": "Draft", "weight": 0.3,
                       "delta_required": True, "is_work_order_target": True, "sections": {}},
        },
        "edges": [
            {"source": "G2-C-X", "target": "G2-B-002", "type": "inherits_from", "cross_layer": True},
            {"source": "G2-C-X", "target": "G2-B-002", "type": "billing-target", "cross_layer": True},
            {"source": "G2-C-X", "target": "G2-B-002", "type": "term-standard"},
        ],
    }
}


def test_node_field_mapping():
    out = M.transform_graph(RAW, "demo")
    assert out["kind"] == "graph"
    assert out["metadata"]["total_nodes"] == 2
    n = {x["id"]: x for x in out["nodes"]}
    assert n["G2-B-002"]["nodeType"] == "reference"
    assert n["G2-B-002"]["sectionCount"] == 2          # sections dict len
    assert n["G2-C-X"]["deltaRequired"] is True
    assert n["G2-C-X"]["isWorkOrderTarget"] is True


def test_edge_style_rules():
    out = M.transform_graph(RAW, "demo")
    styles = [e["style"] for e in out["edges"]]
    assert styles == ["solid", "danger", "dashed"]      # inherits / billing-target / *-standard
    assert out["edges"][0]["crossLayer"] is True
    assert out["edges"][0]["id"] == "E-001"             # auto-numbered


def test_accepts_flat_graph():
    flat = RAW["graph"]
    out = M.transform_graph(flat, "demo")
    assert out["metadata"]["total_nodes"] == 2


# nodes with cluster metadata attached by cluster_identify.py mixed with plain nodes
RAW_CLUSTER = {
    "graph": {
        "metadata": {"prefix": "G3", "product_code": "demo"},
        "nodes": {
            "G3-B-001": {"doc_id": "G3-B-001", "layer": "B", "node_type": "reference",
                         "title": "Clustered", "status": "Approved",
                         "capability": "billing", "cluster_id": "C-01",
                         "cluster_name": "Billing", "cluster_provenance": "seed_kept",
                         "sections": {}},
            "G3-B-002": {"doc_id": "G3-B-002", "layer": "B", "node_type": "reference",
                         "title": "Unclustered", "status": "Draft", "sections": {}},
        },
        "edges": [],
    }
}


def test_cluster_metadata_passthrough():
    out = M.transform_graph(RAW_CLUSTER, "demo")
    n = {x["id"]: x for x in out["nodes"]}
    c = n["G3-B-001"]
    assert c["capability"] == "billing"
    assert c["clusterId"] == "C-01"
    assert c["clusterName"] == "Billing"
    assert c["clusterProvenance"] == "seed_kept"


def test_cluster_metadata_omitted_when_absent():
    out = M.transform_graph(RAW_CLUSTER, "demo")
    n = {x["id"]: x for x in out["nodes"]}
    plain = n["G3-B-002"]
    # back-compat: when cluster fields are absent they do not appear in the contract (no empty strings)
    assert "capability" not in plain
    assert "clusterId" not in plain
    assert "clusterName" not in plain
    assert "clusterProvenance" not in plain
    # existing node fields are still emitted
    assert plain["nodeType"] == "reference"
    assert plain["status"] == "Draft"


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
