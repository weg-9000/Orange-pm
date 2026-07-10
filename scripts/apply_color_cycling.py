#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Color Cycling Orchestrator (Phase 3C + 3F + 3G + 3H).

publish 시점에 호출되어 다음을 수행:
    1. 직전 publish 상태 (meta.json._color_state) 로딩
    2. 현재 MD source 와 직전 source 의 block-level diff
    3. 색상 region 계산 (G_N green / B_N blue, 2-cycle decay)
    4. MD source 에 색상 span 주입 + 페이지 상단에 "이번 변경 요약" panel 삽입
    5. 새 _color_state 직렬화 (caller 가 meta.json 갱신)

의존:
    diff_blocks.py — block 단위 parse / diff / compute_color_regions

CLI:
    python apply_color_cycling.py \
        --input draft.md \
        --output /tmp/draft.colored.md \
        --meta-in meta.json \
        --meta-out /tmp/meta.updated.json \
        [--color-reset]                  # Phase 3G: 다음 publish 를 N=1 baseline 으로
        [--deliverable-type meetings]    # Phase 3H: D4 특수 cycling (신규 항목만 초록)

종료 코드:
    0 = 성공 (색상 주입 또는 baseline 초기화)
    1 = 입력 파일 미존재 / 파싱 오류
    2 = 사용법 오류

Phase 3 사양:
    publication-syntax.md §6 (특히 §6.2 2-cycle decay, §6.4 schema)

Note:
    md_to_storage.py 와 독립적으로 작동 — caller(예: render skill 또는 cron)가
    apply_color_cycling → md_to_storage 순서로 호출.
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


# ── meta.json 읽기/쓰기 ───────────────────────────────────────────────────
def load_meta(path: Path) -> dict:
    """meta.json 로드. 없으면 baseline 신규 state 반환."""
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"meta.json 파싱 실패 ({path}): {exc}") from exc


def _default_color_state() -> dict:
    return {
        "publish_round": 0,
        "previous_source_hash": None,
        "previous_blocks": [],
        "previous_green_regions": [],
        "baseline": True,
    }


def get_color_state(meta: dict) -> dict:
    """meta 에서 _color_state 추출. 없으면 default baseline 반환."""
    state = meta.get("_color_state")
    if not isinstance(state, dict):
        return _default_color_state()
    # 누락 필드 보강
    base = _default_color_state()
    base.update(state)
    return base


def _block_from_state(d: dict) -> Block:
    """meta.json 의 previous_blocks 엔트리 → stub Block (diff 비교용).

    line/raw 정보는 보존되지 않으므로 -1/empty. path + hash 만으로 diff 가능.
    """
    return Block(
        kind=d.get("kind", "paragraph"),
        path=d.get("path", ""),
        content=d.get("content", ""),
        block_hash=d.get("block_hash", ""),
    )


# ── 색상 주입 — content-based 치환 (cursor 진행) ──────────────────────────
def _wrap_color(content: str, cls: str) -> str:
    """content 를 [content]{.color-XXX} 로 wrap (multi-line 안전).

    빈 content 는 wrap 하지 않는다.
    """
    if not content.strip():
        return content
    # nested span 금지 (사양 §6.1) — 이미 wrap 되어 있으면 건너뜀
    if re.match(r"^\[.*\]\{\.color-(green|blue)\}$", content.strip()):
        return content
    return f"[{content}]{{.{cls}}}"


def _inject_color_at_path(
    md_lines: list[str],
    block: Block,
    cls: str,
    cursor: int,
) -> tuple[list[str], int]:
    """source 라인 배열에서 block.content 와 일치하는 첫 영역을 wrap.

    Strategy:
      1. cursor 부터 시작해 block.content 와 일치하는 라인 찾기
         (정규화된 content vs raw line — 양끝 공백 무시).
      2. 매칭되면 해당 라인을 wrap, cursor 갱신.
      3. 매칭 실패 시 무시 (warning 누적).

    table cell 처럼 한 라인 안에 여러 region 이 있는 경우는 별도 처리 (table mode).
    """
    target = block.content.strip()
    if not target:
        return md_lines, cursor

    # table cell 인 경우 — 라인 안의 셀 단위 치환
    if block.kind in ("table_cell",):
        for i in range(cursor, len(md_lines)):
            line = md_lines[i]
            if "|" not in line:
                continue
            # 셀들을 | 로 split, target 과 매칭되는 셀 wrap
            parts = line.split("|")
            for j, cell in enumerate(parts):
                if cell.strip() == target:
                    parts[j] = " " + _wrap_color(cell.strip(), cls) + " "
                    md_lines[i] = "|".join(parts)
                    return md_lines, i
        return md_lines, cursor

    # heading — 같은 라인의 `#+ heading_text` 패턴
    if block.kind in ("heading",):
        for i in range(cursor, len(md_lines)):
            m = re.match(r"^(#+\s+)(.+?)\s*$", md_lines[i])
            if m and m.group(2).strip() == target:
                md_lines[i] = m.group(1) + _wrap_color(target, cls)
                return md_lines, i + 1
        return md_lines, cursor

    # list_item — `- ` 또는 `1. ` prefix 뒤의 텍스트
    if block.kind in ("list_item",):
        for i in range(cursor, len(md_lines)):
            m = re.match(r"^(\s*(?:[-*+]|\d+\.)\s+)(.+?)\s*$", md_lines[i])
            if m and m.group(2).strip() == target:
                md_lines[i] = m.group(1) + _wrap_color(target, cls)
                return md_lines, i + 1
        return md_lines, cursor

    # code — 전체 코드블록을 외부 wrapper 로 (CDATA 내부 span 불가, 사양 §6.1)
    # MD 단계에선 wrapper 표시만 — XML 변환 시점에 다른 처리 필요. 일단 skip 후
    # 변경 요약 panel 에 별도 항목으로 등재.
    if block.kind in ("code",):
        return md_lines, cursor

    # paragraph / panel_inner_para / blockquote — 멀티라인 가능
    # cursor 부터 target 시작 텍스트와 일치하는 라인 찾기
    target_lines = [ln.strip() for ln in target.split("\n") if ln.strip()]
    if not target_lines:
        return md_lines, cursor

    first_target = target_lines[0]
    for i in range(cursor, len(md_lines)):
        line = md_lines[i].strip()
        if line == first_target:
            # 멀티 라인 매치 확인
            if len(target_lines) == 1:
                # 단일 라인 paragraph — wrap
                indent = re.match(r"^(\s*)", md_lines[i]).group(1)
                md_lines[i] = indent + _wrap_color(target, cls)
                return md_lines, i + 1
            else:
                # 멀티 라인: 첫 라인만 [content_first]{.color-X} 로 표시
                # (멀티 라인 fenced span 은 round-trip 시 깨질 수 있어 보수적)
                indent = re.match(r"^(\s*)", md_lines[i]).group(1)
                md_lines[i] = indent + _wrap_color(first_target, cls)
                return md_lines, i + len(target_lines)
    return md_lines, cursor


def apply_colors(md_source: str, regions: ColorRegions, warnings: list[str]) -> str:
    """ColorRegions 의 green/blue path 별로 색상 span 주입.

    cursor 가 단조 증가 — 같은 라인을 두 번 wrap 하지 않음.
    매칭 실패는 warnings 에 누적 (FAIL 아님 — 사용자 알림).
    """
    if not regions.green and not regions.blue:
        return md_source

    md_lines = md_source.splitlines()
    cursor = 0

    # green 먼저 (B_N 은 G_N \ ... 이므로 path 가 겹치지 않음 — 순서 무관)
    # 단, path 순으로 정렬해 cursor 단조 진행 보장
    all_regions: list[tuple[str, Block]] = []
    for b in regions.green:
        all_regions.append(("color-green", b))
    for b in regions.blue:
        all_regions.append(("color-blue", b))

    # path 의 첫 등장 라인 추정 — content 가 source 어디에 있는지로 정렬
    def _approx_line(blk: Block) -> int:
        target = blk.content.strip().split("\n")[0]
        for i, line in enumerate(md_lines):
            if target and target in line:
                return i
        return len(md_lines)  # 끝으로

    all_regions.sort(key=lambda pair: _approx_line(pair[1]))

    for cls, block in all_regions:
        before = md_lines[:]
        md_lines, cursor = _inject_color_at_path(md_lines, block, cls, cursor)
        if md_lines == before:
            warnings.append(f"색상 주입 실패 (매칭 안 됨): {cls} {block.kind} '{block.path}'")

    return "\n".join(md_lines) + ("\n" if md_source.endswith("\n") else "")


# ── 변경 요약 패널 (Phase 3F) ─────────────────────────────────────────────
def _summarize_changes(
    diff: DiffResult,
    regions: ColorRegions,
    publish_round: int,
) -> str:
    """이번 변경 요약을 fenced div panel 로 생성.

    페이지 최상단 (frontmatter 이후) 에 prepend.
    """
    added_paths = [b.path for b in diff.added]
    removed_paths = [b.path for b in diff.removed]
    modified_paths = [new.path for (_old, new) in diff.modified]
    blue_paths = [b.path for b in regions.blue]

    lines = [f"::: {{.panel section=\"이번 변경 요약 (v{publish_round})\" style=\"info\"}}"]
    lines.append(f"## 이번 변경 요약 (v{publish_round})")
    lines.append("")
    if added_paths:
        lines.append(f"- **추가** ({len(added_paths)}건, 초록 표기):")
        for p in added_paths[:10]:
            lines.append(f"  - `{p}`")
        if len(added_paths) > 10:
            lines.append(f"  - … 외 {len(added_paths) - 10}건")
    if modified_paths:
        lines.append(f"- **수정** ({len(modified_paths)}건, 초록 표기):")
        for p in modified_paths[:10]:
            lines.append(f"  - `{p}`")
        if len(modified_paths) > 10:
            lines.append(f"  - … 외 {len(modified_paths) - 10}건")
    if blue_paths:
        lines.append(f"- **직전 라운드 변경** ({len(blue_paths)}건, 파랑 표기 = 이번엔 안정)")
    if removed_paths:
        lines.append(f"- **삭제** ({len(removed_paths)}건, 표시 불가 — 본문에서 사라짐):")
        for p in removed_paths[:5]:
            lines.append(f"  - `{p}`")
        if len(removed_paths) > 5:
            lines.append(f"  - … 외 {len(removed_paths) - 5}건")
    if not (added_paths or modified_paths or blue_paths or removed_paths):
        lines.append("- 변경 없음 (모든 영역 안정)")
    lines.append(":::")
    lines.append("")
    return "\n".join(lines)


def _prepend_summary(md_source: str, summary: str) -> str:
    """frontmatter 이후 본문 시작 지점에 summary 삽입."""
    if md_source.startswith("---\n"):
        end = md_source.find("\n---\n", 4)
        if end >= 0:
            head = md_source[: end + 5]  # \n---\n 포함
            body = md_source[end + 5 :]
            return head + "\n" + summary + body
    # frontmatter 없으면 맨 앞
    return summary + md_source


# ── D4 회의록 특수 cycling (Phase 3H) ────────────────────────────────────
def _is_meetings_d4(deliverable_type: str) -> bool:
    return deliverable_type.lower() in ("meetings", "회의록", "d4")


def _adjust_for_meetings(diff: DiffResult, regions: ColorRegions) -> ColorRegions:
    """D4 회의록 특수 룰 (사양 §6.6):

    - 신규 회의 항목 (added panel 전체) → 초록
    - 기존 회의 본문 수정 → 일반 cycling (그대로)
    - blue 영역은 회의록에서 시간 표시 자체가 변화 지표이므로 자동 만료 빠르게.

    현 구현: 일반 흐름과 동일하게 처리하되, blue 영역은 빈 list 로 리셋 (회의록
    특수 룰의 핵심 — 누적 blue 가 가독성 저해하므로 회의록은 2-cycle 대신 1-cycle).
    """
    return ColorRegions(green=list(regions.green), blue=[])


# ── 핵심 orchestration ───────────────────────────────────────────────────
def apply_cycling(
    md_source: str,
    color_state: dict,
    *,
    color_reset: bool = False,
    deliverable_type: str = "",
) -> tuple[str, dict, list[str]]:
    """색상 cycling 의 핵심 진입.

    Returns:
        (annotated_md, new_color_state, warnings)
    """
    warnings: list[str] = []
    current_hash = _sha256(md_source)
    publish_round = color_state.get("publish_round", 0)
    baseline = color_state.get("baseline", True)

    # --color-reset 또는 baseline → 첫 publish 처리 (색상 없음, 요약 panel 없음)
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

    # 정상 cycling
    old_blocks = [_block_from_state(d) for d in color_state.get("previous_blocks", [])]
    new_blocks = parse_blocks(md_source)
    diff = diff_blocks(old_blocks, new_blocks)

    previous_green = list(color_state.get("previous_green_regions", []))
    regions = compute_color_regions(old_blocks, new_blocks, previous_green)

    # D4 회의록 특수 룰
    if _is_meetings_d4(deliverable_type):
        regions = _adjust_for_meetings(diff, regions)

    # 색상 주입 + 변경 요약 panel
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
        description="Color Cycling Orchestrator — publish 직전 MD 에 색상 span 주입 (사양: publication-syntax.md §6)",
    )
    parser.add_argument("--input", required=True, help="입력 MD source")
    parser.add_argument("--output", required=True, help="출력 annotated MD")
    parser.add_argument("--meta-in", help="입력 meta.json (없으면 baseline 으로 처리)")
    parser.add_argument("--meta-out", help="출력 meta.json (없으면 --meta-in 위에 in-place 쓰기 안 함, 단순 출력 안 함)")
    parser.add_argument(
        "--color-reset",
        action="store_true",
        help="Phase 3G — 다음 publish 를 baseline (N=1) 으로 처리 (색상 미적용, 상태 초기화)",
    )
    parser.add_argument(
        "--deliverable-type",
        default="",
        help="Phase 3H — 'meetings' 지정 시 D4 회의록 특수 cycling (blue 자동 만료)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    in_path = Path(args.input)
    out_path = Path(args.output)

    if not in_path.is_file():
        print(f"[apply_color_cycling] ERROR: 입력 파일 없음: {in_path}", file=sys.stderr)
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
        f"({len(new_state['previous_green_regions'])} green) → {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
