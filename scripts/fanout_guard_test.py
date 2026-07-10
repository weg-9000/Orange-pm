#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fail-closed 트랙 가드 회귀 테스트 (fix-plan-track-routing P0/P1).

이번 사고(Track A/dossier 프로젝트에 legacy fanout → 빈 WO 셸 양산)의 재현
케이스를 고정한다. 표준 라이브러리만 사용 (pytest 비의존).
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
    """product_dir/{graph,work-orders,drafts} 골격 + graph.json 생성."""
    (tmp / "graph").mkdir(parents=True, exist_ok=True)
    (tmp / "work-orders").mkdir(parents=True, exist_ok=True)
    (tmp / "drafts").mkdir(parents=True, exist_ok=True)
    graph = {"graph": {"nodes": nodes or {}, "edges": []}}
    gpath = tmp / "graph" / "graph.json"
    gpath.write_text(json.dumps(graph), encoding="utf-8")
    return gpath, tmp / "work-orders"


# ── _detect_cluster_signals 단위 ──────────────────────────────────────────

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


# ── fanout fail-closed 가드 (핵심 회귀) ────────────────────────────────────

def test_fanout_aborts_on_dossier_without_flag():
    """이번 사고 재현: dossier 존재 + legacy fanout → 반드시 중단."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        gpath, out = _layout(tmp)
        (tmp / "drafts" / "cluster_PR-01.draft.md").write_text("---\ntype: cluster_draft\n---\n", encoding="utf-8")
        try:
            FD.fanout(gpath, out, "p", prefix="G2")
        except FD.FanoutError as e:
            assert "cluster(dossier) 모델" in str(e), str(e)
            return
        raise AssertionError("FanoutError 가 발생하지 않음 — 가드 미작동")


def test_fanout_force_legacy_bypasses_guard():
    """--force-legacy 는 가드를 우회한다 (이후 빈 노드로 별도 에러)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        gpath, out = _layout(tmp)  # nodes 비어 있음
        (tmp / "drafts" / "cluster_PR-01.draft.md").write_text("---\ntype: cluster_draft\n---\n", encoding="utf-8")
        try:
            FD.fanout(gpath, out, "p", prefix="G2", force_legacy=True)
        except FD.FanoutError as e:
            # 가드를 통과했으므로 cluster 가드 메시지가 아니라 노드 부재 에러여야 함
            assert "cluster(dossier) 모델" not in str(e), str(e)
            assert "처리할 노드" in str(e), str(e)
            return
        raise AssertionError("빈 노드 graph 인데 에러가 없음")


def test_fanout_no_signal_passes_guard():
    """신호 없으면 가드는 통과(빈 노드 → 별도 노드 부재 에러로 통과 확인)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        gpath, out = _layout(tmp)
        try:
            FD.fanout(gpath, out, "p", prefix="G2")
        except FD.FanoutError as e:
            assert "cluster(dossier) 모델" not in str(e), str(e)
            assert "처리할 노드" in str(e), str(e)
            return
        raise AssertionError("빈 노드 graph 인데 에러가 없음")


# ── project-mode.json 기록 (P1) ────────────────────────────────────────────

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
        assert mode["decided_by"] == "DEC-BDB-008"  # PM 결정 보존
        assert mode["cluster_count"] == 3           # 카운트는 갱신


def test_write_project_mode_defaults_publication_mode_dossier_page():
    # 신규(파일 없음) → dossier-page 기본 (dbaas 등 기존 프로젝트 회귀 가드)
    with tempfile.TemporaryDirectory() as d:
        graph_dir = Path(d)
        CI.write_project_mode(graph_dir, 5)
        mode = json.loads((graph_dir / "project-mode.json").read_text(encoding="utf-8"))
        assert mode["publication_mode"] == "dossier-page"


def test_write_project_mode_preserves_publication_mode():
    # /fanout 이 split 으로 박아둔 값을 cluster_identify 재실행이 덮어쓰지 않음
    with tempfile.TemporaryDirectory() as d:
        graph_dir = Path(d)
        (graph_dir / "project-mode.json").write_text(
            json.dumps({"track": "A", "model": "dossier",
                        "publication_mode": "split-deliverable"}), encoding="utf-8")
        CI.write_project_mode(graph_dir, 9)
        mode = json.loads((graph_dir / "project-mode.json").read_text(encoding="utf-8"))
        assert mode["publication_mode"] == "split-deliverable"  # 보존


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
