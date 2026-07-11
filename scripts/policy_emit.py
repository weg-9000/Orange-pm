#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""policy_emit — tenant policy governance state → normalized JSON (viz, Phase 6).

Converts the tenant hub's policy context state into a contract consumable by
viz. Read-only.
  - prefixes: A/B/C document counts per reference-docs/{PREFIX}
  - installedPacks: CONTEXT/installed-packs.json (install history)
  - availablePacks: packs/registry.json (marketplace, if found)
  - gatePreset: CONTEXT/gates/_active-preset.txt (defaults to 'standard')

    python policy_emit.py --hub-root <tenant> --emit-json
Output: {kind:"policy", gatePreset, prefixes:[{id,a,b,c}], installedPacks, availablePacks, version}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import _emit_common as C


def _count_layer(ref: Path, prefix: str, layer: str) -> int:
    d = ref / prefix / layer
    if not d.is_dir():
        return 0
    return sum(1 for p in d.rglob("*.md") if p.name != "README.md")


def _prefixes(hub_root: Path) -> list[dict]:
    ref = hub_root / "CONTEXT" / "reference-docs"
    out: list[dict] = []
    if not ref.is_dir():
        return out
    for d in sorted(p for p in ref.iterdir() if p.is_dir() and not p.name.startswith(".")):
        out.append({
            "id": d.name,
            "a": _count_layer(ref, d.name, "A"),
            "b": _count_layer(ref, d.name, "B"),
            "c": _count_layer(ref, d.name, "C"),
        })
    return out


def _installed_packs(hub_root: Path) -> list[dict]:
    p = hub_root / "CONTEXT" / "installed-packs.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def _available_packs(hub_root: Path) -> list[dict]:
    # Search for packs/registry.json in ancestors of the tenant root (platform/repo).
    for base in (hub_root, hub_root.parent, hub_root.parent.parent):
        reg = base / "packs" / "registry.json"
        if reg.exists():
            try:
                return json.loads(reg.read_text(encoding="utf-8")).get("policy_packs", [])
            except Exception:
                return []
    return []


def _gate_preset(hub_root: Path) -> str:
    p = hub_root / "CONTEXT" / "gates" / "_active-preset.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").strip() or "standard"
    return "standard"


def transform(hub_root: str) -> dict:
    h = Path(hub_root)
    return {
        "kind": "policy-packs",
        "gatePreset": _gate_preset(h),
        "prefixes": _prefixes(h),
        "installedPacks": _installed_packs(h),
        "availablePacks": _available_packs(h),
    }


def main() -> int:
    args = C.make_parser("policy").parse_args()
    if args.from_fixture:
        return C.emit(C.load_fixture(args.from_fixture))
    if not args.hub_root:
        sys.stderr.write("--hub-root required\n")
        return 2
    return C.emit(transform(args.hub_root))


if __name__ == "__main__":
    sys.exit(main())
