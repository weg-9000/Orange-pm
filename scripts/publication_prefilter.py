#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Publication prefilter — deterministic removal of process metadata (Source → Publication step 1).

The Source layer (drafts/*.draft.md) contains process metadata such as
DEC/open-issues/TBD/self-verification checklists. The Confluence canonical
copy needs a clean version.

This script performs removal/substitution only via regex, with no LLM
involved (for reproducibility and verifiability). LLM tone normalization is
handled in a separate step (/render --push --style-example).

Removed items:
    - HTML comments (<!-- ... -->)
    - Self-verification checklist section (from "## N. Self-verification checklist" up to just before the next H2)
    - Prohibited items section
    - Work-order meta blocks (RACI etc.) — authoring guidance, not policy facts
    - render_assemble source tags (⟦expand: {id}@{ver} … source⟧)
    - frontmatter slim down (keep only wo_id/type/layer/version/last_updated)

Substituted items:
    - [TBD — ...]                → (unconfirmed)
    - [needs-confirmation: ...]  → (under review)
    - [policy conflict — ...]    → (needs review — compatible items kept)
    - <!-- DEC: ... -->          → removed

Preserved:
    - All table cells
    - All policy body text
    - All [[POL §X-Y]] markers
    - All [[WO-XX]] markers (later converted into Confluence page links)
    - {PREFIX}-A registered vocabulary

exit code:
    0 = success
    1 = input file missing or parse error
    2 = usage error
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ── Regex patterns ──────────────────────────────────────────────────────────

# HTML comments (multi-line included)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# render_assemble source tag: ⟦expand: id@ver … source⟧
SOURCE_TAG_RE = re.compile(r"⟦expand:[^⟧]*⟧")

# TBD / needs-confirmation / policy-conflict markers
TBD_RE = re.compile(r"\[TBD[^\]]*\]")
CONFIRM_NEEDED_RE = re.compile(r"\[needs-confirmation[^\]]*\]")
POLICY_CONFLICT_RE = re.compile(r"\[policy\s*conflict[^\]]*\]")

# H2 section header
H2_RE = re.compile(r"^##\s+(.+?)$", re.MULTILINE)

# Frontmatter extraction
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Section-title patterns targeted for removal (## N. <title> format or ## <title>)
SECTION_REMOVE_PATTERNS = [
    re.compile(r"^##\s+\d+\.\s*Self-verification\s*checklist\s*$", re.MULTILINE),
    re.compile(r"^##\s+Self-verification\s*checklist\s*$", re.MULTILINE),
    re.compile(r"^##\s+\d+\.\s*Prohibited\s*items\s*$", re.MULTILINE),
    re.compile(r"^##\s+Prohibited\s*items\s*$", re.MULTILINE),
    re.compile(r"^##\s+\d+\.\s*Post-completion\s*procedure\s*$", re.MULTILINE),
    re.compile(r"^##\s+Post-completion\s*procedure\s*$", re.MULTILINE),
    re.compile(r"^##\s+Workflow\s+Connections\s*$", re.MULTILINE),
    re.compile(r"^##\s+Invariant\s*input\s*$", re.MULTILINE),
    re.compile(r"^##\s+\d+\.\s*Invariant\s*input\s*$", re.MULTILINE),
    re.compile(r"^##\s+Assignment\s*scope\s*$", re.MULTILINE),
    re.compile(r"^##\s+\d+\.\s*Assignment\s*scope\s*$", re.MULTILINE),
]

# Whitelist of fields to keep in the publication frontmatter
PUBLICATION_FRONTMATTER_FIELDS = {
    "wo_id", "type", "layer", "version", "last_updated", "title",
}


def _strip_section(text: str, header_pattern: re.Pattern) -> str:
    """Remove the H2 section matched by header_pattern, up to just before the next H2 (or EOF)."""
    m = header_pattern.search(text)
    if not m:
        return text
    start = m.start()
    # Find the next H2 — same-level header or higher
    next_h2 = H2_RE.search(text, m.end())
    end = next_h2.start() if next_h2 else len(text)
    return text[:start] + text[end:]


def _slim_frontmatter(text: str) -> str:
    """Keep only the publication-whitelisted fields in the frontmatter.

    HIGH #5: also preserves multi-line YAML values (block list, folded scalar '>',
    literal '|', continuation indent). A key line is identified by colon position +
    zero indentation; indented lines below it are treated as a continuation of the
    preceding key.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return text
    fm_body = m.group(1)
    rest = text[m.end():]

    kept_lines: list[str] = []
    current_key_kept = False  # whether the preceding key is in the whitelist
    for line in fm_body.splitlines():
        stripped = line.strip()
        if not stripped:
            # blank line — ends the preceding key's region
            current_key_kept = False
            continue
        if stripped.startswith("#"):
            continue
        # whether this is an indented (continuation) line
        is_indented = line and line[0] in (" ", "\t")
        if is_indented:
            if current_key_kept:
                kept_lines.append(line)
            continue
        # top-level key line
        if ":" not in stripped:
            # malformed — skip safely
            current_key_kept = False
            continue
        key = stripped.split(":", 1)[0].strip()
        if key in PUBLICATION_FRONTMATTER_FIELDS:
            kept_lines.append(line)
            current_key_kept = True
        else:
            current_key_kept = False
    if not kept_lines:
        return rest
    return "---\n" + "\n".join(kept_lines) + "\n---\n" + rest


def _collapse_blank_lines(text: str) -> str:
    """Collapse 3+ consecutive blank lines down to 2."""
    return re.sub(r"\n{3,}", "\n\n", text)


def prefilter(text: str) -> str:
    """Apply the publication prefilter — remove process metadata + substitute markers.

    Idempotent: calling twice yields the same result.
    """
    # 1. frontmatter slim
    text = _slim_frontmatter(text)

    # 2. Section-level removal (self-verification/prohibited/post-completion/Workflow Connections/invariant-input/assignment-scope)
    for pattern in SECTION_REMOVE_PATTERNS:
        while pattern.search(text):
            new_text = _strip_section(text, pattern)
            if new_text == text:
                break
            text = new_text

    # 3. Remove HTML comments (includes render_assemble schema markers, DEC markers, etc.)
    text = HTML_COMMENT_RE.sub("", text)

    # 4. Remove source tags (⟦expand: ...⟧)
    text = SOURCE_TAG_RE.sub("", text)

    # 5. TBD/confirmation-needed/policy-conflict → simple placeholder
    text = TBD_RE.sub("(unconfirmed)", text)
    text = CONFIRM_NEEDED_RE.sub("(under review)", text)
    text = POLICY_CONFLICT_RE.sub("(needs review — compatible items kept)", text)

    # 6. Collapse consecutive blank lines
    text = _collapse_blank_lines(text)

    return text.strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Publication prefilter — deterministic removal of process metadata"
    )
    ap.add_argument("input", type=Path, help="Input file (usually reports/render/{WO}.complete.md)")
    ap.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Output file (stdout if omitted)"
    )
    ap.add_argument(
        "--in-place", action="store_true",
        help="Overwrite the input file with the result (cannot be used together with --output)"
    )
    args = ap.parse_args()

    if not args.input.is_file():
        print(f"[prefilter] FAIL: input file not found — {args.input}", file=sys.stderr)
        return 1

    if args.in_place and args.output:
        print("[prefilter] FAIL: --in-place and --output cannot be used together", file=sys.stderr)
        return 2

    text = args.input.read_text(encoding="utf-8")
    result = prefilter(text)

    if args.in_place:
        args.input.write_text(result, encoding="utf-8")
        print(f"[prefilter] OK: {args.input} (in-place)", file=sys.stderr)
    elif args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
        print(f"[prefilter] OK: {args.input} → {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
