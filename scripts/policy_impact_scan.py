#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Policy §-section → screen impact scanner (WP8-2 · Contract C-PIMPACT).

Purpose:
    When a specific §section in a product's policy document (POL draft) changes,
    identifies — at §-granularity — the screen drafts (S0N) that reference that §.
    A product-internal cousin of common→product drift (drift_scan); the
    mechanism is a §content-hash snapshot diff (not a version).

    Pure script (no model involved). The model only reads the
    policy-impact-queue.md summary. Does not modify POL/screen drafts
    (read-only + queue/snapshot output only).

Verdicts (SSoT: gates/policy-impact-gate.md):
    IMPACT  : screen-referenced § ∩ changed § ≠ ∅ (exact match) → BLOCK
    COARSE  : § can't be matched exactly, but referenced_policy pin version < current POL → WARN
    WARN    : referenced_policy pin missing / [[POL §X]] non-standard marker (UNRESOLVED)
    OK      : no change among referenced § & pin version matches
    BASELINE: no snapshot yet, first run → generate snapshot, defer verdict (INFO)

Snapshot: graph/policy-section-hashes.json (baseline as of the last reconciliation).
Rebaseline: after the PM finishes reconciling screens, re-record the current
state with --rebaseline.

Usage:
    python policy_impact_scan.py --hub-root <Hub> --product <p> [--rebaseline]

exit code: 0 no IMPACT / 1 IMPACT≥1 (gate blocked) / 2 argument error
"""
from __future__ import annotations

import argparse
import hashlib
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
HEADING = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
# §id token (section-style only): 4 / 4-1 / 4.1 / 4-1(3) / 4-6-2 / A / B-1.
# Non-§ headings (TOC/Workflow/appendix/P1, etc.) don't match the token → not tracked (noise reduction).
SEC_TOKEN = re.compile(
    r"^(?:§\s*)?("
    r"\d+(?:[-.]\d+)*(?:\([0-9A-Za-z]+\))?"   # 4, 4-1, 4.1, 4-6-2, 4-1(3)
    r"|[A-Z](?:-\d+)?"                          # A, B, B-1
    r")(?=[\s.\)]|$)"
)
POL_MARKER = re.compile(r"\[\[\s*POL\s*§?\s*([A-Za-z0-9][\w.\-()]*?)\s*\]\]")
VER = re.compile(r"v?([0-9]+(?:\.[0-9]+)*)")
# NOTE: "버전" (Korean for "version") is kept in the regex below — it matches a
# real label used in Hub policy documents; the English "version" alternative is
# already handled too. Functional Korean-language pattern data, not a translation gap.
VER_LINE = re.compile(r"(?:\*\*\s*버전\s*[:：]?\s*\*\*|^version\s*:|\*\*\s*version\s*[:：]?\s*\*\*)"
                      r"\s*[:：]?\s*`?v?([0-9]+(?:\.[0-9]+)*)`?", re.I | re.M)


def _norm(s: str) -> str:
    """§id normalization — preserves separators (-.()) to avoid collisions
    (6-2 vs 4-6-2 vs 6.2). Strips whitespace/§/leading-trailing periods only,
    then lowercases."""
    return str(s).strip().strip(".").replace("§", "").replace(" ", "").lower()


def _frontmatter(text: str) -> tuple[dict, str]:
    m = FRONTMATTER.match(text)
    if not m:
        return {}, text
    fm = {}
    for ln in m.group(1).splitlines():
        if ":" in ln:
            k, _, v = ln.partition(":")
            fm[k.strip()] = v.strip()
    return fm, text[m.end():]


def _ver_tuple(v: str):
    m = VER.search(v or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def _pol_version(text: str, fm: dict) -> str:
    if fm.get("version"):
        return fm["version"]
    m = VER_LINE.search(text[:4000])
    return m.group(1) if m else ""


def _sections(text: str) -> dict:
    """POL body §sections → {norm_id: {title, hash}} (parsed the same way as build_b_index)."""
    lines = text.splitlines()
    heads = []
    for i, ln in enumerate(lines):
        m = HEADING.match(ln)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    out = {}
    for hi, (li, depth, title) in enumerate(heads):
        tok = SEC_TOKEN.match(title)
        if not tok:
            continue  # non-§ heading (TOC/Workflow/appendix/P1, etc.) not tracked — noise reduction
        end = len(lines)
        for nj, nd, _ in heads[hi + 1:]:
            if nd <= depth:
                end = nj
                break
        sid = tok.group(1)
        key = _norm(sid)
        if key in out:                       # don't overwrite on norm collision
            n = 2
            while f"{key}#{n}" in out:
                n += 1
            key = f"{key}#{n}"
        body = "\n".join(lines[li:end]).strip()
        h = hashlib.sha256(body.encode("utf-8", "replace")).hexdigest()[:12]
        out[key] = {"raw_id": sid, "title": title[:80], "hash": h}
    return out


def _policy_drafts(drafts: Path):
    pol = []
    for d in sorted(drafts.glob("*.draft.md")):
        if "POL" in d.stem.upper():
            pol.append(d)
            continue
        fm, _ = _frontmatter(d.read_text(encoding="utf-8", errors="replace"))
        if fm.get("type") == "policy":
            pol.append(d)
    return pol


def scan(hub: Path, product: str, rebaseline: bool) -> int:
    proj = hub / "PROJECTS" / product
    drafts = proj / "drafts"
    if not drafts.is_dir():
        sys.stderr.write(f"drafts not found: {drafts}\n")
        return 2

    pol_drafts = _policy_drafts(drafts)
    cur_secs: dict = {}
    pol_version = ""
    for pd in pol_drafts:
        raw = pd.read_text(encoding="utf-8", errors="replace")
        fm, body = _frontmatter(raw)
        pol_version = pol_version or _pol_version(raw, fm)
        for k, v in _sections(body or raw).items():
            v["src"] = pd.name
            cur_secs[k] = v

    snap_path = proj / "graph" / "policy-section-hashes.json"
    snap_path.parent.mkdir(parents=True, exist_ok=True)

    if rebaseline or not snap_path.exists():
        snap_path.write_text(json.dumps({
            "_meta": {"product": product, "policy_version": pol_version,
                      "generated_at": datetime.now().isoformat(timespec="seconds"),
                      "source_drafts": [p.name for p in pol_drafts]},
            "sections": cur_secs,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[policy_impact_scan] {'rebaselined' if rebaseline else 'baseline generated'}"
              f" — {len(cur_secs)} §, v{pol_version or '?'} → {snap_path.relative_to(hub)}")
        if not rebaseline:
            print("[policy_impact_scan] first run: IMPACT verdict deferred (BASELINE).")
        return 0

    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    snap_secs = snap.get("sections", {})
    snap_ver = snap.get("_meta", {}).get("policy_version", "")
    changed = {k for k, v in cur_secs.items()
               if k not in snap_secs or snap_secs[k]["hash"] != v["hash"]}
    changed |= {k for k in snap_secs if k not in cur_secs}

    rows = []
    impact_n = 0
    for sd in sorted(drafts.glob("*.draft.md")):
        if sd in pol_drafts:
            continue
        raw = sd.read_text(encoding="utf-8", errors="replace")
        fm, body = _frontmatter(raw)
        if fm.get("type") and fm["type"] != "screen":
            continue
        refs = {_norm(m) for m in POL_MARKER.findall(body or raw)}
        pin = fm.get("referenced_policy", "")
        pin_ver = pin.split("@")[-1].lstrip("v@ ") if "@" in pin else ""
        if not refs and "[[POL" not in (body or raw) and "POL §" not in (body or raw):
            rows.append((sd.name, pin or "-", "—", "WARN",
                         "No policy §-reference marker — the standard [[POL §X-Y]] marker is required"))
            continue
        hit = sorted(refs & changed)
        if hit:
            impact_n += 1
            raw_hits = ", ".join(cur_secs.get(h, {}).get("raw_id", h) for h in hit)
            rows.append((sd.name, pin or "(no pin)", f"changed § {raw_hits}",
                         "IMPACT", "Referenced policy § changed — screen re-review and reconciliation required"))
            continue
        if not pin:
            rows.append((sd.name, "(no pin)", f"{len(refs)} § referenced", "WARN",
                         "referenced_policy pin missing — cannot be tracked by C-PIMPACT"))
            continue
        pv, cv = _ver_tuple(pin_ver), _ver_tuple(pol_version)
        if pv and cv and pv < cv:
            rows.append((sd.name, pin, f"{len(refs)} § referenced", "COARSE",
                         f"pin v{pin_ver} < POL v{pol_version} — no exact § change, "
                         f"recommend review via version fallback"))
            continue
        rows.append((sd.name, pin, f"{len(refs)} § referenced", "OK",
                     "No change among referenced § & pin matches"))

    qdir = proj / "reports"
    qdir.mkdir(parents=True, exist_ok=True)
    q = qdir / "policy-impact-queue.md"
    n_w = sum(1 for r in rows if r[3] in ("WARN", "COARSE"))
    lines = [
        f"# policy-impact-queue — {product}",
        "",
        f"> Generated: {datetime.now().isoformat(timespec='seconds')} · policy_impact_scan.py (do not edit)",
        f"> POL v{pol_version or '?'} vs snapshot v{snap_ver or '?'} · "
        f"changed §: {len(changed)} · **IMPACT: {impact_n} · WARN/COARSE: {n_w}**",
        "",
        "| Screen draft | referenced_policy | Referenced/changed § | Status | Reason |",
        "|---|---|---|---|---|",
    ]
    if rows:
        for d, p, s, st, why in rows:
            lines.append(f"| {d} | `{p}` | {s} | **{st}** | {why} |")
    else:
        lines.append("| _(no screen drafts)_ | — | — | OK | — |")
    lines += [
        "",
        "## Handling criteria (gates/policy-impact-gate.md)",
        "- IMPACT (exact): blocks phase progress until the screen is reconciled. After reconciliation, run --rebaseline",
        "- COARSE (version fallback): non-blocking WARN — no exact § change, recommend updating the pin version",
        "- WARN: reinforce the standard [[POL §X-Y]] marker / referenced_policy pin",
        f"- Changed § list: {', '.join(sorted(cur_secs.get(c,{}).get('raw_id',c) for c in changed)) or 'none'}",
    ]
    q.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[policy_impact_scan] {product}: IMPACT={impact_n} WARN/COARSE={n_w} "
          f"changed§={len(changed)} → {q.relative_to(hub)}")
    print(f"[policy_impact_scan] done — IMPACT {impact_n}"
          + ("" if impact_n == 0 else " (policy-impact-gate blocked)"))
    return 1 if impact_n else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Policy §→screen impact scan (C-PIMPACT)")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", required=True)
    ap.add_argument("--rebaseline", action="store_true",
                    help="Re-record the current POL § hashes as the reconciliation-baseline snapshot (after PM reconciliation)")
    a = ap.parse_args()
    if not a.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {a.hub_root}\n")
        return 2
    return scan(a.hub_root, a.product, a.rebaseline)


if __name__ == "__main__":
    sys.exit(main())
