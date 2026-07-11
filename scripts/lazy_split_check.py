#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lazy-Split Trigger Check (Phase 5D).

Checks whether a cluster draft exceeds the split thresholds and prints
recommendations. The actual split happens via a fanout re-run or manual
handling after PM approval.

Thresholds (per publication-syntax.md / cluster-draft.md spec):
    - body > 1500 lines
    - §1+§2 item count > 8
    - cumulative R2 BLOCK count (HARD+SOFT) > 5  (from the integrate report)
    - PM-specified --force-split

Child cluster ID pattern (spec):
    {parent_cluster_id}-{suffix}   e.g. PV-01 → PV-01-a, PV-01-b

CLI:
    python lazy_split_check.py --drafts drafts/cluster_*.draft.md
        [--integrate-report reports/integrate/{product}.block.md]
        [--threshold-lines 1500] [--threshold-items 8] [--threshold-blocks 5]
        [--report reports/lazy-split-report.md]

exit code: 0 (no split recommended) / 1 (1+ recommended) / 2 (input error)
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_THRESHOLD_LINES = 1500
DEFAULT_THRESHOLD_ITEMS = 8
DEFAULT_THRESHOLD_BLOCKS = 5


@dataclass
class SplitCheck:
    """Split-check result for a single cluster."""

    cluster_path: Path
    cluster_id: str = ""
    body_lines: int = 0
    section1_items: int = 0  # table/list item count in the §1 policy decisions
    section2_items: int = 0  # table/list item count in the §2 screen design
    integrate_blocks: int = 0  # cumulative R2 BLOCK count
    triggers: list[str] = field(default_factory=list)  # list of exceeded thresholds

    @property
    def should_split(self) -> bool:
        return bool(self.triggers)


def _extract_cluster_id(text: str) -> str:
    m = re.search(r'cluster_id:\s*"?([^"\n]+)"?', text)
    return m.group(1).strip() if m else ""


def _count_panel_items(body: str, section_keyword: str) -> int:
    """Count table rows + list items inside the given panel section."""
    pattern = re.compile(
        r'::: \{\.panel section="[^"]*' + re.escape(section_keyword) + r'[^"]*"[^}]*\}(.*?):::',
        re.DOTALL,
    )
    m = pattern.search(body)
    if not m:
        return 0
    panel_body = m.group(1)
    # table body row count (excludes header/separator)
    table_rows = 0
    in_table = False
    for line in panel_body.splitlines():
        stripped = line.strip()
        if re.match(r"^\|[\s\-:|]+\|$", stripped):
            in_table = True
            continue
        if stripped.startswith("|") and in_table:
            # exclude rows that are only a placeholder ({{...}}) — template intent
            if re.fullmatch(r"\|\s*\{\{[^}]+\}\}\s*(\|\s*[^|]*)*\|", stripped):
                continue
            table_rows += 1
        else:
            in_table = False
    # list items
    list_items = sum(
        1 for ln in panel_body.splitlines() if re.match(r"\s*[-*+]\s+\S", ln)
    )
    return table_rows + list_items


def _count_blocks_for_cluster(
    integrate_report: Path | None, cluster_id: str
) -> int:
    """Count BLOCK occurrences for the given cluster_id in the integrate report."""
    if not integrate_report or not integrate_report.is_file():
        return 0
    text = integrate_report.read_text(encoding="utf-8", errors="replace")
    # lines where cluster_id appears, with HARD/SOFT on the same line / adjacent block
    cluster_lines = [
        ln for ln in text.splitlines() if cluster_id in ln
    ]
    count = 0
    for ln in cluster_lines:
        if re.search(r"\b(HARD|SOFT)_?BLOCK\b", ln, re.IGNORECASE):
            count += 1
    return count


def check_cluster_draft(
    path: Path,
    *,
    integrate_report: Path | None = None,
    threshold_lines: int = DEFAULT_THRESHOLD_LINES,
    threshold_items: int = DEFAULT_THRESHOLD_ITEMS,
    threshold_blocks: int = DEFAULT_THRESHOLD_BLOCKS,
) -> SplitCheck:
    text = path.read_text(encoding="utf-8", errors="replace")
    cluster_id = _extract_cluster_id(text)

    # body (frontmatter excluded)
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end >= 0:
            body = text[end + 5 :]

    check = SplitCheck(
        cluster_path=path,
        cluster_id=cluster_id,
        body_lines=len([ln for ln in body.splitlines() if ln.strip()]),
        section1_items=_count_panel_items(body, "Policy"),
        section2_items=_count_panel_items(body, "Screen"),
        integrate_blocks=_count_blocks_for_cluster(integrate_report, cluster_id),
    )

    if check.body_lines > threshold_lines:
        check.triggers.append(
            f"body line count {check.body_lines} > {threshold_lines}"
        )
    items_total = check.section1_items + check.section2_items
    if items_total > threshold_items:
        check.triggers.append(
            f"§1+§2 item count {items_total} > {threshold_items}"
        )
    if check.integrate_blocks > threshold_blocks:
        check.triggers.append(
            f"cumulative R2 BLOCK count {check.integrate_blocks} > {threshold_blocks}"
        )

    return check


def format_report(
    checks: list[SplitCheck],
    *,
    threshold_lines: int,
    threshold_items: int,
    threshold_blocks: int,
) -> str:
    lines = ["# Lazy-Split Recommendations (Phase 5D)\n"]
    lines.append("**Thresholds** (per publication-syntax.md / cluster-draft.md spec):")
    lines.append(f"- body lines > {threshold_lines}")
    lines.append(f"- §1+§2 item count > {threshold_items}")
    lines.append(f"- cumulative R2 BLOCK count > {threshold_blocks}\n")

    splittable = [c for c in checks if c.should_split]
    lines.append(f"**{len(checks)} clusters checked, {len(splittable)} cluster(s) recommended for split**\n")

    if not splittable:
        lines.append("All clusters are within thresholds — no split recommended.\n")
        return "\n".join(lines) + "\n"

    lines.append("| Cluster ID | Body Lines | §1 Items | §2 Items | BLOCK | Triggers |")
    lines.append("|---|---|---|---|---|---|")
    for c in splittable:
        triggers = "<br>".join(c.triggers) or "_(within thresholds)_"
        lines.append(
            f"| `{c.cluster_id}` | {c.body_lines} | "
            f"{c.section1_items} | {c.section2_items} | "
            f"{c.integrate_blocks} | {triggers} |"
        )

    lines.append("\n## Recommended follow-up\n")
    lines.append("For each cluster recommended for split, after PM confirmation:")
    lines.append("1. Assign child cluster IDs: `{parent_cluster_id}-a`, `-b`, ...")
    lines.append("2. Redistribute the original cluster draft's member nodes among the children")
    lines.append("3. Register the child IDs in `cluster_identify.py`'s `cluster_map.json`")
    lines.append("4. Re-run `fanout --cluster-mode` → generates the child cluster drafts")
    lines.append("5. (Optional) `--force-split` can be used to force a split below threshold\n")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lazy_split_check",
        description="Cluster draft split-threshold check (Phase 5D)",
    )
    parser.add_argument(
        "--drafts", nargs="+", type=Path, required=True,
        help="cluster draft files (drafts/cluster_*.draft.md)",
    )
    parser.add_argument(
        "--integrate-report", type=Path, default=None,
        help="integrate R2 BLOCK report (optional)",
    )
    parser.add_argument("--threshold-lines", type=int, default=DEFAULT_THRESHOLD_LINES)
    parser.add_argument("--threshold-items", type=int, default=DEFAULT_THRESHOLD_ITEMS)
    parser.add_argument("--threshold-blocks", type=int, default=DEFAULT_THRESHOLD_BLOCKS)
    parser.add_argument(
        "--report", type=Path, default=None,
        help="report markdown output path",
    )
    args = parser.parse_args(argv)

    missing = [p for p in args.drafts if not p.is_file()]
    if missing:
        print(f"[lazy_split_check] ERROR: file(s) not found: {missing}", file=sys.stderr)
        return 2

    checks = [
        check_cluster_draft(
            p,
            integrate_report=args.integrate_report,
            threshold_lines=args.threshold_lines,
            threshold_items=args.threshold_items,
            threshold_blocks=args.threshold_blocks,
        )
        for p in args.drafts
    ]

    report = format_report(
        checks,
        threshold_lines=args.threshold_lines,
        threshold_items=args.threshold_items,
        threshold_blocks=args.threshold_blocks,
    )

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")
    else:
        print(report)

    splittable = [c for c in checks if c.should_split]
    print(
        f"[lazy_split_check] {len(checks)} clusters checked, "
        f"{len(splittable)} recommended for split",
        file=sys.stderr,
    )
    return 1 if splittable else 0


if __name__ == "__main__":
    raise SystemExit(main())
