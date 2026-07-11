#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bulk-insert the guard block into SKILL.md files (Improvement F — CONTEXT_OPTIMIZATION.md, one-off).

Inserts the 'Bootstrap Cache Guard' block right after the frontmatter (`---...---`).
init-hub is excluded because it is the skill that generates the guard itself.
SKILL.md files that already contain GUARD_MARKER in their body are skipped (idempotent).

Usage:
    python _apply_bootstrap_guard.py --plugin-root <orange-pm-plugin>
    python _apply_bootstrap_guard.py --plugin-root <orange-pm-plugin> --check
        (--check: report unapplied files only, no changes made)

This script may be deleted after it has been run.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

GUARD_MARKER = "## Bootstrap Cache Guard (Improvement F"

GUARD_BLOCK = """\

## Bootstrap Cache Guard (Improvement F — CONTEXT_OPTIMIZATION.md)

On first entry into a session, load `CONTEXT/_session-bootstrap.md` only once.
If this file has already been read in the same session, do not re-read it.
If the cache is missing or stale, refresh it with the following command before proceeding:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```

This guard replaces reloading the 6 source files layer-config / about-pm / project-rules /
brand-voice / doc-layer-schema / team-members.
Reading the source files directly is allowed only when essential to this skill's core work.

"""

EXCLUDE = {"init-hub"}  # the skill that generates the guard itself


def insert_guard(text: str) -> str:
    """Insert GUARD_BLOCK right after the frontmatter."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return GUARD_BLOCK + text
    if not lines[0].startswith("---"):
        # SKILL.md with no frontmatter — insert at the very top of the file
        return GUARD_BLOCK + text
    # find the closing '---'
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
