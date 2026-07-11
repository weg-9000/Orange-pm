#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""session_emit unit tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import session_emit as M  # noqa: E402

DECISIONS = """# Decision log
| DEC ID | Date | Decision | Reason | Impact |
|---|---|---|---|---|
| DEC-VIZ-001 | 2026-06-03 | Externalize design | directive | policy |
| DEC-VIZ-002 | 2026-06-03 | Option A only | balance | plan |
"""

OPEN = """# Open issues
## P0 (blocking)
(none)
## P1 (needs discussion)
| ID | Item | State | Owner | Due |
|---|---|---|---|---|
| OI-001 | Terminal identification | tentative | PM | M4 |
## P2 (nice to have)
| ID | Item | State | Owner | Due |
|---|---|---|---|---|
| OI-003 | bridge default | off | PM | M5 |
"""


def test_parse_decisions():
    res = M.parse_decisions(DECISIONS)
    assert [d["id"] for d in res] == ["DEC-VIZ-001", "DEC-VIZ-002"]
    assert res[0]["date"] == "2026-06-03"
    assert res[0]["title"] == "Externalize design"
    assert res[0]["status"] == "approved"


DECISIONS_REAL = """## Decision log
| DEC ID | Registered | Status | Domain | Decision Summary | Impacted FR/§ | Reversal Target | Approval | Evidence File |
|---|---|---|---|---|---|---|---|---|
| DEC-001 | 2026-04-27 | registered | 🏗️ | Exclude upper-layer references | all deliverables | - | ✅ jeongdh | session-log |
| ~~DEC-003~~ | 2026-05-11 | reversed | 💰 | No commitment-period tab | S01 | - | ✅ jeongdh | DEC-045 |
| DEC-080 | 2026-05-20 | registered | 🧭 | Preset change | S02 | - | ⬜ | TBD |
"""


def test_parse_decisions_header_aware_real_layout():
    # real 9-column table: Decision Summary in col 4, Status in col 2, Approval in col 7
    # — verifies header-name based column lookup
    res = M.parse_decisions(DECISIONS_REAL)
    by = {d["id"]: d for d in res}
    assert by["DEC-001"]["date"] == "2026-04-27"
    assert by["DEC-001"]["title"] == "Exclude upper-layer references"   # not cells[2]='registered'
    assert by["DEC-001"]["regType"] == "registered"
    assert by["DEC-001"]["approval"] == "approved"
    assert by["DEC-001"]["approver"] == "jeongdh"
    assert "DEC-003" in by                                   # id with ~~strikethrough~~ stripped
    assert by["DEC-080"]["approval"] == "pending"            # ⬜ pending


DECISIONS_ID_HEADER = """## Decisions
| ID | Date | Domain | Key Decision | Reversal | Approval | Evidence |
|---|---|---|---|---|---|---|
| DEC-001 | 2026-05-28 | 🤖auto-log | Confluence-only synthesis | — | ✅ jeongdh | /draft-req |
"""

DECISIONS_4COL = """## Decisions
| ID | Decision Detail | Confirmed | Decider |
|---|---|---|---|
| DEC-01 | **Project scope**: new stats development only | 2026-05-13 | PM |
"""


def test_parse_decisions_id_header_7col():
    # table whose first column is 'ID' rather than 'DEC ID' (dbaas style) — header lookup generalization
    res = M.parse_decisions(DECISIONS_ID_HEADER)
    d = res[0]
    assert d["date"] == "2026-05-28"
    assert d["title"] == "Confluence-only synthesis"
    assert d["approval"] == "approved" and d["approver"] == "jeongdh"


def test_parse_decisions_4col_no_approval():
    # 4-column table without an approval column (back-office style)
    # — Decider becomes approver, ** markdown stripped
    res = M.parse_decisions(DECISIONS_4COL)
    d = res[0]
    assert d["date"] == "2026-05-13"
    assert d["title"] == "Project scope: new stats development only"   # ** removed
    assert d["approval"] == "approved"                       # no approval column → default
    assert d["approver"] == "PM"                             # Decider fallback


DECISIONS_LEDGER = """## Decision ledger
| Decision ID | Decision Detail | Decider | Impact Scope (cluster) | Effective |
|---|---|---|---|---|
| DEC-001 | Cache TTL fixed to 5 min | parkPM | CL-RES | 2026-06-02 |
"""


def test_parse_decisions_ledger_header():
    # meeting-ledger style: first cell 'Decision ID', date 'Effective', approver 'Decider'
    res = M.parse_decisions(DECISIONS_LEDGER)
    d = res[0]
    assert d["date"] == "2026-06-02"
    assert d["title"] == "Cache TTL fixed to 5 min"
    assert d["approver"] == "parkPM"


DECISIONS_WITH_ADDENDUM = """## DEC ledger (SSoT)
| ID | Date | Domain | Key Decision | Reversal | Approval | Evidence (skill·session) |
|---|---|---|---|---|---|---|
| DEC-001 | 2026-06-01 | 🏗️ | Actual decision A | - | ✅ jeongdh | /write |
| DEC-002 | 2026-06-01 | 💰 | Actual decision B | - | ⬜ | /su |

## Unresolved / issues
| DEC ID | Issue | Needs PM check |
|---|---|---|
| DEC-067·068 | needs promotion | PM check |

## On-hold items
| ID | Item | Reason |
|---|---|---|
| DEC-099 | held item | TBD |
"""


def test_parse_decisions_skips_addendum_tables():
    # only decision tables (Key Decision column) are parsed; DEC rows of
    # issue/on-hold addendum tables are excluded
    res = M.parse_decisions(DECISIONS_WITH_ADDENDUM)
    assert [d["id"] for d in res] == ["DEC-001", "DEC-002"]
    assert res[0]["title"] == "Actual decision A"
    assert res[0]["approval"] == "approved" and res[1]["approval"] == "pending"


def test_parse_open_issues_priority_from_section():
    res = M.parse_open_issues(OPEN)
    by = {i["id"]: i for i in res}
    assert by["OI-001"]["p"] == 1
    assert by["OI-003"]["p"] == 2
    assert "(none)" not in [i["id"] for i in res]   # table rows only


# ── checkbox format (real-file regressions: back-office stats / dbaas-mysql / cloud-calculator) ──

OPEN_CHECKBOX = """# Back-office stats Open Issues
## P0 — resolve immediately
_(none)_
## Gen1·Gen2 live-data survey results (2026-06-01)
- [x] **[OPEN-30] resolved (DEC-37, 2026-06-01)** — option B adopted
- [ ] **[OPEN-33] (P1)** public-cloud revenue source/aggregation undecided — assumes DEC-37 unified view
- [i] **[OPEN-31 related]** monthly-report auto-feed candidate
- [ ] **[OPEN-32] (P1)** subscriber-change metric definition differs
- [ ] **[OPEN-12] progress** — incomplete export, join-key check remains
## P1 — Discovery must-collect items
- [x] [DISC-01] competitor analysis → `/research` done
- [ ] [DISC-04] `BACKSTAT-B` master policy Confluence link unregistered
## P2 — recommended collection items
- [ ] [OPEN-02] snapshot infra adoption undecided
"""


def test_parse_open_issues_checkbox_format():
    # back-office style: 0 tables, all checkboxes + **[ID]** wrapping — the old parser returned 0 (regression)
    res = M.parse_open_issues(OPEN_CHECKBOX)
    by = {i["id"]: i for i in res}
    assert set(by) == {"OPEN-33", "OPEN-32", "OPEN-12", "DISC-04", "OPEN-02"}
    assert by["OPEN-33"]["p"] == 1                       # non-P section + inline (P1) wins
    assert by["OPEN-33"]["title"].startswith("public-cloud")  # (P1)·** markup stripped
    assert by["OPEN-12"]["p"] == 1                       # non-P ## section → default P1
    assert by["DISC-04"]["p"] == 1 and by["OPEN-02"]["p"] == 2


OPEN_DBAAS_STYLE = """# dbaas-mysql Open Issues
## P1 — must reinforce/resolve synthesis results
### Policy itself undecided (Confluence v94/v12 explicitly open)
- [ ] **[TBD-01]** overdue suspension handling — figures missing / confirm with: billing team
- [x] ~~**[TBD-06]** monitoring alert threshold policy missing~~ → **resolved (2026-05-28 / DEC-005)**
## P2 — recommended collection / policy under review
- [ ] **[ERRCODE-G2A-UNRESOLVED]** *(P1 / upstream gap, 2026-06-05)* G2-A error-code scheme undecided
- [ ] **[CONSOLIDATED-FM-SYNC]** *(WRN-01 / Round 5)* consolidated frontmatter stale — accepted as P2
"""


def test_parse_open_issues_dbaas_subheading_and_inline_p():
    # dbaas style: ~~strikethrough~~ resolved items excluded · ### subheading keeps P · inline "(P1 …)"
    res = M.parse_open_issues(OPEN_DBAAS_STYLE)
    by = {i["id"]: i for i in res}
    assert set(by) == {"TBD-01", "ERRCODE-G2A-UNRESOLVED", "CONSOLIDATED-FM-SYNC"}
    assert by["TBD-01"]["p"] == 1                        # ### subheading keeps section P1
    assert by["ERRCODE-G2A-UNRESOLVED"]["p"] == 1        # P2 section + inline "(P1 / …)" wins
    assert by["CONSOLIDATED-FM-SYNC"]["p"] == 2          # no inline marker → section P2


OPEN_CLOUDCALC_STYLE = """# cloud-calculator Open Issues
## P0 — resolve immediately
- [x] [RESP-Q01] ~~responsive undefined~~ → **resolved (PM decision 2026-05-18)**
- [~] (HOLD — carried to dev kickoff meeting) **natural-scroll shell sticky panel height model** | dev kickoff meeting
- [ ] [DRIFT-GATE-OPTOUT] **CON-001 drift-gate formal registration — P2 (2026-05-20, /review --all round 30)** | planner
## P1 — infra/security SW dependency · screen model fixed (2026-05-16 round 19)
- [x] [INFRA-SEC-MODEL] **dependency·screen·billing model fixed** — table below is canonical.

  | Target | Screen input method (UI) | Requires / Suggests |
  |---|---|---|
  | CDN | external domain URL direct text input | Requires: none |
  | NAS | subnet selection·capacity choice | Requires: VPC |

- [ ] [STK-Q02] product-management system API integration — dev kickoff technical validation items:
  - [ ] [STK-Q02-2] non-member quote call path — common platform dev team
  - [~] [STK-Q02-1] commitment discount policy registered? — partial reply
"""


def test_parse_open_issues_embedded_reference_table_ignored():
    # regression guard: the reference table (header 'Target') inside a resolved
    # item's body used to be mis-parsed as 9 issues
    res = M.parse_open_issues(OPEN_CLOUDCALC_STYLE)
    ids = [i["id"] for i in res]
    assert "Target" not in ids and "CDN" not in ids and "NAS" not in ids


def test_parse_open_issues_hold_and_nested():
    res = M.parse_open_issues(OPEN_CLOUDCALC_STYLE)
    by = {i["id"]: i for i in res}
    assert "RESP-Q01" not in by                          # [x] resolved excluded
    assert by["DRIFT-GATE-OPTOUT"]["p"] == 2             # P0 section + inline "— P2 (…)" wins
    assert by["STK-Q02"]["p"] == 1
    assert by["STK-Q02-2"]["p"] == 1                     # indented sub-checkbox is its own item
    assert by["STK-Q02-1"]["p"] == 1                     # [~] hold = counted as open
    no_id = [i for i in res if i["id"] == ""]            # [~] items without an ID also collected
    assert len(no_id) == 1 and no_id[0]["p"] == 0
    assert no_id[0]["title"].startswith("(HOLD")


def test_parse_open_issues_long_title_truncated():
    res = M.parse_open_issues("## P1\n- [ ] [LONG-01] " + "x" * 200 + "\n")
    assert res[0]["id"] == "LONG-01"
    assert len(res[0]["title"]) == 120 and res[0]["title"].endswith("…")


UI_EVENTS = "\n".join([
    '{"ts":"2026-06-01T17:20:00+09:00","hook":"PostToolUse","tool":"edit","detail":"S01.draft.md"}',
    '{"ts":"2026-06-01T17:35:00+09:00","hook":"SubagentStop","agent":"reviewer"}',
    'not-json-line-ignored',
    '{"ts":"2026-06-01T16:50:00+09:00","hook":"SessionStart"}',
])


def test_parse_ui_events_sorted_and_mapped():
    tl = M.parse_ui_events(UI_EVENTS)
    assert len(tl) == 3                                   # broken line ignored
    assert tl[0]["ts"] == "2026-06-01T17:35:00+09:00"     # newest first
    assert tl[0]["event"] == "subagent" and tl[0]["label"] == "reviewer"
    assert tl[-1]["event"] == "skill"                     # SessionStart → skill


def test_transform_session_timeline_from_hook_channel():
    out = M.transform_session({"decisions.md": DECISIONS, "open-issues.md": OPEN},
                              "demo", ui_events=UI_EVENTS)
    assert out["kind"] == "session"
    assert len(out["decisions"]) == 2
    assert len(out["openIssues"]) == 2
    assert out["resume"] is None
    assert len(out["timeline"]) == 3                      # hook channel enrichment


def test_transform_session_empty_timeline_without_events():
    out = M.transform_session({"decisions.md": DECISIONS}, "demo")
    assert out["timeline"] == []


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
