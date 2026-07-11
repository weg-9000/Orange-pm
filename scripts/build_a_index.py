#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the {PREFIX}-A terms reverse index (multi-PREFIX SaaS Phase 1).

Purpose:
    Build a "term -> {file, line, short definition}" reverse index from the
    A layer (terminology/principles reference), used for term validation and
    precise reference (L2) when authoring screens/policies.
    This is the A-layer counterpart of build_b_index.py (B heading index).

    Output: CONTEXT/.template-cache/{PREFIX}-a-terms-index.json

Extraction heuristics (deterministic):
    1) Markdown table row: `| term | definition ... |` (header/separator rows excluded)
    2) Definition line: `- **term**: definition` / `**term** — definition` / `**term**: definition`
    Definitions are truncated to 80 chars max. On duplicate terms, first occurrence wins.

Usage:
    python build_a_index.py --hub-root <path to Planning-Agent-Hub>

exit code:
    0 = success (empty index is still a success when there are 0 A documents)
    1 = PREFIX extraction failed
    2 = argument error
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from _cache_utils import (
    discover_layer_sources,
    ensure_cache_dir,
    make_hub_root_parser,
    read_active_prefix,
    validate_hub_root,
)

# `| term | definition |` table row — matched when there are 2+ cells and it's not a separator (---).
TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
# `- **term**: definition` / `**term** — definition` / `**term**: definition`
BOLD_DEF = re.compile(r"^\s*[-*]?\s*\*\*\s*(?P<term>[^*]+?)\s*\*\*\s*[:：—\-]\s*(?P<def>.+?)\s*$")

_HEADER_HINTS = ("term", "definition", "description", "용어", "정의", "설명")


def _truncate(text: str, limit: int = 80) -> str:
    text = re.sub(r"\s+", " ", text).strip().strip("`")
    return text[:limit]


def _is_separator_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in cells if c.strip())


def extract_terms(md_text: str, file_rel: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    lines = md_text.splitlines()
    in_table_body = False
    table_is_glossary = False
    for idx, line in enumerate(lines, start=1):
        tm = TABLE_ROW.match(line)
        if tm:
            cells = [c.strip() for c in tm.group(1).split("|")]
            if _is_separator_row(cells):
                in_table_body = True
                continue
            # Header row detection — treat the body as a glossary table if the header looks like a term/definition header.
            if not in_table_body:
                joined = " ".join(cells).lower()
                table_is_glossary = any(h in joined for h in _HEADER_HINTS)
                continue
            if in_table_body and table_is_glossary and len(cells) >= 2:
                term = _truncate(cells[0], 60)
                definition = _truncate(cells[1])
                if term and term not in out:
                    out[term] = {"file": file_rel, "line": idx, "def": definition}
            continue
        else:
            in_table_body = False
            table_is_glossary = False

        bm = BOLD_DEF.match(line)
        if bm:
            term = _truncate(bm.group("term"), 60)
            definition = _truncate(bm.group("def"))
            if term and term not in out:
                out[term] = {"file": file_rel, "line": idx, "def": definition}
    return out


def build(hub_root: Path) -> int:
    prefix = read_active_prefix(hub_root)
    sources = discover_layer_sources(hub_root, prefix, "A")
    cache_dir = ensure_cache_dir(hub_root)
    out_path = cache_dir / f"{prefix}-a-terms-index.json"

    terms: dict[str, dict] = {}
    for src in sources:
        rel = str(src.relative_to(hub_root).as_posix())
        for term, meta in extract_terms(src.read_text(encoding="utf-8", errors="replace"), rel).items():
            terms.setdefault(term, meta)

    payload = {
        "_meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "prefix": prefix,
            "source_count": len(sources),
            "term_count": len(terms),
        },
        "terms": terms,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[build_a_index] wrote {out_path} (terms={len(terms)}, sources={len(sources)})")
    return 0


def main() -> int:
    parser = make_hub_root_parser("Build {PREFIX}-A terms reverse index")
    args = parser.parse_args()
    rc = validate_hub_root(args.hub_root)
    if rc:
        return rc
    return build(args.hub_root)


if __name__ == "__main__":
    sys.exit(main())
