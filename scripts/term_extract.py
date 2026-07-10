#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""임포트 문서 용어 추출 + 글로서리 대조 → 후보 큐 (멀티테넌트 SaaS Phase 2).

목적:
    폐쇄형 glossary(terms.yml 사전 등재 필수) 를 "후보 큐 + PM 승인" 으로 완화한다.
    임포트 문서에서 용어를 추출(build_a_index.extract_terms 재사용)하고 기존
    glossary 와 대조하여 신규/충돌(동일어 상이 정의) 로 분류한 뒤,
    CONTEXT/glossary/term-candidates.yml 스테이징에 등재한다.
    terms.yml(정본) 은 직접 수정하지 않는다 — PM 승인 후 별도 반영.

사용법:
    python term_extract.py --hub-root <Hub> --input X.md [--write-candidates]

exit code: 0 성공 / 1 입력 없음 / 2 인자 오류
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from build_a_index import extract_terms

# terms.yml / aliases.yml 의 canonical_name·aliases 단순 추출(파서 비의존).
_CANON = re.compile(r"-\s*canonical_name\s*:\s*(.+?)\s*$", re.MULTILINE)
_ALIASES = re.compile(r"aliases\s*:\s*\[(.*?)\]", re.MULTILINE)
_DEF = re.compile(r"definition\s*:\s*(.+?)\s*$", re.MULTILINE)


def _load_glossary(hub_root: Path) -> dict[str, str]:
    """canonical_name → definition(없으면 '') 맵. aliases 도 키로 펼친다."""
    out: dict[str, str] = {}
    terms_path = hub_root / "CONTEXT" / "glossary" / "terms.yml"
    if not terms_path.exists():
        return out
    text = terms_path.read_text(encoding="utf-8", errors="replace")
    # 블록 단위로 canonical + definition 매칭(근사) — 라인 순서 기반.
    canon = None
    for line in text.splitlines():
        cm = _CANON.match(line.strip()) if line.strip().startswith("- canonical_name") else None
        if cm:
            canon = cm.group(1).strip().strip("'\"")
            out.setdefault(canon, "")
            continue
        dm = re.match(r"definition\s*:\s*(.+)$", line.strip())
        if dm and canon:
            out[canon] = dm.group(1).strip().strip("'\"")
            canon = None
    # aliases 도 동일 정의를 가리키도록 키 추가
    aliases_path = hub_root / "CONTEXT" / "glossary" / "aliases.yml"
    if aliases_path.exists():
        atext = aliases_path.read_text(encoding="utf-8", errors="replace")
        raw = canon2 = None
        for line in atext.splitlines():
            s = line.strip()
            rm = re.match(r'-\s*raw\s*:\s*"?(.+?)"?\s*$', s)
            cm = re.match(r'canonical_name\s*:\s*"?(.+?)"?\s*$', s)
            if rm:
                raw = rm.group(1)
            elif cm:
                canon2 = cm.group(1)
                if raw:
                    out.setdefault(raw, out.get(canon2, ""))
                    raw = None
    return out


def diff_terms(extracted: dict[str, dict], glossary: dict[str, str]) -> dict:
    """추출 용어를 glossary 와 대조 → {new, conflict, known}."""
    new: list[dict] = []
    conflict: list[dict] = []
    known: list[str] = []
    for term, meta in extracted.items():
        if term not in glossary:
            new.append({"term": term, "definition": meta["def"],
                        "file": meta["file"], "line": meta["line"]})
        else:
            existing = glossary[term]
            cand = meta["def"]
            # 정의가 비어있지 않고 서로 다르면 충돌 후보.
            if existing and cand and existing.strip() != cand.strip():
                conflict.append({"term": term, "existing": existing, "candidate": cand,
                                 "file": meta["file"], "line": meta["line"]})
            else:
                known.append(term)
    return {"new": new, "conflict": conflict, "known": known}


def _render_candidates_yaml(diff: dict, source: str) -> str:
    today = date.today().isoformat()
    lines = [
        "# term-candidates.yml — 자동 추출 용어 후보 (PM 승인 전 스테이징)",
        "# term_extract.py 자동 생성. 승인 후 terms.yml 로 수동 반영.",
        f"# 최종 갱신: {today} · source: {source or '(미상)'}",
        "",
        "candidates:",
    ]
    for item in diff["new"]:
        lines += [
            f"  - term: {item['term']}",
            f"    definition: {item['definition']}",
            f"    source: {source}",
            f"    location: \"{item['file']}:{item['line']}\"",
            "    status: pending",
        ]
    if diff["conflict"]:
        lines += ["", "conflicts:"]
        for item in diff["conflict"]:
            lines += [
                f"  - term: {item['term']}",
                f"    existing: {item['existing']}",
                f"    candidate: {item['candidate']}",
                f"    location: \"{item['file']}:{item['line']}\"",
                "    status: needs-review",
            ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="용어 추출 + glossary 대조 → 후보 큐")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--source", default="")
    ap.add_argument("--write-candidates", action="store_true",
                    help="CONTEXT/glossary/term-candidates.yml 에 기록")
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    if not args.input.is_file():
        sys.stderr.write(f"input not found: {args.input}\n")
        return 1

    extracted = extract_terms(args.input.read_text(encoding="utf-8", errors="replace"),
                              str(args.input.name))
    glossary = _load_glossary(args.hub_root)
    diff = diff_terms(extracted, glossary)

    if args.write_candidates:
        out = args.hub_root / "CONTEXT" / "glossary" / "term-candidates.yml"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_render_candidates_yaml(diff, args.source), encoding="utf-8")
        # 미지 용어 로그에도 누적(기존 자산 활용)
        log = args.hub_root / "CONTEXT" / "glossary" / "unknown_terms.log"
        if diff["new"]:
            with log.open("a", encoding="utf-8") as fh:
                for item in diff["new"]:
                    fh.write(f"{date.today().isoformat()}\t{item['term']}\t{args.source}\n")
        print(f"[term_extract] wrote {out} "
              f"(new={len(diff['new'])}, conflict={len(diff['conflict'])})")
    else:
        print(f"[term_extract] {args.input.name}: "
              f"new={len(diff['new'])} conflict={len(diff['conflict'])} known={len(diff['known'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
