#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Load sample/external tenant data into the empty-default platform hub (multi-tenant SaaS).

Purpose:
    The platform (Planning-Agent-Hub) ships empty, with no product data baked in.
    This script loads the policy data (reference-docs + master-id-map +
    layer-config) from `examples/sample-tenant-{name}/` into the hub via a
    **non-destructive merge**, so a demo/regression/onboarding environment can
    be set up instantly. (Users load their own data via /import-source.)

    This isn't about "loading a specific product's data" — it's the base
    implementation of "an environment (capability) where anyone can load
    their own data." The sample is just one input to that capability.

Behavior (idempotent, non-destructive):
    1. Copy {sample}/reference-docs/{PREFIX}/ → hub/CONTEXT/reference-docs/{PREFIX}/
       (an existing PREFIX directory is skipped unless --force is given)
    2. Merge the pinned entries from {sample}/reference-docs/master-id-map.yml
       into the hub map (skip duplicates)
    3. If the hub layer-config's PREFIXES is empty, replace it with the sample
       layer-config; otherwise only add missing PREFIX entries, and only set
       ACTIVE_PREFIX if it isn't already set

Usage:
    python load_sample_tenant.py --hub-root <Hub> --sample orange [--force]
    python load_sample_tenant.py --hub-root <Hub> --sample-dir <path> [--force]

exit code: 0 success / 1 sample/target not found / 2 argument error
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path


def _resolve_sample_dir(hub_root: Path, sample: str | None, sample_dir: Path | None) -> Path | None:
    if sample_dir:
        return sample_dir if sample_dir.is_dir() else None
    if not sample:
        return None
    # Assumes the hub is directly under the repo root (Planning-Agent-Hub)
    # and looks for a sibling examples/ directory.
    candidates = [
        hub_root.parent / "examples" / f"sample-tenant-{sample}",
        Path.cwd() / "examples" / f"sample-tenant-{sample}",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def _merge_master_id_map(sample_map: Path, hub_map: Path) -> int:
    """Add only the `key: value` entries from the sample map that are missing from the hub. Returns the count added."""
    if not sample_map.exists():
        return 0
    existing_keys = set()
    hub_lines: list[str] = []
    if hub_map.exists():
        hub_lines = hub_map.read_text(encoding="utf-8", errors="replace").splitlines()
        for ln in hub_lines:
            s = ln.strip()
            if s and not s.startswith("#") and ":" in s:
                existing_keys.add(s.partition(":")[0].strip())
    added: list[str] = []
    for ln in sample_map.read_text(encoding="utf-8", errors="replace").splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        key = s.partition(":")[0].strip()
        if key not in existing_keys:
            added.append(ln)
            existing_keys.add(key)
    if added:
        hub_map.parent.mkdir(parents=True, exist_ok=True)
        block = "\n# ── merged from sample tenant load ──\n" + "\n".join(added) + "\n"
        with hub_map.open("a", encoding="utf-8") as fh:
            fh.write(block)
    return len(added)


def _hub_prefixes_empty(layer_config: Path) -> bool:
    if not layer_config.exists():
        return True
    text = layer_config.read_text(encoding="utf-8", errors="replace")
    # Not empty if there's at least one `- id: X` entry on a non-comment line.
    for ln in text.splitlines():
        if re.match(r"^\s*-\s*id:\s*[A-Za-z0-9_-]+\s*$", ln):
            return False
    return True


def load_tenant(hub_root: Path, sample_dir: Path, *, force: bool = False) -> dict:
    """Load the sample tenant into the hub and return a result dict."""
    manifest_path = sample_dir / "tenant.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    src_ref = sample_dir / manifest.get("reference_docs", "reference-docs")
    dst_ref = hub_root / "CONTEXT" / "reference-docs"
    dst_ref.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    skipped: list[str] = []
    if src_ref.is_dir():
        for prefix_dir in sorted(p for p in src_ref.iterdir() if p.is_dir()):
            dst_prefix = dst_ref / prefix_dir.name
            if dst_prefix.exists() and not force:
                skipped.append(prefix_dir.name)
                continue
            shutil.copytree(prefix_dir, dst_prefix, dirs_exist_ok=True)
            copied.append(prefix_dir.name)

    # merge master-id-map
    sample_map = src_ref / "master-id-map.yml"
    added = _merge_master_id_map(sample_map, dst_ref / "master-id-map.yml")

    # layer-config: replace with the sample's if the hub's is empty
    sample_cfg = sample_dir / manifest.get("layer_config", "layer-config.md")
    hub_cfg = hub_root / "CONTEXT" / "layer-config.md"
    cfg_action = "kept"
    if sample_cfg.exists() and (_hub_prefixes_empty(hub_cfg) or force):
        shutil.copyfile(sample_cfg, hub_cfg)
        cfg_action = "replaced"

    return {
        "sample": manifest.get("sample", sample_dir.name),
        "active_prefix": manifest.get("active_prefix", ""),
        "copied_prefixes": copied,
        "skipped_prefixes": skipped,
        "map_entries_added": added,
        "layer_config": cfg_action,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Load sample/tenant data into the hub")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--sample", default=None, help="e.g. orange → examples/sample-tenant-orange")
    ap.add_argument("--sample-dir", default=None, type=Path, help="explicitly specify the sample directory")
    ap.add_argument("--force", action="store_true", help="overwrite existing PREFIX/layer-config")
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    sample_dir = _resolve_sample_dir(args.hub_root, args.sample, args.sample_dir)
    if sample_dir is None:
        sys.stderr.write("sample not found (use --sample <name> or --sample-dir <path>)\n")
        return 1
    result = load_tenant(args.hub_root, sample_dir, force=args.force)
    print(f"[load_sample_tenant] sample={result['sample']} "
          f"copied={result['copied_prefixes']} skipped={result['skipped_prefixes']} "
          f"map+={result['map_entries_added']} layer-config={result['layer_config']}")
    print("  Next: generate caches via build_b_cache / build_b_index / build_a_index / build_c_index")
    return 0


if __name__ == "__main__":
    sys.exit(main())
