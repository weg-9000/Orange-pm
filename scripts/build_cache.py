#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified cache build dispatcher (S1-3, CONTEXT_OPTIMIZATION.md).

WARNING: SUPERSEDED / STANDALONE — not wired into any skill or hook.
    The live cache builders are build_bootstrap / build_b_cache / build_b_index,
    and every skill calls these 3 builders directly (not via this --target all
    dispatcher). This --target all dispatcher has no caller and is effectively
    dead code. It is kept only as a manual/standalone batch-build tool. Runtime
    logic is not changed.

Purpose:
    Provide a single entry point that can invoke the three scripts
    build_b_cache / build_b_index / build_bootstrap. The three original
    scripts remain unchanged and can still be run standalone.

Usage:
    python build_cache.py --hub-root <path to Planning-Agent-Hub> [--target TARGET]

    TARGET:
        b-summary  -> build_b_cache.build(hub_root)
        b-index    -> build_b_index.build(hub_root)
        bootstrap  -> build_bootstrap.build(hub_root)
        all        -> run all three in sequence (default)

exit code:
    0 = all steps succeeded
    1 = a step failed (returns the max exit code across all steps)
    2 = argument error (--hub-root not a directory / unknown --target)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Put the scripts directory at the front of sys.path so the build_* modules in
# the same directory can be imported (keeps behavior consistent regardless of
# where the script is invoked from).
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import build_b_cache  # noqa: E402  (must import after sys.path adjustment)
import build_b_index  # noqa: E402
import build_bootstrap  # noqa: E402
from _cache_utils import validate_hub_root  # noqa: E402

TARGETS = ("b-summary", "b-index", "bootstrap", "all")

# target -> (label, callable)
_DISPATCH = {
    "b-summary": ("build_b_cache", build_b_cache.build),
    "b-index": ("build_b_index", build_b_index.build),
    "bootstrap": ("build_bootstrap", build_bootstrap.build),
}


def _run_one(label: str, fn, hub_root: Path) -> int:
    """Run a single build step and return its exit code. Exceptions map to 1."""
    try:
        rc = fn(hub_root)
    except SystemExit as exc:  # a helper called sys.exit (e.g. layer-config missing)
        rc = exc.code if isinstance(exc.code, int) else 1
        print(f"[build_cache] {label} aborted with exit code {rc}", file=sys.stderr)
        return rc
    except Exception as exc:  # noqa: BLE001 — the dispatcher isolates every exception
        print(f"[build_cache] {label} raised {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return rc or 0


def run(hub_root: Path, target: str) -> int:
    """Run the build corresponding to target and return the overall exit code."""
    if target == "all":
        worst = 0
        for key in ("b-summary", "b-index", "bootstrap"):
            label, fn = _DISPATCH[key]
            rc = _run_one(label, fn, hub_root)
            if rc > worst:
                worst = rc
        return worst
    label, fn = _DISPATCH[target]
    return _run_one(label, fn, hub_root)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified cache build dispatcher (b-summary / b-index / bootstrap)",
    )
    parser.add_argument(
        "--hub-root",
        required=True,
        type=Path,
        help="Planning-Agent-Hub directory",
    )
    parser.add_argument(
        "--target",
        choices=TARGETS,
        default="all",
        help="Which cache to build (default: all)",
    )
    args = parser.parse_args()
    rc = validate_hub_root(args.hub_root)
    if rc:
        return rc
    return run(args.hub_root, args.target)


if __name__ == "__main__":
    sys.exit(main())
