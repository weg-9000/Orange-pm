#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cluster_emit.py tests — cluster_map.json → cluster-map contract."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cluster_emit import transform_cluster_map, _empty, _fr_key  # type: ignore


class TestCapabilities(unittest.TestCase):
    def test_groups_fr_by_capability_then_cluster(self):
        cmap = {"fr_index": {
            "FR-101": {"capability": "Provisioning", "cluster_id": "PR-01"},
            "FR-103": {"capability": "Provisioning", "cluster_id": "PR-01"},
            "FR-201": {"capability": "Pricing", "cluster_id": "PR-02"},
        }}
        out = transform_cluster_map(cmap, "p")
        caps = {c["capability"]: c for c in out["capabilities"]}
        self.assertEqual(sorted(caps), ["Pricing", "Provisioning"])
        prov = caps["Provisioning"]["clusters"]
        self.assertEqual(prov[0]["clusterId"], "PR-01")
        self.assertEqual(prov[0]["frs"], ["FR-101", "FR-103"])

    def test_fr_natural_sort(self):
        cmap = {"fr_index": {
            "FR-2": {"capability": "A", "cluster_id": "AA-01"},
            "FR-10": {"capability": "A", "cluster_id": "AA-01"},
            "FR-1": {"capability": "A", "cluster_id": "AA-01"},
        }}
        out = transform_cluster_map(cmap, "p")
        self.assertEqual(out["capabilities"][0]["clusters"][0]["frs"], ["FR-1", "FR-2", "FR-10"])
        self.assertIn(10, _fr_key("FR-10"))


class TestModules(unittest.TestCase):
    def test_module_matrix_rows(self):
        cmap = {"module_index": {
            "DOC-EMAIL": [
                {"capability": "Provisioning", "cluster_id": "PR-01", "source": "N1", "via": "includes"},
                {"capability": "Operations", "cluster_id": "OP-01", "source": "N2", "via": "references"},
            ],
        }}
        out = transform_cluster_map(cmap, "p")
        self.assertEqual(len(out["modules"]), 1)
        m = out["modules"][0]
        self.assertEqual(m["moduleId"], "DOC-EMAIL")
        self.assertEqual([r["capability"] for r in m["refs"]], ["Provisioning", "Operations"])
        self.assertEqual(m["refs"][0]["via"], "includes")

    def test_multi_module_generic(self):
        cmap = {"module_index": {
            "DOC-EMAIL": [{"capability": "A", "cluster_id": "AA-01"}],
            "DOC-LOG": [{"capability": "B", "cluster_id": "BB-01"}],
        }}
        out = transform_cluster_map(cmap, "p")
        self.assertEqual([m["moduleId"] for m in out["modules"]], ["DOC-EMAIL", "DOC-LOG"])  # sort/generic


class TestGraceful(unittest.TestCase):
    def test_empty_and_malformed(self):
        self.assertEqual(transform_cluster_map({}, "p")["capabilities"], [])
        self.assertEqual(transform_cluster_map({}, "p")["modules"], [])
        self.assertEqual(transform_cluster_map({"fr_index": "bad"}, "p")["capabilities"], [])
        self.assertEqual(_empty("p")["kind"], "cluster-map")

    def test_kind_and_product(self):
        out = transform_cluster_map({"fr_index": {}}, "myprod")
        self.assertEqual(out["kind"], "cluster-map")
        self.assertEqual(out["product"], "myprod")


def _run() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (TestCapabilities, TestModules, TestGraceful):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    failed = len(result.failures) + len(result.errors)
    print(f"\nTotal {result.testsRun} — PASS {result.testsRun - failed} / FAIL {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run())
