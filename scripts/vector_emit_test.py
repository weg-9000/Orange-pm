#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vector_emit regression tests — Neo4j vector index status (fake session) + graceful degrade."""
from __future__ import annotations

import pytest

import vector_emit as ve


class _Row(dict):
    def __getitem__(self, k):  # neo4j-Record-like access
        return super().__getitem__(k)


class _FakeSession:
    def __init__(self, index_rows, chunk_rows):
        self._index = index_rows
        self._chunks = chunk_rows

    def run(self, query, **kw):
        if "SHOW VECTOR INDEXES" in query:
            return iter(self._index)
        if "MATCH (c:Chunk)" in query:
            return iter(self._chunks)
        return iter([])


def test_query_stats_aggregates():
    index_rows = [_Row(name="chunk_embedding", options={"indexConfig": {"vector.dimensions": 1024}})]
    chunk_rows = [
        _Row(prefix="G2", layer="G2-B", docId="G2-B-001", service="", chunks=12),
        _Row(prefix="G2", layer="G2-A", docId="G2-A-001", service="", chunks=5),
        _Row(prefix="PG2", layer="PG2-B", docId="PG2-B-001", service="", chunks=7),
    ]
    stats = ve.query_stats(_FakeSession(index_rows, chunk_rows))
    assert stats["indexName"] == "chunk_embedding"
    assert stats["dimensions"] == 1024
    assert stats["totalChunks"] == 24
    assert len(stats["docs"]) == 3
    g2 = next(p for p in stats["byPrefix"] if p["prefix"] == "G2")
    assert g2["chunks"] == 17 and g2["docs"] == 2


def test_query_stats_handles_missing_index():
    # chunk stats still work even if SHOW VECTOR INDEXES is empty (old version/permissions)
    chunk_rows = [_Row(prefix="EX", layer="EX-B", docId="EX-B-001", service="", chunks=3)]
    stats = ve.query_stats(_FakeSession([], chunk_rows))
    assert stats["indexName"] is None and stats["totalChunks"] == 3


def test_transform_unavailable_without_password(monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    out = ve.transform()
    assert out["kind"] == "vector-index" and out["status"] == "unavailable"
    assert out["totalChunks"] == 0 and out["docs"] == []
    assert "NEO4J_PASSWORD" in out["reason"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
