#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for apply_color_cycling.py (Phase 3C/3F/3G/3H).

Uses only stdlib unittest. 10+ cases.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from apply_color_cycling import (  # type: ignore
    apply_cycling,
    get_color_state,
    _wrap_color,
    _summarize_changes,
    _prepend_summary,
)
from diff_blocks import diff_blocks, parse_blocks, compute_color_regions  # type: ignore


# ── 1. First publish (baseline) ───────────────────────────────────────────
class TestFirstPublish(unittest.TestCase):
    def test_baseline_no_color_no_summary(self):
        md = "::: {.panel section=\"§1\"}\n## §1\nbody\n:::\n"
        state = get_color_state({})
        annotated, new_state, warnings = apply_cycling(md, state)
        # Baseline, so source is unchanged and no color is applied
        self.assertEqual(annotated, md)
        self.assertEqual(new_state["publish_round"], 1)
        self.assertFalse(new_state["baseline"])
        self.assertEqual(new_state["previous_green_regions"], [])
        # No change-summary panel either
        self.assertNotIn("Changes this round", annotated)


# ── 2. No changes (identical content in round 2) ──────────────────────────
class TestUnchanged(unittest.TestCase):
    def test_unchanged_source_no_color_changes(self):
        md = "::: {.panel section=\"§1\"}\n## §1\nbody\n:::\n"
        # Start round 1
        state1 = get_color_state({})
        _, after1, _ = apply_cycling(md, state1)
        # round 2 — identical source
        annotated, new_state, _ = apply_cycling(md, after1)
        self.assertEqual(new_state["publish_round"], 2)
        self.assertEqual(new_state["previous_green_regions"], [])
        # No color span
        self.assertNotIn("{.color-green}", annotated)
        self.assertNotIn("{.color-blue}", annotated)
        # change-summary panel — "no changes" notice
        self.assertIn("No changes", annotated)


# ── 3. Simple paragraph edit → green ──────────────────────────────────────
class TestSimpleModification(unittest.TestCase):
    def test_paragraph_modified_gets_green(self):
        md_v1 = "::: {.panel section=\"§1\"}\n## §1\noriginal body\n:::\n"
        md_v2 = "::: {.panel section=\"§1\"}\n## §1\nmodified body\n:::\n"

        state1 = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state1)
        annotated, new_state, _ = apply_cycling(md_v2, after1)

        self.assertIn("[modified body]{.color-green}", annotated)
        self.assertEqual(new_state["publish_round"], 2)
        # 1 green region stored (paragraph)
        self.assertEqual(len(new_state["previous_green_regions"]), 1)


# ── 4. 2-cycle decay — green → blue → black ─────────────────────────────
class TestTwoCycleDecay(unittest.TestCase):
    def test_previous_green_becomes_blue_when_unchanged(self):
        md_v1 = "::: {.panel section=\"§1\"}\n## §1\noriginal A\n:::\n"
        md_v2 = "::: {.panel section=\"§1\"}\n## §1\nmodified A\n:::\n"
        md_v3 = "::: {.panel section=\"§1\"}\n## §1\nmodified A\n\nnew B\n:::\n"

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state)  # baseline
        _, after2, _ = apply_cycling(md_v2, after1)  # v2 green: "modified A"
        annotated_v3, after3, _ = apply_cycling(md_v3, after2)

        # In v3, "modified A" is unchanged → blue, "new B" is new → green
        self.assertIn("{.color-blue}", annotated_v3)
        self.assertIn("{.color-green}", annotated_v3)
        # Check that "modified A" is wrapped in a blue span
        self.assertTrue(
            "[modified A]{.color-blue}" in annotated_v3
            or "modified A]{.color-blue}" in annotated_v3
        )

    def test_consecutive_modification_stays_green_not_blue(self):
        """Same path modified in two consecutive rounds → green only (no blue)."""
        md_v1 = "::: {.panel section=\"§1\"}\n## §1\nversion 1\n:::\n"
        md_v2 = "::: {.panel section=\"§1\"}\n## §1\nversion 2\n:::\n"
        md_v3 = "::: {.panel section=\"§1\"}\n## §1\nversion 3\n:::\n"

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state)
        _, after2, _ = apply_cycling(md_v2, after1)
        annotated_v3, _, _ = apply_cycling(md_v3, after2)

        # Only "version 3" is green; there should be no blue (same path in both G_2 and G_3)
        self.assertIn("[version 3]{.color-green}", annotated_v3)
        self.assertNotIn("{.color-blue}", annotated_v3)


# ── 5. New panel added → inner blocks green ───────────────────────────────
class TestNewPanel(unittest.TestCase):
    def test_new_panel_all_inner_blocks_green(self):
        md_v1 = "::: {.panel section=\"§1\"}\n## §1\nexisting\n:::\n"
        md_v2 = (
            "::: {.panel section=\"§1\"}\n## §1\nexisting\n:::\n\n"
            "::: {.panel section=\"§2\"}\n## §2\nnew body\n:::\n"
        )

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state)
        annotated, _, _ = apply_cycling(md_v2, after1)

        self.assertIn("[new body]{.color-green}", annotated)
        # Existing §1 body has no color
        self.assertIn("existing", annotated)
        self.assertNotIn("[existing]", annotated)


# ── 6. --color-reset → forced baseline ────────────────────────────────────
class TestColorReset(unittest.TestCase):
    def test_color_reset_forces_baseline_even_if_state_exists(self):
        md_v1 = "::: {.panel section=\"§1\"}\n## §1\nversion 1\n:::\n"
        md_v2 = "::: {.panel section=\"§1\"}\n## §1\nversion 2\n:::\n"

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state)
        annotated, new_state, _ = apply_cycling(md_v2, after1, color_reset=True)

        # --color-reset → no color applied + state = baseline-then-1
        self.assertNotIn("{.color-green}", annotated)
        self.assertNotIn("{.color-blue}", annotated)
        self.assertNotIn("Changes this round", annotated)
        self.assertEqual(new_state["publish_round"], 1)
        self.assertFalse(new_state["baseline"])


# ── 7. D4 meeting-minutes special cycling (blue expires faster) ──────────
class TestMeetingsCycling(unittest.TestCase):
    def test_meetings_clears_blue_keeps_green(self):
        md_v1 = "::: {.panel section=\"§1 R0\"}\nbody v1\n:::\n"
        md_v2 = "::: {.panel section=\"§1 R0\"}\nbody v2\n:::\n"
        md_v3 = "::: {.panel section=\"§1 R0\"}\nbody v2\n\nnew meeting\n:::\n"

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state, deliverable_type="meetings")
        _, after2, _ = apply_cycling(md_v2, after1, deliverable_type="meetings")
        annotated, _, _ = apply_cycling(md_v3, after2, deliverable_type="meetings")

        # D4 special case: in v3, "body v2" is unchanged → would normally be
        # blue, but the meeting-minutes special rule expires blue → no color
        self.assertNotIn("{.color-blue}", annotated)
        # "new meeting" is green
        self.assertIn("[new meeting]{.color-green}", annotated)


# ── 8. Change-summary panel insertion ─────────────────────────────────────
class TestSummaryPanel(unittest.TestCase):
    def test_summary_panel_prepended_with_round_number(self):
        md_v1 = "::: {.panel section=\"§1\"}\noriginal\n:::\n"
        md_v2 = "::: {.panel section=\"§1\"}\nmodified\n:::\n"

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state)
        annotated, _, _ = apply_cycling(md_v2, after1)

        self.assertIn("Changes this round (v2)", annotated)
        self.assertIn("**Modified**", annotated)

    def test_summary_panel_after_frontmatter(self):
        md_v1 = "---\ntitle: T\n---\n::: {.panel section=\"§1\"}\noriginal\n:::\n"
        md_v2 = "---\ntitle: T\n---\n::: {.panel section=\"§1\"}\nmodified\n:::\n"

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state)
        annotated, _, _ = apply_cycling(md_v2, after1)

        # frontmatter stays at the very top, followed by the summary panel
        self.assertTrue(annotated.startswith("---\n"))
        title_idx = annotated.find("title: T")
        summary_idx = annotated.find("Changes this round")
        self.assertGreater(summary_idx, title_idx)


# ── 9. _wrap_color helper ──────────────────────────────────────────────────
class TestWrapColor(unittest.TestCase):
    def test_wrap_basic(self):
        self.assertEqual(_wrap_color("text", "color-green"), "[text]{.color-green}")

    def test_wrap_empty_returns_unchanged(self):
        self.assertEqual(_wrap_color("", "color-green"), "")

    def test_wrap_nested_skipped(self):
        already = "[already]{.color-green}"
        self.assertEqual(_wrap_color(already, "color-blue"), already)


# ── 10. State serialization round-trip ────────────────────────────────────
class TestStateRoundTrip(unittest.TestCase):
    def test_state_json_round_trip(self):
        md_v1 = "::: {.panel section=\"§1\"}\noriginal\n:::\n"
        md_v2 = "::: {.panel section=\"§1\"}\nmodified\n:::\n"

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state)
        # JSON serialization
        serialized = json.dumps(after1, ensure_ascii=False)
        deserialized = json.loads(serialized)
        _, after2, _ = apply_cycling(md_v2, deserialized)
        self.assertEqual(after2["publish_round"], 2)


# ── Runner ─────────────────────────────────────────────────────────────────
def _run() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (
        TestFirstPublish,
        TestUnchanged,
        TestSimpleModification,
        TestTwoCycleDecay,
        TestNewPanel,
        TestColorReset,
        TestMeetingsCycling,
        TestSummaryPanel,
        TestWrapColor,
        TestStateRoundTrip,
    ):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    print(f"\nTotal {total} — PASS {total - failed} / FAIL {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run())
