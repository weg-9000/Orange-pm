# -*- coding: utf-8 -*-
"""
orange-pm 플러그인 업데이터 (git pull 기반)

동작:
  1. ~/.claude/plugins/known_marketplaces.json 에서 orange-pm 소스 경로 탐지
  2. 해당 디렉토리의 git root 에서 git pull 실행
  3. installed_plugins.json 의 orange-pm install path 에 파일 동기화
  4. 변경 커밋 수 보고

사용법:
  python update_orange_pm.py              # 업데이트
  python update_orange_pm.py --check      # 새 커밋 수 확인만 (설치 안 함), 있으면 exit 2
  python update_orange_pm.py --quiet      # 신규 커밋 없으면 무음 (훅 내부용)
  python update_orange_pm.py --version    # 현재 설치 버전 출력

별도 인증 토큰 불필요 — 로컬 git 자격증명 사용
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ── 경로 상수 ──────────────────────────────────────────────────────────────────

CLAUDE_DIR        = Path.home() / ".claude"
KNOWN_MARKETS     = CLAUDE_DIR / "plugins" / "known_marketplaces.json"
INSTALLED_JSON    = CLAUDE_DIR / "plugins" / "installed_plugins.json"
UPDATE_CACHE      = CLAUDE_DIR / "orange-pm-update-check.json"
PLUGIN_NAME       = "orange-pm"

# git pull 시 제외 패턴
_EXCLUDE = shutil.ignore_patterns("*.pyc", "__pycache__", "*_test.py", ".git", ".gitignore")


# ── 경로 탐색 ─────────────────────────────────────────────────────────────────

def find_source_dir() -> Path | None:
    """known_marketplaces.json 에서 orange-pm 소스 디렉토리 반환."""
    if not KNOWN_MARKETS.exists():
        return None
    with open(KNOWN_MARKETS, encoding="utf-8") as f:
        data = json.load(f)
    entry = data.get(PLUGIN_NAME)
    if not entry:
        return None
    path_str = (entry.get("source") or {}).get("path") or entry.get("installLocation")
    return Path(path_str) if path_str else None


def find_git_root(path: Path) -> Path | None:
    """path 또는 부모 디렉토리에서 .git 을 찾아 git root 반환."""
    current = path.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def find_install_paths() -> list[Path]:
    """installed_plugins.json 에서 orange-pm 의 모든 installPath 반환."""
    if not INSTALLED_JSON.exists():
        return []
    with open(INSTALLED_JSON, encoding="utf-8") as f:
        data = json.load(f)
    paths = []
    for key, entries in data.get("plugins", {}).items():
        if not key.startswith(PLUGIN_NAME):
            continue
        for entry in (entries or []):
            p = entry.get("installPath")
            if p and Path(p).exists():
                paths.append(Path(p))
    return paths


# ── git 작업 ──────────────────────────────────────────────────────────────────

def _git(args: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd,
        capture_output=True, text=True, encoding="utf-8",
        timeout=timeout,
    )


def count_new_commits(git_root: Path) -> int:
    """origin/main 에 있고 HEAD 에 없는 커밋 수. 오류 시 -1."""
    # 기본 브랜치 자동 감지 (main / master)
    for branch in ("main", "master"):
        r = _git(["rev-list", f"HEAD..origin/{branch}", "--count"], git_root, timeout=5)
        if r.returncode == 0:
            try:
                return int(r.stdout.strip())
            except ValueError:
                pass
    return -1


def git_pull(git_root: Path) -> tuple[bool, str]:
    """git pull 실행. (성공 여부, 출력 메시지) 반환."""
    r = _git(["pull", "--ff-only"], git_root)
    ok = r.returncode == 0
    msg = (r.stdout + r.stderr).strip()
    return ok, msg


# ── 파일 동기화 ───────────────────────────────────────────────────────────────

def sync_to_install_paths(source_dir: Path) -> list[Path]:
    """source_dir 내용을 모든 install path 에 복사. 동기화된 경로 목록 반환."""
    paths = find_install_paths()
    synced = []
    for dst in paths:
        # source_dir 와 dst 가 같으면 스킵
        if dst.resolve() == source_dir.resolve():
            continue
        shutil.copytree(
            str(source_dir), str(dst),
            ignore=_EXCLUDE,
            dirs_exist_ok=True,
        )
        synced.append(dst)
    return synced


# ── Claude Code 플러그인 갱신 (best-effort) ──────────────────────────────────

def try_claude_plugin_update(quiet: bool = False) -> bool:
    """`claude plugin update orange-pm` 시도. CLI 부재·미지원 버전이면 조용히 False.
    파일 동기화는 이미 끝난 상태라 실패해도 안전하다(새 세션부터 새 버전 적용)."""
    claude = shutil.which("claude")
    if not claude:
        return False
    try:
        r = subprocess.run(
            [claude, "plugin", "update", PLUGIN_NAME],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if r.returncode == 0:
        if not quiet:
            print("✓ claude plugin update 완료 (활성 세션은 재시작 후 적용)")
        return True
    if not quiet:
        print("… claude plugin update 미지원/실패 — 파일 동기화로 충분, 세션 재시작 시 적용")
    return False


# ── viz 작동 설정 부트스트랩 (.vscode/settings.json) ─────────────────────────

def ensure_vscode_settings(workspace_root: Path, quiet: bool = False) -> bool:
    """워크스페이스 .vscode/settings.json 에 orangePmViz.product 를 보장한다.

    viz 패널은 product 미설정 시 기본값 "pm-viz" 로 고정되어 다른 프로젝트
    폴더에서 잘못된 데이터를 표시한다. PROJECTS/ 하위 첫 프로젝트를 기본값으로
    기입하되, 기존 파일의 다른 키는 불가침이며 orangePmViz.product 가 이미
    있으면 아무것도 하지 않는다(멱등). JSONC(주석 포함) 파일은 건드리지 않는다.
    """
    hub = None
    for cand in (workspace_root, workspace_root / "Planning-Agent-Hub"):
        if (cand / "PROJECTS").is_dir():
            hub = cand
            break
    if hub is None:
        return False
    try:
        projects = sorted(p.name for p in (hub / "PROJECTS").iterdir() if p.is_dir())
    except OSError:
        return False
    if not projects:
        return False

    settings_path = workspace_root / ".vscode" / "settings.json"
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # JSONC 등 파싱 불가 — 사용자 파일 보호를 위해 손대지 않는다.
            if not quiet:
                print(f"… {settings_path} 파싱 불가(JSONC?) — orangePmViz.product 수동 설정 필요")
            return False
        if not isinstance(settings, dict) or "orangePmViz.product" in settings:
            return False

    settings["orangePmViz.product"] = projects[0]
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        return False
    if not quiet:
        print(f"✓ .vscode/settings.json 보강: orangePmViz.product={projects[0]}")
    return True


# ── 버전 ──────────────────────────────────────────────────────────────────────

def get_local_version(source_dir: Path | None) -> str:
    candidates = []
    if source_dir:
        candidates.append(source_dir / ".claude-plugin" / "plugin.json")
    for p in find_install_paths():
        candidates.append(p / ".claude-plugin" / "plugin.json")

    for c in candidates:
        if c.exists():
            try:
                with open(c, encoding="utf-8") as f:
                    return json.load(f).get("version", "unknown")
            except Exception:
                pass
    return "unknown"


# ── 캐시 (version_check 공유) ────────────────────────────────────────────────

def write_cache(new_count: int) -> None:
    import time
    try:
        UPDATE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(UPDATE_CACHE, "w", encoding="utf-8") as f:
            json.dump({"checked_at": time.time(), "new_commits": new_count}, f)
    except OSError:
        pass


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="orange-pm 플러그인 git pull 업데이터")
    ap.add_argument("--check",   action="store_true", help="새 커밋 수 확인만, 있으면 exit 2")
    ap.add_argument("--quiet",   action="store_true", help="신규 커밋 없으면 무음")
    ap.add_argument("--no-pull", action="store_true", dest="no_pull",
                    help="git fetch/pull 생략 — VIZ 업데이트 스크립트처럼 이미 pull 된 후 호출 시 사용")
    ap.add_argument("--ensure-vscode", metavar="WORKSPACE_ROOT", dest="ensure_vscode",
                    help="해당 워크스페이스의 .vscode/settings.json 에 orangePmViz.product 보장(viz 부트스트랩)")
    ap.add_argument("--version", action="store_true", help="현재 설치 버전 출력 후 종료")
    args = ap.parse_args()

    # ── 소스 디렉토리 탐색 ────────────────────────────────────────────────────
    source_dir = find_source_dir()
    if not source_dir or not source_dir.exists():
        print("[ERROR] orange-pm 소스 디렉토리를 찾을 수 없습니다.", file=sys.stderr)
        print("  ~/.claude/plugins/known_marketplaces.json 에 'orange-pm' 항목이 있는지 확인하세요.", file=sys.stderr)
        sys.exit(1)

    if args.version:
        print(f"v{get_local_version(source_dir)}")
        return

    git_root = find_git_root(source_dir)
    if not git_root and not args.no_pull:
        print(f"[ERROR] git 저장소를 찾을 수 없습니다: {source_dir}", file=sys.stderr)
        sys.exit(1)

    # ── --no-pull 모드: git 생략, 캐시 동기화만 ──────────────────────────────
    if args.no_pull:
        if not args.quiet:
            print(f"소스 경로: {source_dir}")
            print("git pull 생략 (--no-pull)")
        synced = sync_to_install_paths(source_dir)
        if synced and not args.quiet:
            print(f"플러그인 캐시 동기화: {len(synced)}개 경로")
        try_claude_plugin_update(args.quiet)
        if args.ensure_vscode:
            ensure_vscode_settings(Path(args.ensure_vscode), args.quiet)
        if not args.quiet:
            print(f"✓ 플러그인 동기화 완료 (v{get_local_version(source_dir)})")
        return

    # ── 새 커밋 확인 ──────────────────────────────────────────────────────────
    _git(["fetch", "--quiet"], git_root, timeout=20)
    new_count = count_new_commits(git_root)

    if not args.quiet:
        print(f"소스 경로: {source_dir}")
        if new_count >= 0:
            print(f"새 커밋  : {new_count}개")
        else:
            print("새 커밋  : 확인 불가 (git fetch 실패)")

    write_cache(new_count)

    if new_count == 0:
        if not args.quiet:
            print(f"✓ 최신 상태입니다 (v{get_local_version(source_dir)})")
        sys.exit(0)

    if new_count < 0 and not args.quiet:
        print("[WARN] 커밋 수를 확인하지 못했습니다. pull 을 시도합니다.")

    if args.check:
        if new_count > 0:
            print(f"  → /orange-pm:update 로 업데이트하세요.")
        sys.exit(2 if new_count > 0 else 0)

    # ── git pull ──────────────────────────────────────────────────────────────
    print("git pull 실행 중...")
    ok, msg = git_pull(git_root)
    print(msg)
    if not ok:
        print("[ERROR] git pull 실패. 위 메시지를 확인하세요.", file=sys.stderr)
        sys.exit(1)

    # ── 캐시 동기화 ───────────────────────────────────────────────────────────
    synced = sync_to_install_paths(source_dir)
    if synced:
        print(f"플러그인 캐시 동기화: {len(synced)}개 경로")

    try_claude_plugin_update(args.quiet)
    if args.ensure_vscode:
        ensure_vscode_settings(Path(args.ensure_vscode), args.quiet)

    print(f"\n✓ orange-pm 업데이트 완료 (v{get_local_version(source_dir)})")
    print("  Claude Code를 재시작하면 새 버전이 적용됩니다.")
    print("  Mac: Cmd+Q  /  Windows: 창 닫기 후 재실행")


if __name__ == "__main__":
    main()
