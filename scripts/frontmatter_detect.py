#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""임의 마크다운 frontmatter 자동 감지·정규화 (멀티테넌트 SaaS Phase 2).

목적:
    외부(Confluence/GitLab/Notion)에서 임포트한 임의 마크다운은 frontmatter 가
    없거나 비표준일 수 있다. 본 모듈은 frontmatter 유무를 감지하고, 임포트
    문서용 *reference* 스키마로 정규화한다(본문은 무수정 — 메타만 부착).

    draft 9필드(migrate_draft_frontmatter)와 달리, 임포트 문서는 다음 스키마:
        doc_id, title, layer(A|B|C|unknown), version, status, source, source_url,
        imported_at, original_metadata

    status: ingested(수집) → normalized(메타정규화) → analyzed(분류완료)

사용법:
    python frontmatter_detect.py --input X.md [--source confluence] [--source-url URL]
        [--doc-id ID] [--in-place] [--report]

exit code:
    0 = 성공
    1 = 입력 파일 없음
    2 = 인자 오류
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)

REFERENCE_FIELDS = [
    "doc_id",
    "title",
    "layer",
    "version",
    "status",
    "source",
    "source_url",
    "imported_at",
    "original_metadata",
]

# 다포맷 메타 추출(drift_scan 패턴과 동형): YAML / bold inline / table.
_DOC_ID_BOLD = re.compile(
    r"\*\*\s*(?:문서\s*ID|doc_id)\s*[:：]?\s*\*\*\s*[:：]?\s*`?([A-Za-z0-9._-]+)`?", re.I
)
_DOC_ID_TABLE = re.compile(r"\|\s*\*\*\s*doc_id\s*\*\*\s*\|\s*`?([A-Za-z0-9._-]+)`?", re.I)
_VER_BOLD = re.compile(
    r"\*\*\s*(?:버전|version)\s*[:：]?\s*\*\*\s*[:：]?\s*`?([0-9]+(?:\.[0-9]+)*)`?", re.I
)
_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def detect_frontmatter(text: str) -> tuple[dict, str, bool]:
    """(frontmatter dict, body, had_frontmatter) 반환. 없으면 ({}, text, False)."""
    m = FRONTMATTER.match(text)
    if not m:
        return {}, text, False
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, text[m.end():], True


def _extract_meta_from_body(head: str) -> dict:
    """frontmatter 가 없을 때 본문 상단에서 doc_id/version/title 휴리스틱 추출."""
    out: dict = {}
    dm = _DOC_ID_BOLD.search(head) or _DOC_ID_TABLE.search(head)
    if dm:
        out["doc_id"] = dm.group(1).strip()
    vm = _VER_BOLD.search(head)
    if vm:
        out["version"] = vm.group(1).strip()
    tm = _H1.search(head)
    if tm:
        out["title"] = tm.group(1).strip()
    return out


def normalize(
    text: str,
    *,
    source: str = "",
    source_url: str = "",
    doc_id: str = "",
    layer: str = "unknown",
    imported_at: str = "",
) -> tuple[str, dict]:
    """임포트 MD 를 reference frontmatter 로 정규화한다. 본문은 무수정.

    반환: (정규화된 전체 텍스트, 추론 리포트 dict).
    """
    fm, body, had_fm = detect_frontmatter(text)
    body_meta = _extract_meta_from_body(body[:4000])

    inferred: list[str] = []
    out: dict = {}

    def pick(*cands: str) -> str:
        for c in cands:
            if c:
                return c
        return ""

    out["doc_id"] = pick(doc_id, fm.get("doc_id", ""), body_meta.get("doc_id", ""))
    if not out["doc_id"]:
        inferred.append("doc_id(미상 — 플레이스홀더)")
        out["doc_id"] = "UNCLASSIFIED"
    out["title"] = pick(fm.get("title", ""), body_meta.get("title", ""), out["doc_id"])
    out["layer"] = pick(layer if layer != "unknown" else "", fm.get("layer", ""), "unknown")
    out["version"] = pick(fm.get("version", ""), body_meta.get("version", ""))
    if not out["version"]:
        inferred.append("version(미상)")
        out["version"] = "0.0.0"
    out["status"] = "normalized"
    out["source"] = pick(source, fm.get("source", ""))
    out["source_url"] = pick(source_url, fm.get("source_url", ""))
    out["imported_at"] = pick(imported_at, fm.get("imported_at", ""), date.today().isoformat())

    # 원본 frontmatter 의 비표준 필드는 손실 없이 original_metadata 로 보존.
    extra = {k: v for k, v in fm.items() if k not in REFERENCE_FIELDS}
    out["original_metadata"] = json.dumps(extra, ensure_ascii=False) if extra else "{}"

    lines = ["---"]
    for f in REFERENCE_FIELDS:
        lines.append(f"{f}: {out[f]}")
    lines.append("---")
    normalized = "\n".join(lines) + "\n" + body.lstrip("\n")

    report = {
        "had_frontmatter": had_fm,
        "inferred": inferred,
        "fields": out,
    }
    return normalized, report


def main() -> int:
    ap = argparse.ArgumentParser(description="임의 MD frontmatter 감지·정규화")
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--source", default="")
    ap.add_argument("--source-url", default="")
    ap.add_argument("--doc-id", default="")
    ap.add_argument("--layer", default="unknown")
    ap.add_argument("--in-place", action="store_true", help="입력 파일을 정규화 결과로 덮어쓴다")
    ap.add_argument("--report", action="store_true", help="추론 리포트를 JSON 으로 출력")
    args = ap.parse_args()
    if not args.input.is_file():
        sys.stderr.write(f"input not found: {args.input}\n")
        return 1
    text = args.input.read_text(encoding="utf-8", errors="replace")
    normalized, report = normalize(
        text, source=args.source, source_url=args.source_url,
        doc_id=args.doc_id, layer=args.layer,
    )
    if args.in_place:
        args.input.write_text(normalized, encoding="utf-8")
        print(f"[frontmatter_detect] normalized in place: {args.input}")
    else:
        sys.stdout.write(normalized)
    if args.report:
        sys.stderr.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
