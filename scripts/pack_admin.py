#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Policy pack packaging/install/list — plugin future (multi-tenant SaaS Phase 5).

Policy pack: a deployable policy-context bundle.
    packs/{name}/
      pack.json                      ← {name, version, type, prefixes[], depends_on[], ...}
      reference-docs/{PREFIX}/{A,B,C} ← policy data
      reference-docs/master-id-map.yml

When a tenant picks a pack from the marketplace (packs/registry.json) and installs
it, the corresponding PREFIX is non-destructively merged into their hub. The
install history is recorded with its version in CONTEXT/installed-packs.json,
used for updates and audits.

Commands:
  package --hub-root <tenant> --name <pack> --out <packs-dir> [--prefix G2 ...] [--version 1.0.0]
  install --hub-root <tenant> --pack <name> [--packs-dir packs] [--force]
  list    [--packs-dir packs]

exit code: 0 success / 1 failure / 2 argument error
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
    """Bundle a tenant's reference-docs into a deployable policy pack."""
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
    # bundle master-id-map (if present)
    src_map = src_ref / "master-id-map.yml"
    if src_map.exists():
        shutil.copyfile(src_map, dst_ref / "master-id-map.yml")

    manifest = {
        "name": name,
        "version": version,
        "type": "policy",
        "prefixes": chosen,
        "depends_on": [],
        "description": description or f"{name} policy pack",
        "doc_count": doc_count,
        "created_at": date.today().isoformat(),
    }
    (pack_dir / "pack.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "packaged", "pack_dir": str(pack_dir), **manifest}


def install(tenant_root: Path, pack_dir: Path, *, force: bool = False) -> dict:
    """Install a policy pack into the tenant hub via non-destructive merge + record history."""
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

    # install history
    rec_path = tenant_root / "CONTEXT" / "installed-packs.json"
    records = []
    if rec_path.exists():
        try:
            records = json.loads(rec_path.read_text(encoding="utf-8"))
        except Exception:
            records = []
    records = [r for r in records if r.get("name") != manifest["name"]]  # refresh same pack
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
    ap = argparse.ArgumentParser(description="Policy pack packaging/install/list")
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
            print(f"[pack_admin] no packs found: {args.packs_dir}")
            return 0
        for p in packs:
            print(f"  - {p['name']}@{p.get('version','?')} "
                  f"[{','.join(p.get('prefixes', []))}] docs={p.get('doc_count','?')}")
        return 0

    if args.command == "package":
        if not (args.hub_root and args.name):
            sys.stderr.write("--hub-root, --name required\n")
            return 2
        if not args.hub_root.is_dir():
            sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
            return 2
        r = package(args.hub_root, args.name, args.out, prefixes=args.prefix,
                    version=args.version, description=args.description)
        if r["status"] != "packaged":
            sys.stderr.write(f"[pack_admin] packaging failed: {r}\n")
            return 1
        print(f"[pack_admin] packaged {r['pack_dir']} "
              f"(prefixes={r['prefixes']}, docs={r['doc_count']}, v{r['version']})")
        return 0

    # install
    if not (args.hub_root and args.pack):
        sys.stderr.write("--hub-root, --pack required\n")
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
        sys.stderr.write(f"[pack_admin] install failed: {r}\n")
        return 1
    print(f"[pack_admin] installed {r['name']}@{r['version']} "
          f"copied={r['copied']} skipped={r['skipped']} map+={r['map_entries_added']}")
    print("  next: generate caches with build_b_cache/build_b_index/build_a_index/build_c_index")
    return 0


if __name__ == "__main__":
    sys.exit(main())
