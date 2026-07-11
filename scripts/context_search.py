#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tier 3 context search — L3 vector + graceful degrade (multi-tenant SaaS Phase 3).

Purpose:
    Cross-PREFIX semantic similarity search ("how did the private-sector
    tenant handle a similar policy?"). Uses vector search if a Neo4j vector
    index exists, otherwise **auto-degrades to cache-index keyword search
    (graceful degrade)** -> works and is testable even without the
    infrastructure.

    Data-independent — behaves the same for any tenant's data. No
    assumptions about a specific product.

Usage:
    python context_search.py --hub-root <Hub> --query "resource limit policy" [--prefix G2 PG2]
        [--exclude-prefix PG2] [--layer B C] [--top 5]

exit code: 0 success (vector or degraded) / 1 no results / 2 argument error
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from _cache_utils import read_prefixes
from context_fetch import search_keyword


def neo4j_available() -> bool:
    """True if both the neo4j driver and a connection password are available."""
    if not os.environ.get("NEO4J_PASSWORD"):
        return False
    try:
        import neo4j  # noqa: F401
    except Exception:
        return False
    return True


def vector_search(query: str, *, prefixes: list[str] | None, exclude_prefix: list[str] | None,
                  layers: list[str] | None, top: int,
                  uri: str, user: str, password: str) -> list[dict] | None:
    """Neo4j vector search. Returns None on failure (connection/embedding/index) -> caller degrades."""
    try:
        from neo4j import GraphDatabase
    except Exception:
        return None
    try:
        from embed_pipeline import build_embeddings_model  # reuse the embedding model
    except Exception:
        return None
    try:
        # embed the query with the same model used for ingestion (single source: _embed_config) — guarantees matching dimension/semantics.
        model = build_embeddings_model()
        q_emb = model.embed(query) if hasattr(model, "embed") else model([query])[0]
        q_emb = list(getattr(q_emb, "embedding", q_emb))
    except Exception:
        return None

    cypher = (
        "CALL db.index.vector.queryNodes('chunk_embedding', $k, $emb) YIELD node, score "
        "WHERE score > 0.80 "
        + ("AND node.prefix IN $prefixes " if prefixes else "")
        + ("AND NOT node.prefix IN $exclude " if exclude_prefix else "")
        + ("AND node.layer IN $layers " if layers else "")
        + "RETURN node.prefix AS prefix, node.doc_id AS doc_id, node.layer AS layer, "
        "node.text AS text, score ORDER BY score DESC LIMIT $top"
    )
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            rows = session.run(cypher, k=max(top * 3, 10), emb=q_emb, prefixes=prefixes,
                               exclude=exclude_prefix, layers=layers, top=top)
            out = [dict(r) for r in rows]
        driver.close()
        return out
    except Exception:
        return None


def keyword_fallback(hub_root: Path, query: str, prefixes: list[str],
                     exclude_prefix: list[str] | None, top: int) -> list[dict]:
    """Degrade to cache-index keyword search when vector search is unavailable."""
    exclude = set(exclude_prefix or [])
    results: list[dict] = []
    for pfx in prefixes:
        if pfx in exclude:
            continue
        for hit in search_keyword(hub_root, pfx, query, top):
            results.append({"prefix": pfx, **hit})
    return results[:top]


def main() -> int:
    ap = argparse.ArgumentParser(description="L3 context vector search (+graceful degrade)")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--query", required=True)
    ap.add_argument("--prefix", nargs="*", default=None)
    ap.add_argument("--exclude-prefix", nargs="*", default=None)
    ap.add_argument("--layer", nargs="*", default=None)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--neo4j-uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    ap.add_argument("--neo4j-user", default=os.environ.get("NEO4J_USER", "neo4j"))
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2

    prefixes = args.prefix or read_prefixes(args.hub_root)
    mode = "vector"
    rows = None
    if neo4j_available():
        rows = vector_search(
            args.query, prefixes=args.prefix, exclude_prefix=args.exclude_prefix,
            layers=args.layer, top=args.top,
            uri=args.neo4j_uri, user=args.neo4j_user,
            password=os.environ["NEO4J_PASSWORD"],
        )
    if rows is None:
        mode = "keyword(degrade)"
        rows = keyword_fallback(args.hub_root, args.query, prefixes, args.exclude_prefix, args.top)

    print(f"[context_search] mode={mode} query={args.query!r} -> {len(rows)} result(s)")
    for r in rows:
        print(f"  {r}")
    if mode.startswith("keyword"):
        print("  (Neo4j unavailable -> degraded to keyword search. Vector search needs NEO4J_PASSWORD + an index)")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
