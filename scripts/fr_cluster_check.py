#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FR <-> cluster traceability gate (P4, docs/fr-cluster-alignment.md).

Purpose:
    Deterministically verify that requirements (FR), clusters
    (cluster_map.fr_index), and cluster drafts (fr_refs) stay consistent
    through a single key (capability/cluster_id) (DEC-A/DEC-D). Missing
    seeds (orphan) and unmapped FRs (unmapped) are flagged as WARN
    (non-blocking); a mismatch between fr_index and cluster draft fr_refs is
    flagged as BLOCK (blocking).
    Pure script (no model involvement) — never modifies requirements,
    cluster_map, or drafts.

Verdicts (gates/fr-cluster-trace-gate.md SSoT):
    orphan FR  : FR is in requirements but has neither a capability seed nor
                 an fr_index entry -> WARN
    unmapped FR: FR is in requirements but not in fr_index (seed only) -> WARN
    mismatch   : (a) fr_index maps FR->cluster X but X's cluster draft does
                 not carry that FR in fr_refs, or (b) a cluster draft carries
                 an FR in fr_refs that fr_index maps to a different cluster,
                 or to nothing at all -> BLOCK

Exit codes:
    0  clean (including WARN-only — WARN never blocks)
    2  one or more BLOCKs
    1  input error (file missing, etc.) — graceful, never crashes on an exception

CLI:
    python fr_cluster_check.py \
        --requirements PROJECTS/{p}/inputs/requirements.md \
        --cluster-map  PROJECTS/{p}/graph/cluster_map.json \
        --drafts-dir   PROJECTS/{p}/drafts \
        [--seeds PROJECTS/{p}/inputs/requirements.seeds.yml] \
        [--report PROJECTS/{p}/reports/fr-cluster-trace-queue.md] \
        [--queue  PROJECTS/{p}/reports/fr-cluster-queue.md]

Queue output (--queue):
    Writes `reports/fr-cluster-queue.md`, aggregated by the viz status
    adapter (ssot_emit.py). Uses the same render_report layout as the
    report (--report); ssot_emit absorbs the header line
    `> **BLOCK: N · WARN: M**` as BLOCK/WARN equivalents (the same
    mechanism as the drift/policy-impact/mtg/bdd-coverage queues).

Seed source:
    capability seeds are read from a **sidecar** `requirements.seeds.yml`
    (same directory as requirements.md), not from inline HTML-comment tags
    in requirements.md. Top-level map `FR-ID -> {capability, cluster_hint?,
    lock?}`. An FR has a seed iff it exists as a key in seeds and
    `capability` is non-empty.
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
except Exception:  # pragma: no cover - graceful when yaml is unavailable
    yaml = None  # type: ignore

# FR ID: FR-[section][seq][-sub] (same convention as cluster_seed_backfill.py)
# Only an FR ID appearing in the leading cell of a requirements table row is
# treated as that row's subject.
_ROW_FR_RE = re.compile(r"^\s*\|\s*\*{0,2}(FR-\d+(?:-\d+)*)\*{0,2}\s*\|")

# FR ID appearing inside a cluster draft frontmatter's fr_refs YAML list
_FR_ID_RE = re.compile(r"FR-\d+(?:-\d+)*")


# ── Pure parser helpers (no I/O) ──────────────────────────────────────────
def parse_fr_ids(md_text: str) -> list[str]:
    """Parse FR rows (table leading cell) from the requirements body and return the FR universe.

    Seed information is no longer inferred here (moved to the sidecar yml).

    Returns:
        [FR-ID, ...] — order of appearance preserved, deduplicated.

    Never raises (graceful). Non-string input is treated as an empty list."""
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
    """Read the sidecar requirements.seeds.yml and return {FR-ID: {capability, ...}}.

    Only a top-level map is accepted; values that aren't dicts are skipped.
    Never raises, regardless of a missing file, corrupt content, or missing
    yaml — always falls back gracefully to an empty dict."""
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
    """seeds dict -> set of FRs that have a seed. capability must be truthy (non-empty)."""
    out: set[str] = set()
    if not isinstance(seeds, dict):
        return out
    for fr, info in seeds.items():
        if isinstance(info, dict) and str(info.get("capability") or "").strip():
            out.add(str(fr))
    return out


def read_fr_index(cluster_map: Any) -> dict[str, dict]:
    """Extract fr_index (FR->{capability,cluster_id}) from cluster_map (graceful).

    Returns an empty dict on malformed input (no exceptions — same policy as
    cluster_seed_backfill)."""
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
    """Extract (cluster_id, fr_refs) from a single cluster draft (graceful).

    cluster_id is read from the frontmatter's `cluster_id:` value (either in
    the cluster block or at the top level); fr_refs collects the FR IDs
    found inside the `fr_refs:` list block. Regex-based, so it has no YAML
    library dependency and never raises on any input.

    Returns:
        (cluster_id or None, [FR-ID, ...])"""
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
                # Also absorb an inline list (fr_refs: ["FR-1", "FR-2"])
                inline = line.split(":", 1)[1]
                fr_refs.extend(_FR_ID_RE.findall(inline))
            continue
        # Inside the block — collect only `- "FR-..."`-style entries
        if stripped.startswith("- ") or stripped.startswith("-\t"):
            fr_refs.extend(_FR_ID_RE.findall(line))
            continue
        # A new key indented at or below the fr_refs key level ends the block
        cur_indent = len(line) - len(line.lstrip())
        if stripped and cur_indent <= block_indent and ":" in stripped:
            in_block = False
            continue
        # Blank lines/comments keep the block open
        if not stripped or stripped.startswith("#"):
            continue
        # Any other indented non-list line is treated as ending the block
        if cur_indent <= block_indent:
            in_block = False

    # Deduplicate (preserving order)
    seen: set[str] = set()
    uniq = [f for f in fr_refs if not (f in seen or seen.add(f))]
    return cluster_id, uniq


# ── Finding model + pure check logic ──────────────────────────────────────
@dataclass(frozen=True)
class Finding:
    """A single traceability violation. level ∈ {BLOCK, WARN}."""

    level: str   # "BLOCK" | "WARN"
    fr: str
    reason: str


def check_traceability(
    fr_ids: list[str],
    seeded: set[str],
    fr_index: dict[str, dict],
    cluster_fr_refs: dict[str, list[str]],
) -> list[Finding]:
    """FR <-> cluster traceability check (pure function — no I/O).

    Args:
        fr_ids: [FR-ID, ...] — FR universe parsed from requirements.
        seeded: {FR-ID, ...} — FRs that have a capability seed in the
            sidecar seeds yml.
        fr_index: {FR-ID: {capability, cluster_id}} — cluster_map's
            authoritative mapping.
        cluster_fr_refs: {cluster_id: [FR-ID, ...]} — fr_refs from cluster
            drafts.

    Returns:
        List of Findings (sorted: BLOCK level first, then FR).

    Verdicts (gates/fr-cluster-trace-gate.md):
        orphan(WARN) / unmapped(WARN) / mismatch(BLOCK, both directions)."""
    findings: list[Finding] = []

    fr_ids = fr_ids or []
    seeded = seeded or set()
    fr_index = fr_index or {}
    cluster_fr_refs = cluster_fr_refs or {}

    # FR -> the cluster_ids whose fr_refs carry that FR (reverse index)
    fr_to_draft_clusters: dict[str, list[str]] = {}
    for cid, refs in cluster_fr_refs.items():
        for fr in refs or []:
            fr_to_draft_clusters.setdefault(fr, []).append(cid)

    # ── Based on requirements FRs: orphan / unmapped ──────────────────────
    for fr in fr_ids:
        has_seed = fr in seeded
        in_index = fr in fr_index
        if not in_index and not has_seed:
            findings.append(Finding(
                "WARN", fr,
                "orphan — no capability seed + not registered in fr_index "
                "(cluster_identify/seed_backfill not run)",
            ))
        elif not in_index:
            findings.append(Finding(
                "WARN", fr,
                "unmapped — has a capability seed but not registered in "
                "fr_index (cluster_identify re-run needed)",
            ))

    # ── Direction (a): fr_index mapping <-> missing cluster draft fr_refs -> BLOCK
    for fr, info in fr_index.items():
        cid = str(info.get("cluster_id") or "").strip()
        if not cid:
            continue
        draft_clusters = fr_to_draft_clusters.get(fr, [])
        if cid not in draft_clusters:
            if cid not in cluster_fr_refs:
                # If the mapped cluster's draft doesn't even exist, exclude
                # it from this check (partial validation). Only flag BLOCK
                # when the draft exists but is missing the reference.
                continue
            findings.append(Finding(
                "BLOCK", fr,
                f"mismatch — fr_index maps {fr}->{cid} but the {cid} cluster "
                f"draft's fr_refs is missing {fr} (draft fr_refs needs updating)",
            ))

    # ── Direction (b): cluster draft fr_refs <-> fr_index mismatch -> BLOCK
    for cid, refs in cluster_fr_refs.items():
        for fr in refs or []:
            info = fr_index.get(fr)
            if info is None:
                findings.append(Finding(
                    "BLOCK", fr,
                    f"mismatch — {cid} cluster draft carries {fr} in fr_refs "
                    f"but fr_index has no mapping for {fr} (draft misreference "
                    f"or cluster_identify was skipped)",
                ))
                continue
            mapped = str(info.get("cluster_id") or "").strip()
            if mapped and mapped != cid:
                findings.append(Finding(
                    "BLOCK", fr,
                    f"mismatch — {cid} cluster draft carries {fr} in fr_refs "
                    f"but fr_index maps {fr}->{mapped} (a different cluster) "
                    f"(boundary conflict)",
                ))

    # Determinism: BLOCK first, sort by FR/reason within the same level, dedupe
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
    """Verdicts -> exit code. 2 if at least one BLOCK, else 0 (including WARN-only)."""
    return 2 if any(f.level == "BLOCK" for f in findings) else 0


# ── Report (queue-style markdown) ─────────────────────────────────────────
def render_report(findings: list[Finding], *, product: str | None = None) -> str:
    """Render findings as queue-style markdown (borrows the bdd-coverage-queue.md layout)."""
    blocks = sum(1 for f in findings if f.level == "BLOCK")
    warns = sum(1 for f in findings if f.level == "WARN")
    title = f"# fr-cluster-trace-queue{' — ' + product if product else ''}"
    lines = [
        title,
        "",
        f"> Generated: {datetime.now().isoformat(timespec='seconds')} · "
        f"fr_cluster_check.py (do not edit)",
        f"> **BLOCK: {blocks} · WARN: {warns}**",
        "",
        "| FR | Level | Reason |",
        "|---|---|---|",
    ]
    if findings:
        for f in findings:
            lines.append(f"| {f.fr} | **{f.level}** | {f.reason} |")
    else:
        lines.append("| _(no traceability violations)_ | OK | FR<->cluster consistent |")
    lines += [
        "",
        "## Resolution criteria (gates/fr-cluster-trace-gate.md)",
        "- orphan(WARN): capability seed and fr_index both missing -> "
        "enter the seed via /draft-req or run cluster_identify (non-blocking)",
        "- unmapped(WARN): seed exists but fr_index is missing -> "
        "re-run cluster_identify (non-blocking)",
        "- mismatch(BLOCK): fr_index and cluster draft fr_refs disagree -> "
        "update draft fr_refs or re-cluster with cluster_identify (blocking)",
    ]
    return "\n".join(lines) + "\n"


# ── File I/O wrapper ───────────────────────────────────────────────────────
def _load_drafts_fr_refs(drafts_dir: Path) -> dict[str, list[str]]:
    """Collect {cluster_id: [FR-ID,...]} from the cluster drafts in drafts/ (graceful).

    Drafts with no cluster_id or that fail to parse are skipped (no exceptions)."""
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
    """File I/O wrapper. Returns (exit_code, findings).

    Seeds are read from the sidecar seeds yml. If seeds_path is None it
    defaults to the sibling `requirements.seeds.yml` next to requirements_path.

    If queue_path is given, writes `fr-cluster-queue.md` (aggregated by the
    viz status adapter ssot_emit.py) using the render_report layout — the
    header's `**BLOCK: N · WARN: M**` is absorbed by ssot as BLOCK/WARN
    equivalents. report_path and queue_path share the same layout and can be
    written independently.

    exit_code: 0 clean (including WARN-only) / 2 BLOCK / 1 input error.
    Never raises — corrupt input is absorbed gracefully as an empty result."""
    if not requirements_path.is_file():
        print(f"[fr_cluster_check] ERROR: requirements file not found: {requirements_path}",
              file=sys.stderr)
        return 1, []
    if not cluster_map_path.is_file():
        print(f"[fr_cluster_check] ERROR: cluster_map file not found: {cluster_map_path}",
              file=sys.stderr)
        return 1, []
    if not drafts_dir.is_dir():
        print(f"[fr_cluster_check] ERROR: drafts directory not found: {drafts_dir}",
              file=sys.stderr)
        return 1, []

    try:
        md_text = requirements_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"[fr_cluster_check] ERROR: failed to read requirements: {exc}", file=sys.stderr)
        return 1, []

    cluster_map: Any = {}
    try:
        cluster_map = json.loads(cluster_map_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        # Corrupt cluster_map -> proceed gracefully with an empty fr_index
        # (not blocking; can still yield WARNs)
        print(f"[fr_cluster_check] WARN: failed to parse cluster_map — proceeding with "
              f"empty fr_index: {exc}", file=sys.stderr)
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
    for out_path, label in ((report_path, "report"), (queue_path, "queue")):
        if out_path is None:
            continue
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            print(f"[fr_cluster_check] WARN: failed to write {label}: {exc}", file=sys.stderr)

    blocks = sum(1 for f in findings if f.level == "BLOCK")
    warns = sum(1 for f in findings if f.level == "WARN")
    print(f"[fr_cluster_check] BLOCK={blocks} WARN={warns} "
          f"(FR {len(fr_ids)} · seeded {len(seeded)} · fr_index {len(fr_index)} · "
          f"cluster draft {len(cluster_fr_refs)})"
          + ("" if blocks == 0 else " — blocked by fr-cluster-trace-gate"))
    return code, findings


# ── Main ───────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fr_cluster_check",
        description="FR <-> cluster traceability gate (P4, gates/fr-cluster-trace-gate.md)",
    )
    parser.add_argument("--requirements", type=Path, required=True,
                        help="Input requirements.md (FR table)")
    parser.add_argument("--cluster-map", type=Path, required=True,
                        help="cluster_map.json (authoritative fr_index mapping)")
    parser.add_argument("--drafts-dir", type=Path, required=True,
                        help="Cluster draft directory (*.draft.md, carries fr_refs)")
    parser.add_argument("--seeds", type=Path, default=None,
                        help="Sidecar requirements.seeds.yml (defaults to the "
                             "sibling requirements.seeds.yml if omitted)")
    parser.add_argument("--report", type=Path, default=None,
                        help="Output path for the queue-style report markdown")
    parser.add_argument("--queue", type=Path, default=None,
                        help="Output path for the queue consumed by the viz "
                             "status adapter (ssot_emit.py) "
                             "(reports/fr-cluster-queue.md)")
    parser.add_argument("--product", default=None,
                        help="Product name to show in the report title (optional)")
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
