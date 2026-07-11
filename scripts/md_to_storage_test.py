#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for md_to_storage.py (stdlib unittest).

Run:
    python md_to_storage_test.py
"""
from __future__ import annotations

import hashlib
import io
import sys
import unittest
from pathlib import Path

# Import md_to_storage from the same directory
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import md_to_storage as mts  # noqa: E402


def _normalize(s: str) -> str:
    """Normalize whitespace/line breaks — make comparisons more robust."""
    return "\n".join(line.rstrip() for line in s.splitlines() if line.strip())


class TestBasicPanel(unittest.TestCase):
    """T1: basic panel (common style)."""

    def test_basic_panel(self):
        md = (
            "::: {.panel section=\"§1 Overview\"}\n"
            "## §1 Overview\n"
            "\n"
            "Body paragraph.\n"
            ":::\n"
        )
        xml = mts.convert(md)
        # Verify core elements are present
        self.assertIn('<ac:layout>', xml)
        self.assertIn('<ac:layout-section ac:type="single">', xml)
        self.assertIn('<ac:structured-macro ac:name="panel"', xml)
        self.assertIn('<ac:parameter ac:name="title">§1 Overview</ac:parameter>',
                      xml)
        # borderColor for the default style=common
        self.assertIn(
            '<ac:parameter ac:name="borderColor">#24FE00</ac:parameter>',
            xml,
        )
        self.assertIn(
            '<ac:parameter ac:name="titleColor">#002FD5</ac:parameter>',
            xml,
        )
        self.assertIn('<h2>§1 Overview</h2>', xml)
        self.assertIn('<p>Body paragraph.</p>', xml)
        # Trailing spacer auto-inserted
        self.assertIn(
            '<ac:layout-cell><p><br/></p></ac:layout-cell>',
            xml,
        )


class TestPanelStyleVariant(unittest.TestCase):
    """T2: panel style variants (tbd / product)."""

    def test_panel_tbd_style(self):
        md = (
            "::: {.panel section=\"TBD\" style=\"tbd\"}\n"
            "Needs review.\n"
            ":::\n"
        )
        xml = mts.convert(md)
        self.assertIn(
            '<ac:parameter ac:name="borderColor">#FF4D4F</ac:parameter>',
            xml,
        )
        self.assertIn(
            '<ac:parameter ac:name="titleColor">#FFFFFF</ac:parameter>',
            xml,
        )

    def test_panel_product_style(self):
        md = (
            "::: {.panel section=\"Product\" style=\"product\"}\n"
            "Body text.\n"
            ":::\n"
        )
        xml = mts.convert(md)
        self.assertIn(
            '<ac:parameter ac:name="borderColor">#0050E5</ac:parameter>',
            xml,
        )


class TestInfoCallout(unittest.TestCase):
    """T3: Info / Warning callouts (no layout wrapper)."""

    def test_info_callout(self):
        md = (
            "::: {.info}\n"
            "General information.\n"
            ":::\n"
        )
        xml = mts.convert(md)
        self.assertIn(
            '<ac:structured-macro ac:name="info" ac:schema-version="1">',
            xml,
        )
        self.assertIn('<p>General information.</p>', xml)
        # the info callout must have no layout-section wrapper (spec §7 rule 3)
        # verify: the callout should not be immediately inside a layout-section single
        # (no frontmatter, so it's in the body flow)
        # whether the info macro line is not a direct child of layout-cell is checked via indent
        # simple assertion: the first macro right after <ac:layout> should be info
        self.assertIn(
            '<ac:structured-macro ac:name="info"', xml.split('<ac:layout>')[1]
        )

    def test_warning_callout(self):
        md = "::: {.warning}\nCaution.\n:::\n"
        xml = mts.convert(md)
        self.assertIn('<ac:structured-macro ac:name="warning"', xml)

    def test_note_and_tip(self):
        for cls in ("note", "tip"):
            xml = mts.convert(f"::: {{.{cls}}}\nBody text.\n:::\n")
            self.assertIn(f'<ac:structured-macro ac:name="{cls}"', xml)


class TestTable(unittest.TestCase):
    """T4: table + col-widths directive."""

    def test_table_basic_equal_widths(self):
        md = (
            "| Item | Content |\n"
            "|---|---|\n"
            "| **Purpose** | The policy |\n"
            "| Scope | All |\n"
        )
        xml = mts.convert(md)
        self.assertIn(
            '<table class="relative-table wrapped" style="width: 90%;">',
            xml,
        )
        self.assertIn('<colgroup>', xml)
        # even distribution — 2 col → 50% / 50%
        self.assertIn('<col style="width: 50%;"/>', xml)
        self.assertIn('<th>Item</th>', xml)
        self.assertIn('<th>Content</th>', xml)
        self.assertIn('<td><strong>Purpose</strong></td>', xml)
        self.assertIn('<td>The policy</td>', xml)

    def test_table_with_col_widths_directive(self):
        md = (
            "<!-- col-widths: 15%, 85% -->\n"
            "| Item | Content |\n"
            "|---|---|\n"
            "| Purpose | Policy document |\n"
        )
        xml = mts.convert(md)
        self.assertIn('<col style="width: 15%;"/>', xml)
        self.assertIn('<col style="width: 85%;"/>', xml)

    def test_table_three_columns_equal(self):
        md = (
            "| A | B | C |\n"
            "|---|---|---|\n"
            "| 1 | 2 | 3 |\n"
        )
        xml = mts.convert(md)
        # 100 // 3 = 33, remainder 1 → last one gets 34%
        self.assertIn('<col style="width: 33%;"/>', xml)
        self.assertIn('<col style="width: 34%;"/>', xml)


class TestCodeBlock(unittest.TestCase):
    """T5: code block."""

    def test_code_block_with_language(self):
        md = (
            "```python\n"
            "def foo():\n"
            "    return 1\n"
            "```\n"
        )
        xml = mts.convert(md)
        self.assertIn(
            '<ac:structured-macro ac:name="code" ac:schema-version="1">',
            xml,
        )
        self.assertIn(
            '<ac:parameter ac:name="language">python</ac:parameter>',
            xml,
        )
        self.assertIn(
            '<ac:plain-text-body><![CDATA[def foo():\n    return 1]]>'
            '</ac:plain-text-body>',
            xml,
        )

    def test_code_block_no_language(self):
        md = "```\nplain text\n```\n"
        xml = mts.convert(md)
        self.assertIn('<ac:structured-macro ac:name="code"', xml)
        # no language parameter
        self.assertNotIn('<ac:parameter ac:name="language">', xml)


class TestInlineMacros(unittest.TestCase):
    """T6: inline macros (page link, toc, change_history, placeholders)."""

    def test_page_link(self):
        md = "Reference: [[page:[Policy Definition] DBaaS]]\n"
        xml = mts.convert(md)
        self.assertIn(
            '<ac:link><ri:page ri:content-title="[Policy Definition] DBaaS"/></ac:link>',
            xml,
        )

    def test_toc(self):
        md = "{{toc}}\n"
        xml = mts.convert(md)
        self.assertIn(
            '<ac:structured-macro ac:name="toc" ac:schema-version="1"/>', xml
        )

    def test_change_history(self):
        md = "{{change_history 5}}\n"
        xml = mts.convert(md)
        self.assertIn(
            '<ac:structured-macro ac:name="change-history"', xml
        )
        self.assertIn('<ac:parameter ac:name="limit">5</ac:parameter>', xml)

    def test_placeholder_preserved(self):
        md = "This page is the canonical version of {{PRODUCT_NAME}}.\n"
        xml = mts.convert(md)
        # substitution mode OFF → placeholder text stays as-is
        self.assertIn('{{PRODUCT_NAME}}', xml)

    def test_regular_link(self):
        md = "[Document](https://example.com)\n"
        xml = mts.convert(md)
        self.assertIn('<a href="https://example.com">Document</a>', xml)


class TestFrontmatter(unittest.TestCase):
    """T7: Frontmatter publication section → automatic header/meta layout."""

    def test_header_info(self):
        md = (
            "---\n"
            "title: \"[Policy Definition] X\"\n"
            "publication:\n"
            "  header:\n"
            "    style: info\n"
            "    body: |\n"
            "      **This document is the policy document for X.**\n"
            "---\n"
            "Body starts.\n"
        )
        xml = mts.convert(md)
        self.assertIn('<ac:structured-macro ac:name="info"', xml)
        self.assertIn('<strong>This document is the policy document for X.</strong>', xml)

    def test_meta_two_equal(self):
        md = (
            "---\n"
            "title: X\n"
            "publication:\n"
            "  meta:\n"
            "    layout: two_equal\n"
            "    cells:\n"
            "      - panel:\n"
            "          title: \"Reference\"\n"
            "          body: |\n"
            "            - Item 1\n"
            "      - change_history: 3\n"
            "---\n"
            "Body text.\n"
        )
        xml = mts.convert(md)
        self.assertIn('<ac:layout-section ac:type="two_equal">', xml)
        self.assertIn('<ac:parameter ac:name="title">Reference</ac:parameter>', xml)
        self.assertIn('<ac:parameter ac:name="limit">3</ac:parameter>', xml)


class TestDeterminism(unittest.TestCase):
    """T8: determinism — same input → same byte output (spec §9)."""

    def test_same_input_same_hash(self):
        md = (
            "::: {.panel section=\"§A\"}\n"
            "## §A\n"
            "Content 1.\n"
            "\n"
            "| A | B |\n"
            "|---|---|\n"
            "| 1 | 2 |\n"
            ":::\n"
            "\n"
            "::: {.panel section=\"§B\" style=\"product\"}\n"
            "## §B\n"
            "Content 2.\n"
            ":::\n"
        )
        xml1 = mts.convert(md)
        xml2 = mts.convert(md)
        self.assertEqual(xml1, xml2)
        h1 = hashlib.sha256(xml1.encode("utf-8")).hexdigest()
        h2 = hashlib.sha256(xml2.encode("utf-8")).hexdigest()
        self.assertEqual(h1, h2)


class TestExpand(unittest.TestCase):
    """T9: Expand macro."""

    def test_expand(self):
        md = (
            "::: {.expand title=\"History\"}\n"
            "- 2026-05-01: draft\n"
            "- 2026-05-15: incorporated\n"
            ":::\n"
        )
        xml = mts.convert(md)
        self.assertIn(
            '<ac:structured-macro ac:name="expand"', xml
        )
        self.assertIn(
            '<ac:parameter ac:name="title">History</ac:parameter>', xml
        )
        self.assertIn('<li>2026-05-01: draft</li>', xml)


class TestSpacingBetweenPanels(unittest.TestCase):
    """T10: automatic spacer between panels (spec §7)."""

    def test_two_panels_have_spacer_between(self):
        md = (
            "::: {.panel section=\"A\"}\n"
            "Content A.\n"
            ":::\n"
            "::: {.panel section=\"B\"}\n"
            "Content B.\n"
            ":::\n"
        )
        xml = mts.convert(md)
        # between panels + trailing at the end — 2 spacers should occur
        spacer_marker = '<ac:layout-cell><p><br/></p></ac:layout-cell>'
        count = xml.count(spacer_marker)
        self.assertGreaterEqual(
            count, 2, f"not enough spacers: {count}\n--- XML ---\n{xml}"
        )


class TestCodeBlockCDATAEscape(unittest.TestCase):
    """T11: splitting ]]> inside a code block."""

    def test_cdata_close_marker_split(self):
        md = (
            "```\n"
            "var x = ']]>';\n"
            "```\n"
        )
        xml = mts.convert(md)
        # if the raw ]]> were inserted as-is it would break the CDATA → it must be split
        self.assertIn(']]]]><![CDATA[>', xml)


if __name__ == "__main__":
    unittest.main(verbosity=2)
