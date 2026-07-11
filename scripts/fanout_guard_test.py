#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fail-closed track guard regression tests (fix-plan-track-routing P0/P1).

Pins the reproduction cases of the incident (legacy fanout on a Track A/dossier
project → mass-produced empty WO shells). Uses only the standard library
(no pytest dependency).
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import fanout_dag as FD  # noqa: E402
import cluster_identify as CI  # noqa: E402


def _layout(tmp: Path, *, nodes=None):
    """Create the product_dir/{graph,work-orders,drafts} skeleton + graph.json."""
    (tmp / "graph").mkdir(parents=True, exist_ok=True)
    (tmp / "work-orders").mkdir(parents=True, exist_ok=True)
    (tmp / "drafts").mkdir(parents=True, exist_ok=True)
    graph = {"graph": {"nodes": nodes or {}, "edges": []}}
    gpath = tmp / "graph" / "graph.json"
    gpath.write_text(json.dumps(graph), encoding="utf-8")
    return gpath, tmp / "work-orders"


# ── _detect_cluster_signals unit ───────────────────────────────────────────

def test_detect_signals_empty_when_clean():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        gpath, out = _layout(tmp)
        graph = json.loads(gpath.read_text(encoding="utf-8"))
        assert FD._detect_cluster_signals(gpath, graph, out) == []


def test_detect_signals_dossier_draft():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        gpath, out = _layout(tmp)
        (tmp / "drafts" / "cluster_PR-01.draft.md").write_text("---\ntype: cluster_draft\n---\n", encoding="utf-8")
        graph = json.loads(gpath.read_text(encoding="utf-8"))
        sig = FD._detect_cluster_signals(gpath, graph, out)
        assert any("dossier" in s for s in sig), sig


def test_detect_signals_project_mode():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        gpath, out = _layout(tmp)
        (tmp / "graph" / "project-mode.json").write_text(
            json.dumps({"track": "A", "model": "dossier"}), encoding="utf-8")
        graph = json.loads(gpath.read_text(encoding="utf-8"))
        sig = FD._detect_cluster_signals(gpath, graph, out)
        assert any("project-mode" in s for s in sig), sig


def test_detect_signals_cluster_map():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        gpath, out = _layout(tmp)
        (tmp / "graph" / "cluster_map.json").write_text("{}", encoding="utf-8")
        graph = json.loads(gpath.read_text(encoding="utf-8"))
        assert any("cluster_map" in s for s in FD._detect_cluster_signals(gpath, graph, out))


def test_detect_signals_capability_meta():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        gpath, out = _layout(tmp, nodes={"P1": {"node_type": "policy", "capability": "Pricing"}})
        graph = json.loads(gpath.read_text(encoding="utf-8"))
        assert any("capability" in s for s in FD._detect_cluster_signals(gpath, graph, out))


# ── fanout fail-closed guard (core regression) ─────────────────────────────

def test_fanout_aborts_on_dossier_without_flag():
    """Incident reproduction: dossier exists + legacy fanout → must abort."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        gpath, out = _layout(tmp)
        (tmp / "drafts" / "cluster_PR-01.draft.md").write_text("---\ntype: cluster_draft\n---\n", encoding="utf-8")
        try:
            FD.fanout(gpath, out, "p", prefix="G2")
        except FD.FanoutError as e:
            assert "cluster(dossier) model" in str(e), str(e)
            return
        raise AssertionError("FanoutError not raised — guard inactive")


def test_fanout_force_legacy_bypasses_guard():
    """--force-legacy bypasses the guard (then fails separately on empty nodes)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        gpath, out = _layout(tmp)  # nodes empty
        (tmp / "drafts" / "cluster_PR-01.draft.md").write_text("---\ntype: cluster_draft\n---\n", encoding="utf-8")
        try:
            FD.fanout(gpath, out, "p", prefix="G2", force_legacy=True)
        except FD.FanoutError as e:
            # guard was passed, so the error must be no-nodes, not the cluster-guard message
            assert "cluster(dossier) model" not in str(e), str(e)
            assert "no nodes to process" in str(e), str(e)
            return
        raise AssertionError("empty-node graph but no error")


def test_fanout_no_signal_passes_guard():
    """Without signals the guard passes (empty nodes → verified via the separate no-nodes error)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        gpath, out = _layout(tmp)
        try:
            FD.fanout(gpath, out, "p", prefix="G2")
        except FD.FanoutError as e:
            assert "cluster(dossier) model" not in str(e), str(e)
            assert "no nodes to process" in str(e), str(e)
            return
        raise AssertionError("empty-node graph but no error")


# ── project-mode.json recording (P1) ────────────────────────────────────────

def test_write_project_mode_creates_marker():
    with tempfile.TemporaryDirectory() as d:
        graph_dir = Path(d)
        CI.write_project_mode(graph_dir, 7)
        mode = json.loads((graph_dir / "project-mode.json").read_text(encoding="utf-8"))
        assert mode["track"] == "A"
        assert mode["model"] == "dossier"
        assert mode["cluster_count"] == 7


def test_write_project_mode_preserves_decided_by():
    with tempfile.TemporaryDirectory() as d:
        graph_dir = Path(d)
        (graph_dir / "project-mode.json").write_text(
            json.dumps({"track": "A", "model": "dossier", "decided_by": "DEC-BDB-008",
                        "section_wo_retired": True}), encoding="utf-8")
        CI.write_project_mode(graph_dir, 3)
        mode = json.loads((graph_dir / "project-mode.json").read_text(encoding="utf-8"))
        assert mode["decided_by"] == "DEC-BDB-008"  # PM decision preserved
        assert mode["cluster_count"] == 3           # count refreshed


def test_write_project_mode_defaults_publication_mode_dossier_page():
    # new (no file) → dossier-page default (regression guard for existing projects like dbaas)
    with tempfile.TemporaryDirectory() as d:
        graph_dir = Path(d)
        CI.write_project_mode(graph_dir, 5)
        mode = json.loads((graph_dir / "project-mode.json").read_text(encoding="utf-8"))
        assert mode["publication_mode"] == "dossier-page"


def test_write_project_mode_preserves_publication_mode():
    # a value /fanout pinned as split must not be overwritten by a cluster_identify re-run
    with tempfile.TemporaryDirectory() as d:
        graph_dir = Path(d)
        (graph_dir / "project-mode.json").write_text(
            json.dumps({"track": "A", "model": "dossier",
                        "publication_mode": "split-deliverable"}), encoding="utf-8")
        CI.write_project_mode(graph_dir, 9)
        mode = json.loads((graph_dir / "project-mode.json").read_text(encoding="utf-8"))
        assert mode["publication_mode"] == "split-deliverable"  # preserved


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
