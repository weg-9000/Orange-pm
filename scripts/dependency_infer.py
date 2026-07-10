#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""문서 간 의존성 추론 → 후보 엣지 (멀티테넌트 SaaS Phase 2).

목적:
    명시적 inherits_from/includes 엣지 강제를 완화한다. 임포트 문서 본문에서
    다른 문서 참조 신호를 탐지해 graph-schema.json 호환 후보 엣지를 추론한다.
    PM 이 검토·확정하기 전까지는 후보(confidence)일 뿐이다.

신호 → 엣지 타입:
    "[{ID} §X 참조]" / "{ID} 를 전제" → inherits_from  (high — 명시 ID)
    "공통 정책 ... 포함/include"        → includes      (medium)
    본문 doc_id 토큰 단순 언급          → references    (low)

재사용:
    - drift_scan PIN/master-id-map 해소 패턴(여기서는 경량 자체 구현)
    - templates/graph-schema.json 엣지 스키마(source/target/type/description)

사용법:
    python dependency_infer.py --hub-root <Hub> --input X.md --doc-id SELF [--json]

exit code: 0 성공 / 1 입력 없음 / 2 인자 오류
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# doc_id 토큰: {PREFIX}-{A|B|C}-{seq}
DOC_ID = re.compile(r"\b([A-Za-z0-9]+-[ABC]-\d+)\b")
# 명시 참조: [ID ... 참조] / [ID §X]
REF_BRACKET = re.compile(r"\[([A-Za-z0-9]+-[ABC]-\d+)[^\]]*\]")
# 전제/상속 표현
INHERIT_HINT = re.compile(r"전제|상속|inherits_from|기반으로|따른다")
INCLUDE_HINT = re.compile(r"포함|include|재사용|공통\s*모듈")


def _load_alias_map(hub_root: Path) -> dict:
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


def infer_edges(text: str, self_doc_id: str, amap: dict | None = None) -> list[dict]:
    """본문에서 후보 엣지 목록을 추론한다. self 참조 제거 + target 당 최강 엣지만 유지."""
    amap = amap or {}
    edges: dict[str, dict] = {}  # target → 최강 엣지
    conf_rank = {"low": 0, "medium": 1, "high": 2}
    type_rank = {"references": 0, "includes": 1, "inherits_from": 2}

    def add(target: str, etype: str, conf: str, desc: str) -> None:
        if not target or target == self_doc_id:
            return
        cur = edges.get(target)
        if cur is not None:
            # 더 강한 신뢰도 → 그 다음 더 강한 타입 우선.
            if (conf_rank[conf], type_rank[etype]) <= (
                conf_rank[cur["confidence"]], type_rank[cur["type"]]
            ):
                return
        edges[target] = {
            "source": self_doc_id,
            "target": target,
            "type": etype,
            "confidence": conf,
            "resolved_stem": amap.get(target, ""),
            "description": desc,
        }

    for ln in text.splitlines():
        for m in REF_BRACKET.finditer(ln):
            tid = m.group(1)
            if INHERIT_HINT.search(ln):
                add(tid, "inherits_from", "high", "명시 참조 + 전제/상속 표현")
            elif INCLUDE_HINT.search(ln):
                add(tid, "includes", "high", "명시 참조 + 포함/재사용 표현")
            else:
                add(tid, "references", "high", "대괄호 명시 참조")
    # 본문 일반 언급(대괄호 밖) → references(low)
    for m in DOC_ID.finditer(text):
        add(m.group(1), "references", "low", "본문 doc_id 언급")

    return list(edges.values())


def main() -> int:
    ap = argparse.ArgumentParser(description="문서 간 의존성 추론 → 후보 엣지")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--doc-id", required=True, help="입력 문서 자신의 doc_id")
    ap.add_argument("--out", type=Path, default=None, help="후보 엣지 JSON 저장 경로")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    if not args.input.is_file():
        sys.stderr.write(f"input not found: {args.input}\n")
        return 1
    amap = _load_alias_map(args.hub_root)
    edges = infer_edges(args.input.read_text(encoding="utf-8", errors="replace"),
                        args.doc_id, amap)
    payload = {"doc_id": args.doc_id, "edge_count": len(edges), "edges": edges}
    if args.out:
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[dependency_infer] wrote {args.out} (edges={len(edges)})")
    elif args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[dependency_infer] {args.input.name}: {len(edges)} 후보 엣지")
        for e in edges:
            print(f"  {e['source']} --{e['type']}({e['confidence']})--> {e['target']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
