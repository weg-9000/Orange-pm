#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정책팩 패키징/설치/조회 — 플러그인 future (멀티테넌트 SaaS Phase 5).

정책팩(policy pack): 배포 가능한 정책 컨텍스트 번들.
    packs/{name}/
      pack.json                      ← {name, version, type, prefixes[], depends_on[], ...}
      reference-docs/{PREFIX}/{A,B,C} ← 정책 데이터
      reference-docs/master-id-map.yml

테넌트는 marketplace(packs/registry.json)에서 팩을 골라 install 하면 해당 PREFIX 가
자신의 hub 로 비파괴 병합된다. 설치 이력은 CONTEXT/installed-packs.json 에 버전과
함께 기록되어 업데이트·감사에 쓰인다.

명령:
  package --hub-root <tenant> --name <pack> --out <packs-dir> [--prefix G2 ...] [--version 1.0.0]
  install --hub-root <tenant> --pack <name> [--packs-dir packs] [--force]
  list    [--packs-dir packs]

exit code: 0 성공 / 1 실패 / 2 인자 오류
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

from load_sample_tenant import _merge_master_id_map


def _ref_dir(hub_root: Path) -> Path:
    return hub_root / "CONTEXT" / "reference-docs"


def list_packs(packs_dir: Path) -> list[dict]:
    out: list[dict] = []
    if not packs_dir.is_dir():
        return out
    for d in sorted(p for p in packs_dir.iterdir() if p.is_dir()):
        manifest = d / "pack.json"
        if manifest.exists():
            try:
                out.append(json.loads(manifest.read_text(encoding="utf-8")))
            except Exception:
                pass
    return out


def package(hub_root: Path, name: str, out_dir: Path, *,
            prefixes: list[str] | None = None, version: str = "1.0.0",
            description: str = "") -> dict:
    """테넌트 reference-docs 를 배포 가능한 정책팩으로 번들."""
    src_ref = _ref_dir(hub_root)
    if not src_ref.is_dir():
        return {"status": "no-reference-docs"}
    available = [p.name for p in src_ref.iterdir()
                 if p.is_dir() and not p.name.startswith(".")]
    chosen = prefixes or available
    chosen = [p for p in chosen if (src_ref / p).is_dir()]
    if not chosen:
        return {"status": "no-prefixes", "available": available}

    pack_dir = out_dir / name
    dst_ref = pack_dir / "reference-docs"
    dst_ref.mkdir(parents=True, exist_ok=True)
    doc_count = 0
    for pfx in chosen:
        shutil.copytree(src_ref / pfx, dst_ref / pfx, dirs_exist_ok=True)
        doc_count += sum(1 for _ in (dst_ref / pfx).rglob("*.md"))
    # master-id-map 동봉(있으면)
    src_map = src_ref / "master-id-map.yml"
    if src_map.exists():
        shutil.copyfile(src_map, dst_ref / "master-id-map.yml")

    manifest = {
        "name": name,
        "version": version,
        "type": "policy",
        "prefixes": chosen,
        "depends_on": [],
        "description": description or f"{name} 정책팩",
        "doc_count": doc_count,
        "created_at": date.today().isoformat(),
    }
    (pack_dir / "pack.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "packaged", "pack_dir": str(pack_dir), **manifest}


def install(tenant_root: Path, pack_dir: Path, *, force: bool = False) -> dict:
    """정책팩을 테넌트 hub 로 비파괴 병합 설치 + 이력 기록."""
    manifest_path = pack_dir / "pack.json"
    if not manifest_path.exists():
        return {"status": "no-manifest"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    src_ref = pack_dir / "reference-docs"
    dst_ref = _ref_dir(tenant_root)
    dst_ref.mkdir(parents=True, exist_ok=True)

    copied, skipped = [], []
    if src_ref.is_dir():
        for pfx_dir in sorted(p for p in src_ref.iterdir() if p.is_dir()):
            dst = dst_ref / pfx_dir.name
            if dst.exists() and not force:
                skipped.append(pfx_dir.name)
                continue
            shutil.copytree(pfx_dir, dst, dirs_exist_ok=True)
            copied.append(pfx_dir.name)
    added = _merge_master_id_map(src_ref / "master-id-map.yml", dst_ref / "master-id-map.yml")

    # 설치 이력
    rec_path = tenant_root / "CONTEXT" / "installed-packs.json"
    records = []
    if rec_path.exists():
        try:
            records = json.loads(rec_path.read_text(encoding="utf-8"))
        except Exception:
            records = []
    records = [r for r in records if r.get("name") != manifest["name"]]  # 동일 팩 최신화
    records.append({
        "name": manifest["name"],
        "version": manifest["version"],
        "prefixes": manifest.get("prefixes", []),
        "installed_at": datetime.now().isoformat(timespec="seconds"),
    })
    rec_path.parent.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"status": "installed", "name": manifest["name"], "version": manifest["version"],
            "copied": copied, "skipped": skipped, "map_entries_added": added}


def main() -> int:
    ap = argparse.ArgumentParser(description="정책팩 패키징/설치/조회")
    ap.add_argument("command", choices=["package", "install", "list"])
    ap.add_argument("--hub-root", type=Path, default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--pack", default=None)
    ap.add_argument("--out", type=Path, default=Path("packs"))
    ap.add_argument("--packs-dir", type=Path, default=Path("packs"))
    ap.add_argument("--prefix", nargs="*", default=None)
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--description", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.command == "list":
        packs = list_packs(args.packs_dir)
        if not packs:
            print(f"[pack_admin] 팩 없음: {args.packs_dir}")
            return 0
        for p in packs:
            print(f"  - {p['name']}@{p.get('version','?')} "
                  f"[{','.join(p.get('prefixes', []))}] docs={p.get('doc_count','?')}")
        return 0

    if args.command == "package":
        if not (args.hub_root and args.name):
            sys.stderr.write("--hub-root, --name 필요\n")
            return 2
        if not args.hub_root.is_dir():
            sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
            return 2
        r = package(args.hub_root, args.name, args.out, prefixes=args.prefix,
                    version=args.version, description=args.description)
        if r["status"] != "packaged":
            sys.stderr.write(f"[pack_admin] 패키징 실패: {r}\n")
            return 1
        print(f"[pack_admin] packaged {r['pack_dir']} "
              f"(prefixes={r['prefixes']}, docs={r['doc_count']}, v{r['version']})")
        return 0

    # install
    if not (args.hub_root and args.pack):
        sys.stderr.write("--hub-root, --pack 필요\n")
        return 2
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    pack_dir = args.packs_dir / args.pack
    if not pack_dir.is_dir():
        sys.stderr.write(f"pack not found: {pack_dir}\n")
        return 1
    r = install(args.hub_root, pack_dir, force=args.force)
    if r["status"] != "installed":
        sys.stderr.write(f"[pack_admin] 설치 실패: {r}\n")
        return 1
    print(f"[pack_admin] installed {r['name']}@{r['version']} "
          f"copied={r['copied']} skipped={r['skipped']} map+={r['map_entries_added']}")
    print("  다음: build_b_cache/build_b_index/build_a_index/build_c_index 로 캐시 생성")
    return 0


if __name__ == "__main__":
    sys.exit(main())
