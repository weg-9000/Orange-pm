#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""BDD acceptance-criteria coverage scanner (WP-BDD · contract C-BDD-COV).

Purpose:
    Deterministically verifies that behavior specs (draft matrix / 4-state) are
    fully mapped to executable acceptance criteria (.feature). Automatically
    catches planning-stage behavior holes — missing screen error states,
    ungenerated (stale) .feature files — before Phase advancement.
    Pure script (no model). Does not modify drafts/features (read-only + queue output).

Verdicts (gates/bdd-coverage-gate.md SSoT):
    UNCOVERED : screen 4-state required state (idle/loading/success/error)
                missing (no N/A justification) → BLOCK. A screen draft without a
                4-state table at all counts as 'all missing' → UNCOVERED
                (prevents false green).
    STALE     : draft has behavior spec tables but reports/bdd/{WO}.feature is
                absent, or draft mtime > feature mtime → BLOCK (bdd_assemble
                not run / outdated)
    WARN      : policy matrix non-blank cell ratio low (many undefined cells) — non-blocking advice
    OK        : required states satisfied & feature fresh

Usage:
    python bdd_coverage_scan.py --hub-root <Hub> --product <p>

exit code: 0 no UNCOVERED·STALE / 1 one or more blocks / 2 argument error
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bdd_assemble as A  # noqa: E402  (reuses table extraction / frontmatter parser — SSoT)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

# required-screen-state synonym groups — SSoT is bdd_assemble (keeps verdicts aligned with assemble).
STATE_GROUPS = A.STATE_GROUPS
NA = re.compile(r"N/?A\b|not\s+applicable", re.I)


def screen_missing_states(table) -> list[str]:
    """Missing required state-group names in the 4-state table.

    Only the *state column (col0)* is inspected — states appearing only as
    transition targets ('Next Status') or in condition text are not defined as
    rows, so they don't count as covered (flow rule). A state row present with
    an N/A reason is naturally covered via its col0 match.
    """
    _, data = table
    col0 = " ".join(r[0] for r in data if r)
    missing = [name for name, pat in STATE_GROUPS.items() if not pat.search(col0)]
    # prose-style N/A exemption fallback: an "N/A {group}" marker anywhere in the table exempts.
    if missing:
        whole = " ".join(" ".join(r) for r in data)
        if NA.search(whole):
            missing = [m for m in missing if not re.search(
                STATE_GROUPS[m].pattern + r".{0,12}" + NA.pattern, whole, re.I)
                and not re.search(NA.pattern + r".{0,12}" + STATE_GROUPS[m].pattern, whole, re.I)]
    return missing


def policy_empty_ratio(table) -> tuple[int, int]:
    """Matrix (non-blank cell count, total data cell count)."""
    header, data = table
    n_act = max(len(header) - 1, 0)
    total = filled = 0
    for row in data:
        for cell in row[1:1 + n_act]:
            total += 1
            if not A.EMPTY_CELL.match(cell.strip()):
                filled += 1
    return filled, total


def scan(hub: Path, product: str) -> int:
    proj = hub / "PROJECTS" / product
    drafts = proj / "drafts"
    if not drafts.is_dir():
        sys.stderr.write(f"drafts not found: {drafts}\n")
        return 2
    bdd_dir = proj / "reports" / "bdd"

    rows = []
    uncovered = stale = warn = 0
    for d in sorted(drafts.glob("*.draft.md")):
        wo = d.stem.replace(".draft", "")
        text = d.read_text(encoding="utf-8", errors="replace")
        fm, body = A._parse_frontmatter(text)
        if A.is_wo_stub(body):
            continue  # WO instruction stub — not a behavior-spec deliverable (the real draft is separate)
        kind = (fm.get("type") or "").strip().lower()
        tables = A.extract_tables(body)
        matrix = A.find_matrix_table(tables)
        state_tbl = A.find_state_table(tables)
        # same normalization as assemble_one: explicit policy or (no type + matrix) → policy,
        # everything else (including non-standard types like cluster_draft) maps to screen.
        # (If scan and assemble disagree on kind, STALE/UNCOVERED verdicts go wrong.)
        if kind == "policy" or (not kind and matrix):
            kind = "policy"
        else:
            kind = "screen"
        if kind == "policy" and not matrix:
            continue
        # screen state coverage source: standard single table first; otherwise
        # recognize the '### N-x. {state}' 4-state subsection format
        # (cloud-calculator convention etc.).
        sub_cov: dict | None = None
        if kind == "screen" and not state_tbl:
            # both tables and explicit N/A count as covered ({group: 'table'|'na'}).
            sub_cov = A.state_group_coverage(body)
            if not sub_cov:
                # no 4-state table or subsections = all required 4-states missing (prevents false green).
                feat = bdd_dir / f"{wo}.feature"
                note = ("no 4-state table/subsections — write with /flow" if feat.exists()
                        else "no 4-state table/subsections and no feature — /flow then /bdd")
                uncovered += 1
                rows.append((wo, kind, "no table (all 4-states missing)", "UNCOVERED", note))
                continue

        feat = bdd_dir / f"{wo}.feature"
        if not feat.exists():
            stale += 1
            rows.append((wo, kind, "—", "STALE", "feature not generated — run /bdd"))
            continue
        if d.stat().st_mtime > feat.stat().st_mtime:
            stale += 1
            rows.append((wo, kind, "—", "STALE",
                         "draft changed but feature not refreshed — re-run /bdd"))
            continue

        if kind == "screen":
            if state_tbl:
                miss = screen_missing_states(state_tbl)
                src = "table"
            else:
                miss = [g for g in STATE_GROUPS if g not in sub_cov]
                na = [g for g in STATE_GROUPS if sub_cov.get(g) == "na"]
                src = "subsections" + (f", N/A:{','.join(na)}" if na else "")
            if miss:
                uncovered += 1
                rows.append((wo, kind, f"missing {','.join(miss)}", "UNCOVERED",
                             f"required 4-state missing (no N/A reason) — rewrite flow [{src}]"))
            else:
                rows.append((wo, kind, f"4-state satisfied ({src})", "OK", "all required states covered"))
        else:
            filled, total = policy_empty_ratio(matrix)
            if total and filled / total < 0.5:
                warn += 1
                rows.append((wo, kind, f"defined {filled}/{total} cells", "WARN",
                             "over half of matrix cells undefined — review for behavior gaps"))
            else:
                rows.append((wo, kind, f"defined {filled}/{total} cells", "OK",
                             "key cells defined"))

    qdir = proj / "reports"
    qdir.mkdir(parents=True, exist_ok=True)
    q = qdir / "bdd-coverage-queue.md"
    lines = [
        f"# bdd-coverage-queue — {product}",
        "",
        f"> generated: {datetime.now().isoformat(timespec='seconds')} · bdd_coverage_scan.py (do not edit)",
        f"> **UNCOVERED: {uncovered} · STALE: {stale} · WARN: {warn}**",
        "",
        "| WO | Type | Coverage | Status | Reason |",
        "|---|---|---|---|---|",
    ]
    if rows:
        for wo, kind, cov, st, why in rows:
            lines.append(f"| {wo} | {kind} | {cov} | **{st}** | {why} |")
    else:
        lines.append("| _(no drafts with behavior spec tables)_ | — | — | OK | — |")
    lines += [
        "",
        "## Handling criteria (gates/bdd-coverage-gate.md)",
        "- UNCOVERED: required screen 4-state missing → rewrite with /flow then re-run /bdd",
        "- STALE: feature not generated / outdated → run /bdd",
        "- WARN: over half of policy matrix cells undefined → review behavior gaps (non-blocking)",
    ]
    q.write_text("\n".join(lines) + "\n", encoding="utf-8")
    blocked = uncovered + stale
    print(f"[bdd_coverage_scan] {product}: UNCOVERED={uncovered} STALE={stale} "
          f"WARN={warn} → {q.relative_to(hub)}")
    print(f"[bdd_coverage_scan] done — {blocked} blocking"
          + ("" if blocked == 0 else " (bdd-coverage-gate blocked)"))
    return 1 if blocked else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="BDD acceptance-criteria coverage scan (C-BDD-COV)")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", required=True)
    a = ap.parse_args()
    if not a.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {a.hub_root}\n")
        return 2
    return scan(a.hub_root, a.product)


if __name__ == "__main__":
    sys.exit(main())
