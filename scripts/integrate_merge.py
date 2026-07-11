#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collect drafts/*.draft.md to build an integrator input bundle.

[STANDALONE / NOT-WIRED]
    This script is not invoked by any skill. /integrate (and the integrator
    agent) scan draft frontmatter directly, so they never go through the
    reports/integration-input.json bundle. This script is kept only as an
    optional tool for humans to manually inspect the integration input
    (the pipeline disconnection is intentional).

Change history:
    v1.0: initial implementation (heading + file size only)
    v2.0: type separation / missing-WO detection / decisions.md hash
          mismatch detection / checklist completion / graph node ID /
          level extraction

Usage:
    python integrate_merge.py <project-dir>

Bundle structure:
    {
      "generated_at": "...",
      "project": "...",
      "graph_hash": "...",
      "decisions_hash": "...",
      "summary": {
        "total": N,
        "policy": N,
        "screen": N,
        "missing": N,
        "stale": N,
        "checklist_incomplete": N
      },
      "missing_wos": ["WO-03", ...],
      "stale_wos": ["WO-05", ...],
      "drafts": [
        {
          "path": "drafts/WO-01.draft.md",
          "wo_id": "WO-01",
          "type": "policy",
          "title": "...",
          "graph_node": "...",
          "level": 0,
          "size_bytes": 1234,
          "decisions_hash_match": true,
          "checklist_total": 7,
          "checklist_unchecked": 0
        }
      ]
    }
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _extract_bold_field(text: str, field: str) -> str:
    """Extract value from a **field**: `value` pattern."""
    pattern = rf"\*\*{re.escape(field)}\*\*:\s*`([^`]+)`"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def _extract_title(text: str) -> str:
    """Extract the section title from the first H1.

    Example: # Work Order: WO-01 — Section Title  →  Section Title
    """
    match = re.search(r"^\s*#\s+.+?—\s+(.+)$", text, flags=re.M)
    if match:
        return match.group(1).strip()
    match = re.search(r"^\s*#\s+(.+)$", text, flags=re.M)
    return match.group(1).strip() if match else "(no heading)"


def _extract_checklist(text: str) -> tuple[int, int]:
    """Return the total checklist item count and the unchecked (- [ ]) count."""
    total = len(re.findall(r"- \[[ xX]\]", text))
    unchecked = len(re.findall(r"- \[ \]", text))
    return total, unchecked


def _hash_file(path: Path) -> str:
    if not path.exists():
        return "n/a"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:12]


def _count_dec_status(decisions_path: Path) -> dict:
    """Parse the `Approval` column of the decisions.md DEC table and return counts by status.

    Schema: CONTEXT/dec-schema.md
    | ID | Date | Domain | Key Decision | Reversal | Approval | (optional trailing Rationale) |

    Approval ENUM:
        ⬜              → pending
        ✅ {pm_id}      → approved
        ❌ {pm_id}: ... → rejected
        🟡 hold         → hold

    If the table is missing or the header doesn't match, all counts are returned as -1 (not applicable).
    """
    if not decisions_path.exists():
        return {"total": -1, "pending": -1, "approved": -1, "rejected": -1, "hold": -1}

    text = decisions_path.read_text(encoding="utf-8", errors="replace")
    # Detect the header line (verify the 5 required columns)
    header_re = re.compile(
        r"^\|\s*ID\s*\|\s*Date\s*\|\s*Domain\s*\|\s*Key Decision\s*\|\s*Reversal\s*\|\s*Approval\s*\|",
        re.M,
    )
    if not header_re.search(text):
        return {"total": -1, "pending": -1, "approved": -1, "rejected": -1, "hold": -1}

    # Extract DEC rows (| DEC-NNN | ... | approval cell | ... |)
    row_re = re.compile(
        r"^\|\s*~?~?(DEC-\d+)~?~?\s*\|[^|\n]*\|[^|\n]*\|[^|\n]*\|[^|\n]*\|\s*([^|\n]*?)\s*\|",
        re.M,
    )
    counts = {"total": 0, "pending": 0, "approved": 0, "rejected": 0, "hold": 0}
    for match in row_re.finditer(text):
        approval_cell = match.group(2).strip()
        counts["total"] += 1
        if approval_cell.startswith("⬜"):
            counts["pending"] += 1
        elif approval_cell.startswith("✅"):
            counts["approved"] += 1
        elif approval_cell.startswith("❌"):
            counts["rejected"] += 1
        elif approval_cell.startswith("🟡"):
            counts["hold"] += 1
    return counts


# ── Extract WO ID list from index.md ──────────────────────────────────────────

def _load_index_wo_ids(project: Path) -> list[str]:
    """Extract the WO-NN ID list from work-orders/index.md."""
    index_path = project / "work-orders" / "index.md"
    if not index_path.exists():
        return []
    text = index_path.read_text(encoding="utf-8", errors="replace")
    return re.findall(r"`(WO-\d+)`", text)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    if len(sys.argv) != 2:
        print("usage: integrate_merge.py <project-dir>", file=sys.stderr)
        return 2

    project = Path(sys.argv[1]).resolve()
    drafts_dir = project / "drafts"

    if not drafts_dir.exists():
        print(
            f"[integrate_merge] FAIL: drafts/ directory not found: {drafts_dir}",
            file=sys.stderr,
        )
        return 1

    # ── Compute current hashes ────────────────────────────────────────────────
    graph_hash = _hash_file(project / "graph" / "graph.json")
    decisions_path = project / "decisions.md"
    decisions_hash = _hash_file(decisions_path)
    dec_counts = _count_dec_status(decisions_path)

    # ── Load WO list from index.md ────────────────────────────────────────────
    index_wo_ids = _load_index_wo_ids(project)
    index_wo_set = set(index_wo_ids)

    # ── Collect draft files ───────────────────────────────────────────────────
    draft_files = sorted(drafts_dir.glob("*.draft.md"))
    draft_wo_set: set[str] = set()
    drafts: list[dict] = []

    for path in draft_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        wo_id = path.stem.replace(".draft", "")
        draft_wo_set.add(wo_id)

        wo_type = _extract_bold_field(text, "type") or "unknown"
        graph_node = _extract_bold_field(text, "Document Name") or ""
        if not graph_node:
            # screen WO uses the Screen ID field
            graph_node = _extract_bold_field(text, "Screen ID") or ""

        level_parts = _extract_bold_field(text, "level").split()
        level_str = level_parts[0] if level_parts else ""
        try:
            level = int(level_str)
        except (ValueError, IndexError):
            level = -1

        wo_decisions_hash = _extract_bold_field(text, "decisions.md snapshot hash")
        decisions_hash_match = (
            wo_decisions_hash == decisions_hash
            if wo_decisions_hash not in ("", "n/a")
            else None
        )

        checklist_total, checklist_unchecked = _extract_checklist(text)

        drafts.append({
            "path": str(path.relative_to(project)),
            "wo_id": wo_id,
            "type": wo_type,
            "title": _extract_title(text),
            "graph_node": graph_node,
            "level": level,
            "size_bytes": path.stat().st_size,
            "decisions_hash_match": decisions_hash_match,
            "checklist_total": checklist_total,
            "checklist_unchecked": checklist_unchecked,
        })

    # ── Detect missing WOs ─────────────────────────────────────────────────────
    missing_wos = sorted(index_wo_set - draft_wo_set) if index_wo_set else []

    # ── Detect stale WOs (decisions.md hash mismatch) ─────────────────────────
    stale_wos = [
        d["wo_id"]
        for d in drafts
        if d["decisions_hash_match"] is False
    ]

    # ── WOs with incomplete checklists ────────────────────────────────────────
    checklist_incomplete = [
        d["wo_id"]
        for d in drafts
        if d["checklist_unchecked"] > 0
    ]

    # ── Aggregate by type ──────────────────────────────────────────────────────
    policy_count = sum(1 for d in drafts if d["type"] == "policy")
    screen_count = sum(1 for d in drafts if d["type"] == "screen")

    # ── Build bundle ───────────────────────────────────────────────────────────
    bundle = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "project": project.name,
        "graph_hash": graph_hash,
        "decisions_hash": decisions_hash,
        "dec_status": dec_counts,
        "summary": {
            "total": len(drafts),
            "policy": policy_count,
            "screen": screen_count,
            "missing": len(missing_wos),
            "stale": len(stale_wos),
            "checklist_incomplete": len(checklist_incomplete),
            "dec_pending": dec_counts["pending"],
            "dec_hold": dec_counts["hold"],
        },
        "missing_wos": missing_wos,
        "stale_wos": stale_wos,
        "checklist_incomplete_wos": checklist_incomplete,
        "drafts": drafts,
    }

    # ── Save ───────────────────────────────────────────────────────────────────
    out_dir = project / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "integration-input.json"
    out_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ── Console summary ────────────────────────────────────────────────────────
    # Fall back to ASCII if console stdout encoding isn't utf-8 (e.g. Windows cp949)
    use_emoji = (sys.stdout.encoding or "").lower().startswith("utf")
    if dec_counts["total"] < 0:
        dec_summary = "DEC: table missing or header mismatch — migration required"
    elif use_emoji:
        dec_summary = (
            f"DEC: total {dec_counts['total']} / "
            f"✅ {dec_counts['approved']} / ⬜ {dec_counts['pending']} / "
            f"🟡 {dec_counts['hold']} / ❌ {dec_counts['rejected']}"
        )
    else:
        dec_summary = (
            f"DEC: total {dec_counts['total']} / "
            f"approved {dec_counts['approved']} / pending {dec_counts['pending']} / "
            f"hold {dec_counts['hold']} / rejected {dec_counts['rejected']}"
        )
    print(
        f"[integrate_merge] bundle generated -> {out_path}\n"
        f"  drafts:      {len(drafts)} (policy: {policy_count} / screen: {screen_count})\n"
        f"  missing WO:  {len(missing_wos)} {missing_wos if missing_wos else ''}\n"
        f"  stale WO:    {len(stale_wos)} {stale_wos if stale_wos else ''}\n"
        f"  checklist incomplete: {len(checklist_incomplete)} "
        f"{checklist_incomplete if checklist_incomplete else ''}\n"
        f"  {dec_summary}"
    )

    # Exit with an error if any WOs are missing
    if missing_wos:
        print(
            f"[integrate_merge] FAIL: missing drafts {missing_wos}. "
            "Complete authoring those WOs before running /integrate.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
