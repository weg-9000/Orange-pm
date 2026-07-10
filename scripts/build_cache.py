#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""캐시 빌드 통합 디스패처 (S1-3, CONTEXT_OPTIMIZATION.md).

⚠️ SUPERSEDED / STANDALONE — 어떤 스킬·훅에도 wiring 되어 있지 않다.
    라이브 캐시 빌더는 build_bootstrap / build_b_cache / build_b_index 이며,
    모든 스킬은 이 3개 빌더를 직접 호출한다 (--target all 디스패처 경유 아님).
    본 --target all 디스패처는 호출처가 없어 사실상 dead 다.
    수동/단독 일괄 빌드 도구로만 보존한다. 런타임 로직은 변경하지 않는다.

목적:
    build_b_cache / build_b_index / build_bootstrap 3개 스크립트를 하나의 진입점에서
    호출할 수 있도록 한다. 원본 3개 스크립트는 그대로 유지되어 단독 실행도 가능하다.

사용법:
    python build_cache.py --hub-root <Planning-Agent-Hub 경로> [--target TARGET]

    TARGET:
        b-summary  → build_b_cache.build(hub_root)
        b-index    → build_b_index.build(hub_root)
        bootstrap  → build_bootstrap.build(hub_root)
        all        → 위 셋을 순차 실행 (기본값)

exit code:
    0 = 모든 단계 성공
    1 = 어떤 단계에서 실패 (각 단계의 exit code 중 최댓값을 반환)
    2 = 인자 오류 (--hub-root 디렉토리 아님 / 알 수 없는 --target)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 같은 디렉토리의 build_* 모듈을 import 하기 위해 scripts 경로를 sys.path 앞에 둔다.
# (스크립트가 어디서 호출되더라도 일관되게 동작하도록 한다.)
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import build_b_cache  # noqa: E402  (sys.path 조정 후 import 필요)
import build_b_index  # noqa: E402
import build_bootstrap  # noqa: E402
from _cache_utils import validate_hub_root  # noqa: E402

TARGETS = ("b-summary", "b-index", "bootstrap", "all")

# target → (라벨, 호출가능)
_DISPATCH = {
    "b-summary": ("build_b_cache", build_b_cache.build),
    "b-index": ("build_b_index", build_b_index.build),
    "bootstrap": ("build_bootstrap", build_bootstrap.build),
}


def _run_one(label: str, fn, hub_root: Path) -> int:
    """단일 빌드 단계를 실행하고 종료코드를 반환. 예외는 1로 환산한다."""
    try:
        rc = fn(hub_root)
    except SystemExit as exc:  # 헬퍼가 sys.exit 한 경우(예: layer-config 누락)
        rc = exc.code if isinstance(exc.code, int) else 1
        print(f"[build_cache] {label} aborted with exit code {rc}", file=sys.stderr)
        return rc
    except Exception as exc:  # noqa: BLE001 — 디스패처는 모든 예외를 격리한다
        print(f"[build_cache] {label} raised {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return rc or 0


def run(hub_root: Path, target: str) -> int:
    """target 에 해당하는 빌드를 실행하고 종합 종료코드를 반환한다."""
    if target == "all":
        worst = 0
        for key in ("b-summary", "b-index", "bootstrap"):
            label, fn = _DISPATCH[key]
            rc = _run_one(label, fn, hub_root)
            if rc > worst:
                worst = rc
        return worst
    label, fn = _DISPATCH[target]
    return _run_one(label, fn, hub_root)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified cache build dispatcher (b-summary / b-index / bootstrap)",
    )
    parser.add_argument(
        "--hub-root",
        required=True,
        type=Path,
        help="Planning-Agent-Hub directory",
    )
    parser.add_argument(
        "--target",
        choices=TARGETS,
        default="all",
        help="Which cache to build (default: all)",
    )
    args = parser.parse_args()
    rc = validate_hub_root(args.hub_root)
    if rc:
        return rc
    return run(args.hub_root, args.target)


if __name__ == "__main__":
    sys.exit(main())
