#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""storage_to_md — Confluence Storage Format (XHTML) → Markdown 역변환기.

Option A (MD-only) 아키텍처에서 역방향 sync 용. Confluence snapshot XML 을
정본 MD 와 비교(diff/merge)할 수 있는 형태로 복원한다.

본 변환기는 `md_to_storage.py` 와 round-trip 정합성을 갖는다 (사양 §8/§9):
    md_to_storage(storage_to_md(X)) == X  (정규화 후)

사양 SSoT: `orange-pm-plugin/skills/render/publication-syntax.md`

기존 코드와의 관계:
    `render_sync_check.py::_strip_storage_xml` 및 `_convert_tables_to_markdown`
    의 로직을 흡수·확장한다. 향후 render_sync_check 는 본 모듈로 위임 가능.

CLI:
    python storage_to_md.py --input X.xml --output X.md [--strip-colors]
    python storage_to_md.py --input snapshot.json --from-snapshot --output X.md

종료 코드:
    0  성공
    1  XML/JSON 파싱 실패
    2  미지원 매크로 발견 (텍스트 보존, non-blocking 경고)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

# --- I/O 인코딩 정합 ----------------------------------------------------------
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

# --- Namespaces ---------------------------------------------------------------
# Confluence Storage Format 은 ac:/ri: prefix 를 쓰지만 보통 XML 선언 없이
# fragment 로 제공된다. parse_storage 에서 root 로 감싸고 xmlns 를 주입한다.
NS = {
    "ac": "http://atlassian.com/content",
    "ri": "http://atlassian.com/resource/identifier",
}
# ET API 에서 쓸 prefixed 태그 (Clark notation)
def _q(prefix: str, local: str) -> str:
    return f"{{{NS[prefix]}}}{local}"

# --- 사양 §3.1 Panel style 매핑 (역방향) --------------------------------------
# borderColor 만으로 식별. md_to_storage 와 1:1 대응 (사양 §3.1 표).
PANEL_STYLE_BY_BORDER = {
    "#24FE00": "common",    # 기본 (생략됨)
    "#0050E5": "product",
    "#FF4D4F": "tbd",
    "#FAAD14": "warning",
    "#1890FF": "info",
}

SUPPORTED_FENCED_DIV_MACROS = {"panel", "info", "warning", "note", "tip", "expand"}

# Phase 3 색상 매핑 (예약). md_to_storage 와 1:1 대응 (사양 §6).
COLOR_RGB_TO_CLASS = {
    "rgb(0,176,80)": "color-green",
    "rgb(0,80,229)": "color-blue",
}
# 정확한 매칭을 위해 공백 변형도 허용 (re 로 처리).
_COLOR_SPAN_RE = re.compile(
    r'<span\s+style\s*=\s*"color:\s*(rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\))\s*"\s*>(.*?)</span>',
    re.DOTALL | re.IGNORECASE,
)
_COLOR_SPAN_BARE_RE = re.compile(
    r'<span\s+style\s*=\s*"color:[^"]*"\s*>(.*?)</span>',
    re.DOTALL | re.IGNORECASE,
)


# --- 상태 컨테이너 -----------------------------------------------------------
class _ConvState:
    """변환 중 누적되는 상태 (경고 등). stderr 출력은 main 에서 종합.

    consumed_sections: frontmatter 로 흡수된 layout-section 의 id(Element) 집합.
    body walk 단계에서 중복 emit 방지 (사양 §7 — frontmatter 흡수 영역은 본문 제외).
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


# --- XML 파싱 -----------------------------------------------------------------
def parse_storage(text: str) -> ET.Element:
    """Confluence Storage Format fragment 를 ET.Element 로 파싱.

    fragment 에는 보통 XML 선언이나 namespace 가 없으므로 root 로 감싸고
    xmlns:ac/ri 를 주입한다. 단일 root 보장.
    """
    if not text or not text.strip():
        # 빈 입력은 빈 root 반환 (오류 아님)
        return ET.fromstring(
            '<root xmlns:ac="http://atlassian.com/content" '
            'xmlns:ri="http://atlassian.com/resource/identifier"/>'
        )
    # HTML entity 일부 보존 (&nbsp; 등은 XML 표준 아님 — 수동 치환).
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
        raise ValueError(f"Storage Format XML 파싱 실패: {exc}") from exc


# --- Helpers ------------------------------------------------------------------
def _inner_text(elem: ET.Element) -> str:
    """elem 의 모든 텍스트(자식 포함) 평탄화. 줄바꿈/들여쓰기는 단일 공백 압축."""
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
    """ac:parameter ac:name=... 값을 추출 (없으면 None)."""
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


# --- 인라인 변환 (텍스트 + 인라인 자식) ---------------------------------------
def _inline_to_md(elem: ET.Element, state: _ConvState) -> str:
    """elem 의 자식들을 인라인 MD 로 변환 (블록 요소는 별도 처리).

    elem 자체의 tag 는 사용하지 않고 본문만 변환한다.
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
    """단일 인라인 노드를 MD 문자열로."""
    tag = _strip_ns(node.tag)
    ns = _ns_of(node.tag)

    # ac:link → page link
    if ns == "ac" and tag == "link":
        return _convert_page_link(node, state)
    # ac:structured-macro (인라인 일부 — toc, change-history 는 보통 블록이나
    # frontmatter 의 panel body 내부에 인라인 등장)
    if ns == "ac" and tag == "structured-macro":
        return _convert_macro(node, state)

    # 일반 HTML 인라인
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
        # Phase 3D — 색상 span 직접 처리.
        # ET 파싱 후엔 raw XML markup 이 사라져 후처리 regex 가 동작하지 않으므로
        # 여기서 직접 style 속성을 읽어 MD fenced span 으로 emit.
        # convert_storage 의 strip_colors 후처리는 fallback (raw XML 잔존 시 보완).
        inner = _inline_to_md(node, state)
        style = (node.get("style") or "").replace(" ", "")
        m = re.match(r"color:(rgb\(\d+,\d+,\d+\))", style)
        if m:
            cls = COLOR_RGB_TO_CLASS.get(m.group(1))
            if cls:
                return f"[{inner}]{{.{cls}}}"
        # 알 수 없는 색상/스타일 → 텍스트만
        return inner

    # fallback: 자식 텍스트만 흘림 (미지원 인라인 태그)
    return _inline_to_md(node, state)


def _strip_ns(qname: str) -> str:
    if qname.startswith("{"):
        return qname.split("}", 1)[1]
    return qname


def _ns_of(qname: str) -> str | None:
    """tag 의 ns prefix (ac/ri) 또는 None (HTML)."""
    if not qname.startswith("{"):
        return None
    uri = qname[1:].split("}", 1)[0]
    for prefix, full in NS.items():
        if full == uri:
            return prefix
    return None


# --- 매크로 변환 --------------------------------------------------------------
def _convert_page_link(link: ET.Element, state: _ConvState) -> str:
    page = link.find(_q("ri", "page"))
    if page is not None:
        title = page.get(_q("ri", "content-title")) or ""
        if title:
            return f"[[page:{title}]]"
    # ri:user 등은 Phase 4 (사양 §4.2 — 현재는 텍스트 보존)
    user = link.find(_q("ri", "user"))
    if user is not None:
        key = user.get(_q("ri", "userkey")) or user.get(_q("ri", "account-id")) or ""
        state.unsupported(f"ri:user (Phase 4 예약): {key}")
        return f"[[user:{key}]]" if key else ""
    # 알 수 없는 ac:link → 텍스트만 흘림
    return _inline_to_md(link, state)


def _convert_macro(macro: ET.Element, state: _ConvState) -> str:
    """ac:structured-macro → MD 문자열 (블록/인라인 자동).

    인라인 컨텍스트에서도 toc / change-history 는 그대로 {{}} placeholder.
    panel/info/warning/note/tip/expand 는 본문 흐름에 \n 으로 구분된
    fenced div block 으로 출력 (caller 가 적절히 위치).
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
        # 사양 §3.4 — Phase 2 이후. 본문 텍스트 보존.
        body = _plain_body(macro) or _convert_rich_body(_rich_body(macro), state)
        return f"\n```mermaid\n{body.rstrip()}\n```\n"

    # 미지원 매크로 → 본문 텍스트 보존 + 경고
    state.unsupported(name)
    rb = _rich_body(macro)
    if rb is not None:
        return _convert_rich_body(rb, state)
    pb = _plain_body(macro)
    if pb:
        return pb
    return ""


def _convert_code_macro(macro: ET.Element) -> str:
    """code 매크로 → fenced code block (사양 §3.5)."""
    lang = _get_param(macro, "language") or ""
    body = _plain_body(macro) or ""
    # CDATA 내부 본문이 직접 들어오므로 줄바꿈 보존
    fence_lang = lang if lang else ""
    # 끝 trailing newline 정리
    body = body.rstrip("\n")
    return f"\n```{fence_lang}\n{body}\n```\n"


def _convert_panel(macro: ET.Element, state: _ConvState) -> str:
    """panel 매크로 → ::: {.panel section="..." style="..."} (사양 §3.1)."""
    params = _get_all_params(macro)
    section = params.get("title", "")
    border = params.get("borderColor", "").strip()
    # 기본 style 식별
    style = PANEL_STYLE_BY_BORDER.get(border, "")
    # common (기본) 은 round-trip 시 생략 (사양 §8: 기본 style 은 round-trip 시 생략).
    attrs = [".panel"]
    if section:
        # section 값에 따옴표가 있으면 escape (드물지만 보호)
        sec_esc = section.replace('"', '\\"')
        attrs.append(f'section="{sec_esc}"')
    if style and style != "common":
        attrs.append(f'style="{style}"')
    elif border and style == "":
        # 알 수 없는 borderColor → 사용자 정의로 보존 (raw value)
        attrs.append(f'style="{border}"')
        state.warn(f"알 수 없는 panel borderColor 보존: {border}")
    header = "::: {" + " ".join(attrs) + "}"
    body = _convert_rich_body(_rich_body(macro), state).strip()
    return f"\n{header}\n{body}\n:::\n"


# --- Rich body / 블록 본문 ----------------------------------------------------
def _convert_rich_body(body: ET.Element | None, state: _ConvState) -> str:
    if body is None:
        return ""
    out = _walk_body(body, state)
    # 다중 빈 줄 압축
    return re.sub(r"\n{3,}", "\n\n", out)


def _walk_body(elem: ET.Element, state: _ConvState) -> str:
    """블록 컨테이너의 자식들을 순회하며 MD 로 변환.

    elem 자체는 변환하지 않고 elem.text + 자식들을 처리한다 (rich-text-body 등
    의 컨테이너 변환에 사용).
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
    """단일 블록 노드를 MD 로."""
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
        # 기타 ac:* 는 본문만 흘림
        return _walk_body(node, state)

    # 표준 HTML 블록 ------------------------------------------------------------
    if re.fullmatch(r"h[1-6]", tag):
        level = int(tag[1])
        inner = _inline_to_md(node, state).strip()
        return f"\n{'#' * level} {inner}\n\n"
    if tag == "p":
        inner = _inline_to_md(node, state).rstrip()
        # spacer (<p><br/></p>) 는 빈 줄로
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
        # 색상 span 은 후처리에서 (raw XML 마커가 더 안전). 여기서는 인라인 텍스트만.
        return _inline_node(node, state)

    # fallback
    return _inline_node(node, state)


# --- Layout (사양 §7) ---------------------------------------------------------
def _convert_layout(layout: ET.Element, state: _ConvState) -> str:
    """ac:layout 컨테이너 → 자식 layout-section 순회."""
    return _walk_body(layout, state)


def _convert_layout_section(section: ET.Element, state: _ConvState) -> str:
    """ac:layout-section → 사양 §7 역방향.

    - frontmatter 로 흡수된 section (state.is_consumed) → 빈 출력 (중복 emit 차단)
    - single + panel 1개 → panel 본문만 (자동 layout 래퍼 stripping)
    - spacer (<p><br/></p> 만) → 무시 (빈 줄)
    - meta layout (two_equal / three_equal 등) → 그대로 본문 흘림. frontmatter
      재구성은 best-effort 로 main 단계에서 시도하나, 본 함수는 본문 평탄화 우선.
    """
    if state.is_consumed(section):
        return ""
    cells = section.findall(_q("ac", "layout-cell"))
    # spacer 판정: 모든 cell 이 비어있거나 <p><br/></p> 만
    if all(_is_spacer_cell(c) for c in cells):
        return "\n"
    # single + 단일 panel cell → fenced div 만 노출
    if len(cells) == 1:
        return _walk_body(cells[0], state)
    # multi-cell layout → 각 cell 본문을 순차 출력 (best-effort 평탄화)
    pieces = [_walk_body(c, state) for c in cells]
    return "\n" + "\n".join(p.strip() for p in pieces if p.strip()) + "\n"


def _is_spacer_cell(cell: ET.Element) -> bool:
    """cell 이 빈 spacer 인지 (<p><br/></p> 류). 보수적으로 판단."""
    text = _inner_text(cell)
    if text:
        return False
    # 매크로/표/링크가 하나라도 있으면 spacer 아님
    for tag_name in ("structured-macro", "link"):
        if cell.findall(f".//{_q('ac', tag_name)}"):
            return False
    if cell.findall(".//table") or cell.findall(".//img"):
        return False
    return True


# --- List ---------------------------------------------------------------------
def _convert_list(node: ET.Element, state: _ConvState, *, ordered: bool, depth: int = 0) -> str:
    """ul/ol → MD list. 중첩 지원."""
    items: list[str] = []
    for idx, li in enumerate(node.findall("li"), start=1):
        prefix = f"{idx}. " if ordered else "- "
        indent = "  " * depth
        # li 의 직접 텍스트/인라인 + 중첩 ul/ol
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
                # li 안의 p 는 인라인으로 평탄화
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

    - colgroup 의 width 가 균등하지 않으면 `<!-- col-widths: a%, b%, ... -->`
      directive 자동 삽입 (사양 §5.1).
    - thead / tbody 둘 다 처리. 헤더 행이 없으면 첫 행을 헤더로 간주.
    """
    # 컬럼 너비 추출 -----------------------------------------------------------
    widths: list[str] = []
    colgroup = table.find("colgroup")
    if colgroup is not None:
        for col in colgroup.findall("col"):
            style = col.get("style", "")
            m = re.search(r"width\s*:\s*([\d.]+%)", style)
            widths.append(m.group(1) if m else "")

    # 모든 행 수집 (thead 우선) -----------------------------------------------
    head_rows: list[ET.Element] = []
    body_rows: list[ET.Element] = []
    thead = table.find("thead")
    if thead is not None:
        head_rows = thead.findall("tr")
    tbody = table.find("tbody")
    if tbody is not None:
        body_rows = tbody.findall("tr")
    # tbody/thead 없이 직접 tr 가 있을 수도 있음
    if not head_rows and not body_rows:
        body_rows = table.findall("tr")

    all_rows = head_rows + body_rows
    if not all_rows:
        return "\n"

    # 첫 행이 헤더 (thead 없으면 첫 tbody 행을 헤더로 간주 — 사양 §5)
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
        # 컬럼 수 맞추기
        if len(cells) < n_cols:
            cells = cells + [""] * (n_cols - len(cells))
        md_lines.append("| " + " | ".join(cells[:n_cols]) + " |")

    # 컬럼 너비 directive (균등 여부 판단) -----------------------------------
    directive = ""
    if widths and len(widths) == n_cols and any(widths):
        # 균등 분배인지 (각 width 가 같은 정수 % 인지) 검사
        nums: list[float] = []
        for w in widths:
            try:
                nums.append(float(w.rstrip("%")))
            except ValueError:
                nums.append(0.0)
        if nums:
            even = max(nums) - min(nums) < 1.0  # 1% 이내 → 균등
            if not even:
                directive = "<!-- col-widths: " + ", ".join(widths) + " -->\n"

    return "\n" + directive + "\n".join(md_lines) + "\n"


# --- Frontmatter 재구성 (best-effort) -----------------------------------------
def _try_extract_publication_meta(root: ET.Element, state: _ConvState) -> dict:
    """root 의 첫 layout-section 들을 보고 publication.header / meta 추정.

    완벽한 round-trip 은 보장 안 함 — best-effort (사양 §8 △).
    추출 성공 시 dict 반환, 실패 시 빈 dict.
    """
    pub: dict = {}
    layout = root.find(_q("ac", "layout"))
    if layout is None:
        # root 직속 layout-section 들도 탐색
        sections = root.findall(_q("ac", "layout-section"))
    else:
        sections = layout.findall(_q("ac", "layout-section"))
    if not sections:
        return pub

    # header: 첫 single section + 단일 cell + info/warning 매크로
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

    # meta: type != single 인 첫 section
    for sec in sections:
        t = sec.get(_q("ac", "type")) or "single"
        if t == "single":
            continue
        cells = sec.findall(_q("ac", "layout-cell"))
        meta_cells: list[dict] = []
        for cell in cells:
            ch_macro = cell.find(f"./{_q('ac', 'structured-macro')}[@{_q('ac', 'name')}='change-history']")
            if ch_macro is None:
                # 일부 cell 은 <p> 안에 있음
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
        break  # 첫 meta layout 만 (사양 §7)
    return pub


def _serialize_frontmatter(pub_meta: dict) -> str:
    """publication meta dict → frontmatter YAML 문자열.

    stdlib 만 사용 (yaml 의존 회피 — yaml 은 import 가능하나 결정성 위해 수동
    직렬화. 들여쓰기 2칸, 따옴표 일관, 알파벳 순 아님 = 사양 입력 순).
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


# --- Phase 3 색상 처리 (예약, 코드만 준비) ------------------------------------
def _strip_color_spans(text: str) -> str:
    """color span 마크업 제거 (clean MD 복원, diff 비교용)."""
    # MD fenced span: [...]{.color-XXX} → 본문만
    text = re.sub(r"\[([^\]]+)\]\{\.color-[a-z]+\}", r"\1", text)
    # 누락된 raw XML span 도 제거 (안전)
    text = _COLOR_SPAN_BARE_RE.sub(r"\1", text)
    return text


def _color_spans_to_md(text: str) -> str:
    """raw XML 의 <span style="color: rgb(...)">...</span> → [..]{.color-XXX}.

    이번 단계(Phase 1)는 정의만 — main 에서 호출 안 함 (Phase 3 활성 시).
    """
    def repl(m: re.Match) -> str:
        rgb = re.sub(r"\s+", "", m.group(1))
        cls = COLOR_RGB_TO_CLASS.get(rgb)
        inner = m.group(2)
        if cls is None:
            return inner  # 알 수 없는 색상 → 텍스트만
        return f"[{inner}]{{.{cls}}}"
    return _COLOR_SPAN_RE.sub(repl, text)


# --- 본 변환 진입 -------------------------------------------------------------
def convert_storage(
    xml: str,
    *,
    strip_colors: bool = False,
    extract_frontmatter: bool = True,
) -> tuple[str, _ConvState]:
    """storage XML → MD 문자열 (+ 변환 상태)."""
    state = _ConvState()
    root = parse_storage(xml)

    # frontmatter (best-effort)
    fm = ""
    if extract_frontmatter:
        pub_meta = _try_extract_publication_meta(root, state)
        if pub_meta:
            fm = _serialize_frontmatter({k: pub_meta[k] for k in ("header", "meta") if k in pub_meta})

    # 본문 변환
    body = _walk_body(root, state)
    # 정규화: 다중 빈 줄 압축, 양끝 공백 제거
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    # 색상 span 처리 (Phase 3D 활성):
    #   strip_colors=True  → 완전 제거 (clean MD, diff 비교용)
    #   strip_colors=False → XML span → MD [..]{.color-XXX} 변환 (round-trip 보존)
    if strip_colors:
        body = _strip_color_spans(body)
    else:
        body = _color_spans_to_md(body)

    out = (fm + "\n" + body + "\n") if fm else (body + "\n")
    return out, state


# --- I/O 및 CLI ---------------------------------------------------------------
def _read_input(path: Path, from_snapshot: bool) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if not from_snapshot:
        return raw
    # snapshot JSON 에서 body.storage.value 추출
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"snapshot JSON 파싱 실패: {exc}") from exc
    body = (data.get("body") or {}).get("storage") or {}
    return body.get("value", "")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="storage_to_md",
        description="Confluence Storage Format (XHTML) → Markdown 역변환 (사양: publication-syntax.md)",
    )
    parser.add_argument("--input", required=True, help="입력 파일 (XML 또는 snapshot JSON)")
    parser.add_argument("--output", required=True, help="출력 MD 경로")
    parser.add_argument(
        "--from-snapshot",
        action="store_true",
        help="입력이 confluence_cli get 의 snapshot JSON 인 경우 body.storage.value 추출",
    )
    parser.add_argument(
        "--strip-colors",
        action="store_true",
        help="Phase 3 색상 span 제거 (clean MD 복원, diff 비교용)",
    )
    parser.add_argument(
        "--no-frontmatter",
        action="store_true",
        help="publication frontmatter 추출 비활성 (본문만 출력)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    in_path = Path(args.input)
    out_path = Path(args.output)

    if not in_path.is_file():
        print(f"[storage_to_md] ERROR: 입력 파일 없음: {in_path}", file=sys.stderr)
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
            f"[storage_to_md] WARN: 미지원 매크로 (텍스트 보존): "
            f"{', '.join(state.unsupported_macros)}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
