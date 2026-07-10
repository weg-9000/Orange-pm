#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Session Bootstrap 통합본 생성 (개선안 F — CONTEXT_OPTIMIZATION.md).

목적:
    Hub/.claude/CLAUDE.md 가 세션 시작 시 6개 파일을 순차 로드하도록 강제하던
    구조를, 단일 통합 파일 _session-bootstrap.md 한 번 읽기로 대체한다.
    모든 skill SKILL.md 는 본 파일을 1회만 읽고 이후 재독하지 않는다.

    출력: CONTEXT/_session-bootstrap.md
    포함 원본 파일 (변경 시 자동 재생성):
      - layer-config.md
      - about-pm.md
      - project-rules.md
      - brand-voice.md
      - doc-layer-schema.md
      - team-members.md

    캐시 무효화:
      위 6 파일 중 어떤 것이든 mtime 이 _session-bootstrap.md 보다 새로우면
      재생성한다. 누락된 파일은 자리 표시자 블록만 출력하고 진행한다.

사용법:
    python build_bootstrap.py --hub-root <Planning-Agent-Hub 경로>

exit code:
    0 = 성공
    2 = 인자 오류
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from _cache_utils import (
    cache_is_fresh,
    make_hub_root_parser,
    validate_hub_root,
)

SOURCES = [
    "layer-config.md",
    "about-pm.md",
    "project-rules.md",
    "brand-voice.md",
    "doc-layer-schema.md",
    "team-members.md",
]


def build(hub_root: Path) -> int:
    context_dir = hub_root / "CONTEXT"
    if not context_dir.is_dir():
        sys.stderr.write(f"CONTEXT/ not found: {context_dir}\n")
        return 1

    sources = [context_dir / name for name in SOURCES]
    out_path = context_dir / "_session-bootstrap.md"

    if cache_is_fresh(out_path, sources, allow_missing_sources=True):
        print(f"[build_bootstrap] up-to-date: {out_path}")
        return 0

    parts: list[str] = [
        "# Session Bootstrap (자동 생성, 직접 수정 금지)",
        "",
        "> 본 파일은 build_bootstrap.py 가 자동 생성한다.",
        f"> 생성 시각: {datetime.now().isoformat(timespec='seconds')}",
        "> 변경하려면 원본 CONTEXT/*.md 를 수정한 뒤 build_bootstrap.py 를 다시 실행한다.",
        "",
        "## 사용 규칙",
        "- 각 skill SKILL.md 는 세션 1회만 본 파일을 읽고 이후 재독하지 않는다.",
        "- 본 파일이 보장하는 컨텍스트: PREFIX, PM 프로필, 기획 원칙, 톤 기준,",
        "  문서 스키마, 이해관계자 명단.",
        "- 추가 컨텍스트가 필요한 skill 은 자체 전제조건 단계에서 별도 로드한다.",
        "",
    ]

    found = 0
    missing: list[str] = []
    for src in sources:
        parts.append(f"---\n\n## SOURCE — {src.name}")
        parts.append("")
        if not src.exists():
            parts.append(f"> ⚠️ `{src.name}` 미존재. /init-hub 실행 후 다시 build_bootstrap.py 호출 권장.")
            parts.append("")
            missing.append(src.name)
            continue
        parts.append(src.read_text(encoding="utf-8").rstrip())
        parts.append("")
        found += 1

    out_path.write_text("\n".join(parts), encoding="utf-8")
    msg = f"[build_bootstrap] wrote {out_path} (sources={found}/{len(sources)}"
    if missing:
        msg += f", missing={','.join(missing)}"
    msg += ")"
    print(msg)
    return 0


def main() -> int:
    parser = make_hub_root_parser("Build _session-bootstrap.md")
    args = parser.parse_args()
    rc = validate_hub_root(args.hub_root)
    if rc:
        return rc
    return build(args.hub_root)


if __name__ == "__main__":
    sys.exit(main())
