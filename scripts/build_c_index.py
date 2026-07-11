#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the C-layer master index (multi-PREFIX SaaS Phase 1).

Purpose:
    Build a single lightweight index listing the C layer (completed service
    archive) across all PREFIXes. At session start (L0), read only this file
    to learn "which services exist under which PREFIX," then drill into the
    heading index (L2) / vectors (L3) for detail. Always keep this small
    (service metadata only).

    C layout (post-archive):
      reference-docs/{PREFIX}/C/{service}/
        metadata.json   <- {service, prefix, label?, docs[], status?, archived_at?}
        d1-*.md d2-*.md ...

    Output: CONTEXT/.template-cache/c-master-index.json

Usage:
    python build_c_index.py --hub-root <path to Planning-Agent-Hub>

exit code:
    0 = success (empty index is still a success when there are 0 services)
    1 = layer-config.md missing
    2 = argument error
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from _cache_utils import (
    ensure_cache_dir,
    make_hub_root_parser,
    read_prefixes,
    validate_hub_root,
)

# For extracting `- id: G2` / `label: ...` pairs from the PREFIXES block in layer-config.md.
_PREFIX_LABELS = re.compile(
    r"-\s*id:\s*([A-Za-z0-9_-]+)\s*\n\s*label:\s*(.+?)\s*$",
    re.MULTILINE,
)


def _prefix_labels(hub_root: Path) -> dict[str, str]:
    cfg = hub_root / "CONTEXT" / "layer-config.md"
    if not cfg.exists():
        return {}
    text = cfg.read_text(encoding="utf-8", errors="replace")
    return {m.group(1): m.group(2).strip() for m in _PREFIX_LABELS.finditer(text)}


def _scan_services(c_dir: Path) -> dict[str, dict]:
    services: dict[str, dict] = {}
    if not c_dir.is_dir():
        return services
    for svc_dir in sorted(p for p in c_dir.iterdir() if p.is_dir()):
        meta_path = svc_dir / "metadata.json"
        meta: dict = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        docs = meta.get("docs")
        if not docs:
            # If metadata is incomplete, infer docs from md file stems.
            docs = [p.stem for p in sorted(svc_dir.glob("*.md")) if p.name != "README.md"]
        services[svc_dir.name] = {
            "label": meta.get("label", svc_dir.name),
            "docs": docs,
            "status": meta.get("status", "archived" if docs else "empty"),
            "archived_at": meta.get("archived_at", ""),
        }
    return services


def build(hub_root: Path) -> int:
    prefixes = read_prefixes(hub_root)
    labels = _prefix_labels(hub_root)
    cache_dir = ensure_cache_dir(hub_root)
    out_path = cache_dir / "c-master-index.json"

    base = hub_root / "CONTEXT" / "reference-docs"
    prefixes_payload: dict[str, dict] = {}
    total_services = 0
    for pfx in prefixes:
        # Prefer the new nested layout, fall back to the legacy flat layout (C/).
        nested_c = base / pfx / "C"
        legacy_c = base / "C"
        c_dir = nested_c if nested_c.is_dir() else legacy_c
        services = _scan_services(c_dir)
        total_services += len(services)
        prefixes_payload[pfx] = {
            "label": labels.get(pfx, pfx),
            "services": services,
        }

    payload = {
        "_meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "total_services": total_services,
        },
        "prefixes": prefixes_payload,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[build_c_index] wrote {out_path} (prefixes={len(prefixes)}, services={total_services})")
    return 0


def main() -> int:
    parser = make_hub_root_parser("Build C-layer master index (all PREFIXes)")
    args = parser.parse_args()
    rc = validate_hub_root(args.hub_root)
    if rc:
        return rc
    return build(args.hub_root)


if __name__ == "__main__":
    sys.exit(main())
