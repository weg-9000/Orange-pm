#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fact preservation check — LLM 어투 변환의 안전망.

publication 파이프라인에서 LLM 이 어투·스타일을 변환할 때, 정책 사실
(숫자·상태명·오류코드·표 셀·UI 문구) 이 누락·변경되지 않았는지 결정적으로 검증한다.

검증 방식:
    - "before" 텍스트 (prefilter 직후) 와 "after" 텍스트 (LLM 변환 후) 에서
      각각 fact 집합을 추출
    - before ⊆ after 가 깨지면 FAIL (어떤 fact 가 누락됨)
    - 단순 string 매칭이 아니라 정규화 후 비교 (whitespace·구두점 차이는 허용)

추출 대상 fact 종류:
    1. 숫자 + 단위:  "30일", "100GB", "5회", "1,000원", "85%", "v1.0"
    2. 표 셀 값: | A | B | C | 의 비공백 셀
    3. 코드 블록 본문 (```...```) — UI 문구·API 응답 등
    4. 따옴표 둘러쌓인 문구: "에러 메시지", '버튼 라벨'
    5. 등재 어휘: glossary/terms.yml 에 있는 canonical 표제
    6. [[POL §X-Y]] 마커 (정책 §참조)
    7. [[WO-NN]] 마커

각 fact 는 (kind, normalized_value) 튜플로 식별.
before 의 모든 fact 가 after 에 있어야 PASS.

exit code:
    0 = PASS (모든 fact 보존)
    1 = FAIL (누락된 fact 발견)
    2 = 사용법 오류 또는 파일 미존재
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ── fact 추출 정규식 ────────────────────────────────────────────────────────

# 숫자 + 단위 (한글·영문 단위 + 통화·퍼센트·시간·바이트)
NUMBER_UNIT_RE = re.compile(
    r"(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
    r"(?:%|원|일|시간|분|초|회|건|개|명|GB|MB|KB|TB|byte|bytes|"
    r"days?|hours?|times?|items?|v?\d+\.\d+(?:\.\d+)?)?"
)

# 표 행 — | 로 시작하고 끝나며 셀이 여러 개
TABLE_ROW_RE = re.compile(r"^\|.+\|$", re.MULTILINE)
TABLE_SEPARATOR_RE = re.compile(r"^\|[\s\-:|]+\|$")

# 코드 블록 (펜스)
CODE_BLOCK_RE = re.compile(r"```[a-zA-Z]*\n(.*?)\n```", re.DOTALL)

# 인라인 코드
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")

# 따옴표 둘러싼 문구 (한글 따옴표 포함)
QUOTED_RE = re.compile(r'["“”]([^"“”\n]{2,100})["“”]')

# [[POL §X-Y]] / [[WO-NN]] / [[doc_id §X]] 마커
WIKI_LINK_RE = re.compile(r"\[\[[^\[\]\n]{2,80}\]\]")

# 정책 등재 ID 패턴 ({PREFIX}-A/B/C-XXX 형식)
DOC_ID_RE = re.compile(r"\b[A-Z]{1,4}\d?-[ABC]-(?:[A-Z][A-Z0-9]*-)?\d{3}\b")


def _norm(s: str) -> str:
    """공백·구두점 정규화 — fact 비교용."""
    # 모든 공백을 단일 스페이스로
    s = re.sub(r"\s+", " ", s).strip()
    # 양 끝 마침표·쉼표 제거
    s = s.strip(".,;:!?")
    return s


def _extract_table_cells(text: str) -> set[str]:
    """표 본문 셀 추출 (header 구분선 제외, 빈 셀 제외)."""
    cells: set[str] = set()
    for line in TABLE_ROW_RE.findall(text):
        if TABLE_SEPARATOR_RE.match(line):
            continue
        for cell in line.strip().strip("|").split("|"):
            v = _norm(cell)
            if v:
                cells.add(v)
    return cells


def _extract_facts(text: str, glossary_terms: set[str] | None = None) -> dict[str, set[str]]:
    """텍스트에서 fact 집합 추출 (kind 별로 분리).

    glossary_terms: terms.yml 에서 추출한 canonical 표제 집합 (선택).
    """
    facts: dict[str, set[str]] = {
        "number_unit": set(),
        "table_cell": set(),
        "code_block": set(),
        "inline_code": set(),
        "quoted": set(),
        "wiki_link": set(),
        "doc_id": set(),
        "glossary": set(),
    }

    facts["number_unit"] = {_norm(m) for m in NUMBER_UNIT_RE.findall(text) if any(c.isdigit() for c in m)}
    facts["table_cell"] = _extract_table_cells(text)
    facts["code_block"] = {_norm(b) for b in CODE_BLOCK_RE.findall(text) if _norm(b)}
    facts["inline_code"] = {_norm(c) for c in INLINE_CODE_RE.findall(text) if _norm(c)}
    facts["quoted"] = {_norm(q) for q in QUOTED_RE.findall(text) if _norm(q)}
    facts["wiki_link"] = {_norm(w) for w in WIKI_LINK_RE.findall(text)}
    facts["doc_id"] = {_norm(d) for d in DOC_ID_RE.findall(text)}

    if glossary_terms:
        present = {t for t in glossary_terms if t and t in text}
        facts["glossary"] = present

    return facts


def _load_glossary_terms(hub_root: Path) -> set[str]:
    """CONTEXT/glossary/terms.yml 에서 canonical 표제 추출.

    yaml 의존 없이 단순 라인 파서 — "  - id: foo\n    canonical: '바'" 같은
    구조에서 canonical 값만 수집.

    HIGH #6: substring false-match 방지를 위해 다음 표제는 제외:
    - 1자 (한글·영문 모두) — 다른 어휘 부분 매칭 위험
    - YAML 구조 마커(`>`, `|`, `*`, `&`) 로 시작 — multi-line scalar 마커가
      canonical 로 잘못 추출된 케이스
    """
    terms_path = hub_root / "CONTEXT" / "glossary" / "terms.yml"
    if not terms_path.is_file():
        return set()
    terms: set[str] = set()
    try:
        for line in terms_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("canonical:"):
                v = s.split(":", 1)[1].strip().strip("'\"")
                if not v:
                    continue
                if len(v) <= 1:
                    continue
                if v[0] in (">", "|", "*", "&"):
                    continue
                terms.add(v)
    except Exception:
        pass
    return terms


def check_preservation(
    before_text: str,
    after_text: str,
    glossary_terms: set[str] | None = None,
) -> dict:
    """before fact 가 after 에 모두 보존되는지 검사.

    반환: {
        "pass": bool,
        "missing_by_kind": { kind: [missing_values] },
        "total_before": int,
        "total_missing": int,
    }
    """
    before = _extract_facts(before_text, glossary_terms)
    after = _extract_facts(after_text, glossary_terms)

    missing_by_kind: dict[str, list[str]] = {}
    total_before = 0
    total_missing = 0
    for kind, before_set in before.items():
        total_before += len(before_set)
        after_set = after[kind]
        missing = sorted(before_set - after_set)
        if missing:
            missing_by_kind[kind] = missing
            total_missing += len(missing)

    return {
        "pass": total_missing == 0,
        "missing_by_kind": missing_by_kind,
        "total_before": total_before,
        "total_missing": total_missing,
    }


def _format_report(result: dict, before_path: Path, after_path: Path) -> str:
    lines = [
        "# Fact Preservation Check Report",
        "",
        f"before: `{before_path}`",
        f"after:  `{after_path}`",
        "",
        f"전체 fact 수: {result['total_before']}",
        f"누락 fact 수: {result['total_missing']}",
        f"판정: {'✅ PASS' if result['pass'] else '❌ FAIL'}",
        "",
    ]
    if result["missing_by_kind"]:
        lines.append("## 누락 fact 목록 (LLM 변환에서 손실됨)")
        lines.append("")
        for kind, missing in result["missing_by_kind"].items():
            lines.append(f"### {kind} ({len(missing)}건)")
            lines.append("")
            for v in missing[:50]:
                lines.append(f"- `{v}`")
            if len(missing) > 50:
                lines.append(f"- _… 외 {len(missing) - 50}건_")
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fact preservation check — LLM publication 변환의 안전망"
    )
    ap.add_argument("--before", required=True, type=Path,
                    help="LLM 변환 전 텍스트 (prefilter 직후)")
    ap.add_argument("--after", required=True, type=Path,
                    help="LLM 변환 후 텍스트 (publication 결과)")
    ap.add_argument("--hub-root", type=Path, default=None,
                    help="glossary/terms.yml 로드용 (선택)")
    ap.add_argument("--report", type=Path, default=None,
                    help="결과를 마크다운 보고서로 저장 (생략 시 stdout)")
    ap.add_argument("--json", action="store_true",
                    help="결과를 JSON 으로 출력")
    args = ap.parse_args()

    if not args.before.is_file():
        print(f"[fact-check] FAIL: before 파일 없음 — {args.before}", file=sys.stderr)
        return 2
    if not args.after.is_file():
        print(f"[fact-check] FAIL: after 파일 없음 — {args.after}", file=sys.stderr)
        return 2

    glossary = _load_glossary_terms(args.hub_root) if args.hub_root else set()

    before_text = args.before.read_text(encoding="utf-8")
    after_text = args.after.read_text(encoding="utf-8")

    result = check_preservation(before_text, after_text, glossary)

    if args.json:
        out = json.dumps(result, ensure_ascii=False, indent=2)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(out, encoding="utf-8")
        else:
            sys.stdout.write(out + "\n")
    else:
        report = _format_report(result, args.before, args.after)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(report, encoding="utf-8")
            print(
                f"[fact-check] {'PASS' if result['pass'] else 'FAIL'} "
                f"— missing {result['total_missing']}/{result['total_before']} → {args.report}",
                file=sys.stderr,
            )
        else:
            sys.stdout.write(report)

    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
