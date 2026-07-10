#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lazy-Split Trigger Check (Phase 5D).

Cluster draft 가 분할 임계를 초과하는지 검사하고 권고를 출력한다.
실제 분할은 PM 승인 후 fanout 재실행 또는 수동 처리.

임계 (publication-syntax.md / cluster-draft.md 사양):
    - 본문 > 1500 lines
    - §1+§2 항목 수 > 8
    - R2 BLOCK 누적 (HARD+SOFT) > 5  (integrate 산출 참조)
    - PM 명시 --force-split

자식 cluster ID 패턴 (사양):
    {부모_cluster_id}-{suffix}   예: PV-01 → PV-01-a, PV-01-b

CLI:
    python lazy_split_check.py --drafts drafts/cluster_*.draft.md
        [--integrate-report reports/integrate/{product}.block.md]
        [--threshold-lines 1500] [--threshold-items 8] [--threshold-blocks 5]
        [--report reports/lazy-split-report.md]

종료 코드: 0 (분할 권고 없음) / 1 (1개 이상 권고) / 2 (입력 오류)
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_THRESHOLD_LINES = 1500
DEFAULT_THRESHOLD_ITEMS = 8
DEFAULT_THRESHOLD_BLOCKS = 5


@dataclass
class SplitCheck:
    """단일 cluster 의 분할 검사 결과."""

    cluster_path: Path
    cluster_id: str = ""
    body_lines: int = 0
    section1_items: int = 0  # §1 정책 결정의 표/리스트 항목 수
    section2_items: int = 0  # §2 화면 설계의 표/리스트 항목 수
    integrate_blocks: int = 0  # R2 BLOCK 누적
    triggers: list[str] = field(default_factory=list)  # 위반 임계 목록

    @property
    def should_split(self) -> bool:
        return bool(self.triggers)


def _extract_cluster_id(text: str) -> str:
    m = re.search(r'cluster_id:\s*"?([^"\n]+)"?', text)
    return m.group(1).strip() if m else ""


def _count_panel_items(body: str, section_keyword: str) -> int:
    """주어진 panel section 안의 표 행 + 리스트 항목 수."""
    pattern = re.compile(
        r'::: \{\.panel section="[^"]*' + re.escape(section_keyword) + r'[^"]*"[^}]*\}(.*?):::',
        re.DOTALL,
    )
    m = pattern.search(body)
    if not m:
        return 0
    panel_body = m.group(1)
    # 표 본문 행 수 (헤더/구분선 제외)
    table_rows = 0
    in_table = False
    for line in panel_body.splitlines():
        stripped = line.strip()
        if re.match(r"^\|[\s\-:|]+\|$", stripped):
            in_table = True
            continue
        if stripped.startswith("|") and in_table:
            # placeholder ({{...}}) 만 있는 행은 제외 (양식 의도)
            if re.fullmatch(r"\|\s*\{\{[^}]+\}\}\s*(\|\s*[^|]*)*\|", stripped):
                continue
            table_rows += 1
        else:
            in_table = False
    # 리스트 항목
    list_items = sum(
        1 for ln in panel_body.splitlines() if re.match(r"\s*[-*+]\s+\S", ln)
    )
    return table_rows + list_items


def _count_blocks_for_cluster(
    integrate_report: Path | None, cluster_id: str
) -> int:
    """integrate 산출에서 해당 cluster_id 의 BLOCK 카운트."""
    if not integrate_report or not integrate_report.is_file():
        return 0
    text = integrate_report.read_text(encoding="utf-8", errors="replace")
    # cluster_id 가 본문에 등장하면서 같은 라인 / 인접 블록에 HARD/SOFT 가 있는지
    cluster_lines = [
        ln for ln in text.splitlines() if cluster_id in ln
    ]
    count = 0
    for ln in cluster_lines:
        if re.search(r"\b(HARD|SOFT)_?BLOCK\b", ln, re.IGNORECASE):
            count += 1
    return count


def check_cluster_draft(
    path: Path,
    *,
    integrate_report: Path | None = None,
    threshold_lines: int = DEFAULT_THRESHOLD_LINES,
    threshold_items: int = DEFAULT_THRESHOLD_ITEMS,
    threshold_blocks: int = DEFAULT_THRESHOLD_BLOCKS,
) -> SplitCheck:
    text = path.read_text(encoding="utf-8", errors="replace")
    cluster_id = _extract_cluster_id(text)

    # body (frontmatter 제외)
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end >= 0:
            body = text[end + 5 :]

    check = SplitCheck(
        cluster_path=path,
        cluster_id=cluster_id,
        body_lines=len([ln for ln in body.splitlines() if ln.strip()]),
        section1_items=_count_panel_items(body, "정책"),
        section2_items=_count_panel_items(body, "화면"),
        integrate_blocks=_count_blocks_for_cluster(integrate_report, cluster_id),
    )

    if check.body_lines > threshold_lines:
        check.triggers.append(
            f"본문 라인 수 {check.body_lines} > {threshold_lines}"
        )
    items_total = check.section1_items + check.section2_items
    if items_total > threshold_items:
        check.triggers.append(
            f"§1+§2 항목 수 {items_total} > {threshold_items}"
        )
    if check.integrate_blocks > threshold_blocks:
        check.triggers.append(
            f"R2 BLOCK 누적 {check.integrate_blocks} > {threshold_blocks}"
        )

    return check


def format_report(
    checks: list[SplitCheck],
    *,
    threshold_lines: int,
    threshold_items: int,
    threshold_blocks: int,
) -> str:
    lines = ["# Lazy-Split 권고 (Phase 5D)\n"]
    lines.append("**임계** (publication-syntax.md / cluster-draft.md 사양):")
    lines.append(f"- 본문 라인 > {threshold_lines}")
    lines.append(f"- §1+§2 항목 수 > {threshold_items}")
    lines.append(f"- R2 BLOCK 누적 > {threshold_blocks}\n")

    splittable = [c for c in checks if c.should_split]
    lines.append(f"**총 {len(checks)} cluster 검사, {len(splittable)} cluster 분할 권고**\n")

    if not splittable:
        lines.append("모든 cluster 가 임계 이내 — 분할 권고 없음.\n")
        return "\n".join(lines) + "\n"

    lines.append("| Cluster ID | 본문 라인 | §1 항목 | §2 항목 | BLOCK | 트리거 |")
    lines.append("|---|---|---|---|---|---|")
    for c in splittable:
        triggers = "<br>".join(c.triggers) or "_(임계 이내)_"
        lines.append(
            f"| `{c.cluster_id}` | {c.body_lines} | "
            f"{c.section1_items} | {c.section2_items} | "
            f"{c.integrate_blocks} | {triggers} |"
        )

    lines.append("\n## 권장 후속 처리\n")
    lines.append("각 분할 권고 cluster 에 대해 PM 확인 후:")
    lines.append("1. 자식 cluster ID 부여: `{부모_cluster_id}-a`, `-b`, ...")
    lines.append("2. 원본 cluster draft 의 멤버 노드를 자식 간 재배분")
    lines.append("3. `cluster_identify.py` 의 `cluster_map.json` 에 자식 ID 등재")
    lines.append("4. `fanout --cluster-mode` 재실행 → 자식 cluster drafts 생성")
    lines.append("5. (선택) `--force-split` 으로 임계 미달 시도 가능\n")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lazy_split_check",
        description="Cluster draft 분할 임계 검사 (Phase 5D)",
    )
    parser.add_argument(
        "--drafts", nargs="+", type=Path, required=True,
        help="cluster draft 파일들 (drafts/cluster_*.draft.md)",
    )
    parser.add_argument(
        "--integrate-report", type=Path, default=None,
        help="integrate R2 BLOCK 보고서 (옵션)",
    )
    parser.add_argument("--threshold-lines", type=int, default=DEFAULT_THRESHOLD_LINES)
    parser.add_argument("--threshold-items", type=int, default=DEFAULT_THRESHOLD_ITEMS)
    parser.add_argument("--threshold-blocks", type=int, default=DEFAULT_THRESHOLD_BLOCKS)
    parser.add_argument(
        "--report", type=Path, default=None,
        help="보고서 markdown 출력 경로",
    )
    args = parser.parse_args(argv)

    missing = [p for p in args.drafts if not p.is_file()]
    if missing:
        print(f"[lazy_split_check] ERROR: 파일 없음: {missing}", file=sys.stderr)
        return 2

    checks = [
        check_cluster_draft(
            p,
            integrate_report=args.integrate_report,
            threshold_lines=args.threshold_lines,
            threshold_items=args.threshold_items,
            threshold_blocks=args.threshold_blocks,
        )
        for p in args.drafts
    ]

    report = format_report(
        checks,
        threshold_lines=args.threshold_lines,
        threshold_items=args.threshold_items,
        threshold_blocks=args.threshold_blocks,
    )

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")
    else:
        print(report)

    splittable = [c for c in checks if c.should_split]
    print(
        f"[lazy_split_check] {len(checks)} cluster 검사, "
        f"{len(splittable)} 분할 권고",
        file=sys.stderr,
    )
    return 1 if splittable else 0


if __name__ == "__main__":
    raise SystemExit(main())
