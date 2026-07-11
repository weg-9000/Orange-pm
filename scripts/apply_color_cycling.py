#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Color Cycling Orchestrator (Phase 3C + 3F + 3G + 3H).

Invoked at publish time to perform the following:
    1. Load the previous publish state (meta.json._color_state)
    2. Block-level diff between the current MD source and the previous source
    3. Compute color regions (G_N green / B_N blue, 2-cycle decay)
    4. Inject color spans into the MD source + insert a "changes this round"
       panel at the top of the page
    5. Serialize the new _color_state (the caller updates meta.json)

Depends on:
    diff_blocks.py — block-level parse / diff / compute_color_regions

CLI:
    python apply_color_cycling.py \
        --input draft.md \
        --output /tmp/draft.colored.md \
        --meta-in meta.json \
        --meta-out /tmp/meta.updated.json \
        [--color-reset]                  # Phase 3G: treat next publish as N=1 baseline
        [--deliverable-type meetings]    # Phase 3H: D4 special cycling (only new items green)

Exit code:
    0 = success (color injected or baseline reset)
    1 = input file missing / parse error
    2 = usage error

Phase 3 spec:
    publication-syntax.md §6 (especially §6.2 2-cycle decay, §6.4 schema)

Note:
    Operates independently of md_to_storage.py — the caller (e.g. a render
    skill or cron job) invokes apply_color_cycling then md_to_storage, in that order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).parent))

from diff_blocks import (  # type: ignore
    Block,
    DiffResult,
    ColorRegions,
    parse_blocks,
    diff_blocks,
    compute_color_regions,
    serialize_state,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── read/write meta.json ───────────────────────────────────────────────────
def load_meta(path: Path) -> dict:
    """Load meta.json. If missing, return a fresh baseline state."""
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse meta.json ({path}): {exc}") from exc


def _default_color_state() -> dict:
    return {
        "publish_round": 0,
        "previous_source_hash": None,
        "previous_blocks": [],
        "previous_green_regions": [],
        "baseline": True,
    }


def get_color_state(meta: dict) -> dict:
    """Extract _color_state from meta. If missing, return the default baseline."""
    state = meta.get("_color_state")
    if not isinstance(state, dict):
        return _default_color_state()
    # fill in missing fields
    base = _default_color_state()
    base.update(state)
    return base


def _block_from_state(d: dict) -> Block:
    """Convert a previous_blocks entry from meta.json into a stub Block (for diff comparison).

    line/raw info isn't preserved, so it's -1/empty. Diffing works with just path + hash.
    """
    return Block(
        kind=d.get("kind", "paragraph"),
        path=d.get("path", ""),
        content=d.get("content", ""),
        block_hash=d.get("block_hash", ""),
    )


# ── color injection — content-based replacement (cursor progresses) ────────
def _wrap_color(content: str, cls: str) -> str:
    """Wrap content as [content]{.color-XXX} (multi-line safe).

    Empty content is not wrapped.
    """
    if not content.strip():
        return content
    # nested spans are forbidden (spec §6.1) — skip if already wrapped
    if re.match(r"^\[.*\]\{\.color-(green|blue)\}$", content.strip()):
        return content
    return f"[{content}]{{.{cls}}}"


def _inject_color_at_path(
    md_lines: list[str],
    block: Block,
    cls: str,
    cursor: int,
) -> tuple[list[str], int]:
    """Wrap the first region in the source line array that matches block.content.

    Strategy:
      1. Starting at cursor, find the line matching block.content
         (normalized content vs raw line — ignore leading/trailing whitespace).
      2. On a match, wrap that line and advance cursor.
      3. On no match, skip (warning is accumulated).

    Cases like a table cell, where a single line has multiple regions, are
    handled separately (table mode).
    """
    target = block.content.strip()
    if not target:
        return md_lines, cursor

    # table cell case — replace at the cell level within the line
    if block.kind in ("table_cell",):
        for i in range(cursor, len(md_lines)):
            line = md_lines[i]
            if "|" not in line:
                continue
            # split cells on |, wrap the cell matching target
            parts = line.split("|")
            for j, cell in enumerate(parts):
                if cell.strip() == target:
                    parts[j] = " " + _wrap_color(cell.strip(), cls) + " "
                    md_lines[i] = "|".join(parts)
                    return md_lines, i
        return md_lines, cursor

    # heading — the `#+ heading_text` pattern on the same line
    if block.kind in ("heading",):
        for i in range(cursor, len(md_lines)):
            m = re.match(r"^(#+\s+)(.+?)\s*$", md_lines[i])
            if m and m.group(2).strip() == target:
                md_lines[i] = m.group(1) + _wrap_color(target, cls)
                return md_lines, i + 1
        return md_lines, cursor

    # list_item — the text after a `- ` or `1. ` prefix
    if block.kind in ("list_item",):
        for i in range(cursor, len(md_lines)):
            m = re.match(r"^(\s*(?:[-*+]|\d+\.)\s+)(.+?)\s*$", md_lines[i])
            if m and m.group(2).strip() == target:
                md_lines[i] = m.group(1) + _wrap_color(target, cls)
                return md_lines, i + 1
        return md_lines, cursor

    # code — wrap the whole code block externally (no spans inside CDATA, spec §6.1)
    # At the MD stage this only marks the wrapper — the XML conversion step
    # needs separate handling. Skip for now, and register it as a separate
    # entry in the change-summary panel instead.
    if block.kind in ("code",):
        return md_lines, cursor

    # paragraph / panel_inner_para / blockquote — can be multi-line
    # find the line matching target's starting text, starting at cursor
    target_lines = [ln.strip() for ln in target.split("\n") if ln.strip()]
    if not target_lines:
        return md_lines, cursor

    first_target = target_lines[0]
    for i in range(cursor, len(md_lines)):
        line = md_lines[i].strip()
        if line == first_target:
            # check for a multi-line match
            if len(target_lines) == 1:
                # single-line paragraph — wrap
                indent = re.match(r"^(\s*)", md_lines[i]).group(1)
                md_lines[i] = indent + _wrap_color(target, cls)
                return md_lines, i + 1
            else:
                # multi-line: mark only the first line as [content_first]{.color-X}
                # (conservative, since a multi-line fenced span can break on round-trip)
                indent = re.match(r"^(\s*)", md_lines[i]).group(1)
                md_lines[i] = indent + _wrap_color(first_target, cls)
                return md_lines, i + len(target_lines)
    return md_lines, cursor


def apply_colors(md_source: str, regions: ColorRegions, warnings: list[str]) -> str:
    """Inject color spans for each green/blue path in ColorRegions.

    cursor increases monotonically — the same line is never wrapped twice.
    Match failures are accumulated into warnings (not a FAIL — just a notice to the user).
    """
    if not regions.green and not regions.blue:
        return md_source

    md_lines = md_source.splitlines()
    cursor = 0

    # green first (B_N is G_N \ ..., so paths never overlap — order doesn't matter)
    # but sort by path order to guarantee cursor advances monotonically
    all_regions: list[tuple[str, Block]] = []
    for b in regions.green:
        all_regions.append(("color-green", b))
    for b in regions.blue:
        all_regions.append(("color-blue", b))

    # estimate the first occurrence line for a path — sort by where content appears in the source
    def _approx_line(blk: Block) -> int:
        target = blk.content.strip().split("\n")[0]
        for i, line in enumerate(md_lines):
            if target and target in line:
                return i
        return len(md_lines)  # to the end

    all_regions.sort(key=lambda pair: _approx_line(pair[1]))

    for cls, block in all_regions:
        before = md_lines[:]
        md_lines, cursor = _inject_color_at_path(md_lines, block, cls, cursor)
        if md_lines == before:
            warnings.append(f"Color injection failed (no match): {cls} {block.kind} '{block.path}'")

    return "\n".join(md_lines) + ("\n" if md_source.endswith("\n") else "")


# ── change-summary panel (Phase 3F) ─────────────────────────────────────
def _summarize_changes(
    diff: DiffResult,
    regions: ColorRegions,
    publish_round: int,
) -> str:
    """Generate a "changes this round" summary as a fenced div panel.

    Prepended at the very top of the page (after frontmatter).
    """
    added_paths = [b.path for b in diff.added]
    removed_paths = [b.path for b in diff.removed]
    modified_paths = [new.path for (_old, new) in diff.modified]
    blue_paths = [b.path for b in regions.blue]

    lines = [f"::: {{.panel section=\"Changes this round (v{publish_round})\" style=\"info\"}}"]
    lines.append(f"## Changes this round (v{publish_round})")
    lines.append("")
    if added_paths:
        lines.append(f"- **Added** ({len(added_paths)}, marked green):")
        for p in added_paths[:10]:
            lines.append(f"  - `{p}`")
        if len(added_paths) > 10:
            lines.append(f"  - ... and {len(added_paths) - 10} more")
    if modified_paths:
        lines.append(f"- **Modified** ({len(modified_paths)}, marked green):")
        for p in modified_paths[:10]:
            lines.append(f"  - `{p}`")
        if len(modified_paths) > 10:
            lines.append(f"  - ... and {len(modified_paths) - 10} more")
    if blue_paths:
        lines.append(f"- **Changed in the previous round** ({len(blue_paths)}, marked blue = stable this round)")
    if removed_paths:
        lines.append(f"- **Removed** ({len(removed_paths)}, cannot be marked — removed from the body):")
        for p in removed_paths[:5]:
            lines.append(f"  - `{p}`")
        if len(removed_paths) > 5:
            lines.append(f"  - ... and {len(removed_paths) - 5} more")
    if not (added_paths or modified_paths or blue_paths or removed_paths):
        lines.append("- No changes (all regions stable)")
    lines.append(":::")
    lines.append("")
    return "\n".join(lines)


def _prepend_summary(md_source: str, summary: str) -> str:
    """Insert the summary right where the body starts, after frontmatter."""
    if md_source.startswith("---\n"):
        end = md_source.find("\n---\n", 4)
        if end >= 0:
            head = md_source[: end + 5]  # includes \n---\n
            body = md_source[end + 5 :]
            return head + "\n" + summary + body
    # no frontmatter -> prepend at the very front
    return summary + md_source


# ── D4 meeting-notes special cycling (Phase 3H) ─────────────────────────
def _is_meetings_d4(deliverable_type: str) -> bool:
    return deliverable_type.lower() in ("meetings", "meeting-notes", "d4")


def _adjust_for_meetings(diff: DiffResult, regions: ColorRegions) -> ColorRegions:
    """D4 meeting-notes special rule (spec §6.6):

    - New meeting entry (entire added panel) -> green
    - Modification to an existing meeting body -> normal cycling (unchanged)
    - Since a blue region's time display itself signals change in meeting
      notes, expire it faster automatically.

    Current implementation: process the same as the normal flow, but reset
    the blue region to an empty list (the core of the meeting-notes special
    rule — accumulated blue hurts readability, so meeting notes use 1-cycle
    instead of 2-cycle).
    """
    return ColorRegions(green=list(regions.green), blue=[])


# ── core orchestration ───────────────────────────────────────────────────
def apply_cycling(
    md_source: str,
    color_state: dict,
    *,
    color_reset: bool = False,
    deliverable_type: str = "",
) -> tuple[str, dict, list[str]]:
    """Core entry point for color cycling.

    Returns:
        (annotated_md, new_color_state, warnings)
    """
    warnings: list[str] = []
    current_hash = _sha256(md_source)
    publish_round = color_state.get("publish_round", 0)
    baseline = color_state.get("baseline", True)

    # --color-reset or baseline -> treat as the first publish (no color, no summary panel)
    if color_reset or baseline:
        new_blocks = parse_blocks(md_source)
        new_state = {
            "publish_round": 1,
            "previous_source_hash": current_hash,
            "previous_blocks": [b.to_dict() for b in new_blocks],
            "previous_green_regions": [],
            "baseline": False,
        }
        return md_source, new_state, warnings

    # normal cycling
    old_blocks = [_block_from_state(d) for d in color_state.get("previous_blocks", [])]
    new_blocks = parse_blocks(md_source)
    diff = diff_blocks(old_blocks, new_blocks)

    previous_green = list(color_state.get("previous_green_regions", []))
    regions = compute_color_regions(old_blocks, new_blocks, previous_green)

    # D4 meeting-notes special rule
    if _is_meetings_d4(deliverable_type):
        regions = _adjust_for_meetings(diff, regions)

    # color injection + change-summary panel
    annotated = apply_colors(md_source, regions, warnings)
    summary = _summarize_changes(diff, regions, publish_round + 1)
    annotated = _prepend_summary(annotated, summary)

    new_state = {
        "publish_round": publish_round + 1,
        "previous_source_hash": current_hash,
        "previous_blocks": [b.to_dict() for b in new_blocks],
        "previous_green_regions": serialize_state(regions),
        "baseline": False,
    }
    return annotated, new_state, warnings


# ── CLI ──────────────────────────────────────────────────────────────────
def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apply_color_cycling",
        description="Color Cycling Orchestrator — inject color spans into MD right before publish (spec: publication-syntax.md §6)",
    )
    parser.add_argument("--input", required=True, help="input MD source")
    parser.add_argument("--output", required=True, help="output annotated MD")
    parser.add_argument("--meta-in", help="input meta.json (treated as baseline if missing)")
    parser.add_argument("--meta-out", help="output meta.json (if omitted, does not write in-place over --meta-in, and produces no output)")
    parser.add_argument(
        "--color-reset",
        action="store_true",
        help="Phase 3G — treat the next publish as baseline (N=1) (no color applied, state reset)",
    )
    parser.add_argument(
        "--deliverable-type",
        default="",
        help="Phase 3H — when set to 'meetings', use D4 meeting-notes special cycling (blue auto-expires)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    in_path = Path(args.input)
    out_path = Path(args.output)

    if not in_path.is_file():
        print(f"[apply_color_cycling] ERROR: input file not found: {in_path}", file=sys.stderr)
        return 1

    md_source = in_path.read_text(encoding="utf-8")

    meta: dict = {}
    if args.meta_in:
        try:
            meta = load_meta(Path(args.meta_in))
        except ValueError as exc:
            print(f"[apply_color_cycling] ERROR: {exc}", file=sys.stderr)
            return 1
    color_state = get_color_state(meta)

    annotated, new_state, warnings = apply_cycling(
        md_source,
        color_state,
        color_reset=args.color_reset,
        deliverable_type=args.deliverable_type,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(annotated, encoding="utf-8")

    if args.meta_out:
        meta_out = dict(meta)
        meta_out["_color_state"] = new_state
        Path(args.meta_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.meta_out).write_text(
            json.dumps(meta_out, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    for w in warnings:
        print(f"[apply_color_cycling] WARN: {w}", file=sys.stderr)

    print(
        f"[apply_color_cycling] OK: round={new_state['publish_round']} "
        f"({len(new_state['previous_green_regions'])} green) -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
