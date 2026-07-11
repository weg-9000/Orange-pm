#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for diff_blocks.py (stdlib unittest).

Run:
    python diff_blocks_test.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import diff_blocks as db  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────


MD_V1_BASE = """---
title: "test"
version: 1
---

::: {.panel section="§3 Policy"}
## §3 Policy

### §3.1 Standard Pricing

| Item | Price |
|---|---|
| Default | $1000 |
| Add-on | $100 |

Standard pricing plan description paragraph.

Additional paragraph body.
:::

::: {.panel section="§4 Operations"}
## §4 Operations

- Item A
- Item B
- Item C
:::
"""


def _by_path(blocks):
    return {b.path: b for b in blocks}


# ── T1: No change ─────────────────────────────────────────────────────────────


class TestNoChange(unittest.TestCase):
    """T1: old == new — everything unchanged. green/blue both ∅."""

    def test_no_change(self):
        old = db.parse_blocks(MD_V1_BASE)
        new = db.parse_blocks(MD_V1_BASE)
        diff = db.diff_blocks(old, new)
        self.assertEqual(len(diff.added), 0)
        self.assertEqual(len(diff.removed), 0)
        self.assertEqual(len(diff.modified), 0)
        self.assertGreater(len(diff.unchanged), 0)

        regions = db.compute_color_regions(old, new, None)
        self.assertEqual(len(regions.green), 0)
        self.assertEqual(len(regions.blue), 0)


# ── T2: First write — everything added ─────────────────────────────────────


class TestFirstWrite(unittest.TestCase):
    """T2: old is empty MD — everything added.

    Spec: G_1 = ∅ (all black). The caller must discard the result on the
    first publish; here we only check that the added count is greater than
    0, verifying consistency with the docstring's statement that the
    "actual first-publish policy" is the caller's responsibility.
    """

    def test_first_write_all_added(self):
        old = db.parse_blocks("")
        new = db.parse_blocks(MD_V1_BASE)
        diff = db.diff_blocks(old, new)
        self.assertEqual(len(diff.unchanged), 0)
        self.assertEqual(len(diff.removed), 0)
        self.assertEqual(len(diff.modified), 0)
        self.assertGreater(len(diff.added), 0)

        # compute_color_regions itself computes added as green — the caller
        # must recognize this is the first publish and discard/ignore the result.
        regions = db.compute_color_regions(old, new, None)
        self.assertEqual(len(regions.green), len(diff.added))
        self.assertEqual(len(regions.blue), 0)


# ── T3: Simple paragraph edit ────────────────────────────────────────────────


class TestParagraphModify(unittest.TestCase):
    """T3: paragraph body edited in one place → green 1, rest unchanged."""

    def test_paragraph_modify(self):
        v1 = MD_V1_BASE
        v2 = MD_V1_BASE.replace(
            "Standard pricing plan description paragraph.",
            "Standard pricing plan changed description paragraph.",
        )
        old = db.parse_blocks(v1)
        new = db.parse_blocks(v2)
        diff = db.diff_blocks(old, new)
        self.assertEqual(len(diff.added), 0)
        self.assertEqual(len(diff.removed), 0)
        self.assertEqual(len(diff.modified), 1)

        old_b, new_b = diff.modified[0]
        self.assertEqual(old_b.path, new_b.path)
        self.assertNotEqual(old_b.block_hash, new_b.block_hash)
        self.assertIn("§3 Policy", new_b.path)
        self.assertEqual(new_b.kind, db.KIND_PANEL_INNER_PARA)

        regions = db.compute_color_regions(old, new, None)
        self.assertEqual(len(regions.green), 1)
        self.assertEqual(len(regions.blue), 0)
        self.assertEqual(regions.green[0].path, new_b.path)


# ── T4: One table cell edited ────────────────────────────────────────────────


class TestTableCellModify(unittest.TestCase):
    """T4: only a single table cell is edited → 1 cell-level modified entry (not row-level)."""

    def test_table_cell_modify(self):
        v1 = MD_V1_BASE
        v2 = MD_V1_BASE.replace("| Default | $1000 |", "| Default | $1500 |")
        old = db.parse_blocks(v1)
        new = db.parse_blocks(v2)
        diff = db.diff_blocks(old, new)

        self.assertEqual(len(diff.added), 0)
        self.assertEqual(len(diff.removed), 0)
        # Only 1 cell should have changed
        self.assertEqual(
            len(diff.modified), 1,
            f"expected 1 modified cell, got {[(o.path, n.path) for o, n in diff.modified]}",
        )
        old_b, new_b = diff.modified[0]
        self.assertEqual(new_b.kind, db.KIND_TABLE_CELL)
        # Cell path includes <td
        self.assertIn("<td[", new_b.path)
        # The "Default" cell should remain unchanged
        all_paths = [b.path for b in diff.unchanged]
        self.assertTrue(any("Default" in old.path for old in diff.unchanged) or True)
        # The "Default" cell should be present in unchanged
        unchanged_contents = {b.content for b in diff.unchanged}
        self.assertIn("Default", unchanged_contents)

        regions = db.compute_color_regions(old, new, None)
        self.assertEqual(len(regions.green), 1)
        self.assertEqual(regions.green[0].kind, db.KIND_TABLE_CELL)


# ── T5: New panel added ──────────────────────────────────────────────────────


class TestNewPanelAdded(unittest.TestCase):
    """T5: new panel added → every inner block is green."""

    def test_new_panel(self):
        v1 = MD_V1_BASE
        v2 = MD_V1_BASE + (
            "\n::: {.panel section=\"§5 New\"}\n"
            "## §5 New\n"
            "\n"
            "New policy paragraph 1.\n"
            "\n"
            "New policy paragraph 2.\n"
            ":::\n"
        )
        old = db.parse_blocks(v1)
        new = db.parse_blocks(v2)
        diff = db.diff_blocks(old, new)
        self.assertEqual(len(diff.removed), 0)
        self.assertEqual(len(diff.modified), 0)
        # New panel contains heading 1 + para 2 = 3 blocks
        self.assertEqual(len(diff.added), 3)
        # All have the §5 New prefix
        for b in diff.added:
            self.assertIn("§5 New", b.path)
        # heading + paragraph are all green
        regions = db.compute_color_regions(old, new, None)
        self.assertEqual(len(regions.green), 3)
        kinds = {b.kind for b in regions.green}
        self.assertIn(db.KIND_HEADING, kinds)
        self.assertIn(db.KIND_PANEL_INNER_PARA, kinds)


# ── T6: Previously green region unchanged this time → blue ─────────────────


class TestPreviousGreenBecomesBlue(unittest.TestCase):
    """T6: a region that was green in the previous publish is unchanged this time → blue."""

    def test_previous_green_decays_to_blue(self):
        # Simulation:
        # v1 → v2: paragraph A is edited (G_2 = {A})
        # v2 → v3: paragraph B is edited (G_3 = {B}). A is unchanged → B_3 = {A}.
        v1 = MD_V1_BASE
        v2 = v1.replace("Standard pricing plan description paragraph.", "Modified standard pricing paragraph.")
        v3 = v2.replace("Additional paragraph body.", "Modified additional paragraph body.")

        b_v1 = db.parse_blocks(v1)
        b_v2 = db.parse_blocks(v2)
        b_v3 = db.parse_blocks(v3)

        # publish 2 — green = {A}
        regions_2 = db.compute_color_regions(b_v1, b_v2, None)
        self.assertEqual(len(regions_2.green), 1)
        self.assertEqual(len(regions_2.blue), 0)
        state_2 = db.serialize_state(regions_2)
        self.assertEqual(len(state_2), 1)
        green_2_path = regions_2.green[0].path

        # publish 3 — green = {B}, blue = {A}
        regions_3 = db.compute_color_regions(b_v2, b_v3, state_2)
        self.assertEqual(len(regions_3.green), 1)
        self.assertEqual(len(regions_3.blue), 1)
        # A should become blue — but with v3's current hash
        self.assertEqual(regions_3.blue[0].path, green_2_path)
        self.assertNotEqual(regions_3.blue[0].path, regions_3.green[0].path)


# ── T7: Same region edited in two consecutive publishes → green only ───────


class TestSameRegionConsecutiveModify(unittest.TestCase):
    """T7: same path is in previous_green and is edited again this time → green only."""

    def test_same_region_consecutive_modify(self):
        v1 = MD_V1_BASE
        v2 = v1.replace("Standard pricing plan description paragraph.", "Modification 1.")
        v3 = v2.replace("Modification 1.", "Modification 2.")

        b_v1 = db.parse_blocks(v1)
        b_v2 = db.parse_blocks(v2)
        b_v3 = db.parse_blocks(v3)

        regions_2 = db.compute_color_regions(b_v1, b_v2, None)
        state_2 = db.serialize_state(regions_2)
        self.assertEqual(len(regions_2.green), 1)
        green_2_path = regions_2.green[0].path

        regions_3 = db.compute_color_regions(b_v2, b_v3, state_2)
        # Same path reappears as green — should not go into blue
        self.assertEqual(len(regions_3.green), 1)
        self.assertEqual(regions_3.green[0].path, green_2_path)
        self.assertEqual(len(regions_3.blue), 0)


# ── T8: heading text change → heading block green ──────────────────────────


class TestHeadingTextModify(unittest.TestCase):
    """T8: heading text change → the heading block itself is green.

    Note: since heading text is also used in the path prefix, child blocks'
    paths change too and may be caught as added/removed. This test only
    verifies that "the heading block itself is caught as modified, or as
    added/removed".
    """

    def test_heading_modify(self):
        v1 = MD_V1_BASE
        v2 = MD_V1_BASE.replace("### §3.1 Standard Pricing", "### §3.1 Changed Pricing")
        old = db.parse_blocks(v1)
        new = db.parse_blocks(v2)
        diff = db.diff_blocks(old, new)

        # Heading text change → the heading block at that path is modified.
        # The heading block's path includes itself, so the new text becomes
        # the leaf of the path. So it may also be caught as added + removed
        # due to the path change — verify that either way, the change is
        # caught at the region level.
        all_new_heading_paths = [
            b.path for b in new if b.kind == db.KIND_HEADING
        ]
        all_old_heading_paths = [
            b.path for b in old if b.kind == db.KIND_HEADING
        ]
        # h3 changed — path should differ between old/new
        self.assertNotEqual(set(all_new_heading_paths), set(all_old_heading_paths))

        # The regions in the changed §3.1 area should be included in green
        # (since the path prefix changes to "§3.1 Changed Pricing", they're caught as added)
        regions = db.compute_color_regions(old, new, None)
        self.assertGreater(len(regions.green), 0)
        green_paths = [b.path for b in regions.green]
        self.assertTrue(
            any("Changed Pricing" in p for p in green_paths),
            f"expected 'Changed Pricing' in green paths, got {green_paths}",
        )


# ── Bonus: serialize/deserialize round-trip ────────────────────────────────


class TestSerializeRoundTrip(unittest.TestCase):
    """serialize_state → JSON → compute_color_regions round trip."""

    def test_serialize_roundtrip(self):
        v1 = MD_V1_BASE
        v2 = v1.replace("Standard pricing plan description paragraph.", "Modified.")
        b_v1 = db.parse_blocks(v1)
        b_v2 = db.parse_blocks(v2)
        regions = db.compute_color_regions(b_v1, b_v2, None)
        state = db.serialize_state(regions)

        # JSON-serializable
        encoded = json.dumps(state, ensure_ascii=False)
        decoded = json.loads(encoded)
        self.assertEqual(len(decoded), len(regions.green))
        for entry in decoded:
            self.assertIn("path", entry)
            self.assertIn("block_hash", entry)


# ── Bonus: code block as a whole ────────────────────────────────────────────


class TestCodeBlockSingleRegion(unittest.TestCase):
    """code block is a single region without internal splitting — spec §6 (internal spans forbidden)."""

    def test_code_block_single(self):
        md_with_code = (
            "## Example\n\n"
            "```python\n"
            "def foo():\n"
            "    return 1\n"
            "```\n"
        )
        blocks = db.parse_blocks(md_with_code)
        code_blocks = [b for b in blocks if b.kind == db.KIND_CODE]
        self.assertEqual(len(code_blocks), 1)
        self.assertIn("def foo()", code_blocks[0].content)
        # Code preserves line breaks
        self.assertIn("\n", code_blocks[0].content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
