#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Confluence XML structural quality verification script (C-VERIFY).

Purpose:
    Verifies that the output of md_to_storage.py (or leftover XML under
    confluence-source/) complies with our in-house Confluence Storage Format
    quality rules. Quickly detects structural damage right after --push, or
    after manual XML edits (not recommended — Option A policy prohibits direct
    edits).

Division of responsibility (Option A — after MD-only):
    - **MD stage (1st gate)**: lint_publication_syntax.py (L1~L7) verifies
      compliance with the spec (publication-syntax.md §10) before conversion.
      This is where user authoring errors are caught quickly.
    - **XML stage (2nd gate, this script)**: verifies after the fact the
      quality of the converter's (md_to_storage.py) own regressions or of
      manually edited XML. In the normal flow, F1/F2 pass automatically once
      L1~L7 pass and the converter behaves correctly.

Checks (FAIL = blocking / WARN = warning):
    [FAIL] F1 — panel macro color rules
               borderColor=#24FE00 / titleColor=#002FD5 /
               titleBGColor=24FE00 / borderStyle=none
               (MD counterpart: lint L3 — panel style="common")
    [FAIL] F2 — code block: must use ac:plain-text-body + CDATA
               (FAIL if code appears inside ac:rich-text-body)
               (MD counterpart: md_to_storage auto-CDATA-wraps code blocks — this catches regressions)
    [FAIL] F3 — color-span allowed-zone verification (Phase 3E)
               forbidden inside CDATA code blocks / ac:parameter values / nested spans
               (MD counterpart: lint L6 — spec §6.1)
    [WARN] W1 — FR numbering scheme: FR-\d{3}(-\d+)? pattern (§-base 3 digits)
               e.g. FR-101 ✓   FR-101-1 ✓   FR-01 ✗   FR-1 ✗
    [WARN] W2 — required layout section present (at least 1 ac:layout-section)
    [WARN] W3 — leftover empty placeholders ({{...}} pattern)

Output:
    PROJECTS/{product}/reports/verify-report.md  (auto-generated, do not edit)

exit code:
    0 = no FAIL (WARN is non-blocking)
    1 = 1 or more FAIL
    2 = argument error

Usage:
    python render_verify.py --hub-root <Hub> [--product <name>]
    (omit --product to scan all of PROJECTS/*)
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

# ── Pattern definitions ──────────────────────────────────────────────────────

# Extract panel macro parameters
RE_PANEL_MACRO = re.compile(
    r'<ac:structured-macro[^>]*ac:name="panel"[^>]*>(.*?)</ac:structured-macro>',
    re.DOTALL,
)
RE_PARAM = re.compile(r'<ac:parameter ac:name="([^"]+)">([^<]*)</ac:parameter>')

# Code block: FAIL if rich-text-body appears inside the code macro
RE_CODE_MACRO = re.compile(
    r'<ac:structured-macro[^>]*ac:name="code"[^>]*>(.*?)</ac:structured-macro>',
    re.DOTALL,
)
RE_RICH_TEXT_BODY = re.compile(r'<ac:rich-text-body>')

# FR numbering — §-base 3-digit verification
RE_FR_ANY = re.compile(r'\bFR-(\d+)(-\d+)?\b')
RE_FR_VALID = re.compile(r'\bFR-\d{3}(-\d+)?\b')

# Required layout
RE_LAYOUT_SECTION = re.compile(r'<ac:layout-section')

# Leftover placeholders
RE_PLACEHOLDER = re.compile(r'\{\{[^}]+\}\}')

# Recommended panel colors (CLAUDE.md standard)
EXPECTED_PANEL_COLORS = {
    "borderColor": "#24FE00",
    "titleColor": "#002FD5",
    "titleBGColor": "24FE00",
    "borderStyle": "none",
}


def _check_panel_colors(xml: str) -> list[tuple[str, str, str]]:
    """[F1] Verify panel macro color rules. Returns (level, code, message)."""
    issues: list[tuple[str, str, str]] = []
    for i, m in enumerate(RE_PANEL_MACRO.finditer(xml), 1):
        body = m.group(1)
        params = dict(RE_PARAM.findall(body))
        for key, expected in EXPECTED_PANEL_COLORS.items():
            actual = params.get(key, "")
            if actual and actual != expected:
                issues.append((
                    "FAIL", "F1",
                    f"panel #{i}: {key}={actual!r} (expected {expected!r})",
                ))
    return issues


def _check_code_blocks(xml: str) -> list[tuple[str, str, str]]:
    """[F2] rich-text-body is not allowed inside a code macro."""
    issues: list[tuple[str, str, str]] = []
    for i, m in enumerate(RE_CODE_MACRO.finditer(xml), 1):
        body = m.group(1)
        if RE_RICH_TEXT_BODY.search(body):
            issues.append((
                "FAIL", "F2",
                f"code block #{i}: uses ac:rich-text-body — must be replaced with ac:plain-text-body + CDATA",
            ))
    return issues


# Phase 3E — F3: verify color-span allowed zones.
# Forbidden inside CDATA code blocks, macro parameter values (ac:parameter), or as nested spans.
RE_CDATA_BLOCK = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)
RE_COLOR_SPAN = re.compile(
    r'<span\s+style\s*=\s*"color:\s*rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)\s*"\s*>(.*?)</span>',
    re.DOTALL | re.IGNORECASE,
)
RE_PARAM_TAG = re.compile(
    r"<ac:parameter[^>]*>(.*?)</ac:parameter>", re.DOTALL
)


def _check_color_spans(xml: str) -> list[tuple[str, str, str]]:
    """[F3] Verify that color spans only appear in allowed zones.

    Forbidden zones:
      - inside a CDATA code block (the XML parser doesn't interpret it → meaningless markup)
      - inside an ac:parameter value (a color span inside a macro parameter breaks it)
      - nested spans (`<span><span>...</span></span>`)
    """
    issues: list[tuple[str, str, str]] = []

    # Check for spans inside CDATA
    for i, m in enumerate(RE_CDATA_BLOCK.finditer(xml), 1):
        body = m.group(1)
        if RE_COLOR_SPAN.search(body):
            issues.append((
                "FAIL", "F3",
                f"color span found inside CDATA #{i} — color markup is not allowed inside code blocks",
            ))

    # Check for spans inside ac:parameter values
    for i, m in enumerate(RE_PARAM_TAG.finditer(xml), 1):
        body = m.group(1)
        if RE_COLOR_SPAN.search(body):
            issues.append((
                "FAIL", "F3",
                f"color span found inside ac:parameter #{i} — spans are not allowed in macro parameters",
            ))

    # Nested span: check whether a span's inner content contains another span
    for i, m in enumerate(RE_COLOR_SPAN.finditer(xml), 1):
        inner = m.group(1)
        if RE_COLOR_SPAN.search(inner):
            issues.append((
                "FAIL", "F3",
                f"color span #{i}: nested span — nesting is forbidden by spec §6.1",
            ))

    return issues


def _check_fr_numbering(xml: str) -> list[tuple[str, str, str]]:
    """[W1] Verify the FR numbering §-base 3-digit format."""
    issues: list[tuple[str, str, str]] = []
    bad: list[str] = []
    for m in RE_FR_ANY.finditer(xml):
        full = m.group(0)
        if not RE_FR_VALID.match(full):
            bad.append(full)
    bad = list(dict.fromkeys(bad))  # de-duplicate
    if bad:
        sample = ", ".join(bad[:5]) + ("..." if len(bad) > 5 else "")
        issues.append((
            "WARN", "W1",
            f"{len(bad)} FR numbering mismatches (e.g. {sample}) — expected: FR-NNN or FR-NNN-N",
        ))
    return issues


def _check_layout(xml: str) -> list[tuple[str, str, str]]:
    """[W2] At least one ac:layout-section must be present."""
    if not RE_LAYOUT_SECTION.search(xml):
        return [("WARN", "W2", "no ac:layout-section found — check the Confluence Storage Format layout structure")]
    return []


def _check_placeholders(xml: str) -> list[tuple[str, str, str]]:
    """[W3] Leftover {{...}} placeholders."""
    found = list(dict.fromkeys(RE_PLACEHOLDER.findall(xml)))
    if found:
        sample = ", ".join(found[:5]) + ("..." if len(found) > 5 else "")
        return [("WARN", "W3", f"{len(found)} leftover placeholder(s) ({sample}) — substitution required")]
    return []


def verify_file(xml_path: Path) -> list[tuple[str, str, str]]:
    xml = xml_path.read_text(encoding="utf-8", errors="replace")
    issues: list[tuple[str, str, str]] = []
    issues += _check_panel_colors(xml)
    issues += _check_code_blocks(xml)
    issues += _check_color_spans(xml)
    issues += _check_fr_numbering(xml)
    issues += _check_layout(xml)
    issues += _check_placeholders(xml)
    return issues


def scan(hub_root: Path, product: str | None = None) -> int:
    projects_root = hub_root / "PROJECTS"
    if not projects_root.is_dir():
        print(f"[verify] PROJECTS not found: {projects_root} — nothing to scan")
        return 0

    products = (
        [projects_root / product]
        if product
        else sorted(p for p in projects_root.iterdir() if p.is_dir())
    )

    total_fail = 0

    for proj in products:
        pname = proj.name
        src_dir = proj / "confluence-source"
        xml_files = sorted(src_dir.glob("*.xml")) if src_dir.is_dir() else []

        if not xml_files:
            print(f"[verify] {pname}: no XML — skipping")
            continue

        file_results: list[tuple[Path, list]] = []
        for xf in xml_files:
            issues = verify_file(xf)
            file_results.append((xf, issues))

        n_fail = sum(1 for _, iss in file_results for (lv, _, _) in iss if lv == "FAIL")
        n_warn = sum(1 for _, iss in file_results for (lv, _, _) in iss if lv == "WARN")
        total_fail += n_fail

        reports = proj / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        out = reports / "verify-report.md"

        lines = [
            f"# verify-report — {pname}",
            "",
            f"> Generated: {datetime.now().isoformat(timespec='seconds')}"
            f" · auto-generated by render_verify.py (do not edit)",
            f"> **FAIL: {n_fail} · WARN: {n_warn}**",
            "",
        ]

        for xf, issues in file_results:
            rel = xf.relative_to(proj)
            lines += [f"## {rel}", ""]
            if not issues:
                lines += ["> ✅ All checks passed", ""]
                continue
            lines += [
                "| Level | Code | Message |",
                "|---|---|---|",
            ]
            for lv, code, msg in issues:
                emoji = "🔴" if lv == "FAIL" else "🟡"
                lines.append(f"| {emoji} **{lv}** | {code} | {msg} |")
            lines.append("")

        lines += [
            "---",
            "",
            "## Verification criteria",
            "| Code | Level | Rule |",
            "|---|---|---|",
            "| F1 | FAIL | Panel macro: borderColor=#24FE00 / titleColor=#002FD5 / titleBGColor=24FE00 / borderStyle=none |",
            "| F2 | FAIL | Code block: ac:plain-text-body + CDATA (ac:rich-text-body forbidden) |",
            "| F3 | FAIL | Color span: forbidden inside CDATA/ac:parameter/nested (Phase 3E) |",
            "| W1 | WARN | FR numbering: FR-NNN or FR-NNN-N format (§-base 3 digits) |",
            "| W2 | WARN | At least 1 ac:layout-section |",
            "| W3 | WARN | No leftover {{...}} placeholders |",
        ]
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[verify] {pname}: FAIL={n_fail} WARN={n_warn} → {out.relative_to(hub_root)}")

    print(f"[verify] done — total FAIL {total_fail}"
          + ("" if total_fail == 0 else " (gate blocked)"))
    return 1 if total_fail else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Confluence XML structural quality verification")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", default=None, help="PROJECTS/<product> (omit = all)")
    ap.add_argument("--file", default=None, type=Path,
                    help="Directly specify a single XML file (works without --hub-root)")
    args = ap.parse_args()

    if args.file:
        if not args.file.is_file():
            sys.stderr.write(f"file not found: {args.file}\n")
            return 2
        issues = verify_file(args.file)
        n_fail = sum(1 for lv, _, _ in issues if lv == "FAIL")
        for lv, code, msg in issues:
            print(f"[{lv}] {code}: {msg}")
        if not issues:
            print("✅ All checks passed")
        return 1 if n_fail else 0

    if not args.hub_root or not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    return scan(args.hub_root, args.product)


if __name__ == "__main__":
    sys.exit(main())
