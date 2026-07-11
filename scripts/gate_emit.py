#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_emit — gate definitions + ssot queues → normalized gates contract (§4, v1 simplified).

Note: full /lc phase-determination integration is a follow-up. This v1 derives
draft-complete gate blocking from ssot BLOCK equivalence, and lists gates
present under CONTEXT/gates/*.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import _emit_common as C
import ssot_emit

PHASE_NAMES = [(-1, "Discovery"), (0, "Ingest&Graph"), (1, "Fanout"),
               (2, "Draft"), (3, "Integrate"), (4, "Confirm")]


def _phases(current: int) -> list[dict]:
    out = []
    for pid, name in PHASE_NAMES:
        state = "done" if pid < current else "active" if pid == current else "locked"
        out.append({"id": pid, "name": name, "state": state})
    return out


def transform_gates(ssot: dict, gate_names: list[str], product: str = "",
                    current_phase: int | None = None) -> dict:
    """ssot contract result + gate name list → gates contract.

    If current_phase=None, the phase is estimated from ssot BLOCK equivalence
    (phaseEstimated=True): BLOCK>0 blocks draft-complete (2→3), so Phase 2 (Draft);
    otherwise Phase 3 (Integrate). If an explicit value is given, it is used
    as-is and the estimated flag is turned off.
    """
    blockers = []
    for q in ssot.get("queues", []):
        if q.get("block", 0) > 0:
            blockers.append({"source": q["id"], "count": q["block"], "ref": q["queueFile"]})
    total_block = ssot.get("totals", {}).get("block", 0)

    # fr-cluster-trace gate state = determined by the fr-cluster queue BLOCK count (mismatch blocks).
    frc = next((q for q in ssot.get("queues", []) if q.get("id") == "fr-cluster"), None)
    frc_block = frc.get("block", 0) if frc else 0
    frc_ref = frc.get("queueFile", "reports/fr-cluster-queue.md") if frc \
        else "reports/fr-cluster-queue.md"

    estimated = current_phase is None
    if estimated:
        current_phase = 2 if total_block > 0 else 3

    gates = []
    for name in gate_names:
        if name == "draft-complete":
            gates.append({
                "id": name, "phaseBoundary": "2→3",
                "state": "blocked" if total_block else "pass",
                "passed": max(0, 5 - len(blockers)) if total_block else 5,
                "total": 5, "blockers": blockers,
            })
        elif name == "fr-cluster-trace":
            # FR↔cluster traceability: blocked if a mismatch (BLOCK) exists, otherwise passes.
            frc_blockers = (
                [{"source": "fr-cluster", "count": frc_block, "ref": frc_ref}]
                if frc_block else []
            )
            gates.append({
                "id": name, "phaseBoundary": "3→4",
                "state": "blocked" if frc_block else "pass",
                "passed": 0 if frc_block else 1,
                "total": 1, "blockers": frc_blockers,
            })
        else:
            gates.append({"id": name, "phaseBoundary": "", "state": "pass",
                          "passed": 1, "total": 1, "blockers": []})
    return {
        "version": "", "product": product, "kind": "gates",
        "currentPhase": current_phase,
        "phaseEstimated": estimated,
        "phases": _phases(current_phase),
        "gates": gates,
        "recommended": [{"label": "Verify gates", "cmd": "/lc", "arg": product}],
    }


def main(argv: list[str]) -> int:
    args = C.make_parser("gate").parse_args(argv)
    if args.from_fixture:
        return C.emit(C.load_fixture(args.from_fixture))
    if not (args.hub_root and args.product):
        sys.stderr.write("--hub-root, --product required\n")
        return 2
    # reuse ssot queue aggregation
    rdir = C.product_dir(args.hub_root, args.product) / "reports"

    def read_queue(fname: str):
        p = rdir / fname
        return p.read_text(encoding="utf-8") if p.exists() else None

    ssot = ssot_emit.transform_ssot(read_queue, args.product)

    gates_dir = Path(args.hub_root) / "CONTEXT" / "gates"
    gate_names = sorted(p.stem.replace("-gate", "") for p in gates_dir.glob("*.md")) \
        if gates_dir.is_dir() else ["draft-complete"]
    if "draft-complete" not in gate_names:
        gate_names.append("draft-complete")
    if "fr-cluster-trace" not in gate_names:
        gate_names.append("fr-cluster-trace")

    return C.emit(transform_gates(ssot, gate_names, args.product))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
