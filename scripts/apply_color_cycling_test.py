#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_color_cycling.py 테스트 (Phase 3C/3F/3G/3H).

stdlib unittest 만 사용. 10+ 케이스.
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


# ── 1. 첫 publish (baseline) ─────────────────────────────────────────────
class TestFirstPublish(unittest.TestCase):
    def test_baseline_no_color_no_summary(self):
        md = "::: {.panel section=\"§1\"}\n## §1\n본문\n:::\n"
        state = get_color_state({})
        annotated, new_state, warnings = apply_cycling(md, state)
        # baseline 이므로 source 그대로 + 색상 미적용
        self.assertEqual(annotated, md)
        self.assertEqual(new_state["publish_round"], 1)
        self.assertFalse(new_state["baseline"])
        self.assertEqual(new_state["previous_green_regions"], [])
        # 변경 요약 panel 도 없음
        self.assertNotIn("이번 변경 요약", annotated)


# ── 2. 변경 없음 (round 2 에서 동일 내용) ─────────────────────────────────
class TestUnchanged(unittest.TestCase):
    def test_unchanged_source_no_color_changes(self):
        md = "::: {.panel section=\"§1\"}\n## §1\n본문\n:::\n"
        # round 1 시작
        state1 = get_color_state({})
        _, after1, _ = apply_cycling(md, state1)
        # round 2 — 동일 source
        annotated, new_state, _ = apply_cycling(md, after1)
        self.assertEqual(new_state["publish_round"], 2)
        self.assertEqual(new_state["previous_green_regions"], [])
        # 색상 span 없음
        self.assertNotIn("{.color-green}", annotated)
        self.assertNotIn("{.color-blue}", annotated)
        # 변경 요약 panel — "변경 없음" 안내
        self.assertIn("변경 없음", annotated)


# ── 3. 단순 paragraph 수정 → 초록 ────────────────────────────────────────
class TestSimpleModification(unittest.TestCase):
    def test_paragraph_modified_gets_green(self):
        md_v1 = "::: {.panel section=\"§1\"}\n## §1\n원래 본문\n:::\n"
        md_v2 = "::: {.panel section=\"§1\"}\n## §1\n수정된 본문\n:::\n"

        state1 = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state1)
        annotated, new_state, _ = apply_cycling(md_v2, after1)

        self.assertIn("[수정된 본문]{.color-green}", annotated)
        self.assertEqual(new_state["publish_round"], 2)
        # green region 1개 저장됨 (paragraph)
        self.assertEqual(len(new_state["previous_green_regions"]), 1)


# ── 4. 2-cycle decay — green → blue → black ─────────────────────────────
class TestTwoCycleDecay(unittest.TestCase):
    def test_previous_green_becomes_blue_when_unchanged(self):
        md_v1 = "::: {.panel section=\"§1\"}\n## §1\n원래 A\n:::\n"
        md_v2 = "::: {.panel section=\"§1\"}\n## §1\n수정 A\n:::\n"
        md_v3 = "::: {.panel section=\"§1\"}\n## §1\n수정 A\n\n새 B\n:::\n"

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state)  # baseline
        _, after2, _ = apply_cycling(md_v2, after1)  # v2 green: 수정 A
        annotated_v3, after3, _ = apply_cycling(md_v3, after2)

        # v3 에서 "수정 A" 는 변경 없음 → blue, "새 B" 는 신규 → green
        self.assertIn("{.color-blue}", annotated_v3)
        self.assertIn("{.color-green}", annotated_v3)
        # "수정 A" 가 파랑 span 으로 wrap 되었는지
        self.assertTrue(
            "[수정 A]{.color-blue}" in annotated_v3
            or "수정 A]{.color-blue}" in annotated_v3
        )

    def test_consecutive_modification_stays_green_not_blue(self):
        """같은 path 가 두 라운드 연속 수정 → 초록만 (파랑 X)."""
        md_v1 = "::: {.panel section=\"§1\"}\n## §1\n버전 1\n:::\n"
        md_v2 = "::: {.panel section=\"§1\"}\n## §1\n버전 2\n:::\n"
        md_v3 = "::: {.panel section=\"§1\"}\n## §1\n버전 3\n:::\n"

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state)
        _, after2, _ = apply_cycling(md_v2, after1)
        annotated_v3, _, _ = apply_cycling(md_v3, after2)

        # "버전 3" 만 초록, 파랑은 없어야 함 (같은 path 가 G_2 와 G_3 둘 다)
        self.assertIn("[버전 3]{.color-green}", annotated_v3)
        self.assertNotIn("{.color-blue}", annotated_v3)


# ── 5. 신규 panel 추가 → 내부 block 들 초록 ─────────────────────────────
class TestNewPanel(unittest.TestCase):
    def test_new_panel_all_inner_blocks_green(self):
        md_v1 = "::: {.panel section=\"§1\"}\n## §1\n기존\n:::\n"
        md_v2 = (
            "::: {.panel section=\"§1\"}\n## §1\n기존\n:::\n\n"
            "::: {.panel section=\"§2\"}\n## §2\n신규 본문\n:::\n"
        )

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state)
        annotated, _, _ = apply_cycling(md_v2, after1)

        self.assertIn("[신규 본문]{.color-green}", annotated)
        # 기존 §1 본문은 색상 없음
        self.assertIn("기존", annotated)
        self.assertNotIn("[기존]", annotated)


# ── 6. --color-reset → 강제 baseline ────────────────────────────────────
class TestColorReset(unittest.TestCase):
    def test_color_reset_forces_baseline_even_if_state_exists(self):
        md_v1 = "::: {.panel section=\"§1\"}\n## §1\n버전 1\n:::\n"
        md_v2 = "::: {.panel section=\"§1\"}\n## §1\n버전 2\n:::\n"

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state)
        annotated, new_state, _ = apply_cycling(md_v2, after1, color_reset=True)

        # --color-reset → 색상 미적용 + state = baseline-then-1
        self.assertNotIn("{.color-green}", annotated)
        self.assertNotIn("{.color-blue}", annotated)
        self.assertNotIn("이번 변경 요약", annotated)
        self.assertEqual(new_state["publish_round"], 1)
        self.assertFalse(new_state["baseline"])


# ── 7. D4 회의록 특수 cycling (blue 만료 빠르게) ─────────────────────────
class TestMeetingsCycling(unittest.TestCase):
    def test_meetings_clears_blue_keeps_green(self):
        md_v1 = "::: {.panel section=\"§1 R0\"}\n본문 v1\n:::\n"
        md_v2 = "::: {.panel section=\"§1 R0\"}\n본문 v2\n:::\n"
        md_v3 = "::: {.panel section=\"§1 R0\"}\n본문 v2\n\n새 회의\n:::\n"

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state, deliverable_type="meetings")
        _, after2, _ = apply_cycling(md_v2, after1, deliverable_type="meetings")
        annotated, _, _ = apply_cycling(md_v3, after2, deliverable_type="meetings")

        # D4 특수: v3 에서 "본문 v2" 는 unchanged → 일반 케이스라면 blue 이지만
        # 회의록 특수 룰로 blue 만료 → 색상 미적용
        self.assertNotIn("{.color-blue}", annotated)
        # "새 회의" 는 green
        self.assertIn("[새 회의]{.color-green}", annotated)


# ── 8. 변경 요약 panel 삽입 ──────────────────────────────────────────────
class TestSummaryPanel(unittest.TestCase):
    def test_summary_panel_prepended_with_round_number(self):
        md_v1 = "::: {.panel section=\"§1\"}\n원래\n:::\n"
        md_v2 = "::: {.panel section=\"§1\"}\n수정\n:::\n"

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state)
        annotated, _, _ = apply_cycling(md_v2, after1)

        self.assertIn("이번 변경 요약 (v2)", annotated)
        self.assertIn("**수정**", annotated)

    def test_summary_panel_after_frontmatter(self):
        md_v1 = "---\ntitle: T\n---\n::: {.panel section=\"§1\"}\n원래\n:::\n"
        md_v2 = "---\ntitle: T\n---\n::: {.panel section=\"§1\"}\n수정\n:::\n"

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state)
        annotated, _, _ = apply_cycling(md_v2, after1)

        # frontmatter 가 가장 앞에 유지되고 그 뒤 summary panel
        self.assertTrue(annotated.startswith("---\n"))
        title_idx = annotated.find("title: T")
        summary_idx = annotated.find("이번 변경 요약")
        self.assertGreater(summary_idx, title_idx)


# ── 9. _wrap_color 헬퍼 ──────────────────────────────────────────────────
class TestWrapColor(unittest.TestCase):
    def test_wrap_basic(self):
        self.assertEqual(_wrap_color("텍스트", "color-green"), "[텍스트]{.color-green}")

    def test_wrap_empty_returns_unchanged(self):
        self.assertEqual(_wrap_color("", "color-green"), "")

    def test_wrap_nested_skipped(self):
        already = "[이미]{.color-green}"
        self.assertEqual(_wrap_color(already, "color-blue"), already)


# ── 10. State 직렬화 round-trip ─────────────────────────────────────────
class TestStateRoundTrip(unittest.TestCase):
    def test_state_json_round_trip(self):
        md_v1 = "::: {.panel section=\"§1\"}\n원래\n:::\n"
        md_v2 = "::: {.panel section=\"§1\"}\n수정\n:::\n"

        state = get_color_state({})
        _, after1, _ = apply_cycling(md_v1, state)
        # JSON 직렬화
        serialized = json.dumps(after1, ensure_ascii=False)
        deserialized = json.loads(serialized)
        _, after2, _ = apply_cycling(md_v2, deserialized)
        self.assertEqual(after2["publish_round"], 2)


# ── 실행기 ───────────────────────────────────────────────────────────────
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
    print(f"\n총 {total}개 — PASS {total - failed} / FAIL {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run())
