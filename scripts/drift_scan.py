#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Common (G2-A/B) ↔ product draft referenced_master pin drift scanner (WP2 — C-PIN).

Purpose:
    As the G2-A/G2-B common policy keeps getting updated, track which version an
    already-written product draft is based on via the frontmatter
    `referenced_master: [{id}@{ver}, ...]` pin. This script diffs the pin against
    the current common version, classifies drift into tiers, and generates
    reports/drift-queue.md.

    Pure script (no model involvement). The model only reads the drift-queue.md
    summary. Common documents are read-only — never modified.

Tier policy (gates/drift-gate.md SSoT):
    OK         : pinned version == current version
    WARN       : minor/patch bump · pin > current (anomaly) · version unknown (mtime fallback) · pin unresolved
    BLOCK      : major bump (precise detection of referenced-§section changes is unsupported due to
                 snapshot limitations — treated conservatively)
    (empty referenced_master = no common reference → not drift, counted for info only.
     opt-out justification is owned by master-derivation-gate)

Common-metadata multi-format parser:
    1) YAML frontmatter  : `version:` / `doc_id:` / `last_updated:`
    2) bold inline       : `**버전:** 1.2.0` / `**문서 ID:** \`X\`` / `**최종 업데이트:** ...`
    3) markdown table    : `| **doc_id** | \`X\` |` / `| **version** | ... |`
    + pin-ID resolution: (a) CONTEXT/reference-docs/master-id-map.yml alias map (if present)
                 (b) exact match on extracted doc_id  (c) partial match on filename/heading  (d) unresolved → WARN

Usage:
    python drift_scan.py --hub-root <Hub> [--product <name>]
    (all of PROJECTS/* if --product is omitted)

exit code:
    0 = no BLOCK drift (WARN/UNRESOLVED are non-blocking)
    1 = one or more BLOCK drift (subject to drift-gate blocking)
    2 = argument error
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 so non-ASCII print doesn't crash on Windows' default console (cp949, etc.).
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
PIN = re.compile(r"^\s*([^@\s]+)\s*@\s*v?([0-9][0-9.]*)\s*$")
VER_TOKEN = re.compile(r"v?([0-9]+(?:\.[0-9]+)*)")


def _parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER.match(text)
    if not m:
        return {}
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm


def _parse_list(raw) -> list[str]:
    if isinstance(raw, list):
        return raw
    raw = (raw or "").strip()
    if not raw or raw == "[]":
        return []
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [x.strip() for x in raw.split(",") if x.strip()]


def _extract_master_meta(path: Path) -> dict:
    """Extract doc_id / version / update-timestamp from a single common document, across multiple formats."""
    text = path.read_text(encoding="utf-8", errors="replace")
    head = text[:4000]
    doc_id = ""
    version = ""
    updated = ""

    fm = _parse_frontmatter(text)
    if fm:
        doc_id = fm.get("doc_id", "") or doc_id
        version = fm.get("version", "") or version
        updated = fm.get("last_updated", "") or updated

    # In bold/table formats, the colon can appear anywhere inside or outside the closing **
    # (observed in the wild: `**문서 ID:** \`X\``, `**버전:** 1.2.0`, `| **doc_id** | \`X\` |`).
    # NOTE: the Korean labels below (문서 ID / 버전 / 최종 업데이트) are intentionally kept —
    # they match real-world common-policy documents still authored in Korean, not code.
    if not doc_id:
        m = (re.search(r"\*\*\s*(?:문서\s*ID|doc_id)\s*[:：]?\s*\*\*\s*[:：]?\s*`?([A-Za-z0-9._-]+)`?", head, re.I)
             or re.search(r"\|\s*\*\*\s*doc_id\s*\*\*\s*\|\s*`?([A-Za-z0-9._-]+)`?", head, re.I))
        if m:
            doc_id = m.group(1).strip()
    if not version:
        m = (re.search(r"\*\*\s*(?:버전|version)\s*[:：]?\s*\*\*\s*[:：]?\s*`?([0-9]+(?:\.[0-9]+)*)`?", head, re.I)
             or re.search(r"\|\s*\*\*\s*(?:버전|version)\s*\*\*\s*\|\s*`?([0-9]+(?:\.[0-9]+)*)`?", head, re.I))
        if m:
            version = m.group(1).strip()
    if not updated:
        m = re.search(r"\*\*최종\s*업데이트\*\*\s*[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", head)
        if m:
            updated = m.group(1)

    # Layer extraction — PREFIX-independent (dynamic). Extracted from a `[G2-B]`-style
    # label in the body, or from the path.
    # Accepts both the new nested layout (`reference-docs/{PREFIX}/B/`) and the legacy
    # flat layout (`reference-docs/B/`).
    layer = ""
    lm = (re.search(r"\[([A-Za-z0-9]+-[ABC])\]", head)
          or re.search(r"reference-docs[/\\](?:[A-Za-z0-9]+[/\\])?([ABC])[/\\]", str(path)))
    if lm:
        layer = lm.group(1)

    return {
        "path": path,
        "stem": path.stem,
        "doc_id": doc_id,
        "version": version,
        "updated": updated,
        "mtime": path.stat().st_mtime,
        "layer": layer,
    }


def _load_alias_map(hub_root: Path) -> dict:
    """Optional alias map: CONTEXT/reference-docs/master-id-map.yml (simple key: value parsing)."""
    p = hub_root / "CONTEXT" / "reference-docs" / "master-id-map.yml"
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


def _build_registry(hub_root: Path) -> list[dict]:
    """Collect common-document metadata across all of the A/B/C layers.

    Dual paths (safety net for gradual migration):
      - new nested: ``reference-docs/{PREFIX}/{A,B,C}/*.md`` (iterated across every PREFIX)
      - legacy flat: ``reference-docs/{A,B,C}/*.md``
    The same file should never be caught by both, but resolve()-based dedup is applied
    as a safety measure regardless.
    """
    reg: list[dict] = []
    base = hub_root / "CONTEXT" / "reference-docs"
    if not base.is_dir():
        return reg

    search_dirs: list[Path] = [base / layer for layer in ("A", "B", "C")]  # legacy flat
    for prefix_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        search_dirs.extend(prefix_dir / layer for layer in ("A", "B", "C"))  # new nested

    seen: set[Path] = set()
    for d in search_dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            if f.name == "README.md":
                continue
            key = f.resolve()
            if key in seen:
                continue
            seen.add(key)
            reg.append(_extract_master_meta(f))
    return reg


def _resolve(pin_id: str, registry: list[dict], amap: dict) -> dict | None:
    if pin_id in amap:
        target = amap[pin_id]
        for e in registry:
            if e["stem"] == target or e["path"].name == target or e["doc_id"] == target:
                return e
    for e in registry:
        if e["doc_id"] and e["doc_id"] == pin_id:
            return e
    low = pin_id.lower()
    for e in registry:
        if low in e["stem"].lower() or (e["doc_id"] and low in e["doc_id"].lower()):
            return e
    return None


def _ver_tuple(v: str) -> tuple[int, ...] | None:
    m = VER_TOKEN.search(v or "")
    if not m:
        return None
    try:
        return tuple(int(x) for x in m.group(1).split("."))
    except ValueError:
        return None


def _classify(pinned: str, current: str, entry: dict) -> tuple[str, str]:
    pt, ct = _ver_tuple(pinned), _ver_tuple(current)
    if pt is None or ct is None:
        return "WARN", f"version unparseable (pin={pinned!r} current={current!r}) — mtime fallback recommended"
    L = max(len(pt), len(ct))
    pt += (0,) * (L - len(pt))
    ct += (0,) * (L - len(ct))
    if pt == ct:
        return "OK", "pin == current"
    if pt > ct:
        return "WARN", f"pin({pinned}) > current({current}) — anomaly, check pin notation"
    idx = next(i for i in range(L) if pt[i] != ct[i])
    if idx == 0:
        return "BLOCK", f"major bump {pinned}→{current} — revalidation required"
    kind = "minor" if idx == 1 else "patch"
    return "WARN", f"{kind} bump {pinned}→{current} — revalidation recommended (non-blocking)"


def scan(hub_root: Path, product: str | None = None) -> int:
    registry = _build_registry(hub_root)
    amap = _load_alias_map(hub_root)
    projects_root = hub_root / "PROJECTS"
    if not projects_root.is_dir():
        print(f"[drift_scan] no PROJECTS: {projects_root} — nothing to scan")
        return 0

    products = (
        [projects_root / product]
        if product
        else sorted(p for p in projects_root.iterdir() if p.is_dir())
    )

    total_block = 0
    for proj in products:
        drafts_dir = proj / "drafts"
        if not drafts_dir.is_dir():
            continue
        rows: list[tuple] = []
        no_pin = 0
        for draft in sorted(drafts_dir.glob("*.draft.md")):
            fm = _parse_frontmatter(draft.read_text(encoding="utf-8", errors="replace"))
            pins = _parse_list(fm.get("referenced_master", []))
            if not pins:
                no_pin += 1
                continue
            for pin in pins:
                pm = PIN.match(pin)
                if not pm:
                    rows.append((draft.name, pin, "-", "WARN",
                                 "malformed pin (expected: id@vX.Y[.Z])"))
                    continue
                pid, pver = pm.group(1), pm.group(2)
                entry = _resolve(pid, registry, amap)
                if entry is None:
                    rows.append((draft.name, pin, "-", "UNRESOLVED",
                                 f"'{pid}' cannot be resolved in reference-docs — register in master-id-map.yml or fix the pin"))
                    continue
                cur = entry["version"] or ""
                if not cur:
                    rows.append((draft.name, pin,
                                 f"(version unknown, upd={entry['updated'] or '?'})",
                                 "WARN", f"{entry['path'].name} has no version metadata — mtime fallback"))
                    continue
                status, reason = _classify(pver, cur, entry)
                if status == "BLOCK":
                    total_block += 1
                rows.append((draft.name, pin, cur, status, reason))

        # Diff rendered_from_master pins in the complete version (post C-RENDER) (WP5 linkage)
        rdir = proj / "reports" / "render"
        if rdir.is_dir():
            for comp in sorted(rdir.glob("*.complete.md")):
                cfm = _parse_frontmatter(
                    comp.read_text(encoding="utf-8", errors="replace"))
                rpins = _parse_list(cfm.get("rendered_from_master", []))
                if not rpins:
                    continue
                tag = f"render/{comp.name}"
                for pin in rpins:
                    if pin.strip().endswith("@v?") or "@v?" in pin:
                        rows.append((tag, pin, "-", "WARN",
                                     "[complete] version unknown at expansion time — recommend re-render "
                                     "after pinning the source referenced_master"))
                        continue
                    pm = PIN.match(pin)
                    if not pm:
                        rows.append((tag, pin, "-", "WARN", "[complete] malformed pin"))
                        continue
                    pid, pver = pm.group(1), pm.group(2)
                    entry = _resolve(pid, registry, amap)
                    if entry is None:
                        rows.append((tag, pin, "-", "UNRESOLVED",
                                     f"[complete] '{pid}' cannot be resolved — master-id-map.yml"))
                        continue
                    cur = entry["version"] or ""
                    if not cur:
                        rows.append((tag, pin, "(version unknown)", "WARN",
                                     f"[complete] {entry['path'].name} has no version metadata"))
                        continue
                    status, reason = _classify(pver, cur, entry)
                    if status == "BLOCK":
                        total_block += 1
                    rows.append((tag, pin, cur, status,
                                 f"[complete] {reason}"
                                 + (" — re-render required" if status == "BLOCK" else "")))

        reports = proj / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        qpath = reports / "drift-queue.md"
        n_block = sum(1 for r in rows if r[3] == "BLOCK")
        n_warn = sum(1 for r in rows if r[3] in ("WARN", "UNRESOLVED"))
        lines = [
            f"# drift-queue — {proj.name}",
            "",
            f"> Generated: {datetime.now().isoformat(timespec='seconds')} · auto-generated by drift_scan.py (do not edit)",
            f"> **BLOCK: {n_block} · WARN/UNRESOLVED: {n_warn} · drafts with no common reference: {no_pin}**",
            "",
            "| draft | pin | current version | status | reason |",
            "|---|---|---|---|---|",
        ]
        if rows:
            for d, pin, cur, st, why in rows:
                lines.append(f"| {d} | `{pin}` | {cur} | **{st}** | {why} |")
        else:
            lines.append("| _(no drift)_ | — | — | OK | all draft pins == current |")
        lines += [
            "",
            "## Handling criteria (gates/drift-gate.md)",
            "- BLOCK: blocks Phase progression until the draft is revalidated",
            "- WARN/UNRESOLVED: non-blocking, batch-revalidate at the next Phase boundary",
            "- No common reference (empty pin list): opt-out justification is confirmed in master-derivation-gate",
        ]
        qpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[drift_scan] {proj.name}: BLOCK={n_block} WARN/UNRESOLVED={n_warn} "
              f"no-ref={no_pin} → {qpath.relative_to(hub_root)}")

    print(f"[drift_scan] done — total BLOCK {total_block}"
          + ("" if total_block == 0 else " (drift-gate blocked)"))
    return 1 if total_block else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Common↔draft referenced_master drift scan")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", default=None, help="PROJECTS/<product> (omit for all)")
    ap.add_argument("--check", action="store_true",
                    help="(kept for compatibility) same behavior — always read-only, drafts unchanged")
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    return scan(args.hub_root, args.product)


if __name__ == "__main__":
    sys.exit(main())
