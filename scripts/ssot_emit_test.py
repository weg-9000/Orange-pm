#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ssot_emit unit tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import ssot_emit as M  # noqa: E402

DRIFT = "# drift\n> **BLOCK: 2 · WARN/UNRESOLVED: 9 · drafts not referencing common: 2**\n"
PIMPACT = "# pi\n> changed §: 3 · **IMPACT: 1 · WARN/COARSE: 1**\n"
MTG = "# mtg\n> **BLOCK: 0 · FAIL: 0 · WARN: 1**\n"

QUEUES = {"drift-queue.md": DRIFT, "policy-impact-queue.md": PIMPACT, "mtg-queue.md": MTG}


def test_block_equivalent_aggregation():
    out = M.transform_ssot(lambda f: QUEUES.get(f), "demo")
    # BLOCK equivalent = drift BLOCK(2) + policy-impact IMPACT(1) + mtg FAIL/BLOCK(0) = 3
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
    assert out["gatePass"] is True          # block total is 0


def test_bdd_coverage_aggregated_as_block():
    bdd = "# bdd\n> **UNCOVERED: 2 · STALE: 1 · WARN: 0**\n"
    out = M.transform_ssot(lambda f: bdd if f == "bdd-coverage-queue.md" else None, "demo")
    q = {x["id"]: x for x in out["queues"]}
    assert "bdd-coverage" in q               # registered in the fixed list
    assert q["bdd-coverage"]["block"] == 3   # UNCOVERED(2) + STALE(1) — aggregated as viz BLOCK
    assert q["bdd-coverage"]["status"] == "BLOCK"
    assert out["gatePass"] is False          # prevents a false green


def test_fr_cluster_queue_block_counted():
    # 1 mismatch BLOCK in the fr-cluster queue -> aggregated as viz BLOCK equivalent
    frc = "# fr-cluster-trace-queue\n> **BLOCK: 1 · WARN: 2**\n"
    out = M.transform_ssot(lambda f: frc if f == "fr-cluster-queue.md" else None, "demo")
    q = {x["id"]: x for x in out["queues"]}
    assert "fr-cluster" in q                  # registered in the fixed list
    assert q["fr-cluster"]["block"] == 1
    assert q["fr-cluster"]["warn"] == 2
    assert q["fr-cluster"]["status"] == "BLOCK"
    assert out["totals"]["block"] == 1
    assert out["gatePass"] is False


def test_fr_cluster_queue_absent_graceful():
    # queue file absent -> MISSING, block 0 (back-compat)
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
