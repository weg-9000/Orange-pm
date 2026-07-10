#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cluster Seed Backfill — 부트스트랩 (P5, docs/fr-cluster-alignment.md).

무태그 requirements 를 정상화하기 위한 마이그레이션 도구.

배경 (P5 / 2패스 워크플로우):
    씨앗(capability) 태그가 전혀 없는 제품도 `cluster_identify` 를 1회 돌리면
    점수(5축)만으로 cluster_map.json 의 fr_index(FR→{capability,cluster_id}) 가
    산출된다. 이 결과를 **사이드카 YAML(`requirements.seeds.yml`)** 에 backfill
    하면, 이후 실행부터는 union-find 초기 파티션(씨앗)으로 소비되어 2패스가
    정상 동작한다(seed-not-lock).

설계 결정 — 씨앗은 사이드카에 산다:
    requirements.md 본문을 변형하지 않고, 같은 디렉터리의 별도 YAML 파일에
    씨앗을 보관·병합한다. 본문 비파괴 + 결정적 파싱 + git diff 명료.

원칙:
    - 멱등(idempotent): 이미 capability 씨앗이 있는 FR 은 건너뛴다(--force 로 덮어쓰기).
    - 비파괴(non-destructive): fr_index 에 없는 기존 씨앗 항목/필드는 보존한다.
    - --dry-run: 변경 예정 내역만 출력하고 쓰지 않는다.
    - 결정적 출력: 키 정렬(sort_keys) + allow_unicode 로 안정적인 diff 보장.

사이드카 스키마 (`requirements.seeds.yml`, requirements.md 와 동일 디렉터리):
    "FR-101":
      capability: "Provisioning"
      cluster_hint: "PR-01"   # 선택 (없으면 생략)
      lock: false             # 선택, 기본 false
    "FR-102":
      capability: "[확인필요]"

CLI:
    python cluster_seed_backfill.py \
        --cluster-map PROJECTS/{p}/graph/cluster_map.json \
        --seeds       PROJECTS/{p}/inputs/requirements.seeds.yml \
        [--force]         # 기존 capability 씨앗도 덮어쓰기
        [--dry-run]       # 변경 예정만 출력(쓰기 없음)

종료 코드: 0 성공 / 1 입력 오류
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_fr_index(cluster_map: dict[str, Any]) -> dict[str, dict]:
    """cluster_map 에서 fr_index(FR→{capability,cluster_id}) 추출.

    포맷이 어긋나면 빈 dict 를 반환(예외 던지지 않음 — graceful)."""
    raw = cluster_map.get("fr_index")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for fr, info in raw.items():
        if isinstance(info, dict):
            out[str(fr)] = info
    return out


def _read_seeds(path: Path) -> dict[str, dict]:
    """사이드카 YAML 로드. 없거나 비어 있으면 {} (graceful).

    top-level 이 map 이 아니면 {} 로 본다(파손 방지)."""
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict] = {}
    for fr, info in data.items():
        if isinstance(info, dict):
            out[str(fr)] = dict(info)
        else:
            # 형식이 어긋난 항목도 보존(비파괴) — 그대로 둔다
            out[str(fr)] = info
    return out


# ── 순수 병합 로직 ────────────────────────────────────────────────────────
def backfill_seeds(
    fr_index: dict,
    seeds: dict,
    *,
    force: bool = False,
) -> tuple[dict, list[dict]]:
    """fr_index 를 사이드카 seeds dict 에 병합 (순수 함수).

    각 FR 에 대해 capability 와 cluster_hint(=cluster_id) 를 설정한다.
    멱등: 이미 capability 가 있는 FR 은 건너뛴다(--force 면 덮어쓴다).
    fr_index 에 없는 기존 seed 항목/필드는 보존한다(비파괴).

    Args:
        fr_index: FR → {"capability": ..., "cluster_id": ...}
        seeds: 기존 사이드카 dict (FR → {capability, cluster_hint?, lock?})
        force: True 면 기존 capability 씨앗도 덮어쓴다

    Returns:
        (new_seeds, changes) — changes 각 항목: {"fr", "action"}
          action ∈ {"injected", "updated", "skipped_existing"}

    예외를 던지지 않는다(graceful). 항상 (dict, 변경목록) 반환."""
    changes: list[dict] = []

    # 기존 항목 보존을 위해 깊은(1단계) 복사
    new_seeds: dict = {}
    for fr, info in (seeds or {}).items():
        new_seeds[str(fr)] = dict(info) if isinstance(info, dict) else info

    if not isinstance(fr_index, dict):
        return new_seeds, changes

    for fr, info in fr_index.items():
        if not isinstance(info, dict):
            continue
        capability = info.get("capability")
        if capability is None:
            continue
        capability = str(capability)
        cluster_id = info.get("cluster_id")
        fr = str(fr)

        existing = new_seeds.get(fr)
        has_capability = (
            isinstance(existing, dict) and existing.get("capability") not in (None, "")
        )

        if has_capability and not force:
            changes.append({"fr": fr, "action": "skipped_existing"})
            continue

        # 기존 dict 항목의 다른 필드(lock 등)는 보존하고 capability/cluster_hint 만 갱신
        entry: dict = dict(existing) if isinstance(existing, dict) else {}
        action = "updated" if has_capability else "injected"
        entry["capability"] = capability
        if cluster_id is not None and str(cluster_id).strip():
            entry["cluster_hint"] = str(cluster_id).strip()

        new_seeds[fr] = entry
        changes.append({"fr": fr, "action": action})

    return new_seeds, changes


def _dump_seeds(seeds: dict) -> str:
    """사이드카 dict → 결정적 YAML 문자열 (정렬 + unicode 유지)."""
    return yaml.safe_dump(seeds, allow_unicode=True, sort_keys=True)


def _summarize(changes: list[dict]) -> dict[str, int]:
    """action 별 건수 집계."""
    counts: dict[str, int] = {}
    for c in changes:
        counts[c["action"]] = counts.get(c["action"], 0) + 1
    return counts


# ── 파일 I/O ─────────────────────────────────────────────────────────────
def run_backfill(
    cluster_map_path: Path,
    seeds_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[int, list[dict]]:
    """파일 I/O 래퍼. (exit_code, changes) 반환.

    cluster_map(fr_index) 로드(누락/파손 → exit 1), 기존 사이드카 YAML 로드
    (누락 → {}), 병합 계산, dry_run 이 아니면 사이드카에 쓴다. fr_index 에 없는
    기존 seed 항목/필드는 보존한다.

    exit_code: 0 성공 / 1 입력 오류."""
    if not cluster_map_path.is_file():
        print(f"[seed_backfill] ERROR: cluster_map 파일 없음: {cluster_map_path}",
              file=sys.stderr)
        return 1, []

    try:
        cluster_map = _load_json(cluster_map_path)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"[seed_backfill] ERROR: cluster_map 파싱 실패: {exc}", file=sys.stderr)
        return 1, []

    fr_index = _read_fr_index(cluster_map)
    if not fr_index:
        print("[seed_backfill] WARN: cluster_map 에 fr_index 가 비어 있음 — "
              "먼저 cluster_identify 를 1회 실행하세요.", file=sys.stderr)

    seeds = _read_seeds(seeds_path)
    new_seeds, changes = backfill_seeds(fr_index, seeds, force=force)

    counts = _summarize(changes)
    written = counts.get("injected", 0) + counts.get("updated", 0)

    if dry_run:
        print(f"[seed_backfill] DRY-RUN: 주입예정 {counts.get('injected', 0)} · "
              f"갱신예정 {counts.get('updated', 0)} · "
              f"기존유지 {counts.get('skipped_existing', 0)} (쓰기 없음)")
        for c in changes:
            if c["action"] in ("injected", "updated"):
                info = fr_index.get(c["fr"], {})
                print(f"  - {c['action']}: {c['fr']} → "
                      f"capability={info.get('capability')} "
                      f"cluster_hint={info.get('cluster_id')}")
        return 0, changes

    seeds_path.parent.mkdir(parents=True, exist_ok=True)
    seeds_path.write_text(_dump_seeds(new_seeds), encoding="utf-8")

    print(f"[seed_backfill] OK: 주입 {counts.get('injected', 0)} · "
          f"갱신 {counts.get('updated', 0)} · "
          f"기존유지 {counts.get('skipped_existing', 0)} → {seeds_path}")
    return 0, changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cluster_seed_backfill",
        description="cluster_map.fr_index 씨앗을 사이드카 YAML 에 backfill (P5)",
    )
    parser.add_argument("--cluster-map", type=Path, required=True,
                        help="cluster_map.json (fr_index 보유)")
    parser.add_argument("--seeds", type=Path, required=True,
                        help="사이드카 requirements.seeds.yml (병합 대상)")
    parser.add_argument("--force", action="store_true",
                        help="이미 씨앗이 있는 FR 도 덮어쓰기")
    parser.add_argument("--dry-run", action="store_true",
                        help="변경 예정만 출력(쓰기 없음)")
    args = parser.parse_args(argv)

    code, _ = run_backfill(
        args.cluster_map,
        args.seeds,
        force=args.force,
        dry_run=args.dry_run,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
