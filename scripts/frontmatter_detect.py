#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auto-detect and normalize frontmatter in arbitrary markdown (multi-tenant SaaS Phase 2).

Purpose:
    Arbitrary markdown imported from external sources (Confluence/GitLab/Notion)
    may have missing or non-standard frontmatter. This module detects whether
    frontmatter is present, and normalizes it to a *reference* schema for
    imported documents (the body is left unmodified — only metadata is attached).

    Unlike the draft's 9 fields (migrate_draft_frontmatter), imported documents
    use this schema:
        doc_id, title, layer(A|B|C|unknown), version, status, source, source_url,
        imported_at, original_metadata

    status: ingested -> normalized (metadata normalized) -> analyzed (classification done)

Usage:
    python frontmatter_detect.py --input X.md [--source confluence] [--source-url URL]
        [--doc-id ID] [--in-place] [--report]

exit code:
    0 = success
    1 = input file not found
    2 = argument error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)

REFERENCE_FIELDS = [
    "doc_id",
    "title",
    "layer",
    "version",
    "status",
    "source",
    "source_url",
    "imported_at",
    "original_metadata",
]

# Multi-format meta extraction (mirrors the drift_scan pattern): YAML / bold inline / table.
_DOC_ID_BOLD = re.compile(
    r"\*\*\s*(?:doc\s*id|문서\s*ID|doc_id)\s*[:：]?\s*\*\*\s*[:：]?\s*`?([A-Za-z0-9._-]+)`?", re.I
)
_DOC_ID_TABLE = re.compile(r"\|\s*\*\*\s*doc_id\s*\*\*\s*\|\s*`?([A-Za-z0-9._-]+)`?", re.I)
_VER_BOLD = re.compile(
    r"\*\*\s*(?:version|버전)\s*[:：]?\s*\*\*\s*[:：]?\s*`?([0-9]+(?:\.[0-9]+)*)`?", re.I
)
_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def detect_frontmatter(text: str) -> tuple[dict, str, bool]:
    """Return (frontmatter dict, body, had_frontmatter). If absent, return ({}, text, False)."""
    m = FRONTMATTER.match(text)
    if not m:
        return {}, text, False
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, text[m.end():], True


def _extract_meta_from_body(head: str) -> dict:
    """When there's no frontmatter, heuristically extract doc_id/version/title from the top of the body."""
    out: dict = {}
    dm = _DOC_ID_BOLD.search(head) or _DOC_ID_TABLE.search(head)
    if dm:
        out["doc_id"] = dm.group(1).strip()
    vm = _VER_BOLD.search(head)
    if vm:
        out["version"] = vm.group(1).strip()
    tm = _H1.search(head)
    if tm:
        out["title"] = tm.group(1).strip()
    return out


def normalize(
    text: str,
    *,
    source: str = "",
    source_url: str = "",
    doc_id: str = "",
    layer: str = "unknown",
    imported_at: str = "",
) -> tuple[str, dict]:
    """Normalize an imported MD file to reference frontmatter. The body is left unmodified.

    Returns: (normalized full text, inference report dict).
    """
    fm, body, had_fm = detect_frontmatter(text)
    body_meta = _extract_meta_from_body(body[:4000])

    inferred: list[str] = []
    out: dict = {}

    def pick(*cands: str) -> str:
        for c in cands:
            if c:
                return c
        return ""

    out["doc_id"] = pick(doc_id, fm.get("doc_id", ""), body_meta.get("doc_id", ""))
    if not out["doc_id"]:
        inferred.append("doc_id(unknown — placeholder)")
        out["doc_id"] = "UNCLASSIFIED"
    out["title"] = pick(fm.get("title", ""), body_meta.get("title", ""), out["doc_id"])
    out["layer"] = pick(layer if layer != "unknown" else "", fm.get("layer", ""), "unknown")
    out["version"] = pick(fm.get("version", ""), body_meta.get("version", ""))
    if not out["version"]:
        inferred.append("version(unknown)")
        out["version"] = "0.0.0"
    out["status"] = "normalized"
    out["source"] = pick(source, fm.get("source", ""))
    out["source_url"] = pick(source_url, fm.get("source_url", ""))
    out["imported_at"] = pick(imported_at, fm.get("imported_at", ""), date.today().isoformat())

    # Non-standard fields from the original frontmatter are preserved losslessly in original_metadata.
    extra = {k: v for k, v in fm.items() if k not in REFERENCE_FIELDS}
    out["original_metadata"] = json.dumps(extra, ensure_ascii=False) if extra else "{}"

    lines = ["---"]
    for f in REFERENCE_FIELDS:
        lines.append(f"{f}: {out[f]}")
    lines.append("---")
    normalized = "\n".join(lines) + "\n" + body.lstrip("\n")

    report = {
        "had_frontmatter": had_fm,
        "inferred": inferred,
        "fields": out,
    }
    return normalized, report


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect and normalize frontmatter in an arbitrary MD file")
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--source", default="")
    ap.add_argument("--source-url", default="")
    ap.add_argument("--doc-id", default="")
    ap.add_argument("--layer", default="unknown")
    ap.add_argument("--in-place", action="store_true", help="Overwrite the input file with the normalized result")
    ap.add_argument("--report", action="store_true", help="Print the inference report as JSON")
    args = ap.parse_args()
    if not args.input.is_file():
        sys.stderr.write(f"input not found: {args.input}\n")
        return 1
    text = args.input.read_text(encoding="utf-8", errors="replace")
    normalized, report = normalize(
        text, source=args.source, source_url=args.source_url,
        doc_id=args.doc_id, layer=args.layer,
    )
    if args.in_place:
        args.input.write_text(normalized, encoding="utf-8")
        print(f"[frontmatter_detect] normalized in place: {args.input}")
    else:
        sys.stdout.write(normalized)
    if args.report:
        sys.stderr.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
