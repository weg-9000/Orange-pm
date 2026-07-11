#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_emit unit tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import gate_emit as M  # noqa: E402

SSOT_BLOCKED = {
    "totals": {"block": 3, "warn": 11},
    "queues": [
        {"id": "drift", "block": 2, "queueFile": "reports/drift-queue.md"},
        {"id": "policy-impact", "block": 1, "queueFile": "reports/policy-impact-queue.md"},
        {"id": "mtg", "block": 0, "queueFile": "reports/mtg-queue.md"},
    ],
}
SSOT_CLEAN = {"totals": {"block": 0, "warn": 0}, "queues": [
    {"id": "drift", "block": 0, "queueFile": "reports/drift-queue.md"}]}


def test_draft_complete_blocked_from_ssot():
    out = M.transform_gates(SSOT_BLOCKED, ["policy-entry", "draft-complete"], "demo", 2)
    dc = {g["id"]: g for g in out["gates"]}["draft-complete"]
    assert dc["state"] == "blocked"
    assert {b["source"] for b in dc["blockers"]} == {"drift", "policy-impact"}


def test_draft_complete_pass_when_clean():
    out = M.transform_gates(SSOT_CLEAN, ["draft-complete"], "demo", 2)
    dc = out["gates"][0]
    assert dc["state"] == "pass"
    assert dc["blockers"] == []


def test_phase_states():
    out = M.transform_gates(SSOT_CLEAN, ["draft-complete"], "demo", current_phase=1)
    st = {p["id"]: p["state"] for p in out["phases"]}
    assert st[0] == "done" and st[1] == "active" and st[2] == "locked"
    assert out["recommended"][0]["cmd"] == "/lc"
    assert out["phaseEstimated"] is False        # explicit value → not estimated


def test_phase_estimated_from_ssot_block():
    blocked = M.transform_gates(SSOT_BLOCKED, ["draft-complete"], "demo")   # phase=None
    assert blocked["phaseEstimated"] is True
    assert blocked["currentPhase"] == 2          # BLOCK>0 → Draft phase
    clean = M.transform_gates(SSOT_CLEAN, ["draft-complete"], "demo")
    assert clean["currentPhase"] == 3            # pass → Integrate phase
    assert clean["phaseEstimated"] is True


SSOT_FRC_BLOCK = {
    "totals": {"block": 1, "warn": 2},
    "queues": [
        {"id": "fr-cluster", "block": 1, "warn": 2,
         "queueFile": "reports/fr-cluster-queue.md"},
    ],
}


def test_fr_cluster_trace_gate_blocked_and_pass():
    # mismatch BLOCK → fr-cluster-trace gate blocked
    out = M.transform_gates(SSOT_FRC_BLOCK, ["fr-cluster-trace"], "demo", 3)
    g = {x["id"]: x for x in out["gates"]}["fr-cluster-trace"]
    assert g["state"] == "blocked"
    assert g["phaseBoundary"] == "3→4"
    assert g["blockers"] and g["blockers"][0]["source"] == "fr-cluster"
    assert g["blockers"][0]["ref"] == "reports/fr-cluster-queue.md"
    # queue absent (MISSING, block 0) → pass
    clean = M.transform_gates(SSOT_CLEAN, ["fr-cluster-trace"], "demo", 3)
    gc = clean["gates"][0]
    assert gc["state"] == "pass"
    assert gc["blockers"] == []


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
