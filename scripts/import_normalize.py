#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""외부 임포트 마크다운 → 표준 임포트 레코드 (멀티테넌트 SaaS Phase 2).

목적:
    Confluence/GitLab/Notion 등에서 페치된 마크다운(소스 무관)을 표준 임포트
    레코드로 적재한다. 본문은 무손실 보존하고 frontmatter 정규화·메타 기록을
    수행한다. 실제 페치·소스별 변환은 상위(skill)가 담당한다:
      - Confluence snapshot(XML) 은 storage_to_md.py 로 MD 변환 후 본 모듈에 입력.
      - GitLab raw .md / Notion 계열 wiki 커넥터 fetch 결과는 MD 네이티브 → 직접 입력.
    → 본 모듈은 **소스 무관(source-agnostic)** — 항상 MD 를 입력으로 받는다.

산출:
    PROJECTS/{product}/inputs/imports/{source}/{id}.md       (정규화 frontmatter + 본문)
    PROJECTS/{product}/inputs/imports/{source}/{id}.meta.json

멱등: 동일 내용 재실행 무변경. 기존 meta.json 은 덮어쓰지 않는다(from-url 패턴) —
content 가 달라졌으면 경고만 출력한다.

사용법:
    python import_normalize.py --hub-root <Hub> --product <p> --source <confluence|gitlab|notion|file> \
        --id <ID> --input <fetched.md> [--source-url URL] [--intent context]

exit code: 0 성공 / 1 입력 없음 / 2 인자 오류
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from frontmatter_detect import detect_frontmatter, normalize

VALID_SOURCES = ("confluence", "gitlab", "notion", "file")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def write_record(
    hub_root: Path,
    product: str,
    source: str,
    doc_id: str,
    md_text: str,
    *,
    source_url: str = "",
    intent: str = "context",
) -> dict:
    """임포트 레코드(md + meta.json)를 기록하고 결과 dict 반환."""
    out_dir = hub_root / "PROJECTS" / product / "inputs" / "imports" / source
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{doc_id}.md"
    meta_path = out_dir / f"{doc_id}.meta.json"

    imported_at = datetime.now().isoformat(timespec="seconds")
    # 멱등성: 기존 레코드가 있으면 그 imported_at 을 재사용해 재실행이 바이트 동일하도록.
    if md_path.exists():
        prev_fm, _, _ = detect_frontmatter(md_path.read_text(encoding="utf-8", errors="replace"))
        if prev_fm.get("imported_at"):
            imported_at = prev_fm["imported_at"]
    normalized, report = normalize(
        md_text, source=source, source_url=source_url, doc_id=doc_id,
        imported_at=imported_at,
    )
    content_sha = _sha(normalized)

    status = "written"
    if md_path.exists() and _sha(md_path.read_text(encoding="utf-8", errors="replace")) == content_sha:
        status = "unchanged"
    md_path.write_text(normalized, encoding="utf-8")

    if meta_path.exists():
        # 기존 메타 보존 — content 변동만 알림.
        existing = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
        if existing.get("content_sha") != content_sha:
            existing["content_sha"] = content_sha
            existing["last_seen"] = imported_at
            existing["note"] = "content changed since first import"
            meta_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
            status = "meta-updated"
        meta = existing
    else:
        meta = {
            "id": doc_id,
            "source": source,
            "source_url": source_url,
            "intent": intent,
            "imported_at": imported_at,
            "content_sha": content_sha,
            "original_metadata": report["fields"]["original_metadata"],
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": status,
        "md_path": str(md_path.relative_to(hub_root).as_posix()),
        "meta_path": str(meta_path.relative_to(hub_root).as_posix()),
        "report": report,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="외부 임포트 MD → 표준 레코드")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", required=True)
    ap.add_argument("--source", required=True, choices=VALID_SOURCES)
    ap.add_argument("--id", required=True, dest="doc_id")
    ap.add_argument("--input", required=True, type=Path, help="페치된 MD 파일")
    ap.add_argument("--source-url", default="")
    ap.add_argument("--intent", default="context", choices=("context", "target", "template"))
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    if not args.input.is_file():
        sys.stderr.write(f"input not found: {args.input}\n")
        return 1
    result = write_record(
        args.hub_root, args.product, args.source, args.doc_id,
        args.input.read_text(encoding="utf-8", errors="replace"),
        source_url=args.source_url, intent=args.intent,
    )
    print(f"[import_normalize] {result['status']}: {result['md_path']}")
    if result["report"]["inferred"]:
        print(f"  추론: {', '.join(result['report']['inferred'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
