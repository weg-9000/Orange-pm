#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the consolidated Session Bootstrap file (improvement F — CONTEXT_OPTIMIZATION.md).

Purpose:
    Replaces the structure where Hub/.claude/CLAUDE.md forced sequential loading
    of 6 files at session start with a single consolidated file,
    _session-bootstrap.md, read once. Every skill SKILL.md reads this file
    exactly once per session and never re-reads it.

    Output: CONTEXT/_session-bootstrap.md
    Included source files (regenerated automatically on change):
      - layer-config.md
      - about-pm.md
      - project-rules.md
      - brand-voice.md
      - doc-layer-schema.md
      - team-members.md

    Cache invalidation:
      If any of the 6 files above has an mtime newer than
      _session-bootstrap.md, regenerate. Missing files emit only a
      placeholder block and processing continues.

Usage:
    python build_bootstrap.py --hub-root <Planning-Agent-Hub path>

exit code:
    0 = success
    2 = argument error
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from _cache_utils import (
    cache_is_fresh,
    make_hub_root_parser,
    validate_hub_root,
)

SOURCES = [
    "layer-config.md",
    "about-pm.md",
    "project-rules.md",
    "brand-voice.md",
    "doc-layer-schema.md",
    "team-members.md",
]


def build(hub_root: Path) -> int:
    context_dir = hub_root / "CONTEXT"
    if not context_dir.is_dir():
        sys.stderr.write(f"CONTEXT/ not found: {context_dir}\n")
        return 1

    sources = [context_dir / name for name in SOURCES]
    out_path = context_dir / "_session-bootstrap.md"

    if cache_is_fresh(out_path, sources, allow_missing_sources=True):
        print(f"[build_bootstrap] up-to-date: {out_path}")
        return 0

    parts: list[str] = [
        "# Session Bootstrap (auto-generated, do not edit directly)",
        "",
        "> This file is generated automatically by build_bootstrap.py.",
        f"> Generated at: {datetime.now().isoformat(timespec='seconds')}",
        "> To change it, edit the source CONTEXT/*.md files and re-run build_bootstrap.py.",
        "",
        "## Usage rules",
        "- Each skill SKILL.md reads this file once per session and never re-reads it.",
        "- Context guaranteed by this file: PREFIX, PM profile, planning principles,",
        "  tone standards, document schema, stakeholder roster.",
        "- Skills needing extra context load it separately in their own prerequisite step.",
        "",
    ]

    found = 0
    missing: list[str] = []
    for src in sources:
        parts.append(f"---\n\n## SOURCE — {src.name}")
        parts.append("")
        if not src.exists():
            parts.append(f"> ⚠️ `{src.name}` missing. Run /init-hub, then invoke build_bootstrap.py again.")
            parts.append("")
            missing.append(src.name)
            continue
        parts.append(src.read_text(encoding="utf-8").rstrip())
        parts.append("")
        found += 1

    out_path.write_text("\n".join(parts), encoding="utf-8")
    msg = f"[build_bootstrap] wrote {out_path} (sources={found}/{len(sources)}"
    if missing:
        msg += f", missing={','.join(missing)}"
    msg += ")"
    print(msg)
    return 0


def main() -> int:
    parser = make_hub_root_parser("Build _session-bootstrap.md")
    args = parser.parse_args()
    rc = validate_hub_root(args.hub_root)
    if rc:
        return rc
    return build(args.hub_root)


if __name__ == "__main__":
    sys.exit(main())
