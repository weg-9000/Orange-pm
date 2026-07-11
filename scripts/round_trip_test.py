#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round-trip golden tests (Phase 1D).

Verifies that md_to_storage(storage_to_md(X)) and
storage_to_md(md_to_storage(Y)) are idempotent within the guarantees of
spec §8 (after normalization).

Verification axes:
    1. MD -> XML determinism (identical MD -> identical sha256)
    2. MD -> XML -> MD body idempotency (excludes frontmatter publication,
       compares body only)
    3. XML -> MD -> XML preservation of key elements (panel/info/table/code/link)
    4. Real templates/confluence-xml/*.xml convert cleanly (no exceptions, exit 0)
    5. No duplicate emission (verifies the Phase 1C fix)

Uses only the stdlib, no pytest.
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
    """Normalize for comparison: collapse consecutive blank lines, trim both ends, strip trailing whitespace."""
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_body(md_text: str) -> str:
    """Return only the body after stripping the frontmatter."""
    if not md_text.startswith("---\n"):
        return md_text
    end = md_text.find("\n---\n", 4)
    if end == -1:
        return md_text
    return md_text[end + 5 :]


# ── 1. MD -> XML determinism (identical sha256) ───────────────────────────
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
        # identical input — same bytes on every call
        md = "::: {.info}\n메시지\n:::\n"
        outputs = [convert_md(md) for _ in range(3)]
        self.assertEqual(len(set(outputs)), 1, "3 calls with identical input produced different results")

    def test_trailing_blank_lines_become_spacers_per_spec(self):
        # spec §5: blank line -> <p><br/></p> spacer
        md = "::: {.info}\n메시지\n:::\n\n\n"
        xml = convert_md(md)
        self.assertIn("<p><br/></p>", xml)


# ── 2. MD -> XML -> MD body idempotency ───────────────────────────────────
class TestRoundTripFromMD(unittest.TestCase):
    """Whether key body elements (excluding frontmatter) survive a round-trip."""

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


# ── 3. XML -> MD -> XML preservation of key elements ──────────────────────
class TestRoundTripFromXML(unittest.TestCase):
    """Round-trip starting from XML — whether key macros/elements survive into the resulting XML."""

    def _round_trip(self, xml_input: str) -> str:
        md_text, _ = convert_storage(xml_input, extract_frontmatter=False)
        # convert only the body part (no frontmatter)
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


# ── 4. Real fixture XML converts cleanly ──────────────────────────────────
class TestRealWorldFixtures(unittest.TestCase):
    def test_all_confluence_xml_templates_convert_without_error(self):
        if not FIXTURE_XML_DIR.is_dir():
            self.skipTest(f"fixture dir not found: {FIXTURE_XML_DIR}")
        xmls = sorted(FIXTURE_XML_DIR.glob("*.xml"))
        self.assertGreaterEqual(len(xmls), 1, "at least 1 fixture XML is required")
        for xml_file in xmls:
            with self.subTest(xml=xml_file.name):
                raw = xml_file.read_text(encoding="utf-8")
                md, state = convert_storage(raw, extract_frontmatter=True)
                self.assertTrue(md.strip(), f"empty conversion result: {xml_file.name}")
                # Unsupported macros may exist, but they're only recorded in
                # unsupported_macros — the body is still preserved.
                # exit 2 belongs to the main stage — only the conversion is verified here.

    def test_02_policy_no_duplicate_emission(self):
        """Verifies the Phase 1C fix — a region absorbed into frontmatter must not be re-emitted in the body."""
        xml_file = FIXTURE_XML_DIR / "02-policy.xml"
        if not xml_file.is_file():
            self.skipTest(f"fixture not found: {xml_file}")
        raw = xml_file.read_text(encoding="utf-8")
        md, _ = convert_storage(raw, extract_frontmatter=True)

        # "본 문서는 ... 정의서다" -> only in frontmatter publication.header (count == 1)
        self.assertEqual(
            md.count("본 문서는"), 1,
            f"duplicate emission found ('본 문서는' appears >1 time):\n{md[:1000]}"
        )
        # "참고 자료" panel title -> only in frontmatter publication.meta (count == 1)
        self.assertEqual(
            md.count("참고 자료"), 1,
            f"duplicate emission found ('참고 자료' appears >1 time):\n{md[:1000]}"
        )
        # the body must not contain ::: {.info} (it was absorbed into frontmatter)
        body = _extract_body(md)
        self.assertNotIn("::: {.info}", body, "the frontmatter header was also emitted in the body")


# ── 5. Additional idempotence check (identical after normalization) ───────
class TestIdempotence(unittest.TestCase):
    def test_md_round_trip_idempotent_after_normalization(self):
        """A simple input should reach a stable state after 2 round-trips."""
        md_input = (
            "::: {.panel section=\"§1\"}\n## §1\n\n본문 한 줄\n"
            "\n| A | B |\n|---|---|\n| 1 | 2 |\n:::\n"
        )

        def rt(md: str) -> str:
            xml = convert_md(md)
            md_out, _ = convert_storage(xml, extract_frontmatter=False)
            return _normalize_for_compare(md_out)

        first = rt(md_input)
        second = rt(first + "\n")  # feed the first round-trip's result back in as input
        # if the two results match after normalization, it's idempotent (reached a fixed point)
        self.assertEqual(first, second, "output still changed after 2 round-trips (not idempotent)")


# ── Runner ──────────────────────────────────────────────────────────────
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
    print(f"\nTotal {total} — PASS {total - failed} / FAIL {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run())
