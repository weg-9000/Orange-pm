#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tier 3 컨텍스트 검색 — L3 벡터 + graceful degrade (멀티테넌트 SaaS Phase 3).

목적:
    크로스-PREFIX 의미론적 유사 탐색("민간에서 비슷한 정책을 어떻게 처리했나?").
    Neo4j 벡터 인덱스가 있으면 벡터 검색, 없으면 **캐시 인덱스 키워드 검색으로
    자동 강등(graceful degrade)** 한다 → 인프라 없이도 동작·테스트 가능.

    데이터 비종속 — 어느 테넌트의 데이터든 동일 동작. 특정 제품 전제 없음.

사용법:
    python context_search.py --hub-root <Hub> --query "자원 한도 정책" [--prefix G2 PG2]
        [--exclude-prefix PG2] [--layer B C] [--top 5]

exit code: 0 성공(벡터 또는 강등) / 1 결과 없음 / 2 인자 오류
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from _cache_utils import read_prefixes
from context_fetch import search_keyword


def neo4j_available() -> bool:
    """neo4j 드라이버 + 접속 비밀번호가 모두 있으면 True."""
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
    """Neo4j 벡터 검색. 실패(연결·임베딩·인덱스)하면 None 반환 → 호출자가 강등."""
    try:
        from neo4j import GraphDatabase
    except Exception:
        return None
    try:
        from embed_pipeline import build_embeddings_model  # 임베딩 모델 재사용
    except Exception:
        return None
    try:
        # 적재와 동일 모델로 쿼리 임베딩(_embed_config 단일 출처) — 차원·의미 일치 보장.
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
    """벡터 미가용 시 캐시 인덱스 키워드 검색으로 강등."""
    exclude = set(exclude_prefix or [])
    results: list[dict] = []
    for pfx in prefixes:
        if pfx in exclude:
            continue
        for hit in search_keyword(hub_root, pfx, query, top):
            results.append({"prefix": pfx, **hit})
    return results[:top]


def main() -> int:
    ap = argparse.ArgumentParser(description="L3 컨텍스트 벡터 검색(+graceful degrade)")
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

    print(f"[context_search] mode={mode} query={args.query!r} → {len(rows)}건")
    for r in rows:
        print(f"  {r}")
    if mode.startswith("keyword"):
        print("  (Neo4j 미가용 → 키워드 강등. 벡터 검색은 NEO4J_PASSWORD + 인덱스 필요)")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
