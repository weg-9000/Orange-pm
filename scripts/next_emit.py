#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""next_emit — deterministic next-action recommender (work control · /next + viz operator).

Purpose:
    Aggregates in-flight work state (queues, status, DEC, deliverable presence)
    and **deterministically ranks** 1..N next actions. This is non-linear rather
    than a linear happy-path — it presents fix (unblock), backward (revise
    upstream deliverables), and forward (advance) directions together. No model
    involvement (not an LLM router — same deterministic philosophy as the
    gates/scanners). Read-only.

Ranking priority (highest first):
    1. fix     — resolve blocking gates (drift/policy-impact/mtg/bdd-coverage BLOCK)
    2. fix     — resolve pending DEC(⬜) (/dec-approve)
    3. backward— integrate UPSTREAM_GAP → revise upstream (D1/D5) (/draft-req)
    4. forward — advance based on phase/status (graph→fanout→write→review→confirm)

Contract: { kind: "next-actions", product, phase, phaseName, blockers,
        actions: [{ rank, direction, severity, label, cmd, arg, reason, source }] }

Usage:
    python next_emit.py --hub-root <Hub> --product <p> --emit-json
exit code: 0 ok / 1 no source (empty skeleton) / 2 argument error
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import _emit_common as C
import ssot_emit
import wo_emit

PHASE_NAMES = {-1: "Init", 0: "Graph", 1: "Fanout", 2: "Draft", 3: "Integrate", 4: "Publish"}

# ssot queue id → fix action mapping (cmd, reason label, revert direction description)
QUEUE_FIX = {
    "drift": ("/render", "common drift — full re-render required"),
    "policy-impact": ("/flow", "policy §change impact — affected screen needs re-reconciliation"),
    "mtg": ("/su", "meeting delegation not reflected — apply to screen or clean up ledger"),
    "bdd-coverage": ("/bdd", "acceptance criteria not covered (missing 4-state / stale feature) — /flow then /bdd"),
    "fr-cluster": ("/lc", "FR↔cluster traceability mismatch — reinforce draft fr_refs or re-cluster with cluster_identify then integrate"),
}

# If fr-cluster queue WARN (orphan/unmapped) is at or above this threshold, recommend seed backfill (forward).
FRC_BACKFILL_WARN_THRESHOLD = 3
DEC_PENDING_ROW = re.compile(r"^\|\s*DEC-\d+\b.*\|\s*⬜\s*\|", re.M)


def count_pending_dec(decisions_text: str) -> int:
    """Number of pending (⬜) rows in the decisions.md DEC table."""
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
    """Detect the authoring track (fix-plan-track-routing P3).

    "A" (cluster/dossier) / "legacy" (section) / None (undetermined).
    project-mode.json takes priority; if absent, checks cluster signals
    (cidx / cluster_map / dossier draft). If neither exists and only a
    legacy index is present, returns legacy.
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
    """One forward action based on phase/status (None if none applies)."""
    if not has_graph:
        return {"direction": "forward", "severity": "INFO", "label": "Generate graph",
                "cmd": "/graph-gen", "arg": product, "reason": "graph.json not generated — generate clusters/topology", "source": "phase"}
    if not has_wo:
        if track == "A":
            return {"direction": "forward", "severity": "INFO", "label": "Generate cluster WOs",
                    "cmd": "/fanout", "arg": f"{product} --cluster-mode",
                    "reason": "WOs not generated (Track A) — run cluster_identify first, then cluster-mode fanout", "source": "phase"}
        return {"direction": "forward", "severity": "INFO", "label": "Generate Work Orders",
                "cmd": "/fanout", "arg": product, "reason": "WOs not generated — fanout required", "source": "phase"}
    if counts["empty"] > 0:
        it = _first_of_status(items, "empty") or {}
        t = it.get("type", "policy")
        cmd = "/write-cluster" if t == "cluster" else "/flow" if t == "screen" else "/write"
        arg = product if t == "cluster" else (it.get("woId") or product)
        return {"direction": "forward", "severity": "INFO", "label": "Write draft",
                "cmd": cmd, "arg": arg, "reason": f"{counts['empty']} not-written (empty) — write content", "source": "status"}
    if counts["ai-draft"] > 0:
        return {"direction": "forward", "severity": "INFO", "label": "Review draft",
                "cmd": "/review", "arg": product, "reason": f"{counts['ai-draft']} ai-draft — PM review required", "source": "status"}
    if counts["human-reviewed"] > 0:
        return {"direction": "forward", "severity": "INFO", "label": "Freeze",
                "cmd": "/confirm", "arg": product, "reason": f"{counts['human-reviewed']} human-reviewed — ready to freeze", "source": "status"}
    if counts["frozen"] > 0:
        return {"direction": "forward", "severity": "INFO", "label": "Publish",
                "cmd": "/render", "arg": f"{product} --push", "reason": "frozen — publish to Confluence", "source": "status"}
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
    """Pure function (for tests) — signal collection → ranked next-action contract."""
    counts = _status_counts(wo_items)
    total_block = ssot.get("totals", {}).get("block", 0)
    actions: list[dict] = []

    # 0. fix — track confusion (fix-plan-track-routing P3): Track A but a legacy
    #    section/screen WO index (index.json) also exists → suspected mis-routed
    #    output. Surface this as the top-priority cleanup notice.
    if track == "A" and legacy_index_present:
        actions.append({"direction": "fix", "severity": "WARN", "label": "Resolve track confusion",
                        "cmd": "/plan-audit", "arg": product,
                        "reason": "Track A (dossier) but a legacy WO index.json also exists — "
                                  "possible mis-routed output. Confirm the track, then archive the confused WOs",
                        "source": "track"})

    # 1. fix — blocking queues (ssot aggregation order: drift>policy-impact>mtg>bdd-coverage)
    for q in ssot.get("queues", []):
        if q.get("block", 0) > 0 and q["id"] in QUEUE_FIX:
            cmd, reason = QUEUE_FIX[q["id"]]
            actions.append({"direction": "fix", "severity": "BLOCK", "label": f"Resolve {q['title']}",
                            "cmd": cmd, "arg": product, "reason": f"{reason} ({q['block']})", "source": q["id"]})

    # 2. fix — pending DEC
    if dec_pending > 0:
        actions.append({"direction": "fix", "severity": "WARN", "label": "Resolve DEC approvals",
                        "cmd": "/dec-approve", "arg": product, "reason": f"{dec_pending} pending DEC decision(s) exist — resolve before /confirm", "source": "decisions"})

    # 2b. forward — many untagged FRs (fr-cluster WARN: orphan/unmapped) → seed backfill
    frc_q = next((q for q in ssot.get("queues", []) if q.get("id") == "fr-cluster"), None)
    frc_warn = frc_q.get("warn", 0) if frc_q else 0
    if frc_warn >= FRC_BACKFILL_WARN_THRESHOLD:
        actions.append({"direction": "forward", "severity": "INFO", "label": "FR seed backfill",
                        "cmd": "/graph-gen", "arg": f"{product} --backfill-seeds",
                        "reason": f"{frc_warn} untagged/unmapped FR(s) (orphan/unmapped) — reinforce capability seeds via cluster_seed_backfill",
                        "source": "fr-cluster"})

    # 3. backward — integrate UPSTREAM_GAP → revise upstream
    if integration_upstream_gap:
        actions.append({"direction": "backward", "severity": "WARN", "label": "Revise upstream deliverable",
                        "cmd": "/draft-req", "arg": f"{product} --upstream-feedback", "reason": "integrate UPSTREAM_GAP — D1/D5 needs reinforcement", "source": "integrate"})

    # 4. forward — advance by phase/status (meaningful when nothing is blocking; still included for reference otherwise)
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
        sys.stderr.write("--hub-root, --product required\n")
        return 2

    pdir = C.product_dir(args.hub_root, args.product)
    rdir = pdir / "reports"

    def read_queue(fname: str):
        p = rdir / fname
        return p.read_text(encoding="utf-8") if p.exists() else None

    ssot = ssot_emit.transform_ssot(read_queue, args.product)

    # WO items (node index.json first, cluster_index.json otherwise) — reuses wo_emit
    wo = wo_emit.main  # noqa (built directly rather than called indirectly)
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

    # integrate UPSTREAM_GAP — when the UPSTREAM_GAP marker is present in integration-summary.md's header
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
