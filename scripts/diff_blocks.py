#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Block-level diff 라이브러리 — Phase 3 색상 cycling 의 토대.

본 모듈은 publication-targeted MD 두 버전 간 변경된 region 을 *block 단위* 로
식별한다. 사양 SSoT는 ``orange-pm-plugin/skills/render/publication-syntax.md``
§6 "색상 Span (Phase 3 예약)" 이며, 본 모듈이 출력하는 region 정보는
``md_to_storage`` 의 색상 span 삽입 단계에서 소비된다.

설계 결정 (이전 phase 토론에서 확정된 사양):

* **Region 정의**: ``(논리 경로, block_hash)`` 튜플.
* **Block 단위**:
    - paragraph     : 문단 1개
    - heading       : 제목 1개 (텍스트 변경 시)
    - list_item     : 리스트 항목 1개 (중첩 시 nested path)
    - table_cell    : 표 셀 단위 (행 단위가 아님)
    - code          : 코드블록 전체 (내부 span 불가 — 사양 §6 금지)
    - panel_inner_para : panel/info/warning 내부의 paragraph
* **Region 식별자 예시**: ``§3 정책/§3.1/<p[2]>``
* **2-cycle decay**::

    N=1: G_1 = ∅ (모두 검정 — 첫 작성)
    N=2: G_2 = diff(v1, v2) → 초록; B_2 = ∅
    N=3: G_3 = diff(v2, v3) → 초록; B_3 = G_2 \\ G_3 → 파랑
    N=k: G_k = diff(v_{k-1}, v_k) → 초록; B_k = G_{k-1} \\ G_k → 파랑

  같은 path 가 ``previous_green`` 에도 있고 이번에 또 변경됐으면 → 초록 only
  (파랑이 되지 않음; "decay" 가 redundant 한 변경에서 발생하지 않도록).

* **frontmatter**: 무시 (publication.* 변경은 cycling 대상 아님).

본 모듈은 ``stdlib only`` 다 (re, hashlib, dataclasses, json, argparse).
``md_to_storage`` 가 사용하는 정규식 일부를 동일하게 재현하나, 그쪽 모듈을
임포트하지 않는다 — 두 모듈이 독립적으로 발전 가능해야 하므로.

CLI (디버그용):
    python diff_blocks.py --old v1.md --new v2.md \\
        [--previous-green file.json] [--format json|md]

exit code:
    0 = 성공
    1 = I/O 오류
    2 = 인자 오류
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


# ── 정규식 (md_to_storage 와 동일 패턴) ──────────────────────────────────────

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

# Inline 코드 (`...`) 및 strong/em 등은 path 와 무관 — content 정규화에만 영향.
MULTI_SPACE_RE = re.compile(r"\s+")

CALLOUT_CLASSES = {"info", "warning", "note", "tip"}

# Block kind 열거 — 외부에서 참조 가능한 문자열 상수.
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
    """단일 region 의 표현 — (path, content, hash) 트리플 + 위치 메타.

    Attributes:
        kind: 블록 종류 (KIND_* 상수 중 하나).
        path: 논리 경로 — heading hierarchy + 블록 위치 인덱스.
              예: ``"§3 정책/§3.1 표준요금/<p[2]>"``.
        content: 정규화된 블록 본문 텍스트 (양끝 공백 제거, 다중 공백 단일화,
                 inline 마커는 그대로 유지하여 변경 감지에 사용).
        block_hash: sha256(content) 처음 16자 (64-bit equivalent — 충분히 유일).
        line_start: source 의 1-based 시작 라인 (-1 = unknown, deserialize 시).
        line_end: source 의 1-based 끝 라인 inclusive (-1 = unknown).
        raw_content: source 의 원본 텍스트 (정규화 전, color span 주입용).
                     -1 라인 정보가 있을 때만 의미 있음.
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
    """``diff_blocks(old, new)`` 결과.

    매칭 기준은 ``path`` 정확 일치 → ``block_hash`` 비교.
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
    """2-cycle decay 모델 산출물.

    Attributes:
        green: 이번 publish 에서 변경된 block (added + modified.new 측).
        blue: 직전 publish 의 green 영역 중 이번엔 변경되지 않은 것.
    """

    green: list[Block] = field(default_factory=list)
    blue: list[Block] = field(default_factory=list)


# ── 내부 유틸 ────────────────────────────────────────────────────────────────


def _normalize_content(text: str) -> str:
    """블록 본문 정규화 — 비교 안정성 확보.

    - 양끝 공백 제거
    - 모든 whitespace (탭/줄바꿈 포함) → 단일 space
    - 빈 줄로만 구성된 경우 빈 문자열
    """
    if not text:
        return ""
    return MULTI_SPACE_RE.sub(" ", text).strip()


def _block_hash(content: str) -> str:
    """SHA-256(content) 의 hex digest 첫 16자 (64-bit space)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _strip_frontmatter(md_text: str) -> str:
    """frontmatter 영역 제거 (publication.* 는 cycling 대상 아님 — 사양 §6 정신).

    frontmatter 부재 시 원문 그대로 반환.
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
    """| a | b | → ['a', 'b'] (전후 공백·외곽 | 제거)."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _heading_path_join(parts: list[str]) -> str:
    """heading hierarchy 를 ``/`` 로 join. 빈 stack 은 ``""``."""
    return "/".join(p for p in parts if p)


# ── 헤딩 경로 추적 ───────────────────────────────────────────────────────────


class _HeadingStack:
    """h1~h6 헤딩 hierarchy 를 stack 으로 관리.

    h_k 등장 시 stack 을 길이 k 로 잘라내고 (`stack[:k-1]`) 마지막에 text push.
    ``current_path()`` 는 모든 레벨 join 결과 반환.
    """

    def __init__(self) -> None:
        # 인덱스 = level-1 (0-based). 빈 슬롯은 빈 문자열.
        self._levels: list[str] = []

    def push(self, level: int, text: str) -> None:
        # 더 깊은 레벨 제거
        if len(self._levels) >= level:
            self._levels = self._levels[: level - 1]
        # 빈 슬롯 패딩
        while len(self._levels) < level - 1:
            self._levels.append("")
        self._levels.append(text)

    def current_path(self) -> str:
        return _heading_path_join(self._levels)


# ── Block 파서 (메인) ────────────────────────────────────────────────────────


def parse_blocks(md_text: str) -> list[Block]:
    """MD 텍스트 → ``list[Block]``.

    상태 머신:
        1. frontmatter 제거
        2. 라인 순회하며 panel 컨테이너 stack + heading hierarchy stack 관리
        3. 각 블록(paragraph/heading/list_item/table_cell/code) 식별 → Block emit

    Notes:
        - panel 안의 paragraph 는 ``kind=panel_inner_para`` 로 표기 (사양:
          panel/info 등 macro body 는 내부 paragraph 단위).
        - 본 함수는 inline 매크로(``[[page:...]]`` 등)를 *해석하지 않는다* —
          텍스트 그대로 hash 입력에 포함하여 변경 감지 신호로 사용.
        - 다중 줄로 이어지는 paragraph 는 단일 space 로 join 후 hash.
    """
    body = _strip_frontmatter(md_text)
    lines = body.splitlines()

    blocks: list[Block] = []
    heading_stack = _HeadingStack()

    # panel 컨테이너 stack — fenced div ``.panel`` 이 활성일 때 path prefix 에 포함.
    # 각 항목: (kind, path_segment, inner_para_counter)
    container_stack: list[dict] = []

    # 블록 위치 인덱스 — heading 변경 시 reset.
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
        """heading + container 경로 결합."""
        h = heading_stack.current_path()
        c = _container_prefix()
        if h and c:
            return f"{h}/{c}"
        return h or c

    def _emit(kind: str, marker: str, content: str) -> None:
        """Block emit helper.

        marker: path 의 마지막 segment 에 들어갈 표기 (예: ``<p>``, ``<h2>``).
                인덱스가 부여되어 ``<p[2]>`` 형태로 확장됨.
        """
        norm = _normalize_content(content)
        if not norm:
            return  # 빈 블록은 region 으로 의미 없음
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
            # 컨테이너 진입 — 해당 prefix 인덱스 리셋
            _reset_indices_for(_full_prefix())
            i += 1
            continue

        # fenced div close
        if FENCED_DIV_CLOSE_RE.match(line):
            if container_stack:
                container_stack.pop()
            i += 1
            continue

        # code fence — 전체를 1개 code block 으로
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
            # 코드는 normalize 하지 않고 그대로 hash (들여쓰기 의미 있음)
            raw = "\n".join(buf)
            prefix = _full_prefix()
            marker = f"<code:{lang}>" if lang else "<code>"
            idx = _next_idx(prefix, marker)
            leaf = f"{marker[:-1]}[{idx}]>"
            path = f"{prefix}/{leaf}" if prefix else leaf
            # 빈 코드블록도 region 으로 유지 (변경 추적)
            blocks.append(
                Block(
                    kind=KIND_CODE,
                    path=path,
                    content=raw,
                    block_hash=_block_hash(raw),
                )
            )
            continue

        # col-widths directive — 무시 (path/region 영향 없음)
        if COLWIDTHS_DIRECTIVE_RE.match(line):
            i += 1
            continue

        # heading
        m_h = HEADING_RE.match(line)
        if m_h:
            level = len(m_h.group(1))
            text = m_h.group(2).strip()
            # heading text 자체를 block 으로 — 변경 시 region 발생
            # heading_stack 갱신 *후* path 계산 시 자신이 leaf 가 되도록 처리
            heading_stack.push(level, text)
            # 새 heading 경로 진입 — 해당 prefix 인덱스 리셋
            new_prefix = _full_prefix()
            _reset_indices_for(new_prefix)
            # heading block 의 path 는 자신을 leaf 로 표기
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

        # hr — region 아님 (스타일 요소)
        if HR_RE.match(line):
            i += 1
            continue

        # 빈 줄
        if not stripped:
            i += 1
            continue

        # 표 — header 행 + separator 다음부터 행/셀 parse
        if "|" in line and i + 1 < n and TABLE_SEPARATOR_RE.match(lines[i + 1]):
            header_cells = _split_table_row(line)
            prefix = _full_prefix()
            tbl_idx = _next_idx(prefix, "<table>")
            tbl_marker = f"<table[{tbl_idx}]>"
            # 헤더 셀
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

        # 리스트 (ul / ol) — 각 item 별로 list_item block
        m_ul = UL_RE.match(line)
        m_ol = OL_RE.match(line)
        if m_ul or m_ol:
            prefix = _full_prefix()
            list_idx = _next_idx(prefix, "<list>")
            list_marker = f"<list[{list_idx}]>"
            # depth 별 item 카운터 (path 안에 depth chain 포함)
            depth_counters: dict[int, int] = {}
            depth_stack: list[int] = []  # 현재까지 본 depth level 순서
            while i < n:
                cur = lines[i]
                if not cur.strip():
                    break
                m = UL_RE.match(cur) or OL_RE.match(cur)
                if not m:
                    break
                indent_ws = m.group(1)
                depth = len(indent_ws) // 2
                # 더 얕은 depth 진입 시 그보다 깊은 카운터 reset
                for d in list(depth_counters.keys()):
                    if d > depth:
                        depth_counters[d] = 0
                # depth_stack 보정
                while depth_stack and depth_stack[-1] > depth:
                    depth_stack.pop()
                if not depth_stack or depth_stack[-1] < depth:
                    depth_stack.append(depth)
                # 카운터 증가
                depth_counters[depth] = depth_counters.get(depth, 0) + 1
                # path 의 list_item chain 표기 — depth 별 인덱스
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

        # blockquote — 각 내부 단락을 blockquote_para 로
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

        # paragraph — 빈 줄 / 다른 블록 시작까지 누적
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
        # 컨테이너 (panel/info/...) 안의 paragraph 는 별도 kind
        if container_stack:
            kind = KIND_PANEL_INNER_PARA
        else:
            kind = KIND_PARAGRAPH
        _emit(kind, "<p>", para)

    return blocks


# ── Diff ─────────────────────────────────────────────────────────────────────


def diff_blocks(old: list[Block], new: list[Block]) -> DiffResult:
    """두 block 리스트 비교 → DiffResult.

    매칭 기준:
        - ``path`` 정확 일치 → 동일 region.
        - 동일 path 에서 ``block_hash`` 다르면 modified.
        - new 에만 있는 path → added.
        - old 에만 있는 path → removed.
        - 양쪽 동일 path + 동일 hash → unchanged.

    Notes:
        - 같은 path 가 한쪽에 2개 이상 등장하는 경우는 parse_blocks 에서
          인덱스 부여로 방지됨 (path 는 unique).
        - 그래도 안전을 위해 dict 변환 시 첫 등장 우선.
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


# ── 색상 region 계산 (2-cycle decay) ─────────────────────────────────────────


def compute_color_regions(
    old_blocks: list[Block],
    new_blocks: list[Block],
    previous_green_regions: Iterable[dict] | None = None,
) -> ColorRegions:
    """2-cycle decay 모델로 green/blue region 계산.

    G_N = added + modified.new 측.
    B_N = previous_green - 이번에 변경된 path.
          (즉, 직전 publish 에서 green 이었으나 이번 publish 에서 또 변경되지
          않은 region — 이번 발행에서 1단계 decay.)

    Args:
        old_blocks: 직전 publish 의 block list (v_{N-1}).
        new_blocks: 이번 publish 의 block list (v_N).
        previous_green_regions: 직전 publish 의 ``ColorRegions.green`` 을
            ``serialize_state`` 로 직렬화한 list[dict].
            각 항목: ``{"path": ..., "block_hash": ...}``.
            None 이면 빈 list 로 간주 (예: 첫 publish 또는 N=2).

    Returns:
        ColorRegions(green=..., blue=...).

    Notes:
        - 첫 작성(old_blocks 가 빈 경우) 은 사양상 G_1 = ∅ (모두 검정).
          이는 caller 의 책임 — 본 함수는 added 가 있으면 모두 green 으로
          간주하므로, 첫 발행 시 caller 가 ``compute_color_regions`` 를
          호출하지 않거나 결과를 폐기해야 한다.
        - 같은 path 가 previous_green 에도 있고 이번에 또 변경됐으면 green only.
          (modified 로 감지 → green; previous 의 동일 path 는 blue 후보지만
           green 에 이미 포함되어 있으므로 blue 에서 제외.)
    """
    diff = diff_blocks(old_blocks, new_blocks)

    # G_N — 이번 변경
    green: list[Block] = []
    green.extend(diff.added)
    green.extend(b_new for (_, b_new) in diff.modified)

    green_paths = {b.path for b in green}

    # B_N — previous_green 에서 이번에 변경 안 된 것
    blue: list[Block] = []
    if previous_green_regions:
        # new_blocks 의 path → Block lookup
        new_map = {b.path: b for b in new_blocks}
        for entry in previous_green_regions:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            if not path or path in green_paths:
                # 이번에 또 변경됐으면 green only — blue 에서 제외
                continue
            # 현재 발행에 그 path 가 살아있어야 표시 가능
            b_cur = new_map.get(path)
            if b_cur is None:
                # 영역이 삭제됨 — 표시할 수 없음
                continue
            blue.append(b_cur)

    return ColorRegions(green=green, blue=blue)


# ── State 직렬화 ─────────────────────────────────────────────────────────────


def serialize_state(regions: ColorRegions) -> list[dict]:
    """meta.json ``_color_state.previous_green_regions`` 에 저장할 형태로 직렬화.

    Returns:
        ``[{"path": ..., "block_hash": ...}, ...]`` — green 만 직렬화.
        (blue 는 다음 publish 에서 자동으로 재계산되므로 저장 불필요.)
    """
    return [
        {"path": b.path, "block_hash": b.block_hash}
        for b in regions.green
    ]


# ── CLI ──────────────────────────────────────────────────────────────────────


def _format_blocks_md(blocks: list[Block], heading: str) -> list[str]:
    """디버그용 MD 포맷 — 짧은 path + hash."""
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
