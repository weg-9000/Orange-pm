#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse graph.json and MERGE-load its nodes and relationships into Neo4j.

[STANDALONE / OPTIONAL]
    An optional Neo4j loader not invoked by any skill (currently dormant).
    Kept for manual loading only; correct behavior is guaranteed in case it
    is ever invoked.

Usage:
    python graph_to_neo4j.py --product <product_name> [--dry-run]
    python graph_to_neo4j.py --product <product_name> --neo4j-uri bolt://localhost:7687
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


VALID_NODE_TYPES = {"policy", "screen", "reference", "gate"}

EDGE_TYPE_MAP = {
    "inherits_from": "INHERITS_FROM",
    "includes": "INCLUDES",
    "blocks": "BLOCKS",
    "conflicts_with": "CONFLICTS_WITH",
    "verified_by": "VERIFIED_BY",
    "authored_in": "AUTHORED_IN",
    "implements": "IMPLEMENTS",
    "precondition": "PRECONDITION",
}


# ── Argument parsing ───────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="graph.json -> Neo4j MERGE loader script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python graph_to_neo4j.py --product my-product
  python graph_to_neo4j.py --product my-product --dry-run
  python graph_to_neo4j.py --product my-product \\
      --neo4j-uri bolt://db.internal:7687 \\
      --neo4j-user admin
        """,
    )
    p.add_argument("--product", required=True,
                   help="Determines the path PROJECTS/{product}/graph/graph.json")
    p.add_argument("--neo4j-uri", default="bolt://localhost:7687",
                   help="Neo4j Bolt URI (default: bolt://localhost:7687)")
    p.add_argument("--neo4j-user", default="neo4j",
                   help="Neo4j username (default: neo4j)")
    p.add_argument("--neo4j-password", default=None,
                   help="Neo4j password. The NEO4J_PASSWORD env var takes precedence")
    p.add_argument("--dry-run", action="store_true",
                   help="Print only the parse results (node/relationship counts) without loading")
    return p


# ── Load and validate graph.json ────────────────────────────────────────────

def load_graph(product: str) -> dict[str, Any]:
    graph_path = Path("PROJECTS") / product / "graph" / "graph.json"
    if not graph_path.exists():
        print(f"[ERROR] graph.json not found: {graph_path}", file=sys.stderr)
        print(f"        Run /graph-gen {product} first.", file=sys.stderr)
        sys.exit(1)

    try:
        with graph_path.open(encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse graph.json: {e}", file=sys.stderr)
        sys.exit(1)

    # Envelope normalization: accept both the canonical {graph:{nodes,edges}}
    # and the legacy flat {nodes,edges} shape (same pattern as graph_emit.py's
    # raw.get("graph", raw)).
    g = raw.get("graph", raw)

    for key in ("nodes", "edges"):
        if key not in g:
            print(f"[ERROR] graph.json is missing required key '{key}'.", file=sys.stderr)
            sys.exit(1)

    # nodes may be a dict (canonical: {node_id: node}) or a list (legacy) —
    # normalize to a list
    raw_nodes = g["nodes"]
    nodes = list(raw_nodes.values()) if isinstance(raw_nodes, dict) else raw_nodes
    edges = g["edges"]

    invalid = [
        n.get("doc_id") or n.get("screen_id")
        for n in nodes
        if n.get("node_type") not in VALID_NODE_TYPES
    ]
    if invalid:
        print(f"[ERROR] {len(invalid)} node(s) with an invalid node_type: {invalid[:5]}", file=sys.stderr)
        print(f"        Allowed values: {VALID_NODE_TYPES}", file=sys.stderr)
        sys.exit(1)

    return {"nodes": nodes, "edges": edges}


# ── Node/relationship classification ────────────────────────────────────────

def classify_nodes(nodes: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list] = {t: [] for t in VALID_NODE_TYPES}
    for n in nodes:
        ntype = n.get("node_type", "")
        result.setdefault(ntype, []).append(n)
    return result


# ── Neo4j loading ────────────────────────────────────────────────────────────

def get_driver(uri: str, user: str, password: str):
    try:
        from neo4j import GraphDatabase  # type: ignore
    except ImportError:
        print("[ERROR] The neo4j package is missing. Run pip install neo4j.", file=sys.stderr)
        sys.exit(1)

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        return driver
    except Exception as e:
        print(f"[ERROR] Failed to connect to Neo4j: {e}", file=sys.stderr)
        print(f"        URI: {uri}, user: {user}", file=sys.stderr)
        print("        Check that the Neo4j server is running and the connection details are correct.", file=sys.stderr)
        sys.exit(1)


def merge_nodes(session, classified: dict[str, list[dict]]) -> dict[str, int]:
    counts: dict[str, int] = {}

    # Policy nodes
    for node in classified.get("policy", []):
        session.run(
            """
            MERGE (n:Policy {doc_id: $doc_id})
            SET n.title        = $title,
                n.layer        = $layer,
                n.delta_required = $delta_required,
                n.status       = $status,
                n.phase        = $phase
            """,
            doc_id=node.get("doc_id", ""),
            title=node.get("title", ""),
            layer=node.get("layer", ""),
            delta_required=node.get("delta_required", False),
            status=node.get("status", "draft"),
            phase=node.get("phase"),
        )
    counts["Policy"] = len(classified.get("policy", []))

    # Screen nodes
    for node in classified.get("screen", []):
        session.run(
            """
            MERGE (n:Screen {screen_id: $screen_id})
            SET n.title           = $title,
                n.state_count     = $state_count,
                n.component_count = $component_count,
                n.phase           = $phase
            """,
            screen_id=node.get("screen_id", node.get("doc_id", "")),
            title=node.get("title", ""),
            state_count=node.get("state_count", 0),
            component_count=node.get("component_count", 0),
            phase=node.get("phase"),
        )
    counts["Screen"] = len(classified.get("screen", []))

    # Reference nodes
    for node in classified.get("reference", []):
        session.run(
            """
            MERGE (n:Reference {doc_id: $doc_id})
            SET n.title       = $title,
                n.layer       = $layer,
                n.source_path = $source_path
            """,
            doc_id=node.get("doc_id", ""),
            title=node.get("title", ""),
            layer=node.get("layer", ""),
            source_path=node.get("source_path", ""),
        )
    counts["Reference"] = len(classified.get("reference", []))

    # Gate nodes
    for node in classified.get("gate", []):
        session.run(
            """
            MERGE (n:Gate {name: $name})
            SET n.phase      = $phase,
                n.conditions = $conditions
            """,
            name=node.get("name", node.get("doc_id", "")),
            phase=node.get("phase"),
            conditions=json.dumps(node.get("conditions", []), ensure_ascii=False),
        )
    counts["Gate"] = len(classified.get("gate", []))

    return counts


def merge_edges(session, edges: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}

    for edge in edges:
        raw_type = edge.get("type", "")
        rel_type = EDGE_TYPE_MAP.get(raw_type, raw_type.upper())
        source_id = edge.get("source", "")
        target_id = edge.get("target", "")

        cypher = f"""
            MATCH (a {{doc_id: $src}})
            MATCH (b {{doc_id: $tgt}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r.edge_id        = $edge_id,
                r.source_section = $source_section,
                r.target_section = $target_section
        """
        session.run(
            cypher,
            src=source_id,
            tgt=target_id,
            edge_id=edge.get("id", ""),
            source_section=edge.get("source_section", ""),
            target_section=edge.get("target_section", ""),
        )
        counts[rel_type] = counts.get(rel_type, 0) + 1

    return counts


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = build_parser().parse_args()

    password = os.environ.get("NEO4J_PASSWORD") or args.neo4j_password
    if not password and not args.dry_run:
        print("[ERROR] No Neo4j password provided.", file=sys.stderr)
        print("        Use the NEO4J_PASSWORD env var or the --neo4j-password argument.", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Loading graph.json: PROJECTS/{args.product}/graph/graph.json")
    data = load_graph(args.product)

    nodes: list[dict] = data["nodes"]
    edges: list[dict] = data["edges"]
    classified = classify_nodes(nodes)

    print(f"[INFO] Parsed {len(nodes)} node(s), {len(edges)} relationship(s)")
    for ntype, lst in classified.items():
        if lst:
            print(f"       {ntype}: {len(lst)}")

    if args.dry_run:
        print("\n[DRY-RUN] Exiting without loading anything.")
        edge_type_counts: dict[str, int] = {}
        for e in edges:
            t = EDGE_TYPE_MAP.get(e.get("type", ""), e.get("type", "").upper())
            edge_type_counts[t] = edge_type_counts.get(t, 0) + 1
        print("[DRY-RUN] By relationship type:")
        for rtype, cnt in edge_type_counts.items():
            print(f"       {rtype}: {cnt}")
        return

    start = time.time()
    driver = get_driver(args.neo4j_uri, args.neo4j_user, password)

    try:
        with driver.session() as session:
            print("[INFO] Starting Neo4j node MERGE...")
            node_counts = merge_nodes(session, classified)

            print("[INFO] Starting Neo4j relationship MERGE...")
            edge_counts = merge_edges(session, edges)
    finally:
        driver.close()

    elapsed = time.time() - start
    print(f"\n[DONE] Elapsed time: {elapsed:.1f}s")
    print("[DONE] Nodes loaded:")
    for label, cnt in node_counts.items():
        print(f"       :{label} {cnt}")
    print("[DONE] Relationships loaded:")
    for rtype, cnt in edge_counts.items():
        print(f"       [{rtype}] {cnt}")


if __name__ == "__main__":
    main()
