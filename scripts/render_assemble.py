#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""C-RENDER complete-version (secondary) deterministic assembler (WP5).

Purpose:
    Takes a source draft (primary: Delta + [{doc_id} §X reference] links) as
    input and generates the planner's canonical secondary view by inlining
    common (G2-A/G2-B) references via **deterministic text substitution**.
    No model involved — no re-emission of common text (token-boundary/SSoT
    accuracy). Common content is read-only.

Resolution chain:
    [{ID} ... §{sec} reference]  /  Full base-policy application — reference [{ID} ...]
      → master-id-map.yml (pin ID → file stem)
      → B-headings-index.json (stem key → path·section line ranges)
      → inline the matching §-line slice of the common file, tagged with its source.
    G2-A terms: expand the canonical definition (as it appears in the body)
      from terms.yml (derived cache) into an appendix.

Output:
    reports/render/{WO_ID}.complete.md  (single)
    reports/render/{product}.full.complete.md  (--all)
    frontmatter rendered_from_master: [{id}@{version}] pins →
      drift_scan.py also checks the complete version for staleness (WP5 integration).

Usage:
    python render_assemble.py --hub-root <Hub> --product <p> [--wo <WO_ID>] [--all]

exit code: 0 success / 1 no input · fatal / 2 argument error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
PIN = re.compile(r"^\s*([^@\s]+)\s*@\s*v?([0-9][0-9.]*)\s*$")
# Marker phrasing PMs write in Hub draft documents to request an inline
# expansion — matches the "Resolution chain" formats documented above:
# whole-document delegation ("Full base-policy application — reference [{ID}]")
# and section-level reference ("[{ID} §X reference]").
WHOLE_REF = re.compile(r"Full base-policy application\s*[—\-]\s*reference\s*\[([^\]]+)\]")
SEC_REF = re.compile(r"\[([^\]\n§]+?)(?:\s*§\s*([A-Za-z0-9][\w.\-]*))?\s*reference\]")
ID_TOKEN = re.compile(r"([A-Za-z0-9]+-[ABC]-\d+|PLATFORM\.[A-Za-z.]+|common\.[\w.\-]+|[A-Za-z0-9_\-]+)")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = FRONTMATTER.match(text)
    if not m:
        return {}, text
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, text[m.end():]


def _parse_list(raw) -> list[str]:
    if isinstance(raw, list):
        return raw
    raw = (raw or "").strip()
    if not raw or raw == "[]":
        return []
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [x.strip() for x in raw.split(",") if x.strip()]


def _load_alias_map(hub: Path) -> dict:
    p = hub / "CONTEXT" / "reference-docs" / "master-id-map.yml"
    amap: dict = {}
    if not p.exists():
        return amap
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        amap[k.strip()] = v.strip().strip("'\"")
    return amap


def _active_prefix(hub: Path) -> str | None:
    cfg = hub / "CONTEXT" / "layer-config.md"
    if not cfg.exists():
        return None
    text = cfg.read_text(encoding="utf-8", errors="replace")
    m = (re.search(r"^ACTIVE_PREFIX:\s*([A-Za-z0-9_-]+)\s*$", text, re.M)
         or re.search(r"^PREFIX:\s*([A-Za-z0-9_-]+)\s*$", text, re.M))
    return m.group(1) if m else None


def _load_b_index(hub: Path) -> dict:
    cache_dir = hub / "CONTEXT" / ".template-cache"
    # Prefer the PREFIX-namespaced index; fall back to the legacy non-namespaced one.
    prefix = _active_prefix(hub)
    candidates = []
    if prefix:
        candidates.append(cache_dir / f"{prefix}-b-headings-index.json")
    candidates.append(cache_dir / "B-headings-index.json")
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8")).get("documents", {})
            except Exception:
                return {}
    return {}


def _load_terms(hub: Path) -> list[tuple[str, str]]:
    p = hub / "CONTEXT" / "glossary" / "terms.yml"
    if not p.exists():
        return []
    out: list[tuple[str, str]] = []
    cur = None
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        m = re.match(r"-\s*canonical_name\s*:\s*(.+)$", s)
        if m:
            cur = m.group(1).strip().strip("'\"")
            continue
        m = re.match(r"definition\s*:\s*(.+)$", s)
        if m and cur:
            out.append((cur, m.group(1).strip().strip("'\"")))
            cur = None
    return out


def _resolve_doc(token: str, amap: dict, bidx: dict) -> dict | None:
    stem = amap.get(token)
    if stem:
        for k, e in bidx.items():
            if k == stem or e.get("doc_id") == stem or Path(e.get("path", "")).stem == stem:
                return e
    if token in bidx:
        return bidx[token]
    for k, e in bidx.items():
        if e.get("doc_id") == token:
            return e
    low = token.lower()
    for k, e in bidx.items():
        if low in k.lower() or low in str(e.get("doc_id", "")).lower():
            return e
    return None


def _section_text(hub: Path, entry: dict, sec: str | None) -> tuple[str, str]:
    """(extracted text, label). If sec is absent, the entire document (capped at 400 lines)."""
    fp = hub / entry["path"]
    if not fp.exists():
        return f"⚠️ Common file not found: {entry['path']}", "MISSING"
    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
    if sec:
        def _norm(x: str) -> str:
            return re.sub(r"[\s.\-]+", "", str(x)).lower()
        nsec = _norm(sec)
        secs = entry.get("sections", [])
        # 1) exact id match  2) normalized-title prefix/contains match (real-world common docs use A/B/B-1 alpha sections)
        for s in secs:
            if s["id"] == sec:
                seg = lines[s["line_start"] - 1: s["line_end"]]
                return "\n".join(seg).strip(), f"§{sec} {s.get('title','')}".strip()
        for s in secs:
            nt = _norm(s.get("title", ""))
            if nsec and (nt.startswith(nsec) or nsec in nt):
                seg = lines[s["line_start"] - 1: s["line_end"]]
                return "\n".join(seg).strip(), f"§{sec} {s.get('title','')}".strip()
        return (f"⚠️ §{sec} not found — refresh B-headings-index (run build_b_index.py) "
                f"or correct the pin/§ notation", f"§{sec} (not found)")
    seg = lines[:400]
    tail = "" if len(lines) <= 400 else "\n\n…(truncated — see the full common source for the complete text)"
    return "\n".join(seg).strip() + tail, "entire document"


def _pin_version(token: str, pins: list[str], amap: dict) -> str:
    for p in pins:
        m = PIN.match(p)
        if not m:
            continue
        pid = m.group(1)
        if pid == token or amap.get(pid) == amap.get(token) or amap.get(token) == pid:
            return m.group(2)
    return "?"


def assemble_one(hub: Path, draft: Path, amap: dict, bidx: dict,
                 terms: list[tuple[str, str]]) -> tuple[str, list[str]]:
    raw = draft.read_text(encoding="utf-8", errors="replace")
    fm, body = _parse_frontmatter(raw)
    pins = _parse_list(fm.get("referenced_master", []))
    rendered_from: set[str] = set()

    def _inline(token_raw: str, sec: str | None) -> str:
        tok_m = ID_TOKEN.match(token_raw.strip())
        token = tok_m.group(1) if tok_m else token_raw.strip().split()[0]
        entry = _resolve_doc(token, amap, bidx)
        if entry is None:
            return (f"\n> ⟦expand failed: '{token}' could not be resolved — register it in "
                    f"master-id-map.yml or correct the pin⟧\n")
        text, label = _section_text(hub, entry, sec)
        ver = _pin_version(token, pins, amap)
        rendered_from.add(f"{token}@v{ver}")
        return (f"\n> ⟦expand: {token}@v{ver} {label} — source {entry['path']} "
                f"(auto-inlined, edit at the source)⟧\n\n{text}\n\n> ⟦/expand⟧\n")

    body = WHOLE_REF.sub(lambda m: _inline(m.group(1), None), body)
    body = SEC_REF.sub(lambda m: _inline(m.group(1), m.group(2)), body)

    used_terms = [(c, d) for (c, d) in terms if c and c in body]
    appendix = ""
    if used_terms:
        term_doc = f"{_active_prefix(hub) or 'PX'}-A-001"
        appendix = f"\n\n---\n\n## Appendix A. Term definitions ({term_doc} expansion)\n\n"
        appendix += "\n".join(f"- **{c}**: {d}" for c, d in used_terms[:80])
        rendered_from.add(f"{term_doc}@v?")

    rf = sorted(rendered_from)
    wo_id = fm.get("doc_id") or draft.stem.replace(".draft", "")
    header = (
        "---\n"
        f"source_doc_id: {wo_id}\n"
        f"type: {fm.get('type','')}\n"
        f"rendered_at: {datetime.now().isoformat(timespec='seconds')}\n"
        f"rendered_by: render_assemble.py (C-RENDER, deterministic, no model involved)\n"
        f"rendered_from_master: [{', '.join(rf)}]\n"
        f"source_referenced_master: [{', '.join(pins)}]\n"
        "---\n\n"
        "> **Auto-expanded canonical view (C-RENDER)** — render_assemble.py is the\n"
        "> planner's canonical view that deterministically inlines the source draft +\n"
        "> common content (G2-A/B).\n"
        "> Do not edit directly (dual authoring = SSoT collapse). Edit the source\n"
        "> (/write · /flow) instead.\n"
        "> When the common version bumps, drift_scan flags this as stale → re-render is required.\n\n"
        "---\n"
    )
    return header + body + appendix + "\n", rf


def main() -> int:
    ap = argparse.ArgumentParser(description="C-RENDER complete-version deterministic assembly")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", required=True)
    ap.add_argument("--wo", default=None, help="Single WO_ID (omit = all drafts)")
    ap.add_argument("--all", action="store_true", help="Additionally generate {product}.full.complete.md")
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2

    hub = args.hub_root
    proj = hub / "PROJECTS" / args.product
    drafts_dir = proj / "drafts"
    if not drafts_dir.is_dir():
        sys.stderr.write(f"drafts not found: {drafts_dir}\n")
        return 1

    amap = _load_alias_map(hub)
    bidx = _load_b_index(hub)
    terms = _load_terms(hub)
    if not bidx:
        print("[render_assemble] WARN: B-headings-index.json not found — "
              "recommend running build_b_index.py. §-reference inlining will be limited")

    targets = (
        [drafts_dir / f"{args.wo}.draft.md"] if args.wo
        else sorted(drafts_dir.glob("*.draft.md"))
    )
    targets = [t for t in targets if t.exists()]
    if not targets:
        sys.stderr.write("No target drafts\n")
        return 1

    out_dir = proj / "reports" / "render"
    out_dir.mkdir(parents=True, exist_ok=True)
    full_parts: list[str] = []
    for d in targets:
        doc, rf = assemble_one(hub, d, amap, bidx, terms)
        wo = d.stem.replace(".draft", "")
        (out_dir / f"{wo}.complete.md").write_text(doc, encoding="utf-8")
        full_parts.append(f"\n\n<!-- ===== {wo} ===== -->\n\n" + doc)
        print(f"[render_assemble] {wo}.complete.md ← rendered_from_master={rf or '[]'}")

    if args.all and not args.wo:
        (out_dir / f"{args.product}.full.complete.md").write_text(
            "".join(full_parts), encoding="utf-8")
        print(f"[render_assemble] {args.product}.full.complete.md ({len(targets)} draft)")

    print(f"[render_assemble] done — {len(targets)} file(s) → "
          f"{(out_dir).relative_to(hub)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
