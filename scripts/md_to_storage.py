#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown → Confluence Storage Format(XHTML) 결정적 변환기.

본 모듈은 publication-targeted MD(단일 SSoT)를 Confluence storage format XML 로
변환한다. 사양 SSoT는 ``orange-pm-plugin/skills/render/publication-syntax.md`` 다.
구현은 정규식 + 미니 상태머신(외부 MD 라이브러리 없음)으로 결정성·재현성을 보장
한다 (동일 MD → 동일 바이트 XML, §9).

지원 입력 구문 (사양 §3-§6):
    1. Frontmatter (YAML)
        - title / wo_id / type / layer / version / last_updated
        - publication.header   : info macro (style/body)
        - publication.meta     : layout(single|two_equal|three_equal) + cells
        - publication.color_state (Phase 3 — pass-through)
    2. Fenced div 블록
        - ``::: {.panel section="..." [style="common|product|tbd|warning|info"]}``
            → layout-section single + panel macro (자동 spacer 후행)
        - ``::: {.info|.warning|.note|.tip}`` → 단순 콜아웃 매크로
        - ``::: {.expand title="..."}`` → expand 매크로
    3. 표준 MD
        - 헤딩 h1~h6, **bold**/_em_, ul/ol/li, blockquote, hr, paragraph
        - 표: relative-table wrapped, colgroup 균등 분배(기본) +
              ``<!-- col-widths: 15%, 85% -->`` directive 지원
        - 코드블록: structured-macro code + plain-text-body CDATA
    4. 인라인 매크로
        - ``[[page:Title]]`` → ac:link + ri:page
        - ``{{toc}}`` / ``{{change_history N}}`` → structured-macro
        - ``[text](url)`` → ``<a href="url">``
        - ``{{PLACEHOLDER}}`` (PRODUCT_NAME/DOC_ID/VERSION/DATE 등) — 텍스트 그대로

Phase 3 예약 (placeholder만, 본 단계는 텍스트 통과):
    - 색상 span ``[text]{.color-green}`` / ``{.color-blue}``

CLI:
    python md_to_storage.py --input X.md --output X.xml \
        [--style-substitute] [--validate]

exit code:
    0 = 성공
    1 = MD 파싱 실패
    2 = Lint FAIL (--validate 시)
    3 = I/O 오류
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml  # PyYAML 6.0.x 가정 (stdlib 외 유일 의존)
except Exception:  # pragma: no cover - PyYAML 부재 시 frontmatter fallback
    yaml = None  # type: ignore[assignment]


# ── 상수 / 매핑 ───────────────────────────────────────────────────────────────

# 사양 §3.1 — panel style 매핑 (style 값 → 파라미터 dict)
PANEL_STYLE_MAP: dict[str, dict[str, str]] = {
    "common":  {"borderColor": "#24FE00", "titleColor": "#002FD5",
                "titleBGColor": "24FE00", "borderStyle": "none"},
    "product": {"borderColor": "#0050E5", "titleColor": "#FFFFFF",
                "titleBGColor": "0050E5", "borderStyle": "none"},
    "tbd":     {"borderColor": "#FF4D4F", "titleColor": "#FFFFFF",
                "titleBGColor": "FF4D4F", "borderStyle": "none"},
    "warning": {"borderColor": "#FAAD14", "titleColor": "#FFFFFF",
                "titleBGColor": "FAAD14", "borderStyle": "none"},
    "info":    {"borderColor": "#1890FF", "titleColor": "#FFFFFF",
                "titleBGColor": "1890FF", "borderStyle": "none"},
}

# 사양 §6 — 색상 span (Phase 3 예약, 본 단계는 텍스트 통과)
COLOR_SPAN_MAP: dict[str, str] = {
    "color-green": "rgb(0,176,80)",
    "color-blue":  "rgb(0,80,229)",
}

CALLOUT_CLASSES = {"info", "warning", "note", "tip"}
LAYOUT_TYPES = {"single", "two_equal", "three_equal"}

INDENT = "  "

# ── 정규식 ────────────────────────────────────────────────────────────────────

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FENCED_DIV_OPEN_RE = re.compile(r"^:::\s*\{([^}]+)\}\s*$")
FENCED_DIV_CLOSE_RE = re.compile(r"^:::\s*$")
CODE_FENCE_RE = re.compile(r"^```\s*([\w+\-]*)\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
HR_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
UL_RE = re.compile(r"^(\s*)[-*+]\s+(.+)$")
OL_RE = re.compile(r"^(\s*)\d+\.\s+(.+)$")
BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
COLWIDTHS_DIRECTIVE_RE = re.compile(
    r"^\s*<!--\s*col-widths\s*:\s*([^>]+?)\s*-->\s*$"
)

# Inline patterns — applied in defined order
PAGE_LINK_RE = re.compile(r"\[\[page:(.+?)\]\](?!\])")
CHANGE_HISTORY_RE = re.compile(r"\{\{change_history\s+(\d+)\}\}")
TOC_RE = re.compile(r"\{\{toc\}\}")
COLOR_SPAN_RE = re.compile(r"\[([^\[\]]+)\]\{\.(color-[a-z]+)\}")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
STRONG_RE = re.compile(r"\*\*([^*\n]+)\*\*")
EM_RE = re.compile(r"(?<![\*\w])\*([^*\n]+)\*(?!\*)")

# Fenced-div attribute parsing: class tokens (.foo) and key="value"
ATTR_CLASS_RE = re.compile(r"\.([\w\-]+)")
ATTR_KV_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


# ── Frontmatter ──────────────────────────────────────────────────────────────


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """YAML frontmatter 파싱 → (dict, body). 없으면 ({}, text).

    PyYAML 부재 시 매우 한정적 fallback (top-level scalar only).
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    body = text[m.end():]
    fm_text = m.group(1)
    if yaml is not None:
        try:
            data = yaml.safe_load(fm_text) or {}
            if not isinstance(data, dict):
                return {}, body
            return data, body
        except Exception:
            return {}, body
    # fallback — naive line parser (top-level scalars only)
    out: dict = {}
    for line in fm_text.splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        if line.startswith(" ") or line.startswith("\t"):
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out, body


# ── XML escape ───────────────────────────────────────────────────────────────


def _xml_escape(text: str) -> str:
    """XML 텍스트 escape (& < > 만; "는 속성에서 별도 처리)."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _xml_attr_escape(text: str) -> str:
    """XML 속성 값 escape (& < > " ')."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ── Inline conversion (text → XHTML inline string) ──────────────────────────


def _convert_inline(text: str) -> str:
    """인라인 변환: 매크로 → 링크 → strong → em 순서로 적용.

    매크로는 원본 텍스트에 placeholder(\\x00..\\x00) 로 보존 후 escape 회피.
    """
    placeholders: list[str] = []

    def _ph(xml: str) -> str:
        placeholders.append(xml)
        return f"\x00PH{len(placeholders) - 1}\x00"

    # 1. page link
    def _page_repl(m: re.Match) -> str:
        title = m.group(1).strip()
        return _ph(f'<ac:link><ri:page ri:content-title="{_xml_attr_escape(title)}"/></ac:link>')
    text = PAGE_LINK_RE.sub(_page_repl, text)

    # 2. change_history (먼저 — toc 가 substring match 하지 않도록)
    def _ch_repl(m: re.Match) -> str:
        n = m.group(1)
        return _ph(
            '<ac:structured-macro ac:name="change-history" ac:schema-version="1">'
            f'<ac:parameter ac:name="limit">{n}</ac:parameter>'
            '</ac:structured-macro>'
        )
    text = CHANGE_HISTORY_RE.sub(_ch_repl, text)

    # 3. toc
    text = TOC_RE.sub(
        lambda m: _ph('<ac:structured-macro ac:name="toc" ac:schema-version="1"/>'),
        text,
    )

    # 4. 색상 span (Phase 3 — 본 단계는 text pass-through; 사양 §6 hex 사용)
    def _color_repl(m: re.Match) -> str:
        inner, cls = m.group(1), m.group(2)
        color = COLOR_SPAN_MAP.get(cls)
        if color is None:
            return m.group(0)  # 미정의 클래스는 원문 보존
        return _ph(f'<span style="color: {color}">{_xml_escape(inner)}</span>')
    text = COLOR_SPAN_RE.sub(_color_repl, text)

    # 5. 일반 링크 [text](url)
    def _link_repl(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        return _ph(f'<a href="{_xml_attr_escape(url)}">{_xml_escape(label)}</a>')
    text = LINK_RE.sub(_link_repl, text)

    # 6. XML escape (placeholder 마커는 \x00 이므로 영향 없음)
    text = _xml_escape(text)

    # 7. strong / em
    text = STRONG_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", text)
    text = EM_RE.sub(lambda m: f"<em>{m.group(1)}</em>", text)

    # 8. placeholder 복원
    def _restore(m: re.Match) -> str:
        idx = int(m.group(1))
        return placeholders[idx]
    text = re.sub(r"\x00PH(\d+)\x00", _restore, text)

    return text


# ── Block-level conversion ──────────────────────────────────────────────────


class _Line:
    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


def _split_table_row(line: str) -> list[str]:
    """| a | b | → ['a', 'b'] (전후 공백·외곽 | 제거)."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _parse_col_widths(directive: str) -> list[str]:
    """'15%, 85%' → ['15%', '85%']."""
    return [w.strip() for w in directive.split(",") if w.strip()]


def _render_table(
    header: list[str],
    rows: list[list[str]],
    col_widths: list[str] | None,
    indent: int,
) -> list[str]:
    """표 XHTML 렌더링 (사양 §5, §5.1)."""
    n_cols = len(header) if header else (len(rows[0]) if rows else 0)
    if n_cols == 0:
        return []
    if col_widths and len(col_widths) == n_cols:
        widths = col_widths
    else:
        # 균등 분배 — 100 / n (정수 보장 위해 마지막 칸 보정)
        base = 100 // n_cols
        widths = [f"{base}%"] * n_cols
        # remainder 보정: 마지막 컬럼에 잔여
        remainder = 100 - base * n_cols
        if remainder:
            widths[-1] = f"{base + remainder}%"

    ind = INDENT * indent
    out: list[str] = []
    out.append(
        f'{ind}<table class="relative-table wrapped" style="width: 90%;">'
    )
    out.append(f"{ind}{INDENT}<colgroup>")
    for w in widths:
        out.append(f'{ind}{INDENT * 2}<col style="width: {w};"/>')
    out.append(f"{ind}{INDENT}</colgroup>")
    if header:
        out.append(f"{ind}{INDENT}<thead>")
        out.append(f"{ind}{INDENT * 2}<tr>")
        for cell in header:
            out.append(f"{ind}{INDENT * 3}<th>{_convert_inline(cell)}</th>")
        out.append(f"{ind}{INDENT * 2}</tr>")
        out.append(f"{ind}{INDENT}</thead>")
    if rows:
        out.append(f"{ind}{INDENT}<tbody>")
        for row in rows:
            # 셀 수 부족 시 빈 셀로 패딩
            padded = row + [""] * (n_cols - len(row))
            out.append(f"{ind}{INDENT * 2}<tr>")
            for cell in padded[:n_cols]:
                out.append(f"{ind}{INDENT * 3}<td>{_convert_inline(cell)}</td>")
            out.append(f"{ind}{INDENT * 2}</tr>")
        out.append(f"{ind}{INDENT}</tbody>")
    out.append(f"{ind}</table>")
    return out


def _render_code_block(language: str, content: str, indent: int) -> list[str]:
    """코드블록 → ac:structured-macro code + CDATA (사양 §3.5)."""
    ind = INDENT * indent
    out = [f'{ind}<ac:structured-macro ac:name="code" ac:schema-version="1">']
    if language:
        out.append(
            f'{ind}{INDENT}<ac:parameter ac:name="language">'
            f'{_xml_escape(language)}</ac:parameter>'
        )
    # CDATA — 내용 안에 ]]> 있을 시 분할
    safe = content.replace("]]>", "]]]]><![CDATA[>")
    out.append(
        f'{ind}{INDENT}<ac:plain-text-body><![CDATA[{safe}]]></ac:plain-text-body>'
    )
    out.append(f"{ind}</ac:structured-macro>")
    return out


def _render_list(items: list[tuple[int, str, str]], indent: int) -> list[str]:
    """리스트 렌더링.

    items: [(depth_level, ordered_tag, text), ...]  depth_level 0=top.
    동일 depth/태그 연속을 하나의 <ul>/<ol>로 묶고, 더 깊은 들여쓰기는 재귀 nest.
    """
    out: list[str] = []
    _render_list_recursive(items, 0, 0, indent, out)
    return out


def _render_list_recursive(
    items: list[tuple[int, str, str]],
    start: int,
    depth: int,
    indent: int,
    out: list[str],
) -> int:
    """items[start:] 에서 depth==depth 인 연속을 처리. 처리한 마지막 인덱스+1 반환."""
    if start >= len(items):
        return start
    ind = INDENT * indent
    tag = items[start][1]
    out.append(f"{ind}<{tag}>")
    i = start
    while i < len(items):
        d, t, text = items[i]
        if d < depth or (d == depth and t != tag):
            break
        if d > depth:
            # 깊은 항목 — 직전 <li> 닫기 전에 nested list 삽입
            # 가장 가까운 li 의 닫는 태그를 제거하고 nested 리스트 + 재닫기
            if out and out[-1].endswith("</li>"):
                last = out.pop()
                # last 형식: f"{ind}{INDENT}<li>...</li>"  → "</li>" 떼고 추가
                base = last[:-5]  # remove '</li>'
                out.append(base)
            i = _render_list_recursive(items, i, d, indent + 2, out)
            if out:
                out.append(f"{ind}{INDENT}</li>")
            continue
        out.append(f"{ind}{INDENT}<li>{_convert_inline(text)}</li>")
        i += 1
    out.append(f"{ind}</{tag}>")
    return i


def _convert_block_lines(lines: list[str], indent: int) -> list[str]:
    """블록 라인 리스트 → XHTML 라인 리스트 (fenced div 제외, 그 내부에서만 호출).

    Pure block-level converter. 코드블록 / 표 / 리스트 / blockquote / heading /
    hr / paragraph 만 처리. fenced div 는 상위 _convert_body 에서 분기.
    """
    out: list[str] = []
    i = 0
    n = len(lines)
    pending_col_widths: list[str] | None = None
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # col-widths directive — 다음 table 에 적용
        cw = COLWIDTHS_DIRECTIVE_RE.match(line)
        if cw:
            pending_col_widths = _parse_col_widths(cw.group(1))
            i += 1
            continue

        # 빈 줄 → spacer (사양 §5: 빈 줄 → <p><br/></p>)
        if not stripped:
            out.append(f"{INDENT * indent}<p><br/></p>")
            i += 1
            continue

        # 코드 fence
        cf = CODE_FENCE_RE.match(line)
        if cf:
            lang = cf.group(1)
            content_lines: list[str] = []
            i += 1
            while i < n and not CODE_FENCE_RE.match(lines[i]):
                content_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1  # consume closing fence
            out.extend(
                _render_code_block(lang, "\n".join(content_lines), indent)
            )
            continue

        # heading
        h = HEADING_RE.match(line)
        if h:
            level = len(h.group(1))
            text = h.group(2).strip()
            out.append(
                f"{INDENT * indent}<h{level}>{_convert_inline(text)}</h{level}>"
            )
            i += 1
            continue

        # hr
        if HR_RE.match(line):
            out.append(f"{INDENT * indent}<hr/>")
            i += 1
            continue

        # 표
        if "|" in line and i + 1 < n and TABLE_SEPARATOR_RE.match(lines[i + 1]):
            header = _split_table_row(line)
            i += 2  # skip header + separator
            rows: list[list[str]] = []
            while i < n and "|" in lines[i] and lines[i].strip():
                if TABLE_SEPARATOR_RE.match(lines[i]):
                    break
                rows.append(_split_table_row(lines[i]))
                i += 1
            out.extend(
                _render_table(header, rows, pending_col_widths, indent)
            )
            pending_col_widths = None
            continue

        # 리스트
        ul = UL_RE.match(line)
        ol = OL_RE.match(line)
        if ul or ol:
            items: list[tuple[int, str, str]] = []
            while i < n:
                m_ul = UL_RE.match(lines[i])
                m_ol = OL_RE.match(lines[i])
                if not m_ul and not m_ol:
                    if not lines[i].strip():
                        # 빈 줄로 리스트 종료
                        break
                    break
                m = m_ul or m_ol
                indent_ws = m.group(1)
                depth_level = len(indent_ws) // 2
                tag = "ul" if m_ul else "ol"
                items.append((depth_level, tag, m.group(2)))
                i += 1
            out.extend(_render_list(items, indent))
            continue

        # blockquote
        bq = BLOCKQUOTE_RE.match(line)
        if bq:
            bq_lines: list[str] = [bq.group(1)]
            i += 1
            while i < n:
                m_bq = BLOCKQUOTE_RE.match(lines[i])
                if not m_bq:
                    break
                bq_lines.append(m_bq.group(1))
                i += 1
            ind = INDENT * indent
            out.append(f"{ind}<blockquote>")
            for bl in bq_lines:
                if bl.strip():
                    out.append(f"{ind}{INDENT}<p>{_convert_inline(bl)}</p>")
                else:
                    out.append(f"{ind}{INDENT}<p><br/></p>")
            out.append(f"{ind}</blockquote>")
            continue

        # paragraph — 빈 줄까지 누적
        para_lines: list[str] = [stripped]
        i += 1
        while i < n:
            nxt = lines[i]
            if not nxt.strip():
                break
            # 다른 블록의 시작이면 stop
            if (HEADING_RE.match(nxt) or HR_RE.match(nxt)
                    or CODE_FENCE_RE.match(nxt) or UL_RE.match(nxt)
                    or OL_RE.match(nxt) or BLOCKQUOTE_RE.match(nxt)
                    or FENCED_DIV_OPEN_RE.match(nxt)
                    or FENCED_DIV_CLOSE_RE.match(nxt)
                    or COLWIDTHS_DIRECTIVE_RE.match(nxt)):
                break
            # 표 시작?
            if ("|" in nxt and i + 1 < n
                    and TABLE_SEPARATOR_RE.match(lines[i + 1])):
                break
            para_lines.append(nxt.strip())
            i += 1
        para = " ".join(para_lines)
        out.append(f"{INDENT * indent}<p>{_convert_inline(para)}</p>")
    return out


# ── Fenced div parsing ──────────────────────────────────────────────────────


def _parse_div_attrs(attr_text: str) -> tuple[list[str], dict[str, str]]:
    """'.panel section="X" style="tbd"' → (['panel'], {section:X, style:tbd})."""
    classes = ATTR_CLASS_RE.findall(attr_text)
    kvs = dict(ATTR_KV_RE.findall(attr_text))
    return classes, kvs


def _emit_panel(
    section: str,
    style: str,
    inner_lines: list[str],
    indent: int,
) -> list[str]:
    """Panel 매크로 → layout-section single + cell wrap (사양 §3.1, §7)."""
    style_params = PANEL_STYLE_MAP.get(style, PANEL_STYLE_MAP["common"])
    ind = INDENT * indent
    out: list[str] = []
    out.append(f'{ind}<ac:layout-section ac:type="single">')
    out.append(f"{ind}{INDENT}<ac:layout-cell>")
    out.append(
        f'{ind}{INDENT * 2}<ac:structured-macro ac:name="panel"'
        f' ac:schema-version="1">'
    )
    # 파라미터 — 사양 §9 (속성 알파벳 순) 준수 위해 정렬
    # panel 파라미터 자체는 결정성 위해 정렬된 키 순서로 emit
    for key in sorted(style_params.keys()):
        out.append(
            f'{ind}{INDENT * 3}<ac:parameter ac:name="{key}">'
            f'{_xml_escape(style_params[key])}</ac:parameter>'
        )
    out.append(
        f'{ind}{INDENT * 3}<ac:parameter ac:name="title">'
        f'{_xml_escape(section)}</ac:parameter>'
    )
    out.append(f"{ind}{INDENT * 3}<ac:rich-text-body>")
    body_lines = _convert_block_lines(inner_lines, indent + 4)
    out.extend(body_lines)
    out.append(f"{ind}{INDENT * 3}</ac:rich-text-body>")
    out.append(f"{ind}{INDENT * 2}</ac:structured-macro>")
    out.append(f"{ind}{INDENT}</ac:layout-cell>")
    out.append(f"{ind}</ac:layout-section>")
    return out


def _emit_spacer(indent: int) -> list[str]:
    """Panel 간 자동 spacer (사양 §7)."""
    ind = INDENT * indent
    return [
        f'{ind}<ac:layout-section ac:type="single">',
        f"{ind}{INDENT}<ac:layout-cell><p><br/></p></ac:layout-cell>",
        f"{ind}</ac:layout-section>",
    ]


def _emit_callout(name: str, inner_lines: list[str], indent: int) -> list[str]:
    """info/warning/note/tip → 단순 macro (사양 §3.2). layout 래퍼 없음."""
    ind = INDENT * indent
    out = [
        f'{ind}<ac:structured-macro ac:name="{name}" ac:schema-version="1">',
        f"{ind}{INDENT}<ac:rich-text-body>",
    ]
    out.extend(_convert_block_lines(inner_lines, indent + 2))
    out.append(f"{ind}{INDENT}</ac:rich-text-body>")
    out.append(f"{ind}</ac:structured-macro>")
    return out


def _emit_expand(title: str, inner_lines: list[str], indent: int) -> list[str]:
    """Expand 매크로 (사양 §3.3)."""
    ind = INDENT * indent
    out = [
        f'{ind}<ac:structured-macro ac:name="expand" ac:schema-version="1">',
        f'{ind}{INDENT}<ac:parameter ac:name="title">'
        f'{_xml_escape(title)}</ac:parameter>',
        f"{ind}{INDENT}<ac:rich-text-body>",
    ]
    out.extend(_convert_block_lines(inner_lines, indent + 2))
    out.append(f"{ind}{INDENT}</ac:rich-text-body>")
    out.append(f"{ind}</ac:structured-macro>")
    return out


def _convert_body(body: str, indent: int) -> list[str]:
    """MD 본문 → XML 라인. fenced div 분기 + 사이 사이 일반 블록 처리.

    Panel 간 자동 spacer 삽입 (사양 §7).
    """
    raw_lines = body.splitlines()
    out: list[str] = []
    i = 0
    n = len(raw_lines)
    just_emitted_panel = False

    def _flush_plain(buf: list[str]) -> None:
        nonlocal just_emitted_panel
        if not buf:
            return
        # 본문 일반 블록 — 자체 layout 래퍼 없음, 직접 emit
        rendered = _convert_block_lines(buf, indent)
        # spacer 가 마지막에 있고 본문이 빈 줄로만 구성된 경우 압축 (멱등)
        if rendered:
            out.extend(rendered)
            just_emitted_panel = False
        buf.clear()

    plain_buf: list[str] = []
    while i < n:
        line = raw_lines[i]
        m_open = FENCED_DIV_OPEN_RE.match(line)
        if not m_open:
            plain_buf.append(line)
            i += 1
            continue
        # fenced div 시작 — 우선 plain 비움
        _flush_plain(plain_buf)
        classes, kvs = _parse_div_attrs(m_open.group(1))
        # 매칭 close 찾기 (nested fenced div 1단계만 허용)
        depth = 1
        body_start = i + 1
        j = body_start
        while j < n and depth > 0:
            l2 = raw_lines[j]
            if FENCED_DIV_OPEN_RE.match(l2):
                depth += 1
            elif FENCED_DIV_CLOSE_RE.match(l2):
                depth -= 1
                if depth == 0:
                    break
            j += 1
        inner_lines = raw_lines[body_start:j]
        i = j + 1  # consume close
        # 분기
        primary = classes[0] if classes else ""
        if primary == "panel":
            section = kvs.get("section", "")
            style = kvs.get("style", "common")
            if just_emitted_panel:
                out.extend(_emit_spacer(indent))
            out.extend(_emit_panel(section, style, inner_lines, indent))
            just_emitted_panel = True
        elif primary in CALLOUT_CLASSES:
            out.extend(_emit_callout(primary, inner_lines, indent))
            just_emitted_panel = False
        elif primary == "expand":
            out.extend(_emit_expand(kvs.get("title", ""), inner_lines, indent))
            just_emitted_panel = False
        else:
            # 미지원 클래스 — 단순 div pass-through (텍스트 보존)
            out.extend(_convert_block_lines(inner_lines, indent))
            just_emitted_panel = False

    _flush_plain(plain_buf)
    # 마지막 panel 뒤 spacer (사양 §7 — panel 후행 spacer 보장)
    if just_emitted_panel:
        out.extend(_emit_spacer(indent))
    return out


# ── Frontmatter publication 영역 → XML ───────────────────────────────────────


def _emit_header_info(header: dict, indent: int) -> list[str]:
    """publication.header → layout-section single + info-style callout."""
    style = (header.get("style") or "info").strip()
    if style not in CALLOUT_CLASSES:
        style = "info"
    body_md = header.get("body") or ""
    ind = INDENT * indent
    out = [
        f'{ind}<ac:layout-section ac:type="single">',
        f"{ind}{INDENT}<ac:layout-cell>",
    ]
    out.extend(_emit_callout(style, body_md.splitlines(), indent + 2))
    out.append(f"{ind}{INDENT}</ac:layout-cell>")
    out.append(f"{ind}</ac:layout-section>")
    return out


def _emit_meta(meta: dict, indent: int) -> list[str]:
    """publication.meta → layout-section {layout} + cells.

    cells[].panel.body / cells[].change_history N 지원.
    """
    layout = (meta.get("layout") or "single").strip()
    if layout not in LAYOUT_TYPES:
        layout = "single"
    cells = meta.get("cells") or []
    ind = INDENT * indent
    out = [f'{ind}<ac:layout-section ac:type="{layout}">']
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        out.append(f"{ind}{INDENT}<ac:layout-cell>")
        if "panel" in cell and isinstance(cell["panel"], dict):
            p = cell["panel"]
            title = p.get("title", "")
            body_md = (p.get("body") or "").splitlines()
            # meta panel 은 style 미지정 — 기본 common
            # layout-cell 안에 panel macro 직접 (외곽 layout-section 은 이미 있음)
            style_params = PANEL_STYLE_MAP["common"]
            sub = INDENT * (indent + 2)
            out.append(
                f'{sub}<ac:structured-macro ac:name="panel"'
                f' ac:schema-version="1">'
            )
            for key in sorted(style_params.keys()):
                out.append(
                    f'{sub}{INDENT}<ac:parameter ac:name="{key}">'
                    f'{_xml_escape(style_params[key])}</ac:parameter>'
                )
            out.append(
                f'{sub}{INDENT}<ac:parameter ac:name="title">'
                f'{_xml_escape(title)}</ac:parameter>'
            )
            out.append(f"{sub}{INDENT}<ac:rich-text-body>")
            out.extend(_convert_body("\n".join(body_md), indent + 4))
            out.append(f"{sub}{INDENT}</ac:rich-text-body>")
            out.append(f"{sub}</ac:structured-macro>")
        elif "change_history" in cell:
            n_val = cell["change_history"]
            sub = INDENT * (indent + 2)
            out.append(
                f'{sub}<ac:structured-macro ac:name="change-history"'
                f' ac:schema-version="1">'
            )
            out.append(
                f'{sub}{INDENT}<ac:parameter ac:name="limit">'
                f"{int(n_val)}</ac:parameter>"
            )
            out.append(f"{sub}</ac:structured-macro>")
        out.append(f"{ind}{INDENT}</ac:layout-cell>")
    out.append(f"{ind}</ac:layout-section>")
    return out


# ── Style substitution (placeholder 치환) ───────────────────────────────────


def _substitute_placeholders(text: str, mapping: dict[str, str]) -> str:
    """{{KEY}} → mapping[KEY] (정의된 키만)."""
    def _repl(m: re.Match) -> str:
        key = m.group(1)
        return mapping.get(key, m.group(0))
    return re.sub(r"\{\{([A-Z_][A-Z0-9_]*)\}\}", _repl, text)


# ── Main convert ────────────────────────────────────────────────────────────


def convert(text: str, *, style_substitute: bool = False) -> str:
    """MD 정본 → Confluence storage XML 문자열.

    Returns: XML 문자열 (말미 개행 포함).
    Raises: ValueError — frontmatter YAML 오류 등.
    """
    fm, body = _parse_frontmatter(text)
    pub = fm.get("publication") if isinstance(fm.get("publication"), dict) else {}

    if style_substitute:
        # publication 단계 placeholder 치환 (사양 §12 --style-substitute)
        mapping: dict[str, str] = {}
        if "title" in fm and isinstance(fm["title"], str):
            mapping["TITLE"] = fm["title"]
        for k in ("wo_id", "version", "last_updated"):
            v = fm.get(k)
            if v is not None:
                mapping[k.upper().replace("LAST_UPDATED", "DATE")] = str(v)
        # PRODUCT_NAME 추출 — title 의 마지막 {{...}} 가능, but 보수적으로 미설정.
        body = _substitute_placeholders(body, mapping)

    out: list[str] = ['<ac:layout>']
    # frontmatter publication 영역 emit
    if isinstance(pub, dict):
        header = pub.get("header")
        if isinstance(header, dict):
            out.extend(_emit_header_info(header, indent=1))
        meta = pub.get("meta")
        if isinstance(meta, dict):
            out.extend(_emit_meta(meta, indent=1))
        # spacer 1개 (header/meta 와 본문 panel 사이)
        if isinstance(header, dict) or isinstance(meta, dict):
            out.extend(_emit_spacer(indent=1))

    # 본문 변환
    out.extend(_convert_body(body, indent=1))
    out.append('</ac:layout>')
    return "\n".join(out) + "\n"


# ── CLI ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="MD → Confluence Storage Format XHTML 변환기"
    )
    ap.add_argument("--input", required=True, type=Path,
                    help="입력 MD 파일")
    ap.add_argument("--output", required=True, type=Path,
                    help="출력 XML 파일")
    ap.add_argument(
        "--style-substitute", action="store_true",
        help="{{PRODUCT_NAME}} 등 placeholder 치환 (publication 단계 전용)"
    )
    ap.add_argument(
        "--validate", action="store_true",
        help="입력 MD 에 lint_publication_syntax 를 실행하고 FAIL 시 exit 2"
    )
    args = ap.parse_args(argv)

    if not args.input.is_file():
        print(f"[md_to_storage] FAIL: 입력 파일 없음 — {args.input}",
              file=sys.stderr)
        return 3
    try:
        text = args.input.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[md_to_storage] FAIL: 입력 읽기 — {e}", file=sys.stderr)
        return 3
    try:
        result = convert(text, style_substitute=args.style_substitute)
    except Exception as e:
        print(f"[md_to_storage] FAIL: 변환 오류 — {e}", file=sys.stderr)
        return 1

    if args.validate:
        # 변환 성공 + publication-lint 통과를 함께 검증 (exit 2 = Lint FAIL).
        # lint 는 변환 산출물이 아니라 입력 MD 정본에 대해 실행한다.
        try:
            from lint_publication_syntax import lint_file  # 동일 디렉터리 모듈
        except ImportError:
            _here = str(Path(__file__).resolve().parent)
            if _here not in sys.path:
                sys.path.insert(0, _here)
            from lint_publication_syntax import lint_file
        try:
            findings = lint_file(args.input)
        except OSError as e:
            print(f"[md_to_storage] FAIL: lint 입력 읽기 — {e}", file=sys.stderr)
            return 3
        fails = [f for f in findings if f.level == "FAIL"]
        if fails:
            for f in fails:
                print(
                    f"[md_to_storage] LINT FAIL {f.rule} "
                    f"{args.input}:{f.line} — {f.message}",
                    file=sys.stderr,
                )
            return 2

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    except OSError as e:
        print(f"[md_to_storage] FAIL: 출력 쓰기 — {e}", file=sys.stderr)
        return 3
    print(f"[md_to_storage] OK: {args.input} → {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
