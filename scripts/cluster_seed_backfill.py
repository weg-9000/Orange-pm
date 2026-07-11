#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cluster Seed Backfill — bootstrap (P5, docs/fr-cluster-alignment.md).

Migration tool for normalizing untagged requirements.

Background (P5 / 2-pass workflow):
    Even for a product with no seed (capability) tags at all, running
    `cluster_identify` once produces a fr_index (FR→{capability,cluster_id})
    in cluster_map.json based purely on scoring (5-axis). Backfilling this
    result into a **sidecar YAML (`requirements.seeds.yml`)** means subsequent
    runs consume it as the initial union-find partition (seed), so the 2-pass
    workflow works correctly (seed-not-lock).

Design decision — seeds live in a sidecar:
    Rather than modifying requirements.md's body, seeds are stored and merged
    in a separate YAML file in the same directory. This keeps the body
    non-destructive, parsing deterministic, and git diffs clear.

Principles:
    - Idempotent: FRs that already have a capability seed are skipped (--force to overwrite).
    - Non-destructive: existing seed entries/fields not covered by fr_index are preserved.
    - --dry-run: prints planned changes only, writes nothing.
    - Deterministic output: sort_keys + allow_unicode guarantee a stable diff.

Sidecar schema (`requirements.seeds.yml`, same directory as requirements.md):
    "FR-101":
      capability: "Provisioning"
      cluster_hint: "PR-01"   # optional (omit if absent)
      lock: false             # optional, default false
    "FR-102":
      capability: "[needs-confirmation]"

CLI:
    python cluster_seed_backfill.py \
        --cluster-map PROJECTS/{p}/graph/cluster_map.json \
        --seeds       PROJECTS/{p}/inputs/requirements.seeds.yml \
        [--force]         # overwrite existing capability seeds too
        [--dry-run]       # print planned changes only (no write)

Exit codes: 0 success / 1 input error
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_fr_index(cluster_map: dict[str, Any]) -> dict[str, dict]:
    """Extract fr_index(FR→{capability,cluster_id}) from cluster_map.

    Returns an empty dict if the format doesn't match (no exception — graceful)."""
    raw = cluster_map.get("fr_index")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for fr, info in raw.items():
        if isinstance(info, dict):
            out[str(fr)] = info
    return out


def _read_seeds(path: Path) -> dict[str, dict]:
    """Load the sidecar YAML. Returns {} if missing or empty (graceful).

    Returns {} if the top level isn't a map (corruption guard)."""
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict] = {}
    for fr, info in data.items():
        if isinstance(info, dict):
            out[str(fr)] = dict(info)
        else:
            # preserve malformed entries too (non-destructive) — keep as-is
            out[str(fr)] = info
    return out


# ── Pure merge logic ─────────────────────────────────────────────────────────
def backfill_seeds(
    fr_index: dict,
    seeds: dict,
    *,
    force: bool = False,
) -> tuple[dict, list[dict]]:
    """Merge fr_index into the sidecar seeds dict (pure function).

    For each FR, sets capability and cluster_hint(=cluster_id).
    Idempotent: FRs that already have a capability are skipped (overwritten with --force).
    Existing seed entries/fields not covered by fr_index are preserved (non-destructive).

    Args:
        fr_index: FR → {"capability": ..., "cluster_id": ...}
        seeds: existing sidecar dict (FR → {capability, cluster_hint?, lock?})
        force: if True, overwrite existing capability seeds too

    Returns:
        (new_seeds, changes) — each change entry: {"fr", "action"}
          action ∈ {"injected", "updated", "skipped_existing"}

    Never raises (graceful). Always returns (dict, change list)."""
    changes: list[dict] = []

    # shallow (1-level) copy to preserve existing entries
    new_seeds: dict = {}
    for fr, info in (seeds or {}).items():
        new_seeds[str(fr)] = dict(info) if isinstance(info, dict) else info

    if not isinstance(fr_index, dict):
        return new_seeds, changes

    for fr, info in fr_index.items():
        if not isinstance(info, dict):
            continue
        capability = info.get("capability")
        if capability is None:
            continue
        capability = str(capability)
        cluster_id = info.get("cluster_id")
        fr = str(fr)

        existing = new_seeds.get(fr)
        has_capability = (
            isinstance(existing, dict) and existing.get("capability") not in (None, "")
        )

        if has_capability and not force:
            changes.append({"fr": fr, "action": "skipped_existing"})
            continue

        # preserve other fields (lock, etc.) of the existing dict entry, only update capability/cluster_hint
        entry: dict = dict(existing) if isinstance(existing, dict) else {}
        action = "updated" if has_capability else "injected"
        entry["capability"] = capability
        if cluster_id is not None and str(cluster_id).strip():
            entry["cluster_hint"] = str(cluster_id).strip()

        new_seeds[fr] = entry
        changes.append({"fr": fr, "action": action})

    return new_seeds, changes


def _dump_seeds(seeds: dict) -> str:
    """Sidecar dict → deterministic YAML string (sorted + unicode preserved)."""
    return yaml.safe_dump(seeds, allow_unicode=True, sort_keys=True)


def _summarize(changes: list[dict]) -> dict[str, int]:
    """Tally counts per action."""
    counts: dict[str, int] = {}
    for c in changes:
        counts[c["action"]] = counts.get(c["action"], 0) + 1
    return counts


# ── File I/O ──────────────────────────────────────────────────────────────────
def run_backfill(
    cluster_map_path: Path,
    seeds_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[int, list[dict]]:
    """File I/O wrapper. Returns (exit_code, changes).

    Loads cluster_map(fr_index) (missing/corrupt → exit 1), loads the existing
    sidecar YAML (missing → {}), computes the merge, and writes to the sidecar
    unless dry_run. Existing seed entries/fields not covered by fr_index are
    preserved.

    exit_code: 0 success / 1 input error."""
    if not cluster_map_path.is_file():
        print(f"[seed_backfill] ERROR: cluster_map file not found: {cluster_map_path}",
              file=sys.stderr)
        return 1, []

    try:
        cluster_map = _load_json(cluster_map_path)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"[seed_backfill] ERROR: failed to parse cluster_map: {exc}", file=sys.stderr)
        return 1, []

    fr_index = _read_fr_index(cluster_map)
    if not fr_index:
        print("[seed_backfill] WARN: fr_index is empty in cluster_map — "
              "run cluster_identify once first.", file=sys.stderr)

    seeds = _read_seeds(seeds_path)
    new_seeds, changes = backfill_seeds(fr_index, seeds, force=force)

    counts = _summarize(changes)
    written = counts.get("injected", 0) + counts.get("updated", 0)

    if dry_run:
        print(f"[seed_backfill] DRY-RUN: to-inject {counts.get('injected', 0)} · "
              f"to-update {counts.get('updated', 0)} · "
              f"kept {counts.get('skipped_existing', 0)} (no write)")
        for c in changes:
            if c["action"] in ("injected", "updated"):
                info = fr_index.get(c["fr"], {})
                print(f"  - {c['action']}: {c['fr']} → "
                      f"capability={info.get('capability')} "
                      f"cluster_hint={info.get('cluster_id')}")
        return 0, changes

    seeds_path.parent.mkdir(parents=True, exist_ok=True)
    seeds_path.write_text(_dump_seeds(new_seeds), encoding="utf-8")

    print(f"[seed_backfill] OK: injected {counts.get('injected', 0)} · "
          f"updated {counts.get('updated', 0)} · "
          f"kept {counts.get('skipped_existing', 0)} → {seeds_path}")
    return 0, changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cluster_seed_backfill",
        description="Backfill cluster_map.fr_index seeds into sidecar YAML (P5)",
    )
    parser.add_argument("--cluster-map", type=Path, required=True,
                        help="cluster_map.json (holds fr_index)")
    parser.add_argument("--seeds", type=Path, required=True,
                        help="Sidecar requirements.seeds.yml (merge target)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite FRs that already have seeds too")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print planned changes only (no write)")
    args = parser.parse_args(argv)

    code, _ = run_backfill(
        args.cluster_map,
        args.seeds,
        force=args.force,
        dry_run=args.dry_run,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
