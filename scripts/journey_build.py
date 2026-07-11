#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""journey_build — deterministically generates a standard storyboard from draft artifacts (automated builder).

Scripts the deterministic part of the /journey skill (LLM) — screen order
reconstruction and draft status collection. The PostToolUse hook (--from-hook)
runs automatically whenever it detects an edit to drafts/*.draft.md and
refreshes `reports/journey-latest.md` — so the user journey shown in the viz
prototype view stays current at all times without a manual /journey call.

Division of responsibilities:
    journey_build.py (automatic) — standard storyboard: order/status/transition skeleton (0 LLM tokens)
    /journey skill (manual)      — --actor filter, narrative enrichment of key actions/transition conditions
    journey_emit.py              — latest journey-*.md → viz JSON (by mtime)

Output format matches skills/journey/SKILL.md steps 4-5 — journey_emit parses it as-is.
Auto-generated output is not recorded in the session log (to avoid bloat on every edit).

CLI:
    python journey_build.py --hub-root <Hub> --product <name> [--output <path>]
    python journey_build.py --from-hook        # PostToolUse payload (stdin) mode
exit: 0 success (or hook dormant) / 1 no screen source / 2 argument error
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

ICONS = {"done": "✅", "draft": "📝", "sketch": "🔲", "todo": "⬜"}
OUTPUT_NAME = "journey-latest.md"

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
SCR_ID = re.compile(r"\b([A-Z]{2,}-\d+)\b")
SECTION2 = re.compile(r"^#{2,3}\s*§?\s*2\b.*$", re.MULTILINE)
HEADING = re.compile(r"^#{2,3}\s", re.MULTILINE)

HUB_MARKERS = (
    Path("CONTEXT") / "layer-config.md",
    Path("CONTEXT") / "_session-bootstrap.md",
)
DRAFT_PATH_RE = re.compile(
    r"PROJECTS[/\\](?P<product>[^/\\]+)[/\\]drafts[/\\][^/\\]+\.draft\.md$"
)


def _parse_frontmatter(text: str) -> dict:
    """Flat key:value parser — also flattens and captures nested keys (e.g. cluster.cluster_id)."""
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


def _extract_screen_items(text: str) -> list[str]:
    """Top-level bullet items from the §2 screen section of the draft body."""
    m = FRONTMATTER.match(text)
    body = text[m.end():] if m else text
    sec = SECTION2.search(body)
    if not sec:
        return []
    rest = body[sec.end():]
    nxt = HEADING.search(rest)
    section = rest[: nxt.start()] if nxt else rest
    items: list[str] = []
    for ln in section.splitlines():
        if re.match(r"^[-*]\s+\S", ln):
            items.append(re.sub(r"^[-*]\s+", "", ln).strip())
    return items


def _draft_status(fm: dict, has_items: bool) -> str:
    """SKILL.md step 2 — dossier draft status → done/draft/todo."""
    rs = fm.get("review_status", "") or fm.get("status", "")
    if rs == "human-reviewed" or fm.get("reviewed", "").lower() == "true":
        return "done"
    if has_items:
        return "draft"
    return "todo"


def build_dossier_steps(pdir: Path) -> list[dict] | None:
    """dossier (Track A) model — extracts §2 screen items in cluster_index order."""
    cidx = pdir / "work-orders" / "cluster_index.json"
    if not cidx.is_file():
        return None
    try:
        clusters = json.loads(cidx.read_text(encoding="utf-8")).get("clusters", [])
    except Exception:
        return None
    steps: list[dict] = []
    for c in clusters:
        cluster_id = c.get("cluster_id", "") or c.get("wo_id", "")
        capability = c.get("capability", "") or c.get("cluster_name", "")
        dp = c.get("draft_path", "")
        fm: dict = {}
        items: list[str] = []
        draft = pdir / dp if dp else None
        if draft is not None and draft.is_file():
            text = draft.read_text(encoding="utf-8", errors="replace")
            fm = _parse_frontmatter(text)
            items = _extract_screen_items(text)
        if items:
            status = _draft_status(fm, True)
            for n, it in enumerate(items, 1):
                m = SCR_ID.search(it)
                sid = m.group(1) if m else f"{cluster_id}-S{n}"
                label = SCR_ID.sub("", it).strip(" —-·:") or capability or sid
                steps.append({"id": sid, "label": label, "status": status,
                              "capability": capability})
        else:
            steps.append({"id": f"{cluster_id}-S1",
                          "label": f"{capability or cluster_id} [§2 not written]",
                          "status": "todo", "capability": capability})
    return steps or None


def build_legacy_steps(pdir: Path) -> list[dict] | None:
    """section/screen (legacy) model — SCR rows from the screen-list.md table."""
    sl = pdir / "graph" / "screen-list.md"
    if not sl.is_file():
        return None
    steps: list[dict] = []
    for ln in sl.read_text(encoding="utf-8", errors="replace").splitlines():
        if not ln.strip().startswith("|") or "---" in ln:
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        sid = None
        for c in cells[:2]:
            m = SCR_ID.search(c)
            if m:
                sid = m.group(1)
                break
        if not sid:
            continue
        name_idx = 1 if cells and SCR_ID.search(cells[0]) else 2
        label = cells[name_idx] if len(cells) > name_idx else sid
        purpose = cells[name_idx + 1] if len(cells) > name_idx + 1 else ""
        steps.append({"id": sid, "label": label, "status": "todo", "purpose": purpose})
    return steps or None


def render_storyboard(product: str, steps: list[dict]) -> str:
    """storyboard MD in the SKILL.md steps 4-5 format (parseable by journey_emit)."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    counts = {s: sum(1 for st in steps if st["status"] == s)
              for s in ("done", "draft", "sketch", "todo")}
    lines = [
        "---",
        f"generated_at: {now}",
        f"product: {product}",
        "actor: all",
        "from_screen: first",
        f"screen_count: {len(steps)}",
        f"draft_complete: {counts['done']}",
        f"draft_in_progress: {counts['draft']}",
        f"sketch_only: {counts['sketch']}",
        f"not_started: {counts['todo']}",
        "generated_by: journey_build.py (auto)",
        "---",
        "",
        f"Customer journey storyboard — {product}",
        f"Actor: all / Generated at: {now}",
        f"Total {len(steps)} screens ({counts['done']} ✅ / {counts['draft']} 📝 / "
        f"{counts['sketch']} 🔲 / {counts['todo']} ⬜)",
        "─" * 65,
        "",
    ]
    for i, st in enumerate(steps):
        icon = ICONS.get(st["status"], "⬜")
        lines.append(f"[{i + 1}] {st['id']} {st['label']}  {icon}")
        if st["status"] == "todo":
            if st.get("purpose"):
                # NOTE: "목적:" is a Korean field-label kept as-is — it is a parsing
                # contract with journey_emit.py's _DETAIL_KEYS/_DETAIL_RE (out of
                # scope for this translation pass). Only the value is translated.
                lines.append(f"  목적: {st['purpose']}")
            lines.append("  전환: [undetermined]")
        else:
            entry = "Service entry (first screen)" if i == 0 else f"{steps[i - 1]['id']} transition"
            # NOTE: "진입 조건:"/"핵심 행동:"/"전환:" labels below are kept in Korean —
            # they are a parsing contract with journey_emit.py's _DETAIL_KEYS/_DETAIL_RE
            # (out of scope for this translation pass, still expects Korean labels).
            lines.append(f"  진입 조건: {entry}")
            lines.append("  핵심 행동: [auto-generated — enrich via /journey]")
            if i + 1 < len(steps):
                lines.append(f"  전환:      → {steps[i + 1]['id']} ([transition condition undetermined])")
        lines.append("")
    path_ids = " → ".join(st["id"] for st in steps)
    todo_list = ", ".join(st["id"] for st in steps if st["status"] == "todo") or "none"
    lines += [
        "─" * 65,
        "Journey summary",
        f"  Entry point:  {steps[0]['id']} {steps[0]['label']}",
        f"  Key path:     {path_ids}",
        f"  Undetermined: {todo_list}",
        "",
        "> This file is a standard storyboard automatically generated by journey_build.py on draft changes.",
        "> Actor filtering and transition-condition narrative enrichment are generated via /journey {product}.",
        "",
    ]
    return "\n".join(lines)


def _strip_volatile(text: str) -> str:
    """Body excluding generated_at/Generated at lines — for comparison to avoid rewriting when unchanged."""
    return "\n".join(
        ln for ln in text.splitlines()
        if not ln.startswith("generated_at:") and "Generated at:" not in ln
    )


def build(hub_root: Path, product: str, output: Path | None = None,
          quiet: bool = False) -> int:
    pdir = hub_root / "PROJECTS" / product
    steps = build_dossier_steps(pdir) or build_legacy_steps(pdir)
    if not steps:
        if not quiet:
            sys.stderr.write(f"No screen source (cluster_index/screen-list): {pdir}\n")
        return 1
    md = render_storyboard(product, steps)
    out = output or (pdir / "reports" / OUTPUT_NAME)
    if out.is_file():
        try:
            if _strip_volatile(out.read_text(encoding="utf-8")) == _strip_volatile(md):
                return 0  # no substantive change — avoid rewrite and watcher trigger
        except OSError:
            pass
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    if not quiet:
        print(f"[journey-build] {product}: {len(steps)} steps → {out}")
    return 0


# ── PostToolUse hook mode (auto_assemble_on_draft_edit pattern) ─────────────

def _is_hub(cwd: Path) -> bool:
    return cwd.is_dir() and any((cwd / m).is_file() for m in HUB_MARKERS)


def _hook_main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}") or {}
    except Exception:
        payload = {}
    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    if not _is_hub(cwd):
        return 0
    if payload.get("tool_name", "") not in ("Write", "Edit", "MultiEdit"):
        return 0
    file_path = ((payload.get("tool_input") or {}).get("file_path") or "").replace("\\", "/")
    m = DRAFT_PATH_RE.search(file_path)
    if not m:
        return 0
    # Never block the PM's workflow even on failure — always return 0.
    try:
        rc = build(cwd, m.group("product"), quiet=True)
        if rc == 0:
            print(f"[auto-journey] {m.group('product')} {OUTPUT_NAME} refreshed")
    except Exception as exc:
        print(f"[auto-journey] WARN: {exc}", file=sys.stderr)
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Deterministic journey storyboard builder")
    ap.add_argument("--hub-root", type=Path)
    ap.add_argument("--product")
    ap.add_argument("--output", type=Path)
    ap.add_argument("--from-hook", action="store_true",
                    help="PostToolUse payload (stdin) mode — auto-refresh on draft edits")
    args = ap.parse_args(argv)
    if args.from_hook:
        return _hook_main()
    if not (args.hub_root and args.product):
        sys.stderr.write("--hub-root, --product required (or --from-hook)\n")
        return 2
    return build(args.hub_root, args.product, args.output)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
