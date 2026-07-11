#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ssot_emit — drift/policy-impact/mtg queue headers -> normalized ssot-status contract (§3).

BLOCK equivalents: drift BLOCK + policy-impact IMPACT + mtg FAIL/BLOCK. WARN is display-only.

The live SSoT-status adapter (/next -> via next_emit.py). Successor to
build_ssot_status.py; this script is the authority for queue scope (5 queues + viz JSON).
"""
from __future__ import annotations

import sys
from pathlib import Path

import _emit_common as C

# (id, title, queue file, BLOCK-equivalent labels, WARN-equivalent labels)
QUEUES = [
    ("drift", "Drift", "drift-queue.md", ("BLOCK",), ("WARN", "UNRESOLVED")),
    ("policy-impact", "Policy Impact", "policy-impact-queue.md", ("IMPACT",), ("WARN", "COARSE")),
    ("mtg", "MTG Ledger", "mtg-queue.md", ("FAIL", "BLOCK"), ("WARN",)),
    ("bdd-coverage", "BDD Coverage", "bdd-coverage-queue.md", ("UNCOVERED", "STALE"), ("WARN",)),
    ("fr-cluster", "FR-Cluster Trace", "fr-cluster-queue.md", ("BLOCK",), ("WARN",)),
]


def transform_ssot(read_queue, product: str = "") -> dict:
    """Builds the contract, receiving each queue's body via read_queue(filename)->str|None."""
    out_q = []
    total_block = 0
    total_warn = 0
    for qid, title, fname, block_labels, warn_labels in QUEUES:
        text = read_queue(fname)
        if text is None:
            out_q.append({"id": qid, "title": title, "block": 0, "warn": 0,
                          "status": "MISSING", "queueFile": f"reports/{fname}"})
            continue
        counts = C.parse_header_counts(text)
        # Labels can be combined like 'WARN/UNRESOLVED', so split on '/' and aggregate by intersection.
        bset, wset = set(block_labels), set(warn_labels)
        block = sum(v for k, v in counts.items() if bset & set(k.split("/")))
        warn = sum(v for k, v in counts.items() if wset & set(k.split("/")))
        total_block += block
        total_warn += warn
        out_q.append({
            "id": qid, "title": title, "block": block, "warn": warn,
            "status": "BLOCK" if block else "PASS",
            "queueFile": f"reports/{fname}",
        })
    return {
        "version": "", "product": product, "kind": "ssot-status",
        "totals": {"block": total_block, "warn": total_warn},
        "gatePass": total_block == 0,
        "queues": out_q,
    }


def main(argv: list[str]) -> int:
    args = C.make_parser("ssot").parse_args(argv)
    if args.from_fixture:
        return C.emit(C.load_fixture(args.from_fixture))
    if not (args.hub_root and args.product):
        sys.stderr.write("--hub-root, --product required\n")
        return 2
    rdir = C.product_dir(args.hub_root, args.product) / "reports"

    def read_queue(fname: str):
        p = rdir / fname
        return p.read_text(encoding="utf-8") if p.exists() else None

    result = transform_ssot(read_queue, args.product)
    code = 0 if any(q["status"] != "MISSING" for q in result["queues"]) else 1
    C.emit(result)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
