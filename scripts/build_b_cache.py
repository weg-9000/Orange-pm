#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""{PREFIX}-B 공통 정책서 요약 캐시 생성 (개선안 A — CONTEXT_OPTIMIZATION.md).

목적:
    /write, /flow, /integrate 가 매 호출마다 CONTEXT/reference-docs/B/*.md 전체를
    재로드하는 비효율을 제거한다. 각 정책 문서에서 "## " 헤딩 + 헤딩 직후 첫 문단
    (3줄까지)만 발췌해 단일 요약본으로 합친 뒤 .template-cache/B-summary.md 에 저장한다.

    skill 들은 다음 순서로 사용한다:
      1) B-summary.md 가 모든 reference-docs/B/*.md 보다 mtime 이 최신이면 캐시만 로드.
      2) 그렇지 않으면 본 스크립트로 캐시를 재생성한 뒤 다시 캐시만 로드.
    원문 전체 로드는 헤딩 인덱스(B-headings-index.json) 기반 발췌 모드에서만 수행한다.

사용법:
    python build_b_cache.py --hub-root <Planning-Agent-Hub 경로>

exit code:
    0 = 성공 (캐시 새로 생성 또는 최신 상태 확인)
    1 = layer-config.md 에서 PREFIX 추출 실패 또는 reference-docs/B 없음
    2 = 인자 오류
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from _cache_utils import (
    HEADING_PATTERN,
    cache_is_fresh,
    discover_b_sources,
    ensure_cache_dir,
    make_hub_root_parser,
    read_prefix,
    validate_hub_root,
)


def extract_summary(md_text: str, max_para_lines: int = 3) -> list[str]:
    """헤딩 + 헤딩 직후 첫 문단(공백 라인 전까지, 최대 max_para_lines줄)만 추출."""
    lines = md_text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if HEADING_PATTERN.match(line):
            out.append(line)
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            para_lines: list[str] = []
            while j < len(lines) and lines[j].strip() and not HEADING_PATTERN.match(lines[j]):
                para_lines.append(lines[j])
                if len(para_lines) >= max_para_lines:
                    break
                j += 1
            if para_lines:
                out.append("")
                out.extend(para_lines)
            out.append("")
            i = j
            continue
        i += 1
    return out


def _advise_drift(hub_root: Path) -> None:
    """캐시 재생성 후 drift_scan 을 best-effort 로 연쇄한다.

    공통(B) 캐시가 갱신됐다는 것은 B 원본이 바뀌었을 수 있다는 신호이므로,
    영향 제품 draft 의 referenced_master 핀을 재대조한다.
    실패하거나 PROJECTS 가 없으면 조용히 통과한다(build 의 exit code 불변).
    """
    try:
        if not (hub_root / "PROJECTS").is_dir():
            return
        import importlib.util
        ds_path = Path(__file__).with_name("drift_scan.py")
        if not ds_path.exists():
            return
        spec = importlib.util.spec_from_file_location("drift_scan", ds_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        rc = mod.scan(hub_root)
        if rc:
            print("[build_b_cache] drift BLOCK 존재 — reports/drift-queue.md 확인 권고")
    except Exception as exc:  # 연쇄 실패가 캐시 빌드를 막지 않는다
        print(f"[build_b_cache] drift_scan 연쇄 생략({exc})")


def build(hub_root: Path) -> int:
    prefix = read_prefix(hub_root)
    sources = discover_b_sources(hub_root)
    cache_dir = ensure_cache_dir(hub_root)
    # PREFIX 네임스페이스 캐시(주) + 레거시 무네임스페이스(부, 활성 PREFIX 한정).
    cache_path = cache_dir / f"{prefix}-b-summary.md"
    legacy_path = cache_dir / "B-summary.md"

    if cache_is_fresh(cache_path, sources) and legacy_path.exists():
        print(f"[build_b_cache] up-to-date: {cache_path}")
        _advise_drift(hub_root)
        return 0

    parts: list[str] = [
        f"# {prefix}-B Summary Cache (auto-generated)",
        "",
        "> 본 파일은 build_b_cache.py 가 자동 생성한 요약본이다. 직접 수정하지 말 것.",
        f"> 생성 시각: {datetime.now().isoformat(timespec='seconds')}",
        f"> 원본: CONTEXT/reference-docs/{prefix}/B/ ({len(sources)}개 문서)",
        "",
    ]
    for src in sources:
        parts.append(f"## ── {src.name} ──")
        parts.append("")
        parts.extend(extract_summary(src.read_text(encoding="utf-8")))
        parts.append("")

    payload = "\n".join(parts)
    cache_path.write_text(payload, encoding="utf-8")
    # 레거시 호환: 활성 PREFIX 요약을 무네임스페이스 파일로도 미러링(구버전 skill 참조용).
    legacy_path.write_text(payload, encoding="utf-8")
    print(f"[build_b_cache] wrote {cache_path} (+legacy {legacy_path.name}, {len(sources)} sources)")
    _advise_drift(hub_root)
    return 0


def main() -> int:
    parser = make_hub_root_parser("Build {PREFIX}-B summary cache")
    args = parser.parse_args()
    rc = validate_hub_root(args.hub_root)
    if rc:
        return rc
    return build(args.hub_root)


if __name__ == "__main__":
    sys.exit(main())
