#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tenant administration — create/list/path (multi-tenant SaaS Phase 4).

Model: **tenant = one hub directory.**
  - default: uses the platform CONTEXT directly (root ".") — legacy compatibility.
  - new: tenants/{id}/ gets its own isolated CONTEXT·PROJECTS (full file isolation).
Every script receives the tenant root via --hub-root, so isolation requires no code changes.

Create procedure (create):
  1. Validate tenant-config.yml / _presets.yml (no duplicate id, preset must exist)
  2. Copy the platform CONTEXT template into tenants/{id}/CONTEXT (excluding .template-cache / _session-bootstrap)
  3. Record the preset in gates/_active-preset.txt, create PROJECTS/
  4. Register the tenant in tenant-config.yml (comments preserved — block appended at the end)
  5. (optional) Load sample data via --sample

Usage:
  python tenant_admin.py create --hub-root <platform> --id acme [--label "Acme"] \
      [--gate-preset standard] [--sample orange]
  python tenant_admin.py list  --hub-root <platform>
  python tenant_admin.py path  --hub-root <platform> --id acme

exit code: 0 success / 1 validation failure / 2 argument error
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

_COPY_IGNORE = shutil.ignore_patterns(".template-cache", "_session-bootstrap.md")
_ACTIVE = re.compile(r"^active_tenant:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)


def _registry_path(hub_root: Path) -> Path:
    return hub_root / "tenant-config.yml"


def parse_registry(hub_root: Path) -> dict:
    """Returns {active_tenant, tenants:[{id, root, gate_preset, label}]} (lightweight parser)."""
    p = _registry_path(hub_root)
    if not p.exists():
        return {"active_tenant": "default", "tenants": []}
    text = p.read_text(encoding="utf-8", errors="replace")
    active = _ACTIVE.search(text)
    tenants: list[dict] = []
    cur: dict | None = None
    for line in text.splitlines():
        m = re.match(r"^\s*-\s*id:\s*([A-Za-z0-9_-]+)\s*$", line)
        if m:
            cur = {"id": m.group(1), "root": "", "gate_preset": "", "label": ""}
            tenants.append(cur)
            continue
        if cur is not None:
            for field in ("root", "label", "gate_preset"):
                fm = re.match(rf'^\s+{field}:\s*"?(.+?)"?\s*$', line)
                if fm:
                    cur[field] = fm.group(1)
    return {"active_tenant": active.group(1) if active else "default", "tenants": tenants}


def list_preset_names(hub_root: Path) -> list[str]:
    p = hub_root / "CONTEXT" / "gates" / "_presets.yml"
    if not p.exists():
        return ["standard"]
    names: list[str] = []
    in_presets = False
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if re.match(r"^presets:\s*$", line):
            in_presets = True
            continue
        if in_presets:
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
            if m:
                names.append(m.group(1))
    return names or ["standard"]


def tenant_root(hub_root: Path, tenant_id: str) -> Path | None:
    for t in parse_registry(hub_root)["tenants"]:
        if t["id"] == tenant_id:
            root = t.get("root") or "."
            return hub_root if root == "." else hub_root / root
    return None


def create_tenant(hub_root: Path, tenant_id: str, *, label: str = "",
                  gate_preset: str = "standard") -> dict:
    reg = parse_registry(hub_root)
    if any(t["id"] == tenant_id for t in reg["tenants"]):
        return {"status": "exists", "id": tenant_id}
    presets = list_preset_names(hub_root)
    if gate_preset not in presets:
        return {"status": "bad-preset", "preset": gate_preset, "available": presets}

    dest = hub_root / "tenants" / tenant_id
    if dest.exists():
        return {"status": "dir-exists", "path": str(dest)}
    src_ctx = hub_root / "CONTEXT"
    dest.mkdir(parents=True)
    shutil.copytree(src_ctx, dest / "CONTEXT", ignore=_COPY_IGNORE)
    (dest / "PROJECTS").mkdir(exist_ok=True)
    gates_dir = dest / "CONTEXT" / "gates"
    gates_dir.mkdir(parents=True, exist_ok=True)
    (gates_dir / "_active-preset.txt").write_text(gate_preset + "\n", encoding="utf-8")

    block = (
        f"\n  - id: {tenant_id}\n"
        f"    label: {label or tenant_id}\n"
        f"    root: tenants/{tenant_id}\n"
        f"    gate_preset: {gate_preset}\n"
        f"    # External integrations are declared via the tenant's CONTEXT/connectors.md capability mapping.\n"
        f"    # (wiki / chat / design / repo / tasks — convention: plugin CONNECTORS.md)\n"
    )
    reg_path = _registry_path(hub_root)
    if not reg_path.exists():
        reg_path.write_text("active_tenant: default\n\ntenants:\n", encoding="utf-8")
    with reg_path.open("a", encoding="utf-8") as fh:
        fh.write(block)

    return {"status": "created", "id": tenant_id, "root": f"tenants/{tenant_id}",
            "gate_preset": gate_preset}


def main() -> int:
    ap = argparse.ArgumentParser(description="Tenant create/list/path")
    ap.add_argument("command", choices=["create", "list", "path"])
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--id", default=None)
    ap.add_argument("--label", default="")
    ap.add_argument("--gate-preset", default="standard")
    ap.add_argument("--sample", default=None, help="Load sample data after creation (load_sample_tenant)")
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2

    if args.command == "list":
        reg = parse_registry(args.hub_root)
        print(f"active_tenant: {reg['active_tenant']}")
        for t in reg["tenants"]:
            print(f"  - {t['id']} (root={t.get('root') or '.'}, preset={t.get('gate_preset') or '-'})")
        return 0

    if args.command == "path":
        if not args.id:
            sys.stderr.write("--id required\n")
            return 2
        r = tenant_root(args.hub_root, args.id)
        if r is None:
            sys.stderr.write(f"unknown tenant: {args.id}\n")
            return 1
        print(str(r))
        return 0

    if not args.id:
        sys.stderr.write("--id required\n")
        return 2
    r = create_tenant(args.hub_root, args.id, label=args.label, gate_preset=args.gate_preset)
    if r["status"] != "created":
        sys.stderr.write(f"[tenant_admin] creation failed: {r}\n")
        return 1
    print(f"[tenant_admin] created tenant '{r['id']}' → {r['root']} (preset={r['gate_preset']})")
    if args.sample:
        try:
            import load_sample_tenant as lst
            dest = args.hub_root / "tenants" / args.id
            sample_dir = lst._resolve_sample_dir(dest, args.sample, None)
            if sample_dir:
                rr = lst.load_tenant(dest, sample_dir)
                print(f"  sample loaded: copied={rr['copied_prefixes']} active={rr['active_prefix']}")
            else:
                print(f"  (sample '{args.sample}' not found — manual loading required)")
        except Exception as exc:
            print(f"  sample loading skipped ({exc})")
    print(f"  next: run skills/scripts with --hub-root tenants/{args.id} (full isolation)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
