# -*- coding: utf-8 -*-
"""
Lightweight git-based version check for the SessionStart hook.

Behavior:
  - Check the checked_at field in the ~/.claude/orange-pm-update-check.json cache
  - If within TTL (default 24h), decide using the cached new_commits value (no git call)
  - If TTL exceeded, run git fetch + count commits, then refresh the cache
  - Print a one-line notice if new commits exist, otherwise stay silent

All exceptions are silently ignored — so hook errors never disrupt the session.
"""

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    from update_orange_pm import (
        UPDATE_CACHE, find_source_dir, find_git_root,
        count_new_commits, write_cache, get_local_version,
    )
except ImportError:
    sys.exit(0)

TTL_SEC = int(os.environ.get("ORANGE_PM_UPDATE_TTL_HOURS", "24")) * 3600


def _cache_new_commits() -> int | None:
    """Return the cached new_commits value if within TTL, otherwise None."""
    if not UPDATE_CACHE.exists():
        return None
    try:
        with open(UPDATE_CACHE, encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("checked_at", 0) < TTL_SEC:
            return data.get("new_commits", None)
    except Exception:
        pass
    return None


def main() -> None:
    source_dir = find_source_dir()
    if not source_dir or not source_dir.exists():
        return

    # Check the cache TTL
    cached = _cache_new_commits()
    if cached is not None:
        if cached > 0:
            ver = get_local_version(source_dir)
            print(f"[orange-pm] {cached} update(s) pending (current v{ver}) -> /orange-pm:update")
        return

    # TTL exceeded -> check git
    git_root = find_git_root(source_dir)
    if not git_root:
        return

    import subprocess
    subprocess.run(
        ["git", "fetch", "--quiet"], cwd=git_root,
        capture_output=True, timeout=15,
    )
    new_count = count_new_commits(git_root)
    write_cache(new_count)

    if new_count > 0:
        ver = get_local_version(source_dir)
        print(f"[orange-pm] {new_count} update(s) pending (current v{ver}) -> /orange-pm:update")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
