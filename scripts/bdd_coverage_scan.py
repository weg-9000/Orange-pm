#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""BDD 수용 기준 커버리지 스캐너 (WP-BDD · 계약 C-BDD-COV).

목적:
    행위 명세(draft 의 매트릭스·4-state)가 실행 가능한 수용 기준(.feature)으로
    빠짐없이 사상됐는지 결정적으로 검증한다. 기획 단계의 행위 구멍 — screen 의
    error 상태 누락, .feature 미생성(stale) — 을 Phase 전진 전에 자동 적발한다.
    순수 스크립트(모델 미관여). draft·feature 를 수정하지 않는다(읽기 전용 + 큐 산출).

판정 (gates/bdd-coverage-gate.md SSoT):
    UNCOVERED : screen 4-state 필수 상태(idle/loading/success/error) 누락
                (사유 N/A 표기 없음) → BLOCK. 4-state 표 자체가 없는 screen draft
                도 '전부 누락' 으로 UNCOVERED 처리한다(허위 green 방지).
    STALE     : draft 에 행위 명세 표 있으나 reports/bdd/{WO}.feature 부재 또는
                draft mtime > feature mtime → BLOCK (bdd_assemble 미실행/구버전)
    WARN      : policy 매트릭스 비공백 셀 비율 낮음(미정의 셀 다수) — 비차단 권고
    OK        : 필수 상태 충족 & feature 최신

사용법:
    python bdd_coverage_scan.py --hub-root <Hub> --product <p>

exit code: 0 UNCOVERED·STALE 없음 / 1 차단 1건 이상 / 2 인자 오류
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bdd_assemble as A  # noqa: E402  (표 추출·frontmatter 파서 재사용 — SSoT)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

# 화면 필수 상태 동의어 그룹 — SSoT 는 bdd_assemble(assemble 와 판정 일치 보장).
STATE_GROUPS = A.STATE_GROUPS
NA = re.compile(r"해당\s*없음|N/?A|불필요", re.I)


def screen_missing_states(table) -> list[str]:
    """4-state 표에서 누락된 필수 상태 그룹명 목록.

    *상태 컬럼(col0)* 만 검사한다 — 전이 대상('다음 상태')·조건 텍스트에만
    등장한 상태는 행으로 정의된 것이 아니므로 커버로 치지 않는다(flow 규칙).
    상태 행이 N/A 사유와 함께 존재하면 그 행 col0 매칭으로 자연히 커버 처리된다.
    """
    _, data = table
    col0 = " ".join(r[0] for r in data if r)
    missing = [name for name, pat in STATE_GROUPS.items() if not pat.search(col0)]
    # prose 식 N/A 면제 fallback: "해당 없음 {그룹}" 표기가 표 어디든 있으면 면제.
    if missing:
        whole = " ".join(" ".join(r) for r in data)
        if NA.search(whole):
            missing = [m for m in missing if not re.search(
                STATE_GROUPS[m].pattern + r".{0,12}" + NA.pattern, whole, re.I)
                and not re.search(NA.pattern + r".{0,12}" + STATE_GROUPS[m].pattern, whole, re.I)]
    return missing


def policy_empty_ratio(table) -> tuple[int, int]:
    """매트릭스 (비공백 셀 수, 전체 데이터 셀 수)."""
    header, data = table
    n_act = max(len(header) - 1, 0)
    total = filled = 0
    for row in data:
        for cell in row[1:1 + n_act]:
            total += 1
            if not A.EMPTY_CELL.match(cell.strip()):
                filled += 1
    return filled, total


def scan(hub: Path, product: str) -> int:
    proj = hub / "PROJECTS" / product
    drafts = proj / "drafts"
    if not drafts.is_dir():
        sys.stderr.write(f"drafts not found: {drafts}\n")
        return 2
    bdd_dir = proj / "reports" / "bdd"

    rows = []
    uncovered = stale = warn = 0
    for d in sorted(drafts.glob("*.draft.md")):
        wo = d.stem.replace(".draft", "")
        text = d.read_text(encoding="utf-8", errors="replace")
        fm, body = A._parse_frontmatter(text)
        if A.is_wo_stub(body):
            continue  # WO 지시 스텁 — 행위 명세 산출물 아님(실제 draft 는 별도)
        kind = (fm.get("type") or "").strip().lower()
        tables = A.extract_tables(body)
        matrix = A.find_matrix_table(tables)
        state_tbl = A.find_state_table(tables)
        # assemble_one 과 동일 정규화: policy 명시 or (무type+matrix) → policy,
        # 그 외(cluster_draft 등 비표준 type 포함) 전부 screen 으로 사상한다.
        # (scan 과 assemble 의 kind 가 어긋나면 STALE/UNCOVERED 가 허위 판정된다.)
        if kind == "policy" or (not kind and matrix):
            kind = "policy"
        else:
            kind = "screen"
        if kind == "policy" and not matrix:
            continue
        # screen 상태 커버리지 출처: 표준 단일 표 우선, 없으면 '### N-x. {state}'
        # 4-state 하위섹션 형식(cloud-calculator 등 관습)을 인식한다.
        sub_cov: dict | None = None
        if kind == "screen" and not state_tbl:
            # 표·N/A 명시 모두 커버로 인정({group: 'table'|'na'}).
            sub_cov = A.state_group_coverage(body)
            if not sub_cov:
                # 4-state 표·하위섹션 모두 없음 = 필수 4-state 전부 누락(허위 green 방지).
                feat = bdd_dir / f"{wo}.feature"
                note = ("4-state 표/하위섹션 없음 — /flow 작성 필요" if feat.exists()
                        else "4-state 표/하위섹션·feature 모두 없음 — /flow 후 /bdd")
                uncovered += 1
                rows.append((wo, kind, "표 없음(4-state 전부 누락)", "UNCOVERED", note))
                continue

        feat = bdd_dir / f"{wo}.feature"
        if not feat.exists():
            stale += 1
            rows.append((wo, kind, "—", "STALE", "feature 미생성 — /bdd 실행 필요"))
            continue
        if d.stat().st_mtime > feat.stat().st_mtime:
            stale += 1
            rows.append((wo, kind, "—", "STALE",
                         "draft 변경 후 feature 미갱신 — /bdd 재실행 필요"))
            continue

        if kind == "screen":
            if state_tbl:
                miss = screen_missing_states(state_tbl)
                src = "표"
            else:
                miss = [g for g in STATE_GROUPS if g not in sub_cov]
                na = [g for g in STATE_GROUPS if sub_cov.get(g) == "na"]
                src = "하위섹션" + (f", N/A:{','.join(na)}" if na else "")
            if miss:
                uncovered += 1
                rows.append((wo, kind, f"누락 {','.join(miss)}", "UNCOVERED",
                             f"필수 4-state 누락(사유 N/A 없음) — flow 재작성 필요 [{src}]"))
            else:
                rows.append((wo, kind, f"4-state 충족({src})", "OK", "필수 상태 전부 커버"))
        else:
            filled, total = policy_empty_ratio(matrix)
            if total and filled / total < 0.5:
                warn += 1
                rows.append((wo, kind, f"정의 {filled}/{total} 셀", "WARN",
                             "매트릭스 미정의 셀 과반 — 행위 누락 점검 권고"))
            else:
                rows.append((wo, kind, f"정의 {filled}/{total} 셀", "OK",
                             "주요 셀 정의됨"))

    qdir = proj / "reports"
    qdir.mkdir(parents=True, exist_ok=True)
    q = qdir / "bdd-coverage-queue.md"
    lines = [
        f"# bdd-coverage-queue — {product}",
        "",
        f"> 생성: {datetime.now().isoformat(timespec='seconds')} · bdd_coverage_scan.py (수정 금지)",
        f"> **UNCOVERED: {uncovered} · STALE: {stale} · WARN: {warn}**",
        "",
        "| WO | 유형 | 커버리지 | 상태 | 사유 |",
        "|---|---|---|---|---|",
    ]
    if rows:
        for wo, kind, cov, st, why in rows:
            lines.append(f"| {wo} | {kind} | {cov} | **{st}** | {why} |")
    else:
        lines.append("| _(행위 명세 표 있는 draft 없음)_ | — | — | OK | — |")
    lines += [
        "",
        "## 처리 기준 (gates/bdd-coverage-gate.md)",
        "- UNCOVERED: 화면 필수 4-state 누락 → /flow 재작성 후 /bdd 재실행",
        "- STALE: feature 미생성·구버전 → /bdd 실행",
        "- WARN: policy 매트릭스 미정의 셀 과반 → 행위 누락 점검(비차단)",
    ]
    q.write_text("\n".join(lines) + "\n", encoding="utf-8")
    blocked = uncovered + stale
    print(f"[bdd_coverage_scan] {product}: UNCOVERED={uncovered} STALE={stale} "
          f"WARN={warn} → {q.relative_to(hub)}")
    print(f"[bdd_coverage_scan] 완료 — 차단 {blocked}건"
          + ("" if blocked == 0 else " (bdd-coverage-gate 차단)"))
    return 1 if blocked else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="BDD 수용 기준 커버리지 스캔 (C-BDD-COV)")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", required=True)
    a = ap.parse_args()
    if not a.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {a.hub_root}\n")
        return 2
    return scan(a.hub_root, a.product)


if __name__ == "__main__":
    sys.exit(main())
