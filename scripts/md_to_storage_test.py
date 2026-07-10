#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md_to_storage.py 단위 테스트 (stdlib unittest).

실행:
    python md_to_storage_test.py
"""
from __future__ import annotations

import hashlib
import io
import sys
import unittest
from pathlib import Path

# 같은 디렉터리의 md_to_storage 를 임포트
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import md_to_storage as mts  # noqa: E402


def _normalize(s: str) -> str:
    """공백·줄바꿈 정규화 — 비교를 견고하게."""
    return "\n".join(line.rstrip() for line in s.splitlines() if line.strip())


class TestBasicPanel(unittest.TestCase):
    """T1: 기본 panel (common style)."""

    def test_basic_panel(self):
        md = (
            "::: {.panel section=\"§1 개요\"}\n"
            "## §1 개요\n"
            "\n"
            "본문 단락.\n"
            ":::\n"
        )
        xml = mts.convert(md)
        # 핵심 요소 존재 확인
        self.assertIn('<ac:layout>', xml)
        self.assertIn('<ac:layout-section ac:type="single">', xml)
        self.assertIn('<ac:structured-macro ac:name="panel"', xml)
        self.assertIn('<ac:parameter ac:name="title">§1 개요</ac:parameter>',
                      xml)
        # 기본 style=common 의 borderColor
        self.assertIn(
            '<ac:parameter ac:name="borderColor">#24FE00</ac:parameter>',
            xml,
        )
        self.assertIn(
            '<ac:parameter ac:name="titleColor">#002FD5</ac:parameter>',
            xml,
        )
        self.assertIn('<h2>§1 개요</h2>', xml)
        self.assertIn('<p>본문 단락.</p>', xml)
        # 후행 spacer 자동 삽입
        self.assertIn(
            '<ac:layout-cell><p><br/></p></ac:layout-cell>',
            xml,
        )


class TestPanelStyleVariant(unittest.TestCase):
    """T2: panel style 변형 (tbd / product)."""

    def test_panel_tbd_style(self):
        md = (
            "::: {.panel section=\"TBD\" style=\"tbd\"}\n"
            "검토 필요.\n"
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
            "::: {.panel section=\"제품\" style=\"product\"}\n"
            "본문.\n"
            ":::\n"
        )
        xml = mts.convert(md)
        self.assertIn(
            '<ac:parameter ac:name="borderColor">#0050E5</ac:parameter>',
            xml,
        )


class TestInfoCallout(unittest.TestCase):
    """T3: Info / Warning 콜아웃 (layout 래퍼 없음)."""

    def test_info_callout(self):
        md = (
            "::: {.info}\n"
            "일반 정보.\n"
            ":::\n"
        )
        xml = mts.convert(md)
        self.assertIn(
            '<ac:structured-macro ac:name="info" ac:schema-version="1">',
            xml,
        )
        self.assertIn('<p>일반 정보.</p>', xml)
        # info 콜아웃은 layout-section 래퍼가 없어야 함 (사양 §7 규칙3)
        # 검증: 콜아웃이 layout-section single 안에 즉시 들어있지 않아야
        # (frontmatter 없으니 본문 흐름)
        # info 매크로 line 이 layout-cell 의 바로 자식이 아닌지는 indent로 확인
        # 간단 어설션: <ac:layout> 직후 첫 매크로가 info여야 함
        self.assertIn(
            '<ac:structured-macro ac:name="info"', xml.split('<ac:layout>')[1]
        )

    def test_warning_callout(self):
        md = "::: {.warning}\n주의.\n:::\n"
        xml = mts.convert(md)
        self.assertIn('<ac:structured-macro ac:name="warning"', xml)

    def test_note_and_tip(self):
        for cls in ("note", "tip"):
            xml = mts.convert(f"::: {{.{cls}}}\n본문.\n:::\n")
            self.assertIn(f'<ac:structured-macro ac:name="{cls}"', xml)


class TestTable(unittest.TestCase):
    """T4: 표 + col-widths directive."""

    def test_table_basic_equal_widths(self):
        md = (
            "| 항목 | 내용 |\n"
            "|---|---|\n"
            "| **목적** | 본 정책 |\n"
            "| 범위 | 전체 |\n"
        )
        xml = mts.convert(md)
        self.assertIn(
            '<table class="relative-table wrapped" style="width: 90%;">',
            xml,
        )
        self.assertIn('<colgroup>', xml)
        # 균등 분배 — 2 col → 50% / 50%
        self.assertIn('<col style="width: 50%;"/>', xml)
        self.assertIn('<th>항목</th>', xml)
        self.assertIn('<th>내용</th>', xml)
        self.assertIn('<td><strong>목적</strong></td>', xml)
        self.assertIn('<td>본 정책</td>', xml)

    def test_table_with_col_widths_directive(self):
        md = (
            "<!-- col-widths: 15%, 85% -->\n"
            "| 항목 | 내용 |\n"
            "|---|---|\n"
            "| 목적 | 정책서 |\n"
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
        # 100 // 3 = 33, remainder 1 → 마지막 34%
        self.assertIn('<col style="width: 33%;"/>', xml)
        self.assertIn('<col style="width: 34%;"/>', xml)


class TestCodeBlock(unittest.TestCase):
    """T5: 코드블록."""

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
        # language 파라미터 없음
        self.assertNotIn('<ac:parameter ac:name="language">', xml)


class TestInlineMacros(unittest.TestCase):
    """T6: 인라인 매크로 (page link, toc, change_history, placeholders)."""

    def test_page_link(self):
        md = "참고: [[page:[정책정의서] DBaaS]]\n"
        xml = mts.convert(md)
        self.assertIn(
            '<ac:link><ri:page ri:content-title="[정책정의서] DBaaS"/></ac:link>',
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
        md = "이 페이지는 {{PRODUCT_NAME}} 의 정본.\n"
        xml = mts.convert(md)
        # 치환 모드 OFF → placeholder 텍스트 그대로
        self.assertIn('{{PRODUCT_NAME}}', xml)

    def test_regular_link(self):
        md = "[문서](https://example.com)\n"
        xml = mts.convert(md)
        self.assertIn('<a href="https://example.com">문서</a>', xml)


class TestFrontmatter(unittest.TestCase):
    """T7: Frontmatter publication 영역 → header/meta 자동 layout."""

    def test_header_info(self):
        md = (
            "---\n"
            "title: \"[정책정의서] X\"\n"
            "publication:\n"
            "  header:\n"
            "    style: info\n"
            "    body: |\n"
            "      **본 문서는 X 의 정책서다.**\n"
            "---\n"
            "본문 시작.\n"
        )
        xml = mts.convert(md)
        self.assertIn('<ac:structured-macro ac:name="info"', xml)
        self.assertIn('<strong>본 문서는 X 의 정책서다.</strong>', xml)

    def test_meta_two_equal(self):
        md = (
            "---\n"
            "title: X\n"
            "publication:\n"
            "  meta:\n"
            "    layout: two_equal\n"
            "    cells:\n"
            "      - panel:\n"
            "          title: \"참고\"\n"
            "          body: |\n"
            "            - 항목1\n"
            "      - change_history: 3\n"
            "---\n"
            "본문.\n"
        )
        xml = mts.convert(md)
        self.assertIn('<ac:layout-section ac:type="two_equal">', xml)
        self.assertIn('<ac:parameter ac:name="title">참고</ac:parameter>', xml)
        self.assertIn('<ac:parameter ac:name="limit">3</ac:parameter>', xml)


class TestDeterminism(unittest.TestCase):
    """T8: 결정성 — 동일 입력 → 동일 바이트 출력 (사양 §9)."""

    def test_same_input_same_hash(self):
        md = (
            "::: {.panel section=\"§A\"}\n"
            "## §A\n"
            "내용 1.\n"
            "\n"
            "| A | B |\n"
            "|---|---|\n"
            "| 1 | 2 |\n"
            ":::\n"
            "\n"
            "::: {.panel section=\"§B\" style=\"product\"}\n"
            "## §B\n"
            "내용 2.\n"
            ":::\n"
        )
        xml1 = mts.convert(md)
        xml2 = mts.convert(md)
        self.assertEqual(xml1, xml2)
        h1 = hashlib.sha256(xml1.encode("utf-8")).hexdigest()
        h2 = hashlib.sha256(xml2.encode("utf-8")).hexdigest()
        self.assertEqual(h1, h2)


class TestExpand(unittest.TestCase):
    """T9: Expand 매크로."""

    def test_expand(self):
        md = (
            "::: {.expand title=\"이력\"}\n"
            "- 2026-05-01: 초안\n"
            "- 2026-05-15: 반영\n"
            ":::\n"
        )
        xml = mts.convert(md)
        self.assertIn(
            '<ac:structured-macro ac:name="expand"', xml
        )
        self.assertIn(
            '<ac:parameter ac:name="title">이력</ac:parameter>', xml
        )
        self.assertIn('<li>2026-05-01: 초안</li>', xml)


class TestSpacingBetweenPanels(unittest.TestCase):
    """T10: panel 사이 자동 spacer (사양 §7)."""

    def test_two_panels_have_spacer_between(self):
        md = (
            "::: {.panel section=\"A\"}\n"
            "내용 A.\n"
            ":::\n"
            "::: {.panel section=\"B\"}\n"
            "내용 B.\n"
            ":::\n"
        )
        xml = mts.convert(md)
        # 패널 사이 + 마지막 후행 — spacer 2개 발생해야 함
        spacer_marker = '<ac:layout-cell><p><br/></p></ac:layout-cell>'
        count = xml.count(spacer_marker)
        self.assertGreaterEqual(
            count, 2, f"spacer 개수 부족: {count}\n--- XML ---\n{xml}"
        )


class TestCodeBlockCDATAEscape(unittest.TestCase):
    """T11: 코드블록 내 ]]> 분할 처리."""

    def test_cdata_close_marker_split(self):
        md = (
            "```\n"
            "var x = ']]>';\n"
            "```\n"
        )
        xml = mts.convert(md)
        # 원본 ]]> 가 그대로 들어가면 CDATA 깨짐 → 분할되어야
        self.assertIn(']]]]><![CDATA[>', xml)


if __name__ == "__main__":
    unittest.main(verbosity=2)
