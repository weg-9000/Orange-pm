#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""{PREFIX}-B 헤딩 인덱스 생성 (개선안 B — CONTEXT_OPTIMIZATION.md).

목적:
    /write, /flow 가 graph.json 의 inherits_from / includes 에 명시된 섹션만
    선택적으로 발췌 로드할 수 있도록 헤딩 위치 인덱스를 생성한다.

    출력: CONTEXT/.template-cache/B-headings-index.json

    스키마:
      {
        "G2-B-001": {
          "title": "...",
          "path": "CONTEXT/reference-docs/B/G2-B_xxx.md",
          "sections": [
            {"id": "1",   "title": "개요",        "line_start": 5,   "line_end": 38},
            {"id": "3.2", "title": "리소스 한도", "line_start": 142, "line_end": 197}
          ]
        }
      }

    section.id 는 본문에서 "## 1. 개요" / "## 3.2 리소스 한도 계산" 식으로 표기된
    선두 번호를 추출한다. 번호 없는 헤딩은 슬러그(공백 → -)로 대체한다.

    line 번호는 1-based, line_end 는 다음 같은 깊이 또는 더 얕은 헤딩 직전 라인.
    파일 끝까지 이어지면 마지막 라인 번호.

사용법:
    python build_b_index.py --hub-root <Planning-Agent-Hub 경로>

exit code:
    0 = 성공
    1 = PREFIX 추출 실패 또는 reference-docs/B 없음
    2 = 인자 오류
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from _cache_utils import (
    HEADING_PATTERN,
    discover_b_sources,
    ensure_cache_dir,
    make_hub_root_parser,
    read_prefix,
    validate_hub_root,
)

LEADING_NUMBER_PATTERN = re.compile(r"^(?:§\s*)?(\d+(?:\.\d+)*)[\s.\)]\s*(.*)$")
# doc_id 우선순위:
#   1) frontmatter 또는 본문 상단의 명시적 식별자 (예: "doc_id: G2-B-001")
#   2) 파일명 stem 이 G2-B-001 형식이면 그대로 사용
#   3) fallback: 파일 stem 그대로 (PREFIX 중복 추가 안 함)
EXPLICIT_DOC_ID_PATTERN = re.compile(r"(?:^|\n)\s*doc_id\s*[:：]\s*([A-Za-z0-9_-]+)\s*(?:\n|$)")
CANONICAL_DOC_ID_PATTERN = re.compile(r"^([A-Za-z0-9]+)-B-(\d{3,})$")


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[\s/]+", "-", text.strip())
    slug = re.sub(r"[^0-9A-Za-z\-가-힣]", "", slug)
    return slug[:max_len] or "section"


def split_section_id(heading_text: str, fallback_idx: int) -> tuple[str, str]:
    match = LEADING_NUMBER_PATTERN.match(heading_text.strip())
    if match:
        return match.group(1), match.group(2).strip() or heading_text.strip()
    return f"_{fallback_idx}-{slugify(heading_text)}", heading_text.strip()


def derive_doc_id(prefix: str, file_path: Path, body_text: str) -> str:
    """파일에서 doc_id 추출. 식별자가 없는 경우 파일 stem 을 그대로 사용한다.

    인덱스 키는 단순 식별자다. graph.json 의 inherits_from(예: G2-B-001) 과의
    매핑은 별도로 layer-config.md 또는 reference-docs/B/README.md 가 담당한다.
    """
    explicit = EXPLICIT_DOC_ID_PATTERN.search(body_text[:1024])
    if explicit:
        return explicit.group(1)
    if CANONICAL_DOC_ID_PATTERN.match(file_path.stem):
        return file_path.stem
    return file_path.stem


def index_one(file_path: Path, prefix: str) -> dict:
    body = file_path.read_text(encoding="utf-8")
    lines = body.splitlines()
    headings: list[tuple[int, int, str]] = []  # (line_idx_0based, depth, raw_title)
    for idx, line in enumerate(lines):
        match = HEADING_PATTERN.match(line)
        if not match:
            continue
        depth = len(match.group(1))
        if depth < 2:
            continue  # H1 (문서 제목)은 스킵, 섹션 단위는 ## 이상
        headings.append((idx, depth, match.group(2)))

    sections: list[dict] = []
    title = ""
    for h_idx, (line_idx, depth, raw_title) in enumerate(headings):
        sec_id, sec_title = split_section_id(raw_title, fallback_idx=h_idx)
        end_line_0 = len(lines) - 1
        for next_idx, next_depth, _ in headings[h_idx + 1 :]:
            if next_depth <= depth:
                end_line_0 = next_idx - 1
                break
        sections.append(
            {
                "id": sec_id,
                "title": sec_title,
                "depth": depth,
                "line_start": line_idx + 1,
                "line_end": end_line_0 + 1,
            }
        )
        if h_idx == 0 and depth == 2:
            title = sec_title
    if not title:
        # H1 fallback
        for line in lines[:5]:
            m = HEADING_PATTERN.match(line)
            if m and len(m.group(1)) == 1:
                title = m.group(2).strip()
                break

    doc_id = derive_doc_id(prefix, file_path, body)
    return {
        "doc_id": doc_id,
        "title": title or file_path.stem,
        "path": str(file_path.as_posix()),
        "lines_total": len(lines),
        "sections": sections,
    }


def build(hub_root: Path) -> int:
    prefix = read_prefix(hub_root)
    sources = discover_b_sources(hub_root)
    cache_dir = ensure_cache_dir(hub_root)
    # PREFIX 네임스페이스(주) + 레거시 무네임스페이스(부, 활성 PREFIX 한정).
    out_path = cache_dir / f"{prefix}-b-headings-index.json"
    legacy_path = cache_dir / "B-headings-index.json"

    index: dict[str, dict] = {}
    source_dir = ""
    for src in sources:
        rel_src = src.relative_to(hub_root)
        entry = index_one(src, prefix)
        # path 를 hub-root 상대 경로로 정규화
        entry["path"] = str(rel_src.as_posix())
        index[entry["doc_id"]] = entry
        source_dir = str(rel_src.parent.as_posix())

    payload = {
        "_meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "prefix": prefix,
            "source_dir": (source_dir + "/") if source_dir else "CONTEXT/reference-docs/B/",
            "doc_count": len(index),
        },
        "documents": index,
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    out_path.write_text(serialized, encoding="utf-8")
    # 레거시 호환: 활성 PREFIX 인덱스를 무네임스페이스 파일로도 미러링(render_assemble 등).
    legacy_path.write_text(serialized, encoding="utf-8")
    print(f"[build_b_index] wrote {out_path} (+legacy {legacy_path.name}, docs={len(index)})")
    return 0


def main() -> int:
    parser = make_hub_root_parser("Build {PREFIX}-B headings index")
    args = parser.parse_args()
    rc = validate_hub_root(args.hub_root)
    if rc:
        return rc
    return build(args.hub_root)


if __name__ == "__main__":
    sys.exit(main())
