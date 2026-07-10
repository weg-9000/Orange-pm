#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""샘플/외부 테넌트 데이터를 empty-default 플랫폼 hub 로 적재 (멀티테넌트 SaaS).

목적:
    플랫폼(Planning-Agent-Hub)은 특정 제품 데이터를 내장하지 않고 비어서 출고된다.
    본 스크립트는 `examples/sample-tenant-{name}/` 의 정책 데이터(reference-docs +
    master-id-map + layer-config)를 hub 로 **비파괴 병합** 적재해, 데모·회귀·온보딩
    환경을 즉시 구성한다. (사용자 자기 데이터는 /import-source 로 적재.)

    이는 "특정 제품 데이터를 넣는" 것이 아니라 "누구나 자기 데이터를 적재할 수 있는
    환경(능력)" 의 기본 구현이다 — 샘플은 그 능력의 한 입력일 뿐이다.

동작(멱등·비파괴):
    1. {sample}/reference-docs/{PREFIX}/ → hub/CONTEXT/reference-docs/{PREFIX}/ 복사
       (기존 PREFIX 디렉토리는 --force 없으면 건너뜀)
    2. {sample}/reference-docs/master-id-map.yml 의 핀 항목을 hub 맵에 병합(중복 제외)
    3. hub layer-config 의 PREFIXES 가 비어 있으면 샘플 layer-config 로 교체,
       아니면 누락 PREFIX 항목만 추가하고 ACTIVE_PREFIX 가 없을 때만 설정

사용법:
    python load_sample_tenant.py --hub-root <Hub> --sample orange [--force]
    python load_sample_tenant.py --hub-root <Hub> --sample-dir <경로> [--force]

exit code: 0 성공 / 1 샘플/대상 없음 / 2 인자 오류
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
    # hub 가 repo 루트 바로 아래(Planning-Agent-Hub)라고 가정하고 형제 examples/ 탐색.
    candidates = [
        hub_root.parent / "examples" / f"sample-tenant-{sample}",
        Path.cwd() / "examples" / f"sample-tenant-{sample}",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def _merge_master_id_map(sample_map: Path, hub_map: Path) -> int:
    """샘플 맵의 `key: value` 항목 중 hub 에 없는 것만 추가. 추가 건수 반환."""
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
        block = "\n# ── 샘플 적재 병합 ──\n" + "\n".join(added) + "\n"
        with hub_map.open("a", encoding="utf-8") as fh:
            fh.write(block)
    return len(added)


def _hub_prefixes_empty(layer_config: Path) -> bool:
    if not layer_config.exists():
        return True
    text = layer_config.read_text(encoding="utf-8", errors="replace")
    # `- id: X` 항목이 주석 아닌 줄로 하나라도 있으면 비어있지 않음.
    for ln in text.splitlines():
        if re.match(r"^\s*-\s*id:\s*[A-Za-z0-9_-]+\s*$", ln):
            return False
    return True


def load_tenant(hub_root: Path, sample_dir: Path, *, force: bool = False) -> dict:
    """샘플 테넌트를 hub 로 적재하고 결과 dict 반환."""
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

    # master-id-map 병합
    sample_map = src_ref / "master-id-map.yml"
    added = _merge_master_id_map(sample_map, dst_ref / "master-id-map.yml")

    # layer-config: hub 가 비어 있으면 샘플 것으로 교체
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
    ap = argparse.ArgumentParser(description="샘플/테넌트 데이터를 hub 로 적재")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--sample", default=None, help="예: orange → examples/sample-tenant-orange")
    ap.add_argument("--sample-dir", default=None, type=Path, help="샘플 디렉토리 직접 지정")
    ap.add_argument("--force", action="store_true", help="기존 PREFIX·layer-config 덮어쓰기")
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
    print("  다음: build_b_cache / build_b_index / build_a_index / build_c_index 로 캐시 생성")
    return 0


if __name__ == "__main__":
    sys.exit(main())
