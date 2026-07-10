#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""완결 서비스 → C 계층 아카이브 (멀티테넌트 SaaS Phase 3).

목적:
    발행 완료된 제품(서비스)의 산출물을 해당 테넌트(PREFIX)의 C 계층
    `reference-docs/{PREFIX}/C/{service}/` 로 적재한다. C 는 읽기 전용 아카이브이며,
    이후 build_c_index.py 가 마스터 인덱스에, embed_pipeline 이 벡터에 반영한다.

    데이터 비종속(tenant-agnostic): 특정 제품을 전제하지 않고 임의 PROJECTS 산출물을
    적재한다. 완결 산출물(reports/render/*.complete.md)이 있으면 그것을, 없으면
    drafts/*.draft.md 를 적재한다.

멱등:
    - 기존 metadata.json 이 있고 doc 목록이 같으면 archived_at 보존.
    - 내용 동일 파일은 다시 써도 동일(바이트 보존).

사용법:
    python archive_to_context.py --hub-root <Hub> --prefix G2 --product dbaas [--service dbaas] [--force]

exit code: 0 성공 / 1 소스 없음 / 2 인자 오류
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def _resolve_source(hub_root: Path, prefix: str, product: str) -> Path | None:
    """PROJECTS/{prefix}/{product} 우선, 없으면 PROJECTS/{product} 폴백."""
    for cand in (hub_root / "PROJECTS" / prefix / product, hub_root / "PROJECTS" / product):
        if cand.is_dir():
            return cand
    return None


def _collect_docs(source: Path) -> list[Path]:
    """완결판(reports/render/*.complete.md) 우선, 없으면 drafts/*.draft.md."""
    rendered = source / "reports" / "render"
    if rendered.is_dir():
        docs = sorted(p for p in rendered.glob("*.complete.md"))
        if docs:
            return docs
    drafts = source / "drafts"
    if drafts.is_dir():
        return sorted(drafts.glob("*.draft.md"))
    return []


def archive(hub_root: Path, prefix: str, product: str,
            service: str | None = None, *, force: bool = False) -> dict:
    service = service or product
    source = _resolve_source(hub_root, prefix, product)
    if source is None:
        return {"status": "no-source", "service": service}
    docs = _collect_docs(source)
    if not docs:
        return {"status": "no-docs", "service": service, "source": str(source)}

    dest = hub_root / "CONTEXT" / "reference-docs" / prefix / "C" / service
    dest.mkdir(parents=True, exist_ok=True)

    copied, unchanged = [], []
    for d in docs:
        target = dest / d.name
        if target.exists() and not force and _sha(target) == _sha(d):
            unchanged.append(d.name)
            continue
        shutil.copyfile(d, target)
        copied.append(d.name)

    # metadata.json — archived_at 멱등 보존
    meta_path = dest / "metadata.json"
    doc_stems = [d.stem for d in docs]
    archived_at = date.today().isoformat()
    if meta_path.exists():
        try:
            prev = json.loads(meta_path.read_text(encoding="utf-8"))
            if prev.get("docs") == doc_stems and prev.get("archived_at"):
                archived_at = prev["archived_at"]  # 변경 없으면 최초 시각 보존
        except Exception:
            pass
    meta = {
        "service": service,
        "prefix": prefix,
        "source_product": product,
        "docs": doc_stems,
        "doc_files": [d.name for d in docs],
        "status": "archived",
        "archived_at": archived_at,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "archived",
        "service": service,
        "prefix": prefix,
        "dest": str(dest.relative_to(hub_root).as_posix()),
        "copied": copied,
        "unchanged": unchanged,
        "doc_count": len(docs),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="완결 서비스 → C 계층 아카이브")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--product", required=True)
    ap.add_argument("--service", default=None, help="C/{service} 이름(기본=product)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    r = archive(args.hub_root, args.prefix, args.product, args.service, force=args.force)
    if r["status"] in ("no-source", "no-docs"):
        sys.stderr.write(f"[archive_to_context] {r['status']} — service={r['service']}\n")
        return 1
    print(f"[archive_to_context] {r['dest']}: copied={r['copied']} "
          f"unchanged={r['unchanged']} ({r['doc_count']} docs)")
    print("  다음: build_c_index.py 로 c-master-index 갱신")
    return 0


if __name__ == "__main__":
    sys.exit(main())
