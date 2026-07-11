#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for storage_to_md (spec: publication-syntax.md).

Per-macro/element conversion cases + 1 round-trip case.
Run:
    python -m pytest storage_to_md_test.py -q
    python storage_to_md_test.py   # built-in runner
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from storage_to_md import (  # noqa: E402
    _color_spans_to_md,
    _strip_color_spans,
    convert_storage,
    parse_storage,
)


# ── Panel (spec §3.1) ────────────────────────────────────────────────────
def test_panel_with_section_default_style_emits_panel_div():
    xml = (
        '<ac:structured-macro ac:name="panel" ac:schema-version="1">'
        '<ac:parameter ac:name="borderColor">#24FE00</ac:parameter>'
        '<ac:parameter ac:name="titleColor">#002FD5</ac:parameter>'
        '<ac:parameter ac:name="titleBGColor">24FE00</ac:parameter>'
        '<ac:parameter ac:name="borderStyle">none</ac:parameter>'
        '<ac:parameter ac:name="title">§1 Policy Overview</ac:parameter>'
        "<ac:rich-text-body><h2>§1 Policy Overview</h2><p>Body text</p></ac:rich-text-body>"
        "</ac:structured-macro>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert '::: {.panel section="§1 Policy Overview"}' in md, md
    assert "style=" not in md, "the common (default) style is omitted on round-trip"
    assert "## §1 Policy Overview" in md
    assert "Body text" in md
    assert ":::" in md


def test_panel_with_product_style():
    xml = (
        '<ac:structured-macro ac:name="panel" ac:schema-version="1">'
        '<ac:parameter ac:name="borderColor">#0050E5</ac:parameter>'
        '<ac:parameter ac:name="title">Product Area</ac:parameter>'
        "<ac:rich-text-body><p>Content</p></ac:rich-text-body>"
        "</ac:structured-macro>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert 'style="product"' in md, md
    assert 'section="Product Area"' in md


# ── Info / Warning / Note / Tip (spec §3.2) ───────────────────────────────
def test_info_macro():
    xml = (
        '<ac:structured-macro ac:name="info" ac:schema-version="1">'
        "<ac:rich-text-body><p>General informational message</p></ac:rich-text-body>"
        "</ac:structured-macro>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "::: {.info}" in md
    assert "General informational message" in md


def test_warning_macro():
    xml = (
        '<ac:structured-macro ac:name="warning" ac:schema-version="1">'
        "<ac:rich-text-body><p>Caution</p></ac:rich-text-body>"
        "</ac:structured-macro>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "::: {.warning}" in md
    assert "Caution" in md


# ── Expand (spec §3.3) ──────────────────────────────────────────────────
def test_expand_with_title():
    xml = (
        '<ac:structured-macro ac:name="expand" ac:schema-version="1">'
        '<ac:parameter ac:name="title">Detailed Change History</ac:parameter>'
        "<ac:rich-text-body><ul><li>v1: draft</li><li>v2: refined</li></ul></ac:rich-text-body>"
        "</ac:structured-macro>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert '::: {.expand title="Detailed Change History"}' in md
    assert "- v1: draft" in md
    assert "- v2: refined" in md


# ── Code Block (spec §3.5) ───────────────────────────────────────────────
def test_code_macro_with_language():
    xml = (
        '<ac:structured-macro ac:name="code" ac:schema-version="1">'
        '<ac:parameter ac:name="language">python</ac:parameter>'
        '<ac:plain-text-body><![CDATA[def foo():\n    pass]]></ac:plain-text-body>'
        "</ac:structured-macro>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "```python" in md
    assert "def foo():" in md
    assert "    pass" in md  # indentation preserved


def test_code_macro_no_language():
    xml = (
        '<ac:structured-macro ac:name="code" ac:schema-version="1">'
        '<ac:plain-text-body><![CDATA[plain code]]></ac:plain-text-body>'
        "</ac:structured-macro>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "```\nplain code\n```" in md


# ── Table (spec §5.1) ────────────────────────────────────────────────────
def test_simple_table_even_columns_no_directive():
    xml = (
        '<table class="relative-table wrapped">'
        '<colgroup><col style="width: 50%;"/><col style="width: 50%;"/></colgroup>'
        "<thead><tr><th>Item</th><th>Content</th></tr></thead>"
        "<tbody><tr><td>Purpose</td><td>The purpose of this policy document</td></tr></tbody>"
        "</table>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "| Item | Content |" in md
    assert "| Purpose | The purpose of this policy document |" in md
    assert "col-widths" not in md, "even distribution does not emit a directive"


def test_table_uneven_columns_emits_directive():
    xml = (
        '<table class="relative-table wrapped">'
        '<colgroup><col style="width: 15%;"/><col style="width: 85%;"/></colgroup>'
        "<thead><tr><th>Item</th><th>Content</th></tr></thead>"
        "<tbody><tr><td>Purpose</td><td>Body text</td></tr></tbody>"
        "</table>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "<!-- col-widths: 15%, 85% -->" in md, md


def test_table_no_thead_first_row_is_header():
    xml = (
        "<table>"
        "<tbody>"
        "<tr><td>A</td><td>B</td></tr>"
        "<tr><td>1</td><td>2</td></tr>"
        "</tbody>"
        "</table>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "| A | B |" in md
    assert "|---|---|" in md
    assert "| 1 | 2 |" in md


# ── Page link (spec §4.1) ─────────────────────────────────────────────────
def test_page_link():
    xml = (
        '<p><ac:link><ri:page ri:content-title="[Requirements Definition] DBaaS"/></ac:link></p>'
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "[[page:[Requirements Definition] DBaaS]]" in md


# ── Automatic macros (spec §4.3) ──────────────────────────────────────────
def test_toc_macro():
    xml = '<p><ac:structured-macro ac:name="toc" ac:schema-version="1"/></p>'
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "{{toc}}" in md


def test_change_history_macro():
    xml = (
        '<ac:structured-macro ac:name="change-history" ac:schema-version="1">'
        '<ac:parameter ac:name="limit">5</ac:parameter>'
        "</ac:structured-macro>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "{{change_history 5}}" in md


# ── Standard elements (spec §5) ───────────────────────────────────────────
def test_headings():
    xml = "<h1>H1</h1><h2>H2</h2><h3>H3</h3>"
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "# H1" in md
    assert "## H2" in md
    assert "### H3" in md


def test_strong_em_inline():
    xml = "<p>This is <strong>emphasis</strong> and <em>italics</em></p>"
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "**emphasis**" in md
    assert "*italics*" in md


def test_unordered_list():
    xml = "<ul><li>First</li><li>Second</li></ul>"
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "- First" in md
    assert "- Second" in md


def test_ordered_list():
    xml = "<ol><li>One</li><li>Two</li></ol>"
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "1. One" in md
    assert "2. Two" in md


def test_external_link():
    xml = '<p><a href="https://example.com">Example</a></p>'
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "[Example](https://example.com)" in md


def test_hr_and_blockquote():
    xml = "<hr/><blockquote><p>Quote</p></blockquote>"
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "---" in md
    assert "> Quote" in md


# ── Automatic layout stripping (spec §7 reverse direction) ─────────────────
def test_layout_section_single_with_panel_is_stripped():
    xml = (
        '<ac:layout-section ac:type="single"><ac:layout-cell>'
        '<ac:structured-macro ac:name="panel" ac:schema-version="1">'
        '<ac:parameter ac:name="title">§1</ac:parameter>'
        "<ac:rich-text-body><p>Body text</p></ac:rich-text-body>"
        "</ac:structured-macro>"
        "</ac:layout-cell></ac:layout-section>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert '::: {.panel section="§1"}' in md
    # the layout wrapper should disappear
    assert "layout-section" not in md
    assert "layout-cell" not in md


def test_spacer_layout_section_ignored():
    xml = (
        '<ac:layout-section ac:type="single"><ac:layout-cell>'
        "<p><br/></p>"
        "</ac:layout-cell></ac:layout-section>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    # body should be empty (spacer)
    assert md.strip() == "", f"spacer should be empty, got: {md!r}"


# ── Frontmatter reconstruction (spec §2) ──────────────────────────────────
def test_frontmatter_header_extracted_from_first_info_section():
    xml = (
        '<ac:layout>'
        '<ac:layout-section ac:type="single"><ac:layout-cell>'
        '<ac:structured-macro ac:name="info" ac:schema-version="1">'
        "<ac:rich-text-body><p>doc notice</p></ac:rich-text-body>"
        "</ac:structured-macro>"
        "</ac:layout-cell></ac:layout-section>"
        "</ac:layout>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=True)
    assert md.startswith("---")
    assert "publication:" in md
    assert "header:" in md
    assert "style: info" in md
    # prevent duplicate emit: ::: {.info} should not reappear in the body
    assert md.count("doc notice") == 1, f"duplicate emit found:\n{md}"
    assert "::: {.info}" not in md, f"info absorbed into frontmatter was also emitted in the body:\n{md}"


def test_frontmatter_meta_extracted_skips_body_duplication():
    # If the panel/change-history in the meta layout (two_equal) is absorbed into
    # frontmatter, ::: {.panel section="Reference Material"} should not be emitted
    # again in the body.
    xml = (
        '<ac:layout>'
        '<ac:layout-section ac:type="two_equal">'
        '<ac:layout-cell>'
        '<ac:structured-macro ac:name="panel" ac:schema-version="1">'
        '<ac:parameter ac:name="title">Reference Material</ac:parameter>'
        '<ac:rich-text-body><p>Related link</p></ac:rich-text-body>'
        '</ac:structured-macro>'
        '</ac:layout-cell>'
        '<ac:layout-cell>'
        '<ac:structured-macro ac:name="change-history" ac:schema-version="1">'
        '<ac:parameter ac:name="limit">5</ac:parameter>'
        '</ac:structured-macro>'
        '</ac:layout-cell>'
        '</ac:layout-section>'
        '</ac:layout>'
    )
    md, _ = convert_storage(xml, extract_frontmatter=True)
    assert "Reference Material" in md  # frontmatter title
    assert md.count("Related link") == 1
    assert "::: {.panel" not in md, f"panel absorbed into meta was also emitted in the body:\n{md}"


# ── Unsupported macro warning (triggers CLI exit code 2) ──────────────────
def test_unsupported_macro_records_warning():
    xml = (
        '<ac:structured-macro ac:name="jira" ac:schema-version="1">'
        '<ac:parameter ac:name="key">FOO-1</ac:parameter>'
        "</ac:structured-macro>"
    )
    md, state = convert_storage(xml, extract_frontmatter=False)
    assert "jira" in state.unsupported_macros


# ── Color handling (Phase 3 reserved) ─────────────────────────────────────
def test_strip_colors_removes_fenced_spans():
    text = "This is [changed]{.color-green} text"
    stripped = _strip_color_spans(text)
    assert stripped == "This is changed text"


def test_color_spans_to_md_converts_rgb_green():
    text = '<span style="color: rgb(0,176,80)">new</span> text'
    md = _color_spans_to_md(text)
    assert "[new]{.color-green}" in md


def test_color_spans_to_md_converts_rgb_blue():
    text = '<span style="color: rgb(0,80,229)">previous</span>'
    md = _color_spans_to_md(text)
    assert "[previous]{.color-blue}" in md


# ── Color span integration (Phase 3D — convert_storage default behavior) ──
def test_convert_storage_default_converts_xml_span_to_md_fenced_span():
    """Default mode: XML's <span style="color: rgb(...)"> → MD [..]{.color-XXX}"""
    xml = (
        '<p>Before: <span style="color: rgb(0,176,80)">new text</span> after</p>'
    )
    md, _ = convert_storage(xml, extract_frontmatter=False, strip_colors=False)
    assert "[new text]{.color-green}" in md
    # raw XML span should not remain
    assert "<span" not in md


def test_convert_storage_strip_colors_removes_all_color_markup():
    """strip_colors=True: completely remove color info (clean MD, for diff comparison)"""
    xml = (
        '<p>Before: <span style="color: rgb(0,176,80)">new</span> next '
        '<span style="color: rgb(0,80,229)">previous</span> end</p>'
    )
    md, _ = convert_storage(xml, extract_frontmatter=False, strip_colors=True)
    assert "new" in md and "previous" in md
    assert "color-green" not in md and "color-blue" not in md
    assert "<span" not in md


def test_convert_storage_color_span_round_trip_via_md_fenced():
    """Whether XML span → MD fenced span → XML span round-trip is possible"""
    xml = '<p><span style="color: rgb(0,176,80)">changed</span> text</p>'
    md, _ = convert_storage(xml, extract_frontmatter=False, strip_colors=False)
    # the MD must contain a fenced span so the next round-trip step (md_to_storage) can turn it back into an XML span
    assert "{.color-green}" in md


# ── parse_storage robustness ──────────────────────────────────────────────
def test_parse_empty_string_returns_root():
    root = parse_storage("")
    assert root is not None


def test_parse_nbsp_entity():
    # &nbsp; is not valid XML — it must be pre-substituted
    root = parse_storage("<p>A&nbsp;B</p>")
    assert root is not None


def test_parse_invalid_xml_raises():
    try:
        parse_storage("<unclosed>")
    except ValueError:
        return
    raise AssertionError("expected a ValueError to be raised")


# ── Round-trip (spec §8/§9) ──────────────────────────────────────────────
def test_round_trip_simple_panel():
    """md_to_storage(storage_to_md(X)) ≈ X (after normalization) — spec §9.

    Full equivalence comparison is tricky due to frontmatter/layout automation →
    verify that core elements (panel/heading/table/text) are preserved.
    """
    # md_to_storage must be in the same directory
    try:
        from md_to_storage import convert as md_to_storage_convert
    except ImportError:
        # import may fail depending on the environment — skip
        print("  (skip) md_to_storage import unavailable")
        return

    original_md = (
        "::: {.panel section=\"§1 Policy Overview\"}\n"
        "## §1 Policy Overview\n"
        "\n"
        "Body paragraph.\n"
        "\n"
        "| Item | Content |\n"
        "|---|---|\n"
        "| Purpose | The purpose of this policy document |\n"
        ":::\n"
    )
    # MD → XML → MD
    xml = md_to_storage_convert(original_md)
    md2, _ = convert_storage(xml, extract_frontmatter=False)

    # verify core elements are preserved (after whitespace/newline normalization)
    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    n = norm(md2)
    assert "§1 Policy Overview" in n
    assert "Body paragraph" in n
    assert "Purpose" in n
    assert "The purpose of this policy document" in n
    assert ".panel" in n
    # heading preserved
    assert "## §1" in md2 or "##" in md2


# ── CLI smoke ────────────────────────────────────────────────────────────
def test_cli_main_with_xml_input(tmpdir_path=None):
    import tempfile
    from storage_to_md import main as cli_main

    with tempfile.TemporaryDirectory() as tmp:
        xml_path = Path(tmp) / "input.xml"
        out_path = Path(tmp) / "out.md"
        xml_path.write_text(
            '<p>hello <strong>world</strong></p>',
            encoding="utf-8",
        )
        rc = cli_main(["--input", str(xml_path), "--output", str(out_path)])
        assert rc == 0
        out = out_path.read_text(encoding="utf-8")
        assert "hello" in out
        assert "**world**" in out


def test_cli_main_from_snapshot_json():
    import json as _json
    import tempfile
    from storage_to_md import main as cli_main

    with tempfile.TemporaryDirectory() as tmp:
        snap_path = Path(tmp) / "snapshot.json"
        out_path = Path(tmp) / "out.md"
        snap = {
            "id": "1",
            "version": {"number": 1},
            "title": "t",
            "body": {"storage": {"value": "<p>hello</p>"}},
        }
        snap_path.write_text(_json.dumps(snap), encoding="utf-8")
        rc = cli_main([
            "--input", str(snap_path),
            "--from-snapshot",
            "--output", str(out_path),
        ])
        assert rc == 0
        assert "hello" in out_path.read_text(encoding="utf-8")


def test_cli_unsupported_macro_returns_2():
    import tempfile
    from storage_to_md import main as cli_main

    with tempfile.TemporaryDirectory() as tmp:
        xml_path = Path(tmp) / "input.xml"
        out_path = Path(tmp) / "out.md"
        xml_path.write_text(
            '<ac:structured-macro ac:name="jira"/>',
            encoding="utf-8",
        )
        rc = cli_main(["--input", str(xml_path), "--output", str(out_path)])
        assert rc == 2  # unsupported macro


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
    print(f"total {len(tests)} — PASS {passed} / FAIL {len(failed)}")
    if failed:
        for name, msg in failed:
            print(f"  - {name}: {msg}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_run_all())
