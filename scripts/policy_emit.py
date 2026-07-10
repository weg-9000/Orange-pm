#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""policy_emit — 테넌트 정책 거버넌스 상태 → 정규화 JSON (viz, Phase 6).

테넌트 hub 의 정책 컨텍스트 상태를 viz 가 소비할 계약으로 변환한다. 읽기 전용.
  - prefixes: reference-docs/{PREFIX} 별 A/B/C 문서 수
  - installedPacks: CONTEXT/installed-packs.json (설치 이력)
  - availablePacks: packs/registry.json (마켓플레이스, 발견 시)
  - gatePreset: CONTEXT/gates/_active-preset.txt (없으면 'standard')

    python policy_emit.py --hub-root <tenant> --emit-json
출력: {kind:"policy", gatePreset, prefixes:[{id,a,b,c}], installedPacks, availablePacks, version}
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
    # packs/registry.json 탐색: 테넌트 루트 상위(플랫폼/리포)에서 찾는다.
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
        sys.stderr.write("--hub-root 필요\n")
        return 2
    return C.emit(transform(args.hub_root))


if __name__ == "__main__":
    sys.exit(main())
