# -*- coding: utf-8 -*-
"""
orange-pm plugin updater (git-pull based)

Behavior:
  1. Detect the orange-pm source path from ~/.claude/plugins/known_marketplaces.json
  2. Run git pull at that directory's git root
  3. Sync files to the orange-pm install path in installed_plugins.json
  4. Report the number of new commits

Usage:
  python update_orange_pm.py              # update
  python update_orange_pm.py --check      # only check the number of new commits (no install); exit 2 if any
  python update_orange_pm.py --quiet      # silent if there are no new commits (for internal hook use)
  python update_orange_pm.py --version    # print the currently installed version

No separate auth token needed — uses local git credentials
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ── Path constants ──────────────────────────────────────────────────────────────

CLAUDE_DIR        = Path.home() / ".claude"
KNOWN_MARKETS     = CLAUDE_DIR / "plugins" / "known_marketplaces.json"
INSTALLED_JSON    = CLAUDE_DIR / "plugins" / "installed_plugins.json"
UPDATE_CACHE      = CLAUDE_DIR / "orange-pm-update-check.json"
PLUGIN_NAME       = "orange-pm"

# Patterns excluded from git pull
_EXCLUDE = shutil.ignore_patterns("*.pyc", "__pycache__", "*_test.py", ".git", ".gitignore")


# ── Path discovery ─────────────────────────────────────────────────────────────

def find_source_dir() -> Path | None:
    """Returns the orange-pm source directory from known_marketplaces.json."""
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
    """Finds .git in path or a parent directory and returns the git root."""
    current = path.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def find_install_paths() -> list[Path]:
    """Returns all installPaths for orange-pm from installed_plugins.json."""
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


# ── git operations ──────────────────────────────────────────────────────────────

def _git(args: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd,
        capture_output=True, text=True, encoding="utf-8",
        timeout=timeout,
    )


def count_new_commits(git_root: Path) -> int:
    """Number of commits on origin/main not yet in HEAD. -1 on error."""
    # Auto-detect the default branch (main / master)
    for branch in ("main", "master"):
        r = _git(["rev-list", f"HEAD..origin/{branch}", "--count"], git_root, timeout=5)
        if r.returncode == 0:
            try:
                return int(r.stdout.strip())
            except ValueError:
                pass
    return -1


def git_pull(git_root: Path) -> tuple[bool, str]:
    """Runs git pull. Returns (success, output message)."""
    r = _git(["pull", "--ff-only"], git_root)
    ok = r.returncode == 0
    msg = (r.stdout + r.stderr).strip()
    return ok, msg


# ── File sync ───────────────────────────────────────────────────────────────

def sync_to_install_paths(source_dir: Path) -> list[Path]:
    """Copies source_dir's contents to every install path. Returns the list of synced paths."""
    paths = find_install_paths()
    synced = []
    for dst in paths:
        # Skip if source_dir and dst are the same
        if dst.resolve() == source_dir.resolve():
            continue
        shutil.copytree(
            str(source_dir), str(dst),
            ignore=_EXCLUDE,
            dirs_exist_ok=True,
        )
        synced.append(dst)
    return synced


# ── Claude Code plugin refresh (best-effort) ──────────────────────────────────

def try_claude_plugin_update(quiet: bool = False) -> bool:
    """Attempts `claude plugin update orange-pm`. Silently returns False if the
    CLI is absent or the version is unsupported. Safe to fail — file sync is
    already done by this point (the new version takes effect from the next session)."""
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
            print("✓ claude plugin update complete (applies to active sessions after restart)")
        return True
    if not quiet:
        print("… claude plugin update unsupported/failed — file sync is sufficient, applies on session restart")
    return False


# ── viz operation-settings bootstrap (.vscode/settings.json) ─────────────────────

def ensure_vscode_settings(workspace_root: Path, quiet: bool = False) -> bool:
    """Ensures orangePmViz.product is set in the workspace's .vscode/settings.json.

    When product is unset, the viz panel falls back to the default "pm-viz" and
    shows the wrong data in other project folders. Fills in the first project
    under PROJECTS/ as the default, while leaving any other existing keys in
    the file untouched; does nothing if orangePmViz.product is already set
    (idempotent). Leaves JSONC (with comments) files alone.
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
            # Can't parse (JSONC?) — leave the file untouched to protect the user's file.
            if not quiet:
                print(f"… {settings_path} could not be parsed (JSONC?) — set orangePmViz.product manually")
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
        print(f"✓ .vscode/settings.json updated: orangePmViz.product={projects[0]}")
    return True


# ── Version ──────────────────────────────────────────────────────────────────────

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


# ── Cache (shared with version_check) ────────────────────────────────────────

def write_cache(new_count: int) -> None:
    import time
    try:
        UPDATE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(UPDATE_CACHE, "w", encoding="utf-8") as f:
            json.dump({"checked_at": time.time(), "new_commits": new_count}, f)
    except OSError:
        pass


# ── Entry point ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="orange-pm plugin git-pull updater")
    ap.add_argument("--check",   action="store_true", help="Only check the number of new commits; exit 2 if any")
    ap.add_argument("--quiet",   action="store_true", help="Silent if there are no new commits")
    ap.add_argument("--no-pull", action="store_true", dest="no_pull",
                    help="Skip git fetch/pull — use when calling after a pull already happened, e.g. from the VIZ update script")
    ap.add_argument("--ensure-vscode", metavar="WORKSPACE_ROOT", dest="ensure_vscode",
                    help="Ensure orangePmViz.product is set in that workspace's .vscode/settings.json (viz bootstrap)")
    ap.add_argument("--version", action="store_true", help="Print the currently installed version and exit")
    args = ap.parse_args()

    # ── Locate the source directory ────────────────────────────────────────────
    source_dir = find_source_dir()
    if not source_dir or not source_dir.exists():
        print("[ERROR] Could not find the orange-pm source directory.", file=sys.stderr)
        print("  Check that ~/.claude/plugins/known_marketplaces.json has an 'orange-pm' entry.", file=sys.stderr)
        sys.exit(1)

    if args.version:
        print(f"v{get_local_version(source_dir)}")
        return

    git_root = find_git_root(source_dir)
    if not git_root and not args.no_pull:
        print(f"[ERROR] Could not find a git repository: {source_dir}", file=sys.stderr)
        sys.exit(1)

    # ── --no-pull mode: skip git, only sync the cache ──────────────────────────
    if args.no_pull:
        if not args.quiet:
            print(f"Source path: {source_dir}")
            print("Skipping git pull (--no-pull)")
        synced = sync_to_install_paths(source_dir)
        if synced and not args.quiet:
            print(f"Plugin cache synced: {len(synced)} path(s)")
        try_claude_plugin_update(args.quiet)
        if args.ensure_vscode:
            ensure_vscode_settings(Path(args.ensure_vscode), args.quiet)
        if not args.quiet:
            print(f"✓ Plugin sync complete (v{get_local_version(source_dir)})")
        return

    # ── Check for new commits ──────────────────────────────────────────────────────
    _git(["fetch", "--quiet"], git_root, timeout=20)
    new_count = count_new_commits(git_root)

    if not args.quiet:
        print(f"Source path : {source_dir}")
        if new_count >= 0:
            print(f"New commits : {new_count}")
        else:
            print("New commits : could not check (git fetch failed)")

    write_cache(new_count)

    if new_count == 0:
        if not args.quiet:
            print(f"✓ Already up to date (v{get_local_version(source_dir)})")
        sys.exit(0)

    if new_count < 0 and not args.quiet:
        print("[WARN] Could not check the commit count. Attempting a pull.")

    if args.check:
        if new_count > 0:
            print(f"  → Run /orange-pm:update to update.")
        sys.exit(2 if new_count > 0 else 0)

    # ── git pull ──────────────────────────────────────────────────────────────
    print("Running git pull...")
    ok, msg = git_pull(git_root)
    print(msg)
    if not ok:
        print("[ERROR] git pull failed. Check the message above.", file=sys.stderr)
        sys.exit(1)

    # ── Sync cache ───────────────────────────────────────────────────────────
    synced = sync_to_install_paths(source_dir)
    if synced:
        print(f"Plugin cache synced: {len(synced)} path(s)")

    try_claude_plugin_update(args.quiet)
    if args.ensure_vscode:
        ensure_vscode_settings(Path(args.ensure_vscode), args.quiet)

    print(f"\n✓ orange-pm update complete (v{get_local_version(source_dir)})")
    print("  Restart Claude Code to apply the new version.")
    print("  Mac: Cmd+Q  /  Windows: close the window and relaunch")


if __name__ == "__main__":
    main()
