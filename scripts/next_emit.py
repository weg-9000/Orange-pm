#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""next_emit — 다음 행동 결정적 추천기 (작업 관제 · /next + viz operator).

목적:
    진행 중 작업 상태(큐·status·DEC·산출물 존재)를 모아 다음 행동 1~N개를
    **결정적으로 랭킹**한다. 선형 happy-path 가 아니라 비선형 — fix(차단 해소)·
    backward(상위 산출물 역류)·forward(전진) 방향을 함께 제시한다. 모델 미관여
    (LLM 라우터 아님 — 게이트/스캐너와 동일 결정적 철학). 읽기 전용.

랭킹 우선순위 (높은 순):
    1. fix     — 차단 게이트(drift/policy-impact/mtg/bdd-coverage BLOCK) 해소
    2. fix     — 미승인 DEC(⬜) 정리 (/dec-approve)
    3. backward— integrate UPSTREAM_GAP → 상위(D1/D5) 리비전 (/draft-req)
    4. forward — phase·status 기반 전진 (graph→fanout→write→review→confirm)

계약: { kind: "next-actions", product, phase, phaseName, blockers,
        actions: [{ rank, direction, severity, label, cmd, arg, reason, source }] }

사용법:
    python next_emit.py --hub-root <Hub> --product <p> --emit-json
exit code: 0 정상 / 1 원본 없음(빈 골격) / 2 인자 오류
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import _emit_common as C
import ssot_emit
import wo_emit

PHASE_NAMES = {-1: "Init", 0: "Graph", 1: "Fanout", 2: "Draft", 3: "Integrate", 4: "Publish"}

# ssot 큐 id → fix 행동 매핑 (cmd, 사유 라벨, 복귀 방향 설명)
QUEUE_FIX = {
    "drift": ("/render", "공통 drift — 완전판 재-render 필요"),
    "policy-impact": ("/flow", "정책 §변경 영향 — 해당 화면 재정합 필요"),
    "mtg": ("/su", "회의 위임 미반영 — 화면 반영 또는 원장 정리"),
    "bdd-coverage": ("/bdd", "수용 기준 미커버(4-state 누락·feature stale) — /flow 후 /bdd"),
    "fr-cluster": ("/lc", "FR↔cluster 추적성 불일치(mismatch) — draft fr_refs 보강 또는 cluster_identify 재군집 후 통합"),
}

# fr-cluster 큐 WARN(orphan/unmapped) 이 임계 이상이면 씨앗 backfill 권고(forward).
FRC_BACKFILL_WARN_THRESHOLD = 3
DEC_PENDING_ROW = re.compile(r"^\|\s*DEC-\d+\b.*\|\s*⬜\s*\|", re.M)


def count_pending_dec(decisions_text: str) -> int:
    """decisions.md DEC 표에서 미승인(⬜) 행 수."""
    return len(DEC_PENDING_ROW.findall(decisions_text or ""))


def _status_counts(items: list[dict]) -> dict[str, int]:
    out = {"empty": 0, "ai-draft": 0, "human-reviewed": 0, "frozen": 0}
    for it in items:
        s = it.get("status", "empty")
        if s in out:
            out[s] += 1
    return out


def _first_of_status(items: list[dict], status: str) -> dict | None:
    return next((it for it in items if it.get("status") == status), None)


def _detect_track(pdir, idx, cidx) -> str | None:
    """작성 트랙을 감지한다 (fix-plan-track-routing P3).

    "A" (cluster/dossier) / "legacy" (section) / None(미정).
    project-mode.json 을 1순위로, 없으면 cluster 신호(cidx·cluster_map·dossier draft)를
    본다. 둘 다 없고 legacy index 만 있으면 legacy.
    """
    import json
    mode_path = pdir / "graph" / "project-mode.json"
    if mode_path.exists():
        try:
            mode = json.loads(mode_path.read_text(encoding="utf-8"))
        except Exception:
            mode = {}
        if str(mode.get("track", "")).upper() == "A" or mode.get("model") == "dossier":
            return "A"
    if cidx.exists() or (pdir / "graph" / "cluster_map.json").exists():
        return "A"
    if (pdir / "drafts").exists() and any((pdir / "drafts").glob("cluster_*.draft.md")):
        return "A"
    if idx.exists():
        return "legacy"
    return None


def _forward_action(items, counts, has_graph, has_wo, product, track=None) -> dict | None:
    """phase·status 기반 전진 행동 1개(없으면 None)."""
    if not has_graph:
        return {"direction": "forward", "severity": "INFO", "label": "그래프 생성",
                "cmd": "/graph-gen", "arg": product, "reason": "graph.json 미생성 — 군집·위상 생성", "source": "phase"}
    if not has_wo:
        if track == "A":
            return {"direction": "forward", "severity": "INFO", "label": "Cluster WO 생성",
                    "cmd": "/fanout", "arg": f"{product} --cluster-mode",
                    "reason": "WO 미생성 (Track A) — cluster_identify 선행 후 cluster-mode fanout", "source": "phase"}
        return {"direction": "forward", "severity": "INFO", "label": "Work Order 생성",
                "cmd": "/fanout", "arg": product, "reason": "WO 미생성 — fanout 필요", "source": "phase"}
    if counts["empty"] > 0:
        it = _first_of_status(items, "empty") or {}
        t = it.get("type", "policy")
        cmd = "/write-cluster" if t == "cluster" else "/flow" if t == "screen" else "/write"
        arg = product if t == "cluster" else (it.get("woId") or product)
        return {"direction": "forward", "severity": "INFO", "label": "초안 작성",
                "cmd": cmd, "arg": arg, "reason": f"미작성(empty) {counts['empty']}건 — 본문 작성", "source": "status"}
    if counts["ai-draft"] > 0:
        return {"direction": "forward", "severity": "INFO", "label": "초안 검토",
                "cmd": "/review", "arg": product, "reason": f"ai-draft {counts['ai-draft']}건 — PM 검토 필요", "source": "status"}
    if counts["human-reviewed"] > 0:
        return {"direction": "forward", "severity": "INFO", "label": "확정(freeze)",
                "cmd": "/confirm", "arg": product, "reason": f"human-reviewed {counts['human-reviewed']}건 — 동결 가능", "source": "status"}
    if counts["frozen"] > 0:
        return {"direction": "forward", "severity": "INFO", "label": "발행",
                "cmd": "/render", "arg": f"{product} --push", "reason": "frozen — Confluence 발행", "source": "status"}
    return None


def _estimate_phase(has_graph, has_wo, counts, total_block) -> int:
    if not has_graph:
        return 0
    if not has_wo:
        return 1
    if counts["empty"] > 0 or counts["ai-draft"] > 0:
        return 2
    if total_block > 0 or counts["human-reviewed"] > 0:
        return 3
    return 4


def transform_next(product: str, ssot: dict, wo_items: list[dict], dec_pending: int,
                   has_graph: bool, has_wo: bool, integration_upstream_gap: bool = False,
                   track: str | None = None, legacy_index_present: bool = False) -> dict:
    """순수 함수(테스트용) — 신호 모음 → 랭킹된 다음 행동 계약."""
    counts = _status_counts(wo_items)
    total_block = ssot.get("totals", {}).get("block", 0)
    actions: list[dict] = []

    # 0. fix — 트랙 혼선 (fix-plan-track-routing P3): Track A 인데 legacy section/screen
    #    WO 인덱스(index.json)가 공존 → 오라우팅 산출물 의심. 최우선 정리 안내.
    if track == "A" and legacy_index_present:
        actions.append({"direction": "fix", "severity": "WARN", "label": "트랙 혼선 정리",
                        "cmd": "/plan-audit", "arg": product,
                        "reason": "Track A(dossier)인데 legacy WO index.json 공존 — "
                                  "오라우팅 산출물 가능. 트랙 확정 후 혼선 WO 아카이브",
                        "source": "track"})

    # 1. fix — 차단 큐 (ssot 집계 순서: drift>policy-impact>mtg>bdd-coverage)
    for q in ssot.get("queues", []):
        if q.get("block", 0) > 0 and q["id"] in QUEUE_FIX:
            cmd, reason = QUEUE_FIX[q["id"]]
            actions.append({"direction": "fix", "severity": "BLOCK", "label": f"{q['title']} 해소",
                            "cmd": cmd, "arg": product, "reason": f"{reason} ({q['block']}건)", "source": q["id"]})

    # 2. fix — 미승인 DEC
    if dec_pending > 0:
        actions.append({"direction": "fix", "severity": "WARN", "label": "DEC 승인 정리",
                        "cmd": "/dec-approve", "arg": product, "reason": f"미승인 DEC(⬜) {dec_pending}건 — /confirm 전 해소", "source": "decisions"})

    # 2b. forward — 무태그 FR 다수(fr-cluster WARN: orphan/unmapped) → 씨앗 backfill
    frc_q = next((q for q in ssot.get("queues", []) if q.get("id") == "fr-cluster"), None)
    frc_warn = frc_q.get("warn", 0) if frc_q else 0
    if frc_warn >= FRC_BACKFILL_WARN_THRESHOLD:
        actions.append({"direction": "forward", "severity": "INFO", "label": "FR 씨앗 backfill",
                        "cmd": "/graph-gen", "arg": f"{product} --backfill-seeds",
                        "reason": f"무태그/미매핑 FR(orphan·unmapped) {frc_warn}건 — cluster_seed_backfill 로 capability 씨앗 보강",
                        "source": "fr-cluster"})

    # 3. backward — integrate UPSTREAM_GAP → 상위 리비전
    if integration_upstream_gap:
        actions.append({"direction": "backward", "severity": "WARN", "label": "상위 산출물 리비전",
                        "cmd": "/draft-req", "arg": f"{product} --upstream-feedback", "reason": "integrate UPSTREAM_GAP — D1/D5 보강 필요", "source": "integrate"})

    # 4. forward — phase·status 전진 (차단 없을 때 의미 — 있어도 참고용으로 1건)
    fwd = _forward_action(wo_items, counts, has_graph, has_wo, product, track)
    if fwd:
        actions.append(fwd)

    for i, a in enumerate(actions, 1):
        a["rank"] = i

    phase = _estimate_phase(has_graph, has_wo, counts, total_block)
    blockers = sum(1 for a in actions if a["direction"] in ("fix", "backward"))
    return {
        "kind": "next-actions", "product": product,
        "phase": phase, "phaseName": PHASE_NAMES.get(phase, "?"),
        "blockers": blockers, "statusCounts": counts, "actions": actions,
    }


def main(argv: list[str]) -> int:
    args = C.make_parser("next").parse_args(argv)
    if args.from_fixture:
        return C.emit(C.load_fixture(args.from_fixture))
    if not (args.hub_root and args.product):
        sys.stderr.write("--hub-root, --product 필요\n")
        return 2

    pdir = C.product_dir(args.hub_root, args.product)
    rdir = pdir / "reports"

    def read_queue(fname: str):
        p = rdir / fname
        return p.read_text(encoding="utf-8") if p.exists() else None

    ssot = ssot_emit.transform_ssot(read_queue, args.product)

    # WO items (node index.json 우선, 없으면 cluster_index.json) — wo_emit 재사용
    wo = wo_emit.main  # noqa (간접 호출 대신 직접 구성)
    idx = pdir / "work-orders" / "index.json"
    cidx = pdir / "work-orders" / "cluster_index.json"
    has_wo = idx.exists() or cidx.exists()
    wo_items: list[dict] = []
    if has_wo:
        import json
        if idx.exists():
            records = wo_emit._records(json.loads(idx.read_text(encoding="utf-8")))
        else:
            records = wo_emit.normalize_cluster_records(json.loads(cidx.read_text(encoding="utf-8")))

        def status_of(wid: str) -> dict:
            rec = next((r for r in records if r.get("wo_id") == wid), {})
            dp = rec.get("draft_path") or f"drafts/{wid}.draft.md"
            f = pdir / dp
            return C.read_frontmatter(f.read_text(encoding="utf-8")) if f.exists() else {}

        wo_items = wo_emit.transform_wo(records, args.product, status_of)["items"]

    has_graph = (pdir / "graph" / "graph.json").exists() or (pdir / "graph" / "graph.clustered.json").exists()

    dec_p = pdir / "decisions.md"
    dec_pending = count_pending_dec(dec_p.read_text(encoding="utf-8")) if dec_p.exists() else 0

    # integrate UPSTREAM_GAP — integration-summary.md 헤더에 UPSTREAM_GAP 마커 존재 시
    isum = pdir / "reports" / "integration-summary.md"
    upstream = False
    if isum.exists():
        upstream = "UPSTREAM_GAP" in isum.read_text(encoding="utf-8")[:2000]

    track = _detect_track(pdir, idx, cidx)
    legacy_index_present = idx.exists()
    result = transform_next(args.product, ssot, wo_items, dec_pending, has_graph, has_wo,
                            upstream, track, legacy_index_present)
    code = 0 if (has_graph or has_wo or result["actions"]) else 1
    C.emit(result)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
