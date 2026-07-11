#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for lint_publication_syntax.

Verifies a PASS case and a FAIL/WARN case for each rule (L1-L7).
Run:
    python -m pytest lint_publication_syntax_test.py -q
    python lint_publication_syntax_test.py   # built-in runner
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lint_publication_syntax import (  # noqa: E402
    check_l1_l2_l3,
    check_l4,
    check_l5,
    check_l6,
    check_l7,
    format_report,
    lint_file,
)

DUMMY = Path("dummy.md")


# ── L1: allowed classes ──────────────────────────────────────────────────

def test_l1_pass_allowed_classes():
    for cls in ("panel", "info", "warning", "note", "tip", "expand"):
        sec = ' section="X"' if cls == "panel" else ""
        text = "::: {." + cls + sec + "}\nbody\n:::\n"
        findings = check_l1_l2_l3(text, DUMMY)
        assert all(f.rule != "L1" for f in findings), f"L1 false positive for .{cls}"


def test_l1_fail_unknown_class():
    text = '::: {.unknown}\nbody\n:::\n'
    findings = check_l1_l2_l3(text, DUMMY)
    assert any(f.rule == "L1" and f.level == "FAIL" for f in findings)


def test_l1_fail_no_class():
    text = '::: {section="X"}\nbody\n:::\n'
    findings = check_l1_l2_l3(text, DUMMY)
    assert any(f.rule == "L1" for f in findings)


# ── L2: panel section required ────────────────────────────────────────────

def test_l2_pass_with_section():
    text = '::: {.panel section="§1 Policy"}\nbody\n:::\n'
    findings = check_l1_l2_l3(text, DUMMY)
    assert all(f.rule != "L2" for f in findings)


def test_l2_fail_missing_section():
    text = '::: {.panel style="common"}\nbody\n:::\n'
    findings = check_l1_l2_l3(text, DUMMY)
    assert any(f.rule == "L2" and f.level == "FAIL" for f in findings)


# ── L3: allowed panel styles ────────────────────────────────────────────

def test_l3_pass_allowed_styles():
    for sty in ("common", "product", "tbd", "warning", "info"):
        text = f'::: {{.panel section="X" style="{sty}"}}\nbody\n:::\n'
        findings = check_l1_l2_l3(text, DUMMY)
        assert all(f.rule != "L3" for f in findings), f"L3 false positive for style={sty}"


def test_l3_fail_unknown_style():
    text = '::: {.panel section="X" style="garbage"}\nbody\n:::\n'
    findings = check_l1_l2_l3(text, DUMMY)
    assert any(f.rule == "L3" and f.level == "FAIL" for f in findings)


def test_l3_no_style_attr_ok():
    text = '::: {.panel section="X"}\nbody\n:::\n'
    findings = check_l1_l2_l3(text, DUMMY)
    assert all(f.rule != "L3" for f in findings)


# ── L4: code fence language ────────────────────────────────────────────

def test_l4_pass_known_lang():
    text = "```python\ndef f(): pass\n```\n"
    findings = check_l4(text, DUMMY)
    assert all(f.rule != "L4" for f in findings)


def test_l4_pass_no_lang():
    text = "```\nplain\n```\n"
    findings = check_l4(text, DUMMY)
    assert all(f.rule != "L4" for f in findings)


def test_l4_warn_unknown_lang():
    text = "```foolang\nx\n```\n"
    findings = check_l4(text, DUMMY)
    assert any(f.rule == "L4" and f.level == "WARN" for f in findings)


# ── L5: placeholder ────────────────────────────────────────────────────

def test_l5_pass_allowed_placeholders():
    text = "doc: {{DATE}} {{PRODUCT_NAME}} {{toc}} {{change_history 3}}\n"
    findings = check_l5(text, DUMMY)
    assert all(f.rule != "L5" for f in findings)


def test_l5_warn_unknown_placeholder():
    text = "value: {{UNKNOWN_THING}}\n"
    findings = check_l5(text, DUMMY)
    assert any(f.rule == "L5" and f.level == "WARN" for f in findings)


def test_l5_skips_code_block():
    text = "```python\n{{UNKNOWN_THING}}\n```\n"
    findings = check_l5(text, DUMMY)
    assert all(f.rule != "L5" for f in findings)


# ── L6: nested color spans ──────────────────────────────────────────────

def test_l6_pass_flat_color_span():
    text = "This [text]{.color-green} was changed\n"
    findings = check_l6(text, DUMMY)
    assert all(f.rule != "L6" for f in findings)


def test_l6_fail_nested_color_span():
    text = "[a [b]{.color-green} c]{.color-blue}\n"
    findings = check_l6(text, DUMMY)
    assert any(f.rule == "L6" and f.level == "FAIL" for f in findings)


def test_l6_no_color_span_ok():
    text = "A line with just plain text\n"
    findings = check_l6(text, DUMMY)
    assert all(f.rule != "L6" for f in findings)


# ── L7: table column consistency ────────────────────────────────────────

def test_l7_pass_consistent_table():
    text = (
        "| A | B | C |\n"
        "|---|---|---|\n"
        "| 1 | 2 | 3 |\n"
        "| 4 | 5 | 6 |\n"
    )
    findings = check_l7(text, DUMMY)
    assert all(f.rule != "L7" for f in findings)


def test_l7_fail_row_col_mismatch():
    text = (
        "| A | B | C |\n"
        "|---|---|---|\n"
        "| 1 | 2 |\n"
    )
    findings = check_l7(text, DUMMY)
    assert any(f.rule == "L7" and f.level == "FAIL" for f in findings)


def test_l7_no_table_ok():
    text = "plain text\nanother line\n"
    findings = check_l7(text, DUMMY)
    assert all(f.rule != "L7" for f in findings)


# ── Integration: content inside code blocks is masked ──────────────────

def test_code_block_masks_div():
    """A `::: {.bad}` inside a code block is not subject to linting."""
    text = (
        "```markdown\n"
        "::: {.bogus}\n"
        "body\n"
        ":::\n"
        "```\n"
    )
    findings = check_l1_l2_l3(text, DUMMY)
    assert all(f.rule != "L1" for f in findings)


# ── lint_file integration + format_report ───────────────────────────────

def test_lint_file_integration():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.md"
        p.write_text(
            '::: {.panel section="OK"}\n'
            'body\n'
            ':::\n'
            '\n'
            '| A | B |\n'
            '|---|---|\n'
            '| 1 | 2 |\n',
            encoding="utf-8",
        )
        findings = lint_file(p)
        assert findings == []


def test_lint_file_collects_multiple_rules():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.md"
        p.write_text(
            '::: {.panel style="bogus"}\n'  # L2 + L3
            'body\n'
            ':::\n'
            '\n'
            '```weirdlang\n'  # L4
            'code\n'
            '```\n'
            '\n'
            '{{NOT_KNOWN}}\n'  # L5
            '\n'
            '| A | B |\n'  # L7
            '|---|---|\n'
            '| 1 |\n',
            encoding="utf-8",
        )
        findings = lint_file(p)
        rules = {f.rule for f in findings}
        assert "L2" in rules
        assert "L3" in rules
        assert "L4" in rules
        assert "L5" in rules
        assert "L7" in rules


def test_format_report_pass_case():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.md"
        p.write_text("plain text\n", encoding="utf-8")
        results = {p: lint_file(p)}
        out = format_report(results)
        assert "All checks passed" in out
        assert "FAIL: 0" in out


def test_format_report_groups_by_rule():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.md"
        p.write_text(
            '::: {.unknown}\nbody\n:::\n',
            encoding="utf-8",
        )
        results = {p: lint_file(p)}
        out = format_report(results)
        assert "[FAIL] L1" in out
        assert "FAIL: 1" in out


# ── Built-in runner ───────────────────────────────────────────────────────

def _run_all() -> int:
    g = globals()
    tests = sorted(k for k in g if k.startswith("test_") and callable(g[k]))
    failed: list[tuple[str, str]] = []
    passed = 0
    for name in tests:
        try:
            g[name]()
            passed += 1
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed.append((name, f"AssertionError: {e}"))
            print(f"  FAIL  {name}")
        except Exception as e:  # noqa: BLE001
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"  ERROR {name} — {type(e).__name__}: {e}")
    print()
    print(f"Total {len(tests)} — PASS {passed} / FAIL {len(failed)}")
    if failed:
        for name, msg in failed:
            print(f"  - {name}: {msg}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_run_all())
