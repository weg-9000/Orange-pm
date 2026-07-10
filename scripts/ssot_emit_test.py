#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ssot_emit 유닛 테스트."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import ssot_emit as M  # noqa: E402

DRIFT = "# drift\n> **BLOCK: 2 · WARN/UNRESOLVED: 9 · 공통 미참조 draft: 2**\n"
PIMPACT = "# pi\n> 변경 §: 3 · **IMPACT: 1 · WARN/COARSE: 1**\n"
MTG = "# mtg\n> **BLOCK: 0 · FAIL: 0 · WARN: 1**\n"

QUEUES = {"drift-queue.md": DRIFT, "policy-impact-queue.md": PIMPACT, "mtg-queue.md": MTG}


def test_block_equivalent_aggregation():
    out = M.transform_ssot(lambda f: QUEUES.get(f), "demo")
    # BLOCK 등가 = drift BLOCK(2) + policy-impact IMPACT(1) + mtg FAIL/BLOCK(0) = 3
    assert out["totals"]["block"] == 3
    assert out["totals"]["warn"] == 11      # 9 + 1 + 1
    assert out["gatePass"] is False


def test_per_queue_status():
    out = M.transform_ssot(lambda f: QUEUES.get(f), "demo")
    q = {x["id"]: x for x in out["queues"]}
    assert q["drift"]["status"] == "BLOCK"
    assert q["mtg"]["status"] == "PASS"
    assert q["policy-impact"]["block"] == 1


def test_missing_queue_marked():
    out = M.transform_ssot(lambda f: None, "demo")
    assert all(q["status"] == "MISSING" for q in out["queues"])
    assert out["gatePass"] is True          # block 합 0


def test_bdd_coverage_aggregated_as_block():
    bdd = "# bdd\n> **UNCOVERED: 2 · STALE: 1 · WARN: 0**\n"
    out = M.transform_ssot(lambda f: bdd if f == "bdd-coverage-queue.md" else None, "demo")
    q = {x["id"]: x for x in out["queues"]}
    assert "bdd-coverage" in q               # 고정 목록에 등록됨
    assert q["bdd-coverage"]["block"] == 3   # UNCOVERED(2) + STALE(1) — viz BLOCK 집계
    assert q["bdd-coverage"]["status"] == "BLOCK"
    assert out["gatePass"] is False          # 허위 그린 방지


def test_fr_cluster_queue_block_counted():
    # fr-cluster 큐에 mismatch BLOCK 1건 → viz BLOCK 등가로 집계
    frc = "# fr-cluster-trace-queue\n> **BLOCK: 1 · WARN: 2**\n"
    out = M.transform_ssot(lambda f: frc if f == "fr-cluster-queue.md" else None, "demo")
    q = {x["id"]: x for x in out["queues"]}
    assert "fr-cluster" in q                  # 고정 목록에 등록됨
    assert q["fr-cluster"]["block"] == 1
    assert q["fr-cluster"]["warn"] == 2
    assert q["fr-cluster"]["status"] == "BLOCK"
    assert out["totals"]["block"] == 1
    assert out["gatePass"] is False


def test_fr_cluster_queue_absent_graceful():
    # 큐 파일 부재 → MISSING, block 0 (back-compat)
    out = M.transform_ssot(lambda f: None, "demo")
    q = {x["id"]: x for x in out["queues"]}
    assert q["fr-cluster"]["status"] == "MISSING"
    assert q["fr-cluster"]["block"] == 0


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
