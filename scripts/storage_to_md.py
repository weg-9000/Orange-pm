#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""storage_to_md — Confluence Storage Format (XHTML) → Markdown reverse converter.

Used for reverse sync in the Option A (MD-only) architecture. Restores a Confluence
snapshot XML into a form that can be compared (diff/merge) against the canonical MD.

This converter maintains round-trip consistency with `md_to_storage.py` (spec §8/§9):
    md_to_storage(storage_to_md(X)) == X  (after normalization)

Spec SSoT: `orange-pm-plugin/skills/render/publication-syntax.md`

Relationship to existing code:
    Absorbs and extends the logic of `render_sync_check.py::_strip_storage_xml` and
    `_convert_tables_to_markdown`. render_sync_check may delegate to this module in the future.

CLI:
    python storage_to_md.py --input X.xml --output X.md [--strip-colors]
    python storage_to_md.py --input snapshot.json --from-snapshot --output X.md

Exit codes:
    0  success
    1  XML/JSON parse failure
    2  unsupported macro found (text preserved, non-blocking warning)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

# --- I/O encoding consistency ----------------------------------------------------------
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

# --- Namespaces ---------------------------------------------------------------
# Confluence Storage Format uses ac:/ri: prefixes, but is usually provided as a
# fragment without an XML declaration. parse_storage wraps it in a root and injects xmlns.
NS = {
    "ac": "http://atlassian.com/content",
    "ri": "http://atlassian.com/resource/identifier",
}
# Prefixed tag for use with the ET API (Clark notation)
def _q(prefix: str, local: str) -> str:
    return f"{{{NS[prefix]}}}{local}"

# --- Spec §3.1 Panel style mapping (reverse direction) --------------------------------------
# Identified by borderColor alone. 1:1 mapping with md_to_storage (spec §3.1 table).
PANEL_STYLE_BY_BORDER = {
    "#24FE00": "common",    # default (omitted)
    "#0050E5": "product",
    "#FF4D4F": "tbd",
    "#FAAD14": "warning",
    "#1890FF": "info",
}

SUPPORTED_FENCED_DIV_MACROS = {"panel", "info", "warning", "note", "tip", "expand"}

# Phase 3 color mapping (reserved). 1:1 mapping with md_to_storage (spec §6).
COLOR_RGB_TO_CLASS = {
    "rgb(0,176,80)": "color-green",
    "rgb(0,80,229)": "color-blue",
}
# Also allow whitespace variants for exact matching (handled via re).
_COLOR_SPAN_RE = re.compile(
    r'<span\s+style\s*=\s*"color:\s*(rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\))\s*"\s*>(.*?)</span>',
    re.DOTALL | re.IGNORECASE,
)
_COLOR_SPAN_BARE_RE = re.compile(
    r'<span\s+style\s*=\s*"color:[^"]*"\s*>(.*?)</span>',
    re.DOTALL | re.IGNORECASE,
)


# --- State container -----------------------------------------------------------
class _ConvState:
    """State accumulated during conversion (warnings, etc). stderr output is aggregated in main.

    consumed_sections: set of id(Element) for layout-sections absorbed into frontmatter.
    Prevents duplicate emission during the body walk stage (spec §7 — frontmatter-absorbed areas are excluded from the body).
    """

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.unsupported_macros: list[str] = []
        self.consumed_sections: set[int] = set()

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def unsupported(self, name: str) -> None:
        if name not in self.unsupported_macros:
            self.unsupported_macros.append(name)

    def consume(self, elem: ET.Element) -> None:
        self.consumed_sections.add(id(elem))

    def is_consumed(self, elem: ET.Element) -> bool:
        return id(elem) in self.consumed_sections


# --- XML parsing -----------------------------------------------------------------
def parse_storage(text: str) -> ET.Element:
    """Parse a Confluence Storage Format fragment into an ET.Element.

    Since the fragment usually has no XML declaration or namespace, wrap it in a root
    and inject xmlns:ac/ri. Guarantees a single root.
    """
    if not text or not text.strip():
        # Empty input returns an empty root (not an error)
        return ET.fromstring(
            '<root xmlns:ac="http://atlassian.com/content" '
            'xmlns:ri="http://atlassian.com/resource/identifier"/>'
        )
    # Preserve some HTML entities (&nbsp; etc. are not XML-standard — manual substitution).
    sanitized = (
        text.replace("&nbsp;", " ")
            .replace("&ndash;", "–")
            .replace("&mdash;", "—")
            .replace("&hellip;", "…")
    )
    wrapped = (
        '<root xmlns:ac="http://atlassian.com/content" '
        'xmlns:ri="http://atlassian.com/resource/identifier">'
        f"{sanitized}</root>"
    )
    try:
        return ET.fromstring(wrapped)
    except ET.ParseError as exc:
        raise ValueError(f"Storage Format XML parse failed: {exc}") from exc


# --- Helpers ------------------------------------------------------------------
def _inner_text(elem: ET.Element) -> str:
    """Flatten all text of elem (including children). Collapse newlines/indentation into a single space."""
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        parts.append(_inner_text(child))
        if child.tail:
            parts.append(child.tail)
    raw = "".join(parts)
    return re.sub(r"\s+", " ", raw).strip()


def _get_param(macro: ET.Element, name: str) -> str | None:
    """Extract the ac:parameter ac:name=... value (None if absent)."""
    for p in macro.findall(_q("ac", "parameter")):
        if p.get(_q("ac", "name")) == name:
            return (p.text or "").strip()
    return None


def _get_all_params(macro: ET.Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in macro.findall(_q("ac", "parameter")):
        nm = p.get(_q("ac", "name")) or ""
        out[nm] = (p.text or "").strip()
    return out


def _rich_body(macro: ET.Element) -> ET.Element | None:
    return macro.find(_q("ac", "rich-text-body"))


def _plain_body(macro: ET.Element) -> str | None:
    pb = macro.find(_q("ac", "plain-text-body"))
    if pb is None:
        return None
    return pb.text or ""


# --- Inline conversion (text + inline children) ---------------------------------------
def _inline_to_md(elem: ET.Element, state: _ConvState) -> str:
    """Convert elem's children into inline MD (block elements are handled separately).

    Does not use elem's own tag — converts only the body content.
    """
    buf: list[str] = []
    if elem.text:
        buf.append(elem.text)
    for child in elem:
        buf.append(_inline_node(child, state))
        if child.tail:
            buf.append(child.tail)
    return "".join(buf)


def _inline_node(node: ET.Element, state: _ConvState) -> str:
    """Convert a single inline node to an MD string."""
    tag = _strip_ns(node.tag)
    ns = _ns_of(node.tag)

    # ac:link → page link
    if ns == "ac" and tag == "link":
        return _convert_page_link(node, state)
    # ac:structured-macro (partially inline — toc, change-history are usually block-level,
    # but appear inline inside a panel body in frontmatter)
    if ns == "ac" and tag == "structured-macro":
        return _convert_macro(node, state)

    # Standard HTML inline
    if tag in ("strong", "b"):
        return f"**{_inline_to_md(node, state).strip()}**"
    if tag in ("em", "i"):
        return f"*{_inline_to_md(node, state).strip()}*"
    if tag == "code":
        return f"`{_inline_to_md(node, state).strip()}`"
    if tag == "a":
        text = _inline_to_md(node, state).strip()
        href = node.get("href") or ""
        return f"[{text}]({href})"
    if tag == "br":
        return "\n"
    if tag == "span":
        # Phase 3D — handle color spans directly.
        # After ET parsing, raw XML markup is gone so the post-processing regex won't work,
        # so read the style attribute directly here and emit as an MD fenced span.
        # The strip_colors post-processing in convert_storage is a fallback (for when raw XML remains).
        inner = _inline_to_md(node, state)
        style = (node.get("style") or "").replace(" ", "")
        m = re.match(r"color:(rgb\(\d+,\d+,\d+\))", style)
        if m:
            cls = COLOR_RGB_TO_CLASS.get(m.group(1))
            if cls:
                return f"[{inner}]{{.{cls}}}"
        # Unknown color/style → text only
        return inner

    # fallback: pass through child text only (unsupported inline tag)
    return _inline_to_md(node, state)


def _strip_ns(qname: str) -> str:
    if qname.startswith("{"):
        return qname.split("}", 1)[1]
    return qname


def _ns_of(qname: str) -> str | None:
    """The tag's ns prefix (ac/ri), or None (HTML)."""
    if not qname.startswith("{"):
        return None
    uri = qname[1:].split("}", 1)[0]
    for prefix, full in NS.items():
        if full == uri:
            return prefix
    return None


# --- Macro conversion --------------------------------------------------------------
def _convert_page_link(link: ET.Element, state: _ConvState) -> str:
    page = link.find(_q("ri", "page"))
    if page is not None:
        title = page.get(_q("ri", "content-title")) or ""
        if title:
            return f"[[page:{title}]]"
    # ri:user etc. are Phase 4 (spec §4.2 — text preserved for now)
    user = link.find(_q("ri", "user"))
    if user is not None:
        key = user.get(_q("ri", "userkey")) or user.get(_q("ri", "account-id")) or ""
        state.unsupported(f"ri:user (Phase 4 reserved): {key}")
        return f"[[user:{key}]]" if key else ""
    # Unknown ac:link → pass through text only
    return _inline_to_md(link, state)


def _convert_macro(macro: ET.Element, state: _ConvState) -> str:
    """ac:structured-macro → MD string (block/inline auto-detected).

    Even in inline context, toc / change-history remain {{}} placeholders.
    panel/info/warning/note/tip/expand are emitted as fenced div blocks separated
    by \n in the body flow (caller positions them appropriately).
    """
    name = macro.get(_q("ac", "name")) or ""

    if name == "toc":
        return "{{toc}}"
    if name == "change-history":
        limit = _get_param(macro, "limit") or "3"
        return f"{{{{change_history {limit}}}}}"
    if name == "code":
        return _convert_code_macro(macro)
    if name in ("info", "warning", "note", "tip"):
        body = _convert_rich_body(_rich_body(macro), state).strip()
        return f"\n::: {{.{name}}}\n{body}\n:::\n"
    if name == "expand":
        title = _get_param(macro, "title") or ""
        body = _convert_rich_body(_rich_body(macro), state).strip()
        title_attr = f' title="{title}"' if title else ""
        return f"\n::: {{.expand{title_attr}}}\n{body}\n:::\n"
    if name == "panel":
        return _convert_panel(macro, state)
    if name == "mermaid":
        # spec §3.4 — Phase 2 onward. Body text preserved.
        body = _plain_body(macro) or _convert_rich_body(_rich_body(macro), state)
        return f"\n```mermaid\n{body.rstrip()}\n```\n"

    # Unsupported macro → preserve body text + warn
    state.unsupported(name)
    rb = _rich_body(macro)
    if rb is not None:
        return _convert_rich_body(rb, state)
    pb = _plain_body(macro)
    if pb:
        return pb
    return ""


def _convert_code_macro(macro: ET.Element) -> str:
    """code macro → fenced code block (spec §3.5)."""
    lang = _get_param(macro, "language") or ""
    body = _plain_body(macro) or ""
    # CDATA body content comes in directly, so preserve line breaks
    fence_lang = lang if lang else ""
    # Clean up trailing newline at the end
    body = body.rstrip("\n")
    return f"\n```{fence_lang}\n{body}\n```\n"


def _convert_panel(macro: ET.Element, state: _ConvState) -> str:
    """panel macro → ::: {.panel section="..." style="..."} (spec §3.1)."""
    params = _get_all_params(macro)
    section = params.get("title", "")
    border = params.get("borderColor", "").strip()
    # Identify default style
    style = PANEL_STYLE_BY_BORDER.get(border, "")
    # common (default) is omitted on round-trip (spec §8: default style is omitted on round-trip).
    attrs = [".panel"]
    if section:
        # Escape quotes in the section value if present (rare, but a safeguard)
        sec_esc = section.replace('"', '\\"')
        attrs.append(f'section="{sec_esc}"')
    if style and style != "common":
        attrs.append(f'style="{style}"')
    elif border and style == "":
        # Unknown borderColor → preserved as a custom value (raw value)
        attrs.append(f'style="{border}"')
        state.warn(f"Preserving unknown panel borderColor: {border}")
    header = "::: {" + " ".join(attrs) + "}"
    body = _convert_rich_body(_rich_body(macro), state).strip()
    return f"\n{header}\n{body}\n:::\n"


# --- Rich body / block content ----------------------------------------------------
def _convert_rich_body(body: ET.Element | None, state: _ConvState) -> str:
    if body is None:
        return ""
    out = _walk_body(body, state)
    # Collapse multiple blank lines
    return re.sub(r"\n{3,}", "\n\n", out)


def _walk_body(elem: ET.Element, state: _ConvState) -> str:
    """Walk a block container's children and convert to MD.

    Does not convert elem itself — processes elem.text + its children (used for
    converting containers such as rich-text-body).
    """
    buf: list[str] = []
    if elem.text and elem.text.strip():
        buf.append(elem.text)
    for child in elem:
        buf.append(_block_node(child, state))
        if child.tail and child.tail.strip():
            buf.append(child.tail)
    return "".join(buf)


def _block_node(node: ET.Element, state: _ConvState) -> str:
    """Convert a single block node to MD."""
    tag = _strip_ns(node.tag)
    ns = _ns_of(node.tag)

    if ns == "ac":
        if tag == "structured-macro":
            return _convert_macro(node, state)
        if tag == "layout":
            return _convert_layout(node, state)
        if tag == "layout-section":
            return _convert_layout_section(node, state)
        if tag == "layout-cell":
            return _walk_body(node, state)
        if tag == "rich-text-body":
            return _walk_body(node, state)
        if tag == "link":
            return _convert_page_link(node, state)
        # Other ac:* elements pass through body content only
        return _walk_body(node, state)

    # Standard HTML blocks ------------------------------------------------------------
    if re.fullmatch(r"h[1-6]", tag):
        level = int(tag[1])
        inner = _inline_to_md(node, state).strip()
        return f"\n{'#' * level} {inner}\n\n"
    if tag == "p":
        inner = _inline_to_md(node, state).rstrip()
        # spacer (<p><br/></p>) becomes a blank line
        if not inner.strip():
            return "\n"
        return f"\n{inner}\n"
    if tag == "hr":
        return "\n---\n"
    if tag == "br":
        return "\n"
    if tag == "ul":
        return _convert_list(node, state, ordered=False)
    if tag == "ol":
        return _convert_list(node, state, ordered=True)
    if tag == "blockquote":
        inner = _walk_body(node, state).strip()
        lines = [f"> {ln}" if ln.strip() else ">" for ln in inner.splitlines()]
        return "\n" + "\n".join(lines) + "\n"
    if tag == "table":
        return _extract_table(node, state)
    if tag == "pre":
        # <pre><code class="language-xxx">...</code></pre>
        code = node.find("code")
        if code is not None:
            lang = ""
            cls = code.get("class", "")
            m = re.match(r"language-(\S+)", cls)
            if m:
                lang = m.group(1)
            text = (code.text or "").rstrip("\n")
            return f"\n```{lang}\n{text}\n```\n"
        return f"\n```\n{(node.text or '').rstrip()}\n```\n"
    if tag == "div":
        return _walk_body(node, state)
    if tag == "span":
        # Color spans are handled in post-processing (raw XML markers are safer). Only inline text here.
        return _inline_node(node, state)

    # fallback
    return _inline_node(node, state)


# --- Layout (spec §7) ---------------------------------------------------------
def _convert_layout(layout: ET.Element, state: _ConvState) -> str:
    """ac:layout container → walk child layout-sections."""
    return _walk_body(layout, state)


def _convert_layout_section(section: ET.Element, state: _ConvState) -> str:
    """ac:layout-section → spec §7 reverse direction.

    - section absorbed into frontmatter (state.is_consumed) → empty output (blocks duplicate emit)
    - single + one panel → panel body only (automatic layout wrapper stripping)
    - spacer (only <p><br/></p>) → ignored (blank line)
    - meta layout (two_equal / three_equal etc.) → passed through as body content. frontmatter
      reconstruction is attempted best-effort at the main stage, but this function prioritizes body flattening.
    """
    if state.is_consumed(section):
        return ""
    cells = section.findall(_q("ac", "layout-cell"))
    # spacer determination: all cells are empty or contain only <p><br/></p>
    if all(_is_spacer_cell(c) for c in cells):
        return "\n"
    # single + a single panel cell → expose only the fenced div
    if len(cells) == 1:
        return _walk_body(cells[0], state)
    # multi-cell layout → output each cell's body sequentially (best-effort flattening)
    pieces = [_walk_body(c, state) for c in cells]
    return "\n" + "\n".join(p.strip() for p in pieces if p.strip()) + "\n"


def _is_spacer_cell(cell: ET.Element) -> bool:
    """Whether cell is an empty spacer (<p><br/></p> type). Judged conservatively."""
    text = _inner_text(cell)
    if text:
        return False
    # Not a spacer if there's even one macro/table/link
    for tag_name in ("structured-macro", "link"):
        if cell.findall(f".//{_q('ac', tag_name)}"):
            return False
    if cell.findall(".//table") or cell.findall(".//img"):
        return False
    return True


# --- List ---------------------------------------------------------------------
def _convert_list(node: ET.Element, state: _ConvState, *, ordered: bool, depth: int = 0) -> str:
    """ul/ol → MD list. Supports nesting."""
    items: list[str] = []
    for idx, li in enumerate(node.findall("li"), start=1):
        prefix = f"{idx}. " if ordered else "- "
        indent = "  " * depth
        # li's direct text/inline + nested ul/ol
        nested_buf: list[str] = []
        head_buf: list[str] = []
        if li.text and li.text.strip():
            head_buf.append(li.text)
        for child in li:
            child_tag = _strip_ns(child.tag)
            if child_tag in ("ul", "ol"):
                nested_buf.append(_convert_list(
                    child, state, ordered=(child_tag == "ol"), depth=depth + 1,
                ))
            elif child_tag == "p":
                # p inside li is flattened as inline
                head_buf.append(_inline_to_md(child, state))
            else:
                head_buf.append(_inline_node(child, state))
            if child.tail and child.tail.strip():
                head_buf.append(child.tail)
        head = re.sub(r"\s+", " ", "".join(head_buf)).strip()
        items.append(f"{indent}{prefix}{head}")
        for nested in nested_buf:
            items.append(nested.rstrip())
    return "\n" + "\n".join(items) + "\n"


# --- Table --------------------------------------------------------------------
def _extract_table(table: ET.Element, state: _ConvState) -> str:
    """HTML table → MD pipe table.

    - If colgroup widths are not uniform, automatically insert a
      `<!-- col-widths: a%, b%, ... -->` directive (spec §5.1).
    - Handles both thead / tbody. If there's no header row, treat the first row as the header.
    """
    # Extract column widths -----------------------------------------------------------
    widths: list[str] = []
    colgroup = table.find("colgroup")
    if colgroup is not None:
        for col in colgroup.findall("col"):
            style = col.get("style", "")
            m = re.search(r"width\s*:\s*([\d.]+%)", style)
            widths.append(m.group(1) if m else "")

    # Collect all rows (thead first) -----------------------------------------------
    head_rows: list[ET.Element] = []
    body_rows: list[ET.Element] = []
    thead = table.find("thead")
    if thead is not None:
        head_rows = thead.findall("tr")
    tbody = table.find("tbody")
    if tbody is not None:
        body_rows = tbody.findall("tr")
    # There may be direct tr elements without tbody/thead
    if not head_rows and not body_rows:
        body_rows = table.findall("tr")

    all_rows = head_rows + body_rows
    if not all_rows:
        return "\n"

    # First row is the header (if no thead, treat the first tbody row as header — spec §5)
    has_explicit_head = bool(head_rows)
    md_lines: list[str] = []

    def _row_cells(row: ET.Element) -> list[str]:
        cells: list[str] = []
        for c in row:
            local = _strip_ns(c.tag)
            if local not in ("td", "th"):
                continue
            cells.append(_inline_to_md(c, state).strip().replace("\n", " ").replace("|", "\\|"))
        return cells

    header_cells = _row_cells(all_rows[0])
    n_cols = len(header_cells) or (len(widths) or 1)
    md_lines.append("| " + " | ".join(header_cells) + " |")
    md_lines.append("|" + "|".join(["---"] * n_cols) + "|")
    for row in all_rows[1:]:
        cells = _row_cells(row)
        # Match column count
        if len(cells) < n_cols:
            cells = cells + [""] * (n_cols - len(cells))
        md_lines.append("| " + " | ".join(cells[:n_cols]) + " |")

    # Column width directive (determine if uniform) -----------------------------------
    directive = ""
    if widths and len(widths) == n_cols and any(widths):
        # Check whether distribution is uniform (whether each width is the same integer %)
        nums: list[float] = []
        for w in widths:
            try:
                nums.append(float(w.rstrip("%")))
            except ValueError:
                nums.append(0.0)
        if nums:
            even = max(nums) - min(nums) < 1.0  # within 1% → uniform
            if not even:
                directive = "<!-- col-widths: " + ", ".join(widths) + " -->\n"

    return "\n" + directive + "\n".join(md_lines) + "\n"


# --- Frontmatter reconstruction (best-effort) -----------------------------------------
def _try_extract_publication_meta(root: ET.Element, state: _ConvState) -> dict:
    """Infer publication.header / meta by inspecting root's first layout-sections.

    Perfect round-trip is not guaranteed — best-effort (spec §8 △).
    Returns a dict on successful extraction, an empty dict on failure.
    """
    pub: dict = {}
    layout = root.find(_q("ac", "layout"))
    if layout is None:
        # Also search layout-sections directly under root
        sections = root.findall(_q("ac", "layout-section"))
    else:
        sections = layout.findall(_q("ac", "layout-section"))
    if not sections:
        return pub

    # header: first single section + a single cell + info/warning macro
    first = sections[0]
    if first.get(_q("ac", "type")) == "single":
        cells = first.findall(_q("ac", "layout-cell"))
        if len(cells) == 1:
            macros = cells[0].findall(_q("ac", "structured-macro"))
            if len(macros) == 1:
                nm = macros[0].get(_q("ac", "name")) or ""
                if nm in ("info", "warning", "note", "tip"):
                    body = _convert_rich_body(_rich_body(macros[0]), state).strip()
                    if body:
                        pub["header"] = {"style": nm, "body": body}
                        state.consume(first)

    # meta: first section where type != single
    for sec in sections:
        t = sec.get(_q("ac", "type")) or "single"
        if t == "single":
            continue
        cells = sec.findall(_q("ac", "layout-cell"))
        meta_cells: list[dict] = []
        for cell in cells:
            ch_macro = cell.find(f"./{_q('ac', 'structured-macro')}[@{_q('ac', 'name')}='change-history']")
            if ch_macro is None:
                # Some cells are inside a <p>
                ch_macro = cell.find(f".//{_q('ac', 'structured-macro')}[@{_q('ac', 'name')}='change-history']")
            if ch_macro is not None and len(cell.findall(_q("ac", "structured-macro"))) <= 1:
                limit = _get_param(ch_macro, "limit") or "3"
                try:
                    meta_cells.append({"change_history": int(limit)})
                except ValueError:
                    meta_cells.append({"change_history": 3})
                continue
            # panel cell
            panel = cell.find(f"./{_q('ac', 'structured-macro')}[@{_q('ac', 'name')}='panel']")
            if panel is not None:
                title = _get_param(panel, "title") or ""
                body = _convert_rich_body(_rich_body(panel), state).strip()
                meta_cells.append({"panel": {"title": title, "body": body}})
        if meta_cells:
            pub["meta"] = {"layout": t, "cells": meta_cells}
            state.consume(sec)
        break  # first meta layout only (spec §7)
    return pub


def _serialize_frontmatter(pub_meta: dict) -> str:
    """publication meta dict → frontmatter YAML string.

    Uses stdlib only (avoids yaml dependency — yaml could be imported, but for determinism
    we serialize manually. 2-space indent, consistent quoting, not alphabetical — follows spec input order).
    """
    if not pub_meta:
        return ""
    lines = ["---", "publication:"]
    if "header" in pub_meta:
        h = pub_meta["header"]
        lines.append("  header:")
        lines.append(f'    style: {h.get("style", "info")}')
        lines.append("    body: |")
        for ln in (h.get("body") or "").splitlines():
            lines.append(f"      {ln}")
    if "meta" in pub_meta:
        m = pub_meta["meta"]
        lines.append("  meta:")
        lines.append(f'    layout: {m.get("layout", "single")}')
        lines.append("    cells:")
        for cell in m.get("cells", []):
            if "change_history" in cell:
                lines.append(f'      - change_history: {cell["change_history"]}')
            elif "panel" in cell:
                p = cell["panel"]
                lines.append("      - panel:")
                title = (p.get("title") or "").replace('"', '\\"')
                lines.append(f'          title: "{title}"')
                lines.append("          body: |")
                for ln in (p.get("body") or "").splitlines():
                    lines.append(f"            {ln}")
    lines.append("---")
    return "\n".join(lines) + "\n"


# --- Phase 3 color handling (reserved, code prepared only) ------------------------------------
def _strip_color_spans(text: str) -> str:
    """Remove color span markup (restores clean MD, for diff comparison)."""
    # MD fenced span: [...]{.color-XXX} → body content only
    text = re.sub(r"\[([^\]]+)\]\{\.color-[a-z]+\}", r"\1", text)
    # Also remove leftover raw XML spans (for safety)
    text = _COLOR_SPAN_BARE_RE.sub(r"\1", text)
    return text


def _color_spans_to_md(text: str) -> str:
    """raw XML's <span style="color: rgb(...)">...</span> → [..]{.color-XXX}.

    This stage (Phase 1) is definition only — not called from main (used once Phase 3 is active).
    """
    def repl(m: re.Match) -> str:
        rgb = re.sub(r"\s+", "", m.group(1))
        cls = COLOR_RGB_TO_CLASS.get(rgb)
        inner = m.group(2)
        if cls is None:
            return inner  # unknown color → text only
        return f"[{inner}]{{.{cls}}}"
    return _COLOR_SPAN_RE.sub(repl, text)


# --- Main conversion entry point -------------------------------------------------------------
def convert_storage(
    xml: str,
    *,
    strip_colors: bool = False,
    extract_frontmatter: bool = True,
) -> tuple[str, _ConvState]:
    """storage XML → MD string (+ conversion state)."""
    state = _ConvState()
    root = parse_storage(xml)

    # frontmatter (best-effort)
    fm = ""
    if extract_frontmatter:
        pub_meta = _try_extract_publication_meta(root, state)
        if pub_meta:
            fm = _serialize_frontmatter({k: pub_meta[k] for k in ("header", "meta") if k in pub_meta})

    # Convert body
    body = _walk_body(root, state)
    # Normalize: collapse multiple blank lines, trim leading/trailing whitespace
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    # Color span handling (Phase 3D active):
    #   strip_colors=True  → fully removed (clean MD, for diff comparison)
    #   strip_colors=False → XML span → MD [..]{.color-XXX} conversion (round-trip preserved)
    if strip_colors:
        body = _strip_color_spans(body)
    else:
        body = _color_spans_to_md(body)

    out = (fm + "\n" + body + "\n") if fm else (body + "\n")
    return out, state


# --- I/O and CLI ---------------------------------------------------------------
def _read_input(path: Path, from_snapshot: bool) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if not from_snapshot:
        return raw
    # Extract body.storage.value from snapshot JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"snapshot JSON parse failed: {exc}") from exc
    body = (data.get("body") or {}).get("storage") or {}
    return body.get("value", "")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="storage_to_md",
        description="Confluence Storage Format (XHTML) → Markdown reverse conversion (spec: publication-syntax.md)",
    )
    parser.add_argument("--input", required=True, help="Input file (XML or snapshot JSON)")
    parser.add_argument("--output", required=True, help="Output MD path")
    parser.add_argument(
        "--from-snapshot",
        action="store_true",
        help="If the input is snapshot JSON from confluence_cli get, extract body.storage.value",
    )
    parser.add_argument(
        "--strip-colors",
        action="store_true",
        help="Remove Phase 3 color spans (restores clean MD, for diff comparison)",
    )
    parser.add_argument(
        "--no-frontmatter",
        action="store_true",
        help="Disable publication frontmatter extraction (output body only)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    in_path = Path(args.input)
    out_path = Path(args.output)

    if not in_path.is_file():
        print(f"[storage_to_md] ERROR: input file not found: {in_path}", file=sys.stderr)
        return 1

    try:
        xml = _read_input(in_path, args.from_snapshot)
    except ValueError as exc:
        print(f"[storage_to_md] ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        md, state = convert_storage(
            xml,
            strip_colors=args.strip_colors,
            extract_frontmatter=not args.no_frontmatter,
        )
    except ValueError as exc:
        print(f"[storage_to_md] ERROR: {exc}", file=sys.stderr)
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")

    for w in state.warnings:
        print(f"[storage_to_md] WARN: {w}", file=sys.stderr)
    if state.unsupported_macros:
        print(
            f"[storage_to_md] WARN: unsupported macros (text preserved): "
            f"{', '.join(state.unsupported_macros)}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
