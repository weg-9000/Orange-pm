#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fact preservation check — a safety net for LLM tone/style transformation.

When the LLM rewrites tone/style in the publication pipeline, this
deterministically verifies that policy facts (numbers, status names, error
codes, table cells, UI text) haven't been dropped or altered.

Verification method:
    - Extract a fact set from the "before" text (right after prefilter) and
      the "after" text (post-LLM transformation)
    - FAIL if before is not a subset of after (some fact is missing)
    - Not a plain string match — compared after normalization (whitespace/punctuation differences are tolerated)

Fact kinds extracted:
    1. Number + unit: "30 days", "100GB", "5 times", "1,000 won", "85%", "v1.0"
    2. Table cell values: non-empty cells in | A | B | C |
    3. Code block bodies (```...```) — UI text, API responses, etc.
    4. Quoted phrases: "error message", 'button label'
    5. Registered vocabulary: canonical headwords in glossary/terms.yml
    6. [[POL §X-Y]] markers (policy §reference)
    7. [[WO-NN]] markers

Each fact is identified by a (kind, normalized_value) tuple.
PASS requires every fact in before to be present in after.

exit code:
    0 = PASS (all facts preserved)
    1 = FAIL (a missing fact was found)
    2 = usage error or file not found
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ── fact-extraction regexes ────────────────────────────────────────────────────────
# NOTE: these regexes match Korean content inside real Hub documents (policy
# text written in Korean) — the Korean literals below (units, etc.) are data
# patterns, not display text, and must not be translated.

# number + unit (Korean and English units + currency, percent, time, bytes)
NUMBER_UNIT_RE = re.compile(
    r"(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
    r"(?:%|원|일|시간|분|초|회|건|개|명|GB|MB|KB|TB|byte|bytes|"
    r"days?|hours?|times?|items?|v?\d+\.\d+(?:\.\d+)?)?"
)

# table row — starts and ends with |, with multiple cells
TABLE_ROW_RE = re.compile(r"^\|.+\|$", re.MULTILINE)
TABLE_SEPARATOR_RE = re.compile(r"^\|[\s\-:|]+\|$")

# code block (fenced)
CODE_BLOCK_RE = re.compile(r"```[a-zA-Z]*\n(.*?)\n```", re.DOTALL)

# inline code
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")

# quoted phrases (includes Korean-style quotation marks)
QUOTED_RE = re.compile(r'["“”]([^"“”\n]{2,100})["“”]')

# [[POL §X-Y]] / [[WO-NN]] / [[doc_id §X]] markers
WIKI_LINK_RE = re.compile(r"\[\[[^\[\]\n]{2,80}\]\]")

# registered policy ID pattern ({PREFIX}-A/B/C-XXX format)
DOC_ID_RE = re.compile(r"\b[A-Z]{1,4}\d?-[ABC]-(?:[A-Z][A-Z0-9]*-)?\d{3}\b")


def _norm(s: str) -> str:
    """Normalize whitespace/punctuation — for fact comparison."""
    # collapse all whitespace to a single space
    s = re.sub(r"\s+", " ", s).strip()
    # strip leading/trailing periods and commas
    s = s.strip(".,;:!?")
    return s


def _extract_table_cells(text: str) -> set[str]:
    """Extract table body cells (excluding the header separator, excluding empty cells)."""
    cells: set[str] = set()
    for line in TABLE_ROW_RE.findall(text):
        if TABLE_SEPARATOR_RE.match(line):
            continue
        for cell in line.strip().strip("|").split("|"):
            v = _norm(cell)
            if v:
                cells.add(v)
    return cells


def _extract_facts(text: str, glossary_terms: set[str] | None = None) -> dict[str, set[str]]:
    """Extract the fact set from text (split by kind).

    glossary_terms: the set of canonical headwords extracted from terms.yml (optional).
    """
    facts: dict[str, set[str]] = {
        "number_unit": set(),
        "table_cell": set(),
        "code_block": set(),
        "inline_code": set(),
        "quoted": set(),
        "wiki_link": set(),
        "doc_id": set(),
        "glossary": set(),
    }

    facts["number_unit"] = {_norm(m) for m in NUMBER_UNIT_RE.findall(text) if any(c.isdigit() for c in m)}
    facts["table_cell"] = _extract_table_cells(text)
    facts["code_block"] = {_norm(b) for b in CODE_BLOCK_RE.findall(text) if _norm(b)}
    facts["inline_code"] = {_norm(c) for c in INLINE_CODE_RE.findall(text) if _norm(c)}
    facts["quoted"] = {_norm(q) for q in QUOTED_RE.findall(text) if _norm(q)}
    facts["wiki_link"] = {_norm(w) for w in WIKI_LINK_RE.findall(text)}
    facts["doc_id"] = {_norm(d) for d in DOC_ID_RE.findall(text)}

    if glossary_terms:
        present = {t for t in glossary_terms if t and t in text}
        facts["glossary"] = present

    return facts


def _load_glossary_terms(hub_root: Path) -> set[str]:
    """Extract canonical headwords from CONTEXT/glossary/terms.yml.

    A simple line parser with no yaml dependency — collects only the
    canonical value from structures like "  - id: foo\n    canonical: 'bar'".

    HIGH #6: to prevent substring false-matches, the following headwords are excluded:
    - single-character (both Korean and English) — risk of partial-matching other vocabulary
    - starts with a YAML structure marker (`>`, `|`, `*`, `&`) — cases where a
      multi-line scalar marker was mistakenly extracted as the canonical value
    """
    terms_path = hub_root / "CONTEXT" / "glossary" / "terms.yml"
    if not terms_path.is_file():
        return set()
    terms: set[str] = set()
    try:
        for line in terms_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("canonical:"):
                v = s.split(":", 1)[1].strip().strip("'\"")
                if not v:
                    continue
                if len(v) <= 1:
                    continue
                if v[0] in (">", "|", "*", "&"):
                    continue
                terms.add(v)
    except Exception:
        pass
    return terms


def check_preservation(
    before_text: str,
    after_text: str,
    glossary_terms: set[str] | None = None,
) -> dict:
    """Check whether every fact in before is preserved in after.

    Returns: {
        "pass": bool,
        "missing_by_kind": { kind: [missing_values] },
        "total_before": int,
        "total_missing": int,
    }
    """
    before = _extract_facts(before_text, glossary_terms)
    after = _extract_facts(after_text, glossary_terms)

    missing_by_kind: dict[str, list[str]] = {}
    total_before = 0
    total_missing = 0
    for kind, before_set in before.items():
        total_before += len(before_set)
        after_set = after[kind]
        missing = sorted(before_set - after_set)
        if missing:
            missing_by_kind[kind] = missing
            total_missing += len(missing)

    return {
        "pass": total_missing == 0,
        "missing_by_kind": missing_by_kind,
        "total_before": total_before,
        "total_missing": total_missing,
    }


def _format_report(result: dict, before_path: Path, after_path: Path) -> str:
    lines = [
        "# Fact Preservation Check Report",
        "",
        f"before: `{before_path}`",
        f"after:  `{after_path}`",
        "",
        f"Total facts: {result['total_before']}",
        f"Missing facts: {result['total_missing']}",
        f"Result: {'✅ PASS' if result['pass'] else '❌ FAIL'}",
        "",
    ]
    if result["missing_by_kind"]:
        lines.append("## Missing facts (lost during LLM transformation)")
        lines.append("")
        for kind, missing in result["missing_by_kind"].items():
            lines.append(f"### {kind} ({len(missing)})")
            lines.append("")
            for v in missing[:50]:
                lines.append(f"- `{v}`")
            if len(missing) > 50:
                lines.append(f"- _... and {len(missing) - 50} more_")
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fact preservation check — a safety net for LLM publication conversion"
    )
    ap.add_argument("--before", required=True, type=Path,
                    help="text before LLM conversion (right after prefilter)")
    ap.add_argument("--after", required=True, type=Path,
                    help="text after LLM conversion (publication result)")
    ap.add_argument("--hub-root", type=Path, default=None,
                    help="for loading glossary/terms.yml (optional)")
    ap.add_argument("--report", type=Path, default=None,
                    help="save the result as a markdown report (stdout if omitted)")
    ap.add_argument("--json", action="store_true",
                    help="output the result as JSON")
    args = ap.parse_args()

    if not args.before.is_file():
        print(f"[fact-check] FAIL: before file not found — {args.before}", file=sys.stderr)
        return 2
    if not args.after.is_file():
        print(f"[fact-check] FAIL: after file not found — {args.after}", file=sys.stderr)
        return 2

    glossary = _load_glossary_terms(args.hub_root) if args.hub_root else set()

    before_text = args.before.read_text(encoding="utf-8")
    after_text = args.after.read_text(encoding="utf-8")

    result = check_preservation(before_text, after_text, glossary)

    if args.json:
        out = json.dumps(result, ensure_ascii=False, indent=2)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(out, encoding="utf-8")
        else:
            sys.stdout.write(out + "\n")
    else:
        report = _format_report(result, args.before, args.after)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(report, encoding="utf-8")
            print(
                f"[fact-check] {'PASS' if result['pass'] else 'FAIL'} "
                f"— missing {result['total_missing']}/{result['total_before']} → {args.report}",
                file=sys.stderr,
            )
        else:
            sys.stdout.write(report)

    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
