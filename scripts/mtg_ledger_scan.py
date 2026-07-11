#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Meeting decisions ledger ↔ screen pin deterministic cross-check (WP8-4 · contract C-MTG).

Purpose:
    **Deterministically cross-check only** `meetings/mtg-ledger.md` (PM's
    canonical source) against the screen draft frontmatter's
    `meeting_decisions: [MTG-NN]` pins.
    Classification/summary is **never auto-generated/extracted** from meeting
    minutes prose (hallucination / C5 violation).
    The ledger is authored by the PM; this script only reads, validates, and
    produces a queue.

Checks (all deterministic):
    - SCREEN-DELEGATED rows:
        - open + no screen reflects it in meeting_decisions → BLOCK (delegation not reflected)
        - open + due date (YYYY-MM-DD) < today → WARN (overdue)
        - closed + closure rationale blank or not reflected → WARN (incomplete closure)
    - MTG-NN referenced in screen meeting_decisions:
        - not in the ledger → FAIL (claims an unregistered MTG)
        - in the ledger but classification ≠ SCREEN-DELEGATED → WARN (misclassified claim)
    Ledger missing → INFO (not authored — PM should author it). Never auto-generated.

Usage:
    python mtg_ledger_scan.py --hub-root <Hub> --product <p>

exit code: 0 no BLOCK/FAIL / 1 BLOCK·FAIL≥1 (gate blocked) / 2 argument error
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
MTG_ID = re.compile(r"^MTG-\d+$")
DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
CLASSES = {"POLICY-REFLECTED", "SCREEN-DELEGATED", "EXTERNAL-PENDING"}


def _fm(text: str) -> dict:
    m = FRONTMATTER.match(text)
    if not m:
        return {}
    d = {}
    for ln in m.group(1).splitlines():
        if ":" in ln:
            k, _, v = ln.partition(":")
            d[k.strip()] = v.strip()
    return d


def _list(raw) -> list[str]:
    raw = (raw or "").strip()
    if not raw or raw == "[]":
        return []
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [x.strip() for x in raw.split(",") if x.strip()]


def _parse_ledger(p: Path) -> list[dict]:
    """Extract MTG rows from the fixed 7-column pipe table (positional). Skips header/separator rows."""
    rows = []
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cols = [c.strip() for c in s.strip("|").split("|")]
        if not cols or not MTG_ID.match(cols[0]):
            continue
        # 0:ID 1:source 2:summary 3:class 4:target 5:status 6:closure rationale
        c = cols + [""] * (7 - len(cols))
        rows.append({
            "id": c[0], "src": c[1], "summary": c[2],
            "cls": c[3].upper(), "target": c[4],
            "status": c[5].lower(), "closure": c[6],
        })
    return rows


def scan(hub: Path, product: str) -> int:
    proj = hub / "PROJECTS" / product
    drafts = proj / "drafts"
    ledger = proj / "meetings" / "mtg-ledger.md"
    if not drafts.is_dir():
        sys.stderr.write(f"drafts not found: {drafts}\n")
        return 2

    qdir = proj / "reports"
    qdir.mkdir(parents=True, exist_ok=True)
    q = qdir / "mtg-queue.md"

    if not ledger.exists():
        q.write_text(
            f"# mtg-queue — {product}\n\n"
            f"> Generated: {datetime.now().isoformat(timespec='seconds')} · mtg_ledger_scan.py\n"
            f"> **INFO: mtg-ledger not authored** — the PM must author "
            f"`meetings/mtg-ledger.md` for C-MTG tracking to work "
            f"(template: templates/mtg-ledger-template.md). "
            f"Not auto-generated (no hallucinated content).\n",
            encoding="utf-8")
        print(f"[mtg_ledger_scan] {product}: ledger not authored — INFO (not auto-generated)")
        return 0

    led = _parse_ledger(ledger)
    led_ids = {r["id"]: r for r in led}

    # collect screen meeting_decisions
    screen_pins: dict[str, list[str]] = {}   # MTG-ID → [draft...]
    for sd in sorted(drafts.glob("*.draft.md")):
        fm = _fm(sd.read_text(encoding="utf-8", errors="replace"))
        if fm.get("type") and fm["type"] != "screen":
            continue
        for mid in _list(fm.get("meeting_decisions", [])):
            screen_pins.setdefault(mid, []).append(sd.name)

    today = date.today()
    rows = []
    block = fail = 0

    for r in led:
        if r["cls"] not in CLASSES:
            rows.append((r["id"], r["cls"] or "(blank)", "WARN",
                         "classification not a valid enum (POLICY-REFLECTED/SCREEN-DELEGATED/EXTERNAL-PENDING)"))
            continue
        if r["cls"] != "SCREEN-DELEGATED":
            continue
        reflected = screen_pins.get(r["id"], [])
        if r["status"] != "closed" and not reflected:
            block += 1
            rows.append((r["id"], "SCREEN-DELEGATED", "BLOCK",
                         f"delegation open not reflected — no screen has a "
                         f"meeting_decisions pin for {r['id']} (target: {r['target'] or '?'})"))
            continue
        dm = DATE.search(r["target"])
        if r["status"] != "closed" and dm:
            try:
                dl = datetime.strptime(dm.group(1), "%Y-%m-%d").date()
                if dl < today:
                    rows.append((r["id"], "SCREEN-DELEGATED", "WARN",
                                 f"overdue ({dm.group(1)}) open — reflected in: "
                                 f"{', '.join(reflected) or 'none'}"))
                    continue
            except ValueError:
                pass
        if r["status"] == "closed" and (not r["closure"] or not reflected):
            rows.append((r["id"], "SCREEN-DELEGATED", "WARN",
                         f"closed but closure rationale blank or not reflected in a screen "
                         f"(rationale:'{r['closure'] or '-'}' / reflected in:{reflected or 'none'})"))
            continue
        rows.append((r["id"], "SCREEN-DELEGATED", "OK",
                     f"reflected in: {', '.join(reflected)} / status {r['status']}"))

    for mid, ds in sorted(screen_pins.items()):
        if mid not in led_ids:
            fail += 1
            rows.append((mid, "(not in ledger)", "FAIL",
                         f"screen(s) {', '.join(ds)} claim unregistered {mid} — must be registered in the ledger"))
        elif led_ids[mid]["cls"] != "SCREEN-DELEGATED":
            rows.append((mid, led_ids[mid]["cls"], "WARN",
                         f"screen(s) {', '.join(ds)} claim it but ledger classification={led_ids[mid]['cls']} "
                         f"(not SCREEN-DELEGATED)"))

    n_w = sum(1 for r in rows if r[2] == "WARN")
    lines = [
        f"# mtg-queue — {product}",
        "",
        f"> Generated: {datetime.now().isoformat(timespec='seconds')} · mtg_ledger_scan.py (do not edit)",
        f"> ledger {len(led)} rows · screen pins {sum(len(v) for v in screen_pins.values())} · "
        f"**BLOCK: {block} · FAIL: {fail} · WARN: {n_w}**",
        "",
        "| MTG-ID | Class | Status | Reason |",
        "|---|---|---|---|",
    ]
    if rows:
        for i, cls, st, why in rows:
            lines.append(f"| {i} | {cls} | **{st}** | {why} |")
    else:
        lines.append("| _(no SCREEN-DELEGATED)_ | — | OK | — |")
    lines += [
        "",
        "## Handling criteria (gates/mtg-gate.md)",
        "- BLOCK: SCREEN-DELEGATED open not reflected → blocks Phase progress until the corresponding screen reflects it",
        "- FAIL: screen claims an unregistered MTG → register in the ledger (PM) or correct the pin",
        "- WARN: overdue / incomplete closure / misclassified — non-blocking, PM should verify",
        "- INFO: ledger not authored — PM should author it (not auto-generated, no hallucinated content)",
    ]
    q.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[mtg_ledger_scan] {product}: BLOCK={block} FAIL={fail} WARN={n_w} "
          f"→ {q.relative_to(hub)}")
    print(f"[mtg_ledger_scan] done — {block + fail} blocked"
          + ("" if block + fail == 0 else " (mtg-gate blocked)"))
    return 1 if (block + fail) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Meeting ledger ↔ screen pin cross-check (C-MTG)")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", required=True)
    a = ap.parse_args()
    if not a.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {a.hub_root}\n")
        return 2
    return scan(a.hub_root, a.product)


if __name__ == "__main__":
    sys.exit(main())
