#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render apply inbox — applies the PM's decision from a Confluence-drift merge-proposal to the draft.

Design intent:
    When render_sync_check.py --with-remote detects that a Confluence page is
    newer, it generates reports/inbox/{WO_ID}.merge-proposal.md.
    The PM selects a checkbox in the proposal, then this script applies it.

    LLM round-trips are lossy, so auto-applying is risky. This script:
    - Overwrites the draft only when the PM explicitly checks "Adopt full body"
    - Immediately runs fact_preservation_check right after applying → blocks and rolls back on fact loss
    - Simply archives (leaving the draft unchanged) when "Manual review complete" is checked
    - NOOPs when neither is checked

Checkbox format:
    - [x] **Adopt full body** ...    ← apply target
    - [x] **Manual review complete** ...    ← archive only
    - [ ] **...**                   ← ignored

exit code:
    0 = success (applied, archived, or NOOP)
    1 = fact_preservation_check FAIL (apply blocked, draft unchanged)
    2 = usage/file error
    3 = malformed proposal (both checkboxes checked — full+manual simultaneously)
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
FACT_CHECK_SCRIPT = HERE / "fact_preservation_check.py"

# MEDIUM #12: tolerate BOM/CRLF/leading whitespace — prevents losing the whole
# frontmatter block if \A strict matching fails
FRONTMATTER_RE = re.compile(r"\A﻿?\s*---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
# MEDIUM #9: allow both checkbox case variants
CHECKED_FULL_RE = re.compile(
    r"^\s*-\s*\[[xX]\]\s*\*\*Adopt\s*full\s*body\*\*",
    re.MULTILINE,
)
CHECKED_MANUAL_RE = re.compile(
    r"^\s*-\s*\[[xX]\]\s*\*\*Manual\s*review\s*complete\*\*",
    re.MULTILINE,
)
# CRITICAL #2: body extraction uses an HTML comment sentinel (avoids conflicts with ``` code fences)
# render_sync_check's _write_merge_proposal wraps the body with the following sentinel pair.
CONFLUENCE_BODY_RE = re.compile(
    r"<!--\s*confluence-body:start\s*-->\s*\n(.*?)\n<!--\s*confluence-body:end\s*-->",
    re.DOTALL,
)
META_PAGE_RE = re.compile(r"page_id:\s*`([^`]+)`")


def _read_proposal(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"proposal not found: {path}")
    text = path.read_text(encoding="utf-8")
    has_full = bool(CHECKED_FULL_RE.search(text))
    has_manual = bool(CHECKED_MANUAL_RE.search(text))
    body_m = CONFLUENCE_BODY_RE.search(text)
    page_m = META_PAGE_RE.search(text)
    return {
        "text": text,
        "has_full": has_full,
        "has_manual": has_manual,
        "remote_body": body_m.group(1) if body_m else "",
        "page_id": page_m.group(1) if page_m else "",
    }


def _replace_body_preserve_frontmatter(draft_text: str, new_body: str) -> str:
    """Keep the draft's frontmatter as-is and replace only the body."""
    m = FRONTMATTER_RE.match(draft_text)
    if not m:
        return new_body
    fm_block = draft_text[: m.end()]
    return fm_block + new_body.rstrip() + "\n"


def _archive(proposal_path: Path, suffix: str) -> Path:
    archive_dir = proposal_path.parent / "archived"
    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    archived = archive_dir / f"{proposal_path.stem}.{ts}.{suffix}.md"
    shutil.move(str(proposal_path), str(archived))
    return archived


def _run_fact_check(before: Path, after: Path, hub_root: Path, report: Path) -> int:
    """Run fact_preservation_check. Returns the exit code."""
    cmd = [
        sys.executable,
        str(FACT_CHECK_SCRIPT),
        "--before", str(before),
        "--after", str(after),
        "--hub-root", str(hub_root),
        "--report", str(report),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode


def apply_inbox(hub_root: Path, product: str, wo_id: str) -> int:
    proj = hub_root / "PROJECTS" / product
    proposal_path = proj / "reports" / "inbox" / f"{wo_id}.merge-proposal.md"
    draft_path = proj / "drafts" / f"{wo_id}.draft.md"

    if not proj.is_dir():
        print(f"[apply-inbox] FAIL: project not found — {proj}", file=sys.stderr)
        return 2
    if not draft_path.is_file():
        print(f"[apply-inbox] FAIL: draft not found — {draft_path}", file=sys.stderr)
        return 2

    try:
        proposal = _read_proposal(proposal_path)
    except FileNotFoundError as exc:
        print(f"[apply-inbox] FAIL: {exc}", file=sys.stderr)
        return 2

    if proposal["has_full"] and proposal["has_manual"]:
        print("[apply-inbox] FAIL: both 'Adopt full body' and "
              "'Manual review complete' are checked — "
              "please select only one", file=sys.stderr)
        return 3

    # 1. NOOP: neither checked
    if not proposal["has_full"] and not proposal["has_manual"]:
        print(f"[apply-inbox] NOOP: {wo_id} — no checkbox selected, proposal kept as-is")
        return 0

    # 2. archive only: manual review complete
    if proposal["has_manual"]:
        archived = _archive(proposal_path, "manual-reviewed")
        print(f"[apply-inbox] ARCHIVED (manual review): {wo_id} → {archived.relative_to(hub_root)}")
        return 0

    # 3. adopt full body
    remote_body = proposal["remote_body"].strip()
    if not remote_body:
        print(f"[apply-inbox] FAIL: failed to extract Confluence body from proposal", file=sys.stderr)
        return 2

    # backup
    backup_path = draft_path.with_suffix(draft_path.suffix + ".bak")
    shutil.copy(str(draft_path), str(backup_path))

    original_text = draft_path.read_text(encoding="utf-8")
    new_text = _replace_body_preserve_frontmatter(original_text, remote_body)

    # save new body to a temp file → fact-check
    tmp_dir = proj / "reports" / "inbox" / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_after = tmp_dir / f"{wo_id}.candidate.md"
    tmp_after.write_text(new_text, encoding="utf-8")

    fact_report = proj / "reports" / "inbox" / f"{wo_id}.fact-check.md"
    rc = _run_fact_check(backup_path, tmp_after, hub_root, fact_report)

    if rc != 0:
        # fact loss detected — block the apply, roll back to backup
        # backup is already the original, so no further action needed
        backup_path.unlink(missing_ok=True)
        tmp_after.unlink(missing_ok=True)
        print(f"[apply-inbox] FAIL: {wo_id} — fact loss detected when applying the Confluence body. "
              f"draft unchanged. Missing facts: {fact_report.relative_to(hub_root)}",
              file=sys.stderr)
        return 1

    # PASS: update draft
    draft_path.write_text(new_text, encoding="utf-8")
    tmp_after.unlink(missing_ok=True)
    backup_path.unlink(missing_ok=True)

    archived = _archive(proposal_path, "applied")
    print(f"[apply-inbox] APPLIED: {wo_id} — fact-check PASS. "
          f"draft updated + proposal archived → {archived.relative_to(hub_root)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Apply the PM's decision from reports/inbox/{WO}.merge-proposal.md to the draft"
    )
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", required=True)
    ap.add_argument("--wo", required=True, help="Target WO_ID (e.g. WO-05)")
    args = ap.parse_args()

    if not args.hub_root.is_dir():
        print(f"[apply-inbox] FAIL: hub-root not found — {args.hub_root}", file=sys.stderr)
        return 2

    return apply_inbox(args.hub_root, args.product, args.wo)


if __name__ == "__main__":
    sys.exit(main())
