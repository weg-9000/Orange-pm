#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""임의 마크다운 계층 자동 분류 A/B/C (멀티테넌트 SaaS Phase 2).

목적:
    위치(reference-docs/{A,B,C}) 기반 계층 결정의 대안. 외부 임포트 문서를
    내용 휴리스틱으로 A(용어·정의) / B(공통 정책) / C(서비스 산출물) 로 분류한다.
    결정적 코어 — 저신뢰(임계 미만)는 layer='unknown' 으로 PM 확인에 위임한다
    (자동 강제 금지).

분류 신호:
    A: 용어/정의 밀도 (build_a_index.extract_terms 재사용) + "용어/정의/약어" 헤딩.
    B: 정책 동사("해야 한다/금지/원칙/기준/정책/필수") 빈도 + 다(多)제품 참조.
    C: 특정 제품/서비스명 + 공통정책 참조 패턴("[{ID} §X 참조]", "공통 정책").

사용법:
    python layer_classify.py --input X.md [--json]

exit code: 0 성공 / 1 입력 없음 / 2 인자 오류
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from build_a_index import extract_terms

# 정책 동사·표현 (B 신호)
_POLICY_TERMS = [
    "해야 한다", "하여야 한다", "금지", "원칙", "기준", "정책", "필수",
    "허용", "제한", "준수", "규정", "불가", "가능하다", "한다.",
]
# 공통정책 참조 패턴 (C 신호) — [{ID} §X 참조] / 공통 정책 / 상속
_REF_PATTERNS = [
    re.compile(r"\[[A-Za-z0-9]+-[ABC]-?\d*[^\]]*참조\]"),
    re.compile(r"공통\s*정책"),
    re.compile(r"inherits_from"),
    re.compile(r"§\s*\d"),
]
# 계층 힌트 헤딩
_A_HEADINGS = re.compile(r"^#{1,6}\s*.*(용어|정의|약어|glossary|terminology)", re.I | re.M)
_DOC_ID_TOKEN = re.compile(r"[A-Za-z0-9]+-[ABC]-\d+")

CONFIDENCE_THRESHOLD = 0.34  # 최고 점수 비중이 이 미만이면 unknown


def _count(patterns_or_terms, text: str) -> int:
    n = 0
    for t in patterns_or_terms:
        if isinstance(t, re.Pattern):
            n += len(t.findall(text))
        else:
            n += text.count(t)
    return n


def classify(text: str) -> dict:
    """{layer, confidence, scores, signals} 반환."""
    n_lines = max(text.count("\n") + 1, 1)
    terms = extract_terms(text, "x.md")
    term_density = len(terms) / n_lines  # 줄당 정의 수

    # A 점수: 용어 밀도 + 용어 헤딩
    a_score = term_density * 8.0 + (2.0 if _A_HEADINGS.search(text) else 0.0)
    # B 점수: 정책 동사 빈도 (줄당 정규화) + 다제품 참조 다양성
    policy_hits = _count(_POLICY_TERMS, text)
    b_score = (policy_hits / n_lines) * 6.0
    # C 점수: 공통정책 참조 패턴 + 서비스 doc_id 토큰
    ref_hits = _count(_REF_PATTERNS, text)
    c_score = (ref_hits / n_lines) * 6.0

    scores = {"A": round(a_score, 4), "B": round(b_score, 4), "C": round(c_score, 4)}
    total = sum(scores.values()) or 1.0
    best = max(scores, key=scores.get)
    confidence = round(scores[best] / total, 4)

    signals = []
    signals.append(f"용어 {len(terms)}개(밀도 {term_density:.3f})")
    signals.append(f"정책표현 {policy_hits}회")
    signals.append(f"공통참조 {ref_hits}회")

    layer = best if (scores[best] > 0 and confidence >= CONFIDENCE_THRESHOLD) else "unknown"
    return {
        "layer": layer,
        "confidence": confidence,
        "scores": scores,
        "signals": signals,
        "needs_review": layer == "unknown",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="임의 MD 계층 분류 A/B/C")
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--json", action="store_true", help="결과를 JSON 으로 출력")
    args = ap.parse_args()
    if not args.input.is_file():
        sys.stderr.write(f"input not found: {args.input}\n")
        return 1
    result = classify(args.input.read_text(encoding="utf-8", errors="replace"))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        tag = result["layer"] + ("(검토 필요)" if result["needs_review"] else "")
        print(f"[layer_classify] {args.input.name} → {tag} "
              f"(conf={result['confidence']}, {', '.join(result['signals'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
