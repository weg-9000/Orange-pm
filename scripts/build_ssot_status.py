#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""SSoT unified status dashboard builder (Sprint S2-2).

Warning: SUPERSEDED / STANDALONE — not wired to any skill or hook.
    The live SSoT-status adapter is ssot_emit.py (via /next -> next_emit.py),
    and ssot_emit.py is the authority for queue scope (5 queues + viz JSON).
    This script writes reports/ssot-status.md, but nothing consumes it, and it
    only covers 3 queues (drift/policy-impact/mtg), so its scope differs from
    ssot_emit.py. Kept only as a manual/standalone diagnostic tool. Runtime
    logic is not changed.

Purpose:
    Parse the header line of each queue file (reports/drift-queue.md,
    policy-impact-queue.md, mtg-queue.md) produced by the three scanners
    drift_scan / policy_impact_scan / mtg_ledger_scan, and generate a single
    unified status page at PROJECTS/{product}/reports/ssot-status.md.

    A pure aggregator. Does not modify the queue sources, scanners, or gate
    definitions. Only the BLOCK count feeds into the phase-advance decision;
    the WARN total is display-only.

Queue header format (each scanner's own SSoT):
    drift          : **BLOCK: N · WARN/UNRESOLVED: M · unreferenced-by-common draft: K**
    policy-impact  : changed section: X · **IMPACT: N · WARN/COARSE: M**
    mtg-ledger     : **BLOCK: N · FAIL: N · WARN: N**

    IMPACT (policy-impact) and FAIL (mtg) are counted as BLOCK-equivalent (gate-blocking).

Usage:
    python build_ssot_status.py --hub-root <Hub> --product <name>
    python build_ssot_status.py --hub-root <Hub> --product <name> --check
        # --check: doesn't write the file, exit code only (for CI)

exit code:
    0 = every queue's BLOCK-equivalent count = 0 (phase advance allowed)
    1 = BLOCK-equivalent >= 1 (blocked)
    2 = argument error
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

# Avoid Windows console cp949 issues.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


# Header parser: keyword -> number. Accepts both `·` and `•`. Absorbs label variants.
# drift:         BLOCK / WARN/UNRESOLVED
# policy-impact: IMPACT / WARN/COARSE
# mtg:           BLOCK / FAIL / WARN
# Matches the label anywhere in the header line (regardless of a leading `**`).
# Word boundary is restricted to non-alphabetic/slash to avoid false positives on body text.
HEADER_NUM = re.compile(
    r"(?<![A-Za-z/])([A-Z]+(?:/[A-Z]+)?)\s*:\s*(\d+)",
)


def _parse_header(text: str) -> dict | None:
    """Find the header line in a queue file body and return a label->int map. None on failure.

    The header is typically inside a blockquote in the form
    `> **BLOCK: ... · WARN: ...**`. Only searched within the first 30 lines
    of the body (a well-formed queue file has it within the first 5 lines).
    """
    block_line = None
    for raw in text.splitlines()[:30]:
        if "**" in raw and re.search(r"\*\*[A-Z]+:", raw):
            block_line = raw
            break
    if not block_line:
        return None
    out: dict[str, int] = {}
    for m in HEADER_NUM.finditer(block_line):
        label = m.group(1).upper()
        try:
            out[label] = int(m.group(2))
        except ValueError:
            continue
    if not out:
        return None
    return out


def _file_mtime_date(path: Path) -> str:
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except OSError:
        return "-"


def _summarize_queue(
    path: Path,
    block_labels: tuple[str, ...],
    warn_labels: tuple[str, ...],
) -> dict:
    """Read a single queue file and return its BLOCK/WARN-equivalent counts and a status string.

    If any of block_labels is present in the header, its sum counts as
    BLOCK-equivalent. File missing -> status='not scanned yet', header parse
    failure -> 'parse failed'.
    """
    if not path.exists():
        return {
            "block": None,
            "warn": None,
            "updated": "-",
            "status": "not scanned yet",
            "ok": True,  # not-yet-scanned isn't a block, just informational
        }
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {
            "block": None,
            "warn": None,
            "updated": "-",
            "status": f"read failed: {e}",
            "ok": False,
        }
    parsed = _parse_header(text)
    if parsed is None:
        return {
            "block": None,
            "warn": None,
            "updated": _file_mtime_date(path),
            "status": "parse failed",
            "ok": False,
        }
    block_total = sum(parsed.get(lbl, 0) for lbl in block_labels)
    warn_total = sum(parsed.get(lbl, 0) for lbl in warn_labels)
    ok = block_total == 0
    return {
        "block": block_total,
        "warn": warn_total,
        "updated": _file_mtime_date(path),
        "status": "PASS" if ok else "BLOCK",
        "ok": ok,
    }


# Queue definitions: (title, filename, BLOCK-equivalent labels, WARN-equivalent labels, queue description)
QUEUES = [
    (
        "drift (master pin)",
        "drift-queue.md",
        ("BLOCK",),
        ("WARN/UNRESOLVED",),
        "click through to check per-section when BLOCK is N",
    ),
    (
        "policy-impact (§ → screen)",
        "policy-impact-queue.md",
        ("IMPACT",),
        ("WARN/COARSE",),
        "check §-level detail when IMPACT is N",
    ),
    (
        "mtg-ledger (meeting decision pins)",
        "mtg-queue.md",
        ("BLOCK", "FAIL"),
        ("WARN",),
        "check when N delegated decisions are unreflected",
    ),
]


def _cell(n) -> str:
    return "-" if n is None else str(n)


def _status_cell(s: dict) -> str:
    if s["status"] == "not scanned yet":
        return "not scanned yet"
    if s["status"] == "parse failed":
        return "parse failed"
    if s.get("ok"):
        return "✅ PASS"
    return "🚨 BLOCK"


def build(hub_root: Path, product: str, check_only: bool) -> int:
    reports = hub_root / "PROJECTS" / product / "reports"
    summaries: list[dict] = []
    total_block = 0
    total_warn = 0
    for title, fname, b_labels, w_labels, _hint in QUEUES:
        s = _summarize_queue(reports / fname, b_labels, w_labels)
        s["title"] = title
        s["file"] = fname
        summaries.append(s)
        if s["block"]:
            total_block += s["block"]
        if s["warn"]:
            total_warn += s["warn"]

    overall_pass = total_block == 0

    if check_only:
        print(
            f"[build_ssot_status] {product}: BLOCK total={total_block} "
            f"WARN total={total_warn} "
            + ("-> PASS" if overall_pass else "-> BLOCKED")
        )
        return 0 if overall_pass else 1

    if not reports.exists():
        reports.mkdir(parents=True, exist_ok=True)

    now_iso = datetime.now().isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append(f"# SSoT Status — {product}")
    lines.append("")
    lines.append(f"Generated: {now_iso}")
    lines.append("")
    lines.append("## Overall Summary")
    lines.append("")
    lines.append("| Queue | BLOCK | WARN | Last Updated | Status |")
    lines.append("|---|---:|---:|---|---|")
    for s in summaries:
        lines.append(
            f"| {s['title']} | {_cell(s['block'])} | {_cell(s['warn'])} "
            f"| {s['updated']} | {_status_cell(s)} |"
        )
    lines.append(
        f"| **Total** | **{total_block}** | **{total_warn}** | — | — |"
    )
    lines.append("")
    lines.append("## Pass Condition")
    lines.append("Phase advance is allowed when every queue's BLOCK = 0.")
    lines.append("")
    lines.append("## Queue Details")
    for (title, fname, _b, _w, hint), s in zip(QUEUES, summaries):
        n = s["block"] if s["block"] is not None else "-"
        lines.append(f"- [[{fname}]] — {hint.replace('N', str(n))}")
    lines.append("")
    lines.append("## Workflow Connections")
    lines.append(
        "- Trigger: drift_scan / policy_impact_scan / mtg_ledger_scan PostToolUse"
    )
    lines.append(
        "- Gates: [[drift-gate]], [[policy-impact-gate]], [[mtg-gate]]"
    )

    out_path = reports / "ssot-status.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"[build_ssot_status] {product}: BLOCK total={total_block} "
        f"WARN total={total_warn} -> {out_path.relative_to(hub_root)} "
        + ("(PASS)" if overall_pass else "(BLOCKED)")
    )
    return 0 if overall_pass else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="SSoT unified status dashboard builder (aggregates drift+policy-impact+mtg queue headers)"
    )
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument(
        "--product",
        required=True,
        help="target product name under PROJECTS/<product>",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="don't write the file, return only the exit code (for CI)",
    )
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    return build(args.hub_root, args.product, args.check)


if __name__ == "__main__":
    sys.exit(main())
