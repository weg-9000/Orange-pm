#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Draft <-> Confluence XML bidirectional sync scanner (C-SYNC).

Purpose:
    Where drift_scan.py catches version drift in the Master(G2-A/B) -> Draft
    direction, this script catches the sync gap in the Draft <-> Confluence
    XML direction (both ways).

Status classification:
    SYNCED        : both the draft and Confluence match the last push
    OUTDATED      : the draft is newer (push needed — `/render --push`)
    REMOTE-DRIFT  : Confluence is newer (PM edited it in Confluence — a merge-proposal is generated)
    PENDING       : no meta.json, or page_id is a placeholder (contains "{{")
    REMOTE-UNKNOWN: no wiki snapshot exists (the model hasn't run a wiki-connector lookup yet)
    UNKNOWN       : updated_at or last_published_at could not be parsed

Remote drift detection pattern (wiki connector integration):
    This script never calls a remote API directly (per the auth/tool
    separation principle — all external I/O goes exclusively through the
    model's wiki-connector tool calls; see docs/CONNECTORS.md). Instead, the model
    (on `/render --check-sync` or entering `/lc`) looks at the page_id list in
    the sync-queue, looks up each page via a wiki connector (e.g. Confluence
    or another MCP tool), and saves the result to
    reports/.confluence-snapshot/{page_id}.json. This script then compares
    that snapshot file against meta.json._sync.last_published_version.

    Expected snapshot JSON shape (as saved by the wiki connector):
        {
          "id": "12345",
          "version": {"number": 7, "when": "2026-05-28T..."},
          "title": "...",
          "body": {"storage": {"value": "<xml>...</xml>"}}
        }

    If no snapshot exists: REMOTE-UNKNOWN (not an error, just a warning)
    If snapshot version > meta.json._sync.last_published_version: REMOTE-DRIFT
        -> automatically generates reports/inbox/{WO_ID}.merge-proposal.md

Output:
    PROJECTS/{product}/reports/sync-queue.md         (all statuses)
    PROJECTS/{product}/reports/inbox/{WO_ID}.merge-proposal.md (on REMOTE-DRIFT)

exit code:
    0 = no OUTDATED / PENDING / REMOTE-DRIFT
    1 = one or more of the above
    2 = argument error

Usage:
    python render_sync_check.py --hub-root <Hub> [--product <name>] [--with-remote]
    (--with-remote: also checks the confluence snapshot; forward-only if omitted)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import _emit_common as C

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
ISO_DATE = re.compile(r"(\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?)")
PLACEHOLDER = re.compile(r"\{\{")

# Candidate keys in meta.json that hold the last publish time (priority order)
META_PUBLISHED_KEYS = [
    ("_sync", "last_published_at"),
    ("lastUpdatedAt",),
    ("version", "when"),
]


def _parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER.match(text)
    if not m:
        return {}
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm


def _extract_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    m = ISO_DATE.search(s)
    if not m:
        return None
    raw = m.group(1)
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(raw[:len(fmt) + 2], fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError:
            continue
    return None


def _get_meta_published(meta: dict) -> datetime | None:
    """Extract last_published_at from meta.json using a multi-key strategy."""
    for key_path in META_PUBLISHED_KEYS:
        obj = meta
        for k in key_path:
            if isinstance(obj, dict) and k in obj:
                obj = obj[k]
            else:
                obj = None
                break
        if obj and isinstance(obj, str):
            dt = _extract_iso(obj)
            if dt:
                return dt
    return None


def _classify(draft_upd: datetime | None, pub: datetime | None) -> tuple[str, str]:
    if draft_upd is None:
        return "UNKNOWN", "could not parse draft updated_at"
    if pub is None:
        return "UNKNOWN", "could not parse meta.json last_published_at"
    if pub >= draft_upd:
        return "SYNCED", f"published({pub.date()}) >= draft modified({draft_upd.date()})"
    return "OUTDATED", f"draft modified({draft_upd.date()}) > last published({pub.date()}) — push needed"


# ── Publication mode (fix-plan-dossier-publish-split) ───────────────────────

# split-deliverable publication units: (transpose deliverable, meta slug, display label)
SPLIT_DELIVERABLES = [
    ("D2", "02-policy", "Policy Definition"),
    ("D3", "03-screen-design", "Screen Design"),
]

# Common publication docs regardless of publication mode (publication-map §0/§0-bis:
# D1/D4/D5, one page each).
# (slug, label, source subdirectory, file glob) — the row is omitted if no source file exists.
# doc_id follows the same `{slug}-{product}` canonical key as the meta naming
# convention (kept consistent with sync_emit).
COMMON_DOCS = [
    ("01-requirements", "Requirements Definition", "inputs", "requirements*.md"),
    ("04-meetings", "Meeting Notes", "meetings", "*.md"),
    ("05-research", "Competitor Research", "inputs", "research*.md"),
]


def _scan_common_docs(proj: Path, src_dir: Path, product: str) -> tuple[list[tuple], int, int]:
    """Scan the D1/D4/D5 common docs (audit 2026-06-11 gap 1 — fixes D4/D5 not being scanned).

    Draft-side baseline: the max frontmatter updated_at across the source
    files, falling back to file mtime when there's no frontmatter (e.g. Meeting Notes).
    Returns: (rows, n_outdated, n_pending)
    """
    rows: list[tuple] = []
    n_out = n_pend = 0
    for slug, label, subdir, pattern in COMMON_DOCS:
        d = proj / subdir
        files = [f for f in (sorted(d.glob(pattern)) if d.is_dir() else []) if f.is_file()]
        if not files:
            continue
        doc_id = f"{slug}-{product}"
        fname = files[0].name if len(files) == 1 else f"{subdir}/{pattern} ({len(files)} files)"

        sides: list[datetime] = []
        for f in files:
            fm = _parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
            dt = _extract_iso(fm.get("updated_at", "") or fm.get("frozen_at", ""))
            if dt is None:
                try:
                    dt = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                except OSError:
                    continue
            sides.append(dt)
        draft_side = max(sides) if sides else None

        meta_path: Path | None = None
        if src_dir.is_dir():
            cands = sorted(src_dir.glob(f"{slug}-{product}.meta.json")) \
                or sorted(src_dir.glob(f"{slug}*.meta.json"))
            if cands:
                meta_path = cands[0]
        if meta_path is None:
            rows.append((fname, doc_id, "—", "no meta.json", "PENDING",
                         f"{slug}-{product}.meta.json missing — create/initialize the page via /cr"))
            n_pend += 1
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            rows.append((fname, doc_id, str(meta_path.name), str(e), "UNKNOWN",
                         "meta.json parse error"))
            continue
        page_id = str(meta.get("id", ""))
        if PLACEHOLDER.search(page_id) or not page_id:
            rows.append((fname, doc_id, meta_path.name, "id=PLACEHOLDER",
                         "PENDING", "Confluence page not yet created"))
            n_pend += 1
            continue
        pub = _get_meta_published(meta)
        status, reason = _classify(draft_side, pub)
        if status == "OUTDATED":
            n_out += 1
        rows.append((fname, doc_id, meta_path.name,
                     (draft_side.date().isoformat() if draft_side else "?"),
                     status, reason))
    return rows, n_out, n_pend


def _parse_source_clusters(text: str) -> set[str] | None:
    """The source_clusters list in assembled.md frontmatter (block or inline YAML list).

    Returns None if absent — the caller falls back to the whole-draft baseline.
    """
    m = FRONTMATTER.match(text)
    if not m:
        return None
    out: set[str] = set()
    in_block = False
    for ln in m.group(1).splitlines():
        if ln.startswith("source_clusters:"):
            rest = ln.partition(":")[2].strip()
            if rest.startswith("["):
                for tok in rest.strip("[]").split(","):
                    tok = tok.strip().strip("'\"")
                    if tok:
                        out.add(tok)
                return out or None
            in_block = True
            continue
        if in_block:
            s = ln.strip()
            if s.startswith("- "):
                out.add(s[2:].strip().strip("'\""))
            elif s and not ln.startswith((" ", "\t")):
                break
    return out or None


def _deliverable_source_clusters(proj: Path, dtype: str, slug: str) -> set[str] | None:
    """The set of contributing clusters for a deliverable, from the assembled
    output in reports/render/.

    render_transpose records source_clusters in the frontmatter (addresses
    audit gap 4). Returns None if the output/field is absent (falls back to
    the whole-draft baseline — previous behavior).
    """
    render_dir = proj / "reports" / "render"
    if not render_dir.is_dir():
        return None
    cands = sorted(render_dir.glob(f"{slug}*.assembled.md")) \
        + sorted(render_dir.glob(f"{dtype}_*.assembled.md"))
    for f in cands:
        try:
            srcs = _parse_source_clusters(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if srcs:
            return srcs
    return None


def _read_publication_mode(proj: Path) -> str:
    """Read publication_mode from graph/project-mode.json.

    Delegates to the single source of truth (_emit_common.read_publication_mode)
    to stay consistent with sync_emit. If the file/key is absent, defaults to
    "dossier-page" (previous behavior) — a regression guard for existing
    projects such as dbaas.
    """
    return C.read_publication_mode(proj)


def _scan_split(
    proj: Path, drafts_dir: Path, src_dir: Path, product: str
) -> tuple[list[tuple], int, int]:
    """Scan split-deliverable mode.

    A dossier draft is the canonical source, so it's shown only as
    **SOURCE-ONLY** (lowest severity, excluded from actionable) to avoid a
    false PENDING. The actual publication units are the two deliverables D2
    Policy Definition / D3 Screen Design, and their freshness is classified
    as *max updated_at across contributing dossier drafts* vs. the
    deliverable meta.json's last_published_at.

    Returns: (rows, n_outdated, n_pending)
    """
    rows: list[tuple] = []
    # cluster_id -> updated_at — used to scope the comparison to each deliverable's
    # contributing clusters (audit gap 4).
    draft_upd_by_cluster: dict[str, datetime] = {}
    if drafts_dir.is_dir():
        for draft in sorted(drafts_dir.glob("*.draft.md")):
            text = draft.read_text(encoding="utf-8", errors="replace")
            fm = _parse_frontmatter(text)
            doc_id = fm.get("doc_id", draft.stem)
            upd_str = fm.get("updated_at", "") or fm.get("frozen_at", "")
            dt = _extract_iso(upd_str)
            # The naive frontmatter parser also picks up cluster_id from the
            # nested cluster: block, flattened.
            cluster_id = fm.get("cluster_id", "") or draft.stem.replace(".draft", "").replace("cluster_", "")
            if dt:
                draft_upd_by_cluster[cluster_id] = max(
                    dt, draft_upd_by_cluster.get(cluster_id, dt))
            rows.append((draft.name, doc_id, "—", upd_str or "?", "SOURCE-ONLY",
                         "split canonical source — publication unit is D2/D3 (excluded from actionable)"))
    all_side = max(draft_upd_by_cluster.values()) if draft_upd_by_cluster else None

    n_out = n_pend = 0
    for _dtype, slug, label in SPLIT_DELIVERABLES:
        doc_id = f"{slug}-{product}"
        # If contributing clusters are recorded, compare only that subset's max
        # (avoids false OUTDATED).
        sources = _deliverable_source_clusters(proj, _dtype, slug)
        if sources:
            scoped = [dt for cid, dt in draft_upd_by_cluster.items() if cid in sources]
            draft_side = max(scoped) if scoped else all_side
        else:
            draft_side = all_side
        meta_path: Path | None = None
        if src_dir.is_dir():
            cands = sorted(src_dir.glob(f"{slug}-{product}.meta.json")) \
                or sorted(src_dir.glob(f"{slug}*.meta.json"))
            if cands:
                meta_path = cands[0]
        if meta_path is None:
            rows.append((f"{label} (assembled)", doc_id, "—", "no meta.json",
                         "PENDING", f"{slug}-{product}.meta.json missing — create via /cr split hierarchy"))
            n_pend += 1
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            rows.append((f"{label} (assembled)", doc_id, meta_path.name, str(e),
                         "UNKNOWN", "meta.json parse error"))
            continue
        page_id = str(meta.get("id", ""))
        if PLACEHOLDER.search(page_id) or not page_id:
            rows.append((f"{label} (assembled)", doc_id, meta_path.name, "id=PLACEHOLDER",
                         "PENDING", "Confluence page not yet created — create new via templates/standard/"))
            n_pend += 1
            continue
        pub = _get_meta_published(meta)
        status, reason = _classify(draft_side, pub)
        if status == "OUTDATED":
            n_out += 1
        rows.append((f"{label} (assembled)", doc_id, meta_path.name,
                     (draft_side.date().isoformat() if draft_side else "?"),
                     status, reason))
    return rows, n_out, n_pend


# ── Remote (Confluence) drift detection ─────────────────────────────────────

def _snapshot_path(proj: Path, page_id: str) -> Path:
    return proj / "reports" / ".confluence-snapshot" / f"{page_id}.json"


def _load_remote_snapshot(proj: Path, page_id: str) -> dict | None:
    """Load the snapshot the model saved via a wiki-connector lookup. None if absent."""
    p = _snapshot_path(proj, page_id)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _classify_remote(meta: dict, snapshot: dict | None) -> tuple[str, str, int | None, int | None]:
    """Compare remote version vs local last_published_version.

    Returns: (status, reason, local_ver, remote_ver)
    """
    if snapshot is None:
        return ("REMOTE-UNKNOWN",
                "no wiki snapshot — the model hasn't run a wiki-connector lookup yet",
                None, None)
    sync_block = meta.get("_sync") or {}
    local_ver = sync_block.get("last_published_version")
    remote_ver = (snapshot.get("version") or {}).get("number")
    if not isinstance(local_ver, int) or not isinstance(remote_ver, int):
        return ("REMOTE-UNKNOWN",
                f"missing version field (local={local_ver}, remote={remote_ver})",
                local_ver if isinstance(local_ver, int) else None,
                remote_ver if isinstance(remote_ver, int) else None)
    if remote_ver > local_ver:
        return ("REMOTE-DRIFT",
                f"Confluence v{remote_ver} > last push v{local_ver} — edited in Confluence",
                local_ver, remote_ver)
    # MEDIUM #11: remote < local suggests a Confluence page rollback or page-ID
    # mismatch — a regression signal
    if remote_ver < local_ver:
        return ("REMOTE-ROLLBACK",
                f"Confluence v{remote_ver} < last push v{local_ver} — suspected page rollback or page_id mismatch",
                local_ver, remote_ver)
    return ("SYNCED", f"Confluence v{remote_ver} == last push v{local_ver}", local_ver, remote_ver)


def _convert_tables_to_markdown(xml: str) -> str:
    """Convert <table><tr><td>...</td></tr></table> to markdown table format.

    fact_preservation_check needs the `| cell |` format to extract table cells.
    """
    def _table_repl(table_match: re.Match) -> str:
        table_body = table_match.group(1)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_body, re.DOTALL | re.IGNORECASE)
        if not rows:
            return "\n"
        md_lines: list[str] = []
        for i, row in enumerate(rows):
            cells = re.findall(
                r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.DOTALL | re.IGNORECASE,
            )
            # strip inner tags from cells + normalize whitespace/newlines
            clean_cells = []
            for c in cells:
                c = re.sub(r"<[^>]+>", "", c)
                c = re.sub(r"\s+", " ", c).strip()
                clean_cells.append(c)
            if not clean_cells:
                continue
            md_lines.append("| " + " | ".join(clean_cells) + " |")
            # add a header separator after the first row (whether all cells
            # were th, or just as the first row)
            if i == 0:
                md_lines.append("|" + "|".join(["---"] * len(clean_cells)) + "|")
        return "\n" + "\n".join(md_lines) + "\n"

    return re.sub(
        r"<table[^>]*>(.*?)</table>",
        _table_repl,
        xml,
        flags=re.DOTALL | re.IGNORECASE,
    )


def _strip_storage_xml(xml: str) -> str:
    """Convert Confluence Storage Format XML to markdown for review.

    Tables are preserved in markdown table format (fact_preservation_check
    compatible). Not a perfect conversion — its purpose is letting the PM see
    the difference in the merge-proposal. The actual body is applied by
    render_apply_inbox.py.
    """
    if not xml:
        return ""
    # strip ac:* / ri:* macro tags (opening and closing forms)
    text = re.sub(r"</?ac:[^>]+>", "", xml)
    text = re.sub(r"</?ri:[^>]+>", "", text)
    # unwrap CDATA (preserves code block bodies)
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
    # tables -> markdown (before other tags are stripped)
    text = _convert_tables_to_markdown(text)
    # headings -> markdown headers
    for level in range(1, 7):
        text = re.sub(
            rf"<h{level}[^>]*>(.*?)</h{level}>",
            lambda m, lv=level: "\n" + ("#" * lv) + " " + re.sub(r"<[^>]+>", "", m.group(1)).strip() + "\n",
            text, flags=re.DOTALL | re.IGNORECASE,
        )
    # lists
    text = re.sub(r"<li[^>]*>(.*?)</li>", lambda m: "- " + re.sub(r"<[^>]+>", "", m.group(1)).strip() + "\n", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"</?[uo]l[^>]*>", "\n", text)
    # paragraphs / line breaks
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</p>", "\n\n", text)
    text = re.sub(r"<p[^>]*>", "", text)
    # bold / italic -> markdown
    text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<i[^>]*>(.*?)</i>", r"*\1*", text, flags=re.DOTALL | re.IGNORECASE)
    # strip all remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # collapse consecutive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _write_merge_proposal(
    proj: Path,
    wo_id: str,
    page_id: str,
    local_ver: int | None,
    remote_ver: int | None,
    remote_snapshot: dict,
    draft_text: str,
) -> Path:
    """Generate a merge-proposal for PM review when REMOTE-DRIFT is detected."""
    inbox_dir = proj / "reports" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    out_path = inbox_dir / f"{wo_id}.merge-proposal.md"

    remote_storage = ((remote_snapshot.get("body") or {}).get("storage") or {}).get("value", "")
    remote_text = _strip_storage_xml(remote_storage)

    # strip frontmatter from the draft body (for easier comparison)
    fm_match = FRONTMATTER.match(draft_text)
    local_body = draft_text[fm_match.end():] if fm_match else draft_text

    # CRITICAL #2: the body that apply extracts is wrapped in HTML-comment
    # sentinels rather than ``` fences (so extraction stays safe even if the
    # Confluence body itself contains ```).
    remote_truncated = remote_text[:20000]
    remote_overflow = "" if len(remote_text) <= 20000 else f"\n\n_... truncated (full length {len(remote_text)} chars)_"
    local_truncated = local_body[:20000]
    local_overflow = "" if len(local_body) <= 20000 else f"\n\n_... truncated (full length {len(local_body)} chars)_"
    storage_truncated = remote_storage[:10000]
    storage_overflow = "" if len(remote_storage) <= 10000 else f"\n\n_... truncated (full length {len(remote_storage)} chars)_"

    lines = [
        f"# Merge Proposal — {wo_id} (REMOTE-DRIFT detected)",
        "",
        f"> Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"> page_id: `{page_id}`  ·  Confluence v{remote_ver}  vs  last push v{local_ver}",
        f"> Auto-generated (do not edit) — render_sync_check.py",
        "",
        "## How to proceed",
        "",
        "Compare the two bodies below, then choose one of:",
        "",
        f"- [ ] **Adopt full body** (overwrite the draft with the wiki body — handled by `/render --apply-inbox {wo_id}`)",
        "- [ ] **Manual review complete** (PM manually applies via /write etc.; this proposal is archived)",
        "",
        "If neither item is checked, calling `/render --apply-inbox` is a NOOP (the proposal is kept).",
        "When 'Adopt full body' is selected, fact_preservation_check runs automatically right after applying — blocks if fact loss is detected.",
        "",
        "---",
        "",
        f"## Confluence body (current v{remote_ver}) — used on apply",
        "",
        "<!-- confluence-body:start -->",
        remote_truncated + remote_overflow,
        "<!-- confluence-body:end -->",
        "",
        "## Local draft body (frontmatter excluded, for reference)",
        "",
        "<!-- local-body:start -->",
        local_truncated + local_overflow,
        "<!-- local-body:end -->",
        "",
        "---",
        "",
        "## Original Confluence Storage Format (reference only — not used directly on apply)",
        "",
        "<!-- storage-xml:start -->",
        storage_truncated + storage_overflow,
        "<!-- storage-xml:end -->",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def scan(hub_root: Path, product: str | None = None, with_remote: bool = False) -> int:
    projects_root = hub_root / "PROJECTS"
    if not projects_root.is_dir():
        print(f"[sync_check] no PROJECTS: {projects_root} — nothing to scan")
        return 0

    products = (
        [projects_root / product]
        if product
        else sorted(p for p in projects_root.iterdir() if p.is_dir())
    )

    total_outdated = 0
    total_pending = 0
    total_remote_drift = 0
    total_remote_unknown = 0

    for proj in products:
        pname = proj.name
        drafts_dir = proj / "drafts"
        src_dir = proj / "confluence-source"
        rows: list[tuple] = []
        # cache of this product's draft bodies (for merge-proposal generation)
        draft_text_cache: dict[str, str] = {}

        # branch on publication mode (fix-plan-dossier-publish-split).
        pub_mode = _read_publication_mode(proj)

        # ── split-deliverable: dossier is SOURCE-ONLY, publication is 2 units (D2/D3) ──
        if pub_mode == "split-deliverable":
            srows, s_out, s_pend = _scan_split(proj, drafts_dir, src_dir, pname)
            rows.extend(srows)
            total_outdated += s_out
            total_pending += s_pend

        # ── dossier-page (default): 1 draft = 1 page ────────────────────────
        elif drafts_dir.is_dir():
            for draft in sorted(drafts_dir.glob("*.draft.md")):
                text = draft.read_text(encoding="utf-8", errors="replace")
                fm = _parse_frontmatter(text)
                doc_id = fm.get("doc_id", draft.stem)
                upd_str = fm.get("updated_at", "") or fm.get("frozen_at", "")
                draft_upd = _extract_iso(upd_str)

                # Find the corresponding meta.json (per-dossier — fix-plan-dossier-publish).
                # In the dossier model, 1 dossier = 1 page, so each draft is
                # matched only against its own meta.json. A "first-meta
                # fallback" is not used, since it would wrongly match every
                # dossier to the same page (no meta -> PENDING).
                #
                # H3 (audit 2026-06-08): previously matching was done only via
                # meta **filename** substring, which meant a {WO_ID}.meta.json
                # created by cr (e.g. G2-K-PR-01) and the draft stem
                # (cluster_PR-01) could diverge, causing a permanent PENDING
                # report even after publication. Now it joins on the meta's
                # **internal identifiers** (wo_id/doc_id/cluster_id), same as
                # sync_emit. The legacy filename-substring match is kept as a fallback.
                stem_hint = draft.stem.replace(".draft", "")
                wo_id_fm = fm.get("wo_id", "")
                draft_keys = {
                    k.lower() for k in (stem_hint, doc_id, wo_id_fm) if k
                }
                # Deterministic join (audit 2026-06-11 gap 3): (1) exact match
                # on internal identifiers (2) exact match on filename stem
                # (3) legacy substring match (backward-compat fallback).
                # Previously (1)-(3) were combined into one condition and
                # relied on the first glob-sorted match, which could
                # mismatch similar IDs (PR-01 / PR-010). On multiple matches
                # within the same tier, log a warning and use the first
                # sorted entry (deterministic).
                meta_path: Path | None = None
                meta: dict | None = None
                if src_dir.is_dir():
                    cands: list[tuple[Path, dict | None]] = []
                    for f in sorted(src_dir.glob("*.meta.json")):
                        try:
                            cand = json.loads(f.read_text(encoding="utf-8", errors="replace"))
                        except Exception:
                            cand = None
                        cands.append((f, cand if isinstance(cand, dict) else None))

                    def _internal_ids(c: dict | None) -> set[str]:
                        if not c:
                            return set()
                        return {str(c[mk]).lower()
                                for mk in ("wo_id", "doc_id", "cluster_id") if c.get(mk)}

                    tiers = [
                        [(f, c) for f, c in cands if draft_keys & _internal_ids(c)],
                        [(f, c) for f, c in cands if f.stem.lower() in draft_keys],
                        [(f, c) for f, c in cands
                         if any(dk in f.stem.lower() for dk in draft_keys)],
                    ]
                    for matched in tiers:
                        if matched:
                            if len(matched) > 1:
                                names = ", ".join(f.name for f, _ in matched)
                                print(f"[sync_check] WARN: {pname}/{draft.name} multiple meta matches"
                                      f" ({names}) — using the first", file=sys.stderr)
                            meta_path, meta = matched[0]
                            break

                if meta_path is None:
                    rows.append((draft.name, doc_id, "—", "no meta.json", "PENDING",
                                 "no meta.json for this dossier — create/initialize the page via /cr"))
                    total_pending += 1
                    continue

                if meta is None:
                    rows.append((draft.name, doc_id, str(meta_path.name),
                                 "JSON parse error", "UNKNOWN", "meta.json parse error"))
                    continue

                # page_id placeholder check
                page_id = str(meta.get("id", ""))
                if PLACEHOLDER.search(page_id) or not page_id:
                    rows.append((draft.name, doc_id, meta_path.name, "id=PLACEHOLDER",
                                 "PENDING", "Confluence page not yet created — create new via templates/standard/"))
                    total_pending += 1
                    continue

                pub = _get_meta_published(meta)
                status, reason = _classify(draft_upd, pub)
                if status == "OUTDATED":
                    total_outdated += 1
                # add the forward-direction row
                rows.append((draft.name, doc_id, meta_path.name,
                             upd_str or "?", status, reason))

                # ── reverse-direction (Confluence remote drift) check ─────
                if with_remote and not PLACEHOLDER.search(page_id) and page_id:
                    snapshot = _load_remote_snapshot(proj, page_id)
                    r_status, r_reason, l_ver, r_ver = _classify_remote(meta, snapshot)
                    rows.append((
                        draft.name, doc_id, meta_path.name,
                        f"local v{l_ver} / remote v{r_ver}" if (l_ver or r_ver) else "—",
                        r_status, r_reason,
                    ))
                    if r_status == "REMOTE-DRIFT":
                        total_remote_drift += 1
                        # extract WO_ID: drafts/WO-NN.draft.md -> WO-NN
                        wo_id = draft.stem.replace(".draft", "")
                        try:
                            proposal_path = _write_merge_proposal(
                                proj, wo_id, page_id, l_ver, r_ver,
                                snapshot or {}, text,
                            )
                            print(f"[sync_check] {pname}: REMOTE-DRIFT {wo_id} "
                                  f"→ {proposal_path.relative_to(hub_root)}")
                        except Exception as exc:
                            print(f"[sync_check] WARN: failed to generate merge-proposal ({wo_id}): {exc}",
                                  file=sys.stderr)
                    elif r_status == "REMOTE-UNKNOWN":
                        total_remote_unknown += 1

        # ── scan common publication docs (D1 Requirements · D4 Meeting Notes · D5 Competitor Research) ──
        crows, c_out, c_pend = _scan_common_docs(proj, src_dir, pname)
        rows.extend(crows)
        total_outdated += c_out
        total_pending += c_pend

        # ── save report ──────────────────────────────────────────────────────
        reports = proj / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        out = reports / "sync-queue.md"

        n_out = sum(1 for r in rows if r[4] == "OUTDATED")
        n_pend = sum(1 for r in rows if r[4] == "PENDING")
        n_unk = sum(1 for r in rows if r[4] == "UNKNOWN")
        n_drift = sum(1 for r in rows if r[4] == "REMOTE-DRIFT")
        n_runk = sum(1 for r in rows if r[4] == "REMOTE-UNKNOWN")
        n_src = sum(1 for r in rows if r[4] == "SOURCE-ONLY")

        lines = [
            f"# sync-queue — {pname}",
            "",
            f"> Generated: {datetime.now().isoformat(timespec='seconds')}"
            f" · auto-generated by render_sync_check.py (do not edit)"
            + (f" · publication mode: {pub_mode}" if pub_mode != "dossier-page" else ""),
            f"> **OUTDATED: {n_out} · REMOTE-DRIFT: {n_drift} · PENDING: {n_pend}"
            f" · REMOTE-UNKNOWN: {n_runk} · UNKNOWN: {n_unk}**"
            + (f" · SOURCE-ONLY: {n_src}" if n_src else ""),
            "",
            "| File | doc_id | meta.json | Baseline | Status | Reason |",
            "|---|---|---|---|---|---|",
        ]
        if rows:
            for fname, did, mname, upd, st, why in rows:
                lines.append(f"| {fname} | `{did}` | {mname} | {upd} | **{st}** | {why} |")
        else:
            lines.append("| _(none)_ | — | — | — | — | drafts/ or inputs/ is empty |")

        lines += [
            "",
            "## Handling criteria",
            "- **OUTDATED**: no push since the draft was modified — sync via `/render --push`",
            "- **REMOTE-DRIFT**: Confluence is newer (edited by the PM in Confluence) — review `reports/inbox/{WO}.merge-proposal.md`, then `/render --apply-inbox {WO}` or apply manually",
            "- **PENDING**: Confluence page not yet created — create new from the templates/standard/ default template, then initialize meta.json",
            "- **REMOTE-UNKNOWN**: no wiki snapshot — the model hasn't yet looked up the page via a wiki connector and saved it to `reports/.confluence-snapshot/{id}.json`",
            "- **UNKNOWN**: could not parse updated_at/last_published_at — check the date format (ISO 8601 recommended)",
            "- **SYNCED**: normal — no further action needed",
        ]
        if n_src:
            lines.append(
                "- **SOURCE-ONLY**: canonical dossier source in split-deliverable mode — "
                "not a publication unit, so excluded from actionable (see the D2/D3 deliverable rows)"
            )
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[sync_check] {pname}: OUTDATED={n_out} REMOTE-DRIFT={n_drift}"
              f" PENDING={n_pend} REMOTE-UNKNOWN={n_runk} UNKNOWN={n_unk}"
              f" → {out.relative_to(hub_root)}")

    total_actionable = total_outdated + total_pending + total_remote_drift
    print(f"[sync_check] done — OUTDATED {total_outdated} REMOTE-DRIFT {total_remote_drift}"
          f" PENDING {total_pending} REMOTE-UNKNOWN {total_remote_unknown}"
          + ("" if total_actionable == 0 else " (sync needed)"))
    return 1 if total_actionable > 0 else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Draft<->Confluence bidirectional sync scan")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", default=None, help="PROJECTS/<product> (omit for all)")
    ap.add_argument("--with-remote", action="store_true",
                    help="also compare against the remote version in reports/.confluence-snapshot/ (REMOTE-DRIFT detection)")
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    return scan(args.hub_root, args.product, with_remote=args.with_remote)


if __name__ == "__main__":
    sys.exit(main())
