#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 2 external import + markdown analysis pipeline regression tests.

Targets: frontmatter_detect / layer_classify / term_extract / dependency_infer /
      import_normalize.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import frontmatter_detect as fd
import layer_classify as lc
import term_extract as te
import dependency_infer as di
import import_normalize as inrm


POLICY_MD = (
    "# 결제 정책\n\n## 1. 개요\n본 정책은 결제를 규정한다.\n\n"
    "## 2. 규칙\n- 결제 수단을 등록해야 한다.\n- 미납 시 이용이 금지된다.\n"
    "- 환불은 [G2-B-002 §3 참조] 를 전제로 한다.\n"
)
TERMS_MD = (
    "# 용어 사전\n\n| 용어 | 정의 |\n|---|---|\n"
    "| 인스턴스 | VM 단위 자원 |\n| 프로젝트 | 자원 묶음 |\n| 쿼타 | 자원 한도 |\n"
)


# ── frontmatter_detect ─────────────────────────────────────────────────────────

def test_detect_no_frontmatter():
    fm, body, had = fd.detect_frontmatter("# title\nbody\n")
    assert had is False and fm == {} and body.startswith("# title")


def test_detect_with_frontmatter():
    fm, body, had = fd.detect_frontmatter("---\ndoc_id: X-A-1\nv: 2\n---\nbody\n")
    assert had is True and fm["doc_id"] == "X-A-1" and body == "body\n"


def test_normalize_fills_and_preserves_body():
    out, report = fd.normalize(POLICY_MD, source="gitlab", doc_id="P-1",
                               imported_at="2026-01-02")
    assert out.startswith("---\n")
    assert "doc_id: P-1" in out
    assert "imported_at: 2026-01-02" in out
    assert "version(unknown)" in report["inferred"]
    # Body preserved losslessly — original key line retained
    assert "환불은 [G2-B-002 §3 참조]" in out


def test_normalize_preserves_custom_metadata():
    src = "---\ndoc_id: X-B-9\nversion: 2.1.0\ncustom: hi\n---\n# T\nbody\n"
    out, report = fd.normalize(src, source="notion")
    assert report["fields"]["doc_id"] == "X-B-9"
    assert report["fields"]["version"] == "2.1.0"
    assert json.loads(report["fields"]["original_metadata"])["custom"] == "hi"


# ── layer_classify ─────────────────────────────────────────────────────────────

def test_classify_policy_is_B():
    r = lc.classify(POLICY_MD)
    assert r["layer"] == "B"
    assert r["confidence"] > 0.3


def test_classify_terms_is_A():
    r = lc.classify(TERMS_MD)
    assert r["layer"] == "A"


def test_classify_empty_is_unknown():
    r = lc.classify("# 제목\n\n평범한 한 줄.\n")
    assert r["layer"] == "unknown"
    assert r["needs_review"] is True


# ── term_extract ───────────────────────────────────────────────────────────────

def test_diff_terms_new_and_known():
    extracted = {
        "인스턴스": {"def": "VM", "file": "f", "line": 1},
        "프로젝트": {"def": "묶음", "file": "f", "line": 2},
    }
    glossary = {"프로젝트": "묶음"}
    d = te.diff_terms(extracted, glossary)
    assert [x["term"] for x in d["new"]] == ["인스턴스"]
    assert "프로젝트" in d["known"]


def test_diff_terms_conflict():
    extracted = {"쿼타": {"def": "새 정의", "file": "f", "line": 3}}
    glossary = {"쿼타": "기존 정의"}
    d = te.diff_terms(extracted, glossary)
    assert d["conflict"] and d["conflict"][0]["term"] == "쿼타"


def test_term_extract_writes_candidates(tmp_path):
    hub = tmp_path / "Hub"
    (hub / "CONTEXT" / "glossary").mkdir(parents=True)
    (hub / "CONTEXT" / "glossary" / "terms.yml").write_text("terms:\n", encoding="utf-8")
    src = tmp_path / "t.md"
    src.write_text(TERMS_MD, encoding="utf-8")
    g = te._load_glossary(hub)
    extracted = te.extract_terms(TERMS_MD, "t.md")
    d = te.diff_terms(extracted, g)
    assert len(d["new"]) == 3  # 인스턴스/프로젝트/쿼타 (instance/project/quota) are all new


# ── dependency_infer ───────────────────────────────────────────────────────────

def test_infer_inherits_from_high():
    edges = di.infer_edges(POLICY_MD, "SELF-1")
    assert len(edges) == 1
    e = edges[0]
    assert e["target"] == "G2-B-002"
    assert e["type"] == "inherits_from"
    assert e["confidence"] == "high"


def test_infer_excludes_self():
    text = "[SELF-1 참조] 와 [X-B-2 참조]\n"
    edges = di.infer_edges(text, "SELF-1")
    assert [e["target"] for e in edges] == ["X-B-2"]


def test_infer_resolves_alias():
    edges = di.infer_edges("[G2-B-002 참조]\n", "S", {"G2-B-002": "상품요금결제정책"})
    assert edges[0]["resolved_stem"] == "상품요금결제정책"


# ── import_normalize ───────────────────────────────────────────────────────────

def test_write_record_creates_md_and_meta(tmp_path):
    hub = tmp_path / "Hub"
    (hub).mkdir()
    r = inrm.write_record(hub, "demo", "gitlab", "doc-1", POLICY_MD,
                          source_url="https://gitlab/x")
    md = hub / r["md_path"]
    meta = hub / r["meta_path"]
    assert md.exists() and meta.exists()
    assert r["status"] == "written"
    m = json.loads(meta.read_text(encoding="utf-8"))
    assert m["source"] == "gitlab" and m["id"] == "doc-1"


def test_write_record_idempotent(tmp_path):
    hub = tmp_path / "Hub"
    hub.mkdir()
    inrm.write_record(hub, "demo", "notion", "d", TERMS_MD)
    r2 = inrm.write_record(hub, "demo", "notion", "d", TERMS_MD)
    assert r2["status"] == "unchanged"


def test_write_record_meta_not_clobbered(tmp_path):
    hub = tmp_path / "Hub"
    hub.mkdir()
    inrm.write_record(hub, "demo", "file", "d", "# a\nbody1\n")
    meta_path = hub / "PROJECTS/demo/inputs/imports/file/d.meta.json"
    first = json.loads(meta_path.read_text(encoding="utf-8"))
    # Rewritten after content changed — preserves original metadata + flags the content change
    r = inrm.write_record(hub, "demo", "file", "d", "# a\nbody2-changed\n")
    second = json.loads(meta_path.read_text(encoding="utf-8"))
    assert second["imported_at"] == first["imported_at"]  # original metadata preserved
    assert r["status"] == "meta-updated"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
