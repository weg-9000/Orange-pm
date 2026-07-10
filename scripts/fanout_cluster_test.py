#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fanout_dag cluster status 라이프사이클 유닛 테스트."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import fanout_dag as M  # noqa: E402

NODE = {
    "node_type": "policy", "capability": "Pricing", "cluster_id": "PR-01",
    "cluster_name": "요금", "sections": {"1": {"title": "범위"}}, "fr_refs": ["FR-1"],
}


def test_generated_cluster_draft_has_status_empty():
    content = M._generate_cluster_draft_content(
        "Pricing", "PR-01", "요금", [("N1", NODE)],
        product_name="demo", graph_hash="abc123def456",
        now_iso="2026-06-06T00:00:00Z", prefix_val="G2")
    assert "status: empty" in content
    assert "type: cluster_draft" in content
    # _check_existing_draft_status 가 읽어낼 수 있어야 함(라운드트립)
    import io
    assert content.startswith("---")


def test_inject_status_when_missing_preserves_other_fields():
    text = ('---\ntitle: x\nwo_id: G2-K-PR-01\ntype: cluster_draft\n'
            'cluster:\n  capability: "P"\nmembers: ["N1","N2"]\n---\n# 본문 보존\n')
    out = M._inject_status_field(text, "ai-draft")
    assert "status: ai-draft" in out
    assert out.count("status:") == 1
    # 중첩 YAML·배열·본문 모두 보존(재렌더 아님)
    assert 'cluster:\n  capability: "P"' in out
    assert 'members: ["N1","N2"]' in out
    assert "# 본문 보존" in out


def test_inject_status_inserts_after_type_line():
    text = '---\ntitle: x\ntype: cluster_draft\nlayer: C\n---\nbody\n'
    out = M._inject_status_field(text, "ai-draft")
    lines = out.splitlines()
    assert lines[lines.index("type: cluster_draft") + 1] == "status: ai-draft"


def test_inject_status_idempotent_when_present():
    text = '---\ntype: cluster_draft\nstatus: human-reviewed\n---\nbody\n'
    assert M._inject_status_field(text, "ai-draft") == text  # 기존 보존


def test_inject_status_noop_without_frontmatter():
    text = "no frontmatter here\n"
    assert M._inject_status_field(text, "ai-draft") == text


# ── is_common_shell 방출 (GAP1 — fix-plan-dossier-publish-split) ─────────────

def test_generated_draft_emits_is_common_shell_false_by_default():
    content = M._generate_cluster_draft_content(
        "Pricing", "PR-01", "요금", [("N1", NODE)],
        product_name="demo", graph_hash="abc", now_iso="2026-06-06T00:00:00Z",
        prefix_val="G2")
    assert "is_common_shell: false" in content


def test_generated_draft_emits_is_common_shell_true_for_common():
    # cluster_id 가 COMMON 으로 시작하면 공통 셸로 방출
    c1 = M._generate_cluster_draft_content(
        "Common", "COMMON-01", "NavShell", [("N1", NODE)],
        product_name="demo", graph_hash="abc", now_iso="2026-06-06T00:00:00Z",
        prefix_val="G2")
    assert "is_common_shell: true" in c1
    # capability 가 Common 이어도 공통 셸
    c2 = M._generate_cluster_draft_content(
        "Common", "NV-01", "Nav", [("N1", NODE)],
        product_name="demo", graph_hash="abc", now_iso="2026-06-06T00:00:00Z",
        prefix_val="G2")
    assert "is_common_shell: true" in c2


# ── publication_mode 영속화 (--publication-mode) ────────────────────────────

def test_apply_publication_mode_writes_and_preserves():
    with tempfile.TemporaryDirectory() as d:
        gdir = Path(d) / "graph"
        gdir.mkdir()
        (gdir / "project-mode.json").write_text(
            json.dumps({"track": "A", "model": "dossier", "decided_by": "DEC-X",
                        "section_wo_retired": True}), encoding="utf-8")
        M._apply_publication_mode(gdir, "split-deliverable")
        m = json.loads((gdir / "project-mode.json").read_text(encoding="utf-8"))
        assert m["publication_mode"] == "split-deliverable"
        assert m["decided_by"] == "DEC-X"        # 기존 키 보존
        assert m["section_wo_retired"] is True


def test_apply_publication_mode_none_is_noop():
    with tempfile.TemporaryDirectory() as d:
        gdir = Path(d) / "graph"
        gdir.mkdir()
        (gdir / "project-mode.json").write_text(
            json.dumps({"track": "A", "publication_mode": "dossier-page"}),
            encoding="utf-8")
        M._apply_publication_mode(gdir, None)  # 무변경
        m = json.loads((gdir / "project-mode.json").read_text(encoding="utf-8"))
        assert m["publication_mode"] == "dossier-page"


def test_apply_publication_mode_rejects_invalid():
    with tempfile.TemporaryDirectory() as d:
        gdir = Path(d) / "graph"
        gdir.mkdir()
        try:
            M._apply_publication_mode(gdir, "bogus-mode")
        except M.FanoutError:
            return
        raise AssertionError("무효 publication_mode 인데 FanoutError 미발생")


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
