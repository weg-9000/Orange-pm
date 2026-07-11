#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 3 regression tests — archive_to_context / context_fetch / context_search /
embed_pipeline meta helpers. Data-independent, graceful-degrade verification (no infra required)."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

import archive_to_context as arch
import context_fetch as cf
import context_search as cs

# embed_pipeline requires chonkie at module import time -> inject a stub before importing.
if "chonkie" not in sys.modules:
    _m = types.ModuleType("chonkie")
    _m.__version__ = "stub"
    _m.RecursiveChunker = object
    _m.EmbeddingsRefinery = object
    sys.modules["chonkie"] = _m
import embed_pipeline as ep  # noqa: E402


# ── archive_to_context ─────────────────────────────────────────────────────────

def _hub_with_product(tmp_path: Path, *, rendered=True) -> Path:
    hub = tmp_path / "Hub"
    if rendered:
        d = hub / "PROJECTS" / "dbaas" / "reports" / "render"
        d.mkdir(parents=True)
        (d / "WO-001.complete.md").write_text("# Policy Complete\nBody text\n", encoding="utf-8")
    else:
        d = hub / "PROJECTS" / "dbaas" / "drafts"
        d.mkdir(parents=True)
        (d / "WO-001.draft.md").write_text("# Draft\n", encoding="utf-8")
    return hub


def test_archive_creates_c_and_metadata(tmp_path):
    hub = _hub_with_product(tmp_path)
    r = arch.archive(hub, "G2", "dbaas")
    assert r["status"] == "archived"
    c = hub / "CONTEXT/reference-docs/G2/C/dbaas"
    assert (c / "WO-001.complete.md").exists()
    meta = json.loads((c / "metadata.json").read_text(encoding="utf-8"))
    assert meta["prefix"] == "G2" and meta["service"] == "dbaas"
    assert meta["docs"] == ["WO-001.complete"]


def test_archive_idempotent_preserves_archived_at(tmp_path):
    hub = _hub_with_product(tmp_path)
    r1 = arch.archive(hub, "G2", "dbaas")
    meta1 = json.loads((hub / "CONTEXT/reference-docs/G2/C/dbaas/metadata.json").read_text("utf-8"))
    r2 = arch.archive(hub, "G2", "dbaas")
    meta2 = json.loads((hub / "CONTEXT/reference-docs/G2/C/dbaas/metadata.json").read_text("utf-8"))
    assert r2["copied"] == [] and r2["unchanged"] == ["WO-001.complete.md"]
    assert meta1["archived_at"] == meta2["archived_at"]


def test_archive_falls_back_to_drafts(tmp_path):
    hub = _hub_with_product(tmp_path, rendered=False)
    r = arch.archive(hub, "G2", "dbaas")
    assert r["status"] == "archived"
    assert (hub / "CONTEXT/reference-docs/G2/C/dbaas/WO-001.draft.md").exists()


def test_archive_no_source(tmp_path):
    hub = tmp_path / "Hub"
    hub.mkdir()
    assert arch.archive(hub, "G2", "ghost")["status"] == "no-source"


# ── context_fetch (L2) ─────────────────────────────────────────────────────────

def _hub_with_b_index(tmp_path: Path, prefix="G2") -> Path:
    hub = tmp_path / "Hub"
    (hub / "CONTEXT").mkdir(parents=True)
    (hub / "CONTEXT" / "layer-config.md").write_text(f"ACTIVE_PREFIX: {prefix}\n", encoding="utf-8")
    src = hub / "CONTEXT" / "reference-docs" / prefix / "B" / "doc.md"
    src.parent.mkdir(parents=True)
    src.write_text("# Document\n\n## 1. Overview\nOverview body.\n\n## 2. Limit\nLimit body.\n", encoding="utf-8")
    cache = hub / "CONTEXT" / ".template-cache"
    cache.mkdir(parents=True)
    idx = {"_meta": {"prefix": prefix}, "documents": {
        f"{prefix}-B-001": {
            "doc_id": f"{prefix}-B-001", "title": "Document",
            "path": f"CONTEXT/reference-docs/{prefix}/B/doc.md",
            "sections": [
                {"id": "1", "title": "Overview", "line_start": 3, "line_end": 5},
                {"id": "2", "title": "Limit", "line_start": 6, "line_end": 7},
            ]}}}
    (cache / f"{prefix}-b-headings-index.json").write_text(
        json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    (cache / f"{prefix}-a-terms-index.json").write_text(
        json.dumps({"terms": {"Instance": {"def": "VM unit", "file": "x", "line": 1}}},
                   ensure_ascii=False), encoding="utf-8")
    return hub


def test_fetch_section_by_id(tmp_path):
    hub = _hub_with_b_index(tmp_path)
    text, label = cf.fetch_section(hub, "G2", "G2-B-001", "2")
    assert "Limit body" in text and "§2" in label


def test_fetch_section_by_title(tmp_path):
    hub = _hub_with_b_index(tmp_path)
    text, label = cf.fetch_section(hub, "G2", "G2-B-001", "Overview")
    assert "Overview body" in text


def test_fetch_section_by_ordinal_id_via_map(tmp_path):
    hub = _hub_with_b_index(tmp_path)
    # Index key is stem(G2-B-001). Pinned ID(G2-B-003) is resolved via master-id-map.
    mp = hub / "CONTEXT" / "reference-docs" / "master-id-map.yml"
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text("G2-B-003: G2-B-001\n", encoding="utf-8")
    text, label = cf.fetch_section(hub, "G2", "G2-B-003", "2")
    assert "Limit body" in text


def test_fetch_section_unresolved(tmp_path):
    hub = _hub_with_b_index(tmp_path)
    text, label = cf.fetch_section(hub, "G2", "NOPE", "1")
    assert text == "" and label == "UNRESOLVED"


def test_fetch_term(tmp_path):
    hub = _hub_with_b_index(tmp_path)
    r = cf.fetch_term(hub, "G2", "Instance")
    assert r and r["def"] == "VM unit"


def test_search_keyword(tmp_path):
    hub = _hub_with_b_index(tmp_path)
    hits = cf.search_keyword(hub, "G2", "Limit", 5)
    assert any(h.get("section") == "2" for h in hits)


# ── context_search (L3 graceful degrade) ───────────────────────────────────────

def test_neo4j_unavailable_without_password(monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    assert cs.neo4j_available() is False


def test_keyword_fallback(tmp_path):
    hub = _hub_with_b_index(tmp_path)
    rows = cs.keyword_fallback(hub, "Limit", ["G2"], None, 5)
    assert rows and rows[0]["prefix"] == "G2"


def test_keyword_fallback_excludes_prefix(tmp_path):
    hub = _hub_with_b_index(tmp_path)
    rows = cs.keyword_fallback(hub, "Limit", ["G2"], ["G2"], 5)
    assert rows == []


# ── embed_pipeline meta helpers ─────────────────────────────────────────────────

def test_derive_prefix_nested(tmp_path):
    assert ep._derive_prefix(Path("CONTEXT/reference-docs/PG2/B/x.md"), "G2") == "PG2"
    assert ep._derive_prefix(Path("CONTEXT/reference-docs/B/x.md"), "G2") == "G2"


def test_derive_service():
    assert ep._derive_service(Path("CONTEXT/reference-docs/G2/C/dbaas/d2.md")) == "dbaas"
    assert ep._derive_service(Path("CONTEXT/reference-docs/G2/B/x.md")) == ""


def test_derive_doc_type():
    assert ep._derive_doc_type(Path("d2-policy.md")) == "d2"
    assert ep._derive_doc_type(Path("x.md")) == ""


def test_needs_reembed():
    p = Path(__file__)  # an actually-existing file
    mtime = p.stat().st_mtime
    assert ep._needs_reembed(p, {}) is True                      # not yet processed
    assert ep._needs_reembed(p, {str(p): mtime}) is False        # same mtime
    assert ep._needs_reembed(p, {str(p): mtime - 100}) is True   # source is newer


# ── Update/delete sync (Neo4j reconciliation) ──────────────────────────────────

def test_compute_removed():
    known = {"a.md", "b.md", "c.md"}
    current = {"a.md", "c.md"}
    assert ep.compute_removed(known, current) == ["b.md"]       # b removed
    assert ep.compute_removed(current, current) == []           # no change


class _FakeResult:
    def __init__(self, n): self._n = n
    def consume(self):
        return types.SimpleNamespace(counters=types.SimpleNamespace(nodes_deleted=self._n))


class _FakeSession:
    def __init__(self): self.queries = []
    def run(self, q, **kw):
        self.queries.append((q, kw))
        return _FakeResult(len(kw.get("files", [])) * 2)  # assume 2 chunks deleted per file


def test_delete_chunks_for_files_runs_detach_delete():
    s = _FakeSession()
    n = ep.delete_chunks_for_files(s, ["a.md", "b.md"])
    assert n == 4                                               # 2 files × 2
    q, kw = s.queries[0]
    assert "DETACH DELETE" in q and kw["files"] == ["a.md", "b.md"]


def test_delete_chunks_for_files_empty_noop():
    s = _FakeSession()
    assert ep.delete_chunks_for_files(s, []) == 0
    assert s.queries == []                                      # no calls made


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
