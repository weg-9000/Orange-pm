#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helper to connect/update reference-docs as a GitLab policy-repo submodule.

The URL is never hardcoded — the **user provides it** (argument or prompt).
The canonical policy sources (A/B/C) are managed in a separate policy repo,
and the hub references that repo as a CONTEXT/reference-docs submodule
(guide: docs/reference-docs-submodule.md).

Usage:
    # Initial connection (the user provides the URL — prompted if the argument is omitted)
    python reference_submodule.py add --url <git@gitlab:planning/policy-docs.git> \
        [--path CONTEXT/reference-docs] [--branch main]

    # Init after clone / update to the latest pin
    python reference_submodule.py update [--remote]

Notes:
    - If the `add` target path is already tracked, run `git rm -r <path>` first (guide §2).
    - This runs real git commands, so run it from the hub (working tree) root.

exit code: 0 success / 1 failure (path conflict / git error) / 2 argument error
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def build_add_cmd(url: str, path: str, branch: str | None) -> list[str]:
    """Build the git submodule add command (pure function — under test)."""
    cmd = ["git", "submodule", "add"]
    if branch:
        cmd += ["-b", branch]
    cmd += [url, path]
    return cmd


def build_update_cmd(remote: bool) -> list[str]:
    cmd = ["git", "submodule", "update", "--init", "--recursive"]
    if remote:
        cmd.append("--remote")
    return cmd


def _prompt_url(given: str | None) -> str:
    """The URL is user input. If no argument is given, prompt interactively."""
    url = (given or "").strip()
    if not url:
        try:
            url = input("Enter the policy repo URL (e.g. git@gitlab.example.com:planning/policy-docs.git): ").strip()
        except EOFError:
            url = ""
    return url


def _run(cmd: list[str]) -> int:
    print("[reference_submodule] $ " + " ".join(cmd))
    return subprocess.call(cmd)


def main() -> int:
    ap = argparse.ArgumentParser(description="Connect/update the reference-docs policy-repo submodule")
    sub = ap.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Connect the policy repo as a submodule (user-provided URL)")
    p_add.add_argument("--url", default=None, help="Policy repo URL (prompted if not specified)")
    p_add.add_argument("--path", default="CONTEXT/reference-docs")
    p_add.add_argument("--branch", default="main")

    p_upd = sub.add_parser("update", help="Initialize/update the submodule")
    p_upd.add_argument("--remote", action="store_true", help="Update to the latest remote commit")

    args = ap.parse_args()

    if args.command == "update":
        return 0 if _run(build_update_cmd(args.remote)) == 0 else 1

    # add
    url = _prompt_url(args.url)
    if not url:
        sys.stderr.write("A URL is required (via --url argument or the prompt)\n")
        return 2
    target = Path(args.path)
    if target.exists() and any(target.iterdir()):
        sys.stderr.write(
            f"Path is not empty: {target}\n"
            f"  First move the canonical source into the policy repo, then run `git rm -r {args.path}` and try again.\n"
        )
        return 1
    return 0 if _run(build_add_cmd(url, args.path, args.branch)) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
