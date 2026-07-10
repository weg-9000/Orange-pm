#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ssot_emit — drift/policy-impact/mtg 큐 헤더 → 정규화 ssot-status 계약 (§3).

BLOCK 등가: drift BLOCK + policy-impact IMPACT + mtg FAIL/BLOCK. WARN 은 표시만.

라이브 SSoT-status 어댑터 (/next → next_emit.py 경유). build_ssot_status.py 의
후속 구현이며, 큐 스코프(5개 큐 + viz JSON)의 권위 기준은 본 스크립트다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import _emit_common as C

# (id, 제목, 큐 파일, BLOCK 등가 라벨, WARN 등가 라벨)
QUEUES = [
    ("drift", "Drift", "drift-queue.md", ("BLOCK",), ("WARN", "UNRESOLVED")),
    ("policy-impact", "Policy Impact", "policy-impact-queue.md", ("IMPACT",), ("WARN", "COARSE")),
    ("mtg", "MTG Ledger", "mtg-queue.md", ("FAIL", "BLOCK"), ("WARN",)),
    ("bdd-coverage", "BDD Coverage", "bdd-coverage-queue.md", ("UNCOVERED", "STALE"), ("WARN",)),
    ("fr-cluster", "FR-Cluster Trace", "fr-cluster-queue.md", ("BLOCK",), ("WARN",)),
]


def transform_ssot(read_queue, product: str = "") -> dict:
    """read_queue(filename)->str|None 로 각 큐 본문을 받아 계약 생성."""
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
        # 라벨은 'WARN/UNRESOLVED' 처럼 결합될 수 있어 '/' 분해 후 교집합으로 집계.
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
        sys.stderr.write("--hub-root, --product 필요\n")
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
