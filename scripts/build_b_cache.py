#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the {PREFIX}-B common policy document summary cache (Improvement A — CONTEXT_OPTIMIZATION.md).

Purpose:
    Eliminate the inefficiency of /write, /flow, /integrate reloading the
    entire CONTEXT/reference-docs/B/*.md set on every invocation. From each
    policy document, extract only the "## " headings plus the first
    paragraph right after each heading (up to 3 lines), merge them into a
    single summary, and save it to .template-cache/B-summary.md.

    Skills use it in the following order:
      1) If B-summary.md's mtime is newer than every reference-docs/B/*.md, load the cache only.
      2) Otherwise, regenerate the cache with this script, then load the cache only.
    Loading the full original text happens only in excerpt mode based on the
    heading index (B-headings-index.json).

Usage:
    python build_b_cache.py --hub-root <Planning-Agent-Hub path>

exit code:
    0 = success (cache freshly generated or confirmed up to date)
    1 = failed to extract PREFIX from layer-config.md, or reference-docs/B missing
    2 = argument error
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from _cache_utils import (
    HEADING_PATTERN,
    cache_is_fresh,
    discover_b_sources,
    ensure_cache_dir,
    make_hub_root_parser,
    read_prefix,
    validate_hub_root,
)


def extract_summary(md_text: str, max_para_lines: int = 3) -> list[str]:
    """Extract only the heading plus the first paragraph right after it (up to the blank line, max max_para_lines lines)."""
    lines = md_text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if HEADING_PATTERN.match(line):
            out.append(line)
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            para_lines: list[str] = []
            while j < len(lines) and lines[j].strip() and not HEADING_PATTERN.match(lines[j]):
                para_lines.append(lines[j])
                if len(para_lines) >= max_para_lines:
                    break
                j += 1
            if para_lines:
                out.append("")
                out.extend(para_lines)
            out.append("")
            i = j
            continue
        i += 1
    return out


def _advise_drift(hub_root: Path) -> None:
    """Chain into drift_scan on a best-effort basis after the cache is rebuilt.

    A refreshed common (B) cache signals that a B source may have changed, so
    re-check the referenced_master pins of affected product drafts.
    Passes silently if it fails or PROJECTS doesn't exist (build's exit code is unaffected).
    """
    try:
        if not (hub_root / "PROJECTS").is_dir():
            return
        import importlib.util
        ds_path = Path(__file__).with_name("drift_scan.py")
        if not ds_path.exists():
            return
        spec = importlib.util.spec_from_file_location("drift_scan", ds_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        rc = mod.scan(hub_root)
        if rc:
            print("[build_b_cache] drift BLOCK found — recommend checking reports/drift-queue.md")
    except Exception as exc:  # a chaining failure must not block the cache build
        print(f"[build_b_cache] skipped drift_scan chaining ({exc})")


def build(hub_root: Path) -> int:
    prefix = read_prefix(hub_root)
    sources = discover_b_sources(hub_root)
    cache_dir = ensure_cache_dir(hub_root)
    # PREFIX-namespaced cache (primary) + legacy non-namespaced cache (secondary, active PREFIX only).
    cache_path = cache_dir / f"{prefix}-b-summary.md"
    legacy_path = cache_dir / "B-summary.md"

    if cache_is_fresh(cache_path, sources) and legacy_path.exists():
        print(f"[build_b_cache] up-to-date: {cache_path}")
        _advise_drift(hub_root)
        return 0

    parts: list[str] = [
        f"# {prefix}-B Summary Cache (auto-generated)",
        "",
        "> This file is an auto-generated summary from build_b_cache.py. Do not edit directly.",
        f"> Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"> Source: CONTEXT/reference-docs/{prefix}/B/ ({len(sources)} document(s))",
        "",
    ]
    for src in sources:
        parts.append(f"## ── {src.name} ──")
        parts.append("")
        parts.extend(extract_summary(src.read_text(encoding="utf-8")))
        parts.append("")

    payload = "\n".join(parts)
    cache_path.write_text(payload, encoding="utf-8")
    # legacy compat: mirror the active PREFIX summary into the non-namespaced file too (for older skills to reference).
    legacy_path.write_text(payload, encoding="utf-8")
    print(f"[build_b_cache] wrote {cache_path} (+legacy {legacy_path.name}, {len(sources)} sources)")
    _advise_drift(hub_root)
    return 0


def main() -> int:
    parser = make_hub_root_parser("Build {PREFIX}-B summary cache")
    args = parser.parse_args()
    rc = validate_hub_root(args.hub_root)
    if rc:
        return rc
    return build(args.hub_root)


if __name__ == "__main__":
    sys.exit(main())
