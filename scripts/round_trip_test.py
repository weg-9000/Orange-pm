#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round-trip 골든 테스트 (Phase 1D).

md_to_storage(storage_to_md(X)) 와 storage_to_md(md_to_storage(Y)) 가
사양 §8 의 보장 범위(정규화 후) 내에서 idempotent 한지 검증한다.

검증 축:
    1. MD → XML 결정성 (동일 MD → sha256 동일)
    2. MD → XML → MD 본문 idempotency (frontmatter publication 제외, 본문만 비교)
    3. XML → MD → XML 핵심 요소 보존 (panel/info/table/code/link)
    4. 실제 templates/confluence-xml/*.xml 변환 정상 (예외 없음, 종료 0)
    5. 중복 emit 부재 (Phase 1C 수정 검증)

stdlib 만 사용, pytest 미사용.
"""
from __future__ import annotations

import hashlib
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from md_to_storage import convert as convert_md  # type: ignore
from storage_to_md import convert_storage  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_XML_DIR = REPO_ROOT / "Planning-Agent-Hub" / "templates" / "confluence-xml"


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _normalize_for_compare(text: str) -> str:
    """비교 위한 정규화: 연속 빈 줄 압축, 양끝 trim, 줄끝 공백 제거."""
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_body(md_text: str) -> str:
    """frontmatter 제거 후 본문만 반환."""
    if not md_text.startswith("---\n"):
        return md_text
    end = md_text.find("\n---\n", 4)
    if end == -1:
        return md_text
    return md_text[end + 5 :]


# ── 1. MD → XML 결정성 (sha256 동일) ───────────────────────────────────────
class TestDeterminism(unittest.TestCase):
    def test_md_to_xml_byte_identical_on_repeat(self):
        md = (
            "---\ntitle: T\n---\n"
            "::: {.panel section=\"§1\"}\n## §1\n\n본문 한 줄\n:::\n"
        )
        xml1 = convert_md(md)
        xml2 = convert_md(md)
        self.assertEqual(_hash(xml1), _hash(xml2))

    def test_md_to_xml_repeated_calls_produce_identical_output(self):
        # 동일 입력 — 호출마다 동일 바이트
        md = "::: {.info}\n메시지\n:::\n"
        outputs = [convert_md(md) for _ in range(3)]
        self.assertEqual(len(set(outputs)), 1, "동일 입력 3회 호출 결과가 다름")

    def test_trailing_blank_lines_become_spacers_per_spec(self):
        # 사양 §5: 빈 줄 → <p><br/></p> spacer
        md = "::: {.info}\n메시지\n:::\n\n\n"
        xml = convert_md(md)
        self.assertIn("<p><br/></p>", xml)


# ── 2. MD → XML → MD 본문 idempotency ─────────────────────────────────────
class TestRoundTripFromMD(unittest.TestCase):
    """본문(frontmatter 제외) 핵심 요소가 round-trip 후에도 보존되는지."""

    def _round_trip(self, md_input: str) -> str:
        xml = convert_md(md_input)
        md_out, _ = convert_storage(xml, extract_frontmatter=False)
        return md_out

    def test_simple_panel_round_trip(self):
        md_in = "::: {.panel section=\"§1 개요\"}\n## §1 개요\n\n본문\n:::\n"
        md_out = self._round_trip(md_in)
        self.assertIn("::: {.panel section=\"§1 개요\"", md_out)
        self.assertIn("## §1 개요", md_out)
        self.assertIn("본문", md_out)
        self.assertIn(":::", md_out)

    def test_panel_with_style_tbd_round_trip(self):
        md_in = "::: {.panel section=\"미결\" style=\"tbd\"}\n내용\n:::\n"
        md_out = self._round_trip(md_in)
        self.assertIn("style=\"tbd\"", md_out)
        self.assertIn("미결", md_out)

    def test_info_callout_round_trip(self):
        md_in = "::: {.info}\n정보 메시지\n:::\n"
        md_out = self._round_trip(md_in)
        self.assertIn("::: {.info}", md_out)
        self.assertIn("정보 메시지", md_out)

    def test_table_round_trip_preserves_cells(self):
        md_in = (
            "| 항목 | 내용 |\n"
            "|---|---|\n"
            "| **목적** | 본 정책서 |\n"
            "| **범위** | 전체 |\n"
        )
        md_out = self._round_trip(md_in)
        self.assertIn("| 항목 |", md_out)
        self.assertIn("**목적**", md_out)
        self.assertIn("본 정책서", md_out)
        self.assertIn("전체", md_out)

    def test_code_block_round_trip_preserves_language_and_body(self):
        md_in = "```python\ndef foo():\n    return 42\n```\n"
        md_out = self._round_trip(md_in)
        self.assertIn("```python", md_out)
        self.assertIn("def foo():", md_out)
        self.assertIn("return 42", md_out)

    def test_page_link_round_trip(self):
        md_in = "참고: [[page:[요구사항] DBaaS]]\n"
        md_out = self._round_trip(md_in)
        self.assertIn("[[page:[요구사항] DBaaS]]", md_out)

    def test_multi_panel_round_trip_preserves_order(self):
        md_in = (
            "::: {.panel section=\"§1\"}\n## §1\n첫 번째\n:::\n\n"
            "::: {.panel section=\"§2\"}\n## §2\n두 번째\n:::\n"
        )
        md_out = self._round_trip(md_in)
        idx_a = md_out.find("§1")
        idx_b = md_out.find("§2")
        self.assertGreater(idx_a, 0)
        self.assertGreater(idx_b, idx_a)
        self.assertIn("첫 번째", md_out)
        self.assertIn("두 번째", md_out)


# ── 3. XML → MD → XML 핵심 요소 보존 ──────────────────────────────────────
class TestRoundTripFromXML(unittest.TestCase):
    """XML 에서 출발한 round-trip — 핵심 매크로/요소가 결과 XML 에도 존재하는지."""

    def _round_trip(self, xml_input: str) -> str:
        md_text, _ = convert_storage(xml_input, extract_frontmatter=False)
        # body 부분만 변환 (frontmatter 없음)
        return convert_md(md_text)

    def test_panel_xml_round_trip_preserves_macro(self):
        xml_in = (
            '<ac:layout><ac:layout-section ac:type="single"><ac:layout-cell>'
            '<ac:structured-macro ac:name="panel" ac:schema-version="1">'
            '<ac:parameter ac:name="title">§1 개요</ac:parameter>'
            '<ac:rich-text-body><h2>§1 개요</h2><p>본문</p></ac:rich-text-body>'
            '</ac:structured-macro>'
            '</ac:layout-cell></ac:layout-section></ac:layout>'
        )
        xml_out = self._round_trip(xml_in)
        self.assertIn('ac:name="panel"', xml_out)
        self.assertIn("§1 개요", xml_out)
        self.assertIn("본문", xml_out)

    def test_info_xml_round_trip_preserves_macro(self):
        xml_in = (
            '<ac:structured-macro ac:name="info" ac:schema-version="1">'
            '<ac:rich-text-body><p>안내</p></ac:rich-text-body>'
            '</ac:structured-macro>'
        )
        xml_out = self._round_trip(xml_in)
        self.assertIn('ac:name="info"', xml_out)
        self.assertIn("안내", xml_out)

    def test_code_xml_round_trip_preserves_cdata(self):
        xml_in = (
            '<ac:structured-macro ac:name="code" ac:schema-version="1">'
            '<ac:parameter ac:name="language">python</ac:parameter>'
            '<ac:plain-text-body><![CDATA[print("x")]]></ac:plain-text-body>'
            '</ac:structured-macro>'
        )
        xml_out = self._round_trip(xml_in)
        self.assertIn('ac:name="code"', xml_out)
        self.assertIn("CDATA", xml_out)
        self.assertIn('print("x")', xml_out)


# ── 4. 실제 fixture XML 변환 정상 ─────────────────────────────────────────
class TestRealWorldFixtures(unittest.TestCase):
    def test_all_confluence_xml_templates_convert_without_error(self):
        if not FIXTURE_XML_DIR.is_dir():
            self.skipTest(f"fixture dir not found: {FIXTURE_XML_DIR}")
        xmls = sorted(FIXTURE_XML_DIR.glob("*.xml"))
        self.assertGreaterEqual(len(xmls), 1, "최소 1개 fixture XML 필요")
        for xml_file in xmls:
            with self.subTest(xml=xml_file.name):
                raw = xml_file.read_text(encoding="utf-8")
                md, state = convert_storage(raw, extract_frontmatter=True)
                self.assertTrue(md.strip(), f"빈 변환 결과: {xml_file.name}")
                # 미지원 매크로는 있을 수 있으나 unsupported_macros 만 기록되고 본문은 보존
                # exit 2 는 main 단계 — 여기서는 변환만 검증

    def test_02_policy_no_duplicate_emission(self):
        """Phase 1C 수정 검증 — frontmatter 흡수된 영역이 본문에 중복 emit 되면 안 됨."""
        xml_file = FIXTURE_XML_DIR / "02-policy.xml"
        if not xml_file.is_file():
            self.skipTest(f"fixture not found: {xml_file}")
        raw = xml_file.read_text(encoding="utf-8")
        md, _ = convert_storage(raw, extract_frontmatter=True)

        # 본 문서는 ... 정의서다 → frontmatter publication.header 에만 (count == 1)
        self.assertEqual(
            md.count("본 문서는"), 1,
            f"중복 emit 발견 ('본 문서는' >1):\n{md[:1000]}"
        )
        # 참고 자료 panel title → frontmatter publication.meta 에만 (count == 1)
        self.assertEqual(
            md.count("참고 자료"), 1,
            f"중복 emit 발견 ('참고 자료' >1):\n{md[:1000]}"
        )
        # 본문에는 ::: {.info} 가 없어야 함 (frontmatter 로 흡수됨)
        body = _extract_body(md)
        self.assertNotIn("::: {.info}", body, "frontmatter header 가 body 에도 emit됨")


# ── 5. 멱등성 추가 검증 (정규화 후 동일) ───────────────────────────────────
class TestIdempotence(unittest.TestCase):
    def test_md_round_trip_idempotent_after_normalization(self):
        """간단한 입력은 2회 round-trip 후 안정 상태에 도달해야 함."""
        md_input = (
            "::: {.panel section=\"§1\"}\n## §1\n\n본문 한 줄\n"
            "\n| A | B |\n|---|---|\n| 1 | 2 |\n:::\n"
        )

        def rt(md: str) -> str:
            xml = convert_md(md)
            md_out, _ = convert_storage(xml, extract_frontmatter=False)
            return _normalize_for_compare(md_out)

        first = rt(md_input)
        second = rt(first + "\n")  # 첫 round-trip 결과를 입력으로
        # 정규화 후 두 결과가 같으면 멱등 (fixed point 도달)
        self.assertEqual(first, second, "round-trip 2회 후에도 변화 발생 (비멱등)")


# ── 실행기 ────────────────────────────────────────────────────────────────
def _run() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (
        TestDeterminism,
        TestRoundTripFromMD,
        TestRoundTripFromXML,
        TestRealWorldFixtures,
        TestIdempotence,
    ):
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    print(f"\n총 {total}개 — PASS {total - failed} / FAIL {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run())
