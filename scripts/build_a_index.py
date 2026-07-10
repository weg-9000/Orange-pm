#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""{PREFIX}-A 용어 역인덱스 생성 (멀티-PREFIX SaaS Phase 1).

목적:
    A 계층(용어·원칙 기준서)에서 "용어 → {파일, 라인, 짧은 정의}" 역인덱스를
    생성해, 화면/정책 작성 시 용어 검증과 정확 참조(L2)에 사용한다.
    build_b_index.py(B 헤딩 인덱스)의 A 계층 대응물이다.

    출력: CONTEXT/.template-cache/{PREFIX}-a-terms-index.json

추출 휴리스틱(결정적):
    1) 마크다운 표 행:  `| 용어 | 정의 ... |`  (헤더/구분선 제외)
    2) 정의 라인:       `- **용어**: 정의` / `**용어** — 정의` / `**용어**: 정의`
    정의는 최대 80자로 절단. 동일 용어 중복 시 첫 등장 우선.

사용법:
    python build_a_index.py --hub-root <Planning-Agent-Hub 경로>

exit code:
    0 = 성공 (A 문서 0개여도 빈 인덱스로 성공)
    1 = PREFIX 추출 실패
    2 = 인자 오류
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from _cache_utils import (
    discover_layer_sources,
    ensure_cache_dir,
    make_hub_root_parser,
    read_active_prefix,
    validate_hub_root,
)

# `| 용어 | 정의 |` 표 행 — 셀이 2개 이상이고 구분선(---)이 아닌 경우.
TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
# `- **용어**: 정의` / `**용어** — 정의` / `**용어**: 정의`
BOLD_DEF = re.compile(r"^\s*[-*]?\s*\*\*\s*(?P<term>[^*]+?)\s*\*\*\s*[:：—\-]\s*(?P<def>.+?)\s*$")

_HEADER_HINTS = ("용어", "term", "정의", "definition", "설명")


def _truncate(text: str, limit: int = 80) -> str:
    text = re.sub(r"\s+", " ", text).strip().strip("`")
    return text[:limit]


def _is_separator_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in cells if c.strip())


def extract_terms(md_text: str, file_rel: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    lines = md_text.splitlines()
    in_table_body = False
    table_is_glossary = False
    for idx, line in enumerate(lines, start=1):
        tm = TABLE_ROW.match(line)
        if tm:
            cells = [c.strip() for c in tm.group(1).split("|")]
            if _is_separator_row(cells):
                in_table_body = True
                continue
            # 헤더 행 감지 — 용어/정의 류 헤더면 본문을 용어표로 취급.
            if not in_table_body:
                joined = " ".join(cells).lower()
                table_is_glossary = any(h in joined for h in _HEADER_HINTS)
                continue
            if in_table_body and table_is_glossary and len(cells) >= 2:
                term = _truncate(cells[0], 60)
                definition = _truncate(cells[1])
                if term and term not in out:
                    out[term] = {"file": file_rel, "line": idx, "def": definition}
            continue
        else:
            in_table_body = False
            table_is_glossary = False

        bm = BOLD_DEF.match(line)
        if bm:
            term = _truncate(bm.group("term"), 60)
            definition = _truncate(bm.group("def"))
            if term and term not in out:
                out[term] = {"file": file_rel, "line": idx, "def": definition}
    return out


def build(hub_root: Path) -> int:
    prefix = read_active_prefix(hub_root)
    sources = discover_layer_sources(hub_root, prefix, "A")
    cache_dir = ensure_cache_dir(hub_root)
    out_path = cache_dir / f"{prefix}-a-terms-index.json"

    terms: dict[str, dict] = {}
    for src in sources:
        rel = str(src.relative_to(hub_root).as_posix())
        for term, meta in extract_terms(src.read_text(encoding="utf-8", errors="replace"), rel).items():
            terms.setdefault(term, meta)

    payload = {
        "_meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "prefix": prefix,
            "source_count": len(sources),
            "term_count": len(terms),
        },
        "terms": terms,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[build_a_index] wrote {out_path} (terms={len(terms)}, sources={len(sources)})")
    return 0


def main() -> int:
    parser = make_hub_root_parser("Build {PREFIX}-A terms reverse index")
    args = parser.parse_args()
    rc = validate_hub_root(args.hub_root)
    if rc:
        return rc
    return build(args.hub_root)


if __name__ == "__main__":
    sys.exit(main())
