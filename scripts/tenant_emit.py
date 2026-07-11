#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tenant_emit — tenant registry -> normalized JSON (viz governance, Phase 6).

Converts the platform hub's tenant-config.yml into the normalized contract
that viz consumes. Read-only. --emit-json contract (_emit_common).

    python tenant_emit.py --hub-root <platform> --emit-json
Output: {kind:"tenants", activeTenant, tenants:[{id,label,root,gatePreset}], version}
"""
from __future__ import annotations

import sys
from pathlib import Path

import _emit_common as C
import tenant_admin


def transform(hub_root: str) -> dict:
    reg = tenant_admin.parse_registry(Path(hub_root))
    tenants = [{
        "id": t["id"],
        "label": t.get("label") or t["id"],
        "root": t.get("root") or ".",
        "gatePreset": t.get("gate_preset") or "",
    } for t in reg["tenants"]]
    return {"kind": "tenants", "activeTenant": reg["active_tenant"], "tenants": tenants}


def main() -> int:
    args = C.make_parser("tenants").parse_args()
    if args.from_fixture:
        return C.emit(C.load_fixture(args.from_fixture))
    if not args.hub_root:
        sys.stderr.write("--hub-root required\n")
        return 2
    return C.emit(transform(args.hub_root))


if __name__ == "__main__":
    sys.exit(main())
