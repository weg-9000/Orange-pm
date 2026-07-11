#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Publication Syntax Lint — MD publication syntax validation (publication-lint).

Purpose:
    Validates that the publication syntax (publication-syntax.md spec) for the
    Option A (MD-only) foundation is correctly applied in the canonical
    Markdown. Provides fast feedback before invoking md_to_storage.py.

Checks (FAIL = blocking / WARN = warning):
    [FAIL] L1 — fenced div class is in the allowed list
                (panel | info | warning | note | tip | expand)
    [FAIL] L2 — panel block (.panel) requires a section="..." attribute
    [FAIL] L3 — panel style value is in the allowed mapping
                (common | product | tbd | warning | info)
    [WARN] L4 — code block language fence is a known language
                (python | bash | json | yaml | sql | javascript |
                 typescript | markdown | xml | html | css | text, etc.)
    [WARN] L5 — unresolved auto-macro {{...}} placeholder
                (DATE/PRODUCT_NAME/DOC_ID/VERSION/toc/change_history are allowed)
    [FAIL] L6 — nested color spans forbidden (reserved for Phase 3, rule active in advance)
    [FAIL] L7 — table column count consistency (header row matches body rows)

Output:
    Standard output (render_verify.py report format)
    If --report <path> is given, the same content is also saved as an md file

Exit code:
    0 = no FAIL (WARN is non-blocking)
    1 = 1+ FAIL
    2 = I/O error

Usage:
    python lint_publication_syntax.py --input X.md [--report report.md]
    python lint_publication_syntax.py --hub-root <Hub> [--product <name>]
        (if --product is omitted, checks all of PROJECTS/*)

Spec SSoT:
    orange-pm-plugin/skills/render/publication-syntax.md §10 validation gate
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

# ── Rule metadata ──────────────────────────────────────────────────────────

RULES: dict[str, dict[str, str]] = {
    "L1": {"level": "FAIL", "desc": "fenced div class in allowed list"},
    "L2": {"level": "FAIL", "desc": "panel section attribute missing"},
    "L3": {"level": "FAIL", "desc": "panel style value in allowed mapping"},
    "L4": {"level": "WARN", "desc": "unknown code language"},
    "L5": {"level": "WARN", "desc": "unresolved placeholder"},
    "L6": {"level": "FAIL", "desc": "nested color span"},
    "L7": {"level": "FAIL", "desc": "table column count mismatch"},
}

ALLOWED_DIV_CLASSES = {"panel", "info", "warning", "note", "tip", "expand"}
ALLOWED_PANEL_STYLES = {"common", "product", "tbd", "warning", "info"}
ALLOWED_CODE_LANGS = {
    "python", "py",
    "bash", "sh", "shell", "zsh",
    "json", "yaml", "yml", "toml", "ini",
    "sql",
    "javascript", "js",
    "typescript", "ts",
    "markdown", "md",
    "xml", "html", "css",
    "text", "txt", "plain", "plaintext",
    "mermaid", "plantuml",
    "diff", "patch",
    "java", "kotlin", "go", "rust", "c", "cpp", "csharp",
    "ruby", "php", "perl",
    "dockerfile", "makefile",
}
ALLOWED_PLACEHOLDERS = {
    # macro placeholders substituted at publish time
    "DATE", "PRODUCT_NAME", "DOC_ID", "VERSION", "WO_ID",
    "LAST_UPDATED", "AUTHOR", "TYPE", "LAYER",
    # auto-macro imperative placeholder
    "toc",
}
# macro prefix taking an argument, e.g. {{change_history 3}}
ALLOWED_PLACEHOLDER_PREFIXES = ("change_history",)


# ── Pattern definitions ────────────────────────────────────────────────────

# Fenced div open: ::: {.class attr="..." ...}
# Closing div is a standalone ::: line
RE_DIV_OPEN = re.compile(r'^:::\s*\{([^}]*)\}\s*$')
RE_DIV_CLOSE = re.compile(r'^:::\s*$')
# attribute parsing: .class or key="value"
RE_DIV_CLASS = re.compile(r'\.([A-Za-z_][\w-]*)')
RE_DIV_ATTR = re.compile(r'([A-Za-z_][\w-]*)\s*=\s*"([^"]*)"')

# code fence: ``` or ~~~ + (optional) language
RE_CODE_FENCE = re.compile(r'^(\s*)(`{3,}|~{3,})\s*([^\s`{]*)')

# Placeholder {{...}}
RE_PLACEHOLDER = re.compile(r'\{\{\s*([A-Za-z_][\w]*)(?:\s+[^}]*)?\s*\}\}')

# Color span — Pandoc bracketed_spans: [text]{.class}
# nested detection: [text [inner]{.color-X} more]{.color-Y}
# checks whether another color span exists inside a color span
RE_COLOR_SPAN = re.compile(
    r'\[([^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*)\]\{\.color-[A-Za-z0-9_-]+\}'
)
RE_INNER_COLOR_SPAN = re.compile(r'\[[^\[\]]+\]\{\.color-[A-Za-z0-9_-]+\}')

# table line: cell separator | appears 2+ times (e.g. | a | b |)
# a separator row (|---|---|) must follow the header to count as a table
RE_TABLE_SEP = re.compile(r'^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$')


# ── Data structures ────────────────────────────────────────────────────────

@dataclass
class Finding:
    path: Path
    line: int
    rule: str  # L1 ~ L7
    level: str  # FAIL | WARN
    message: str
    snippet: str = ""


# ── Helper: mask code block regions ────────────────────────────────────────

def _scan_code_fence_regions(lines: list[str]) -> list[tuple[int, int, str]]:
    """Return regions [start_idx, end_idx] enclosed by code fences, with language fence.

    start_idx / end_idx are 0-based and both inclusive (fence lines themselves included).
    """
    regions: list[tuple[int, int, str]] = []
    i = 0
    n = len(lines)
    while i < n:
        m = RE_CODE_FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        fence = m.group(2)
        lang = m.group(3) or ""
        start = i
        i += 1
        # until a fence of the same kind and length or longer is found
        while i < n:
            m2 = re.match(rf'^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$', lines[i])
            if m2:
                break
            i += 1
        end = i if i < n else n - 1
        regions.append((start, end, lang))
        i += 1
    return regions


def _line_in_regions(idx: int, regions: list[tuple[int, int, str]]) -> bool:
    for s, e, _ in regions:
        if s <= idx <= e:
            return True
    return False


# ── Rule functions ─────────────────────────────────────────────────────────

def check_l1_l2_l3(text: str, path: Path) -> list[Finding]:
    """[L1] fenced div class allowed list / [L2] panel section required /
    [L3] panel style allowed mapping."""
    findings: list[Finding] = []
    lines = text.splitlines()
    code_regions = _scan_code_fence_regions(lines)

    for idx, raw in enumerate(lines):
        if _line_in_regions(idx, code_regions):
            continue
        m = RE_DIV_OPEN.match(raw)
        if not m:
            continue
        inner = m.group(1)
        classes = RE_DIV_CLASS.findall(inner)
        attrs = dict(RE_DIV_ATTR.findall(inner))
        ln = idx + 1

        # L1: validate allowed class
        if not classes:
            findings.append(Finding(
                path=path, line=ln, rule="L1", level="FAIL",
                message="fenced div has no class (must use `::: {.panel ...}` format)",
                snippet=raw.strip(),
            ))
            continue
        first_cls = classes[0]
        if first_cls not in ALLOWED_DIV_CLASSES:
            findings.append(Finding(
                path=path, line=ln, rule="L1", level="FAIL",
                message=f"disallowed fenced div class: .{first_cls} "
                        f"(allowed: {sorted(ALLOWED_DIV_CLASSES)})",
                snippet=raw.strip(),
            ))
            continue

        # L2: panel requires section
        if first_cls == "panel" and "section" not in attrs:
            findings.append(Finding(
                path=path, line=ln, rule="L2", level="FAIL",
                message="panel block missing section=\"...\" attribute",
                snippet=raw.strip(),
            ))

        # L3: panel style allowed mapping
        if first_cls == "panel" and "style" in attrs:
            sty = attrs["style"]
            if sty not in ALLOWED_PANEL_STYLES:
                findings.append(Finding(
                    path=path, line=ln, rule="L3", level="FAIL",
                    message=f"disallowed panel style value: {sty!r} "
                            f"(allowed: {sorted(ALLOWED_PANEL_STYLES)})",
                    snippet=raw.strip(),
                ))

    return findings


def check_l4(text: str, path: Path) -> list[Finding]:
    """[L4] code block language fence is a known language (when specified)."""
    findings: list[Finding] = []
    lines = text.splitlines()
    regions = _scan_code_fence_regions(lines)
    for start, _end, lang in regions:
        if not lang:
            continue
        if lang.lower() not in ALLOWED_CODE_LANGS:
            findings.append(Finding(
                path=path, line=start + 1, rule="L4", level="WARN",
                message=f"unknown code language fence: {lang!r} "
                        f"(not in allowed list — confirm this is intentional)",
                snippet=lines[start].strip(),
            ))
    return findings


def check_l5(text: str, path: Path) -> list[Finding]:
    """[L5] unresolved auto-macro `{{...}}` placeholder."""
    findings: list[Finding] = []
    lines = text.splitlines()
    regions = _scan_code_fence_regions(lines)
    for idx, raw in enumerate(lines):
        if _line_in_regions(idx, regions):
            continue
        for m in RE_PLACEHOLDER.finditer(raw):
            name = m.group(1)
            if name in ALLOWED_PLACEHOLDERS:
                continue
            if any(name.startswith(p) for p in ALLOWED_PLACEHOLDER_PREFIXES):
                continue
            findings.append(Finding(
                path=path, line=idx + 1, rule="L5", level="WARN",
                message=f"unresolved placeholder: {{{{{name}}}}} "
                        f"(not in allowed list — substitution may be missing)",
                snippet=raw.strip(),
            ))
    return findings


def check_l6(text: str, path: Path) -> list[Finding]:
    """[L6] nested color spans forbidden (reserved for Phase 3)."""
    findings: list[Finding] = []
    lines = text.splitlines()
    regions = _scan_code_fence_regions(lines)
    for idx, raw in enumerate(lines):
        if _line_in_regions(idx, regions):
            continue
        for m in RE_COLOR_SPAN.finditer(raw):
            inner_text = m.group(1)
            if RE_INNER_COLOR_SPAN.search(inner_text):
                findings.append(Finding(
                    path=path, line=idx + 1, rule="L6", level="FAIL",
                    message="nested color span found — nesting forbidden (Phase 3 spec)",
                    snippet=raw.strip(),
                ))
                break
    return findings


def check_l7(text: str, path: Path) -> list[Finding]:
    """[L7] table column count consistency."""
    findings: list[Finding] = []
    lines = text.splitlines()
    regions = _scan_code_fence_regions(lines)
    n = len(lines)
    i = 0
    while i < n - 1:
        if _line_in_regions(i, regions):
            i += 1
            continue
        header = lines[i]
        sep = lines[i + 1]
        if "|" not in header or not RE_TABLE_SEP.match(sep):
            i += 1
            continue
        header_cols = _count_table_cols(header)
        if header_cols < 1:
            i += 1
            continue
        sep_cols = _count_table_cols(sep)
        if sep_cols != header_cols:
            findings.append(Finding(
                path=path, line=i + 2, rule="L7", level="FAIL",
                message=f"table separator row column count mismatch — "
                        f"header: {header_cols}, separator: {sep_cols}",
                snippet=sep.strip(),
            ))
        # check body rows
        j = i + 2
        row_num = 0
        while j < n:
            if _line_in_regions(j, regions):
                break
            row = lines[j]
            if "|" not in row or not row.strip():
                break
            row_num += 1
            row_cols = _count_table_cols(row)
            if row_cols != header_cols:
                findings.append(Finding(
                    path=path, line=j + 1, rule="L7", level="FAIL",
                    message=f"table column count mismatch — header: {header_cols} cols, "
                            f"body row {row_num}: {row_cols} cols",
                    snippet=row.strip(),
                ))
            j += 1
        i = max(j, i + 1)
    return findings


def _count_table_cols(line: str) -> int:
    """Count cells based on pipes. Ignores leading/trailing pipes."""
    s = line.strip()
    if not s:
        return 0
    # strip leading/trailing |
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    if not s:
        return 0
    # escape handling omitted (simple split is sufficient at lint level)
    return s.count("|") + 1


# ── File/product level ──────────────────────────────────────────────────────

def lint_file(path: Path) -> list[Finding]:
    """Check a single MD file (runs all rules)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise OSError(f"read failed: {path} — {e}") from e

    findings: list[Finding] = []
    findings += check_l1_l2_l3(text, path)
    findings += check_l4(text, path)
    findings += check_l5(text, path)
    findings += check_l6(text, path)
    findings += check_l7(text, path)
    # sort by line, then by rule
    findings.sort(key=lambda f: (f.line, f.rule))
    return findings


def lint_product(hub_root: Path, product: str) -> dict:
    """Lint at the product level. Result: {path: [Finding]} dict."""
    proj_root = hub_root / "PROJECTS" / product
    if not proj_root.is_dir():
        raise FileNotFoundError(f"product directory not found: {proj_root}")
    md_files: list[Path] = []
    for sub in ("drafts", "reports/render", "reports"):
        d = proj_root / sub
        if d.is_dir():
            md_files += sorted(d.rglob("*.md"))
    results: dict[Path, list[Finding]] = {}
    for mf in md_files:
        results[mf] = lint_file(mf)
    return results


# ── Report output ──────────────────────────────────────────────────────────

def format_report(
    results: dict[Path, list[Finding]],
    base_dir: Path | None = None,
) -> str:
    """Generate a text report in the render_verify.py pattern."""
    all_findings: list[Finding] = []
    for fs in results.values():
        all_findings += fs

    n_files = len(results)
    n_pass = sum(1 for fs in results.values() if not fs)
    n_fail = sum(1 for f in all_findings if f.level == "FAIL")
    n_warn = sum(1 for f in all_findings if f.level == "WARN")

    lines: list[str] = []
    lines.append("Publication Syntax Lint Results")
    lines.append("============================")
    lines.append("")
    lines.append(f"Files checked: {n_files}")
    lines.append(f"PASS: {n_pass} files")
    lines.append(f"FAIL: {n_fail} items")
    lines.append(f"WARN: {n_warn} items")
    lines.append("")

    if not all_findings:
        lines.append("All checks passed")
        lines.append("")
        return "\n".join(lines)

    # group by rule (FAIL first, then WARN)
    by_rule: dict[str, list[Finding]] = {}
    for f in all_findings:
        by_rule.setdefault(f.rule, []).append(f)
    order = sorted(
        by_rule.keys(),
        key=lambda r: (0 if RULES[r]["level"] == "FAIL" else 1, r),
    )

    for rule in order:
        meta = RULES[rule]
        lines.append(f"[{meta['level']}] {rule} ({meta['desc']})")
        for f in by_rule[rule]:
            display_path = (
                f.path.relative_to(base_dir) if base_dir and _is_rel(f.path, base_dir)
                else f.path
            )
            lines.append(f"  - {display_path}:{f.line}")
            if f.snippet:
                lines.append(f"    {f.snippet}")
            lines.append(f"    -> {f.message}")
        lines.append("")

    return "\n".join(lines)


def _is_rel(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def format_report_md(
    results: dict[Path, list[Finding]],
    base_dir: Path | None = None,
) -> str:
    """Markdown report for --report."""
    header = [
        "# publication-lint report",
        "",
        f"> Generated: {datetime.now().isoformat(timespec='seconds')}"
        f" · auto-generated by lint_publication_syntax.py (do not edit)",
        "",
    ]
    body = format_report(results, base_dir=base_dir)
    # wrap the body in a code block to preserve alignment
    return "\n".join(header) + "```\n" + body + "\n```\n"


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Publication Syntax Lint (publication-lint)")
    ap.add_argument("--input", type=Path, default=None,
                    help="check a single MD file")
    ap.add_argument("--hub-root", type=Path, default=None,
                    help="Planning-Agent-Hub root (used with --product)")
    ap.add_argument("--product", default=None,
                    help="check only PROJECTS/<product> (checks all if omitted)")
    ap.add_argument("--report", type=Path, default=None,
                    help="path to save the md report")
    args = ap.parse_args()

    if not args.input and not args.hub_root:
        sys.stderr.write("[lint] --input or --hub-root required\n")
        return 2

    results: dict[Path, list[Finding]] = {}
    base_dir: Path | None = None

    try:
        if args.input:
            if not args.input.is_file():
                sys.stderr.write(f"[lint] file not found: {args.input}\n")
                return 2
            results[args.input] = lint_file(args.input)
        else:
            hub = args.hub_root
            if not hub.is_dir():
                sys.stderr.write(f"[lint] hub-root not found: {hub}\n")
                return 2
            base_dir = hub
            projects_root = hub / "PROJECTS"
            if not projects_root.is_dir():
                sys.stderr.write(f"[lint] PROJECTS not found: {projects_root}\n")
                return 2
            if args.product:
                results.update(lint_product(hub, args.product))
            else:
                for proj in sorted(projects_root.iterdir()):
                    if not proj.is_dir():
                        continue
                    try:
                        results.update(lint_product(hub, proj.name))
                    except FileNotFoundError:
                        continue
    except OSError as e:
        sys.stderr.write(f"[lint] I/O error: {e}\n")
        return 2

    report = format_report(results, base_dir=base_dir)
    sys.stdout.write(report)
    if not report.endswith("\n"):
        sys.stdout.write("\n")

    if args.report:
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                format_report_md(results, base_dir=base_dir),
                encoding="utf-8",
            )
        except OSError as e:
            sys.stderr.write(f"[lint] failed to save report: {e}\n")
            return 2

    n_fail = sum(1 for fs in results.values() for f in fs if f.level == "FAIL")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
