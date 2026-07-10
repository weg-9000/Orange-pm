#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""플러그인 버전 bump — SSoT(plugin.json) 기준 3곳 원자 동기화.

버전 필드 위치 (항상 동일 값 유지):
  1. .claude-plugin/plugin.json          .version          ← SSoT
  2. .claude-plugin/marketplace.json     .plugins[0].version
  3. .claude-plugin/marketplace.json     .version (최상위)

사용법:
  python scripts/bump_version.py patch          # 2.0.0 → 2.0.1
  python scripts/bump_version.py minor          # 2.0.0 → 2.1.0
  python scripts/bump_version.py major          # 2.0.0 → 3.0.0
  python scripts/bump_version.py --set 2.5.0    # 명시 지정
  python scripts/bump_version.py --check        # 3곳 일치 검증만 (CI용)

bump 후 안내되는 절차:
  1. CHANGELOG.md 의 [Unreleased] 항목을 새 버전 섹션으로 이동
  2. git add -A && git commit -m "release: vX.Y.Z"
  3. git tag vX.Y.Z && git push && git push --tags

exit code: 0 성공 / 1 검증 실패 / 2 인자 오류
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
        print("FAIL: 버전 필드 불일치 — bump_version.py 로 동기화하세요.")
        return 1
    v = vals.pop()
    if not SEMVER.match(v):
        print(f"FAIL: '{v}' 는 SemVer(X.Y.Z) 형식이 아닙니다.")
        return 1
    print(f"OK: v{v} (3곳 일치)")
    return 0


def bump(kind: str | None, explicit: str | None) -> int:
    cur = _load(PLUGIN_JSON).get("version", "0.0.0")
    m = SEMVER.match(cur)
    if not m:
        print(f"FAIL: 현재 버전 '{cur}' 파싱 불가")
        return 1
    major, minor, patch = map(int, m.groups())

    if explicit:
        if not SEMVER.match(explicit):
            print(f"FAIL: '{explicit}' 는 SemVer(X.Y.Z) 형식이 아닙니다.")
            return 2
        new = explicit
    elif kind == "major":
        new = f"{major + 1}.0.0"
    elif kind == "minor":
        new = f"{major}.{minor + 1}.0"
    elif kind == "patch":
        new = f"{major}.{minor}.{patch + 1}"
    else:
        print("FAIL: patch|minor|major 또는 --set X.Y.Z 필요")
        return 2

    plugin = _load(PLUGIN_JSON)
    plugin["version"] = new
    _save(PLUGIN_JSON, plugin)

    market = _load(MARKETPLACE_JSON)
    market["plugins"][0]["version"] = new
    market["version"] = new
    _save(MARKETPLACE_JSON, market)

    print(f"v{cur} → v{new}  (plugin.json + marketplace.json 2곳 동기화 완료)")
    print("\n다음 절차:")
    print(f"  1. CHANGELOG.md [Unreleased] → [{new}] 섹션으로 이동")
    print(f'  2. git add -A && git commit -m "release: v{new}"')
    print(f"  3. git tag v{new} && git push && git push --tags")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="플러그인 버전 bump (3곳 동기화)")
    ap.add_argument("kind", nargs="?", choices=["patch", "minor", "major"])
    ap.add_argument("--set", dest="explicit", metavar="X.Y.Z")
    ap.add_argument("--check", action="store_true", help="일치 검증만 수행")
    args = ap.parse_args()

    if args.check:
        return check()
    return bump(args.kind, args.explicit)


if __name__ == "__main__":
    sys.exit(main())
