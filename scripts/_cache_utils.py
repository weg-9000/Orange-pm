#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for cache build scripts (build_b_cache / build_b_index / build_bootstrap).

This module centralizes the logic that used to be duplicated across the three
cache build scripts. Script-specific logic (summary extraction, heading
indexing, source listing, etc.) stays in each individual script.

Design principles:
    - Each helper should have few dependencies and clear side effects.
    - sys.exit() is only called from a script's main(). Helpers report
      failures via exceptions or explicit return values (currently only
      read_prefix keeps sys.exit, for backward compatibility).
    - This module never prints to the screen.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Shared regexes (used identically by build_b_cache / build_b_index).
# Note: ``^PREFIX:`` only matches the legacy single declaration where the line
# starts with exactly ``PREFIX:``. ``ACTIVE_PREFIX:`` and ``PREFIXES:`` have a
# different leading token so they don't match (intentional isolation).
PREFIX_PATTERN = re.compile(r"^PREFIX:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)
ACTIVE_PREFIX_PATTERN = re.compile(r"^ACTIVE_PREFIX:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)
PREFIXES_ITEM_PATTERN = re.compile(r"^\s*-\s*id:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _read_layer_config(hub_root: Path) -> str:
    """Read the body of CONTEXT/layer-config.md. Calls ``sys.exit(1)`` if missing."""
    config = hub_root / "CONTEXT" / "layer-config.md"
    if not config.exists():
        sys.stderr.write(f"layer-config.md not found: {config}\n")
        sys.exit(1)
    return config.read_text(encoding="utf-8")


def read_active_prefix(hub_root: Path) -> str:
    """Return the PREFIX the current session is working on.

    Priority:
      1) ``ACTIVE_PREFIX: <value>``  (multi-PREFIX format, Phase 1+)
      2) ``PREFIX: <value>``         (legacy single declaration)

    If neither is present, writes to stderr then ``sys.exit(1)`` (same exit
    signal as the original read_prefix).
    """
    text = _read_layer_config(hub_root)
    m = ACTIVE_PREFIX_PATTERN.search(text)
    if m:
        return m.group(1)
    m = PREFIX_PATTERN.search(text)
    if m:
        return m.group(1)
    sys.stderr.write(
        "PREFIX/ACTIVE_PREFIX not declared in layer-config.md "
        "(expected `PREFIX: <value>` or `ACTIVE_PREFIX: <value>`)\n"
    )
    sys.exit(1)


def read_prefixes(hub_root: Path) -> list[str]:
    """Return the full list of declared PREFIXes (multi-PREFIX, Phase 1+).

    Collects the ``- id: <value>`` entries of the ``PREFIXES:`` block in order.
    If the block is absent, falls back to the single PREFIX
    ([read_active_prefix()]) for backward compatibility.
    """
    text = _read_layer_config(hub_root)
    ids = PREFIXES_ITEM_PATTERN.findall(text)
    if ids:
        return ids
    return [read_active_prefix(hub_root)]


def read_prefix(hub_root: Path) -> str:
    """[Backward-compat wrapper] Return the current active PREFIX.

    Preserves the signature that existing scripts (build_b_cache /
    build_b_index, etc.) call. Delegates internally to ``read_active_prefix``,
    so it automatically reflects the ACTIVE_PREFIX migration.
    """
    return read_active_prefix(hub_root)


def discover_layer_sources(hub_root: Path, prefix: str, layer: str) -> list[Path]:
    """Collect the markdown sources for a given (prefix, layer) under ``reference-docs``.

    Dual-path lookup (safety net for gradual migration):
      1) New nested layout: ``CONTEXT/reference-docs/{prefix}/{layer}/*.md``
      2) Legacy flat layout: ``CONTEXT/reference-docs/{layer}/*.md``
    If the new path exists as a directory, use it; otherwise fall back to the
    legacy path.

    Excludes README.md and returns a sorted list. Returns an empty list if the
    directory doesn't exist (does not exit — lets the caller decide the
    missing-source policy).
    """
    base = hub_root / "CONTEXT" / "reference-docs"
    nested = base / prefix / layer
    legacy = base / layer
    src_dir = nested if nested.is_dir() else legacy
    if not src_dir.is_dir():
        return []
    return sorted(p for p in src_dir.glob("*.md") if p.name != "README.md")


def discover_b_sources(hub_root: Path) -> list[Path]:
    """[Backward-compat wrapper] Return the B-layer sources for the active PREFIX.

    If the directory doesn't exist or there are zero target documents, writes
    an stderr message then ``sys.exit(1)`` (preserves the original behavior
    1:1).
    """
    prefix = read_active_prefix(hub_root)
    sources = discover_layer_sources(hub_root, prefix, "B")
    if not sources:
        sys.stderr.write(
            f"no B documents under reference-docs/{prefix}/B or reference-docs/B\n"
        )
        sys.exit(1)
    return sources


def ensure_cache_dir(hub_root: Path) -> Path:
    """Ensure ``CONTEXT/.template-cache/`` exists and return its path."""
    cache_dir = hub_root / "CONTEXT" / ".template-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def cache_is_fresh(
    cache_path: Path,
    sources: list[Path],
    *,
    allow_missing_sources: bool = False,
) -> bool:
    """True if the cache is newer than all sources.

    - False if cache_path doesn't exist.
    - ``allow_missing_sources=False`` (default): a missing source meaning
      False (= needs rebuild) would be ambiguous, so the ``stat()`` call is
      left to raise its own exception.
    - ``allow_missing_sources=True`` (bootstrap case): a missing source file
      is treated as not affecting cache freshness (the missing placeholder is
      simply left as-is).
    """
    if not cache_path.exists():
        return False
    cache_mtime = cache_path.stat().st_mtime
    if allow_missing_sources:
        return all((not src.exists()) or src.stat().st_mtime <= cache_mtime for src in sources)
    return all(src.stat().st_mtime <= cache_mtime for src in sources)


def make_hub_root_parser(description: str) -> argparse.ArgumentParser:
    """Create a standard ArgumentParser with only a ``--hub-root`` argument."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--hub-root",
        required=True,
        type=Path,
        help="Planning-Agent-Hub directory",
    )
    return parser


def validate_hub_root(hub_root: Path) -> int:
    """Print to stderr and return 2 if hub-root isn't a directory; 0 otherwise.

    In a script's main(), after ``rc = validate_hub_root(...)``, immediately
    ``return rc`` if it's nonzero.
    """
    if not hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {hub_root}\n")
        return 2
    return 0
