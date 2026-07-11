#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fanout_dag cluster status lifecycle unit tests."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import fanout_dag as M  # noqa: E402

NODE = {
    "node_type": "policy", "capability": "Pricing", "cluster_id": "PR-01",
    "cluster_name": "Pricing", "sections": {"1": {"title": "Scope"}}, "fr_refs": ["FR-1"],
}


def test_generated_cluster_draft_has_status_empty():
    content = M._generate_cluster_draft_content(
        "Pricing", "PR-01", "Pricing", [("N1", NODE)],
        product_name="demo", graph_hash="abc123def456",
        now_iso="2026-06-06T00:00:00Z", prefix_val="G2")
    assert "status: empty" in content
    assert "type: cluster_draft" in content
    # _check_existing_draft_status must be able to read it back (round trip)
    import io
    assert content.startswith("---")


def test_inject_status_when_missing_preserves_other_fields():
    text = ('---\ntitle: x\nwo_id: G2-K-PR-01\ntype: cluster_draft\n'
            'cluster:\n  capability: "P"\nmembers: ["N1","N2"]\n---\n# body preserved\n')
    out = M._inject_status_field(text, "ai-draft")
    assert "status: ai-draft" in out
    assert out.count("status:") == 1
    # nested YAML, arrays, and body all preserved (no re-render)
    assert 'cluster:\n  capability: "P"' in out
    assert 'members: ["N1","N2"]' in out
    assert "# body preserved" in out


def test_inject_status_inserts_after_type_line():
    text = '---\ntitle: x\ntype: cluster_draft\nlayer: C\n---\nbody\n'
    out = M._inject_status_field(text, "ai-draft")
    lines = out.splitlines()
    assert lines[lines.index("type: cluster_draft") + 1] == "status: ai-draft"


def test_inject_status_idempotent_when_present():
    text = '---\ntype: cluster_draft\nstatus: human-reviewed\n---\nbody\n'
    assert M._inject_status_field(text, "ai-draft") == text  # existing preserved


def test_inject_status_noop_without_frontmatter():
    text = "no frontmatter here\n"
    assert M._inject_status_field(text, "ai-draft") == text


# ── is_common_shell emission (GAP1 — fix-plan-dossier-publish-split) ──────────

def test_generated_draft_emits_is_common_shell_false_by_default():
    content = M._generate_cluster_draft_content(
        "Pricing", "PR-01", "Pricing", [("N1", NODE)],
        product_name="demo", graph_hash="abc", now_iso="2026-06-06T00:00:00Z",
        prefix_val="G2")
    assert "is_common_shell: false" in content


def test_generated_draft_emits_is_common_shell_true_for_common():
    # a cluster_id starting with COMMON is emitted as a common shell
    c1 = M._generate_cluster_draft_content(
        "Common", "COMMON-01", "NavShell", [("N1", NODE)],
        product_name="demo", graph_hash="abc", now_iso="2026-06-06T00:00:00Z",
        prefix_val="G2")
    assert "is_common_shell: true" in c1
    # a Common capability is also a common shell
    c2 = M._generate_cluster_draft_content(
        "Common", "NV-01", "Nav", [("N1", NODE)],
        product_name="demo", graph_hash="abc", now_iso="2026-06-06T00:00:00Z",
        prefix_val="G2")
    assert "is_common_shell: true" in c2


# ── publication_mode persistence (--publication-mode) ─────────────────────────

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
        assert m["decided_by"] == "DEC-X"        # existing keys preserved
        assert m["section_wo_retired"] is True


def test_apply_publication_mode_none_is_noop():
    with tempfile.TemporaryDirectory() as d:
        gdir = Path(d) / "graph"
        gdir.mkdir()
        (gdir / "project-mode.json").write_text(
            json.dumps({"track": "A", "publication_mode": "dossier-page"}),
            encoding="utf-8")
        M._apply_publication_mode(gdir, None)  # no change
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
        raise AssertionError("invalid publication_mode did not raise FanoutError")


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
