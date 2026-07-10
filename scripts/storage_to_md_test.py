#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for storage_to_md (사양: publication-syntax.md).

각 매크로/요소 변환 케이스 + 1개 round-trip 케이스.
실행:
    python -m pytest storage_to_md_test.py -q
    python storage_to_md_test.py   # 내장 러너
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


# ── Panel (사양 §3.1) ─────────────────────────────────────────────────────
def test_panel_with_section_default_style_emits_panel_div():
    xml = (
        '<ac:structured-macro ac:name="panel" ac:schema-version="1">'
        '<ac:parameter ac:name="borderColor">#24FE00</ac:parameter>'
        '<ac:parameter ac:name="titleColor">#002FD5</ac:parameter>'
        '<ac:parameter ac:name="titleBGColor">24FE00</ac:parameter>'
        '<ac:parameter ac:name="borderStyle">none</ac:parameter>'
        '<ac:parameter ac:name="title">§1 정책 개요</ac:parameter>'
        "<ac:rich-text-body><h2>§1 정책 개요</h2><p>본문</p></ac:rich-text-body>"
        "</ac:structured-macro>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert '::: {.panel section="§1 정책 개요"}' in md, md
    assert "style=" not in md, "common(기본) style 은 round-trip 시 생략"
    assert "## §1 정책 개요" in md
    assert "본문" in md
    assert ":::" in md


def test_panel_with_product_style():
    xml = (
        '<ac:structured-macro ac:name="panel" ac:schema-version="1">'
        '<ac:parameter ac:name="borderColor">#0050E5</ac:parameter>'
        '<ac:parameter ac:name="title">제품 영역</ac:parameter>'
        "<ac:rich-text-body><p>내용</p></ac:rich-text-body>"
        "</ac:structured-macro>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert 'style="product"' in md, md
    assert 'section="제품 영역"' in md


# ── Info / Warning / Note / Tip (사양 §3.2) ────────────────────────────────
def test_info_macro():
    xml = (
        '<ac:structured-macro ac:name="info" ac:schema-version="1">'
        "<ac:rich-text-body><p>일반 정보성 메시지</p></ac:rich-text-body>"
        "</ac:structured-macro>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "::: {.info}" in md
    assert "일반 정보성 메시지" in md


def test_warning_macro():
    xml = (
        '<ac:structured-macro ac:name="warning" ac:schema-version="1">'
        "<ac:rich-text-body><p>주의</p></ac:rich-text-body>"
        "</ac:structured-macro>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "::: {.warning}" in md
    assert "주의" in md


# ── Expand (사양 §3.3) ───────────────────────────────────────────────────
def test_expand_with_title():
    xml = (
        '<ac:structured-macro ac:name="expand" ac:schema-version="1">'
        '<ac:parameter ac:name="title">상세 변경 이력</ac:parameter>'
        "<ac:rich-text-body><ul><li>v1: 초안</li><li>v2: 보강</li></ul></ac:rich-text-body>"
        "</ac:structured-macro>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert '::: {.expand title="상세 변경 이력"}' in md
    assert "- v1: 초안" in md
    assert "- v2: 보강" in md


# ── Code Block (사양 §3.5) ────────────────────────────────────────────────
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
    assert "    pass" in md  # 들여쓰기 보존


def test_code_macro_no_language():
    xml = (
        '<ac:structured-macro ac:name="code" ac:schema-version="1">'
        '<ac:plain-text-body><![CDATA[plain code]]></ac:plain-text-body>'
        "</ac:structured-macro>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "```\nplain code\n```" in md


# ── Table (사양 §5.1) ─────────────────────────────────────────────────────
def test_simple_table_even_columns_no_directive():
    xml = (
        '<table class="relative-table wrapped">'
        '<colgroup><col style="width: 50%;"/><col style="width: 50%;"/></colgroup>'
        "<thead><tr><th>항목</th><th>내용</th></tr></thead>"
        "<tbody><tr><td>목적</td><td>본 정책서의 목적</td></tr></tbody>"
        "</table>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "| 항목 | 내용 |" in md
    assert "| 목적 | 본 정책서의 목적 |" in md
    assert "col-widths" not in md, "균등 분배는 directive 미생성"


def test_table_uneven_columns_emits_directive():
    xml = (
        '<table class="relative-table wrapped">'
        '<colgroup><col style="width: 15%;"/><col style="width: 85%;"/></colgroup>'
        "<thead><tr><th>항목</th><th>내용</th></tr></thead>"
        "<tbody><tr><td>목적</td><td>본문</td></tr></tbody>"
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


# ── 페이지 링크 (사양 §4.1) ──────────────────────────────────────────────
def test_page_link():
    xml = (
        '<p><ac:link><ri:page ri:content-title="[요구사항 정의서] DBaaS"/></ac:link></p>'
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "[[page:[요구사항 정의서] DBaaS]]" in md


# ── 자동 매크로 (사양 §4.3) ──────────────────────────────────────────────
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


# ── 표준 요소 (사양 §5) ──────────────────────────────────────────────────
def test_headings():
    xml = "<h1>H1</h1><h2>H2</h2><h3>H3</h3>"
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "# H1" in md
    assert "## H2" in md
    assert "### H3" in md


def test_strong_em_inline():
    xml = "<p>이것은 <strong>강조</strong>와 <em>이탤릭</em></p>"
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "**강조**" in md
    assert "*이탤릭*" in md


def test_unordered_list():
    xml = "<ul><li>첫째</li><li>둘째</li></ul>"
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "- 첫째" in md
    assert "- 둘째" in md


def test_ordered_list():
    xml = "<ol><li>하나</li><li>둘</li></ol>"
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "1. 하나" in md
    assert "2. 둘" in md


def test_external_link():
    xml = '<p><a href="https://example.com">예시</a></p>'
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "[예시](https://example.com)" in md


def test_hr_and_blockquote():
    xml = "<hr/><blockquote><p>인용문</p></blockquote>"
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert "---" in md
    assert "> 인용문" in md


# ── Layout 자동 stripping (사양 §7 역방향) ───────────────────────────────
def test_layout_section_single_with_panel_is_stripped():
    xml = (
        '<ac:layout-section ac:type="single"><ac:layout-cell>'
        '<ac:structured-macro ac:name="panel" ac:schema-version="1">'
        '<ac:parameter ac:name="title">§1</ac:parameter>'
        "<ac:rich-text-body><p>본문</p></ac:rich-text-body>"
        "</ac:structured-macro>"
        "</ac:layout-cell></ac:layout-section>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    assert '::: {.panel section="§1"}' in md
    # layout 래퍼는 사라져야 함
    assert "layout-section" not in md
    assert "layout-cell" not in md


def test_spacer_layout_section_ignored():
    xml = (
        '<ac:layout-section ac:type="single"><ac:layout-cell>'
        "<p><br/></p>"
        "</ac:layout-cell></ac:layout-section>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=False)
    # 본문은 없어야 함 (spacer)
    assert md.strip() == "", f"spacer 가 비어있어야 함, got: {md!r}"


# ── Frontmatter 재구성 (사양 §2) ─────────────────────────────────────────
def test_frontmatter_header_extracted_from_first_info_section():
    xml = (
        '<ac:layout>'
        '<ac:layout-section ac:type="single"><ac:layout-cell>'
        '<ac:structured-macro ac:name="info" ac:schema-version="1">'
        "<ac:rich-text-body><p>doc 안내</p></ac:rich-text-body>"
        "</ac:structured-macro>"
        "</ac:layout-cell></ac:layout-section>"
        "</ac:layout>"
    )
    md, _ = convert_storage(xml, extract_frontmatter=True)
    assert md.startswith("---")
    assert "publication:" in md
    assert "header:" in md
    assert "style: info" in md
    # 중복 emit 차단: 본문에 ::: {.info} 가 다시 나오면 안 됨
    assert md.count("doc 안내") == 1, f"중복 emit 발견:\n{md}"
    assert "::: {.info}" not in md, f"frontmatter 흡수된 info 가 본문에도 emit됨:\n{md}"


def test_frontmatter_meta_extracted_skips_body_duplication():
    # meta layout (two_equal) 의 panel/change-history 가 frontmatter 로 흡수되면
    # 본문에 ::: {.panel section="참고"} 가 다시 emit 되면 안 된다.
    xml = (
        '<ac:layout>'
        '<ac:layout-section ac:type="two_equal">'
        '<ac:layout-cell>'
        '<ac:structured-macro ac:name="panel" ac:schema-version="1">'
        '<ac:parameter ac:name="title">참고 자료</ac:parameter>'
        '<ac:rich-text-body><p>관련 링크</p></ac:rich-text-body>'
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
    assert "참고 자료" in md  # frontmatter title
    assert md.count("관련 링크") == 1
    assert "::: {.panel" not in md, f"meta 흡수된 panel 이 본문에도 emit됨:\n{md}"


# ── 미지원 매크로 경고 (CLI 종료 코드 2 트리거) ─────────────────────────
def test_unsupported_macro_records_warning():
    xml = (
        '<ac:structured-macro ac:name="jira" ac:schema-version="1">'
        '<ac:parameter ac:name="key">FOO-1</ac:parameter>'
        "</ac:structured-macro>"
    )
    md, state = convert_storage(xml, extract_frontmatter=False)
    assert "jira" in state.unsupported_macros


# ── 색상 처리 (Phase 3 예약) ─────────────────────────────────────────────
def test_strip_colors_removes_fenced_spans():
    text = "이것은 [변경됨]{.color-green} 텍스트"
    stripped = _strip_color_spans(text)
    assert stripped == "이것은 변경됨 텍스트"


def test_color_spans_to_md_converts_rgb_green():
    text = '<span style="color: rgb(0,176,80)">신규</span> 텍스트'
    md = _color_spans_to_md(text)
    assert "[신규]{.color-green}" in md


def test_color_spans_to_md_converts_rgb_blue():
    text = '<span style="color: rgb(0,80,229)">직전</span>'
    md = _color_spans_to_md(text)
    assert "[직전]{.color-blue}" in md


# ── 색상 span 통합 (Phase 3D — convert_storage 기본 동작) ────────────────
def test_convert_storage_default_converts_xml_span_to_md_fenced_span():
    """기본 모드: XML 의 <span style="color: rgb(...)"> → MD [..]{.color-XXX}"""
    xml = (
        '<p>이전: <span style="color: rgb(0,176,80)">신규 텍스트</span> 이후</p>'
    )
    md, _ = convert_storage(xml, extract_frontmatter=False, strip_colors=False)
    assert "[신규 텍스트]{.color-green}" in md
    # raw XML span 이 남아 있으면 안 됨
    assert "<span" not in md


def test_convert_storage_strip_colors_removes_all_color_markup():
    """strip_colors=True: 색상 정보 완전 제거 (clean MD, diff 비교용)"""
    xml = (
        '<p>이전: <span style="color: rgb(0,176,80)">신규</span> 다음 '
        '<span style="color: rgb(0,80,229)">직전</span> 끝</p>'
    )
    md, _ = convert_storage(xml, extract_frontmatter=False, strip_colors=True)
    assert "신규" in md and "직전" in md
    assert "color-green" not in md and "color-blue" not in md
    assert "<span" not in md


def test_convert_storage_color_span_round_trip_via_md_fenced():
    """XML span → MD fenced span → XML span round-trip 가능 여부"""
    xml = '<p><span style="color: rgb(0,176,80)">변경</span> 텍스트</p>'
    md, _ = convert_storage(xml, extract_frontmatter=False, strip_colors=False)
    # MD 에 fenced span 이 들어 있어야 round-trip 다음 단계(md_to_storage)에서 다시 XML span 으로
    assert "{.color-green}" in md


# ── parse_storage 견고성 ─────────────────────────────────────────────────
def test_parse_empty_string_returns_root():
    root = parse_storage("")
    assert root is not None


def test_parse_nbsp_entity():
    # &nbsp; 는 XML 표준 아님 — 사전 치환되어야 함
    root = parse_storage("<p>A&nbsp;B</p>")
    assert root is not None


def test_parse_invalid_xml_raises():
    try:
        parse_storage("<unclosed>")
    except ValueError:
        return
    raise AssertionError("ValueError 발생해야 함")


# ── Round-trip (사양 §8/§9) ───────────────────────────────────────────────
def test_round_trip_simple_panel():
    """md_to_storage(storage_to_md(X)) ≈ X (정규화 후) — 사양 §9.

    완전 동치 비교는 frontmatter/layout 자동화로 까다로움 → 핵심 요소
    (panel/heading/table/text) 유지 검증.
    """
    # md_to_storage 가 같은 디렉터리에 있어야 함
    try:
        from md_to_storage import convert as md_to_storage_convert
    except ImportError:
        # 환경에 따라 import 실패 가능 — skip
        print("  (skip) md_to_storage import 불가")
        return

    original_md = (
        "::: {.panel section=\"§1 정책 개요\"}\n"
        "## §1 정책 개요\n"
        "\n"
        "본문 단락.\n"
        "\n"
        "| 항목 | 내용 |\n"
        "|---|---|\n"
        "| 목적 | 본 정책서의 목적 |\n"
        ":::\n"
    )
    # MD → XML → MD
    xml = md_to_storage_convert(original_md)
    md2, _ = convert_storage(xml, extract_frontmatter=False)

    # 핵심 요소 보존 검증 (공백/줄바꿈 정규화 후)
    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    n = norm(md2)
    assert "§1 정책 개요" in n
    assert "본문 단락" in n
    assert "목적" in n
    assert "본 정책서의 목적" in n
    assert ".panel" in n
    # heading 보존
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
            "body": {"storage": {"value": "<p>안녕</p>"}},
        }
        snap_path.write_text(_json.dumps(snap), encoding="utf-8")
        rc = cli_main([
            "--input", str(snap_path),
            "--from-snapshot",
            "--output", str(out_path),
        ])
        assert rc == 0
        assert "안녕" in out_path.read_text(encoding="utf-8")


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
        assert rc == 2  # 미지원 매크로


# ── 내장 러너 ───────────────────────────────────────────────────────────
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
    print(f"총 {len(tests)}개 — PASS {passed} / FAIL {len(failed)}")
    if failed:
        for name, msg in failed:
            print(f"  - {name}: {msg}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_run_all())
