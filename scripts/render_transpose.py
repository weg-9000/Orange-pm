#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cluster Draft → Deliverable Transpose (Phase 5F).

Publication-mode dependent (fix-plan-dossier-publish-split):
    transpose() is **re-enabled in the split-deliverable publication mode**
    (graph/project-mode.json `publication_mode: split-deliverable`).
    - dossier-page (default): 1 feature definition = 1 page. transpose not called.
                             (render/SKILL.md step 3-A, publication-map.md §0)
    - split-deliverable    : dossier §1 → D2 policy definition / §2 → D3 screen
                             design spec, published split. This module's
                             transpose() owns that assembly.
    The P3 derived views (`render_fr_capability_view`·`render_cross_cutting_matrix`)
    are valid in both modes (only the link targets differ per mode).

    ⚠️ FLAG: §0/§5/§6 are not reflected into D2/D3 (policy is self-contained in
       §1). If a dossier drops D2/D3 from deliverable_targets, that cluster is
       omitted — see the split-branch caution note in render/SKILL.md.

Purpose:
    Deterministic transpose function assembling Track A (Full Product) cluster
    work outputs (drafts/cluster_*.draft.md) into single pages of publication
    deliverables (D2 policy / D3 screen / Dα etc).

    Extract only the §1 / §2 / §α panel blocks of cluster_drafts → sort by
    capability + cluster_id per deliverable → rewrap as chapter panels.
    §3 (data/dependencies) and §4 (OQ/UPSTREAM_GAP) are excluded from publish.

Spec SSoT:
    - skills/render/publication-map.md §2 (transpose matrix)
    - skills/render/publication-map.md §4 (function interface)
    - skills/render/publication-map.md §7 (chapter naming)
    - templates/standard/cluster-draft.md (cluster 4-section format)
    - templates/standard/D2_policy.md / D3_screen.md / Dα_*.md (target formats)

Behavior:
    1. parse cluster_draft frontmatter (cluster.capability / cluster_id /
       cluster_name + deliverable_targets)
    2. select only clusters whose deliverable_targets include deliverable_type
    3. § section mapping per deliverable_type:
         - D2          → extract cluster §1 panel block
         - D3          → extract cluster §2 panel block
         - Da_api      → extract cluster §α (api) panel block
         - Da_db       → extract cluster §α (db) panel block
         - Da_migration→ extract cluster §α (migration) panel block
    4. sort (deterministic): capability alphabetical → cluster_id natural order
    5. chapter panel assembly (publication-map.md §7 naming):
         ::: {.panel section="§{N} {Capability} / {ClusterName} ({cluster_id})"}
         ## §{N} {Capability} / {ClusterName} ({cluster_id})
         {original §1/§2/§α body — inserted after removing the panel wrapper}
         :::
    6. D3 only: the §2 sections of common_shell_clusters go into a separate
       `§Appendix A — Common Shell` panel
    7. frontmatter assembly (target_template's frontmatter + refresh when given,
       otherwise a deliverable_type based default frontmatter)
    8. returns a single MD string — the caller (e.g. render skill) converts to
       XML via md_to_storage.py

CLI:
    python render_transpose.py \\
        --cluster-drafts drafts/cluster_*.draft.md \\
        --deliverable D2 \\
        --output reports/render/D2_policy.assembled.md \\
        [--template orange-pm-plugin/templates/standard/D2_policy.md] \\
        [--common-shell drafts/cluster_common_*.draft.md]   # D3 only

exit code:
    0 = success
    1 = parse error (cluster_draft frontmatter / panel structure violation)
    2 = no eligible clusters (deliverable_targets matched 0 items)
    3 = IO error
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml  # PyYAML 6.0.x — non-stdlib (same policy as md_to_storage.py)
except Exception:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


# ── constants ────────────────────────────────────────────────────────────────

# spec §2 / §4 — § keywords to extract per deliverable_type
# extraction is a partial match on the cluster panel section attribute text
# (see the panel section labels of cluster-draft.md)
DELIVERABLE_SECTION_MAP: dict[str, str] = {
    "D2": "§1",
    "D3": "§2",
    "Da_api": "§α",
    "Da_db": "§α",
    "Da_migration": "§α",
}

# Da_* extra keywords (separates api / db / migration within §α)
# cluster-draft.md has optional §α-API / §α-DB / §α-MIG panels per type.
# Panels whose section starts with "§α" and contains a keyword below are
# extracted per deliverable.
DA_TYPE_KEYWORDS: dict[str, list[str]] = {
    "Da_api": ["api", "API"],
    "Da_db": ["db", "DB", "data"],
    "Da_migration": ["migration", "mig"],
}

VALID_DELIVERABLES = set(DELIVERABLE_SECTION_MAP.keys())

# regexes
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# panel block — capture section attribute + body
# fenced div: ::: {.panel section="..." style="..."}
#             ...
#             :::
PANEL_OPEN_RE = re.compile(
    r'^:::\s*\{\.panel\s+([^}]*)\}\s*$', re.MULTILINE
)
PANEL_SECTION_ATTR_RE = re.compile(r'section\s*=\s*"([^"]*)"')

# for cluster_id natural sort — split letters/digits
NATSORT_RE = re.compile(r"(\d+)|(\D+)")


# ── Frontmatter ──────────────────────────────────────────────────────────────


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter → (dict, body).

    Very limited fallback without PyYAML (top-level scalars only) — cluster
    structure is nested so yaml is required. Returns an empty dict when absent.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    body = text[m.end():]
    fm_text = m.group(1)
    if yaml is not None:
        try:
            data = yaml.safe_load(fm_text) or {}
            if not isinstance(data, dict):
                return {}, body
            return data, body
        except Exception:
            return {}, body
    return {}, body


def _render_frontmatter(fm: dict) -> str:
    """dict → YAML frontmatter MD block.

    Uses PyYAML (allow_unicode, sort_keys=False).
    """
    if yaml is None:
        # naive fallback — top-level scalars only
        lines = ["---"]
        for k, v in fm.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                lines.append(f"{k}: {v if v is not None else 'null'}")
        lines.append("---")
        return "\n".join(lines) + "\n"
    body = yaml.safe_dump(
        fm, allow_unicode=True, sort_keys=False, default_flow_style=False
    )
    return f"---\n{body}---\n"


# ── cluster metadata load / validation ───────────────────────────────────────


class TransposeError(Exception):
    """Parse/structure error at the transpose stage."""


def _load_cluster_meta(path: Path) -> dict:
    """cluster_draft file → metadata dict.

    Returns:
        {
            "path": Path,
            "text": str,              # full body (frontmatter excluded)
            "frontmatter": dict,      # parsed frontmatter
            "capability": str,
            "cluster_id": str,
            "cluster_name": str,
            "deliverable_targets": list[str],
            "is_common_shell": bool,
            "title": str,             # frontmatter title
            "wo_id": str,             # frontmatter wo_id
        }

    Raises:
        TransposeError — frontmatter or cluster metadata missing / malformed
    """
    if not path.exists():
        raise TransposeError(f"cluster_draft file not found: {path}")
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise TransposeError(f"failed to read cluster_draft: {path} — {exc}")

    fm, body = _parse_frontmatter(raw)
    if not fm:
        raise TransposeError(
            f"failed to parse cluster_draft frontmatter: {path} — "
            "malformed YAML or PyYAML not installed"
        )

    cluster = fm.get("cluster")
    if not isinstance(cluster, dict):
        raise TransposeError(
            f"'cluster:' block missing in cluster_draft frontmatter: {path}"
        )

    capability = str(cluster.get("capability", "")).strip()
    cluster_id = str(cluster.get("cluster_id", "")).strip()
    cluster_name = str(cluster.get("cluster_name", "")).strip()
    if not capability or not cluster_id:
        raise TransposeError(
            f"cluster.capability / cluster.cluster_id missing: {path}"
        )

    targets_raw = fm.get("deliverable_targets") or []
    if isinstance(targets_raw, str):
        # single-line expression fallback
        targets = [t.strip() for t in targets_raw.strip("[]").split(",") if t.strip()]
    elif isinstance(targets_raw, list):
        targets = [str(t).strip() for t in targets_raw]
    else:
        targets = []

    is_common_shell = bool(fm.get("is_common_shell", False))

    # related_screens — for D3 screen-level chapter (split-deliverable) assembly.
    # supports both a list and the single-line "[a, b]" expression fallback.
    rs_raw = fm.get("related_screens") or []
    if isinstance(rs_raw, str):
        related_screens = [
            s.strip().strip('"').strip("'")
            for s in rs_raw.strip("[]").split(",")
            if s.strip()
        ]
    elif isinstance(rs_raw, list):
        related_screens = [str(s).strip() for s in rs_raw if str(s).strip()]
    else:
        related_screens = []

    return {
        "path": path,
        "text": body,
        "frontmatter": fm,
        "capability": capability,
        "cluster_id": cluster_id,
        "cluster_name": cluster_name or cluster_id,
        "deliverable_targets": targets,
        "is_common_shell": is_common_shell,
        "related_screens": related_screens,
        "primary_screen": str(fm.get("primary_screen") or "").strip(),
        "title": str(fm.get("title", "")).strip(),
        "wo_id": str(fm.get("wo_id", "")).strip(),
    }


# ── panel block extraction ──────────────────────────────────────────────────


def _iter_panel_blocks(body: str) -> list[tuple[str, str, str, int, int]]:
    """Extract every panel block from the body.

    Returns: list of (section_attr_text, attr_inner, inner_body, start, end)
        - section_attr_text: panel section attribute value (e.g. "§1 Policy Decisions (D2 ...)")
        - attr_inner: full inside of the panel `{...}` (for debugging)
        - inner_body: panel inner body (h2/sub-content — `:::` excluded)
        - start, end: raw positions in the body (whole panel — `:::` lines included)

    Supports nested fenced divs (e.g. .info / .expand inside a panel) — depth counter.
    """
    out: list[tuple[str, str, str, int, int]] = []
    lines = body.splitlines(keepends=True)
    # precompute line start offsets
    offsets = [0]
    for ln in lines:
        offsets.append(offsets[-1] + len(ln))

    i = 0
    while i < len(lines):
        ln = lines[i].rstrip("\n")
        m = PANEL_OPEN_RE.match(ln)
        if m:
            attr_inner = m.group(1)
            sec_m = PANEL_SECTION_ATTR_RE.search(attr_inner)
            if not sec_m:
                # panel without a section attribute — skip (TBD items etc.)
                i += 1
                continue
            section_attr = sec_m.group(1)
            # find the closing ::: — depth counter
            depth = 1
            j = i + 1
            body_lines: list[str] = []
            while j < len(lines):
                lj = lines[j].rstrip("\n")
                if lj.startswith(":::"):
                    # opening ::: { ... } or closing :::
                    if re.match(r"^:::\s*\{", lj):
                        depth += 1
                        body_lines.append(lines[j])
                    elif re.match(r"^:::\s*$", lj):
                        depth -= 1
                        if depth == 0:
                            # closing panel
                            inner = "".join(body_lines)
                            out.append(
                                (
                                    section_attr,
                                    attr_inner,
                                    inner,
                                    offsets[i],
                                    offsets[j + 1],
                                )
                            )
                            i = j + 1
                            break
                        body_lines.append(lines[j])
                    else:
                        body_lines.append(lines[j])
                else:
                    body_lines.append(lines[j])
                j += 1
            else:
                # unclosed — structure violation
                raise TransposeError(
                    f"unclosed panel block (section={section_attr!r})"
                )
            continue
        i += 1
    return out


def _extract_panel_section(
    body: str, section_keyword: str, *, type_keywords: list[str] | None = None
) -> tuple[str, str] | None:
    """Return the body of the first panel whose section attribute starts with `section_keyword`.

    Args:
        body: cluster_draft body without frontmatter
        section_keyword: partial-match key (e.g. "§1", "§2", "§α")
        type_keywords: for Da_*, extra keys separating types within §α (e.g. ["api"])

    Returns:
        (section_attr_text, inner_body) or None (section absent)
    """
    blocks = _iter_panel_blocks(body)
    for sec, _attr, inner, _s, _e in blocks:
        if not sec.startswith(section_keyword):
            # some panels look like "§1 Policy Decisions (D2 → ...)" so match with startswith
            continue
        if type_keywords:
            # for §α, additional per-type keyword matching
            if not any(kw.lower() in sec.lower() for kw in type_keywords):
                continue
        return (sec, inner.rstrip() + "\n")
    return None


# ── sorting ─────────────────────────────────────────────────────────────────


def _natural_key(s: str) -> tuple:
    """Natural sort key — 'PR-01' < 'PR-02' < 'PR-10'.

    e.g. "PR-01" → (("PR-",), (1,))
    """
    out: list[Any] = []
    for m in NATSORT_RE.finditer(s):
        num, txt = m.group(1), m.group(2)
        if num is not None:
            out.append((1, int(num)))
        else:
            out.append((0, txt.lower()))
    return tuple(out)


def _sort_clusters(clusters: list[dict]) -> list[dict]:
    """publication-map.md §2 deterministic sort:

        1st: capability alphabetical (case-insensitive)
        2nd: cluster_id natural order (PR-01 < PR-02 < PR-10)
    """
    return sorted(
        clusters,
        key=lambda c: (c["capability"].lower(), _natural_key(c["cluster_id"])),
    )


# ── P3 derived views (cluster_map.json indexes → markdown panels) ─────────────
# DEC-C / DEC-F: takes cluster_map.json's fr_index / module_index as SSoT and
# synthesizes markdown panels deterministically and purely (no side effects).
# No fixed prose TOC — on re-clustering (threshold changes) only the index
# changes and the views follow automatically (zero manual edits).
# Works generically for any module (email/logging/auth…) — no email-specific hardcoding.


def render_fr_capability_view(fr_index: dict[str, dict]) -> str:
    """D1 capability group-by derived view (DEC-C).

    Groups `cluster_map.json`'s `fr_index` ({FR-id: {capability, cluster_id}})
    by capability and returns a panel markdown listing the FRs under each
    capability plus an anchor link to the corresponding feature definition
    (cluster_id).

    Deterministic sort:
        - capability alphabetical (case-insensitive)
        - FRs within a capability in natural order (FR-1 < FR-2 < FR-10)

    Args:
        fr_index: FR → {capability, cluster_id} authoritative index (SSoT).

    Returns:
        `::: {.panel section="..."}` panel markdown string. For empty input,
        returns a panel with only a notice (deterministic).
    """
    section = "§D1 FR groups by capability (derived from cluster_map.fr_index)"
    parts: list[str] = [
        f'::: {{.panel section="{section}"}}\n',
        f"## {section}\n\n",
        "> This view is auto-synthesized from `cluster_map.json` `fr_index` "
        "(no manual edits · follows re-clustering automatically).\n\n",
    ]

    # group-by capability
    groups: dict[str, list[tuple[str, str]]] = {}
    for fr, meta in (fr_index or {}).items():
        cap = str((meta or {}).get("capability", "")).strip() or "(unassigned)"
        cid = str((meta or {}).get("cluster_id", "")).strip()
        groups.setdefault(cap, []).append((str(fr), cid))

    if not groups:
        parts.append("_No FRs mapped._\n")
        parts.append(":::\n")
        return "".join(parts)

    for cap in sorted(groups, key=lambda c: c.lower()):
        frs = sorted(groups[cap], key=lambda t: _natural_key(t[0]))
        parts.append(f"### {cap}\n\n")
        for fr, cid in frs:
            if cid:
                # feature-definition (cluster) anchor — cross-link via cluster_id
                parts.append(f"- **{fr}** → [feature definition {cid}](#{cid})\n")
            else:
                parts.append(f"- **{fr}** → (cluster unmapped)\n")
        parts.append("\n")

    parts.append(":::\n")
    return "".join(parts).rstrip("\n") + "\n"


def render_cross_cutting_matrix(
    module_index: dict[str, list[dict]],
    node_titles: dict[str, str] | None = None,
) -> str:
    """Cross-cutting concern matrix derived view (DEC-F).

    From `cluster_map.json`'s `module_index`
    ({moduleDocId: [{cluster_id, capability, source, via, section}, ...]}),
    synthesizes a matrix panel showing at a glance "which features (clusters)
    reference this module" for every shared module. Works generically for any
    module (email, logging, auth etc. — no module-specific hardcoding).

    One markdown table per module:
        | capability | cluster_id | source | via | section |
    Rows are sorted deterministically (capability → cluster_id natural → source → via).
    Modules themselves in docId alphabetical order.

    Args:
        module_index: module → referencing cluster record list (reverse index, SSoT).
        node_titles: (optional) module docId → human-readable title mapping. If
            present, headers read "title (docId)", otherwise docId only.

    Returns:
        `::: {.panel section="..."}` panel markdown string. For empty input,
        returns a panel with only a notice (deterministic).
    """
    section = "§Cross-cutting concern matrix (derived from cluster_map.module_index)"
    titles = node_titles or {}
    parts: list[str] = [
        f'::: {{.panel section="{section}"}}\n',
        f"## {section}\n\n",
        "> Reverse index of features (clusters) referencing shared modules. "
        "Auto-synthesized from `cluster_map.json` `module_index` (SSoT · no manual edits).\n\n",
    ]

    modules = module_index or {}
    if not modules:
        parts.append("_No cross-cutting modules._\n")
        parts.append(":::\n")
        return "".join(parts)

    for module_id in sorted(modules):
        rows = modules[module_id] or []
        title = str(titles.get(module_id, "")).strip()
        heading = f"{title} ({module_id})" if title else module_id
        parts.append(f"### {heading}\n\n")

        if not rows:
            parts.append("_No referencing features._\n\n")
            continue

        parts.append("| capability | cluster_id | source | via | section |\n")
        parts.append("|---|---|---|---|---|\n")
        sorted_rows = sorted(
            rows,
            key=lambda r: (
                str(r.get("capability", "")).lower(),
                _natural_key(str(r.get("cluster_id", ""))),
                _natural_key(str(r.get("source", ""))),
                str(r.get("via", "")),
            ),
        )
        for r in sorted_rows:
            cap = str(r.get("capability", "")).strip() or "—"
            cid = str(r.get("cluster_id", "")).strip() or "—"
            src = str(r.get("source", "")).strip() or "—"
            via = str(r.get("via", "")).strip() or "—"
            sec = str(r.get("section") or "").strip() or "—"
            parts.append(f"| {cap} | {cid} | {src} | {via} | {sec} |\n")
        parts.append("\n")

    parts.append(":::\n")
    return "".join(parts).rstrip("\n") + "\n"


# ── chapter assembly ────────────────────────────────────────────────────────


def _strip_first_h2(body: str) -> str:
    """Remove the first line of an extracted panel body if it is `## §...`.

    The original §1 body starts with an `## §1 Policy Decisions` h2 — the
    chapter panel adds its own h2, so the original h2 is dropped to avoid
    duplication.
    """
    lines = body.lstrip("\n").splitlines(keepends=True)
    if not lines:
        return body
    first = lines[0].rstrip("\n").strip()
    if re.match(r"^##\s+§", first):
        # remove the h2 line plus the blank line right after it
        rest = lines[1:]
        while rest and rest[0].strip() == "":
            rest = rest[1:]
        return "".join(rest)
    return body


def _assemble_chapter(
    cluster: dict, section_body: str, chapter_num: int
) -> str:
    """Extracted § body of a single cluster → chapter panel MD.

    publication-map.md §7 naming:
        §{N} {Capability} / {ClusterName} ({cluster_id})
    """
    cap = cluster["capability"]
    name = cluster["cluster_name"]
    cid = cluster["cluster_id"]
    title = f"§{chapter_num} {cap} / {name} ({cid})"

    inner = _strip_first_h2(section_body).rstrip() + "\n"

    return (
        f'::: {{.panel section="{title}"}}\n'
        f"## {title}\n\n"
        f"{inner}"
        ":::\n"
    )


def _assemble_common_shell_appendix(
    common_clusters: list[dict], section_keyword: str
) -> str:
    """Assemble the D3 common-shell appendix panel.

    Extracts each common_cluster's §2 → collected in sub §α / §α-1 form.
    """
    if not common_clusters:
        return ""

    parts = ['::: {.panel section="§Appendix A — Common Shell"}\n']
    parts.append("## §Appendix A — Common Shell\n\n")
    parts.append(
        "> This appendix holds the screen design of the common screen shells "
        "(NavShell / AuthFlow etc.) shared by all clusters.\n\n"
    )
    sorted_common = _sort_clusters(common_clusters)
    for i, cluster in enumerate(sorted_common, start=1):
        extracted = _extract_panel_section(cluster["text"], section_keyword)
        if not extracted:
            sys.stderr.write(
                f"[render_transpose] WARN: common-shell cluster "
                f"{cluster['cluster_id']} has no {section_keyword} section — skipped\n"
            )
            continue
        _sec, inner = extracted
        title = (
            f"Appendix A.{i} {cluster['cluster_name']} ({cluster['cluster_id']})"
        )
        inner = _strip_first_h2(inner).rstrip() + "\n\n"
        parts.append(f"### {title}\n\n")
        parts.append(inner)
    parts.append(":::\n")
    return "".join(parts)


# ── D3 screen-level chapters (split-deliverable — fix-plan-dossier-publish-split) ─

# screen ID token — auxiliary pattern detecting screen tagging in §2 headings even when related_screens is empty.
SCREEN_ID_RE = re.compile(r"\bSCR-[A-Za-z0-9]+\b")
HEADING_RE = re.compile(r"^(#{2,6})\s+(.*)$")


def _strip_first_heading(body: str) -> str:
    """Remove the first line if it is a heading of any level (## ~ ######), plus the blank line after."""
    lines = body.lstrip("\n").splitlines(keepends=True)
    if lines and HEADING_RE.match(lines[0].rstrip("\n")):
        rest = lines[1:]
        while rest and rest[0].strip() == "":
            rest = rest[1:]
        return "".join(rest)
    return body


def _screen_name_from_heading(heading_text: str, sid: str) -> str:
    """Extract the screen name from heading text — strips the leading §x-y token, screen ID, parens."""
    t = re.sub(r"^§\S+\s*", "", heading_text)  # strip leading §2-1 etc.
    t = t.replace(f"({sid})", "").replace(sid, "")
    t = t.strip(" ()[]—-:·\t")
    return t or sid


def _split_by_screen_headings(
    body: str, screen_ids: list[str]
) -> list[tuple[str, str, str]]:
    """Extract heading ranges tagged with screen IDs from the §2 body.

    If a heading (## ~ ######) text contains one of screen_ids (or the SCR-
    pattern), the range from that heading up to just before the next same/upper
    level heading is one screen section.

    Returns: [(screen_id, heading_text, section_md), ...] (order of appearance)
    """
    lines = body.splitlines(keepends=True)
    idset = [s for s in screen_ids if s]
    heads: list[tuple[int, int, str, str | None]] = []  # (idx, level, text, sid)
    for i, ln in enumerate(lines):
        m = HEADING_RE.match(ln.rstrip("\n"))
        if not m:
            continue
        level, text = len(m.group(1)), m.group(2).strip()
        sid: str | None = None
        for s in idset:
            if s in text:
                sid = s
                break
        if sid is None:
            mm = SCREEN_ID_RE.search(text)
            if mm:
                sid = mm.group(0)
        heads.append((i, level, text, sid))

    sections: list[tuple[str, str, str]] = []
    for hi, (idx, level, text, sid) in enumerate(heads):
        if sid is None:
            continue
        end = len(lines)
        for (idx2, level2, _t2, _s2) in heads[hi + 1:]:
            if level2 <= level:
                end = idx2
                break
        section_md = "".join(lines[idx:end]).rstrip() + "\n"
        sections.append((sid, text, section_md))
    return sections


def _render_screen_index(
    screen_to_clusters: dict[str, list[dict]], screen_names: dict[str, str]
) -> str:
    """Screen index panel — lists the related_screens union in screen-ID natural order."""
    parts = [
        '::: {.panel section="§Screen Index"}\n',
        "## §Screen Index\n\n",
        "> This index is auto-synthesized from the union of `related_screens` "
        "in cluster_*.draft.md frontmatter (no manual edits).\n\n",
        "| Screen ID | Screen Name | Source cluster |\n",
        "|---|---|---|\n",
    ]
    for sid in sorted(screen_to_clusters, key=_natural_key):
        clusters = screen_to_clusters[sid]
        src = " · ".join(
            f"{c['capability']} / {c['cluster_name']} ({c['cluster_id']})"
            for c in clusters
        ) or "—"
        parts.append(f"| {sid} | {screen_names.get(sid, '—') or '—'} | {src} |\n")
    parts.append(":::\n")
    return "".join(parts)


def _assemble_d3_screen_chapters(
    eligible: list[dict],
) -> tuple[str, list[str]] | None:
    """split-deliverable D3 — screen-level chapter assembly.

    Finds screen-ID tagged headings in each cluster's §2 body and reorganizes
    by screen. If no screen tagging exists at all, returns None so the caller
    falls back to cluster-level chapters (+WARN).

    Returns:
        (screen_index_md, [chapter_md, ...]) or None (fallback signal)
    """
    section_keyword = DELIVERABLE_SECTION_MAP["D3"]

    # 1. extract §2 per cluster
    per_cluster: list[tuple[dict, str]] = []
    for meta in eligible:
        extracted = _extract_panel_section(meta["text"], section_keyword)
        if not extracted:
            sys.stderr.write(
                f"[render_transpose] WARN: {meta['cluster_id']} has no "
                f"{section_keyword} section — skipped\n"
            )
            continue
        per_cluster.append((meta, _strip_first_h2(extracted[1])))

    if not per_cluster:
        return None

    # 2. related_screens union → source mapping
    screen_to_clusters: dict[str, list[dict]] = {}
    for meta in eligible:
        for s in meta["related_screens"]:
            screen_to_clusters.setdefault(s, []).append(meta)

    # 3. collect §2 screen-tagged headings
    universe = sorted(
        {s for meta in eligible for s in meta["related_screens"]},
        key=_natural_key,
    )
    by_screen: dict[str, dict] = {}
    screen_names: dict[str, str] = {}
    for meta, s2 in per_cluster:
        ids = meta["related_screens"] or universe
        for sid, htext, smd in _split_by_screen_headings(s2, ids):
            entry = by_screen.setdefault(sid, {"parts": []})
            entry["parts"].append((meta, smd))
            screen_names.setdefault(sid, _screen_name_from_heading(htext, sid))
            screen_to_clusters.setdefault(sid, [])
            if meta not in screen_to_clusters[sid]:
                screen_to_clusters[sid].append(meta)

    if not by_screen:
        # no screen tagging at all — cluster-level fallback (WARN at the call site)
        return None

    # 4. emit screen-level chapters (Screen ID natural order)
    chapters: list[str] = []
    for n, sid in enumerate(sorted(by_screen, key=_natural_key), start=1):
        name = screen_names.get(sid) or sid
        title = f"§{n} {name} ({sid})"
        body_parts: list[str] = []
        multi = len(by_screen[sid]["parts"]) > 1
        for meta, smd in by_screen[sid]["parts"]:
            inner = _strip_first_heading(smd).rstrip()
            if multi:
                body_parts.append(
                    f"### {meta['cluster_name']} ({meta['cluster_id']})\n\n{inner}\n"
                )
            else:
                body_parts.append(inner + "\n")
        chapters.append(
            f'::: {{.panel section="{title}"}}\n'
            f"## {title}\n\n"
            + "\n".join(body_parts).rstrip()
            + "\n:::\n"
        )

    screen_index_md = _render_screen_index(screen_to_clusters, screen_names)
    return screen_index_md, chapters


# ── target_template / default frontmatter ───────────────────────────────────


def _default_frontmatter(deliverable_type: str) -> dict:
    """Generate a deliverable_type based default frontmatter when there is no target_template.

    Minimal skeleton following the D2_policy.md / D3_screen.md / Dα_*.md formats.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    title_map = {
        "D2": "[Policy Definition] {{PRODUCT_NAME}}",
        "D3": "[Screen Design Spec] {{PRODUCT_NAME}}",
        "Da_api": "[API Spec] {{PRODUCT_NAME}}",
        "Da_db": "[DB Schema] {{PRODUCT_NAME}}",
        "Da_migration": "[Migration Plan] {{PRODUCT_NAME}}",
    }
    type_map = {
        "D2": "policy",
        "D3": "screen",
        "Da_api": "etc",
        "Da_db": "etc",
        "Da_migration": "etc",
    }
    related_links_map = {
        "D2": [
            "[[page:[Requirements Definition] {{PRODUCT_NAME}}]]",
            "[[page:[Screen Design Spec] {{PRODUCT_NAME}}]]",
        ],
        "D3": [
            "[[page:[Requirements Definition] {{PRODUCT_NAME}}]]",
            "[[page:[Policy Definition] {{PRODUCT_NAME}}]]",
        ],
        "Da_api": [
            "[[page:[Policy Definition] {{PRODUCT_NAME}}]]",
            "[[page:[Screen Design Spec] {{PRODUCT_NAME}}]]",
        ],
        "Da_db": [
            "[[page:[Policy Definition] {{PRODUCT_NAME}}]]",
        ],
        "Da_migration": [
            "[[page:[Policy Definition] {{PRODUCT_NAME}}]]",
        ],
    }
    related_block = "\n".join(
        f"            - {link}" for link in related_links_map[deliverable_type]
    )
    header_body = (
        f"**This document is the canonical "
        f"{title_map[deliverable_type].split(']')[0][1:]} of {{{{PRODUCT_NAME}}}}.**\n\n"
        f"doc_id: {{{{DOC_ID}}}} version: {{{{VERSION}}}} last modified: {{{{DATE}}}}"
    )
    return {
        "title": title_map[deliverable_type],
        "type": type_map[deliverable_type],
        "layer": "C",
        "version": 1.0,
        "last_updated": today,
        "publication": {
            "header": {"style": "info", "body": header_body},
            "meta": {
                "layout": "two_equal",
                "cells": [
                    {
                        "panel": {
                            "title": "References",
                            "body": (
                                "**Related documents**\n\n"
                                + "\n".join(
                                    f"- {l}"
                                    for l in related_links_map[deliverable_type]
                                )
                            ),
                        }
                    },
                    {"change_history": 3},
                ],
            },
        },
        "transposed_from": "cluster_drafts (render_transpose.py)",
        "transposed_at": datetime.now().isoformat(timespec="seconds"),
    }


def _apply_template_frontmatter(
    template_path: Path, deliverable_type: str
) -> dict:
    """Load + refresh the target_template's frontmatter.

    - replace last_updated with today
    - add transposed_from / transposed_at metadata
    """
    if not template_path.exists():
        raise TransposeError(f"target_template not found: {template_path}")
    try:
        raw = template_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise TransposeError(
            f"failed to read target_template: {template_path} — {exc}"
        )
    fm, _body = _parse_frontmatter(raw)
    if not fm:
        # fall back to the default when the template has no frontmatter
        sys.stderr.write(
            f"[render_transpose] WARN: target_template has no frontmatter — "
            f"using defaults: {template_path}\n"
        )
        return _default_frontmatter(deliverable_type)
    fm["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    fm["transposed_from"] = "cluster_drafts (render_transpose.py)"
    fm["transposed_at"] = datetime.now().isoformat(timespec="seconds")
    return fm


# ── main transpose function ─────────────────────────────────────────────────


def transpose(
    cluster_drafts: list[Path],
    deliverable_type: str,
    *,
    common_shell_clusters: list[Path] | None = None,
    target_template: Path | None = None,
) -> str:
    """Extract and assemble the deliverable_type sections from cluster_drafts → MD source.

    Args:
        cluster_drafts: list of cluster_draft file paths
        deliverable_type: "D2" | "D3" | "Da_api" | "Da_db" | "Da_migration"
        common_shell_clusters: G2-COMMON-* clusters (D3 only — ignored for other types)
        target_template: skeleton frontmatter source (optional)

    Returns:
        MD string (frontmatter + chapters + common-shell appendix for D3 only)

    Raises:
        TransposeError — parse / match / structure error
        ValueError — invalid deliverable_type
    """
    if deliverable_type not in VALID_DELIVERABLES:
        raise ValueError(
            f"invalid deliverable_type: {deliverable_type!r}. "
            f"allowed: {sorted(VALID_DELIVERABLES)}"
        )

    # 1. load + filter cluster_drafts
    section_keyword = DELIVERABLE_SECTION_MAP[deliverable_type]
    type_keywords = DA_TYPE_KEYWORDS.get(deliverable_type)

    eligible: list[dict] = []
    for path in cluster_drafts:
        try:
            meta = _load_cluster_meta(path)
        except TransposeError as exc:
            sys.stderr.write(
                f"[render_transpose] WARN: {path} skip — {exc}\n"
            )
            continue
        if deliverable_type not in meta["deliverable_targets"]:
            continue
        if meta["is_common_shell"]:
            # clusters with is_common_shell set are excluded from normal chapters
            # (the D3 appendix comes via the separate common_shell_clusters argument)
            continue
        eligible.append(meta)

    # 2. sort
    eligible = _sort_clusters(eligible)

    # 3. chapter assembly
    chapter_md: list[str] = []
    screen_index_md = ""

    # D3 tries screen-level chapters first (split-deliverable). Without screen
    # tagging it receives None and falls back to cluster-level chapters (+WARN).
    if deliverable_type == "D3":
        screen_result = _assemble_d3_screen_chapters(eligible)
        if screen_result is not None:
            screen_index_md, chapter_md = screen_result
        else:
            sys.stderr.write(
                "[render_transpose] WARN: D3 §2 has no screen-ID tagged "
                "headings, cannot split into screen-level chapters — falling "
                "back to cluster-level chapters\n"
            )

    if not chapter_md:
        chapter_num = 0
        for meta in eligible:
            extracted = _extract_panel_section(
                meta["text"], section_keyword, type_keywords=type_keywords
            )
            if not extracted:
                sys.stderr.write(
                    f"[render_transpose] WARN: {meta['cluster_id']} has no "
                    f"{section_keyword}"
                    + (
                        f" ({'/'.join(type_keywords)})"
                        if type_keywords
                        else ""
                    )
                    + " section — skipped\n"
                )
                continue
            _sec, inner = extracted
            chapter_num += 1
            chapter_md.append(_assemble_chapter(meta, inner, chapter_num))

    if not chapter_md:
        raise TransposeError(
            f"0 items: no cluster matches deliverable_type={deliverable_type} "
            f"(or the section is missing in every cluster)"
        )

    # 4. common-shell appendix (D3 only)
    appendix_md = ""
    common_metas: list[dict] = []
    if deliverable_type == "D3" and common_shell_clusters:
        for path in common_shell_clusters:
            try:
                meta = _load_cluster_meta(path)
            except TransposeError as exc:
                sys.stderr.write(
                    f"[render_transpose] WARN: common_shell {path} "
                    f"skip — {exc}\n"
                )
                continue
            common_metas.append(meta)
        appendix_md = _assemble_common_shell_appendix(
            common_metas, section_keyword
        )

    # 5. frontmatter
    if target_template is not None:
        fm = _apply_template_frontmatter(target_template, deliverable_type)
    else:
        fm = _default_frontmatter(deliverable_type)
    # record contributing clusters — render_sync_check judges deliverable
    # freshness against contributors only (prevents false OUTDATED from
    # comparing against the max of all drafts).
    fm["source_clusters"] = [m["cluster_id"] for m in eligible + common_metas]

    fm_md = _render_frontmatter(fm)

    # 6. final assembly
    parts: list[str] = [fm_md, "\n"]
    if screen_index_md:
        parts.append(screen_index_md)
    parts.extend(chapter_md)
    if appendix_md:
        parts.append("\n")
        parts.append(appendix_md)
    return "\n".join(p.rstrip("\n") for p in parts) + "\n"


# ── CLI ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Cluster Draft → Deliverable Transpose (Phase 5F)"
    )
    ap.add_argument(
        "--cluster-drafts",
        nargs="+",
        required=True,
        type=Path,
        help="drafts/cluster_*.draft.md list (1 or more)",
    )
    ap.add_argument(
        "--deliverable",
        required=True,
        choices=sorted(VALID_DELIVERABLES),
        help="target deliverable_type",
    )
    ap.add_argument(
        "--output",
        required=True,
        type=Path,
        help="assembled MD output path",
    )
    ap.add_argument(
        "--template",
        type=Path,
        default=None,
        help="target deliverable template file (optional)",
    )
    ap.add_argument(
        "--common-shell",
        nargs="*",
        type=Path,
        default=None,
        help="D3 common-shell cluster draft list (D3 only)",
    )
    args = ap.parse_args(argv)

    # input validation
    missing = [p for p in args.cluster_drafts if not p.exists()]
    if missing:
        sys.stderr.write(
            f"[render_transpose] ERROR: cluster_draft not found: "
            f"{[str(p) for p in missing]}\n"
        )
        return 3

    if args.common_shell:
        missing_cs = [p for p in args.common_shell if not p.exists()]
        if missing_cs:
            sys.stderr.write(
                f"[render_transpose] ERROR: common_shell cluster not found: "
                f"{[str(p) for p in missing_cs]}\n"
            )
            return 3

    if args.template is not None and not args.template.exists():
        sys.stderr.write(
            f"[render_transpose] ERROR: template not found: {args.template}\n"
        )
        return 3

    # transpose
    try:
        result = transpose(
            cluster_drafts=list(args.cluster_drafts),
            deliverable_type=args.deliverable,
            common_shell_clusters=(
                list(args.common_shell) if args.common_shell else None
            ),
            target_template=args.template,
        )
    except TransposeError as exc:
        msg = str(exc)
        if "0 items" in msg or "none" in msg and "cluster" in msg.lower():
            sys.stderr.write(f"[render_transpose] {msg}\n")
            return 2
        sys.stderr.write(f"[render_transpose] parse error: {msg}\n")
        return 1
    except ValueError as exc:
        sys.stderr.write(f"[render_transpose] argument error: {exc}\n")
        return 1

    # output
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"[render_transpose] IO error: {exc}\n")
        return 3

    n_chapters = result.count("::: {.panel section=")
    print(
        f"[render_transpose] {args.deliverable} → {args.output} "
        f"(panels={n_chapters})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
