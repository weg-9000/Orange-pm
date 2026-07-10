#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tenant_emit — 테넌트 레지스트리 → 정규화 JSON (viz 거버넌스, Phase 6).

플랫폼 hub 의 tenant-config.yml 을 viz 가 소비할 정규화 계약으로 변환한다.
읽기 전용. --emit-json 계약(_emit_common).

    python tenant_emit.py --hub-root <platform> --emit-json
출력: {kind:"tenants", activeTenant, tenants:[{id,label,root,gatePreset}], version}
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
        sys.stderr.write("--hub-root 필요\n")
        return 2
    return C.emit(transform(args.hub_root))


if __name__ == "__main__":
    sys.exit(main())
