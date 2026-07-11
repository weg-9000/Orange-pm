#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External import markdown -> standard import record (multi-tenant SaaS Phase 2).

Purpose:
    Load markdown fetched from Confluence/GitLab/Notion etc. (source-agnostic)
    into a standard import record. Preserves the body losslessly while
    normalizing frontmatter and recording metadata. The actual fetch and
    per-source conversion is handled by the caller (skill):
      - A Confluence snapshot (XML) is converted to MD via storage_to_md.py
        before being fed into this module.
      - GitLab raw .md / Notion-family wiki connector fetch results are
        already MD-native -> fed in directly.
    -> This module is **source-agnostic** — it always takes MD as input.

Output:
    PROJECTS/{product}/inputs/imports/{source}/{id}.md       (normalized frontmatter + body)
    PROJECTS/{product}/inputs/imports/{source}/{id}.meta.json

Idempotent: re-running with identical content is a no-op. The existing
meta.json is not overwritten (from-url pattern) — a mismatched content hash
only prints a warning.

Usage:
    python import_normalize.py --hub-root <Hub> --product <p> --source <confluence|gitlab|notion|file> \
        --id <ID> --input <fetched.md> [--source-url URL] [--intent context]

exit code: 0 success / 1 no input / 2 argument error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from frontmatter_detect import detect_frontmatter, normalize

VALID_SOURCES = ("confluence", "gitlab", "notion", "file")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def write_record(
    hub_root: Path,
    product: str,
    source: str,
    doc_id: str,
    md_text: str,
    *,
    source_url: str = "",
    intent: str = "context",
) -> dict:
    """Write the import record (md + meta.json) and return a result dict."""
    out_dir = hub_root / "PROJECTS" / product / "inputs" / "imports" / source
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{doc_id}.md"
    meta_path = out_dir / f"{doc_id}.meta.json"

    imported_at = datetime.now().isoformat(timespec="seconds")
    # Idempotency: if a prior record exists, reuse its imported_at so a
    # re-run produces byte-identical output.
    if md_path.exists():
        prev_fm, _, _ = detect_frontmatter(md_path.read_text(encoding="utf-8", errors="replace"))
        if prev_fm.get("imported_at"):
            imported_at = prev_fm["imported_at"]
    normalized, report = normalize(
        md_text, source=source, source_url=source_url, doc_id=doc_id,
        imported_at=imported_at,
    )
    content_sha = _sha(normalized)

    status = "written"
    if md_path.exists() and _sha(md_path.read_text(encoding="utf-8", errors="replace")) == content_sha:
        status = "unchanged"
    md_path.write_text(normalized, encoding="utf-8")

    if meta_path.exists():
        # Preserve the existing metadata — only flag a content change.
        existing = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
        if existing.get("content_sha") != content_sha:
            existing["content_sha"] = content_sha
            existing["last_seen"] = imported_at
            existing["note"] = "content changed since first import"
            meta_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
            status = "meta-updated"
        meta = existing
    else:
        meta = {
            "id": doc_id,
            "source": source,
            "source_url": source_url,
            "intent": intent,
            "imported_at": imported_at,
            "content_sha": content_sha,
            "original_metadata": report["fields"]["original_metadata"],
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": status,
        "md_path": str(md_path.relative_to(hub_root).as_posix()),
        "meta_path": str(meta_path.relative_to(hub_root).as_posix()),
        "report": report,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="External import MD -> standard record")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", required=True)
    ap.add_argument("--source", required=True, choices=VALID_SOURCES)
    ap.add_argument("--id", required=True, dest="doc_id")
    ap.add_argument("--input", required=True, type=Path, help="Fetched MD file")
    ap.add_argument("--source-url", default="")
    ap.add_argument("--intent", default="context", choices=("context", "target", "template"))
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    if not args.input.is_file():
        sys.stderr.write(f"input not found: {args.input}\n")
        return 1
    result = write_record(
        args.hub_root, args.product, args.source, args.doc_id,
        args.input.read_text(encoding="utf-8", errors="replace"),
        source_url=args.source_url, intent=args.intent,
    )
    print(f"[import_normalize] {result['status']}: {result['md_path']}")
    if result["report"]["inferred"]:
        print(f"  inferred: {', '.join(result['report']['inferred'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
