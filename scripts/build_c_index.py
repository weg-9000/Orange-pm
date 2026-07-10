#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C 계층 마스터 인덱스 생성 (멀티-PREFIX SaaS Phase 1).

목적:
    전 PREFIX 의 C 계층(완결 서비스 아카이브) 목록을 단일 경량 인덱스로 만든다.
    세션 시작(L0)에 이 파일만 읽어 "어느 PREFIX 에 어떤 서비스가 있나" 를 파악하고,
    세부는 헤딩 인덱스(L2)·벡터(L3)로 진입한다. 항상 작게 유지(서비스 메타만).

    C 레이아웃(아카이브 후):
      reference-docs/{PREFIX}/C/{service}/
        metadata.json   ← {service, prefix, label?, docs[], status?, archived_at?}
        d1-*.md d2-*.md ...

    출력: CONTEXT/.template-cache/c-master-index.json

사용법:
    python build_c_index.py --hub-root <Planning-Agent-Hub 경로>

exit code:
    0 = 성공 (서비스 0개여도 빈 인덱스로 성공)
    1 = layer-config.md 없음
    2 = 인자 오류
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

# layer-config.md PREFIXES 블록의 `- id: G2` / `label: 민간 ...` 쌍 추출용.
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
            # metadata 미비 시 md 파일 stem 으로 docs 유추.
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
        # 신규 중첩 우선, 레거시 평면(C/) 폴백.
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
