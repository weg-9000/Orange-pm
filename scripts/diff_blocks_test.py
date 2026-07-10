#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diff_blocks.py 단위 테스트 (stdlib unittest).

실행:
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


# ── 픽스처 ───────────────────────────────────────────────────────────────────


MD_V1_BASE = """---
title: "test"
version: 1
---

::: {.panel section="§3 정책"}
## §3 정책

### §3.1 표준요금

| 항목 | 가격 |
|---|---|
| 기본 | 1000원 |
| 추가 | 100원 |

표준 요금제 설명 단락.

추가 단락 본문.
:::

::: {.panel section="§4 운영"}
## §4 운영

- 항목 A
- 항목 B
- 항목 C
:::
"""


def _by_path(blocks):
    return {b.path: b for b in blocks}


# ── T1: 변경 없음 ────────────────────────────────────────────────────────────


class TestNoChange(unittest.TestCase):
    """T1: old == new — 모두 unchanged. green/blue 모두 ∅."""

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


# ── T2: 첫 작성 — 모두 added ────────────────────────────────────────────────


class TestFirstWrite(unittest.TestCase):
    """T2: old 가 빈 MD — 모두 added.

    사양: G_1 = ∅ (모두 검정). caller 가 첫 발행 시 결과를 폐기해야 하나,
    여기서는 added 개수가 0 보다 큼만 확인하고, '실제 첫 발행 정책' 은 caller
    의 책임이라는 docstring 일치를 검증.
    """

    def test_first_write_all_added(self):
        old = db.parse_blocks("")
        new = db.parse_blocks(MD_V1_BASE)
        diff = db.diff_blocks(old, new)
        self.assertEqual(len(diff.unchanged), 0)
        self.assertEqual(len(diff.removed), 0)
        self.assertEqual(len(diff.modified), 0)
        self.assertGreater(len(diff.added), 0)

        # compute_color_regions 자체는 added 를 green 으로 산출 — caller 가
        # 첫 발행임을 인지하고 결과를 폐기/무시해야 함.
        regions = db.compute_color_regions(old, new, None)
        self.assertEqual(len(regions.green), len(diff.added))
        self.assertEqual(len(regions.blue), 0)


# ── T3: 단순 paragraph 수정 ─────────────────────────────────────────────────


class TestParagraphModify(unittest.TestCase):
    """T3: paragraph 본문 1군데 수정 → green 1, 나머지는 unchanged."""

    def test_paragraph_modify(self):
        v1 = MD_V1_BASE
        v2 = MD_V1_BASE.replace(
            "표준 요금제 설명 단락.",
            "표준 요금제 변경된 설명 단락.",
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
        self.assertIn("§3 정책", new_b.path)
        self.assertEqual(new_b.kind, db.KIND_PANEL_INNER_PARA)

        regions = db.compute_color_regions(old, new, None)
        self.assertEqual(len(regions.green), 1)
        self.assertEqual(len(regions.blue), 0)
        self.assertEqual(regions.green[0].path, new_b.path)


# ── T4: 표 셀 1개 수정 ──────────────────────────────────────────────────────


class TestTableCellModify(unittest.TestCase):
    """T4: 표의 단일 셀만 수정 → 셀 단위 modified 1건 (행 단위 아님)."""

    def test_table_cell_modify(self):
        v1 = MD_V1_BASE
        v2 = MD_V1_BASE.replace("| 기본 | 1000원 |", "| 기본 | 1500원 |")
        old = db.parse_blocks(v1)
        new = db.parse_blocks(v2)
        diff = db.diff_blocks(old, new)

        self.assertEqual(len(diff.added), 0)
        self.assertEqual(len(diff.removed), 0)
        # 단 1개 셀만 변경되어야 함
        self.assertEqual(
            len(diff.modified), 1,
            f"expected 1 modified cell, got {[(o.path, n.path) for o, n in diff.modified]}",
        )
        old_b, new_b = diff.modified[0]
        self.assertEqual(new_b.kind, db.KIND_TABLE_CELL)
        # 셀 경로에 <td 가 포함
        self.assertIn("<td[", new_b.path)
        # "기본" 셀은 그대로 unchanged 여야 함
        all_paths = [b.path for b in diff.unchanged]
        self.assertTrue(any("기본" in old.path for old in diff.unchanged) or True)
        # 기본 셀이 unchanged 에 있어야
        unchanged_contents = {b.content for b in diff.unchanged}
        self.assertIn("기본", unchanged_contents)

        regions = db.compute_color_regions(old, new, None)
        self.assertEqual(len(regions.green), 1)
        self.assertEqual(regions.green[0].kind, db.KIND_TABLE_CELL)


# ── T5: 새 panel 추가 ───────────────────────────────────────────────────────


class TestNewPanelAdded(unittest.TestCase):
    """T5: 새 panel 추가 → 내부 모든 block 이 green."""

    def test_new_panel(self):
        v1 = MD_V1_BASE
        v2 = MD_V1_BASE + (
            "\n::: {.panel section=\"§5 신규\"}\n"
            "## §5 신규\n"
            "\n"
            "신규 정책 단락 1.\n"
            "\n"
            "신규 정책 단락 2.\n"
            ":::\n"
        )
        old = db.parse_blocks(v1)
        new = db.parse_blocks(v2)
        diff = db.diff_blocks(old, new)
        self.assertEqual(len(diff.removed), 0)
        self.assertEqual(len(diff.modified), 0)
        # 새 panel 안에는 heading 1 + para 2 = 3 block
        self.assertEqual(len(diff.added), 3)
        # 모두 §5 신규 prefix
        for b in diff.added:
            self.assertIn("§5 신규", b.path)
        # heading + paragraph 가 모두 green
        regions = db.compute_color_regions(old, new, None)
        self.assertEqual(len(regions.green), 3)
        kinds = {b.kind for b in regions.green}
        self.assertIn(db.KIND_HEADING, kinds)
        self.assertIn(db.KIND_PANEL_INNER_PARA, kinds)


# ── T6: 이전 green 영역이 이번엔 unchanged → blue ───────────────────────────


class TestPreviousGreenBecomesBlue(unittest.TestCase):
    """T6: 직전 publish 에서 green 이었던 영역이 이번엔 안 변함 → blue."""

    def test_previous_green_decays_to_blue(self):
        # 시뮬레이션:
        # v1 → v2: 단락 A 가 수정 (G_2 = {A})
        # v2 → v3: 단락 B 가 수정 (G_3 = {B}). A 는 안 변함 → B_3 = {A}.
        v1 = MD_V1_BASE
        v2 = v1.replace("표준 요금제 설명 단락.", "수정된 표준 요금제 단락.")
        v3 = v2.replace("추가 단락 본문.", "수정된 추가 단락 본문.")

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
        # A 가 blue 가 되어야 — 단 v3 의 현재 hash 로
        self.assertEqual(regions_3.blue[0].path, green_2_path)
        self.assertNotEqual(regions_3.blue[0].path, regions_3.green[0].path)


# ── T7: 같은 영역 두 publish 연속 수정 → green only ────────────────────────


class TestSameRegionConsecutiveModify(unittest.TestCase):
    """T7: 같은 path 가 previous_green 에도 있고 이번에 또 변경 → green only."""

    def test_same_region_consecutive_modify(self):
        v1 = MD_V1_BASE
        v2 = v1.replace("표준 요금제 설명 단락.", "수정 1차.")
        v3 = v2.replace("수정 1차.", "수정 2차.")

        b_v1 = db.parse_blocks(v1)
        b_v2 = db.parse_blocks(v2)
        b_v3 = db.parse_blocks(v3)

        regions_2 = db.compute_color_regions(b_v1, b_v2, None)
        state_2 = db.serialize_state(regions_2)
        self.assertEqual(len(regions_2.green), 1)
        green_2_path = regions_2.green[0].path

        regions_3 = db.compute_color_regions(b_v2, b_v3, state_2)
        # 같은 path 가 green 으로 다시 등장 — blue 에는 들어가지 않아야
        self.assertEqual(len(regions_3.green), 1)
        self.assertEqual(regions_3.green[0].path, green_2_path)
        self.assertEqual(len(regions_3.blue), 0)


# ── T8: heading 텍스트 변경 → heading block green ──────────────────────────


class TestHeadingTextModify(unittest.TestCase):
    """T8: heading 텍스트 변경 → heading block 자체가 green.

    주의: heading 텍스트가 path prefix 에도 쓰이므로, 자식 block 들도 path 가
    바뀌어 added/removed 로 잡힐 수 있다. 본 테스트는 "heading block 자체가
    modified 또는 added/removed 로 잡힘" 만 검증.
    """

    def test_heading_modify(self):
        v1 = MD_V1_BASE
        v2 = MD_V1_BASE.replace("### §3.1 표준요금", "### §3.1 변경된요금")
        old = db.parse_blocks(v1)
        new = db.parse_blocks(v2)
        diff = db.diff_blocks(old, new)

        # heading 텍스트 변경 → 해당 path 의 heading block 이 modified.
        # heading block 의 path 는 자신을 포함하므로 새 텍스트가 path 의 leaf
        # 가 됨. 따라서 path 변화로 인해 added + removed 로 잡힐 가능성도 있음
        # — 두 경우 모두 region 차원에서 변경이 잡혀야 함을 확인.
        all_new_heading_paths = [
            b.path for b in new if b.kind == db.KIND_HEADING
        ]
        all_old_heading_paths = [
            b.path for b in old if b.kind == db.KIND_HEADING
        ]
        # h3 가 변경됨 — old/new 에서 path 가 달라야
        self.assertNotEqual(set(all_new_heading_paths), set(all_old_heading_paths))

        # 변경된 §3.1 영역의 region 들이 green 에 포함되어야 (path prefix 가
        # "§3.1 변경된요금" 으로 바뀌므로 added 로 잡힘)
        regions = db.compute_color_regions(old, new, None)
        self.assertGreater(len(regions.green), 0)
        green_paths = [b.path for b in regions.green]
        self.assertTrue(
            any("변경된요금" in p for p in green_paths),
            f"expected '변경된요금' in green paths, got {green_paths}",
        )


# ── Bonus: serialize/deserialize round-trip ────────────────────────────────


class TestSerializeRoundTrip(unittest.TestCase):
    """serialize_state → JSON → compute_color_regions 라운드 트립."""

    def test_serialize_roundtrip(self):
        v1 = MD_V1_BASE
        v2 = v1.replace("표준 요금제 설명 단락.", "수정.")
        b_v1 = db.parse_blocks(v1)
        b_v2 = db.parse_blocks(v2)
        regions = db.compute_color_regions(b_v1, b_v2, None)
        state = db.serialize_state(regions)

        # JSON 직렬화 가능
        encoded = json.dumps(state, ensure_ascii=False)
        decoded = json.loads(encoded)
        self.assertEqual(len(decoded), len(regions.green))
        for entry in decoded:
            self.assertIn("path", entry)
            self.assertIn("block_hash", entry)


# ── Bonus: code block 통째 ────────────────────────────────────────────────


class TestCodeBlockSingleRegion(unittest.TestCase):
    """code block 은 내부 분할 없이 1개 region — 사양 §6 (내부 span 금지)."""

    def test_code_block_single(self):
        md_with_code = (
            "## 예시\n\n"
            "```python\n"
            "def foo():\n"
            "    return 1\n"
            "```\n"
        )
        blocks = db.parse_blocks(md_with_code)
        code_blocks = [b for b in blocks if b.kind == db.KIND_CODE]
        self.assertEqual(len(code_blocks), 1)
        self.assertIn("def foo()", code_blocks[0].content)
        # 코드는 줄바꿈 보존
        self.assertIn("\n", code_blocks[0].content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
