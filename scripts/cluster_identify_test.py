#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cluster_identify.py 테스트 (Phase 5A).

stdlib unittest. 8+ 케이스.
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


# ── 1. 점수 산정 ────────────────────────────────────────────────────────
class TestScoring(unittest.TestCase):
    def test_identical_nodes_score_high(self):
        n = _make_node(
            policy_axis=["가격", "한도"],
            domain_object=["Instance"],
            primary_screen="SCR-001",
            deliverable_targets=["D2", "D3"],
        )
        score, bd = cluster_score("a", n, "b", n, {})
        # 동일 메타 → 점수 = 모든 축 합 (의존성 제외 — 빈 dep_map)
        self.assertGreaterEqual(score, 0.7)

    def test_completely_different_nodes_score_zero(self):
        n1 = _make_node(policy_axis=["A"], domain_object=["X"], primary_screen="S1")
        n2 = _make_node(policy_axis=["B"], domain_object=["Y"], primary_screen="S2")
        score, _ = cluster_score("a", n1, "b", n2, {})
        # 공유 없으면 dependency_cone + publication_fit 의 default 만
        # (deliverable_targets 기본 D2 → publication_fit = 0.15 * 1.0)
        self.assertLessEqual(score, 0.20)

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1.0, places=5)


# ── 2. 군집 — 모든 노드가 독립 cluster ───────────────────────────────────
class TestNoMerge(unittest.TestCase):
    def test_isolated_nodes_each_own_cluster(self):
        nodes = {
            "node_a": _make_node(policy_axis=["A"], primary_screen="S1"),
            "node_b": _make_node(policy_axis=["B"], primary_screen="S2"),
            "node_c": _make_node(policy_axis=["C"], primary_screen="S3"),
        }
        assignments, log = cluster_nodes(nodes, [], threshold=DEFAULT_THRESHOLD)
        # 3개 모두 다른 cluster (자기 자신)
        self.assertEqual(len(set(assignments.values())), 3)
        self.assertEqual(len(log), 0)


# ── 3. 군집 — 강한 결합 ──────────────────────────────────────────────────
class TestStrongMerge(unittest.TestCase):
    def test_two_similar_nodes_merge(self):
        n = dict(
            node_type="policy",
            policy_axis=["가격"],
            domain_object=["Instance"],
            primary_screen="SCR-001",
            deliverable_targets=["D2"],
        )
        nodes = {"node_a": dict(n), "node_b": dict(n), "node_c": _make_node(policy_axis=["다른"])}
        assignments, log = cluster_nodes(nodes, [], threshold=DEFAULT_THRESHOLD)
        # a, b 가 같은 cluster, c 는 독립
        self.assertEqual(assignments["node_a"], assignments["node_b"])
        self.assertNotEqual(assignments["node_a"], assignments["node_c"])
        self.assertEqual(len(log), 1)


# ── 4. ID 부여 + 안정성 ──────────────────────────────────────────────────
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
        # Provisioning 은 "PR-NN", Billing 은 "BI-NN"
        self.assertTrue(any(i.startswith("PR-") for i in ids))
        self.assertTrue(any(i.startswith("BI-") for i in ids))

    def test_persistent_cluster_map_reuse(self):
        nodes = {"n1": _make_node(capability="Pricing"), "n2": _make_node(capability="Pricing")}
        assignments, _ = cluster_nodes(nodes, [], threshold=DEFAULT_THRESHOLD)
        # 첫 실행
        m1: dict = {"canonical_to_id": {}}
        info1 = assign_cluster_ids(nodes, assignments, m1)
        first_ids = sorted(v["cluster_id"] for v in info1.values())
        # 두 번째 실행 — 같은 매핑 재사용
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
                        policy_axis=["인스턴스"],
                        domain_object=["Instance"],
                        primary_screen="SCR-001",
                    ),
                    "policy_b": _make_node(
                        capability="Provisioning",
                        policy_axis=["인스턴스"],
                        domain_object=["Instance"],
                        primary_screen="SCR-001",
                    ),
                    "policy_c": _make_node(
                        capability="Pricing",
                        policy_axis=["가격"],
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

            # policy_a, policy_b 는 같은 cluster + Provisioning
            anodes = annotated["graph"]["nodes"]
            self.assertEqual(anodes["policy_a"]["cluster_id"], anodes["policy_b"]["cluster_id"])
            self.assertEqual(anodes["policy_a"]["capability"], "Provisioning")
            # policy_c 는 Pricing 별도 cluster
            self.assertEqual(anodes["policy_c"]["capability"], "Pricing")
            self.assertNotEqual(
                anodes["policy_a"]["cluster_id"], anodes["policy_c"]["cluster_id"]
            )
            # screen 노드는 cluster_id 미부여
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

            # 첫 실행
            ann1, _, _ = identify_clusters(graph_path, out_path, cluster_map_path=map_path)
            id1 = ann1["graph"]["nodes"]["p1"]["cluster_id"]
            # 두 번째 실행 — 동일 ID
            ann2, _, _ = identify_clusters(graph_path, out_path, cluster_map_path=map_path)
            id2 = ann2["graph"]["nodes"]["p1"]["cluster_id"]
            self.assertEqual(id1, id2)


# ── 6. 의존성 cone 점수 ──────────────────────────────────────────────────
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
        # n_a, n_b 는 공유 의존 + 같은 axis → 결합
        self.assertEqual(assignments["n_a"], assignments["n_b"])


# ── 7. 씨앗(seed) 소비·검증·FR 인덱스 (P2) ──────────────────────────────
_HI = dict(  # 고점수 공통 메타(쌍이 임계 초과하도록)
    node_type="policy", policy_axis=["가격"], domain_object=["Instance"],
    primary_screen="SCR-001", deliverable_targets=["D2"],
)


class TestSeed(unittest.TestCase):
    def test_seed_hint_preunion_merges_low_score(self):
        # 점수는 낮지만(다른 axis) 동일 (capability, cluster_hint) → 씨앗으로 결합
        nodes = {
            "a": _make_node(capability="Prov", cluster_hint="Catalog", policy_axis=["X"]),
            "b": _make_node(capability="Prov", cluster_hint="Catalog", policy_axis=["Y"]),
        }
        assignments, log = cluster_nodes(nodes, [], threshold=DEFAULT_THRESHOLD)
        self.assertEqual(assignments["a"], assignments["b"])  # 씨앗 결합
        self.assertEqual(len(log), 0)  # 점수 결합은 아님

    def test_ignore_seed_disables_preunion(self):
        nodes = {
            "a": _make_node(capability="Prov", cluster_hint="Catalog", policy_axis=["X"]),
            "b": _make_node(capability="Prov", cluster_hint="Catalog", policy_axis=["Y"]),
        }
        assignments, _ = cluster_nodes(nodes, [], threshold=DEFAULT_THRESHOLD, ignore_seed=True)
        self.assertNotEqual(assignments["a"], assignments["b"])  # 레버만(씨앗 무시)

    def test_cluster_lock_excludes_score_merge(self):
        # 고점수 쌍이지만 a 가 lock → 점수 병합 제외(씨앗 경계 고정)
        nodes = {"a": dict(_HI, cluster_lock=True), "b": dict(_HI)}
        assignments, log = cluster_nodes(nodes, [], threshold=DEFAULT_THRESHOLD)
        self.assertNotEqual(assignments["a"], assignments["b"])
        self.assertEqual(len(log), 0)

    def test_provenance_kept_and_overridden(self):
        # a,b(Provisioning) + c(Billing) 가 점수로 한 cluster → 다수결 capability=Provisioning
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
            # 서로 다른 capability → 다른 cluster_id
            self.assertNotEqual(
                cmap["fr_index"]["FR-101"]["cluster_id"],
                cmap["fr_index"]["FR-201"]["cluster_id"],
            )


# ── 8. 횡단(cross-cutting) 모듈 인덱스 (DEC-F) ──────────────────────────
class TestCrossCutting(unittest.TestCase):
    def test_module_index_aggregates_referencing_clusters(self):
        # 이메일 모듈을 서로 다른 capability(생성/백업)이 참조 → 한꺼번에 보임
        graph = {
            "graph": {
                "nodes": {
                    "create_feat": _make_node(capability="Provisioning", fr_refs=["FR-1"]),
                    "backup_feat": _make_node(capability="Operations", fr_refs=["FR-2"]),
                    "email_mod": _make_node(
                        node_type="reference", role="cross-cutting",
                        title="이메일·SMS 발송 모듈",
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
            self.assertEqual(caps, ["Operations", "Provisioning"])  # 두 기능 한꺼번에

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


# ── 실행기 ───────────────────────────────────────────────────────────────
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
    print(f"\n총 {total}개 — PASS {total - failed} / FAIL {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run())
