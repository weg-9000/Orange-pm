#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Confluence XML 구조 품질 검증 스크립트 (C-VERIFY).

목적:
    md_to_storage.py 변환 결과(또는 confluence-source/ 잔존 XML)가 자사 표준
    Confluence Storage Format 품질 규칙을 준수하는지 검증한다. --push 직후 또는
    XML 수작업 편집(권장 X — Option A 정책상 직접 편집 금지) 후 구조 훼손
    여부를 빠르게 탐지한다.

책임 분담 (Option A — MD-only 이후):
    - **MD 단계 (1차 게이트)**: lint_publication_syntax.py (L1~L7) 가 사양
      (publication-syntax.md §10) 준수 여부를 변환 전에 검증한다. 사용자 작성
      오류를 빠르게 차단하는 곳.
    - **XML 단계 (2차 게이트, 본 스크립트)**: 변환기(md_to_storage.py) 자체의
      회귀 또는 직접 편집된 XML 의 품질을 사후 검증한다. 정상 흐름에서는
      L1~L7 통과 + 변환기 정상 동작 시 F1/F2 도 자동 통과.

검증 항목 (FAIL = 차단 / WARN = 경고):
    [FAIL] F1 — 패널 매크로 색상 규칙
               borderColor=#24FE00 / titleColor=#002FD5 /
               titleBGColor=24FE00 / borderStyle=none
               (MD 대응: lint L3 — panel style="common")
    [FAIL] F2 — 코드 블록: ac:plain-text-body + CDATA 사용
               (ac:rich-text-body 안에 코드가 있으면 FAIL)
               (MD 대응: md_to_storage 가 코드블록 자동 CDATA 처리 — 회귀 시 잡힘)
    [FAIL] F3 — 색상 span 허용 영역 검증 (Phase 3E)
               CDATA 코드블록 내부 / ac:parameter 값 내부 / nested span 금지
               (MD 대응: lint L6 — 사양 §6.1)
    [WARN] W1 — FR 번호 체계: FR-\d{3}(-\d+)? 패턴 (§ 베이스 3자리)
               예) FR-101 ✓   FR-101-1 ✓   FR-01 ✗   FR-1 ✗
    [WARN] W2 — 필수 레이아웃 섹션 존재 여부 (ac:layout-section 최소 1개)
    [WARN] W3 — 빈 플레이스홀더 잔존 여부 ({{...}} 패턴)

출력:
    PROJECTS/{product}/reports/verify-report.md  (자동 생성, 수정 금지)

exit code:
    0 = FAIL 없음 (WARN 은 비차단)
    1 = FAIL 1건 이상
    2 = 인자 오류

사용법:
    python render_verify.py --hub-root <Hub> [--product <name>]
    (--product 생략 시 PROJECTS/* 전체)
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

# ── 패턴 정의 ──────────────────────────────────────────────────────────────

# 패널 매크로 파라미터 추출
RE_PANEL_MACRO = re.compile(
    r'<ac:structured-macro[^>]*ac:name="panel"[^>]*>(.*?)</ac:structured-macro>',
    re.DOTALL,
)
RE_PARAM = re.compile(r'<ac:parameter ac:name="([^"]+)">([^<]*)</ac:parameter>')

# 코드 블록: code macro 안에 rich-text-body 가 있으면 FAIL
RE_CODE_MACRO = re.compile(
    r'<ac:structured-macro[^>]*ac:name="code"[^>]*>(.*?)</ac:structured-macro>',
    re.DOTALL,
)
RE_RICH_TEXT_BODY = re.compile(r'<ac:rich-text-body>')

# FR 번호 — §-base 3자리 검증
RE_FR_ANY = re.compile(r'\bFR-(\d+)(-\d+)?\b')
RE_FR_VALID = re.compile(r'\bFR-\d{3}(-\d+)?\b')

# 필수 레이아웃
RE_LAYOUT_SECTION = re.compile(r'<ac:layout-section')

# 플레이스홀더 잔존
RE_PLACEHOLDER = re.compile(r'\{\{[^}]+\}\}')

# 권장 패널 색상 (CLAUDE.md 표준)
EXPECTED_PANEL_COLORS = {
    "borderColor": "#24FE00",
    "titleColor": "#002FD5",
    "titleBGColor": "24FE00",
    "borderStyle": "none",
}


def _check_panel_colors(xml: str) -> list[tuple[str, str, str]]:
    """[F1] 패널 매크로 색상 규칙 검증. (level, code, message) 반환."""
    issues: list[tuple[str, str, str]] = []
    for i, m in enumerate(RE_PANEL_MACRO.finditer(xml), 1):
        body = m.group(1)
        params = dict(RE_PARAM.findall(body))
        for key, expected in EXPECTED_PANEL_COLORS.items():
            actual = params.get(key, "")
            if actual and actual != expected:
                issues.append((
                    "FAIL", "F1",
                    f"패널 #{i}: {key}={actual!r} (기대 {expected!r})",
                ))
    return issues


def _check_code_blocks(xml: str) -> list[tuple[str, str, str]]:
    """[F2] code macro 안 rich-text-body 사용 금지."""
    issues: list[tuple[str, str, str]] = []
    for i, m in enumerate(RE_CODE_MACRO.finditer(xml), 1):
        body = m.group(1)
        if RE_RICH_TEXT_BODY.search(body):
            issues.append((
                "FAIL", "F2",
                f"코드 블록 #{i}: ac:rich-text-body 사용 — ac:plain-text-body + CDATA 로 교체 필요",
            ))
    return issues


# Phase 3E — F3: 색상 span 허용 영역 검증
# 코드블록(CDATA) 내부, 매크로 파라미터 값(ac:parameter), nested span 금지.
RE_CDATA_BLOCK = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)
RE_COLOR_SPAN = re.compile(
    r'<span\s+style\s*=\s*"color:\s*rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)\s*"\s*>(.*?)</span>',
    re.DOTALL | re.IGNORECASE,
)
RE_PARAM_TAG = re.compile(
    r"<ac:parameter[^>]*>(.*?)</ac:parameter>", re.DOTALL
)


def _check_color_spans(xml: str) -> list[tuple[str, str, str]]:
    """[F3] 색상 span 이 허용 영역에만 존재하는지 검증.

    금지 영역:
      - CDATA 코드블록 내부 (XML 파서가 인식 안 함 → 의미 없는 마크업)
      - ac:parameter 값 내부 (매크로 파라미터에 색상 span 들어가면 깨짐)
      - nested span (`<span><span>...</span></span>`)
    """
    issues: list[tuple[str, str, str]] = []

    # CDATA 내부에 span 이 있는지
    for i, m in enumerate(RE_CDATA_BLOCK.finditer(xml), 1):
        body = m.group(1)
        if RE_COLOR_SPAN.search(body):
            issues.append((
                "FAIL", "F3",
                f"CDATA #{i} 내부 색상 span 발견 — 코드블록 내부는 색상 표기 불가",
            ))

    # ac:parameter 값 내부에 span
    for i, m in enumerate(RE_PARAM_TAG.finditer(xml), 1):
        body = m.group(1)
        if RE_COLOR_SPAN.search(body):
            issues.append((
                "FAIL", "F3",
                f"ac:parameter #{i} 내부 색상 span 발견 — 매크로 파라미터에 span 금지",
            ))

    # nested span: span 의 inner 에 또 span 이 있는지
    for i, m in enumerate(RE_COLOR_SPAN.finditer(xml), 1):
        inner = m.group(1)
        if RE_COLOR_SPAN.search(inner):
            issues.append((
                "FAIL", "F3",
                f"색상 span #{i}: nested span — 사양 §6.1 nested 금지",
            ))

    return issues


def _check_fr_numbering(xml: str) -> list[tuple[str, str, str]]:
    """[W1] FR 번호 §-base 3자리 형식 검증."""
    issues: list[tuple[str, str, str]] = []
    bad: list[str] = []
    for m in RE_FR_ANY.finditer(xml):
        full = m.group(0)
        if not RE_FR_VALID.match(full):
            bad.append(full)
    bad = list(dict.fromkeys(bad))  # 중복 제거
    if bad:
        sample = ", ".join(bad[:5]) + ("..." if len(bad) > 5 else "")
        issues.append((
            "WARN", "W1",
            f"FR 번호 형식 불일치 {len(bad)}건 (예: {sample}) — 기대: FR-NNN 또는 FR-NNN-N",
        ))
    return issues


def _check_layout(xml: str) -> list[tuple[str, str, str]]:
    """[W2] ac:layout-section 최소 1개 존재."""
    if not RE_LAYOUT_SECTION.search(xml):
        return [("WARN", "W2", "ac:layout-section 없음 — Confluence Storage Format 레이아웃 구조 확인 필요")]
    return []


def _check_placeholders(xml: str) -> list[tuple[str, str, str]]:
    """[W3] {{...}} 플레이스홀더 잔존."""
    found = list(dict.fromkeys(RE_PLACEHOLDER.findall(xml)))
    if found:
        sample = ", ".join(found[:5]) + ("..." if len(found) > 5 else "")
        return [("WARN", "W3", f"플레이스홀더 {len(found)}건 잔존 ({sample}) — 치환 필요")]
    return []


def verify_file(xml_path: Path) -> list[tuple[str, str, str]]:
    xml = xml_path.read_text(encoding="utf-8", errors="replace")
    issues: list[tuple[str, str, str]] = []
    issues += _check_panel_colors(xml)
    issues += _check_code_blocks(xml)
    issues += _check_color_spans(xml)
    issues += _check_fr_numbering(xml)
    issues += _check_layout(xml)
    issues += _check_placeholders(xml)
    return issues


def scan(hub_root: Path, product: str | None = None) -> int:
    projects_root = hub_root / "PROJECTS"
    if not projects_root.is_dir():
        print(f"[verify] PROJECTS 없음: {projects_root} — 스캔 대상 없음")
        return 0

    products = (
        [projects_root / product]
        if product
        else sorted(p for p in projects_root.iterdir() if p.is_dir())
    )

    total_fail = 0

    for proj in products:
        pname = proj.name
        src_dir = proj / "confluence-source"
        xml_files = sorted(src_dir.glob("*.xml")) if src_dir.is_dir() else []

        if not xml_files:
            print(f"[verify] {pname}: XML 없음 — 건너뜀")
            continue

        file_results: list[tuple[Path, list]] = []
        for xf in xml_files:
            issues = verify_file(xf)
            file_results.append((xf, issues))

        n_fail = sum(1 for _, iss in file_results for (lv, _, _) in iss if lv == "FAIL")
        n_warn = sum(1 for _, iss in file_results for (lv, _, _) in iss if lv == "WARN")
        total_fail += n_fail

        reports = proj / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        out = reports / "verify-report.md"

        lines = [
            f"# verify-report — {pname}",
            "",
            f"> 생성: {datetime.now().isoformat(timespec='seconds')}"
            f" · render_verify.py 자동 생성 (수정 금지)",
            f"> **FAIL: {n_fail} · WARN: {n_warn}**",
            "",
        ]

        for xf, issues in file_results:
            rel = xf.relative_to(proj)
            lines += [f"## {rel}", ""]
            if not issues:
                lines += ["> ✅ 모든 검증 통과", ""]
                continue
            lines += [
                "| 수준 | 코드 | 내용 |",
                "|---|---|---|",
            ]
            for lv, code, msg in issues:
                emoji = "🔴" if lv == "FAIL" else "🟡"
                lines.append(f"| {emoji} **{lv}** | {code} | {msg} |")
            lines.append("")

        lines += [
            "---",
            "",
            "## 검증 기준",
            "| 코드 | 수준 | 규칙 |",
            "|---|---|---|",
            "| F1 | FAIL | 패널 매크로: borderColor=#24FE00 / titleColor=#002FD5 / titleBGColor=24FE00 / borderStyle=none |",
            "| F2 | FAIL | 코드 블록: ac:plain-text-body + CDATA (ac:rich-text-body 금지) |",
            "| F3 | FAIL | 색상 span: CDATA/ac:parameter/nested 내부 금지 (Phase 3E) |",
            "| W1 | WARN | FR 번호: FR-NNN 또는 FR-NNN-N 형식 (§-base 3자리) |",
            "| W2 | WARN | ac:layout-section 최소 1개 |",
            "| W3 | WARN | {{...}} 플레이스홀더 잔존 없음 |",
        ]
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[verify] {pname}: FAIL={n_fail} WARN={n_warn} → {out.relative_to(hub_root)}")

    print(f"[verify] 완료 — 총 FAIL {total_fail}건"
          + ("" if total_fail == 0 else " (게이트 차단)"))
    return 1 if total_fail else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Confluence XML 구조 품질 검증")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", default=None, help="PROJECTS/<product> (생략=전체)")
    ap.add_argument("--file", default=None, type=Path,
                    help="단일 XML 파일 직접 지정 (--hub-root 없이도 가능)")
    args = ap.parse_args()

    if args.file:
        if not args.file.is_file():
            sys.stderr.write(f"파일 없음: {args.file}\n")
            return 2
        issues = verify_file(args.file)
        n_fail = sum(1 for lv, _, _ in issues if lv == "FAIL")
        for lv, code, msg in issues:
            print(f"[{lv}] {code}: {msg}")
        if not issues:
            print("✅ 모든 검증 통과")
        return 1 if n_fail else 0

    if not args.hub_root or not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    return scan(args.hub_root, args.product)


if __name__ == "__main__":
    sys.exit(main())
