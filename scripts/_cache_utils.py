#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for cache build scripts (build_b_cache / build_b_index / build_bootstrap).

본 모듈은 3개 캐시 빌드 스크립트가 중복으로 들고 있던 로직을 한 곳에 모은다.
스크립트별 고유 로직(요약 추출·헤딩 인덱싱·소스 명단 등)은 각 스크립트에 그대로 둔다.

설계 원칙:
    - 각 헬퍼는 의존성이 작고 부수효과가 명확해야 한다.
    - sys.exit() 는 스크립트 main() 에서만 호출한다. 헬퍼는 예외 또는 명시적 반환값을
      통해 실패를 보고한다(현재 read_prefix 만 호환성 유지를 위해 sys.exit 유지).
    - 본 모듈에 화면 표시(print)는 두지 않는다.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 공용 정규식 (build_b_cache / build_b_index 가 동일 패턴 사용).
# 주의: ``^PREFIX:`` 는 줄 시작이 정확히 ``PREFIX:`` 인 레거시 단일 선언만 매칭한다.
# ``ACTIVE_PREFIX:`` 와 ``PREFIXES:`` 는 줄 시작 토큰이 달라 매칭되지 않는다(의도된 격리).
PREFIX_PATTERN = re.compile(r"^PREFIX:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)
ACTIVE_PREFIX_PATTERN = re.compile(r"^ACTIVE_PREFIX:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)
PREFIXES_ITEM_PATTERN = re.compile(r"^\s*-\s*id:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _read_layer_config(hub_root: Path) -> str:
    """CONTEXT/layer-config.md 본문을 읽는다. 없으면 ``sys.exit(1)``."""
    config = hub_root / "CONTEXT" / "layer-config.md"
    if not config.exists():
        sys.stderr.write(f"layer-config.md not found: {config}\n")
        sys.exit(1)
    return config.read_text(encoding="utf-8")


def read_active_prefix(hub_root: Path) -> str:
    """현재 세션 작업 대상 PREFIX 를 반환한다.

    우선순위:
      1) ``ACTIVE_PREFIX: <value>``  (멀티-PREFIX 형식, Phase 1+)
      2) ``PREFIX: <value>``         (레거시 단일 선언)

    둘 다 없으면 stderr 후 ``sys.exit(1)`` (기존 read_prefix 와 동일 종료 시그널).
    """
    text = _read_layer_config(hub_root)
    m = ACTIVE_PREFIX_PATTERN.search(text)
    if m:
        return m.group(1)
    m = PREFIX_PATTERN.search(text)
    if m:
        return m.group(1)
    sys.stderr.write(
        "PREFIX/ACTIVE_PREFIX not declared in layer-config.md "
        "(expected `PREFIX: <value>` or `ACTIVE_PREFIX: <value>`)\n"
    )
    sys.exit(1)


def read_prefixes(hub_root: Path) -> list[str]:
    """선언된 전체 PREFIX 목록을 반환한다 (멀티-PREFIX, Phase 1+).

    ``PREFIXES:`` 블록의 ``- id: <value>`` 항목을 순서대로 수집한다.
    블록이 없으면 단일 PREFIX([read_active_prefix()]) 로 폴백한다(하위호환).
    """
    text = _read_layer_config(hub_root)
    ids = PREFIXES_ITEM_PATTERN.findall(text)
    if ids:
        return ids
    return [read_active_prefix(hub_root)]


def read_prefix(hub_root: Path) -> str:
    """[하위호환 래퍼] 현재 활성 PREFIX 를 반환한다.

    기존 스크립트(build_b_cache / build_b_index 등)가 호출하던 시그니처를 보존한다.
    내부적으로 ``read_active_prefix`` 에 위임하므로 ACTIVE_PREFIX 전환을 자동 반영한다.
    """
    return read_active_prefix(hub_root)


def discover_layer_sources(hub_root: Path, prefix: str, layer: str) -> list[Path]:
    """``reference-docs`` 에서 특정 (prefix, layer) 의 마크다운 소스를 수집한다.

    듀얼 경로 탐색(점진 마이그레이션 안전망):
      1) 신규 중첩: ``CONTEXT/reference-docs/{prefix}/{layer}/*.md``
      2) 레거시 평면: ``CONTEXT/reference-docs/{layer}/*.md``
    신규 경로가 디렉토리로 존재하면 그것을, 아니면 레거시 경로를 사용한다.

    README.md 는 제외하며 정렬된 목록을 반환한다. 디렉토리가 없으면 빈 목록
    (호출자가 누락 정책을 결정하도록 종료하지 않는다).
    """
    base = hub_root / "CONTEXT" / "reference-docs"
    nested = base / prefix / layer
    legacy = base / layer
    src_dir = nested if nested.is_dir() else legacy
    if not src_dir.is_dir():
        return []
    return sorted(p for p in src_dir.glob("*.md") if p.name != "README.md")


def discover_b_sources(hub_root: Path) -> list[Path]:
    """[하위호환 래퍼] 활성 PREFIX 의 B 계층 소스를 반환한다.

    디렉토리가 존재하지 않거나 대상 문서가 0개면 stderr 메시지 후 ``sys.exit(1)``
    (기존 동작 1:1 보존).
    """
    prefix = read_active_prefix(hub_root)
    sources = discover_layer_sources(hub_root, prefix, "B")
    if not sources:
        sys.stderr.write(
            f"no B documents under reference-docs/{prefix}/B or reference-docs/B\n"
        )
        sys.exit(1)
    return sources


def ensure_cache_dir(hub_root: Path) -> Path:
    """``CONTEXT/.template-cache/`` 를 보장 생성하고 그 경로를 반환한다."""
    cache_dir = hub_root / "CONTEXT" / ".template-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def cache_is_fresh(
    cache_path: Path,
    sources: list[Path],
    *,
    allow_missing_sources: bool = False,
) -> bool:
    """캐시가 모든 소스보다 새로우면 True.

    - cache_path 가 없으면 False.
    - ``allow_missing_sources=False`` (기본): 소스가 존재하지 않으면 False(=재생성 필요)
      는 의미가 모호하므로 ``stat()`` 호출이 그대로 예외를 던지게 둔다.
    - ``allow_missing_sources=True`` (bootstrap 케이스): 소스 파일 누락은 캐시 신선도에
      영향을 주지 않는 것으로 본다(누락된 자리표시자는 그대로 유지된다).
    """
    if not cache_path.exists():
        return False
    cache_mtime = cache_path.stat().st_mtime
    if allow_missing_sources:
        return all((not src.exists()) or src.stat().st_mtime <= cache_mtime for src in sources)
    return all(src.stat().st_mtime <= cache_mtime for src in sources)


def make_hub_root_parser(description: str) -> argparse.ArgumentParser:
    """``--hub-root`` 인자만 가진 표준 ArgumentParser 를 생성한다."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--hub-root",
        required=True,
        type=Path,
        help="Planning-Agent-Hub directory",
    )
    return parser


def validate_hub_root(hub_root: Path) -> int:
    """hub-root 가 디렉토리가 아니면 stderr 출력 + 2 반환, 정상이면 0.

    스크립트 main() 에서 ``rc = validate_hub_root(...)`` 후 0 이 아니면 즉시 ``return rc``.
    """
    if not hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {hub_root}\n")
        return 2
    return 0
