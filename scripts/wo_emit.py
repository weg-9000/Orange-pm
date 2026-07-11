#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wo_emit — work-orders/index.json | cluster_index.json + draft frontmatter → normalized WO contract (§2).

Absorbs two fanout tracks into a single work board:
- node mode (default): work-orders/index.json (per-node policy/screen WO).
- cluster mode (Track A): falls back to work-orders/cluster_index.json when
  index.json is absent (per-cluster WO — exposes capability/member count).

Also injects BDD info (scenario count, coverage) for WO card badges. The
feature/coverage keys are keyed on the **draft file stem**, not wo_id (a
cluster draft is cluster_{id}.draft.md, so stem != wo_id — node mode has
stem == wo_id, so it's backward compatible).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import _emit_common as C

COV_ROW = re.compile(r"^\|\s*([^\s|][^|]*?)\s*\|.*\*\*(OK|UNCOVERED|STALE|WARN)\*\*", re.M)


def doc_id_of(draft_rel: str) -> str:
    """draft_path (relative) → BDD artifact key (doc_id stem). 'drafts/X.draft.md' → 'X'.
    Used to match the .feature file and coverage queue when the WO number
    (WO-NN) differs from the draft filename."""
    name = Path(draft_rel).name
    return name[:-len(".draft.md")] if name.endswith(".draft.md") else Path(name).stem


def parse_coverage(text: str) -> dict[str, str]:
    """bdd-coverage-queue.md table → {draft_stem: status}. Header/divider rows
    naturally don't match."""
    return {m.group(1).strip(): m.group(2) for m in COV_ROW.finditer(text or "")}


def _records(raw) -> list[dict]:
    """Extract the record list from index.json (accepts either a bare list or
    a key-wrapped dict). Anything else -> []."""
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        return []
    for key in ("work_orders", "items", "wo", "records"):
        if isinstance(raw.get(key), list):
            return raw[key]
    return []


def normalize_cluster_records(raw) -> list[dict]:
    """Normalize cluster_index.json {clusters:[...]} into node-record shape.

    Cluster drafts have no status frontmatter (Phase 5 limitation), so the
    record's status (new/ai-draft/...) is passed through as record_status
    for fallback. members -> linkedWos.
    """
    clusters = raw.get("clusters", []) if isinstance(raw, dict) else []
    out = []
    for c in clusters:
        members = c.get("members") or []
        out.append({
            "wo_id": c.get("wo_id", ""),
            "type": "cluster",
            "level": 0,
            "node_name": c.get("cluster_id", ""),
            "section_title": c.get("cluster_name", ""),
            "delta_required": False,
            "linked_wos": members,
            "members": members,
            "capability": c.get("capability", ""),
            "draft_path": c.get("draft_path", ""),
            "record_status": c.get("status"),
        })
    return out


# Extracts the dossier §2 screen section (free-form bullet notes) — input
# for prototype/journey in cluster (dossier) mode.
# §2 is a prose bullet list, not a structured screen list, so we don't
# generate screen IDs — only the bullet text is carried.
_SEC2_RE = re.compile(r"^##\s*§?\s*2\b[^\n]*\n(.*?)(?=^##\s|\Z)", re.S | re.M)


def extract_screen_notes(text: str) -> list[str]:
    """dossier body → top-level bullet text list from the §2 screen section
    (gracefully handles empty/missing)."""
    m = _SEC2_RE.search(text or "")
    if not m:
        return []
    notes: list[str] = []
    for line in m.group(1).splitlines():
        # Top-level bullets only (excludes indented sub-bullets). Starts with '- ' or '* '.
        if re.match(r"^[-*]\s+", line) and not line[:1].isspace():
            notes.append(re.sub(r"^[-*]\s+", "", line).strip())
    return notes


def _board_status(fm: dict) -> str:
    """Normalize draft frontmatter into board status vocabulary
    (empty/ai-draft/human-reviewed/frozen).
    review_status is the lifecycle source of truth (ai-draft -> human-reviewed
    -> frozen, transitioned via /review, /confirm). Older drafts use
    non-standard values (Draft, draft, no-delta) in the status field, so
    review_status takes priority. empty if neither is present."""
    return fm.get("review_status") or fm.get("status") or "empty"


def transform_wo(raw, product: str = "", status_of=None, bdd_of=None, screens_of=None) -> dict:
    """raw index -> contract. status_of(wo_id)->dict|None injects draft
    frontmatter. bdd_of(wo_id)->dict injects {scenarios:int, coverage:str|None}
    BDD badge info. screens_of(wo_id)->list[str] injects the cluster (dossier)
    §2 screen bullets. Cluster records additionally carry
    capability/memberCount/screens, and fall back to record_status (mapped
    new->empty) when frontmatter status is absent."""
    status_of = status_of or (lambda _wo: {})
    bdd_of = bdd_of or (lambda _wo: {})
    screens_of = screens_of or (lambda _wo: [])
    recs = _records(raw)
    items = []
    levels: set[int] = set()
    for r in recs:
        wid = r.get("wo_id", "")
        fm = status_of(wid) or {}
        bdd = bdd_of(wid) or {}
        lvl = int(r.get("level", 0))
        levels.add(lvl)
        # review_status is the lifecycle source of truth (ai-draft ->
        # human-reviewed -> frozen, transitioned via /review, /confirm).
        # Older drafts use non-standard values in status, so review_status
        # takes priority; cluster falls back to record_status.
        raw_status = fm.get("review_status") or fm.get("status") or r.get("record_status") or "empty"
        status = "empty" if raw_status == "new" else raw_status
        members = r.get("members")
        items.append({
            "woId": wid,
            "type": r.get("type", "policy"),
            "level": lvl,
            "status": status,
            "title": r.get("section_title") or r.get("node_name", wid),
            "nodeName": r.get("node_name", ""),
            "sectionId": r.get("section_id", ""),
            "sectionTitle": r.get("section_title", ""),
            "nodeRole": r.get("node_role", "unknown"),
            "deltaRequired": bool(r.get("delta_required", False)),
            "linkedWos": r.get("linked_wos", []),
            "draftPath": r.get("draft_path") or f"drafts/{wid}.draft.md",
            "reviewedBy": fm.get("reviewed_by") or None,
            "reviewedAt": fm.get("reviewed_at") or None,
            "capability": r.get("capability") or None,
            "memberCount": len(members) if isinstance(members, list) else None,
            "screens": (screens_of(wid) if r.get("type") == "cluster" else []),
            "bddScenarios": int(bdd.get("scenarios", 0)),
            "bddCoverage": bdd.get("coverage") or None,
        })
    return {
        "version": "", "product": product, "kind": "work-orders",
        "levels": sorted(levels), "items": items,
    }


def _draft_stem(draft_path: str, wo_id: str) -> str:
    """draft relative path -> stem (.draft.md stripped from filename). node:
    == wo_id, cluster: cluster_{id}."""
    name = Path(draft_path or f"drafts/{wo_id}.draft.md").name
    return name[:-len(".draft.md")] if name.endswith(".draft.md") else Path(name).stem


def main(argv: list[str]) -> int:
    args = C.make_parser("wo").parse_args(argv)
    if args.from_fixture:
        return C.emit(C.load_fixture(args.from_fixture))
    if not (args.hub_root and args.product):
        sys.stderr.write("--hub-root, --product required\n")
        return 2
    pdir = C.product_dir(args.hub_root, args.product)
    idx = pdir / "work-orders" / "index.json"
    cidx = pdir / "work-orders" / "cluster_index.json"
    if idx.exists():
        records = _records(json.loads(idx.read_text(encoding="utf-8")))
    elif cidx.exists():
        records = normalize_cluster_records(json.loads(cidx.read_text(encoding="utf-8")))
    else:
        sys.stderr.write(f"Neither index.json nor cluster_index.json found: {pdir / 'work-orders'}\n")
        return C.emit({"version": "empty", "product": args.product,
                       "kind": "work-orders", "levels": [], "items": []}) or 1

    path_of = {r.get("wo_id", ""): r.get("draft_path") or f"drafts/{r.get('wo_id','')}.draft.md"
               for r in records}
    stem_of = {wid: _draft_stem(dp, wid) for wid, dp in path_of.items()}

    def _doc_id(wo_id: str) -> str:
        # The WO number (WO-NN) can differ from the actual draft filename
        # (doc_id). BDD artifacts (reports/bdd/{doc_id}.feature, coverage
        # queue) key on the draft stem (doc_id), so we must resolve via
        # draft_path — same as status_of — for the badge to match.
        return doc_id_of(path_of.get(wo_id) or f"drafts/{wo_id}.draft.md")

    def status_of(wo_id: str) -> dict:
        d = pdir / path_of.get(wo_id, f"drafts/{wo_id}.draft.md")
        if not d.exists():
            return {}
        return C.read_frontmatter(d.read_text(encoding="utf-8"))

    def screens_of(wo_id: str) -> list[str]:
        d = pdir / path_of.get(wo_id, f"drafts/{wo_id}.draft.md")
        if not d.exists():
            return []
        return extract_screen_notes(d.read_text(encoding="utf-8"))

    cov_q = pdir / "reports" / "bdd-coverage-queue.md"
    coverage = parse_coverage(cov_q.read_text(encoding="utf-8")) if cov_q.exists() else {}

    def bdd_of(wo_id: str) -> dict:
        # Matches the BDD artifact key when the WO number (WO-NN) != draft filename (doc_id) (gitlab regression fix).
        doc = _doc_id(wo_id)
        feat = pdir / "reports" / "bdd" / f"{doc}.feature"
        n = feat.read_text(encoding="utf-8").count("Scenario:") if feat.exists() else 0
        return {"scenarios": n, "coverage": coverage.get(doc)}

    return C.emit(transform_wo(records, args.product, status_of, bdd_of, screens_of))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
