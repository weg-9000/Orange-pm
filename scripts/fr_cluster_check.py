#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FR ↔ cluster 추적성 게이트 (P4, docs/fr-cluster-alignment.md).

목적:
    요구사항(FR) · 군집(cluster_map.fr_index) · cluster draft(fr_refs) 3자가
    하나의 키(capability/cluster_id)로 일관되게 관통되는지(DEC-A/DEC-D) 결정적으로
    검증한다. 씨앗 누락(orphan) · 미매핑(unmapped) 은 WARN(비차단)으로, fr_index ↔
    cluster draft fr_refs 불일치(mismatch) 는 BLOCK(차단)으로 적발한다.
    순수 스크립트(모델 미관여) — requirements·cluster_map·draft 를 수정하지 않는다.

판정 (gates/fr-cluster-trace-gate.md SSoT):
    orphan FR  : FR 이 requirements 에 있으나 capability 씨앗도 없고 fr_index 에도
                 없음 → WARN
    unmapped FR: FR 이 requirements 에 있으나 fr_index 에 없음(씨앗만 있음) → WARN
    mismatch   : (a) fr_index 가 FR→cluster X 로 매핑하는데 X 의 cluster draft 가
                 그 FR 을 fr_refs 에 안 실음, 또는 (b) 어떤 cluster draft 가
                 fr_refs 에 실은 FR 이 fr_index 에서 다른 cluster 로 매핑되거나
                 어디에도 매핑 안 됨 → BLOCK

종료 코드:
    0  clean (WARN-only 포함 — WARN 은 차단하지 않음)
    2  BLOCK 1건 이상
    1  입력 오류(파일 없음 등) — graceful, 절대 예외로 죽지 않음

CLI:
    python fr_cluster_check.py \
        --requirements PROJECTS/{p}/inputs/requirements.md \
        --cluster-map  PROJECTS/{p}/graph/cluster_map.json \
        --drafts-dir   PROJECTS/{p}/drafts \
        [--seeds PROJECTS/{p}/inputs/requirements.seeds.yml] \
        [--report PROJECTS/{p}/reports/fr-cluster-trace-queue.md] \
        [--queue  PROJECTS/{p}/reports/fr-cluster-queue.md]

큐 출력(--queue):
    viz status 어댑터(ssot_emit.py)가 집계하는 `reports/fr-cluster-queue.md` 를
    쓴다. 보고서(--report)와 동일한 render_report 양식이며, 헤더의
    `> **BLOCK: N · WARN: M**` 라인을 ssot_emit 이 BLOCK/WARN 등가로 흡수한다
    (drift/policy-impact/mtg/bdd-coverage 큐와 동일 메커니즘).

씨앗 출처:
    capability 씨앗은 requirements.md 인라인 HTML-주석 태그가 아니라 **사이드카**
    `requirements.seeds.yml`(requirements.md 와 같은 디렉터리) 에서 읽는다.
    top-level map `FR-ID → {capability, cluster_hint?, lock?}`. FR 이 씨앗을
    가진다 ⇔ seeds 에 키로 존재하고 `capability` 가 비어있지 않다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - yaml 부재 시 graceful
    yaml = None  # type: ignore

# FR ID: FR-[섹션][순번][-하위] (cluster_seed_backfill.py 와 동일 규약)
# requirements 테이블 행의 선두 셀에 등장하는 FR ID 만 그 행의 주체로 본다.
_ROW_FR_RE = re.compile(r"^\s*\|\s*\*{0,2}(FR-\d+(?:-\d+)*)\*{0,2}\s*\|")

# cluster draft frontmatter 의 fr_refs YAML 리스트 안에 등장하는 FR ID
_FR_ID_RE = re.compile(r"FR-\d+(?:-\d+)*")


# ── 순수 파서 헬퍼 (I/O 없음) ─────────────────────────────────────────────
def parse_fr_ids(md_text: str) -> list[str]:
    """requirements 본문에서 FR 행(테이블 선두 셀)을 파싱해 FR universe 를 반환.

    씨앗 정보는 더 이상 여기서 추론하지 않는다(사이드카 yml 로 이동).

    Returns:
        [FR-ID, ...] — 등장 순서 보존, 중복 제거.

    예외를 던지지 않는다(graceful). 비문자열 입력은 빈 리스트로 처리."""
    out: list[str] = []
    if not isinstance(md_text, str):
        return out
    seen: set[str] = set()
    for line in md_text.splitlines():
        m = _ROW_FR_RE.match(line)
        if not m:
            continue
        fr = m.group(1)
        if fr not in seen:
            seen.add(fr)
            out.append(fr)
    return out


def read_seeds(seeds_path: Path) -> dict[str, dict]:
    """사이드카 requirements.seeds.yml 을 읽어 {FR-ID: {capability, ...}} 반환.

    top-level map 만 받아들이며, 값이 dict 가 아니면 건너뛴다. 파일 부재·손상·
    yaml 부재 등 어떤 경우에도 예외를 던지지 않고 빈 dict 로 graceful 처리."""
    if yaml is None:
        return {}
    try:
        if not seeds_path.is_file():
            return {}
        raw = yaml.safe_load(seeds_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for fr, info in raw.items():
        if isinstance(info, dict):
            out[str(fr)] = info
    return out


def seeded_set(seeds: dict[str, dict]) -> set[str]:
    """seeds dict → 씨앗을 가진 FR 집합. capability 가 truthy(비어있지 않음)여야 함."""
    out: set[str] = set()
    if not isinstance(seeds, dict):
        return out
    for fr, info in seeds.items():
        if isinstance(info, dict) and str(info.get("capability") or "").strip():
            out.add(str(fr))
    return out


def read_fr_index(cluster_map: Any) -> dict[str, dict]:
    """cluster_map 에서 fr_index(FR→{capability,cluster_id}) 추출 (graceful).

    포맷이 어긋나면 빈 dict 를 반환(예외 금지 — cluster_seed_backfill 과 동일 정책)."""
    if not isinstance(cluster_map, dict):
        return {}
    raw = cluster_map.get("fr_index")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for fr, info in raw.items():
        if isinstance(info, dict):
            out[str(fr)] = info
    return out


def parse_cluster_fr_refs(draft_text: str) -> tuple[str | None, list[str]]:
    """cluster draft 1개에서 (cluster_id, fr_refs) 추출 (graceful).

    cluster_id 는 frontmatter 의 `cluster_id:` 값(cluster 블록 또는 top-level)을 읽고,
    fr_refs 는 `fr_refs:` 리스트 블록 안의 FR ID 들을 수집한다. 정규식 기반이라
    YAML 라이브러리 의존이 없으며 어떤 입력이든 예외를 던지지 않는다.

    Returns:
        (cluster_id 또는 None, [FR-ID, ...])"""
    if not isinstance(draft_text, str):
        return None, []

    cluster_id: str | None = None
    cid_m = re.search(
        r'(?m)^\s*cluster_id\s*:\s*"?([A-Za-z0-9][A-Za-z0-9-]*)"?\s*$', draft_text
    )
    if cid_m:
        cluster_id = cid_m.group(1).strip()

    fr_refs: list[str] = []
    lines = draft_text.splitlines()
    in_block = False
    block_indent = 0
    for line in lines:
        stripped = line.strip()
        if not in_block:
            if re.match(r"^\s*fr_refs\s*:", line):
                in_block = True
                block_indent = len(line) - len(line.lstrip())
                # 인라인 리스트 (fr_refs: ["FR-1", "FR-2"]) 도 흡수
                inline = line.split(":", 1)[1]
                fr_refs.extend(_FR_ID_RE.findall(inline))
            continue
        # 블록 내부 — `- "FR-..."` 형태의 항목만 수집
        if stripped.startswith("- ") or stripped.startswith("-\t"):
            fr_refs.extend(_FR_ID_RE.findall(line))
            continue
        # 들여쓰기가 fr_refs 키 수준 이하인 새 키를 만나면 블록 종료
        cur_indent = len(line) - len(line.lstrip())
        if stripped and cur_indent <= block_indent and ":" in stripped:
            in_block = False
            continue
        # 빈 줄·주석은 블록 유지
        if not stripped or stripped.startswith("#"):
            continue
        # 그 외 들여쓴 비리스트 라인은 블록 종료로 간주
        if cur_indent <= block_indent:
            in_block = False

    # 중복 제거(순서 보존)
    seen: set[str] = set()
    uniq = [f for f in fr_refs if not (f in seen or seen.add(f))]
    return cluster_id, uniq


# ── Finding 모델 + 순수 검사 로직 ─────────────────────────────────────────
@dataclass(frozen=True)
class Finding:
    """추적성 위반 1건. level ∈ {BLOCK, WARN}."""

    level: str   # "BLOCK" | "WARN"
    fr: str
    reason: str


def check_traceability(
    fr_ids: list[str],
    seeded: set[str],
    fr_index: dict[str, dict],
    cluster_fr_refs: dict[str, list[str]],
) -> list[Finding]:
    """FR ↔ cluster 추적성 검사 (순수 함수 — I/O 없음).

    Args:
        fr_ids: [FR-ID, ...] — requirements 에서 파싱한 FR universe.
        seeded: {FR-ID, ...} — 사이드카 seeds yml 에 capability 씨앗을 가진 FR 집합.
        fr_index: {FR-ID: {capability, cluster_id}} — cluster_map 권위 매핑.
        cluster_fr_refs: {cluster_id: [FR-ID, ...]} — cluster draft 들의 fr_refs.

    Returns:
        Finding 리스트 (정렬됨: level BLOCK 먼저, 그 다음 FR).

    판정(gates/fr-cluster-trace-gate.md):
        orphan(WARN) / unmapped(WARN) / mismatch(BLOCK, 양방향)."""
    findings: list[Finding] = []

    fr_ids = fr_ids or []
    seeded = seeded or set()
    fr_index = fr_index or {}
    cluster_fr_refs = cluster_fr_refs or {}

    # FR → 그 FR 을 fr_refs 에 실은 cluster_id 들 (역인덱스)
    fr_to_draft_clusters: dict[str, list[str]] = {}
    for cid, refs in cluster_fr_refs.items():
        for fr in refs or []:
            fr_to_draft_clusters.setdefault(fr, []).append(cid)

    # ── requirements FR 기준: orphan / unmapped ──────────────────────────
    for fr in fr_ids:
        has_seed = fr in seeded
        in_index = fr in fr_index
        if not in_index and not has_seed:
            findings.append(Finding(
                "WARN", fr,
                "orphan — capability 씨앗 없음 + fr_index 미등록 "
                "(cluster_identify/seed_backfill 미실행)",
            ))
        elif not in_index:
            findings.append(Finding(
                "WARN", fr,
                "unmapped — capability 씨앗은 있으나 fr_index 미등록 "
                "(cluster_identify 재실행 필요)",
            ))

    # ── 방향 (a): fr_index 매핑 ↔ cluster draft fr_refs 누락 → BLOCK ──────
    for fr, info in fr_index.items():
        cid = str(info.get("cluster_id") or "").strip()
        if not cid:
            continue
        draft_clusters = fr_to_draft_clusters.get(fr, [])
        if cid not in draft_clusters:
            if cid not in cluster_fr_refs:
                # 매핑된 cluster 의 draft 자체가 없으면 검사 대상에서 제외(부분 검증).
                # draft 가 존재하는데 누락된 경우만 BLOCK 으로 본다.
                continue
            findings.append(Finding(
                "BLOCK", fr,
                f"mismatch — fr_index 는 {fr}→{cid} 인데 {cid} cluster draft 의 "
                f"fr_refs 에 {fr} 가 없음 (draft fr_refs 보강 필요)",
            ))

    # ── 방향 (b): cluster draft fr_refs ↔ fr_index 불일치 → BLOCK ────────
    for cid, refs in cluster_fr_refs.items():
        for fr in refs or []:
            info = fr_index.get(fr)
            if info is None:
                findings.append(Finding(
                    "BLOCK", fr,
                    f"mismatch — {cid} cluster draft 가 fr_refs 에 {fr} 를 실었으나 "
                    f"fr_index 에 {fr} 매핑이 없음 (draft 오참조 또는 cluster_identify 누락)",
                ))
                continue
            mapped = str(info.get("cluster_id") or "").strip()
            if mapped and mapped != cid:
                findings.append(Finding(
                    "BLOCK", fr,
                    f"mismatch — {cid} cluster draft 가 fr_refs 에 {fr} 를 실었으나 "
                    f"fr_index 는 {fr}→{mapped} (다른 cluster) 로 매핑 (경계 충돌)",
                ))

    # 결정성: BLOCK 먼저, 같은 level 내 FR·reason 정렬, 중복 제거
    seen: set[tuple[str, str, str]] = set()
    uniq: list[Finding] = []
    for f in findings:
        key = (f.level, f.fr, f.reason)
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    level_order = {"BLOCK": 0, "WARN": 1}
    uniq.sort(key=lambda f: (level_order.get(f.level, 9), f.fr, f.reason))
    return uniq


def exit_code_for(findings: list[Finding]) -> int:
    """판정 → 종료 코드. BLOCK 1건 이상이면 2, 아니면 0(WARN-only 포함)."""
    return 2 if any(f.level == "BLOCK" for f in findings) else 0


# ── 보고서 (큐 스타일 markdown) ──────────────────────────────────────────
def render_report(findings: list[Finding], *, product: str | None = None) -> str:
    """findings 를 큐 스타일 markdown 으로 렌더(bdd-coverage-queue.md 양식 차용)."""
    blocks = sum(1 for f in findings if f.level == "BLOCK")
    warns = sum(1 for f in findings if f.level == "WARN")
    title = f"# fr-cluster-trace-queue{' — ' + product if product else ''}"
    lines = [
        title,
        "",
        f"> 생성: {datetime.now().isoformat(timespec='seconds')} · "
        f"fr_cluster_check.py (수정 금지)",
        f"> **BLOCK: {blocks} · WARN: {warns}**",
        "",
        "| FR | 등급 | 사유 |",
        "|---|---|---|",
    ]
    if findings:
        for f in findings:
            lines.append(f"| {f.fr} | **{f.level}** | {f.reason} |")
    else:
        lines.append("| _(추적성 위반 없음)_ | OK | FR↔cluster 일관 |")
    lines += [
        "",
        "## 처리 기준 (gates/fr-cluster-trace-gate.md)",
        "- orphan(WARN): capability 씨앗 + fr_index 부재 → "
        "/draft-req 씨앗 기입 또는 cluster_identify 실행 (비차단)",
        "- unmapped(WARN): 씨앗은 있으나 fr_index 부재 → cluster_identify 재실행 (비차단)",
        "- mismatch(BLOCK): fr_index ↔ cluster draft fr_refs 불일치 → "
        "draft fr_refs 보강 또는 cluster_identify 재군집 (차단)",
    ]
    return "\n".join(lines) + "\n"


# ── 파일 I/O 래퍼 ────────────────────────────────────────────────────────
def _load_drafts_fr_refs(drafts_dir: Path) -> dict[str, list[str]]:
    """drafts/ 의 cluster draft 들에서 {cluster_id: [FR-ID,...]} 수집 (graceful).

    cluster_id 가 없는 draft·파싱 실패 파일은 건너뛴다(예외 금지)."""
    result: dict[str, list[str]] = {}
    if not drafts_dir.is_dir():
        return result
    for path in sorted(drafts_dir.glob("*.draft.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        cid, refs = parse_cluster_fr_refs(text)
        if not cid:
            continue
        merged = result.setdefault(cid, [])
        for fr in refs:
            if fr not in merged:
                merged.append(fr)
    return result


def run_check(
    requirements_path: Path,
    cluster_map_path: Path,
    drafts_dir: Path,
    *,
    seeds_path: Path | None = None,
    report_path: Path | None = None,
    queue_path: Path | None = None,
    product: str | None = None,
) -> tuple[int, list[Finding]]:
    """파일 I/O 래퍼. (exit_code, findings) 반환.

    씨앗은 사이드카 seeds yml 에서 읽는다. seeds_path 가 None 이면
    requirements_path 의 형제 `requirements.seeds.yml` 로 기본 설정.

    queue_path 가 주어지면 viz status 어댑터(ssot_emit.py)가 집계하는
    `fr-cluster-queue.md` 를 render_report 양식으로 쓴다(헤더의
    `**BLOCK: N · WARN: M**` 가 ssot 에서 BLOCK/WARN 등가로 흡수됨).
    report_path 와 queue_path 는 동일 양식이며 독립적으로 쓸 수 있다.

    exit_code: 0 clean(WARN-only 포함) / 2 BLOCK / 1 입력 오류.
    절대 예외로 죽지 않는다 — 손상 입력은 graceful 하게 빈 결과로 흡수."""
    if not requirements_path.is_file():
        print(f"[fr_cluster_check] ERROR: requirements 파일 없음: {requirements_path}",
              file=sys.stderr)
        return 1, []
    if not cluster_map_path.is_file():
        print(f"[fr_cluster_check] ERROR: cluster_map 파일 없음: {cluster_map_path}",
              file=sys.stderr)
        return 1, []
    if not drafts_dir.is_dir():
        print(f"[fr_cluster_check] ERROR: drafts 디렉터리 없음: {drafts_dir}",
              file=sys.stderr)
        return 1, []

    try:
        md_text = requirements_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"[fr_cluster_check] ERROR: requirements 읽기 실패: {exc}", file=sys.stderr)
        return 1, []

    cluster_map: Any = {}
    try:
        cluster_map = json.loads(cluster_map_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        # 손상 cluster_map → 빈 fr_index 로 graceful 처리(차단 아님, WARN 만 산출 가능)
        print(f"[fr_cluster_check] WARN: cluster_map 파싱 실패 — 빈 fr_index 로 진행: {exc}",
              file=sys.stderr)
        cluster_map = {}

    if seeds_path is None:
        seeds_path = requirements_path.parent / "requirements.seeds.yml"

    fr_ids = parse_fr_ids(md_text)
    seeds = read_seeds(seeds_path)
    seeded = seeded_set(seeds)
    fr_index = read_fr_index(cluster_map)
    cluster_fr_refs = _load_drafts_fr_refs(drafts_dir)

    findings = check_traceability(fr_ids, seeded, fr_index, cluster_fr_refs)
    code = exit_code_for(findings)

    rendered = render_report(findings, product=product)
    for out_path, label in ((report_path, "보고서"), (queue_path, "큐")):
        if out_path is None:
            continue
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            print(f"[fr_cluster_check] WARN: {label} 쓰기 실패: {exc}", file=sys.stderr)

    blocks = sum(1 for f in findings if f.level == "BLOCK")
    warns = sum(1 for f in findings if f.level == "WARN")
    print(f"[fr_cluster_check] BLOCK={blocks} WARN={warns} "
          f"(FR {len(fr_ids)} · seeded {len(seeded)} · fr_index {len(fr_index)} · "
          f"cluster draft {len(cluster_fr_refs)})"
          + ("" if blocks == 0 else " — fr-cluster-trace-gate 차단"))
    return code, findings


# ── 메인 ─────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fr_cluster_check",
        description="FR ↔ cluster 추적성 게이트 (P4, gates/fr-cluster-trace-gate.md)",
    )
    parser.add_argument("--requirements", type=Path, required=True,
                        help="입력 requirements.md (FR 테이블)")
    parser.add_argument("--cluster-map", type=Path, required=True,
                        help="cluster_map.json (fr_index 권위 매핑)")
    parser.add_argument("--drafts-dir", type=Path, required=True,
                        help="cluster draft 디렉터리 (*.draft.md, fr_refs 보유)")
    parser.add_argument("--seeds", type=Path, default=None,
                        help="사이드카 requirements.seeds.yml (생략 시 "
                             "requirements 형제 requirements.seeds.yml)")
    parser.add_argument("--report", type=Path, default=None,
                        help="큐 스타일 보고서 markdown 출력 경로")
    parser.add_argument("--queue", type=Path, default=None,
                        help="viz status 어댑터(ssot_emit.py) 집계용 큐 "
                             "(reports/fr-cluster-queue.md) 출력 경로")
    parser.add_argument("--product", default=None,
                        help="보고서 제목에 표기할 제품명(선택)")
    args = parser.parse_args(argv)

    code, _ = run_check(
        args.requirements,
        args.cluster_map,
        args.drafts_dir,
        seeds_path=args.seeds,
        report_path=args.report,
        queue_path=args.queue,
        product=args.product,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
