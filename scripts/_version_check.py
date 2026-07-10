# -*- coding: utf-8 -*-
"""
SessionStart 훅 전용 경량 버전 체크 (git 기반).

동작:
  - ~/.claude/orange-pm-update-check.json 캐시의 checked_at 확인
  - TTL(기본 24h) 이내면 캐시된 new_commits 값으로 판단 (git 미호출)
  - TTL 초과 시 git fetch + 커밋 수 체크 후 캐시 갱신
  - 새 커밋 있으면 1줄 알림 출력, 없으면 무음

모든 예외는 조용히 무시한다 — 훅 오류가 세션을 방해하지 않도록.
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
    """TTL 이내면 캐시된 new_commits 반환, 아니면 None."""
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

    # 캐시 TTL 확인
    cached = _cache_new_commits()
    if cached is not None:
        if cached > 0:
            ver = get_local_version(source_dir)
            print(f"[orange-pm] {cached}개 업데이트 대기 중 (현재 v{ver}) → /orange-pm:update")
        return

    # TTL 초과 → git 확인
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
        print(f"[orange-pm] {new_count}개 업데이트 대기 중 (현재 v{ver}) → /orange-pm:update")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
