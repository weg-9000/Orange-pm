#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reference-docs 를 GitLab 정책 레포 서브모듈로 연결/갱신하는 헬퍼.

URL 을 코드에 하드코딩하지 않고 **사용자가 입력**한다(인자 또는 프롬프트).
정책 진본(A/B/C)은 별도 정책 레포에서 관리하고, 허브는 그 레포를
CONTEXT/reference-docs 서브모듈로 참조한다(가이드: docs/reference-docs-submodule.md).

사용법:
    # 최초 연결(URL 은 사용자가 입력 — 인자 생략 시 프롬프트)
    python reference_submodule.py add --url <git@gitlab:planning/policy-docs.git> \
        [--path CONTEXT/reference-docs] [--branch main]

    # 클론 후 초기화 / 최신 핀으로 갱신
    python reference_submodule.py update [--remote]

주의:
    - add 대상 경로가 이미 추적 중이면 먼저 `git rm -r <path>` 후 실행한다(가이드 §2).
    - 실제 git 명령을 수행하므로 허브(작업 트리) 루트에서 실행한다.

exit code: 0 성공 / 1 실패(경로 충돌·git 오류) / 2 인자 오류
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def build_add_cmd(url: str, path: str, branch: str | None) -> list[str]:
    """git submodule add 명령 구성(순수 함수 — 테스트 대상)."""
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
    """URL 은 사용자 입력. 인자 없으면 대화형 프롬프트."""
    url = (given or "").strip()
    if not url:
        try:
            url = input("정책 레포 URL 을 입력하세요 (예: git@gitlab.example.com:planning/policy-docs.git): ").strip()
        except EOFError:
            url = ""
    return url


def _run(cmd: list[str]) -> int:
    print("[reference_submodule] $ " + " ".join(cmd))
    return subprocess.call(cmd)


def main() -> int:
    ap = argparse.ArgumentParser(description="reference-docs 정책 레포 서브모듈 연결/갱신")
    sub = ap.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="정책 레포를 서브모듈로 연결(URL 사용자 입력)")
    p_add.add_argument("--url", default=None, help="정책 레포 URL(미지정 시 프롬프트)")
    p_add.add_argument("--path", default="CONTEXT/reference-docs")
    p_add.add_argument("--branch", default="main")

    p_upd = sub.add_parser("update", help="서브모듈 초기화/갱신")
    p_upd.add_argument("--remote", action="store_true", help="원격 최신 커밋으로 갱신")

    args = ap.parse_args()

    if args.command == "update":
        return 0 if _run(build_update_cmd(args.remote)) == 0 else 1

    # add
    url = _prompt_url(args.url)
    if not url:
        sys.stderr.write("URL 이 필요합니다(인자 --url 또는 프롬프트 입력)\n")
        return 2
    target = Path(args.path)
    if target.exists() and any(target.iterdir()):
        sys.stderr.write(
            f"경로가 비어있지 않습니다: {target}\n"
            f"  먼저 진본을 정책 레포로 옮긴 뒤 `git rm -r {args.path}` 후 다시 실행하세요.\n"
        )
        return 1
    return 0 if _run(build_add_cmd(url, args.path, args.branch)) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
