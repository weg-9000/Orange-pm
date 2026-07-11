#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_emit — Confluence sync status adapter (kind: sync, fix-plan-dossier-publish G1).

In the dossier model (1 capability = 1 feature spec = 1 Confluence page), normalizes
each dossier's sync status so viz can visualize and selectively push per dossier.

Join sources (all read-only):
    work-orders/cluster_index.json        — dossier list (wo_id, capability, draft_path)
    reports/sync-queue.md                 — status SSoT produced by render_sync_check
    reports/inbox/{WO}.merge-proposal.md   — pending remote-drift proposals
    confluence-source/{doc}.meta.json      — per-dossier page_id (if present)

Status (most severe first): REMOTE-DRIFT > OUTDATED > PENDING > REMOTE-UNKNOWN
                             > UNKNOWN > SYNCED

CLI:
    python sync_emit.py --hub-root <Hub> --product <name> --emit-json
exit: 0 ok / 1 no cluster_index (empty skeleton) / 2 argument error
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import _emit_common as C
import wo_emit

# Status severity (lower = higher priority). viz shows a single "most actionable"
# status per dossier.
# SOURCE-ONLY: the dossier's source-of-record in split-deliverable mode — not a
# publication unit, so it's excluded from actionable status (lowest priority).
# This closes the information gap between sync-queue.md's raw data and the viz display.
SEVERITY = {
    "REMOTE-DRIFT": 0,
    "OUTDATED": 1,
    "PENDING": 2,
    "REMOTE-UNKNOWN": 3,
    "UNKNOWN": 4,
    "SYNCED": 5,
    "SOURCE-ONLY": 6,
}
DEFAULT_STATUS = "PENDING"  # if there's no sync-queue row (not yet checked), default conservatively to PENDING

_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
_BOLD_RE = re.compile(r"\*\*([A-Z-]+)\*\*")
_CODE_RE = re.compile(r"`([^`]+)`")


def parse_sync_queue(text: str) -> dict[str, str]:
    """sync-queue.md table → {doc_id: most severe status}.

    Row format: | file | `doc_id` | meta | baseline | **STATUS** | reason |
    A single draft can have two rows (forward/reverse direction), so we merge
    them to the most severe status per doc_id.
    """
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("|") or "doc_id" in line or "---" in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        cid = _CODE_RE.search(cells[1])
        doc_id = cid.group(1) if cid else cells[1]
        st_m = _BOLD_RE.search(cells[4])
        status = st_m.group(1) if st_m else cells[4]
        if status not in SEVERITY:
            continue
        prev = out.get(doc_id)
        if prev is None or SEVERITY[status] < SEVERITY[prev]:
            out[doc_id] = status
    return out


def _doc_id_of(rec: dict) -> str:
    """Dossier doc_id for a cluster record (cluster_id == dossier file stem).

    normalize_cluster_records carries cluster_id in node_name. Supports both
    that and raw cluster records (which hold cluster_id directly); final
    fallback is the draft_path stem.
    """
    return (rec.get("cluster_id") or rec.get("node_name")
            or Path(rec.get("draft_path", "")).stem.replace(".draft", "")
            or rec.get("wo_id", ""))


def transform_sync(
    product: str,
    dossiers: list[dict],
    queue_status: dict[str, str],
    inbox_docs: set[str],
    page_ids: dict[str, str],
) -> dict:
    """Pure function (for tests) — dossier list + status signals → sync contract.

    queue_status: {doc_id: status}, inbox_docs: set of doc_ids pending a
    merge proposal, page_ids: {doc_id: page_id}.
    """
    items: list[dict] = []
    for rec in dossiers:
        doc_id = _doc_id_of(rec)
        # Records with a forced _status (e.g. SOURCE-ONLY) skip the queue join.
        status = rec.get("_status") or queue_status.get(doc_id, DEFAULT_STATUS)
        page_id = page_ids.get(doc_id)
        # No page_id means the page hasn't been created yet -> coerce to PENDING
        if not page_id and status == "SYNCED":
            status = "PENDING"
        items.append({
            "woId": rec.get("wo_id", ""),
            "docId": doc_id,
            "capability": rec.get("capability", ""),
            "clusterId": rec.get("cluster_id") or rec.get("node_name", ""),
            "draftPath": rec.get("draft_path", ""),
            "pageId": page_id or None,
            "status": status,
            "inboxPending": doc_id in inbox_docs,
        })
    items.sort(key=lambda it: (SEVERITY.get(it["status"], 9), it["docId"]))

    def _count(s: str) -> int:
        return sum(1 for it in items if it["status"] == s)

    totals = {
        "dossiers": len(items),
        "outdated": _count("OUTDATED"),
        "remoteDrift": _count("REMOTE-DRIFT"),
        "pending": _count("PENDING"),
        "synced": _count("SYNCED"),
        "inbox": sum(1 for it in items if it["inboxPending"]),
    }
    return {"kind": "sync", "product": product, "items": items, "totals": totals}


# split-deliverable publication units (kept consistent with render_sync_check.SPLIT_DELIVERABLES)
SPLIT_DELIVERABLES = [("02-policy", "Policy Definition"), ("03-screen-design", "Screen Design")]

# Common publication docs regardless of publication mode (publication-map §0/§0-bis: D1/D4/D5, one page each).
# (slug, label, source subdirectory, file glob) — item omitted if no source file exists.
COMMON_DOCS = [
    ("01-requirements", "Requirements Definition", "inputs", "requirements*.md"),
    ("04-meetings", "Meeting Notes", "meetings", "*.md"),
    ("05-research", "Competitor Research", "inputs", "research*.md"),
]


def _collect_common(pdir: Path, product: str) -> tuple[list[dict], dict[str, str]]:
    """D1/D4/D5 common document records + page_id. Only includes docs with a source file present.

    Audit 2026-06-11 gap 1: D1/D4/D5 are publication targets but weren't
    shown in the sync view, so PMs couldn't check their sync status. doc_id
    uses the same canonical `{slug}-{product}` key as the meta naming
    convention (kept consistent with render_sync_check).
    """
    src = pdir / "confluence-source"
    records: list[dict] = []
    page_ids: dict[str, str] = {}
    for slug, label, subdir, pattern in COMMON_DOCS:
        d = pdir / subdir
        files = [f for f in (sorted(d.glob(pattern)) if d.is_dir() else []) if f.is_file()]
        if not files:
            continue
        doc_id = f"{slug}-{product}"
        draft_path = f"{subdir}/{files[0].name}" if len(files) == 1 else f"{subdir}/"
        records.append({
            "wo_id": doc_id, "cluster_id": doc_id, "capability": label,
            "draft_path": draft_path,
        })
        pid = _meta_page_id(src, slug, product)
        if pid:
            page_ids[doc_id] = pid
    return records, page_ids


def _read_publication_mode(pdir: Path) -> str:
    """publication_mode from graph/project-mode.json. Defaults to dossier-page if the file/key is missing.

    Delegates to the single source of truth (_emit_common.read_publication_mode) — kept consistent with render_sync_check.
    """
    return C.read_publication_mode(pdir)


def _meta_page_id(src: Path, slug: str, product: str) -> str | None:
    """page_id from the deliverable meta in confluence-source (placeholders excluded)."""
    if not src.is_dir():
        return None
    cands = sorted(src.glob(f"{slug}-{product}.meta.json")) \
        or sorted(src.glob(f"{slug}*.meta.json"))
    for mf in cands:
        try:
            meta = json.loads(mf.read_text(encoding="utf-8"))
            pid = str(meta.get("id", ""))
            if pid and "{{" not in pid:
                return pid
        except Exception:
            pass
        break
    return None


def _collect_split(
    pdir: Path, product: str, queue_status: dict[str, str], inbox_docs: set[str],
    dossiers: list[dict],
) -> dict:
    """split-deliverable — publication units = D2 policy doc / D3 screen design doc (+ common D1/D4/D5).

    The dossier is the source of record, not a publication unit, but we still
    emit it as a SOURCE-ONLY info row to close the information gap with the
    raw sync-queue.md (audit gap 2) — viz renders it as a checkbox-less info
    row, keeping it excluded from publish actions.
    """
    src = pdir / "confluence-source"
    records: list[dict] = []
    page_ids: dict[str, str] = {}
    for slug, label in SPLIT_DELIVERABLES:
        doc_id = f"{slug}-{product}"
        records.append({
            "wo_id": doc_id, "cluster_id": doc_id, "capability": label,
            "draft_path": f"reports/render/{slug}.assembled.md",
        })
        pid = _meta_page_id(src, slug, product)
        if pid:
            page_ids[doc_id] = pid
    common_recs, common_pids = _collect_common(pdir, product)
    records.extend(common_recs)
    page_ids.update(common_pids)
    for rec in dossiers:
        records.append({
            "wo_id": rec.get("wo_id", ""), "cluster_id": _doc_id_of(rec),
            "capability": rec.get("capability", ""),
            "draft_path": rec.get("draft_path", ""),
            "_status": "SOURCE-ONLY",
        })
    return transform_sync(product, records, queue_status, inbox_docs, page_ids)


def _collect(pdir: Path, product: str) -> dict:
    # dossier list (cluster_index.json)
    cidx = pdir / "work-orders" / "cluster_index.json"
    if not cidx.exists():
        return {"kind": "sync", "product": product, "items": [],
                "totals": {"dossiers": 0, "outdated": 0, "remoteDrift": 0,
                           "pending": 0, "synced": 0, "inbox": 0},
                "note": "cluster_index.json not found — not a dossier model, or not yet generated"}
    dossiers = wo_emit.normalize_cluster_records(
        json.loads(cidx.read_text(encoding="utf-8")))

    # status SSoT (sync-queue.md)
    sq = pdir / "reports" / "sync-queue.md"
    queue_status = parse_sync_queue(sq.read_text(encoding="utf-8")) if sq.exists() else {}

    # pending inbox proposals -> doc_id set (filename {WO_or_doc}.merge-proposal.md)
    inbox = pdir / "reports" / "inbox"
    inbox_docs: set[str] = set()
    if inbox.is_dir():
        for f in inbox.glob("*.merge-proposal.md"):
            inbox_docs.add(f.name.replace(".merge-proposal.md", ""))

    # Branch on publication mode (fix-plan-dossier-publish-split). If split,
    # the publication units are the 2 docs D2/D3 (+ common docs) + dossier
    # SOURCE-ONLY info rows.
    if _read_publication_mode(pdir) == "split-deliverable":
        return _collect_split(pdir, product, queue_status, inbox_docs, dossiers)

    # per-dossier page_id (confluence-source/{doc}.meta.json)
    src = pdir / "confluence-source"
    page_ids: dict[str, str] = {}
    if src.is_dir():
        for rec in dossiers:
            doc_id = _doc_id_of(rec)
            for mf in sorted(src.glob("*.meta.json")):
                if doc_id.lower() in mf.stem.lower():
                    try:
                        meta = json.loads(mf.read_text(encoding="utf-8"))
                        pid = str(meta.get("id", ""))
                        if pid and "{{" not in pid:
                            page_ids[doc_id] = pid
                    except Exception:
                        pass
                    break

    # Common publication docs (D1/D4/D5) are also shown alongside dossiers (audit gap 1).
    common_recs, common_pids = _collect_common(pdir, product)
    page_ids.update(common_pids)

    return transform_sync(product, dossiers + common_recs, queue_status, inbox_docs, page_ids)


def main(argv: list[str]) -> int:
    args = C.make_parser("sync").parse_args(argv)
    if args.from_fixture:
        return C.emit(C.load_fixture(args.from_fixture))
    if not (args.hub_root and args.product):
        sys.stderr.write("--hub-root, --product required\n")
        return 2
    pdir = C.product_dir(args.hub_root, args.product)
    result = _collect(pdir, args.product)
    return C.emit(result)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
