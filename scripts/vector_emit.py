#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vector_emit — Neo4j 벡터 인덱스 현황 → 정규화 JSON (viz 거버넌스, Phase 6).

Neo4j 에 실제로 적재된 :Chunk(임베딩 문서)가 무엇인지 보여준다:
  - 벡터 인덱스 이름·차원
  - 총 청크 수
  - 문서별(doc_id/prefix/layer/service) 청크 수
  - PREFIX 별 집계

읽기 전용. Neo4j 미가용(드라이버·비밀번호·연결 실패) 시 status="unavailable" 로
graceful degrade — 인프라/오프라인/CI 에서도 안전.

    python vector_emit.py --emit-json
출력: {kind:"vector-index", status, indexName, dimensions, totalChunks, docs[], byPrefix[], version}
환경: NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
"""
from __future__ import annotations

import os
import sys

import _emit_common as C


def _connect():
    """(driver, None) 또는 (None, 사유). 실패해도 예외 없이 사유 문자열 반환."""
    if not os.environ.get("NEO4J_PASSWORD"):
        return None, "NEO4J_PASSWORD 미설정"
    try:
        from neo4j import GraphDatabase
    except Exception:
        return None, "neo4j 드라이버 미설치 (pip install neo4j)"
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    try:
        d = GraphDatabase.driver(uri, auth=(user, os.environ["NEO4J_PASSWORD"]))
        d.verify_connectivity()
        return d, None
    except Exception as e:
        return None, f"연결 실패: {e}"


def query_stats(session) -> dict:
    """세션에서 인덱스·청크 통계를 수집(쿼리는 best-effort)."""
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
        pass  # 구버전/권한 등 — 인덱스 메타 없이 통계만

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
