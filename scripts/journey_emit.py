#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""journey_emit — journey 스토리보드(reports/journey-*.md) → 정규화 journey 계약.

소스는 두 갈래이며 **mtime 최신본**을 파싱한다(읽기 전용):
    reports/journey-latest.md            — journey_build.py 자동 생성(draft 편집 훅)
    reports/journey-{YYYYMMDD-HHMM}.md   — /journey 스킬 수동 생성(액터 필터·서사 보강)

[VIZ-LAYER ADAPTER]
    유일한 소비자는 외부 확장(orange-pm-viz) — PrototypeView 사용자 여정 보드.
    계약: docs/visual-interface/01-data-contract.md §5c.

스토리보드 화면 라인 형식(SKILL.md 단계4):
    [{순번}] {SCR-NNN} {화면명}  {상태아이콘}
    + 하위 들여쓰기 상세(진입 조건/핵심 행동/전환/이탈/목적) — 있는 키만 부가
상태 아이콘: ✅ 완료 / 📝 작성중 / 🔲 스케치 / ⬜ 미착수
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import _emit_common as C

# [1] SCR-001 화면명  ✅   (아이콘은 선택)
_LINE = re.compile(r"^\[(\d+)\]\s+(\S+)\s+(.+?)\s*([✅📝🔲⬜])?\s*$")
_ICON_STATUS = {"✅": "done", "📝": "draft", "🔲": "sketch", "⬜": "todo"}

# 화면 라인 하위 상세(SKILL.md 단계4) — viz journey 보드가 표시할 키로 정규화.
# "진입 조건: …" / "핵심 행동: …" / "전환: → SCR-002 (조건)" / "이탈: ✕ 경로" / "목적: …"
_DETAIL_KEYS = {
    "진입 조건": "entry", "진입조건": "entry",
    "핵심 행동": "action", "핵심행동": "action",
    "전환": "transition",
    "이탈": "exit",
    "목적": "purpose",
    "REQ": "req",
}
_DETAIL_RE = re.compile(
    r"^(진입 ?조건|핵심 ?행동|전환|이탈|목적|REQ)\s*:\s*(.+)$"
)


def parse_storyboard(text: str) -> list[dict]:
    """스토리보드 본문 → [{order, id, label, status, entry?, action?, …}].

    화면 라인 + 그 하위 들여쓰기 상세 라인을 추출한다(상세는 있는 키만 부가).
    """
    steps: list[dict] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        m = _LINE.match(line)
        if m:
            order, sid, label, icon = m.group(1), m.group(2), m.group(3).strip(), m.group(4)
            # SCR-NNN / G2-... 형태(하이픈 포함 식별자)만 단계로 인정 — 요약/구분선 오탐 방지
            if not re.match(r"^[A-Za-z0-9]+-", sid):
                current = None
                continue
            current = {
                "order": int(order), "id": sid, "label": label,
                "status": _ICON_STATUS.get(icon or "", "unknown"),
            }
            steps.append(current)
            continue
        if current is not None and raw.startswith((" ", "\t")):
            dm = _DETAIL_RE.match(line)
            if dm:
                key = _DETAIL_KEYS.get(dm.group(1).replace(" ", ""), None) \
                    or _DETAIL_KEYS.get(dm.group(1))
                val = dm.group(2).strip().lstrip("→✕").strip()
                if key and val:
                    current[key] = val
        elif line and not raw.startswith((" ", "\t")):
            current = None  # 화면 블록 종료(요약 섹션 등)
    steps.sort(key=lambda s: s["order"])
    return steps


def _latest_journey(reports_dir: Path) -> Path | None:
    """가장 최근 수정된 journey-*.md — journey-latest.md(자동)와 타임스탬프본(수동)
    중 실제 최신을 고른다(파일명 사전순은 latest 가 항상 이겨 stale 위험)."""
    files = list(reports_dir.glob("journey-*.md"))
    if not files:
        return None
    try:
        return max(files, key=lambda p: p.stat().st_mtime)
    except OSError:
        return sorted(files)[-1]


def transform_journey(text: str, product: str = "") -> dict:
    return {"version": "", "product": product, "kind": "journey", "steps": parse_storyboard(text)}


def main(argv: list[str]) -> int:
    args = C.make_parser("journey").parse_args(argv)
    if args.from_fixture:
        return C.emit(C.load_fixture(args.from_fixture))
    if not (args.hub_root and args.product):
        sys.stderr.write("--hub-root, --product 필요\n")
        return 2
    rdir = C.product_dir(args.hub_root, args.product) / "reports"
    src = _latest_journey(rdir) if rdir.is_dir() else None
    if not src:
        sys.stderr.write(f"journey-*.md 없음: {rdir}\n")
        return C.emit({"version": "empty", "product": args.product, "kind": "journey", "steps": []}) or 1
    return C.emit(transform_journey(src.read_text(encoding="utf-8"), args.product))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
