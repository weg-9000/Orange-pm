#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vector_emit — Neo4j vector index status → normalized JSON (viz governance, Phase 6).

Shows what's actually loaded into Neo4j as :Chunk (embedded documents):
  - vector index name/dimensions
  - total chunk count
  - chunk count per document (doc_id/prefix/layer/service)
  - aggregation by PREFIX

Read-only. When Neo4j is unavailable (driver/password/connection failure),
gracefully degrades to status="unavailable" — safe in infra/offline/CI environments.

    python vector_emit.py --emit-json
Output: {kind:"vector-index", status, indexName, dimensions, totalChunks, docs[], byPrefix[], version}
Environment: NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
"""
from __future__ import annotations

import os
import sys

import _emit_common as C


def _connect():
    """Returns (driver, None) or (None, reason). Returns a reason string instead of raising on failure."""
    if not os.environ.get("NEO4J_PASSWORD"):
        return None, "NEO4J_PASSWORD not set"
    try:
        from neo4j import GraphDatabase
    except Exception:
        return None, "neo4j driver not installed (pip install neo4j)"
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    try:
        d = GraphDatabase.driver(uri, auth=(user, os.environ["NEO4J_PASSWORD"]))
        d.verify_connectivity()
        return d, None
    except Exception as e:
        return None, f"connection failed: {e}"


def query_stats(session) -> dict:
    """Collects index/chunk statistics from the session (queries are best-effort)."""
    index_name = None
    dimensions = None
    try:
        for r in session.run("SHOW VECTOR INDEXES YIELD name, options RETURN name, options"):
            index_name = r["name"]
            opts = r["options"] or {}
            cfg = opts.get("indexConfig") or {}
            dimensions = cfg.get("vector.dimensions")
            break
    except Exception:
        pass  # older version/permissions, etc. — fall back to stats without index metadata

    docs: list[dict] = []
    total = 0
    for r in session.run(
        "MATCH (c:Chunk) "
        "RETURN coalesce(c.prefix,'') AS prefix, coalesce(c.layer,'') AS layer, "
        "coalesce(c.doc_id,'') AS docId, coalesce(c.service,'') AS service, count(c) AS chunks "
        "ORDER BY prefix, layer, docId"
    ):
        chunks = int(r["chunks"])
        docs.append({"prefix": r["prefix"], "layer": r["layer"], "docId": r["docId"],
                     "service": r["service"], "chunks": chunks})
        total += chunks

    by_prefix: dict[str, dict] = {}
    for d in docs:
        key = d["prefix"] or "(none)"
        agg = by_prefix.setdefault(key, {"prefix": key, "chunks": 0, "docs": 0})
        agg["chunks"] += d["chunks"]
        agg["docs"] += 1

    return {
        "indexName": index_name,
        "dimensions": dimensions,
        "totalChunks": total,
        "docs": docs,
        "byPrefix": list(by_prefix.values()),
    }


def transform() -> dict:
    driver, reason = _connect()
    if driver is None:
        return {"kind": "vector-index", "status": "unavailable", "reason": reason,
                "indexName": None, "dimensions": None, "totalChunks": 0,
                "docs": [], "byPrefix": []}
    try:
        with driver.session() as session:
            stats = query_stats(session)
    except Exception as e:
        return {"kind": "vector-index", "status": "error", "reason": str(e),
                "totalChunks": 0, "docs": [], "byPrefix": []}
    finally:
        driver.close()
    return {"kind": "vector-index", "status": "ok", **stats}


def main() -> int:
    args = C.make_parser("vector-index").parse_args()
    if args.from_fixture:
        return C.emit(C.load_fixture(args.from_fixture))
    return C.emit(transform())


if __name__ == "__main__":
    sys.exit(main())
