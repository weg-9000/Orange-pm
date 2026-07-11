#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""session_emit — RESUME/decisions/open-issues/session-log → normalized session contract (§5)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import _emit_common as C

_ROW = re.compile(r"^\|(.+)\|\s*$")


def _rows(text: str) -> list[list[str]]:
    """Data rows of a markdown table (header/separator excluded) → cell lists."""
    out = []
    for line in text.splitlines():
        m = _ROW.match(line.strip())
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if not cells or all(set(c) <= {"-", ":", " "} for c in cells):
            continue  # separator
        if cells[0] in ("DEC ID", "ID", "#", "Version"):
            continue  # header
        out.append(cells)
    return out


_HEADER_FIRST = {"ID", "DEC ID", "DEC", "Decision ID", "#", "No."}


def _col(header: list[str], *names: str) -> int:
    """First column index in the header containing one of names (-1 if none)."""
    for i, h in enumerate(header):
        for n in names:
            if n in h:
                return i
    return -1


def _decision_col(header: list[str]) -> int:
    """Index of the decision-content column. Specific names first; fallback is a
    'Decision' column that is neither an 'ID' nor a 'Decider' column.
    (Prevents 'Decision' from mis-matching ID columns like 'DEC ID'/'Decision ID'.)"""
    for i, h in enumerate(header):
        if any(k in h for k in ("Decision Summary", "Key Decision",
                                "Decision Detail", "Decision Content")):
            return i
    for i, h in enumerate(header):
        if "Decision" in h and "ID" not in h.upper() and "Decider" not in h:
            return i
    return -1


def _approval_state(cell: str, has_col: bool = True) -> str:
    """Approval cell → approved/pending/hold/rejected.
    Tables without an approval column at all (legacy) → approved (keeps prior behavior)."""
    if not has_col:
        return "approved"
    low = cell.lower()
    if "✅" in cell:
        return "approved"
    if "❌" in cell or "rejected" in low:
        return "rejected"
    if "🟡" in cell or "hold" in low:
        return "hold"
    if "⬜" in cell or "pending" in low:
        return "pending"
    return "approved" if cell.strip() else "pending"


# status-cell words that are not approver identifiers ("✅ approved" has no approver)
_STATUS_WORDS = {"approved", "rejected", "pending", "hold", "on-hold", "on"}


def _approver(cell: str) -> str:
    """'✅ jeongdh' → 'jeongdh' (identifier after emoji/symbol; status words skipped)."""
    for m in re.finditer(r"[A-Za-z][\w.\-]+", cell):
        if m.group(0).lower() not in _STATUS_WORDS:
            return m.group(0)
    return ""


def parse_decisions(text: str) -> list[dict]:
    """Decision table rows → {id,date,regType,title,detail,approval,approver,status}.
    Processed per table: only 'decision tables' whose header has a decision column
    (Key Decision / Decision Detail / Decision Summary etc.) are parsed; addendum
    tables (issue/item/reason etc.) are skipped. Multiple decision tables per file
    each use their own header. Columns are located by header name (handles
    per-project layout differences)."""
    res: list[dict] = []
    cols: dict | None = None      # columns of the current decision table. None outside a table / after a heading
    last: dict | None = None      # most recent decision-table layout (fallback for header-less trailing DEC rows)
    suppressed = False            # True inside an explicitly non-decision table (issue/item/reason …)
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):              # section (heading) boundary → reset table context only
            cols = None
            suppressed = False
            continue
        if not s.startswith("|"):          # prose/blank outside a table → keep context
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        is_sep = all(set(c) <= {"-", ":", " "} for c in cells)
        if cells and cells[0] in _HEADER_FIRST and not is_sep:   # header row
            i_dec = _decision_col(cells)
            if i_dec >= 0:
                i_reg = _col(cells, "Status")
                i_appr = _col(cells, "Approval")
                if i_appr < 0:
                    # canonical minimal header carries the approval tokens
                    # (✅ approved / ❌ rejected …) in the Status column
                    i_appr = i_reg
                cols = {
                    "date": _col(cells, "Date", "Registered", "Effective", "Confirmed"),
                    "dec": i_dec,
                    "reg": i_reg,
                    "appr": i_appr,
                    "by": _col(cells, "Decider"),
                    "det": _col(cells, "Impact", "Reason", "Evidence", "Rationale"),
                }
                last = cols
                suppressed = False
            else:                          # non-decision table (issue/item/reason) → suppress
                cols = None
                suppressed = True
            continue
        if is_sep:
            continue
        # With a header use cols; header-less trailing DEC rows fall back to the
        # previous decision table (last). No fallback inside an explicitly
        # non-decision table.
        active = cols if cols is not None else (None if suppressed else last)
        if active is None or "DEC" not in cells[0]:
            continue

        def get(i: int) -> str:
            return cells[i] if 0 <= i < len(cells) else ""

        cols = active  # (compat with block below)
        appr_cell = get(cols["appr"])
        title = re.sub(r"~~", "", get(cols["dec"])).replace("**", "").strip()
        appr = _approval_state(appr_cell, cols["appr"] >= 0)
        res.append({
            "id": re.sub(r"~~", "", cells[0]).strip(),
            "date": get(cols["date"]),
            "regType": get(cols["reg"]),
            "title": title or get(cols["reg"]),
            "detail": get(cols["det"]),
            "approval": appr,
            "approver": _approver(appr_cell) or (get(cols["by"]) if cols["by"] >= 0 else ""),
            "status": appr,  # back-compat (existing consumers)
        })
    return res


# open-issues checkbox item: "- [ ] body" (indented sub-items and * bullets allowed)
_CHECKBOX = re.compile(r"^\s*[-*]\s+\[(.)\]\s+(\S.*)$")
# leading [ID] token — bold/strikethrough wrapping allowed (**[ID]**, ~~**[ID]** …)
_ISSUE_ID = re.compile(r"^[\s*~_]*\[([^\[\]]{1,80})\]\s*")
# inline priority markers: "(P1)" / "(P1 / …)" / "— P2 (…)"
_P_INLINE = re.compile(r"\(\s*P([0-2])\b|[—–-]\s*P([0-2])\s*[\(（—–-]")
# priority headings: "## P0 — …" / "### P1 …"
_P_HEAD = re.compile(r"^#{2,3}\s*P([0-2])\b")
# first-column names accepted as issue-table headers (other tables are treated as reference-only)
_ISSUE_TABLE_HEAD = ("ID", "DEC ID", "#", "No.")


def _md_plain(s: str) -> str:
    """Strip bold/strikethrough/code markup + collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"\*\*|~~|`", "", s)).strip()


def parse_open_issues(text: str) -> list[dict]:
    """open-issues.md → unresolved items [{id,p,title}]. Accepts varied formats:

    - Checkboxes: `- [ ] **[ID]** …` (open) · `- [~] …` (on hold = counted as open).
      `- [x]` (resolved) and `- [i]` (informational) are excluded. Indented
      sub-checkboxes are individual items.
    - Tables: only data rows of tables whose first header cell is ID-like
      (`ID`/`DEC ID`/`#`/`No.`). Reference tables embedded in item bodies
      (e.g. the cloud-calculator dependency model table) are ignored.

    Priority: tracks `## P0/P1/P2` headings — a non-P `##` heading resets to the
    default P1, `###` keeps the parent section. Inline `(P1)`/`— P2 (…)` markers
    in the body take precedence.
    """
    res: list[dict] = []
    cur_p = 1
    in_issue_table = False
    for line in text.splitlines():
        s = line.strip()
        mh = _P_HEAD.match(s)
        if mh:
            cur_p = int(mh.group(1))
            in_issue_table = False
            continue
        if s.startswith("#"):                      # non-P heading
            if not s.startswith("###"):            # ## section boundary → default P1
                cur_p = 1
            in_issue_table = False
            continue
        mc = _CHECKBOX.match(line)
        if mc:
            in_issue_table = False
            mark, body = mc.group(1), mc.group(2)
            if mark in "xX✓i":                     # exclude resolved/informational
                continue
            iid = ""
            mid = _ISSUE_ID.match(body)
            if mid:
                iid = _md_plain(mid.group(1))
                body = body[mid.end():]
            title = _md_plain(body)
            mp = _P_INLINE.search(title[:200])
            p = int(mp.group(1) or mp.group(2)) if mp else cur_p
            title = re.sub(r"^\(\s*P[0-2][^)]*\)\s*", "", title)
            if len(title) > 120:
                title = title[:119] + "…"
            res.append({"id": iid, "p": p, "title": title})
            continue
        m = _ROW.match(s)
        if not m:
            in_issue_table = False                 # table ended (blank/prose)
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if not cells or all(set(c) <= {"-", ":", " "} for c in cells):
            continue                               # separator (table state kept)
        if cells[0] in _ISSUE_TABLE_HEAD:
            in_issue_table = True                  # issue table starts
            continue
        if not in_issue_table:
            continue                               # ignore rows of reference tables
        res.append({"id": cells[0], "p": cur_p,
                    "title": cells[1] if len(cells) > 1 else ""})
    return res


def parse_resume(text: str) -> dict | None:
    """Extract lastSkill/lastWo/savedAt from RESUME.md (key:value or table)."""
    fm = C.read_frontmatter(text)
    if fm.get("last_skill") or fm.get("lastSkill"):
        return {"lastSkill": fm.get("last_skill") or fm.get("lastSkill"),
                "lastWo": fm.get("last_wo") or fm.get("lastWo", ""),
                "savedAt": fm.get("saved_at") or fm.get("savedAt", "")}
    return None


# hook event → timeline label mapping (.claude/ui-events.jsonl, M3 hook channel)
_HOOK_LABEL = {
    "SessionStart": ("skill", "session start"),
    "Stop": ("skill", "session end"),
    "SubagentStop": ("subagent", "subagent done"),
    "PostToolUse": ("edit", "edit"),
    "UserPromptSubmit": ("skill", "prompt"),
}


def parse_ui_events(text: str, limit: int = 50) -> list[dict]:
    """.claude/ui-events.jsonl (1 JSON per line) → timeline event list (newest first)."""
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind, default_label = _HOOK_LABEL.get(ev.get("hook", ""), ("skill", ev.get("hook", "")))
        detail = ev.get("detail") or ev.get("agent") or ev.get("tool") or default_label
        out.append({"ts": ev.get("ts", ""), "event": kind, "label": detail})
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out[:limit]


def transform_session(texts: dict[str, str], product: str = "",
                      ui_events: str = "") -> dict:
    return {
        "version": "", "product": product, "kind": "session",
        "resume": parse_resume(texts.get("RESUME.md", "")),
        "openIssues": parse_open_issues(texts.get("open-issues.md", "")),
        "decisions": parse_decisions(texts.get("decisions.md", "")),
        "timeline": parse_ui_events(ui_events),  # hook channel enrichment
    }


def main(argv: list[str]) -> int:
    args = C.make_parser("session").parse_args(argv)
    if args.from_fixture:
        return C.emit(C.load_fixture(args.from_fixture))
    if not (args.hub_root and args.product):
        sys.stderr.write("--hub-root and --product are required\n")
        return 2
    pdir = C.product_dir(args.hub_root, args.product)
    names = ["RESUME.md", "open-issues.md", "decisions.md", "session-log.md"]
    texts = {n: (pdir / n).read_text(encoding="utf-8")
             for n in names if (pdir / n).exists()}
    # hook channel: <hub-root>/.claude/ui-events.jsonl
    ui_path = Path(args.hub_root) / ".claude" / "ui-events.jsonl"
    ui_events = ui_path.read_text(encoding="utf-8") if ui_path.exists() else ""
    code = 0 if (texts or ui_events) else 1
    C.emit(transform_session(texts, args.product, ui_events))
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
