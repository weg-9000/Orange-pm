#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Publication Syntax Lint — MD 발행 문법 검증 (publication-lint).

목적:
    Option A(MD-only) 토대의 발행 문법(publication-syntax.md 사양)이
    Markdown 정본에 올바르게 적용됐는지 검증한다. md_to_storage.py 호출 전
    빠른 피드백을 제공한다.

검증 항목 (FAIL = 차단 / WARN = 경고):
    [FAIL] L1 — Fenced div 클래스가 허용 목록
                (panel | info | warning | note | tip | expand)
    [FAIL] L2 — Panel 블록(.panel)은 section="..." 속성 필수
    [FAIL] L3 — Panel style 값이 허용 매핑
                (common | product | tbd | warning | info)
    [WARN] L4 — 코드블록 언어 fence 가 알려진 언어
                (python | bash | json | yaml | sql | javascript |
                 typescript | markdown | xml | html | css | text 등)
    [WARN] L5 — 자동 매크로 {{...}} 미해결 placeholder
                (DATE/PRODUCT_NAME/DOC_ID/VERSION/toc/change_history 는 허용)
    [FAIL] L6 — 색상 span nested 금지 (Phase 3 예약, 룰은 사전 활성)
    [FAIL] L7 — 표 컬럼 수 일관성 (헤더 행과 본문 행 동일)

출력:
    표준 출력 (render_verify.py 보고 형식)
    --report <path> 지정 시 동일 내용을 md 파일로 저장

exit code:
    0 = FAIL 없음 (WARN 비차단)
    1 = FAIL 1건 이상
    2 = I/O 오류

사용법:
    python lint_publication_syntax.py --input X.md [--report report.md]
    python lint_publication_syntax.py --hub-root <Hub> [--product <name>]
        (--product 생략 시 PROJECTS/* 전체)

사양 SSoT:
    orange-pm-plugin/skills/render/publication-syntax.md §10 검증 게이트
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

# ── 규칙 메타 ──────────────────────────────────────────────────────────────

RULES: dict[str, dict[str, str]] = {
    "L1": {"level": "FAIL", "desc": "Fenced div 클래스가 허용 목록"},
    "L2": {"level": "FAIL", "desc": "Panel section 속성 누락"},
    "L3": {"level": "FAIL", "desc": "Panel style 값이 허용 매핑"},
    "L4": {"level": "WARN", "desc": "알 수 없는 코드 언어"},
    "L5": {"level": "WARN", "desc": "미해결 placeholder"},
    "L6": {"level": "FAIL", "desc": "색상 span nested"},
    "L7": {"level": "FAIL", "desc": "표 컬럼 수 불일치"},
}

ALLOWED_DIV_CLASSES = {"panel", "info", "warning", "note", "tip", "expand"}
ALLOWED_PANEL_STYLES = {"common", "product", "tbd", "warning", "info"}
ALLOWED_CODE_LANGS = {
    "python", "py",
    "bash", "sh", "shell", "zsh",
    "json", "yaml", "yml", "toml", "ini",
    "sql",
    "javascript", "js",
    "typescript", "ts",
    "markdown", "md",
    "xml", "html", "css",
    "text", "txt", "plain", "plaintext",
    "mermaid", "plantuml",
    "diff", "patch",
    "java", "kotlin", "go", "rust", "c", "cpp", "csharp",
    "ruby", "php", "perl",
    "dockerfile", "makefile",
}
ALLOWED_PLACEHOLDERS = {
    # 발행 시 치환되는 매크로 placeholder
    "DATE", "PRODUCT_NAME", "DOC_ID", "VERSION", "WO_ID",
    "LAST_UPDATED", "AUTHOR", "TYPE", "LAYER",
    # 자동 매크로 명령형 placeholder
    "toc",
}
# {{change_history 3}} 처럼 인자 동반 매크로 prefix
ALLOWED_PLACEHOLDER_PREFIXES = ("change_history",)


# ── 패턴 정의 ──────────────────────────────────────────────────────────────

# Fenced div 시작: ::: {.class attr="..." ...}
# 닫는 div 는 ::: 단독 줄
RE_DIV_OPEN = re.compile(r'^:::\s*\{([^}]*)\}\s*$')
RE_DIV_CLOSE = re.compile(r'^:::\s*$')
# attribute 파싱: .class 또는 key="value"
RE_DIV_CLASS = re.compile(r'\.([A-Za-z_][\w-]*)')
RE_DIV_ATTR = re.compile(r'([A-Za-z_][\w-]*)\s*=\s*"([^"]*)"')

# 코드 펜스: ``` 또는 ~~~ + (선택) 언어
RE_CODE_FENCE = re.compile(r'^(\s*)(`{3,}|~{3,})\s*([^\s`{]*)')

# Placeholder {{...}}
RE_PLACEHOLDER = re.compile(r'\{\{\s*([A-Za-z_][\w]*)(?:\s+[^}]*)?\s*\}\}')

# 색상 span — Pandoc bracketed_spans: [text]{.class}
# nested 탐지: [text [inner]{.color-X} more]{.color-Y}
# 이를 위해 색상 span 안에 또 다른 색상 span 이 있는지를 검사
RE_COLOR_SPAN = re.compile(
    r'\[([^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*)\]\{\.color-[A-Za-z0-9_-]+\}'
)
RE_INNER_COLOR_SPAN = re.compile(r'\[[^\[\]]+\]\{\.color-[A-Za-z0-9_-]+\}')

# 표 라인: 셀 구분자 | 가 2개 이상 (예: | a | b |)
# 헤더 다음에 separator 행 (|---|---|) 가 있어야 표
RE_TABLE_SEP = re.compile(r'^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$')


# ── 데이터 구조 ────────────────────────────────────────────────────────────

@dataclass
class Finding:
    path: Path
    line: int
    rule: str  # L1 ~ L7
    level: str  # FAIL | WARN
    message: str
    snippet: str = ""


# ── 헬퍼: 코드블록 영역 마스킹 ────────────────────────────────────────────

def _scan_code_fence_regions(lines: list[str]) -> list[tuple[int, int, str]]:
    """코드 펜스로 둘러싸인 영역 [start_idx, end_idx], 언어 fence 반환.

    start_idx / end_idx 는 0-based, 둘 다 포함 (펜스 라인 본인 포함).
    """
    regions: list[tuple[int, int, str]] = []
    i = 0
    n = len(lines)
    while i < n:
        m = RE_CODE_FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        fence = m.group(2)
        lang = m.group(3) or ""
        start = i
        i += 1
        # 같은 종류·같은 길이 이상의 펜스 만날 때까지
        while i < n:
            m2 = re.match(rf'^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$', lines[i])
            if m2:
                break
            i += 1
        end = i if i < n else n - 1
        regions.append((start, end, lang))
        i += 1
    return regions


def _line_in_regions(idx: int, regions: list[tuple[int, int, str]]) -> bool:
    for s, e, _ in regions:
        if s <= idx <= e:
            return True
    return False


# ── 규칙 함수 ──────────────────────────────────────────────────────────────

def check_l1_l2_l3(text: str, path: Path) -> list[Finding]:
    """[L1] fenced div 클래스 허용 목록 / [L2] panel section 필수 /
    [L3] panel style 허용 매핑."""
    findings: list[Finding] = []
    lines = text.splitlines()
    code_regions = _scan_code_fence_regions(lines)

    for idx, raw in enumerate(lines):
        if _line_in_regions(idx, code_regions):
            continue
        m = RE_DIV_OPEN.match(raw)
        if not m:
            continue
        inner = m.group(1)
        classes = RE_DIV_CLASS.findall(inner)
        attrs = dict(RE_DIV_ATTR.findall(inner))
        ln = idx + 1

        # L1: 허용 클래스 검증
        if not classes:
            findings.append(Finding(
                path=path, line=ln, rule="L1", level="FAIL",
                message="fenced div 에 클래스 없음 (`::: {.panel ...}` 형식 필요)",
                snippet=raw.strip(),
            ))
            continue
        first_cls = classes[0]
        if first_cls not in ALLOWED_DIV_CLASSES:
            findings.append(Finding(
                path=path, line=ln, rule="L1", level="FAIL",
                message=f"허용되지 않은 fenced div 클래스: .{first_cls} "
                        f"(허용: {sorted(ALLOWED_DIV_CLASSES)})",
                snippet=raw.strip(),
            ))
            continue

        # L2: panel 은 section 필수
        if first_cls == "panel" and "section" not in attrs:
            findings.append(Finding(
                path=path, line=ln, rule="L2", level="FAIL",
                message="panel 블록에 section=\"...\" 속성 누락",
                snippet=raw.strip(),
            ))

        # L3: panel style 허용 매핑
        if first_cls == "panel" and "style" in attrs:
            sty = attrs["style"]
            if sty not in ALLOWED_PANEL_STYLES:
                findings.append(Finding(
                    path=path, line=ln, rule="L3", level="FAIL",
                    message=f"panel style 값 허용 안 됨: {sty!r} "
                            f"(허용: {sorted(ALLOWED_PANEL_STYLES)})",
                    snippet=raw.strip(),
                ))

    return findings


def check_l4(text: str, path: Path) -> list[Finding]:
    """[L4] 코드블록 언어 fence 가 알려진 언어 (지정된 경우)."""
    findings: list[Finding] = []
    lines = text.splitlines()
    regions = _scan_code_fence_regions(lines)
    for start, _end, lang in regions:
        if not lang:
            continue
        if lang.lower() not in ALLOWED_CODE_LANGS:
            findings.append(Finding(
                path=path, line=start + 1, rule="L4", level="WARN",
                message=f"알 수 없는 코드 언어 fence: {lang!r} "
                        f"(허용 목록에 없음 — 정말 의도된 값인지 확인)",
                snippet=lines[start].strip(),
            ))
    return findings


def check_l5(text: str, path: Path) -> list[Finding]:
    """[L5] 자동 매크로 `{{...}}` 미해결 placeholder."""
    findings: list[Finding] = []
    lines = text.splitlines()
    regions = _scan_code_fence_regions(lines)
    for idx, raw in enumerate(lines):
        if _line_in_regions(idx, regions):
            continue
        for m in RE_PLACEHOLDER.finditer(raw):
            name = m.group(1)
            if name in ALLOWED_PLACEHOLDERS:
                continue
            if any(name.startswith(p) for p in ALLOWED_PLACEHOLDER_PREFIXES):
                continue
            findings.append(Finding(
                path=path, line=idx + 1, rule="L5", level="WARN",
                message=f"미해결 placeholder: {{{{{name}}}}} "
                        f"(허용 목록 외 — 치환 누락 가능성)",
                snippet=raw.strip(),
            ))
    return findings


def check_l6(text: str, path: Path) -> list[Finding]:
    """[L6] 색상 span nested 금지 (Phase 3 예약)."""
    findings: list[Finding] = []
    lines = text.splitlines()
    regions = _scan_code_fence_regions(lines)
    for idx, raw in enumerate(lines):
        if _line_in_regions(idx, regions):
            continue
        for m in RE_COLOR_SPAN.finditer(raw):
            inner_text = m.group(1)
            if RE_INNER_COLOR_SPAN.search(inner_text):
                findings.append(Finding(
                    path=path, line=idx + 1, rule="L6", level="FAIL",
                    message="색상 span 중첩 발견 — nested 금지 (Phase 3 사양)",
                    snippet=raw.strip(),
                ))
                break
    return findings


def check_l7(text: str, path: Path) -> list[Finding]:
    """[L7] 표 컬럼 수 일관성."""
    findings: list[Finding] = []
    lines = text.splitlines()
    regions = _scan_code_fence_regions(lines)
    n = len(lines)
    i = 0
    while i < n - 1:
        if _line_in_regions(i, regions):
            i += 1
            continue
        header = lines[i]
        sep = lines[i + 1]
        if "|" not in header or not RE_TABLE_SEP.match(sep):
            i += 1
            continue
        header_cols = _count_table_cols(header)
        if header_cols < 1:
            i += 1
            continue
        sep_cols = _count_table_cols(sep)
        if sep_cols != header_cols:
            findings.append(Finding(
                path=path, line=i + 2, rule="L7", level="FAIL",
                message=f"표 separator 행 컬럼 수 불일치 — "
                        f"헤더: {header_cols}, separator: {sep_cols}",
                snippet=sep.strip(),
            ))
        # 본문 행 검사
        j = i + 2
        row_num = 0
        while j < n:
            if _line_in_regions(j, regions):
                break
            row = lines[j]
            if "|" not in row or not row.strip():
                break
            row_num += 1
            row_cols = _count_table_cols(row)
            if row_cols != header_cols:
                findings.append(Finding(
                    path=path, line=j + 1, rule="L7", level="FAIL",
                    message=f"표 컬럼 수 불일치 — 헤더: {header_cols} 컬럼, "
                            f"본문 {row_num}번째 행: {row_cols} 컬럼",
                    snippet=row.strip(),
                ))
            j += 1
        i = max(j, i + 1)
    return findings


def _count_table_cols(line: str) -> int:
    """파이프 기준 셀 개수 카운트. 양 끝 파이프는 무시."""
    s = line.strip()
    if not s:
        return 0
    # 양 끝 | 제거
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    if not s:
        return 0
    # escape 처리는 생략 (lint 수준에서는 단순 split 충분)
    return s.count("|") + 1


# ── 파일/제품 단위 ─────────────────────────────────────────────────────────

def lint_file(path: Path) -> list[Finding]:
    """단일 MD 파일 검사. (모든 규칙 실행)"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise OSError(f"read failed: {path} — {e}") from e

    findings: list[Finding] = []
    findings += check_l1_l2_l3(text, path)
    findings += check_l4(text, path)
    findings += check_l5(text, path)
    findings += check_l6(text, path)
    findings += check_l7(text, path)
    # 라인 → 규칙 순으로 정렬
    findings.sort(key=lambda f: (f.line, f.rule))
    return findings


def lint_product(hub_root: Path, product: str) -> dict:
    """제품 단위 lint. 결과: {path: [Finding]} 사전."""
    proj_root = hub_root / "PROJECTS" / product
    if not proj_root.is_dir():
        raise FileNotFoundError(f"제품 디렉터리 없음: {proj_root}")
    md_files: list[Path] = []
    for sub in ("drafts", "reports/render", "reports"):
        d = proj_root / sub
        if d.is_dir():
            md_files += sorted(d.rglob("*.md"))
    results: dict[Path, list[Finding]] = {}
    for mf in md_files:
        results[mf] = lint_file(mf)
    return results


# ── 보고 출력 ──────────────────────────────────────────────────────────────

def format_report(
    results: dict[Path, list[Finding]],
    base_dir: Path | None = None,
) -> str:
    """render_verify.py 패턴의 텍스트 보고 생성."""
    all_findings: list[Finding] = []
    for fs in results.values():
        all_findings += fs

    n_files = len(results)
    n_pass = sum(1 for fs in results.values() if not fs)
    n_fail = sum(1 for f in all_findings if f.level == "FAIL")
    n_warn = sum(1 for f in all_findings if f.level == "WARN")

    lines: list[str] = []
    lines.append("Publication Syntax Lint 결과")
    lines.append("============================")
    lines.append("")
    lines.append(f"검사 파일: {n_files}개")
    lines.append(f"PASS: {n_pass}개 파일")
    lines.append(f"FAIL: {n_fail}개 항목")
    lines.append(f"WARN: {n_warn}개 항목")
    lines.append("")

    if not all_findings:
        lines.append("모든 검증 통과")
        lines.append("")
        return "\n".join(lines)

    # 규칙별 그룹 (FAIL 먼저, 그다음 WARN)
    by_rule: dict[str, list[Finding]] = {}
    for f in all_findings:
        by_rule.setdefault(f.rule, []).append(f)
    order = sorted(
        by_rule.keys(),
        key=lambda r: (0 if RULES[r]["level"] == "FAIL" else 1, r),
    )

    for rule in order:
        meta = RULES[rule]
        lines.append(f"[{meta['level']}] {rule} ({meta['desc']})")
        for f in by_rule[rule]:
            display_path = (
                f.path.relative_to(base_dir) if base_dir and _is_rel(f.path, base_dir)
                else f.path
            )
            lines.append(f"  - {display_path}:{f.line}")
            if f.snippet:
                lines.append(f"    {f.snippet}")
            lines.append(f"    -> {f.message}")
        lines.append("")

    return "\n".join(lines)


def _is_rel(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def format_report_md(
    results: dict[Path, list[Finding]],
    base_dir: Path | None = None,
) -> str:
    """--report 용 markdown 보고."""
    header = [
        "# publication-lint report",
        "",
        f"> 생성: {datetime.now().isoformat(timespec='seconds')}"
        f" · lint_publication_syntax.py 자동 생성 (수정 금지)",
        "",
    ]
    body = format_report(results, base_dir=base_dir)
    # 본문을 코드 블록으로 감싸 정렬 보존
    return "\n".join(header) + "```\n" + body + "\n```\n"


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Publication Syntax Lint (publication-lint)")
    ap.add_argument("--input", type=Path, default=None,
                    help="단일 MD 파일 검사")
    ap.add_argument("--hub-root", type=Path, default=None,
                    help="Planning-Agent-Hub 루트 (--product 와 함께)")
    ap.add_argument("--product", default=None,
                    help="PROJECTS/<product> 한 제품만 검사 (생략 시 전체)")
    ap.add_argument("--report", type=Path, default=None,
                    help="md 보고 저장 경로")
    args = ap.parse_args()

    if not args.input and not args.hub_root:
        sys.stderr.write("[lint] --input 또는 --hub-root 필요\n")
        return 2

    results: dict[Path, list[Finding]] = {}
    base_dir: Path | None = None

    try:
        if args.input:
            if not args.input.is_file():
                sys.stderr.write(f"[lint] 파일 없음: {args.input}\n")
                return 2
            results[args.input] = lint_file(args.input)
        else:
            hub = args.hub_root
            if not hub.is_dir():
                sys.stderr.write(f"[lint] hub-root 없음: {hub}\n")
                return 2
            base_dir = hub
            projects_root = hub / "PROJECTS"
            if not projects_root.is_dir():
                sys.stderr.write(f"[lint] PROJECTS 없음: {projects_root}\n")
                return 2
            if args.product:
                results.update(lint_product(hub, args.product))
            else:
                for proj in sorted(projects_root.iterdir()):
                    if not proj.is_dir():
                        continue
                    try:
                        results.update(lint_product(hub, proj.name))
                    except FileNotFoundError:
                        continue
    except OSError as e:
        sys.stderr.write(f"[lint] I/O 오류: {e}\n")
        return 2

    report = format_report(results, base_dir=base_dir)
    sys.stdout.write(report)
    if not report.endswith("\n"):
        sys.stdout.write("\n")

    if args.report:
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                format_report_md(results, base_dir=base_dir),
                encoding="utf-8",
            )
        except OSError as e:
            sys.stderr.write(f"[lint] report 저장 실패: {e}\n")
            return 2

    n_fail = sum(1 for fs in results.values() for f in fs if f.level == "FAIL")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
