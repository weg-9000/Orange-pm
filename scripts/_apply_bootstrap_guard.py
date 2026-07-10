#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SKILL.md 일괄 가드 블록 삽입 (개선안 F — CONTEXT_OPTIMIZATION.md, 일회성).

frontmatter (`---...---`) 직후에 'Bootstrap 캐시 가드' 블록을 삽입한다.
init-hub 은 가드 자체를 생성하는 skill 이므로 제외한다.
이미 GUARD_MARKER 가 본문에 있는 SKILL.md 는 skip (멱등).

사용법:
    python _apply_bootstrap_guard.py --plugin-root <orange-pm-plugin>
    python _apply_bootstrap_guard.py --plugin-root <orange-pm-plugin> --check
        (--check: 미적용 파일만 보고하고 변경 없음)

실행 후 본 스크립트는 삭제 가능.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

GUARD_MARKER = "## Bootstrap 캐시 가드 (개선안 F"

GUARD_BLOCK = """\

## Bootstrap 캐시 가드 (개선안 F — CONTEXT_OPTIMIZATION.md)

세션 첫 진입 시 `CONTEXT/_session-bootstrap.md` 를 1회만 로드한다.
이미 같은 세션에서 본 파일을 읽었다면 재독을 금지한다.
캐시가 없거나 stale 이면 다음 명령으로 갱신한 뒤 진행한다:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```

본 가드는 layer-config / about-pm / project-rules / brand-voice /
doc-layer-schema / team-members 6개 원본 파일 재로드를 대체한다.
원본 파일 직접 Read 는 본 skill 의 핵심 작업에 필수인 경우에만 허용된다.

"""

EXCLUDE = {"init-hub"}  # 가드를 생성하는 skill 자체


def insert_guard(text: str) -> str:
    """frontmatter 직후에 GUARD_BLOCK 삽입."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return GUARD_BLOCK + text
    if not lines[0].startswith("---"):
        # frontmatter 없는 SKILL.md — 파일 최상단에 삽입
        return GUARD_BLOCK + text
    # 닫는 '---' 찾기
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].startswith("---"):
            end_idx = idx
            break
    if end_idx is None:
        return GUARD_BLOCK + text
    head = "".join(lines[: end_idx + 1])
    tail = "".join(lines[end_idx + 1 :])
    return head + GUARD_BLOCK + tail


def process(plugin_root: Path, check_only: bool) -> int:
    skills_dir = plugin_root / "skills"
    if not skills_dir.is_dir():
        sys.stderr.write(f"skills/ not found: {skills_dir}\n")
        return 2

    targets = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name in EXCLUDE:
            continue
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            targets.append(skill_md)

    pending: list[str] = []
    applied = 0
    for skill_md in targets:
        text = skill_md.read_text(encoding="utf-8")
        if GUARD_MARKER in text:
            continue
        if check_only:
            pending.append(skill_md.relative_to(plugin_root).as_posix())
            continue
        new_text = insert_guard(text)
        skill_md.write_text(new_text, encoding="utf-8")
        applied += 1
        print(f"[guard] {skill_md.relative_to(plugin_root).as_posix()}")

    if check_only:
        if pending:
            sys.stderr.write("[check] guard missing in:\n")
            for line in pending:
                sys.stderr.write(f"  - {line}\n")
            return 1
        print(f"[check] all {len(targets)} skills have guard")
        return 0

    print(f"[apply_bootstrap_guard] applied to {applied}/{len(targets)} skills (excluded: {sorted(EXCLUDE)})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin-root", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    return process(args.plugin_root, args.check)


if __name__ == "__main__":
    sys.exit(main())
