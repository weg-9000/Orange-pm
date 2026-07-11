#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plugin version bump — atomically syncs 3 locations against the SSoT (plugin.json).

Version field locations (must always hold the same value):
  1. .claude-plugin/plugin.json          .version          <- SSoT
  2. .claude-plugin/marketplace.json     .plugins[0].version
  3. .claude-plugin/marketplace.json     .version (top level)

Usage:
  python scripts/bump_version.py patch          # 2.0.0 -> 2.0.1
  python scripts/bump_version.py minor          # 2.0.0 -> 2.1.0
  python scripts/bump_version.py major          # 2.0.0 -> 3.0.0
  python scripts/bump_version.py --set 2.5.0    # explicit version
  python scripts/bump_version.py --check        # only verify all 3 locations match (for CI)

Procedure to follow after bumping:
  1. git add -A && git commit -m "release: vX.Y.Z"
  2. git tag vX.Y.Z && git push && git push --tags
  3. Publish notes on GitHub Releases (version history lives there, not in-repo):
       gh release create vX.Y.Z --generate-notes
     (or draft it in the GitHub web UI)

exit code: 0 success / 1 verification failed / 2 argument error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_JSON = ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = ROOT / ".claude-plugin" / "marketplace.json"
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _load(p: Path) -> dict:
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _save(p: Path, data: dict) -> None:
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def current_versions() -> dict[str, str]:
    plugin = _load(PLUGIN_JSON)
    market = _load(MARKETPLACE_JSON)
    return {
        "plugin.json .version": plugin.get("version", "?"),
        "marketplace.json .plugins[0].version": market["plugins"][0].get("version", "?"),
        "marketplace.json .version": market.get("version", "?"),
    }


def check() -> int:
    vers = current_versions()
    vals = set(vers.values())
    for k, v in vers.items():
        print(f"  {v:>10}  {k}")
    if len(vals) != 1:
        print("FAIL: version fields do not match — sync them with bump_version.py.")
        return 1
    v = vals.pop()
    if not SEMVER.match(v):
        print(f"FAIL: '{v}' is not in SemVer (X.Y.Z) format.")
        return 1
    print(f"OK: v{v} (all 3 locations match)")
    return 0


def bump(kind: str | None, explicit: str | None) -> int:
    cur = _load(PLUGIN_JSON).get("version", "0.0.0")
    m = SEMVER.match(cur)
    if not m:
        print(f"FAIL: could not parse current version '{cur}'")
        return 1
    major, minor, patch = map(int, m.groups())

    if explicit:
        if not SEMVER.match(explicit):
            print(f"FAIL: '{explicit}' is not in SemVer (X.Y.Z) format.")
            return 2
        new = explicit
    elif kind == "major":
        new = f"{major + 1}.0.0"
    elif kind == "minor":
        new = f"{major}.{minor + 1}.0"
    elif kind == "patch":
        new = f"{major}.{minor}.{patch + 1}"
    else:
        print("FAIL: need patch|minor|major or --set X.Y.Z")
        return 2

    plugin = _load(PLUGIN_JSON)
    plugin["version"] = new
    _save(PLUGIN_JSON, plugin)

    market = _load(MARKETPLACE_JSON)
    market["plugins"][0]["version"] = new
    market["version"] = new
    _save(MARKETPLACE_JSON, market)

    print(f"v{cur} -> v{new}  (plugin.json + marketplace.json both synced)")
    print("\nNext steps:")
    print(f'  1. git add -A && git commit -m "release: v{new}"')
    print(f"  2. git tag v{new} && git push && git push --tags")
    print(f"  3. gh release create v{new} --generate-notes   (publish notes on GitHub Releases)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Bump plugin version (syncs 3 locations)")
    ap.add_argument("kind", nargs="?", choices=["patch", "minor", "major"])
    ap.add_argument("--set", dest="explicit", metavar="X.Y.Z")
    ap.add_argument("--check", action="store_true", help="only verify all locations match")
    args = ap.parse_args()

    if args.check:
        return check()
    return bump(args.kind, args.explicit)


if __name__ == "__main__":
    sys.exit(main())
