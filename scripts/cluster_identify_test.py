#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for cluster_identify.py (Phase 5A).

stdlib unittest. 8+ cases.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cluster_identify import (  # type: ignore
    cluster_score,
    cluster_nodes,
    assign_cluster_ids,
    identify_clusters,
    compute_provenance,
    build_fr_index,
    build_module_index,
    DEFAULT_THRESHOLD,
    WEIGHTS,
)


def _make_node(**kwargs) -> dict:
    base = {"node_type": "policy"}
    base.update(kwargs)
    return base


# ── 1. score computation ────────────────────────────────────────────────
class TestScoring(unittest.TestCase):
    def test_identical_nodes_score_high(self):
        n = _make_node(
            policy_axis=["price", "limit"],
            domain_object=["Instance"],
            primary_screen="SCR-001",
            deliverable_targets=["D2", "D3"],
        )
        score, bd = cluster_score("a", n, "b", n, {})
        # identical meta -> score = sum of all axes (excluding dependency — empty dep_map)
        self.assertGreaterEqual(score, 0.7)

    def test_completely_different_nodes_score_zero(self):
        n1 = _make_node(policy_axis=["A"], domain_object=["X"], primary_screen="S1")
        n2 = _make_node(policy_axis=["B"], domain_object=["Y"], primary_screen="S2")
        score, _ = cluster_score("a", n1, "b", n2, {})
        # with nothing shared, only the default from dependency_cone + publication_fit
        # (deliverable_targets defaults to D2 -> publication_fit = 0.15 * 1.0)
        self.assertLessEqual(score, 0.20)

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1.0, places=5)


# ── 2. clustering — every node is its own independent cluster ───────────
class TestNoMerge(unittest.TestCase):
    def test_isolated_nodes_each_own_cluster(self):
        nodes = {
            "node_a": _make_node(policy_axis=["A"], primary_screen="S1"),
            "node_b": _make_node(policy_axis=["B"], primary_screen="S2"),
            "node_c": _make_node(policy_axis=["C"], primary_screen="S3"),
        }
        assignments, log = cluster_nodes(nodes, [], threshold=DEFAULT_THRESHOLD)
        # all 3 in different clusters (each on its own)
        self.assertEqual(len(set(assignments.values())), 3)
        self.assertEqual(len(log), 0)


# ── 3. clustering — strong merge ──────────────────────────────────────────
class TestStrongMerge(unittest.TestCase):
    def test_two_similar_nodes_merge(self):
        n = dict(
            node_type="policy",
            policy_axis=["price"],
            domain_object=["Instance"],
            primary_screen="SCR-001",
            deliverable_targets=["D2"],
        )
        nodes = {"node_a": dict(n), "node_b": dict(n), "node_c": _make_node(policy_axis=["other"])}
        assignments, log = cluster_nodes(nodes, [], threshold=DEFAULT_THRESHOLD)
        # a, b in the same cluster, c is independent
        self.assertEqual(assignments["node_a"], assignments["node_b"])
        self.assertNotEqual(assignments["node_a"], assignments["node_c"])
        self.assertEqual(len(log), 1)


# ── 4. ID assignment + stability ──────────────────────────────────────────
class TestIDStability(unittest.TestCase):
    def test_capability_prefix_assignment(self):
        nodes = {
            "n_pr_a": _make_node(capability="Provisioning", policy_axis=["A"]),
            "n_pr_b": _make_node(capability="Provisioning", policy_axis=["A"]),
            "n_bl_a": _make_node(capability="Billing", policy_axis=["B"]),
        }
        assignments, _ = cluster_nodes(nodes, [], threshold=DEFAULT_THRESHOLD)
        cluster_map: dict = {"canonical_to_id": {}}
        info = assign_cluster_ids(nodes, assignments, cluster_map)
        ids = [v["cluster_id"] for v in info.values()]
        # Provisioning gets "PR-NN", Billing gets "BI-NN"
        self.assertTrue(any(i.startswith("PR-") for i in ids))
        self.assertTrue(any(i.startswith("BI-") for i in ids))

    def test_persistent_cluster_map_reuse(self):
        nodes = {"n1": _make_node(capability="Pricing"), "n2": _make_node(capability="Pricing")}
        assignments, _ = cluster_nodes(nodes, [], threshold=DEFAULT_THRESHOLD)
        # first run
        m1: dict = {"canonical_to_id": {}}
        info1 = assign_cluster_ids(nodes, assignments, m1)
        first_ids = sorted(v["cluster_id"] for v in info1.values())
        # second run — reuses the same mapping
        info2 = assign_cluster_ids(nodes, assignments, m1)
        second_ids = sorted(v["cluster_id"] for v in info2.values())
        self.assertEqual(first_ids, second_ids)


# ── 5. End-to-end ─────────────────────────────────────────────────────
class TestEndToEnd(unittest.TestCase):
    def test_identify_clusters_full_flow(self):
        graph = {
            "graph": {
                "nodes": {
                    "policy_a": _make_node(
                        capability="Provisioning",
                        policy_axis=["instance"],
                        domain_object=["Instance"],
                        primary_screen="SCR-001",
                    ),
                    "policy_b": _make_node(
                        capability="Provisioning",
                        policy_axis=["instance"],
                        domain_object=["Instance"],
                        primary_screen="SCR-001",
                    ),
                    "policy_c": _make_node(
                        capability="Pricing",
                        policy_axis=["price"],
                        domain_object=["Plan"],
                    ),
                    "screen_a": _make_node(node_type="screen"),
                },
                "edges": [
                    {"source": "policy_a", "target": "policy_b", "type": "inherits_from"},
                ],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            out_path = tmp_path / "graph.clustered.json"
            map_path = tmp_path / "cluster_map.json"

            annotated, info, _ = identify_clusters(
                graph_path, out_path, cluster_map_path=map_path
            )

            # policy_a, policy_b are in the same cluster + Provisioning
            anodes = annotated["graph"]["nodes"]
            self.assertEqual(anodes["policy_a"]["cluster_id"], anodes["policy_b"]["cluster_id"])
            self.assertEqual(anodes["policy_a"]["capability"], "Provisioning")
            # policy_c is in a separate Pricing cluster
            self.assertEqual(anodes["policy_c"]["capability"], "Pricing")
            self.assertNotEqual(
                anodes["policy_a"]["cluster_id"], anodes["policy_c"]["cluster_id"]
            )
            # screen nodes don't get a cluster_id
            self.assertNotIn("cluster_id", anodes["screen_a"])

    def test_idempotent_rerun_preserves_ids(self):
        graph = {
            "graph": {
                "nodes": {
                    "p1": _make_node(capability="Provisioning", policy_axis=["A"]),
                    "p2": _make_node(capability="Provisioning", policy_axis=["A"]),
                },
                "edges": [],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            out_path = tmp_path / "graph.clustered.json"
            map_path = tmp_path / "cluster_map.json"

            # first run
            ann1, _, _ = identify_clusters(graph_path, out_path, cluster_map_path=map_path)
            id1 = ann1["graph"]["nodes"]["p1"]["cluster_id"]
            # second run — same ID
            ann2, _, _ = identify_clusters(graph_path, out_path, cluster_map_path=map_path)
            id2 = ann2["graph"]["nodes"]["p1"]["cluster_id"]
            self.assertEqual(id1, id2)


# ── 6. dependency-cone score ──────────────────────────────────────────────
class TestDependencyCone(unittest.TestCase):
    def test_shared_inherits_from_increases_score(self):
        nodes = {
            "n_a": _make_node(policy_axis=["X"], primary_screen="S1"),
            "n_b": _make_node(policy_axis=["X"], primary_screen="S1"),
            "n_dep": _make_node(policy_axis=["DEP"]),
        }
        edges = [
            {"source": "n_a", "target": "n_dep", "type": "inherits_from"},
            {"source": "n_b", "target": "n_dep", "type": "inherits_from"},
        ]
        assignments, log = cluster_nodes(nodes, edges, threshold=DEFAULT_THRESHOLD)
        # n_a, n_b share a dependency + same axis -> merge
        self.assertEqual(assignments["n_a"], assignments["n_b"])


# ── 7. seed consumption/validation/FR index (P2) ──────────────────────────
_HI = dict(  # high-score shared meta (so the pair exceeds the threshold)
    node_type="policy", policy_axis=["price"], domain_object=["Instance"],
    primary_screen="SCR-001", deliverable_targets=["D2"],
)


class TestSeed(unittest.TestCase):
    def test_seed_hint_preunion_merges_low_score(self):
        # low score (different axis) but same (capability, cluster_hint) -> merged as a seed
        nodes = {
            "a": _make_node(capability="Prov", cluster_hint="Catalog", policy_axis=["X"]),
            "b": _make_node(capability="Prov", cluster_hint="Catalog", policy_axis=["Y"]),
        }
        assignments, log = cluster_nodes(nodes, [], threshold=DEFAULT_THRESHOLD)
        self.assertEqual(assignments["a"], assignments["b"])  # merged via seed
        self.assertEqual(len(log), 0)  # not a score-based merge

    def test_ignore_seed_disables_preunion(self):
        nodes = {
            "a": _make_node(capability="Prov", cluster_hint="Catalog", policy_axis=["X"]),
            "b": _make_node(capability="Prov", cluster_hint="Catalog", policy_axis=["Y"]),
        }
        assignments, _ = cluster_nodes(nodes, [], threshold=DEFAULT_THRESHOLD, ignore_seed=True)
        self.assertNotEqual(assignments["a"], assignments["b"])  # levers only (seed ignored)

    def test_cluster_lock_excludes_score_merge(self):
        # high-score pair, but a is locked -> excluded from score merge (seed boundary fixed)
        nodes = {"a": dict(_HI, cluster_lock=True), "b": dict(_HI)}
        assignments, log = cluster_nodes(nodes, [], threshold=DEFAULT_THRESHOLD)
        self.assertNotEqual(assignments["a"], assignments["b"])
        self.assertEqual(len(log), 0)

    def test_provenance_kept_and_overridden(self):
        # a,b(Provisioning) + c(Billing) merge into one cluster by score -> majority capability=Provisioning
        nodes = {
            "a": dict(_HI, capability="Provisioning"),
            "b": dict(_HI, capability="Provisioning"),
            "c": dict(_HI, capability="Billing"),
        }
        assignments, _ = cluster_nodes(nodes, [], threshold=DEFAULT_THRESHOLD)
        info = assign_cluster_ids(nodes, assignments, {"canonical_to_id": {}})
        prov = compute_provenance(nodes, assignments, info)
        self.assertEqual(prov["a"], "seed_kept")
        self.assertTrue(prov["c"].startswith("seed_overridden"))

    def test_fr_index_maps_fr_to_cluster(self):
        graph = {
            "graph": {
                "nodes": {
                    "p1": _make_node(capability="Provisioning", fr_refs=["FR-101", "FR-102"]),
                    "p2": _make_node(capability="Pricing", fr_refs=["FR-201"]),
                },
                "edges": [],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            gp = tmp_path / "graph.json"
            gp.write_text(json.dumps(graph), encoding="utf-8")
            mp = tmp_path / "cluster_map.json"
            identify_clusters(gp, tmp_path / "out.json", cluster_map_path=mp)
            cmap = json.loads(mp.read_text(encoding="utf-8"))
            self.assertIn("fr_index", cmap)
            self.assertIn("FR-101", cmap["fr_index"])
            self.assertTrue(cmap["fr_index"]["FR-101"]["cluster_id"].startswith("PR-"))
            # different capability -> different cluster_id
            self.assertNotEqual(
                cmap["fr_index"]["FR-101"]["cluster_id"],
                cmap["fr_index"]["FR-201"]["cluster_id"],
            )


# ── 8. cross-cutting module index (DEC-F) ──────────────────────────
class TestCrossCutting(unittest.TestCase):
    def test_module_index_aggregates_referencing_clusters(self):
        # the email module is referenced by different capabilities (creation/backup) -> shown together
        graph = {
            "graph": {
                "nodes": {
                    "create_feat": _make_node(capability="Provisioning", fr_refs=["FR-1"]),
                    "backup_feat": _make_node(capability="Operations", fr_refs=["FR-2"]),
                    "email_mod": _make_node(
                        node_type="reference", role="cross-cutting",
                        title="Email/SMS sending module",
                    ),
                },
                "edges": [
                    {"source": "create_feat", "target": "email_mod", "type": "includes"},
                    {"source": "backup_feat", "target": "email_mod", "type": "includes"},
                ],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            tp = Path(tmp)
            gp = tp / "graph.json"
            gp.write_text(json.dumps(graph), encoding="utf-8")
            mp = tp / "cluster_map.json"
            identify_clusters(gp, tp / "out.json", cluster_map_path=mp)
            cmap = json.loads(mp.read_text(encoding="utf-8"))
            self.assertIn("module_index", cmap)
            refs = cmap["module_index"].get("email_mod", [])
            caps = sorted(r["capability"] for r in refs)
            self.assertEqual(caps, ["Operations", "Provisioning"])  # both features shown together

    def test_module_index_unit_direct(self):
        nodes = {
            "f1": _make_node(capability="A"),
            "mod": _make_node(node_type="reference", role="cross-cutting"),
        }
        edges = [{"source": "f1", "target": "mod", "type": "references"}]
        assignments = {"f1": "f1", "mod": "mod"}
        info = {
            "f1": {"capability": "A", "cluster_id": "AA-01", "cluster_name": "x", "members": ["f1"]},
            "mod": {"capability": "X", "cluster_id": "XX-01", "cluster_name": "m", "members": ["mod"]},
        }
        idx = build_module_index(nodes, edges, assignments, info)
        self.assertEqual(idx["mod"][0]["cluster_id"], "AA-01")
        self.assertEqual(idx["mod"][0]["via"], "references")


# ── runner ───────────────────────────────────────────────────────────────
def _run() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (
        TestScoring,
        TestNoMerge,
        TestStrongMerge,
        TestIDStability,
        TestEndToEnd,
        TestDependencyCone,
        TestSeed,
        TestCrossCutting,
    ):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    print(f"\nTotal {total} — PASS {total - failed} / FAIL {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run())
