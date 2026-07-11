#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the {PREFIX}-B heading index (Improvement Plan B — CONTEXT_OPTIMIZATION.md).

Purpose:
    Build a heading-location index so that /write and /flow can selectively
    excerpt-load only the sections listed in graph.json's inherits_from /
    includes.

    Output: CONTEXT/.template-cache/B-headings-index.json

    Schema:
      {
        "G2-B-001": {
          "title": "...",
          "path": "CONTEXT/reference-docs/B/G2-B_xxx.md",
          "sections": [
            {"id": "1",   "title": "Overview",        "line_start": 5,   "line_end": 38},
            {"id": "3.2", "title": "Resource limits", "line_start": 142, "line_end": 197}
          ]
        }
      }

    section.id is extracted from a leading number in the heading text, e.g.
    "## 1. Overview" / "## 3.2 Resource limit calculation". Headings without a
    number get a slug instead (spaces -> -).

    line numbers are 1-based; line_end is the line just before the next
    heading of the same or a shallower depth. If it runs to the end of the
    file, it's the last line number.

Usage:
    python build_b_index.py --hub-root <path to Planning-Agent-Hub>

exit code:
    0 = success
    1 = failed to extract PREFIX, or reference-docs/B missing
    2 = argument error
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from _cache_utils import (
    HEADING_PATTERN,
    discover_b_sources,
    ensure_cache_dir,
    make_hub_root_parser,
    read_prefix,
    validate_hub_root,
)

LEADING_NUMBER_PATTERN = re.compile(r"^(?:§\s*)?(\d+(?:\.\d+)*)[\s.\)]\s*(.*)$")
# doc_id priority:
#   1) an explicit identifier in frontmatter or the top of the body (e.g. "doc_id: G2-B-001")
#   2) if the filename stem matches the G2-B-001 pattern, use it as-is
#   3) fallback: the file stem as-is (don't add PREFIX again)
EXPLICIT_DOC_ID_PATTERN = re.compile(r"(?:^|\n)\s*doc_id\s*[:：]\s*([A-Za-z0-9_-]+)\s*(?:\n|$)")
CANONICAL_DOC_ID_PATTERN = re.compile(r"^([A-Za-z0-9]+)-B-(\d{3,})$")


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[\s/]+", "-", text.strip())
    slug = re.sub(r"[^0-9A-Za-z\-가-힣]", "", slug)
    return slug[:max_len] or "section"


def split_section_id(heading_text: str, fallback_idx: int) -> tuple[str, str]:
    match = LEADING_NUMBER_PATTERN.match(heading_text.strip())
    if match:
        return match.group(1), match.group(2).strip() or heading_text.strip()
    return f"_{fallback_idx}-{slugify(heading_text)}", heading_text.strip()


def derive_doc_id(prefix: str, file_path: Path, body_text: str) -> str:
    """Extract doc_id from the file. Falls back to the file stem if there's no identifier.

    The index key is a plain identifier. Its mapping to graph.json's
    inherits_from (e.g. G2-B-001) is handled separately by layer-config.md or
    reference-docs/B/README.md.
    """
    explicit = EXPLICIT_DOC_ID_PATTERN.search(body_text[:1024])
    if explicit:
        return explicit.group(1)
    if CANONICAL_DOC_ID_PATTERN.match(file_path.stem):
        return file_path.stem
    return file_path.stem


def index_one(file_path: Path, prefix: str) -> dict:
    body = file_path.read_text(encoding="utf-8")
    lines = body.splitlines()
    headings: list[tuple[int, int, str]] = []  # (line_idx_0based, depth, raw_title)
    for idx, line in enumerate(lines):
        match = HEADING_PATTERN.match(line)
        if not match:
            continue
        depth = len(match.group(1))
        if depth < 2:
            continue  # skip H1 (document title); sections start at ## or deeper
        headings.append((idx, depth, match.group(2)))

    sections: list[dict] = []
    title = ""
    for h_idx, (line_idx, depth, raw_title) in enumerate(headings):
        sec_id, sec_title = split_section_id(raw_title, fallback_idx=h_idx)
        end_line_0 = len(lines) - 1
        for next_idx, next_depth, _ in headings[h_idx + 1 :]:
            if next_depth <= depth:
                end_line_0 = next_idx - 1
                break
        sections.append(
            {
                "id": sec_id,
                "title": sec_title,
                "depth": depth,
                "line_start": line_idx + 1,
                "line_end": end_line_0 + 1,
            }
        )
        if h_idx == 0 and depth == 2:
            title = sec_title
    if not title:
        # H1 fallback
        for line in lines[:5]:
            m = HEADING_PATTERN.match(line)
            if m and len(m.group(1)) == 1:
                title = m.group(2).strip()
                break

    doc_id = derive_doc_id(prefix, file_path, body)
    return {
        "doc_id": doc_id,
        "title": title or file_path.stem,
        "path": str(file_path.as_posix()),
        "lines_total": len(lines),
        "sections": sections,
    }


def build(hub_root: Path) -> int:
    prefix = read_prefix(hub_root)
    sources = discover_b_sources(hub_root)
    cache_dir = ensure_cache_dir(hub_root)
    # PREFIX-namespaced (primary) + legacy non-namespaced (secondary, active PREFIX only).
    out_path = cache_dir / f"{prefix}-b-headings-index.json"
    legacy_path = cache_dir / "B-headings-index.json"

    index: dict[str, dict] = {}
    source_dir = ""
    for src in sources:
        rel_src = src.relative_to(hub_root)
        entry = index_one(src, prefix)
        # normalize path to be relative to hub-root
        entry["path"] = str(rel_src.as_posix())
        index[entry["doc_id"]] = entry
        source_dir = str(rel_src.parent.as_posix())

    payload = {
        "_meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "prefix": prefix,
            "source_dir": (source_dir + "/") if source_dir else "CONTEXT/reference-docs/B/",
            "doc_count": len(index),
        },
        "documents": index,
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    out_path.write_text(serialized, encoding="utf-8")
    # Legacy compat: also mirror the active PREFIX index to a non-namespaced file (for render_assemble, etc.).
    legacy_path.write_text(serialized, encoding="utf-8")
    print(f"[build_b_index] wrote {out_path} (+legacy {legacy_path.name}, docs={len(index)})")
    return 0


def main() -> int:
    parser = make_hub_root_parser("Build {PREFIX}-B headings index")
    args = parser.parse_args()
    rc = validate_hub_root(args.hub_root)
    if rc:
        return rc
    return build(args.hub_root)


if __name__ == "__main__":
    sys.exit(main())
