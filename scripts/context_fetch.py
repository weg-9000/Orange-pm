#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tier 2 컨텍스트 섹션/용어 페치 — L2 (멀티테넌트 SaaS Phase 3).

목적:
    Neo4j 없이, 캐시 인덱스만으로 정확한 섹션/용어를 최소 토큰으로 추출한다.
    - B 섹션: {PREFIX}-b-headings-index.json 으로 doc·섹션 라인 범위 → 본문 슬라이스
    - A 용어: {PREFIX}-a-terms-index.json 으로 용어 정의·위치
    - 키워드: B 헤딩 제목 + A 용어를 키워드로 검색(L2 디스커버리)

    데이터 비종속 — 어느 테넌트(PREFIX)의 인덱스든 동일하게 동작한다.
    인덱스가 없으면 PM 에게 캐시 생성(build_b_index/build_a_index)을 안내한다.

사용법:
    python context_fetch.py --hub-root <Hub> [--prefix G2] --layer B --doc G2-B-001 --section "프로젝트 생성"
    python context_fetch.py --hub-root <Hub> --layer A --term 인스턴스
    python context_fetch.py --hub-root <Hub> --query "자원 한도" [--top 5]

exit code: 0 성공 / 1 미해소(인덱스/대상 없음) / 2 인자 오류
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _cache_utils import read_active_prefix


def _cache_dir(hub_root: Path) -> Path:
    return hub_root / "CONTEXT" / ".template-cache"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_b_index(hub_root: Path, prefix: str) -> dict:
    cd = _cache_dir(hub_root)
    for name in (f"{prefix}-b-headings-index.json", "B-headings-index.json"):
        data = _load_json(cd / name)
        if data:
            return data.get("documents", {})
    return {}


def load_a_terms(hub_root: Path, prefix: str) -> dict:
    return _load_json(_cache_dir(hub_root) / f"{prefix}-a-terms-index.json").get("terms", {})


def load_alias_map(hub_root: Path) -> dict:
    """master-id-map.yml: 핀 ID(G2-B-003) → 파일 stem 매핑(단순 key:value 파싱)."""
    p = hub_root / "CONTEXT" / "reference-docs" / "master-id-map.yml"
    amap: dict = {}
    if not p.exists():
        return amap
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        amap[k.strip()] = v.strip().strip("'\"")
    return amap


def _norm(x: str) -> str:
    return re.sub(r"[\s.\-]+", "", str(x)).lower()


def fetch_section(hub_root: Path, prefix: str, doc: str, section: str | None) -> tuple[str, str]:
    """(텍스트, 라벨). doc 미해소면 ('', 'UNRESOLVED'). 섹션 없으면 문서 상단."""
    docs = load_b_index(hub_root, prefix)
    entry = docs.get(doc)
    if entry is None:
        # 1) 핀 ID(G2-B-003) → master-id-map 으로 stem 해소 후 매칭
        stem = load_alias_map(hub_root).get(doc, "")
        for k, e in docs.items():
            if stem and (k == stem or e.get("doc_id") == stem or Path(e.get("path", "")).stem == stem):
                entry = e
                break
    if entry is None:
        # 2) doc_id 정확 일치 / 부분 일치 폴백
        for k, e in docs.items():
            if e.get("doc_id") == doc or _norm(doc) in _norm(k):
                entry = e
                break
    if entry is None:
        return "", "UNRESOLVED"
    fp = hub_root / entry["path"]
    if not fp.exists():
        return "", f"MISSING:{entry['path']}"
    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
    if not section:
        seg = lines[:120]
        return "\n".join(seg).strip(), f"{doc} 상단"
    secs = entry.get("sections", [])
    for s in secs:
        if s["id"] == section:
            return "\n".join(lines[s["line_start"] - 1: s["line_end"]]).strip(), f"§{section} {s.get('title','')}".strip()
    nsec = _norm(section)
    for s in secs:
        if nsec and nsec in _norm(s.get("title", "")):
            return "\n".join(lines[s["line_start"] - 1: s["line_end"]]).strip(), f"§{s['id']} {s.get('title','')}".strip()
    return "", f"§{section} 미발견"


def fetch_term(hub_root: Path, prefix: str, term: str) -> dict | None:
    terms = load_a_terms(hub_root, prefix)
    if term in terms:
        return {"term": term, **terms[term]}
    nt = _norm(term)
    for k, v in terms.items():
        if nt and nt in _norm(k):
            return {"term": k, **v}
    return None


def search_keyword(hub_root: Path, prefix: str, query: str, top: int = 5) -> list[dict]:
    """B 헤딩 제목 + A 용어에서 키워드 포함 항목 랭킹(간이 L2 디스커버리)."""
    nq = _norm(query)
    hits: list[dict] = []
    for doc, e in load_b_index(hub_root, prefix).items():
        for s in e.get("sections", []):
            if nq and nq in _norm(s.get("title", "")):
                hits.append({"kind": "B", "doc": e.get("doc_id", doc),
                             "section": s["id"], "title": s.get("title", "")})
    for term, v in load_a_terms(hub_root, prefix).items():
        if nq and (nq in _norm(term) or nq in _norm(v.get("def", ""))):
            hits.append({"kind": "A", "term": term, "def": v.get("def", "")})
    return hits[:top]


def main() -> int:
    ap = argparse.ArgumentParser(description="L2 컨텍스트 섹션/용어 페치")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--layer", choices=["A", "B", "C"], default=None)
    ap.add_argument("--doc", default=None)
    ap.add_argument("--section", default=None)
    ap.add_argument("--term", default=None)
    ap.add_argument("--query", default=None)
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    prefix = args.prefix or read_active_prefix(args.hub_root)

    if args.query:
        hits = search_keyword(args.hub_root, prefix, args.query, args.top)
        if not hits:
            print(f"[context_fetch] '{args.query}' 매치 없음 (캐시 생성 여부 확인)")
            return 1
        print(json.dumps(hits, ensure_ascii=False, indent=2))
        return 0
    if args.layer == "A" or args.term:
        r = fetch_term(args.hub_root, prefix, args.term or args.doc or "")
        if not r:
            print(f"[context_fetch] 용어 미해소: {args.term or args.doc}")
            return 1
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    if args.doc:
        text, label = fetch_section(args.hub_root, prefix, args.doc, args.section)
        if not text:
            print(f"[context_fetch] {label}")
            return 1
        print(f"# {label}\n\n{text}")
        return 0
    sys.stderr.write("--doc/--term/--query 중 하나가 필요합니다\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
