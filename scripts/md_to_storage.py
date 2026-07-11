#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown → Confluence Storage Format (XHTML) deterministic converter.

This module converts publication-targeted MD (single SSoT) to Confluence
storage format XML. The spec SSoT is
``orange-pm-plugin/skills/render/publication-syntax.md``. The implementation
uses regex + a mini state machine (no external MD library) to guarantee
determinism/reproducibility (identical MD → byte-identical XML, §9).

Supported input syntax (spec §3-§6):
    1. Frontmatter (YAML)
        - title / wo_id / type / layer / version / last_updated
        - publication.header   : info macro (style/body)
        - publication.meta     : layout(single|two_equal|three_equal) + cells
        - publication.color_state (Phase 3 — pass-through)
    2. Fenced div blocks
        - ``::: {.panel section="..." [style="common|product|tbd|warning|info"]}``
            → layout-section single + panel macro (auto trailing spacer)
        - ``::: {.info|.warning|.note|.tip}`` → simple callout macro
        - ``::: {.expand title="..."}`` → expand macro
    3. Standard MD
        - headings h1~h6, **bold**/_em_, ul/ol/li, blockquote, hr, paragraph
        - tables: relative-table wrapped, even colgroup distribution (default) +
              ``<!-- col-widths: 15%, 85% -->`` directive support
        - code blocks: structured-macro code + plain-text-body CDATA
    4. Inline macros
        - ``[[page:Title]]`` → ac:link + ri:page
        - ``{{toc}}`` / ``{{change_history N}}`` → structured-macro
        - ``[text](url)`` → ``<a href="url">``
        - ``{{PLACEHOLDER}}`` (PRODUCT_NAME/DOC_ID/VERSION/DATE, etc.) — passed through as text

Reserved for Phase 3 (placeholder only, this phase passes text through):
    - color span ``[text]{.color-green}`` / ``{.color-blue}``

CLI:
    python md_to_storage.py --input X.md --output X.xml \
        [--style-substitute] [--validate]

exit code:
    0 = success
    1 = MD parse failure
    2 = Lint FAIL (with --validate)
    3 = I/O error
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml  # assumes PyYAML 6.0.x (only non-stdlib dependency)
except Exception:  # pragma: no cover - frontmatter fallback when PyYAML is absent
    yaml = None  # type: ignore[assignment]


# ── Constants / mappings ──────────────────────────────────────────────────────

# spec §3.1 — panel style mapping (style value → parameter dict)
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

# spec §6 — color span (reserved for Phase 3, this phase passes text through)
COLOR_SPAN_MAP: dict[str, str] = {
    "color-green": "rgb(0,176,80)",
    "color-blue":  "rgb(0,80,229)",
}

CALLOUT_CLASSES = {"info", "warning", "note", "tip"}
LAYOUT_TYPES = {"single", "two_equal", "three_equal"}

INDENT = "  "

# ── Regexes ───────────────────────────────────────────────────────────────────

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
    """Parse YAML frontmatter → (dict, body). Returns ({}, text) if absent.

    Very limited fallback when PyYAML is absent (top-level scalars only).
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
    """Escape XML text (& < > only; " is handled separately for attributes)."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _xml_attr_escape(text: str) -> str:
    """Escape XML attribute value (& < > " ')."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ── Inline conversion (text → XHTML inline string) ──────────────────────────


def _convert_inline(text: str) -> str:
    """Inline conversion: applies macro → link → strong → em, in that order.

    Macros are preserved in the source text as placeholders (\\x00..\\x00) to
    avoid being mangled by escaping.
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

    # 2. change_history (first — so toc doesn't match as a substring)
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

    # 4. color span (Phase 3 — this phase is a text pass-through; spec §6 uses hex)
    def _color_repl(m: re.Match) -> str:
        inner, cls = m.group(1), m.group(2)
        color = COLOR_SPAN_MAP.get(cls)
        if color is None:
            return m.group(0)  # undefined class — keep the original text
        return _ph(f'<span style="color: {color}">{_xml_escape(inner)}</span>')
    text = COLOR_SPAN_RE.sub(_color_repl, text)

    # 5. plain link [text](url)
    def _link_repl(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        return _ph(f'<a href="{_xml_attr_escape(url)}">{_xml_escape(label)}</a>')
    text = LINK_RE.sub(_link_repl, text)

    # 6. XML escape (placeholder markers use \x00 so they're unaffected)
    text = _xml_escape(text)

    # 7. strong / em
    text = STRONG_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", text)
    text = EM_RE.sub(lambda m: f"<em>{m.group(1)}</em>", text)

    # 8. restore placeholders
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
    """| a | b | → ['a', 'b'] (trims whitespace, strips outer |)."""
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
    """Render table XHTML (spec §5, §5.1)."""
    n_cols = len(header) if header else (len(rows[0]) if rows else 0)
    if n_cols == 0:
        return []
    if col_widths and len(col_widths) == n_cols:
        widths = col_widths
    else:
        # even distribution — 100 / n (last column absorbs remainder for an integer total)
        base = 100 // n_cols
        widths = [f"{base}%"] * n_cols
        # remainder correction: give leftover to the last column
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
            # pad with empty cells if the row has fewer cells than columns
            padded = row + [""] * (n_cols - len(row))
            out.append(f"{ind}{INDENT * 2}<tr>")
            for cell in padded[:n_cols]:
                out.append(f"{ind}{INDENT * 3}<td>{_convert_inline(cell)}</td>")
            out.append(f"{ind}{INDENT * 2}</tr>")
        out.append(f"{ind}{INDENT}</tbody>")
    out.append(f"{ind}</table>")
    return out


def _render_code_block(language: str, content: str, indent: int) -> list[str]:
    """Code block → ac:structured-macro code + CDATA (spec §3.5)."""
    ind = INDENT * indent
    out = [f'{ind}<ac:structured-macro ac:name="code" ac:schema-version="1">']
    if language:
        out.append(
            f'{ind}{INDENT}<ac:parameter ac:name="language">'
            f'{_xml_escape(language)}</ac:parameter>'
        )
    # CDATA — split if the content contains ]]>
    safe = content.replace("]]>", "]]]]><![CDATA[>")
    out.append(
        f'{ind}{INDENT}<ac:plain-text-body><![CDATA[{safe}]]></ac:plain-text-body>'
    )
    out.append(f"{ind}</ac:structured-macro>")
    return out


def _render_list(items: list[tuple[int, str, str]], indent: int) -> list[str]:
    """Render a list.

    items: [(depth_level, ordered_tag, text), ...]  depth_level 0=top.
    Groups a run of the same depth/tag into a single <ul>/<ol>; deeper
    indentation is nested recursively.
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
    """Process the run in items[start:] where depth==depth. Returns the last processed index + 1."""
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
            # Deeper item — insert a nested list before closing the preceding <li>
            # Strip the closing tag off the nearest <li> and re-append after the nested list + re-close
            if out and out[-1].endswith("</li>"):
                last = out.pop()
                # last format: f"{ind}{INDENT}<li>...</li>"  -> strip "</li>" then re-append
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
    """Block line list -> XHTML line list (excludes fenced divs; only called from inside one).

    Pure block-level converter. Handles only code blocks / tables / lists /
    blockquotes / headings / hr / paragraphs. Fenced divs are dispatched by
    the parent _convert_body.
    """
    out: list[str] = []
    i = 0
    n = len(lines)
    pending_col_widths: list[str] | None = None
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # col-widths directive — applies to the next table
        cw = COLWIDTHS_DIRECTIVE_RE.match(line)
        if cw:
            pending_col_widths = _parse_col_widths(cw.group(1))
            i += 1
            continue

        # blank line -> spacer (spec §5: blank line -> <p><br/></p>)
        if not stripped:
            out.append(f"{INDENT * indent}<p><br/></p>")
            i += 1
            continue

        # code fence
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

        # table
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

        # list
        ul = UL_RE.match(line)
        ol = OL_RE.match(line)
        if ul or ol:
            items: list[tuple[int, str, str]] = []
            while i < n:
                m_ul = UL_RE.match(lines[i])
                m_ol = OL_RE.match(lines[i])
                if not m_ul and not m_ol:
                    if not lines[i].strip():
                        # a blank line ends the list
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

        # paragraph — accumulate until a blank line
        para_lines: list[str] = [stripped]
        i += 1
        while i < n:
            nxt = lines[i]
            if not nxt.strip():
                break
            # stop if another block starts
            if (HEADING_RE.match(nxt) or HR_RE.match(nxt)
                    or CODE_FENCE_RE.match(nxt) or UL_RE.match(nxt)
                    or OL_RE.match(nxt) or BLOCKQUOTE_RE.match(nxt)
                    or FENCED_DIV_OPEN_RE.match(nxt)
                    or FENCED_DIV_CLOSE_RE.match(nxt)
                    or COLWIDTHS_DIRECTIVE_RE.match(nxt)):
                break
            # does a table start here?
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
    """Panel macro -> layout-section single + cell wrap (spec §3.1, §7)."""
    style_params = PANEL_STYLE_MAP.get(style, PANEL_STYLE_MAP["common"])
    ind = INDENT * indent
    out: list[str] = []
    out.append(f'{ind}<ac:layout-section ac:type="single">')
    out.append(f"{ind}{INDENT}<ac:layout-cell>")
    out.append(
        f'{ind}{INDENT * 2}<ac:structured-macro ac:name="panel"'
        f' ac:schema-version="1">'
    )
    # Parameters — sorted to comply with spec §9 (alphabetical attribute order)
    # panel parameters themselves are emitted in sorted key order for determinism
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
    """Automatic spacer between panels (spec §7)."""
    ind = INDENT * indent
    return [
        f'{ind}<ac:layout-section ac:type="single">',
        f"{ind}{INDENT}<ac:layout-cell><p><br/></p></ac:layout-cell>",
        f"{ind}</ac:layout-section>",
    ]


def _emit_callout(name: str, inner_lines: list[str], indent: int) -> list[str]:
    """info/warning/note/tip -> a simple macro (spec §3.2). No layout wrapper."""
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
    """Expand macro (spec §3.3)."""
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
    """MD body -> XML lines. Dispatches fenced divs and handles plain blocks in between.

    Inserts an automatic spacer between panels (spec §7).
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
        # Plain body block — no layout wrapper of its own, emit directly
        rendered = _convert_block_lines(buf, indent)
        # Collapse the case where a spacer is last and the body is only
        # blank lines (idempotent)
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
        # fenced div starts — flush the plain buffer first
        _flush_plain(plain_buf)
        classes, kvs = _parse_div_attrs(m_open.group(1))
        # find the matching close (only one level of nested fenced div is allowed)
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
        # dispatch
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
            # unsupported class — simple div pass-through (preserves the text)
            out.extend(_convert_block_lines(inner_lines, indent))
            just_emitted_panel = False

    _flush_plain(plain_buf)
    # spacer after the last panel (spec §7 — guarantees a trailing panel spacer)
    if just_emitted_panel:
        out.extend(_emit_spacer(indent))
    return out


# ── Frontmatter publication section -> XML ──────────────────────────────────


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
    """publication.meta -> layout-section {layout} + cells.

    Supports cells[].panel.body / cells[].change_history N.
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
            # meta panels don't specify a style — default to common
            # panel macro goes directly inside the layout-cell (the outer
            # layout-section already exists)
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


# ── Style substitution (placeholder substitution) ───────────────────────────


def _substitute_placeholders(text: str, mapping: dict[str, str]) -> str:
    """{{KEY}} -> mapping[KEY] (defined keys only)."""
    def _repl(m: re.Match) -> str:
        key = m.group(1)
        return mapping.get(key, m.group(0))
    return re.sub(r"\{\{([A-Z_][A-Z0-9_]*)\}\}", _repl, text)


# ── Main convert ────────────────────────────────────────────────────────────


def convert(text: str, *, style_substitute: bool = False) -> str:
    """MD source -> Confluence storage XML string.

    Returns: an XML string (with a trailing newline).
    Raises: ValueError — for frontmatter YAML errors, etc.
    """
    fm, body = _parse_frontmatter(text)
    pub = fm.get("publication") if isinstance(fm.get("publication"), dict) else {}

    if style_substitute:
        # publication-stage placeholder substitution (spec §12 --style-substitute)
        mapping: dict[str, str] = {}
        if "title" in fm and isinstance(fm["title"], str):
            mapping["TITLE"] = fm["title"]
        for k in ("wo_id", "version", "last_updated"):
            v = fm.get(k)
            if v is not None:
                mapping[k.upper().replace("LAST_UPDATED", "DATE")] = str(v)
        # PRODUCT_NAME extraction — could come from a trailing {{...}} in
        # title, but conservatively left unset for now.
        body = _substitute_placeholders(body, mapping)

    out: list[str] = ['<ac:layout>']
    # emit the frontmatter publication section
    if isinstance(pub, dict):
        header = pub.get("header")
        if isinstance(header, dict):
            out.extend(_emit_header_info(header, indent=1))
        meta = pub.get("meta")
        if isinstance(meta, dict):
            out.extend(_emit_meta(meta, indent=1))
        # one spacer (between header/meta and the body panel)
        if isinstance(header, dict) or isinstance(meta, dict):
            out.extend(_emit_spacer(indent=1))

    # convert the body
    out.extend(_convert_body(body, indent=1))
    out.append('</ac:layout>')
    return "\n".join(out) + "\n"


# ── CLI ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="MD -> Confluence Storage Format XHTML converter"
    )
    ap.add_argument("--input", required=True, type=Path,
                    help="Input MD file")
    ap.add_argument("--output", required=True, type=Path,
                    help="Output XML file")
    ap.add_argument(
        "--style-substitute", action="store_true",
        help="Substitute placeholders like {{PRODUCT_NAME}} (publication stage only)"
    )
    ap.add_argument(
        "--validate", action="store_true",
        help="Run lint_publication_syntax on the input MD and exit 2 on FAIL"
    )
    args = ap.parse_args(argv)

    if not args.input.is_file():
        print(f"[md_to_storage] FAIL: input file not found — {args.input}",
              file=sys.stderr)
        return 3
    try:
        text = args.input.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[md_to_storage] FAIL: reading input — {e}", file=sys.stderr)
        return 3
    try:
        result = convert(text, style_substitute=args.style_substitute)
    except Exception as e:
        print(f"[md_to_storage] FAIL: conversion error — {e}", file=sys.stderr)
        return 1

    if args.validate:
        # Validates both a successful conversion and a passing
        # publication-lint (exit 2 = Lint FAIL). Lint runs against the
        # input MD source, not the conversion output.
        try:
            from lint_publication_syntax import lint_file  # module in the same directory
        except ImportError:
            _here = str(Path(__file__).resolve().parent)
            if _here not in sys.path:
                sys.path.insert(0, _here)
            from lint_publication_syntax import lint_file
        try:
            findings = lint_file(args.input)
        except OSError as e:
            print(f"[md_to_storage] FAIL: reading lint input — {e}", file=sys.stderr)
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
        print(f"[md_to_storage] FAIL: writing output — {e}", file=sys.stderr)
        return 3
    print(f"[md_to_storage] OK: {args.input} -> {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
