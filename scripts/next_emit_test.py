#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""next_emit 유닛 테스트."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import next_emit as M  # noqa: E402


def _ssot(queues):
    total = sum(q.get("block", 0) for q in queues)
    return {"queues": queues, "totals": {"block": total, "warn": 0}}


def test_blocking_queue_emits_fix_action_ranked_first():
    ssot = _ssot([
        {"id": "drift", "title": "Drift", "block": 2, "warn": 0},
        {"id": "bdd-coverage", "title": "BDD Coverage", "block": 1, "warn": 0},
    ])
    out = M.transform_next("demo", ssot, [{"status": "ai-draft", "type": "policy", "woId": "W1"}], 0, True, True)
    a = out["actions"]
    assert a[0]["direction"] == "fix" and a[0]["source"] == "drift"      # drift 우선
    assert a[0]["cmd"] == "/render"
    assert any(x["source"] == "bdd-coverage" and x["cmd"] == "/bdd" for x in a)
    assert out["blockers"] >= 2


def test_pending_dec_fix_action():
    out = M.transform_next("demo", _ssot([]), [{"status": "human-reviewed", "type": "policy", "woId": "W1"}], 3, True, True)
    dec = [x for x in out["actions"] if x["source"] == "decisions"]
    assert dec and dec[0]["cmd"] == "/dec-approve" and "3건" in dec[0]["reason"]


def test_upstream_gap_backward_action():
    out = M.transform_next("demo", _ssot([]), [{"status": "ai-draft", "type": "policy", "woId": "W1"}], 0, True, True,
                           integration_upstream_gap=True)
    back = [x for x in out["actions"] if x["direction"] == "backward"]
    assert back and back[0]["cmd"] == "/draft-req"


def test_forward_by_status_progression():
    # empty → /write (policy)
    o1 = M.transform_next("demo", _ssot([]), [{"status": "empty", "type": "policy", "woId": "W1"}], 0, True, True)
    assert o1["actions"][-1]["cmd"] == "/write"
    # empty cluster → /write-cluster
    o2 = M.transform_next("demo", _ssot([]), [{"status": "empty", "type": "cluster", "woId": "G2-K-PR-01"}], 0, True, True)
    assert o2["actions"][-1]["cmd"] == "/write-cluster"
    # empty screen → /flow
    o3 = M.transform_next("demo", _ssot([]), [{"status": "empty", "type": "screen", "woId": "S1"}], 0, True, True)
    assert o3["actions"][-1]["cmd"] == "/flow"
    # all ai-draft → /review
    o4 = M.transform_next("demo", _ssot([]), [{"status": "ai-draft", "type": "policy", "woId": "W1"}], 0, True, True)
    assert o4["actions"][-1]["cmd"] == "/review"
    # all human-reviewed → /confirm
    o5 = M.transform_next("demo", _ssot([]), [{"status": "human-reviewed", "type": "policy", "woId": "W1"}], 0, True, True)
    assert o5["actions"][-1]["cmd"] == "/confirm"


def test_phase_forward_when_no_graph_or_wo():
    o1 = M.transform_next("demo", _ssot([]), [], 0, False, False)
    assert o1["actions"][-1]["cmd"] == "/graph-gen" and o1["phase"] == 0
    o2 = M.transform_next("demo", _ssot([]), [], 0, True, False)
    assert o2["actions"][-1]["cmd"] == "/fanout" and o2["phase"] == 1


def test_count_pending_dec():
    md = (
        "| ID | 일자 | 도메인 | 핵심 결정 | 번복 | 승인 | 근거 |\n"
        "| DEC-077 | 05-21 | 🎯 | x | - | ⬜ | /critique |\n"
        "| DEC-078 | 05-21 | 💰 | y | - | ✅ jeongdh | /su |\n"
        "| DEC-079 | 05-21 | 🏗️ | z | - | ⬜ | /write |\n"
    )
    assert M.count_pending_dec(md) == 2


def test_clean_state_only_forward_no_blockers():
    out = M.transform_next("demo", _ssot([]), [{"status": "frozen", "type": "policy", "woId": "W1"}], 0, True, True)
    assert out["blockers"] == 0
    assert out["phase"] == 4
    assert out["actions"][-1]["cmd"] == "/render"


def test_fr_cluster_mismatch_emits_fix_action():
    ssot = _ssot([{"id": "fr-cluster", "title": "FR-Cluster Trace", "block": 1, "warn": 0}])
    out = M.transform_next("demo", ssot, [{"status": "ai-draft", "type": "policy", "woId": "W1"}], 0, True, True)
    frc = [x for x in out["actions"] if x["source"] == "fr-cluster" and x["direction"] == "fix"]
    assert frc and frc[0]["cmd"] == "/lc"
    assert frc[0]["severity"] == "BLOCK"
    assert out["blockers"] >= 1


def test_fr_cluster_many_untagged_recommends_backfill():
    # WARN(orphan/unmapped) 임계 이상 → forward backfill 권고
    ssot = {"queues": [{"id": "fr-cluster", "title": "FR-Cluster Trace", "block": 0, "warn": 4}],
            "totals": {"block": 0, "warn": 4}}
    out = M.transform_next("demo", ssot, [{"status": "frozen", "type": "policy", "woId": "W1"}], 0, True, True)
    bf = [x for x in out["actions"] if x["source"] == "fr-cluster" and x["direction"] == "forward"]
    assert bf and "backfill" in bf[0]["arg"]
    assert "cluster_seed_backfill" in bf[0]["reason"]


def test_fr_cluster_few_warns_no_backfill():
    ssot = {"queues": [{"id": "fr-cluster", "title": "FR-Cluster Trace", "block": 0, "warn": 1}],
            "totals": {"block": 0, "warn": 1}}
    out = M.transform_next("demo", ssot, [{"status": "frozen", "type": "policy", "woId": "W1"}], 0, True, True)
    assert not [x for x in out["actions"] if x["source"] == "fr-cluster"]


def test_track_a_no_wo_recommends_cluster_mode():
    """Track A 인데 WO 미생성 → fanout 추천이 --cluster-mode 여야 한다 (P3)."""
    out = M.transform_next("demo", _ssot([]), [], 0, True, False, track="A")
    fwd = [a for a in out["actions"] if a["source"] == "phase"]
    assert fwd and "--cluster-mode" in fwd[0]["arg"], fwd


def test_track_legacy_no_wo_recommends_plain_fanout():
    out = M.transform_next("demo", _ssot([]), [], 0, True, False, track="legacy")
    fwd = [a for a in out["actions"] if a["source"] == "phase"]
    assert fwd and "--cluster-mode" not in fwd[0]["arg"], fwd


def test_track_mismatch_emits_fix_action():
    """Track A + legacy index 공존 → 혼선 정리 fix 액션 (P3)."""
    out = M.transform_next("demo", _ssot([]), [{"status": "empty", "type": "policy", "woId": "W1"}],
                           0, True, True, track="A", legacy_index_present=True)
    tm = [a for a in out["actions"] if a["source"] == "track"]
    assert tm and tm[0]["direction"] == "fix", out["actions"]
    assert "/plan-audit" == tm[0]["cmd"]


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
