#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""SSoT 통합 상태 대시보드 빌더 (Sprint S2-2).

⚠️ SUPERSEDED / STANDALONE — 어떤 스킬·훅에도 wiring 되어 있지 않다.
    라이브 SSoT-status 어댑터는 ssot_emit.py (/next → next_emit.py 경유) 이며,
    큐 스코프(5개 큐 + viz JSON)의 권위 기준은 ssot_emit.py 다.
    본 스크립트는 reports/ssot-status.md 를 쓰지만 소비처가 없고, 커버하는
    큐도 3개(drift/policy-impact/mtg)뿐이라 ssot_emit.py 와 스코프가 다르다.
    수동/단독 진단 도구로만 보존한다. 런타임 로직은 변경하지 않는다.

목적:
    drift_scan / policy_impact_scan / mtg_ledger_scan 3 스캐너가 생성한
    각각의 큐 파일(reports/drift-queue.md, policy-impact-queue.md,
    mtg-queue.md) 헤더 라인을 파싱하여, 단일 통합 상태 페이지
    PROJECTS/{product}/reports/ssot-status.md 를 생성한다.

    순수 집계기. 큐 원본·스캐너·게이트 정의를 수정하지 않는다.
    BLOCK 카운트만 Phase 전진 판정의 합산 대상이며 WARN 합산은 표시만 한다.

큐 헤더 포맷 (각 스캐너 SSoT):
    drift          : **BLOCK: N · WARN/UNRESOLVED: M · 공통 미참조 draft: K**
    policy-impact  : 변경 §: X · **IMPACT: N · WARN/COARSE: M**
    mtg-ledger     : **BLOCK: N · FAIL: N · WARN: N**

    IMPACT(policy-impact) 와 FAIL(mtg) 은 BLOCK 등가(게이트 차단)로 집계한다.

사용법:
    python build_ssot_status.py --hub-root <Hub> --product <name>
    python build_ssot_status.py --hub-root <Hub> --product <name> --check
        # --check: 파일 미작성, exit code 만 (CI 용)

exit code:
    0 = 모든 큐의 BLOCK 등가 카운트 = 0 (Phase 전진 허가)
    1 = BLOCK 등가 ≥ 1 (차단)
    2 = 인자 오류
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

# Windows 콘솔 cp949 회피.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


# 헤더 파서: 키워드 → 숫자. `·` 와 `•` 모두 허용. 라벨 변형 흡수.
# drift:         BLOCK / WARN/UNRESOLVED
# policy-impact: IMPACT / WARN/COARSE
# mtg:           BLOCK / FAIL / WARN
# 라벨은 헤더 라인 어디에 있어도(앞 `**` 유무 무관) 매치한다.
# 단어 경계는 비-알파벳/슬래시로 제한해 본문 단어 오탐을 방지한다.
HEADER_NUM = re.compile(
    r"(?<![A-Za-z/])([A-Z]+(?:/[A-Z]+)?)\s*:\s*(\d+)",
)


def _parse_header(text: str) -> dict | None:
    """큐 파일 본문에서 헤더 라인을 찾고 라벨→정수 맵 반환. 실패 시 None.

    헤더는 일반적으로 `> **BLOCK: ... · WARN: ...**` 형태로 인용문 블록
    안에 있다. 본문 첫 30 줄 내에서만 탐색 (정상 큐 파일은 5 줄 이내).
    """
    block_line = None
    for raw in text.splitlines()[:30]:
        if "**" in raw and re.search(r"\*\*[A-Z]+:", raw):
            block_line = raw
            break
    if not block_line:
        return None
    out: dict[str, int] = {}
    for m in HEADER_NUM.finditer(block_line):
        label = m.group(1).upper()
        try:
            out[label] = int(m.group(2))
        except ValueError:
            continue
    if not out:
        return None
    return out


def _file_mtime_date(path: Path) -> str:
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except OSError:
        return "-"


def _summarize_queue(
    path: Path,
    block_labels: tuple[str, ...],
    warn_labels: tuple[str, ...],
) -> dict:
    """단일 큐 파일을 읽어 BLOCK 등가·WARN 등가 카운트와 상태 문자열 반환.

    block_labels 중 하나라도 헤더에 있으면 그 합을 BLOCK 등가로 친다.
    파일 미존재 → status='스캔 미실행', 헤더 파싱 실패 → '파싱 실패'.
    """
    if not path.exists():
        return {
            "block": None,
            "warn": None,
            "updated": "-",
            "status": "스캔 미실행",
            "ok": True,  # 미실행은 차단 아님(단지 정보)
        }
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {
            "block": None,
            "warn": None,
            "updated": "-",
            "status": f"읽기 실패: {e}",
            "ok": False,
        }
    parsed = _parse_header(text)
    if parsed is None:
        return {
            "block": None,
            "warn": None,
            "updated": _file_mtime_date(path),
            "status": "파싱 실패",
            "ok": False,
        }
    block_total = sum(parsed.get(lbl, 0) for lbl in block_labels)
    warn_total = sum(parsed.get(lbl, 0) for lbl in warn_labels)
    ok = block_total == 0
    return {
        "block": block_total,
        "warn": warn_total,
        "updated": _file_mtime_date(path),
        "status": "PASS" if ok else "BLOCK",
        "ok": ok,
    }


# 큐 정의: (제목, 파일명, BLOCK 등가 라벨, WARN 등가 라벨, 큐 설명 문구)
QUEUES = [
    (
        "drift (master pin)",
        "drift-queue.md",
        ("BLOCK",),
        ("WARN/UNRESOLVED",),
        "BLOCK N건 시 클릭해 §단위 확인",
    ),
    (
        "policy-impact (§ → screen)",
        "policy-impact-queue.md",
        ("IMPACT",),
        ("WARN/COARSE",),
        "IMPACT N건 시 §정밀 확인",
    ),
    (
        "mtg-ledger (회의 결정 핀)",
        "mtg-queue.md",
        ("BLOCK", "FAIL"),
        ("WARN",),
        "위임 결정 N건 미반영 시 확인",
    ),
]


def _cell(n) -> str:
    return "-" if n is None else str(n)


def _status_cell(s: dict) -> str:
    if s["status"] == "스캔 미실행":
        return "스캔 미실행"
    if s["status"] == "파싱 실패":
        return "파싱 실패"
    if s.get("ok"):
        return "✅ PASS"
    return "🚨 BLOCK"


def build(hub_root: Path, product: str, check_only: bool) -> int:
    reports = hub_root / "PROJECTS" / product / "reports"
    summaries: list[dict] = []
    total_block = 0
    total_warn = 0
    for title, fname, b_labels, w_labels, _hint in QUEUES:
        s = _summarize_queue(reports / fname, b_labels, w_labels)
        s["title"] = title
        s["file"] = fname
        summaries.append(s)
        if s["block"]:
            total_block += s["block"]
        if s["warn"]:
            total_warn += s["warn"]

    overall_pass = total_block == 0

    if check_only:
        print(
            f"[build_ssot_status] {product}: BLOCK 합계={total_block} "
            f"WARN 합계={total_warn} "
            + ("→ PASS" if overall_pass else "→ 차단")
        )
        return 0 if overall_pass else 1

    if not reports.exists():
        reports.mkdir(parents=True, exist_ok=True)

    now_iso = datetime.now().isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append(f"# SSoT Status — {product}")
    lines.append("")
    lines.append(f"생성: {now_iso}")
    lines.append("")
    lines.append("## 전체 요약")
    lines.append("")
    lines.append("| 큐 | BLOCK | WARN | 마지막 갱신 | 상태 |")
    lines.append("|---|---:|---:|---|---|")
    for s in summaries:
        lines.append(
            f"| {s['title']} | {_cell(s['block'])} | {_cell(s['warn'])} "
            f"| {s['updated']} | {_status_cell(s)} |"
        )
    lines.append(
        f"| **합계** | **{total_block}** | **{total_warn}** | — | — |"
    )
    lines.append("")
    lines.append("## 통과 조건")
    lines.append("모든 큐의 BLOCK = 0 일 때 Phase 전진 허가.")
    lines.append("")
    lines.append("## 상세 큐")
    for (title, fname, _b, _w, hint), s in zip(QUEUES, summaries):
        n = s["block"] if s["block"] is not None else "-"
        lines.append(f"- [[{fname}]] — {hint.replace('N', str(n))}")
    lines.append("")
    lines.append("## Workflow Connections")
    lines.append(
        "- 트리거: drift_scan / policy_impact_scan / mtg_ledger_scan PostToolUse"
    )
    lines.append(
        "- 게이트: [[drift-gate]], [[policy-impact-gate]], [[mtg-gate]]"
    )

    out_path = reports / "ssot-status.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"[build_ssot_status] {product}: BLOCK 합계={total_block} "
        f"WARN 합계={total_warn} → {out_path.relative_to(hub_root)} "
        + ("(PASS)" if overall_pass else "(차단)")
    )
    return 0 if overall_pass else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="SSoT 통합 상태 대시보드 빌더 (drift+policy-impact+mtg 큐 헤더 집계)"
    )
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument(
        "--product",
        required=True,
        help="PROJECTS/<product> 대상 제품 이름",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="파일 미작성, exit code 만 반환 (CI 용)",
    )
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    return build(args.hub_root, args.product, args.check)


if __name__ == "__main__":
    sys.exit(main())
