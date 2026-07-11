#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply standard frontmatter to drafts/*.draft.md (Option H — CONTEXT_OPTIMIZATION.md).

Purpose:
    Ensure every draft file starts with frontmatter in the following format,
    so reviewers / integrators can narrow candidates in a first pass before
    loading the full body.

    ---
    wo_id: {PREFIX}-C-001
    type: policy           # policy | screen
    layer: C
    status: draft          # draft | review | frozen
    referenced_policies: [G2-B-001, G2-B-005]
    referenced_master:   [G2-B-002@v1.3, G2-A-001@v1.1]
    referenced_screens:    []
    related_decisions:     []
    last_updated: 2026-05-06
    ---

    Missing fields are inferred from (deprecated) work-orders/{WO_ID}.md when it
    exists. After Option A (merging the WO template and draft into one file),
    work-orders/*.md body files are no longer the canonical path — only
    drafts/{WO_ID}.draft.md is authoritative. The inference logic remains for
    backward compatibility, but derive_from_wo() returns an empty dict for new
    projects. If frontmatter already exists, only missing fields are added;
    existing values are preserved.

    Automatic status field:
        When migrating existing drafts/*.draft.md files, if the status field is
        missing it is automatically set to 'ai-draft' (back-inferred: existing
        drafts are all assumed to be at the ai-draft stage).

Usage:
    python migrate_draft_frontmatter.py --hub-root <Hub> --product <product>
    python migrate_draft_frontmatter.py --hub-root <Hub> --product <product> --check
        (--check: report only what's missing, no file changes. exit 1 = missing found)
    python migrate_draft_frontmatter.py --hub-root <Hub> --product <product> --convert-wo-to-draft
        (Option A migration: convert work-orders/{WO_ID}.md → drafts/{WO_ID}.draft.md,
         then move the originals to .archive/work-orders/. index.md/index.json are kept.)

exit code:
    0 = all OK or migration complete
    1 = missing fields found in --check mode
    2 = argument error
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

FRONTMATTER_PATTERN = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
WO_ID_PATTERN = re.compile(r"^([A-Za-z0-9]+-[A-Z]-[A-Za-z0-9]+-\d{3,})$")
WO_TYPE_PATTERN = re.compile(r"^\*?\*?type\*?\*?\s*[:：]\s*[`']?(policy|screen)[`']?", re.MULTILINE)
WO_INHERITS_LINE = re.compile(r"\| inherits_from \| ([A-Za-z0-9-]+) ", re.MULTILINE)
WO_INCLUDES_LINE = re.compile(r"\| includes \| ([A-Za-z0-9-]+) ", re.MULTILINE)

REQUIRED_FIELDS = [
    "wo_id",
    "type",
    "layer",
    "status",
    "referenced_policies",
    "referenced_master",
    "referenced_screens",
    "related_decisions",
    "last_updated",
]


def parse_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}, text
    body = text[match.end() :]
    fm: dict = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip()
    return fm, body


def render_frontmatter(fm: dict) -> str:
    lines = ["---"]
    for key in REQUIRED_FIELDS:
        value = fm.get(key, "")
        if isinstance(value, list):
            inner = ", ".join(value)
            lines.append(f"{key}: [{inner}]")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def parse_list_value(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw or raw == "[]":
        return []
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [item.strip() for item in raw.split(",") if item.strip()]


def derive_from_wo(wo_path: Path) -> dict:
    if not wo_path.exists():
        return {}
    body = wo_path.read_text(encoding="utf-8")
    info: dict = {}
    type_match = WO_TYPE_PATTERN.search(body)
    if type_match:
        info["type"] = type_match.group(1)
    inherits = WO_INHERITS_LINE.findall(body)
    info["referenced_policies"] = inherits
    includes = WO_INCLUDES_LINE.findall(body)
    info["referenced_includes"] = includes
    return info


def derive_wo_id_from_filename(name: str) -> str | None:
    stem = name.replace(".draft.md", "")
    return stem if WO_ID_PATTERN.match(stem) else None


def merge(fm: dict, wo_id: str, wo_info: dict) -> dict:
    merged: dict = dict(fm)
    merged.setdefault("wo_id", wo_id)
    merged.setdefault("type", wo_info.get("type", "policy"))
    merged.setdefault("layer", "C")
    # Option A: back-infer that existing drafts are all at the ai-draft stage.
    # However, if 'status' already exists, never overwrite it (preserve first).
    merged.setdefault("status", "ai-draft")

    pol_existing = parse_list_value(merged.get("referenced_policies", "")) if isinstance(
        merged.get("referenced_policies"), str
    ) else merged.get("referenced_policies", [])
    if not pol_existing and wo_info.get("referenced_policies"):
        pol_existing = wo_info["referenced_policies"]
    merged["referenced_policies"] = pol_existing or []

    mst_existing = parse_list_value(merged.get("referenced_master", "")) if isinstance(
        merged.get("referenced_master"), str
    ) else merged.get("referenced_master", [])
    merged["referenced_master"] = mst_existing or []

    scr_existing = parse_list_value(merged.get("referenced_screens", "")) if isinstance(
        merged.get("referenced_screens"), str
    ) else merged.get("referenced_screens", [])
    merged["referenced_screens"] = scr_existing or []

    dec_existing = parse_list_value(merged.get("related_decisions", "")) if isinstance(
        merged.get("related_decisions"), str
    ) else merged.get("related_decisions", [])
    merged["related_decisions"] = dec_existing or []

    merged.setdefault("last_updated", date.today().isoformat())
    return merged


def process(hub_root: Path, product: str, check_only: bool) -> int:
    project_dir = hub_root / "PROJECTS" / product
    drafts_dir = project_dir / "drafts"
    wo_dir = project_dir / "work-orders"
    if not drafts_dir.is_dir():
        sys.stderr.write(f"drafts dir not found: {drafts_dir}\n")
        return 1

    drafts = sorted(drafts_dir.glob("*.draft.md"))
    if not drafts:
        print(f"[migrate_draft_frontmatter] no drafts under {drafts_dir}")
        return 0

    missing: list[str] = []
    migrated = 0
    for draft in drafts:
        wo_id = derive_wo_id_from_filename(draft.name)
        if not wo_id:
            sys.stderr.write(f"[skip] cannot derive wo_id from {draft.name}\n")
            continue
        text = draft.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        existing_keys = set(fm.keys())
        absent = [key for key in REQUIRED_FIELDS if key not in existing_keys]

        if check_only:
            if absent:
                missing.append(f"{draft.name}: missing {','.join(absent)}")
            continue

        if not absent:
            continue

        wo_info = derive_from_wo(wo_dir / f"{wo_id}.md")
        merged = merge(fm, wo_id, wo_info)
        new_text = render_frontmatter(merged) + body
        draft.write_text(new_text, encoding="utf-8")
        migrated += 1
        print(f"[migrate] {draft.name} ← added: {','.join(absent)}")

    if check_only:
        if missing:
            sys.stderr.write("[check] frontmatter missing in:\n")
            for line in missing:
                sys.stderr.write(f"  - {line}\n")
            return 1
        print(f"[check] all drafts have frontmatter ({len(drafts)})")
        return 0

    print(f"[migrate_draft_frontmatter] migrated={migrated}/{len(drafts)}")
    return 0


STATUS_FIELD_PATTERN = re.compile(r"^status\s*:\s*(\S+)\s*$", re.MULTILINE)
VALID_STATUSES_PROMOTED = {"ai-draft", "human-reviewed", "frozen"}


def _read_status_field(text: str) -> str | None:
    """Read the status field value from a draft body (frontmatter region only).

    Returns None if there is no frontmatter or no status field.
    """
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return None
    fm_block = match.group(1)
    status_match = STATUS_FIELD_PATTERN.search(fm_block)
    if not status_match:
        return None
    return status_match.group(1).strip()


def _ensure_status_field(text: str, status_value: str) -> str:
    """Insert a frontmatter status field into a draft body if missing (preserve if present).

    - No frontmatter at all: create a minimal frontmatter block with just status.
    - Frontmatter exists but status is missing: append a status line at the end
      of the frontmatter.
    - Both frontmatter and status exist: return unchanged (never overwrite).
    """
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        # No frontmatter → create a minimal block
        new_fm = f"---\nstatus: {status_value}\n---\n"
        return new_fm + text
    fm_block = match.group(1)
    if STATUS_FIELD_PATTERN.search(fm_block):
        return text  # status already present — never overwrite
    body = text[match.end() :]
    new_fm = f"---\n{fm_block}\nstatus: {status_value}\n---\n"
    return new_fm + body


TYPE_FIELD_PATTERN = re.compile(r"^type\s*:\s*(\S+)\s*$", re.MULTILINE)
REVIEW_STATUS_FIELD_PATTERN = re.compile(r"^review_status\s*:", re.MULTILINE)


def _ensure_review_status_field(text: str, value: str = "ai-draft") -> str:
    """Non-destructively insert a review_status (kanban lifecycle) block into frontmatter if missing.

    status (document maturity: draft|review|frozen) and review_status (kanban
    lifecycle: empty|ai-draft|human-reviewed|frozen) are separate fields. The
    work board (wo_emit) reads review_status first, so if this field is
    missing, the status value falls back and can't be mapped to the 4 lanes
    (the card doesn't display). This function only fills that gap.

    - No frontmatter → no change (dossier assumes frontmatter exists).
    - review_status already present → no change (preserve first, never
      overwrite → idempotent).
    - Missing → insert 3 lines (review_status / reviewed_by / reviewed_at)
      right after the status line (or at the end of frontmatter if there is
      no status line). Since this only inserts lines, dossier-specific fields
      like doc_id/capability are preserved.
    """
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return text
    fm_block = match.group(1)
    if REVIEW_STATUS_FIELD_PATTERN.search(fm_block):
        return text
    body = text[match.end() :]
    inject = [f"review_status: {value}", "reviewed_by:", "reviewed_at:"]
    out: list[str] = []
    inserted = False
    for line in fm_block.split("\n"):
        out.append(line)
        if not inserted and re.match(r"^status\s*:", line):
            out.extend(inject)
            inserted = True
    if not inserted:
        out.extend(inject)
    new_fm = "---\n" + "\n".join(out) + "\n---\n"
    return new_fm + body


def ensure_dossier_review_status(hub_root: Path, product: str, dry_run: bool = False) -> int:
    """Ensure a review_status: ai-draft block on dossier (type: dossier) drafts (non-destructive).

    Avoids the REQUIRED_FIELDS rewrite path in process()/render_frontmatter
    (which risks losing unique fields) and only performs line insertion.
    Skips files that already have review_status (idempotent).
    """
    drafts_dir = hub_root / "PROJECTS" / product / "drafts"
    if not drafts_dir.is_dir():
        sys.stderr.write(f"drafts dir not found: {drafts_dir}\n")
        return 1
    changed = 0
    skipped = 0
    for draft in sorted(drafts_dir.glob("*.draft.md")):
        text = draft.read_text(encoding="utf-8")
        fm_match = FRONTMATTER_PATTERN.match(text)
        if not fm_match:
            skipped += 1
            continue
        type_match = TYPE_FIELD_PATTERN.search(fm_match.group(1))
        if not type_match or type_match.group(1) != "dossier":
            skipped += 1
            continue
        new_text = _ensure_review_status_field(text)
        if new_text == text:
            skipped += 1
            continue
        prefix = "[dry-run]" if dry_run else ""
        if not dry_run:
            draft.write_text(new_text, encoding="utf-8")
        print(f"{prefix}[review_status] {draft.name} → review_status: ai-draft")
        changed += 1
    print(
        f"[ensure_dossier_review_status] added {changed} / skipped {skipped}"
        + (" (dry-run)" if dry_run else "")
    )
    return 0


def convert_wo_to_draft(hub_root: Path, product: str, dry_run: bool = False) -> int:
    """Option A migration: work-orders/{WO_ID}.md → drafts/{WO_ID}.draft.md.

    Procedure:
        1. Collect work-orders/{WO_ID}.md (excluding index.md/index.json).
        2. Check whether drafts/{WO_ID}.draft.md exists, then branch:
           - Doesn't exist: copy the work-orders body + add frontmatter status: empty.
           - Exists + status ∈ {ai-draft, human-reviewed, frozen}: keep the draft
             (ignore work-orders).
           - Exists + status: empty or no status: keep the draft body + promote
             status to ai-draft.
        3. Move work-orders/{WO_ID}.md → .archive/work-orders/{WO_ID}.md (safe rollback).
        4. Keep work-orders/index.md and work-orders/index.json in place (not moved).

    Idempotency: running the same command twice produces the same result
    (files already moved to .archive are not reprocessed).
    """
    import shutil

    project_root = hub_root / "PROJECTS" / product
    wo_dir = project_root / "work-orders"
    drafts_dir = project_root / "drafts"
    archive_dir = project_root / ".archive" / "work-orders"

    if not wo_dir.exists():
        print(f"[convert_wo_to_draft] work-orders/ not found — skip ({wo_dir})")
        return 0

    if not dry_run:
        drafts_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)

    converted = 0
    preserved = 0
    skipped = 0

    for wo_file in sorted(wo_dir.glob("*.md")):
        if wo_file.name in ("index.md", "index.json"):
            skipped += 1
            continue  # keep: index files are not moved
        wo_id = wo_file.stem
        draft_file = drafts_dir / f"{wo_id}.draft.md"

        if not draft_file.exists():
            # New conversion: copy the work-orders body into a draft + set status: empty
            content = wo_file.read_text(encoding="utf-8")
            new_content = _ensure_status_field(content, "empty")
            if dry_run:
                print(f"[dry-run][convert] {wo_file.name} → {draft_file.name} (status: empty)")
            else:
                draft_file.write_text(new_content, encoding="utf-8")
                print(f"[convert] {wo_file.name} → {draft_file.name} (status: empty)")
            converted += 1
        else:
            existing = draft_file.read_text(encoding="utf-8")
            current_status = _read_status_field(existing)
            if current_status in VALID_STATUSES_PROMOTED:
                # already at ai-draft or beyond — keep the draft body, ignore work-orders body
                if dry_run:
                    print(f"[dry-run][preserve] {draft_file.name} (status: {current_status})")
                else:
                    print(f"[preserve] {draft_file.name} (status: {current_status})")
                preserved += 1
            else:
                # status: empty or missing → promote to ai-draft (keep the draft body)
                new_content = _ensure_status_field(existing, "ai-draft")
                if dry_run:
                    print(f"[dry-run][promote] {draft_file.name} → status: ai-draft")
                else:
                    draft_file.write_text(new_content, encoding="utf-8")
                    print(f"[promote] {draft_file.name} → status: ai-draft")
                converted += 1

        # move the work-orders body file to .archive/ (not deleted immediately — safe rollback)
        archive_target = archive_dir / wo_file.name
        if dry_run:
            print(f"[dry-run][archive] {wo_file} → {archive_target}")
        else:
            shutil.move(str(wo_file), str(archive_target))

    print(
        f"[convert_wo_to_draft] done: converted/promoted {converted} / preserved {preserved} / "
        f"index-skip {skipped}"
        + (" (dry-run)" if dry_run else "")
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply standard frontmatter to drafts")
    parser.add_argument("--hub-root", required=True, type=Path)
    parser.add_argument("--product", required=True, help="PROJECTS/<product> directory name")
    parser.add_argument("--check", action="store_true", help="validate only, no file changes")
    parser.add_argument(
        "--convert-wo-to-draft",
        action="store_true",
        help=(
            "Option A migration: convert existing work-orders/{WO_ID}.md to "
            "drafts/{WO_ID}.draft.md, then move it to .archive/work-orders/ "
            "(index.md/index.json are kept)"
        ),
    )
    parser.add_argument(
        "--ensure-dossier-review-status",
        action="store_true",
        help=(
            "Non-destructively insert a review_status: ai-draft block into "
            "dossier (type: dossier) drafts. Backfills a missing work-board "
            "kanban lifecycle (empty→ai-draft→human-reviewed→frozen) — idempotent."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="used with --convert-wo-to-draft / --ensure-dossier-review-status to print results without changing any files",
    )
    args = parser.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2

    if args.convert_wo_to_draft:
        return convert_wo_to_draft(args.hub_root, args.product, dry_run=args.dry_run)

    if args.ensure_dossier_review_status:
        return ensure_dossier_review_status(args.hub_root, args.product, dry_run=args.dry_run)

    return process(args.hub_root, args.product, args.check)


if __name__ == "__main__":
    sys.exit(main())
