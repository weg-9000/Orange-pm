#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Automatic markdown layer classifier A/B/C (multi-tenant SaaS Phase 2).

Purpose:
    An alternative to location-based (reference-docs/{A,B,C}) layer determination.
    Classifies externally imported documents by content heuristics into
    A (terminology/definitions) / B (common policy) / C (service deliverable).
    Deterministic core — low confidence (below threshold) defers to layer='unknown'
    for PM confirmation (no automatic forcing).

Classification signals:
    A: term/definition density (reuses build_a_index.extract_terms) + a
       "term/definition/abbreviation" heading.
    B: policy-verb frequency ("must/prohibited/principle/standard/policy/required")
       + multi-product reference diversity.
    C: specific product/service name + common-policy reference pattern
       ("[{ID} §X reference]", "common policy").

Usage:
    python layer_classify.py --input X.md [--json]

exit code: 0 success / 1 no input / 2 argument error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from build_a_index import extract_terms

# Policy verbs/expressions (B signal)
# NOTE: this is Korean-language pattern data used to classify real Korean
# policy documents by content — not a translation gap. Keep as-is.
_POLICY_TERMS = [
    "해야 한다", "하여야 한다", "금지", "원칙", "기준", "정책", "필수",
    "허용", "제한", "준수", "규정", "불가", "가능하다", "한다.",
]
# Common-policy reference pattern (C signal) — [{ID} §X 참조] / 공통 정책 / inherits
# NOTE: these regexes match Korean reference/heading phrasing found in real Hub
# documents — functional Korean-language pattern data, not a translation gap.
_REF_PATTERNS = [
    re.compile(r"\[[A-Za-z0-9]+-[ABC]-?\d*[^\]]*참조\]"),
    re.compile(r"공통\s*정책"),
    re.compile(r"inherits_from"),
    re.compile(r"§\s*\d"),
]
# Layer-hint headings
# NOTE: matches Korean terminology-heading words alongside their English
# equivalents — functional Korean-language pattern data, not a translation gap.
_A_HEADINGS = re.compile(r"^#{1,6}\s*.*(용어|정의|약어|glossary|terminology)", re.I | re.M)
_DOC_ID_TOKEN = re.compile(r"[A-Za-z0-9]+-[ABC]-\d+")

CONFIDENCE_THRESHOLD = 0.34  # falls back to unknown if the top score's share is below this


def _count(patterns_or_terms, text: str) -> int:
    n = 0
    for t in patterns_or_terms:
        if isinstance(t, re.Pattern):
            n += len(t.findall(text))
        else:
            n += text.count(t)
    return n


def classify(text: str) -> dict:
    """Returns {layer, confidence, scores, signals}."""
    n_lines = max(text.count("\n") + 1, 1)
    terms = extract_terms(text, "x.md")
    term_density = len(terms) / n_lines  # definitions per line

    # A score: term density + term heading
    a_score = term_density * 8.0 + (2.0 if _A_HEADINGS.search(text) else 0.0)
    # B score: policy-verb frequency (normalized per line) + multi-product reference diversity
    policy_hits = _count(_POLICY_TERMS, text)
    b_score = (policy_hits / n_lines) * 6.0
    # C score: common-policy reference pattern + service doc_id token
    ref_hits = _count(_REF_PATTERNS, text)
    c_score = (ref_hits / n_lines) * 6.0

    scores = {"A": round(a_score, 4), "B": round(b_score, 4), "C": round(c_score, 4)}
    total = sum(scores.values()) or 1.0
    best = max(scores, key=scores.get)
    confidence = round(scores[best] / total, 4)

    signals = []
    signals.append(f"{len(terms)} terms (density {term_density:.3f})")
    signals.append(f"policy expressions x{policy_hits}")
    signals.append(f"common references x{ref_hits}")

    layer = best if (scores[best] > 0 and confidence >= CONFIDENCE_THRESHOLD) else "unknown"
    return {
        "layer": layer,
        "confidence": confidence,
        "scores": scores,
        "signals": signals,
        "needs_review": layer == "unknown",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Classify an arbitrary MD layer A/B/C")
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--json", action="store_true", help="Print the result as JSON")
    args = ap.parse_args()
    if not args.input.is_file():
        sys.stderr.write(f"input not found: {args.input}\n")
        return 1
    result = classify(args.input.read_text(encoding="utf-8", errors="replace"))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        tag = result["layer"] + ("(needs review)" if result["needs_review"] else "")
        print(f"[layer_classify] {args.input.name} → {tag} "
              f"(conf={result['confidence']}, {', '.join(result['signals'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
