#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Infer inter-document dependencies -> candidate edges (multi-tenant SaaS Phase 2).

Purpose:
    Relax the requirement for explicit inherits_from/includes edges. Detects
    cross-document reference signals in imported document bodies and infers
    candidate edges compatible with graph-schema.json. These remain mere
    candidates (confidence) until the PM reviews and confirms them.

Signal -> edge type:
    "[{ID} §X 참조]" / "{ID} 를 전제" -> inherits_from  (high — explicit ID)
    "공통 정책 ... 포함/include"        -> includes      (medium)
    plain mention of a doc_id token in body -> references (low)

Reuse:
    - drift_scan's PIN/master-id-map resolution pattern (lightweight
      self-contained implementation here)
    - templates/graph-schema.json edge schema (source/target/type/description)

Usage:
    python dependency_infer.py --hub-root <Hub> --input X.md --doc-id SELF [--json]

exit code: 0 success / 1 no input / 2 argument error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# doc_id token: {PREFIX}-{A|B|C}-{seq}
DOC_ID = re.compile(r"\b([A-Za-z0-9]+-[ABC]-\d+)\b")
# Explicit reference: [ID ... 참조] / [ID §X]
REF_BRACKET = re.compile(r"\[([A-Za-z0-9]+-[ABC]-\d+)[^\]]*\]")
# Prerequisite/inheritance expressions
INHERIT_HINT = re.compile(r"전제|상속|inherits_from|기반으로|따른다")
INCLUDE_HINT = re.compile(r"포함|include|재사용|공통\s*모듈")


def _load_alias_map(hub_root: Path) -> dict:
    p = hub_root / "CONTEXT" / "reference-docs" / "master-id-map.yml"
    amap: dict = {}
    if not p.exists():
        return amap
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        amap[k.strip()] = v.strip().strip("'\"")
    return amap


def infer_edges(text: str, self_doc_id: str, amap: dict | None = None) -> list[dict]:
    """Infer a list of candidate edges from the body text. Removes self-references and keeps only the strongest edge per target."""
    amap = amap or {}
    edges: dict[str, dict] = {}  # target -> strongest edge
    conf_rank = {"low": 0, "medium": 1, "high": 2}
    type_rank = {"references": 0, "includes": 1, "inherits_from": 2}

    def add(target: str, etype: str, conf: str, desc: str) -> None:
        if not target or target == self_doc_id:
            return
        cur = edges.get(target)
        if cur is not None:
            # Prefer stronger confidence first, then a stronger type.
            if (conf_rank[conf], type_rank[etype]) <= (
                conf_rank[cur["confidence"]], type_rank[cur["type"]]
            ):
                return
        edges[target] = {
            "source": self_doc_id,
            "target": target,
            "type": etype,
            "confidence": conf,
            "resolved_stem": amap.get(target, ""),
            "description": desc,
        }

    for ln in text.splitlines():
        for m in REF_BRACKET.finditer(ln):
            tid = m.group(1)
            if INHERIT_HINT.search(ln):
                add(tid, "inherits_from", "high", "explicit reference + prerequisite/inheritance expression")
            elif INCLUDE_HINT.search(ln):
                add(tid, "includes", "high", "explicit reference + include/reuse expression")
            else:
                add(tid, "references", "high", "explicit bracketed reference")
    # Plain mention in body (outside brackets) -> references(low)
    for m in DOC_ID.finditer(text):
        add(m.group(1), "references", "low", "doc_id mention in body")

    return list(edges.values())


def main() -> int:
    ap = argparse.ArgumentParser(description="Infer inter-document dependencies -> candidate edges")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--doc-id", required=True, help="doc_id of the input document itself")
    ap.add_argument("--out", type=Path, default=None, help="Path to save the candidate edges JSON")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    if not args.input.is_file():
        sys.stderr.write(f"input not found: {args.input}\n")
        return 1
    amap = _load_alias_map(args.hub_root)
    edges = infer_edges(args.input.read_text(encoding="utf-8", errors="replace"),
                        args.doc_id, amap)
    payload = {"doc_id": args.doc_id, "edge_count": len(edges), "edges": edges}
    if args.out:
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[dependency_infer] wrote {args.out} (edges={len(edges)})")
    elif args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[dependency_infer] {args.input.name}: {len(edges)} candidate edges")
        for e in edges:
            print(f"  {e['source']} --{e['type']}({e['confidence']})--> {e['target']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
