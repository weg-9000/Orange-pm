#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Block-level diff library — foundation for Phase 3 color cycling.

This module identifies changed regions between two versions of a publication-targeted
MD document, at *block granularity*. The spec SSoT is
``orange-pm-plugin/skills/render/publication-syntax.md``
§6 "Color Span (Phase 3 reserved)", and the region info this module outputs is
consumed by the color-span insertion step of ``md_to_storage``.

Design decisions (spec finalized in earlier phase discussions):

* **Region definition**: a ``(logical path, block_hash)`` tuple.
* **Block granularity**:
    - paragraph     : one paragraph
    - heading       : one heading (when its text changes)
    - list_item     : one list item (nested path when nested)
    - table_cell    : per table cell (not per row)
    - code          : entire code block (no inner span — forbidden by spec §6)
    - panel_inner_para : a paragraph inside a panel/info/warning
* **Region identifier example**: ``§3 Policy/§3.1/<p[2]>``
* **2-cycle decay**::

    N=1: G_1 = ∅ (all black — first draft)
    N=2: G_2 = diff(v1, v2) → green; B_2 = ∅
    N=3: G_3 = diff(v2, v3) → green; B_3 = G_2 \\ G_3 → blue
    N=k: G_k = diff(v_{k-1}, v_k) → green; B_k = G_{k-1} \\ G_k → blue

  If the same path is also in ``previous_green`` and changed again this time →
  green only (does not become blue; so "decay" doesn't occur on redundant changes).

* **frontmatter**: ignored (publication.* changes are not subject to cycling).

This module is ``stdlib only`` (re, hashlib, dataclasses, json, argparse).
It reproduces some of the same regexes used by ``md_to_storage``, but does not
import that module — the two modules should be able to evolve independently.

CLI (for debugging):
    python diff_blocks.py --old v1.md --new v2.md \\
        [--previous-green file.json] [--format json|md]

exit code:
    0 = success
    1 = I/O error
    2 = argument error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


# ── Regexes (same patterns as md_to_storage) ────────────────────────────────

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
COLWIDTHS_DIRECTIVE_RE = re.compile(r"^\s*<!--\s*col-widths\s*:\s*([^>]+?)\s*-->\s*$")
ATTR_CLASS_RE = re.compile(r"\.([\w\-]+)")
ATTR_KV_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')

# Inline code (`...`) and strong/em etc. are unrelated to path — they only affect
# content normalization.
MULTI_SPACE_RE = re.compile(r"\s+")

CALLOUT_CLASSES = {"info", "warning", "note", "tip"}

# Block kind enumeration — string constants that can be referenced externally.
KIND_PARAGRAPH = "paragraph"
KIND_HEADING = "heading"
KIND_LIST_ITEM = "list_item"
KIND_TABLE_CELL = "table_cell"
KIND_CODE = "code"
KIND_PANEL_INNER_PARA = "panel_inner_para"
KIND_BLOCKQUOTE_PARA = "blockquote_para"


# ── Dataclass ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Block:
    """Representation of a single region — a (path, content, hash) triple + position metadata.

    Attributes:
        kind: block kind (one of the KIND_* constants).
        path: logical path — heading hierarchy + block position index.
              e.g. ``"§3 Policy/§3.1 Standard Pricing/<p[2]>"``.
        content: normalized block body text (leading/trailing whitespace stripped,
                 multiple spaces collapsed to one; inline markers are kept as-is
                 and used for change detection).
        block_hash: first 16 chars of sha256(content) (64-bit equivalent — unique enough).
        line_start: 1-based start line in the source (-1 = unknown, e.g. on deserialize).
        line_end: 1-based inclusive end line in the source (-1 = unknown).
        raw_content: original source text (pre-normalization, for color span injection).
                     Only meaningful when line info is present (not -1).
    """

    kind: str
    path: str
    content: str
    block_hash: str
    line_start: int = -1
    line_end: int = -1
    raw_content: str = ""

    def to_dict(self) -> dict:
        d = {
            "kind": self.kind,
            "path": self.path,
            "content": self.content,
            "block_hash": self.block_hash,
        }
        if self.line_start >= 0:
            d["line_start"] = self.line_start
            d["line_end"] = self.line_end
        return d


@dataclass
class DiffResult:
    """Result of ``diff_blocks(old, new)``.

    Matching criterion: exact ``path`` match → compare ``block_hash``.
    """

    added: list[Block] = field(default_factory=list)
    removed: list[Block] = field(default_factory=list)
    modified: list[tuple[Block, Block]] = field(default_factory=list)
    unchanged: list[Block] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "added": len(self.added),
            "removed": len(self.removed),
            "modified": len(self.modified),
            "unchanged": len(self.unchanged),
        }


@dataclass
class ColorRegions:
    """Output of the 2-cycle decay model.

    Attributes:
        green: blocks changed in this publish (added + the new side of modified).
        blue: previous publish's green region that was not changed again this time.
    """

    green: list[Block] = field(default_factory=list)
    blue: list[Block] = field(default_factory=list)


# ── Internal utilities ───────────────────────────────────────────────────────


def _normalize_content(text: str) -> str:
    """Normalize block body text — for comparison stability.

    - Strip leading/trailing whitespace
    - Collapse all whitespace (including tabs/newlines) to a single space
    - Empty string if the block consists only of blank lines
    """
    if not text:
        return ""
    return MULTI_SPACE_RE.sub(" ", text).strip()


def _block_hash(content: str) -> str:
    """First 16 chars of the SHA-256(content) hex digest (64-bit space)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _strip_frontmatter(md_text: str) -> str:
    """Strip the frontmatter region (publication.* is not subject to cycling — per spec §6).

    Returns the text unchanged if there is no frontmatter.
    """
    m = FRONTMATTER_RE.match(md_text)
    if not m:
        return md_text
    return md_text[m.end():]


def _parse_div_attrs(attr_text: str) -> tuple[list[str], dict[str, str]]:
    """``.panel section="X" style="tbd"`` → (['panel'], {section:X, style:tbd})."""
    classes = ATTR_CLASS_RE.findall(attr_text)
    kvs = dict(ATTR_KV_RE.findall(attr_text))
    return classes, kvs


def _split_table_row(line: str) -> list[str]:
    """| a | b | → ['a', 'b'] (strips surrounding whitespace and the outer |)."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _heading_path_join(parts: list[str]) -> str:
    """Join heading hierarchy with ``/``. Empty stack → ``""``."""
    return "/".join(p for p in parts if p)


# ── Heading path tracking ────────────────────────────────────────────────────


class _HeadingStack:
    """Manages the h1-h6 heading hierarchy as a stack.

    When h_k appears, truncate the stack to length k (`stack[:k-1]`) then push
    the text. ``current_path()`` returns the join of all levels.
    """

    def __init__(self) -> None:
        # index = level-1 (0-based). Empty slots are the empty string.
        self._levels: list[str] = []

    def push(self, level: int, text: str) -> None:
        # drop deeper levels
        if len(self._levels) >= level:
            self._levels = self._levels[: level - 1]
        # pad empty slots
        while len(self._levels) < level - 1:
            self._levels.append("")
        self._levels.append(text)

    def current_path(self) -> str:
        return _heading_path_join(self._levels)


# ── Block parser (main) ──────────────────────────────────────────────────────


def parse_blocks(md_text: str) -> list[Block]:
    """MD text → ``list[Block]``.

    State machine:
        1. Strip frontmatter
        2. Walk lines, maintaining the panel container stack + heading hierarchy stack
        3. Identify each block (paragraph/heading/list_item/table_cell/code) → emit Block

    Notes:
        - A paragraph inside a panel is tagged ``kind=panel_inner_para`` (per spec:
          macro bodies like panel/info are tracked at inner-paragraph granularity).
        - This function does *not* interpret inline macros (e.g. ``[[page:...]]``) —
          it includes the raw text as-is in the hash input, used as a change-detection
          signal.
        - A paragraph spanning multiple lines is joined with a single space before hashing.
    """
    body = _strip_frontmatter(md_text)
    lines = body.splitlines()

    blocks: list[Block] = []
    heading_stack = _HeadingStack()

    # panel container stack — included in the path prefix while a fenced div
    # ``.panel`` is active. Each entry: (kind, path_segment, inner_para_counter)
    container_stack: list[dict] = []

    # block position index — reset when the heading changes.
    # key = path prefix, value = dict(kind -> next_index)
    position_counters: dict[str, dict[str, int]] = {}

    def _next_idx(prefix: str, marker: str) -> int:
        if prefix not in position_counters:
            position_counters[prefix] = {}
        cur = position_counters[prefix].get(marker, 0) + 1
        position_counters[prefix][marker] = cur
        return cur

    def _reset_indices_for(prefix: str) -> None:
        position_counters.pop(prefix, None)

    def _container_prefix() -> str:
        return "/".join(c["path_segment"] for c in container_stack)

    def _full_prefix() -> str:
        """Join heading + container path."""
        h = heading_stack.current_path()
        c = _container_prefix()
        if h and c:
            return f"{h}/{c}"
        return h or c

    def _emit(kind: str, marker: str, content: str) -> None:
        """Block emit helper.

        marker: the notation for the last path segment (e.g. ``<p>``, ``<h2>``).
                Gets an index appended, expanding to e.g. ``<p[2]>``.
        """
        norm = _normalize_content(content)
        if not norm:
            return  # an empty block is meaningless as a region
        prefix = _full_prefix()
        idx = _next_idx(prefix, marker)
        leaf = f"{marker[:-1]}[{idx}]>"  # <p> → <p[1]>
        path = f"{prefix}/{leaf}" if prefix else leaf
        blocks.append(
            Block(kind=kind, path=path, content=norm, block_hash=_block_hash(norm))
        )

    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # fenced div open
        m_div_open = FENCED_DIV_OPEN_RE.match(line)
        if m_div_open:
            classes, kvs = _parse_div_attrs(m_div_open.group(1))
            primary = classes[0] if classes else ""
            if primary == "panel":
                section = kvs.get("section", "").strip() or "panel"
                container_stack.append(
                    {"kind": "panel", "path_segment": section}
                )
            elif primary in CALLOUT_CLASSES:
                container_stack.append(
                    {"kind": primary, "path_segment": f"<{primary}>"}
                )
            elif primary == "expand":
                title = kvs.get("title", "").strip() or "expand"
                container_stack.append(
                    {"kind": "expand", "path_segment": f"<expand:{title}>"}
                )
            else:
                container_stack.append(
                    {"kind": primary or "div", "path_segment": f"<div:{primary}>"}
                )
            # entering a container — reset the index for this prefix
            _reset_indices_for(_full_prefix())
            i += 1
            continue

        # fenced div close
        if FENCED_DIV_CLOSE_RE.match(line):
            if container_stack:
                container_stack.pop()
            i += 1
            continue

        # code fence — treat the whole thing as one code block
        m_code = CODE_FENCE_RE.match(line)
        if m_code:
            lang = m_code.group(1) or ""
            buf: list[str] = []
            i += 1
            while i < n and not CODE_FENCE_RE.match(lines[i]):
                buf.append(lines[i])
                i += 1
            if i < n:
                i += 1  # consume closing fence
            # code is hashed as-is without normalization (indentation is significant)
            raw = "\n".join(buf)
            prefix = _full_prefix()
            marker = f"<code:{lang}>" if lang else "<code>"
            idx = _next_idx(prefix, marker)
            leaf = f"{marker[:-1]}[{idx}]>"
            path = f"{prefix}/{leaf}" if prefix else leaf
            # keep even an empty code block as a region (for change tracking)
            blocks.append(
                Block(
                    kind=KIND_CODE,
                    path=path,
                    content=raw,
                    block_hash=_block_hash(raw),
                )
            )
            continue

        # col-widths directive — ignored (no effect on path/region)
        if COLWIDTHS_DIRECTIVE_RE.match(line):
            i += 1
            continue

        # heading
        m_h = HEADING_RE.match(line)
        if m_h:
            level = len(m_h.group(1))
            text = m_h.group(2).strip()
            # the heading text itself is a block — a region occurs when it changes
            # update heading_stack *then* compute path, so it becomes its own leaf
            heading_stack.push(level, text)
            # entering a new heading path — reset the index for this prefix
            new_prefix = _full_prefix()
            _reset_indices_for(new_prefix)
            # a heading block's path shows itself as the leaf
            marker = f"<h{level}>"
            idx = _next_idx(new_prefix, marker)
            leaf = f"{marker[:-1]}[{idx}]>"
            path = f"{new_prefix}/{leaf}" if new_prefix else leaf
            content = _normalize_content(text)
            blocks.append(
                Block(
                    kind=KIND_HEADING,
                    path=path,
                    content=content,
                    block_hash=_block_hash(content),
                )
            )
            i += 1
            continue

        # hr — not a region (a style element)
        if HR_RE.match(line):
            i += 1
            continue

        # blank line
        if not stripped:
            i += 1
            continue

        # table — header row + parse rows/cells starting after the separator
        if "|" in line and i + 1 < n and TABLE_SEPARATOR_RE.match(lines[i + 1]):
            header_cells = _split_table_row(line)
            prefix = _full_prefix()
            tbl_idx = _next_idx(prefix, "<table>")
            tbl_marker = f"<table[{tbl_idx}]>"
            # header cells
            for ci, cell in enumerate(header_cells, start=1):
                norm = _normalize_content(cell)
                if not norm:
                    continue
                path = (
                    f"{prefix}/{tbl_marker}/<th[{ci}]>"
                    if prefix else f"{tbl_marker}/<th[{ci}]>"
                )
                blocks.append(
                    Block(
                        kind=KIND_TABLE_CELL,
                        path=path,
                        content=norm,
                        block_hash=_block_hash(norm),
                    )
                )
            i += 2  # skip header + separator
            row_no = 0
            while i < n and "|" in lines[i] and lines[i].strip():
                if TABLE_SEPARATOR_RE.match(lines[i]):
                    break
                row_no += 1
                cells = _split_table_row(lines[i])
                for ci, cell in enumerate(cells, start=1):
                    norm = _normalize_content(cell)
                    if not norm:
                        continue
                    path = (
                        f"{prefix}/{tbl_marker}/<tr[{row_no}]>/<td[{ci}]>"
                        if prefix
                        else f"{tbl_marker}/<tr[{row_no}]>/<td[{ci}]>"
                    )
                    blocks.append(
                        Block(
                            kind=KIND_TABLE_CELL,
                            path=path,
                            content=norm,
                            block_hash=_block_hash(norm),
                        )
                    )
                i += 1
            continue

        # list (ul / ol) — one list_item block per item
        m_ul = UL_RE.match(line)
        m_ol = OL_RE.match(line)
        if m_ul or m_ol:
            prefix = _full_prefix()
            list_idx = _next_idx(prefix, "<list>")
            list_marker = f"<list[{list_idx}]>"
            # per-depth item counter (depth chain included in the path)
            depth_counters: dict[int, int] = {}
            depth_stack: list[int] = []  # order of depth levels seen so far
            while i < n:
                cur = lines[i]
                if not cur.strip():
                    break
                m = UL_RE.match(cur) or OL_RE.match(cur)
                if not m:
                    break
                indent_ws = m.group(1)
                depth = len(indent_ws) // 2
                # reset deeper counters when entering a shallower depth
                for d in list(depth_counters.keys()):
                    if d > depth:
                        depth_counters[d] = 0
                # adjust depth_stack
                while depth_stack and depth_stack[-1] > depth:
                    depth_stack.pop()
                if not depth_stack or depth_stack[-1] < depth:
                    depth_stack.append(depth)
                # increment counter
                depth_counters[depth] = depth_counters.get(depth, 0) + 1
                # list_item chain notation in the path — per-depth index
                chain_parts = []
                for d in sorted(set(depth_stack)):
                    chain_parts.append(f"<li[{depth_counters.get(d, 1)}]>")
                chain = "/".join(chain_parts)
                norm = _normalize_content(m.group(2))
                if norm:
                    path = (
                        f"{prefix}/{list_marker}/{chain}"
                        if prefix
                        else f"{list_marker}/{chain}"
                    )
                    blocks.append(
                        Block(
                            kind=KIND_LIST_ITEM,
                            path=path,
                            content=norm,
                            block_hash=_block_hash(norm),
                        )
                    )
                i += 1
            continue

        # blockquote — each inner paragraph becomes blockquote_para
        m_bq = BLOCKQUOTE_RE.match(line)
        if m_bq:
            bq_lines: list[str] = [m_bq.group(1)]
            i += 1
            while i < n:
                m2 = BLOCKQUOTE_RE.match(lines[i])
                if not m2:
                    break
                bq_lines.append(m2.group(1))
                i += 1
            text = " ".join(s for s in bq_lines if s.strip())
            _emit(KIND_BLOCKQUOTE_PARA, "<bq>", text)
            continue

        # paragraph — accumulate until a blank line / another block starts
        para_lines = [stripped]
        i += 1
        while i < n:
            nxt = lines[i]
            if not nxt.strip():
                break
            if (
                HEADING_RE.match(nxt)
                or HR_RE.match(nxt)
                or CODE_FENCE_RE.match(nxt)
                or UL_RE.match(nxt)
                or OL_RE.match(nxt)
                or BLOCKQUOTE_RE.match(nxt)
                or FENCED_DIV_OPEN_RE.match(nxt)
                or FENCED_DIV_CLOSE_RE.match(nxt)
                or COLWIDTHS_DIRECTIVE_RE.match(nxt)
            ):
                break
            if (
                "|" in nxt
                and i + 1 < n
                and TABLE_SEPARATOR_RE.match(lines[i + 1])
            ):
                break
            para_lines.append(nxt.strip())
            i += 1
        para = " ".join(para_lines)
        # a paragraph inside a container (panel/info/...) gets a distinct kind
        if container_stack:
            kind = KIND_PANEL_INNER_PARA
        else:
            kind = KIND_PARAGRAPH
        _emit(kind, "<p>", para)

    return blocks


# ── Diff ─────────────────────────────────────────────────────────────────────


def diff_blocks(old: list[Block], new: list[Block]) -> DiffResult:
    """Compare two block lists → DiffResult.

    Matching criteria:
        - exact ``path`` match → same region.
        - if ``block_hash`` differs for the same path → modified.
        - path only in new → added.
        - path only in old → removed.
        - same path + same hash on both sides → unchanged.

    Notes:
        - The case of the same path appearing twice on one side is prevented by
          the indexing done in parse_blocks (path is unique).
        - Still, the dict conversion prefers the first occurrence for safety.
    """
    old_map = {b.path: b for b in old}
    new_map = {b.path: b for b in new}

    result = DiffResult()
    for path, b_new in new_map.items():
        b_old = old_map.get(path)
        if b_old is None:
            result.added.append(b_new)
        elif b_old.block_hash != b_new.block_hash:
            result.modified.append((b_old, b_new))
        else:
            result.unchanged.append(b_new)
    for path, b_old in old_map.items():
        if path not in new_map:
            result.removed.append(b_old)
    return result


# ── Color region computation (2-cycle decay) ─────────────────────────────────


def compute_color_regions(
    old_blocks: list[Block],
    new_blocks: list[Block],
    previous_green_regions: Iterable[dict] | None = None,
) -> ColorRegions:
    """Compute green/blue regions using the 2-cycle decay model.

    G_N = added + the new side of modified.
    B_N = previous_green - paths changed this time.
          (i.e. regions that were green in the previous publish but were not
          changed again in this publish — one step of decay in this publish.)

    Args:
        old_blocks: block list of the previous publish (v_{N-1}).
        new_blocks: block list of this publish (v_N).
        previous_green_regions: the previous publish's ``ColorRegions.green``
            serialized via ``serialize_state``, as list[dict].
            Each entry: ``{"path": ..., "block_hash": ...}``.
            If None, treated as an empty list (e.g. first publish or N=2).

    Returns:
        ColorRegions(green=..., blue=...).

    Notes:
        - For the first draft (old_blocks empty), the spec says G_1 = ∅ (all black).
          This is the caller's responsibility — this function treats any `added`
          entries as all green, so on the first publish the caller must either not
          call ``compute_color_regions`` or discard its result.
        - If the same path is also in previous_green and changed again this time,
          it is green only. (Detected as modified → green; the same path from
          previous is a blue candidate but is excluded from blue since it's
          already in green.)
    """
    diff = diff_blocks(old_blocks, new_blocks)

    # G_N — this publish's changes
    green: list[Block] = []
    green.extend(diff.added)
    green.extend(b_new for (_, b_new) in diff.modified)

    green_paths = {b.path for b in green}

    # B_N — previous_green entries not changed this time
    blue: list[Block] = []
    if previous_green_regions:
        # path → Block lookup for new_blocks
        new_map = {b.path: b for b in new_blocks}
        for entry in previous_green_regions:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            if not path or path in green_paths:
                # changed again this time → green only, excluded from blue
                continue
            # the path must still exist in the current publish to be displayable
            b_cur = new_map.get(path)
            if b_cur is None:
                # the region was removed — cannot be displayed
                continue
            blue.append(b_cur)

    return ColorRegions(green=green, blue=blue)


# ── State serialization ──────────────────────────────────────────────────────


def serialize_state(regions: ColorRegions) -> list[dict]:
    """Serialize to the form stored in meta.json's ``_color_state.previous_green_regions``.

    Returns:
        ``[{"path": ..., "block_hash": ...}, ...]`` — only green is serialized.
        (blue is recomputed automatically on the next publish, so it needn't be stored.)
    """
    return [
        {"path": b.path, "block_hash": b.block_hash}
        for b in regions.green
    ]


# ── CLI ──────────────────────────────────────────────────────────────────────


def _format_blocks_md(blocks: list[Block], heading: str) -> list[str]:
    """Debug MD format — short path + hash."""
    lines = [f"### {heading} ({len(blocks)})"]
    for b in blocks:
        lines.append(f"- [{b.kind}] `{b.path}` (hash={b.block_hash})")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Block-level diff between two MD versions (Phase 3 color cycling)."
    )
    parser.add_argument("--old", required=True, help="Previous MD file (v_{N-1}).")
    parser.add_argument("--new", required=True, help="Current MD file (v_N).")
    parser.add_argument(
        "--previous-green",
        default=None,
        help=(
            "Optional JSON file with previous publish's green region list "
            "(format produced by serialize_state)."
        ),
    )
    parser.add_argument(
        "--format",
        choices=["json", "md"],
        default="json",
        help="Output format (default: json).",
    )
    args = parser.parse_args(argv)

    try:
        old_text = Path(args.old).read_text(encoding="utf-8")
        new_text = Path(args.new).read_text(encoding="utf-8")
    except OSError as e:
        print(f"I/O error: {e}", file=sys.stderr)
        return 1

    prev_green: list[dict] | None = None
    if args.previous_green:
        try:
            prev_green = json.loads(
                Path(args.previous_green).read_text(encoding="utf-8")
            )
            if not isinstance(prev_green, list):
                print("--previous-green: expected JSON list", file=sys.stderr)
                return 2
        except OSError as e:
            print(f"I/O error: {e}", file=sys.stderr)
            return 1
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}", file=sys.stderr)
            return 2

    old_blocks = parse_blocks(old_text)
    new_blocks = parse_blocks(new_text)
    diff = diff_blocks(old_blocks, new_blocks)
    regions = compute_color_regions(old_blocks, new_blocks, prev_green)

    if args.format == "json":
        out = {
            "summary": diff.summary(),
            "added": [b.to_dict() for b in diff.added],
            "removed": [b.to_dict() for b in diff.removed],
            "modified": [
                {"old": o.to_dict(), "new": n.to_dict()}
                for (o, n) in diff.modified
            ],
            "green": [b.to_dict() for b in regions.green],
            "blue": [b.to_dict() for b in regions.blue],
            "next_state": serialize_state(regions),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        lines: list[str] = []
        lines.append("# diff_blocks report")
        lines.append("")
        lines.append(f"summary: {diff.summary()}")
        lines.append("")
        lines.extend(_format_blocks_md(diff.added, "Added"))
        lines.append("")
        lines.extend(_format_blocks_md(diff.removed, "Removed"))
        lines.append("")
        lines.extend(
            _format_blocks_md(
                [n for (_, n) in diff.modified], "Modified (new side)"
            )
        )
        lines.append("")
        lines.extend(_format_blocks_md(regions.green, "GREEN (this publish)"))
        lines.append("")
        lines.extend(_format_blocks_md(regions.blue, "BLUE (previous publish decay)"))
        print("\n".join(lines))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
