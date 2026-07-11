#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Archive a completed service into the C layer (multi-tenant SaaS Phase 3).

Purpose:
    Load the deliverables of a fully published product (service) into that
    tenant's (PREFIX's) C layer at `reference-docs/{PREFIX}/C/{service}/`. C is
    a read-only archive; afterward build_c_index.py folds it into the master
    index and embed_pipeline folds it into vectors.

    Tenant-agnostic: doesn't assume any particular product — loads whatever
    PROJECTS deliverables are given. Prefers the finalized deliverables
    (reports/render/*.complete.md) if present, otherwise loads
    drafts/*.draft.md.

Idempotent:
    - If an existing metadata.json has the same doc list, archived_at is preserved.
    - Rewriting identical-content files produces identical bytes.

Usage:
    python archive_to_context.py --hub-root <Hub> --prefix G2 --product dbaas [--service dbaas] [--force]

exit code: 0 success / 1 no source / 2 argument error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def _resolve_source(hub_root: Path, prefix: str, product: str) -> Path | None:
    """Prefer PROJECTS/{prefix}/{product}, falling back to PROJECTS/{product}."""
    for cand in (hub_root / "PROJECTS" / prefix / product, hub_root / "PROJECTS" / product):
        if cand.is_dir():
            return cand
    return None


def _collect_docs(source: Path) -> list[Path]:
    """Prefer finalized docs (reports/render/*.complete.md), else drafts/*.draft.md."""
    rendered = source / "reports" / "render"
    if rendered.is_dir():
        docs = sorted(p for p in rendered.glob("*.complete.md"))
        if docs:
            return docs
    drafts = source / "drafts"
    if drafts.is_dir():
        return sorted(drafts.glob("*.draft.md"))
    return []


def archive(hub_root: Path, prefix: str, product: str,
            service: str | None = None, *, force: bool = False) -> dict:
    service = service or product
    source = _resolve_source(hub_root, prefix, product)
    if source is None:
        return {"status": "no-source", "service": service}
    docs = _collect_docs(source)
    if not docs:
        return {"status": "no-docs", "service": service, "source": str(source)}

    dest = hub_root / "CONTEXT" / "reference-docs" / prefix / "C" / service
    dest.mkdir(parents=True, exist_ok=True)

    copied, unchanged = [], []
    for d in docs:
        target = dest / d.name
        if target.exists() and not force and _sha(target) == _sha(d):
            unchanged.append(d.name)
            continue
        shutil.copyfile(d, target)
        copied.append(d.name)

    # metadata.json — archived_at is preserved idempotently
    meta_path = dest / "metadata.json"
    doc_stems = [d.stem for d in docs]
    archived_at = date.today().isoformat()
    if meta_path.exists():
        try:
            prev = json.loads(meta_path.read_text(encoding="utf-8"))
            if prev.get("docs") == doc_stems and prev.get("archived_at"):
                archived_at = prev["archived_at"]  # unchanged -> keep original timestamp
        except Exception:
            pass
    meta = {
        "service": service,
        "prefix": prefix,
        "source_product": product,
        "docs": doc_stems,
        "doc_files": [d.name for d in docs],
        "status": "archived",
        "archived_at": archived_at,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "archived",
        "service": service,
        "prefix": prefix,
        "dest": str(dest.relative_to(hub_root).as_posix()),
        "copied": copied,
        "unchanged": unchanged,
        "doc_count": len(docs),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Archive a completed service into the C layer")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--product", required=True)
    ap.add_argument("--service", default=None, help="C/{service} name (default: product)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    r = archive(args.hub_root, args.prefix, args.product, args.service, force=args.force)
    if r["status"] in ("no-source", "no-docs"):
        sys.stderr.write(f"[archive_to_context] {r['status']} — service={r['service']}\n")
        return 1
    print(f"[archive_to_context] {r['dest']}: copied={r['copied']} "
          f"unchanged={r['unchanged']} ({r['doc_count']} docs)")
    print("  next: run build_c_index.py to refresh the c-master-index")
    return 0


if __name__ == "__main__":
    sys.exit(main())
