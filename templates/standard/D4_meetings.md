---
title: "[Meeting Notes] {{PRODUCT_NAME}}"
wo_id: PX-DIRECT-D4
type: meetings
layer: DIRECT
version: 1.0
last_updated: 2026-05-30

publication:
  header:
    style: info
    body: |
      **This page is the cumulative meeting-notes page for {{PRODUCT_NAME}}. Meeting entries are sorted in reverse chronological order — the most recent meeting is §1.**

      doc_id: {{DOC_ID}} Version: {{VERSION}} Last updated: {{DATE}}
  meta:
    layout: two_equal
    cells:
      - panel:
          title: "Related Pages"
          body: |
            **Related Documents**

            - [[page:[Requirements Definition] {{PRODUCT_NAME}}]]
            - [[page:[Policy Definition] {{PRODUCT_NAME}}]]
            - [[page:[Screen Design] {{PRODUCT_NAME}}]]
      - change_history: 10
---

::: {.panel section="Meeting-Notes Authoring Guide" style="info"}
## Meeting-Notes Authoring Guide

---

- **Cumulative page**: whenever a meeting occurs, add a new entry at the §1 position (reverse chronological order).
- **Numbering rule**: §1 is the most recent meeting, §2 the one before that, etc. The meeting display ID is recommended to follow the `MTG-{{YYYYMMDD}}-{{NN}}` format (for readability on the published page).
- **⚠️ Distinguish the canonical pin ID**: the screen frontmatter `meeting_decisions: [...]` pin and the `mtg-ledger.md` ledger-row ID **must use only the canonical ledger form `MTG-\d+`** (e.g. MTG-01). Since `mtg_ledger_scan.py` cross-validates only against `^MTG-\d+$`, writing the display ID above (`MTG-YYYYMMDD-NN`) into the pin will fail ledger matching. If a mapping between the display ID and the ledger ID is needed, list the ledger `MTG-NN` alongside it in the meeting metadata table.
- **cluster reference**: cross-reference in the "Related cluster" row of the meeting metadata table, in the form PR-XX / BL-XX.
- **Decisions**: record DEC-XXX items as declarative statements ("will do" / "is"). Separate speculation/opinion into §N-5 Open Items.
- **Action items**: always state the owner, deadline, and status (📋 not started / ⏳ in progress / ✅ complete).
- **Bottom index**: when adding a new meeting, add 1 row to the "Meeting-Notes Index" table at the bottom of the page.
:::

::: {.panel section="§1 Meeting — {{MEETING_DATE_LATEST}} {{MEETING_TOPIC_LATEST}}"}
## §1 Meeting — {{MEETING_DATE_LATEST}} {{MEETING_TOPIC_LATEST}}

---

<!-- col-widths: 20%, 80% -->
| Item | Content |
|---|---|
| **Meeting ID** | MTG-{{YYYYMMDD_LATEST}}-01 |
| **Date/Time** | {{MEETING_DATE_LATEST}} {{MEETING_TIME_LATEST}} |
| **Attendees** | {{ATTENDEES_LATEST}} |
| **Absent** | {{ABSENTEES_LATEST}} |
| **Venue/Format** | {{MEETING_VENUE_LATEST}} |
| **Related cluster** | {{CLUSTER_REFS_LATEST}} |
| **Meeting Type** | R2 / in progress |

### §1-1 Agenda

1. {{agenda item 1}}
2. {{agenda item 2}}
3. {{agenda item 3}}

### §1-2 Discussion Summary

- **Agenda 1 — {{agenda item 1}}**: {{discussion summary}}
- **Agenda 2 — {{agenda item 2}}**: {{discussion summary}}
- **Agenda 3 — {{agenda item 3}}**: {{discussion summary}}

### §1-3 Decisions

<!-- col-widths: 10%, 40%, 15%, 20%, 15% -->
| Decision ID | Decision Content | Decider | Impact Scope (cluster) | Effective Date |
|---|---|---|---|---|
| **DEC-001** | {{decision statement — "will do" / "is"}} | {{decider}} | {{PR-01}} | {{YYYY-MM-DD}} |
| **DEC-002** | {{decision statement}} | {{decider}} | {{BL-02}} | {{YYYY-MM-DD}} |

### §1-4 Action Items

<!-- col-widths: 10%, 45%, 15%, 15%, 15% -->
| Action ID | Content | Owner | Deadline | Status |
|---|---|---|---|---|
| **ACT-001** | {{action content}} | {{owner}} | {{YYYY-MM-DD}} | 📋 |
| **ACT-002** | {{action content}} | {{owner}} | {{YYYY-MM-DD}} | ⏳ |

### §1-5 Open Items / Open Questions

- **OQ-001** {{open question}} — carried over to the next meeting (MTG-{{YYYYMMDD_NEXT}})
- **OQ-002** {{open question}} — {{owner}} to confirm via a separate channel
:::

::: {.panel section="§2 Meeting — {{MEETING_DATE_PREV}} {{MEETING_TOPIC_PREV}}"}
## §2 Meeting — {{MEETING_DATE_PREV}} {{MEETING_TOPIC_PREV}}

---

<!-- col-widths: 20%, 80% -->
| Item | Content |
|---|---|
| **Meeting ID** | MTG-{{YYYYMMDD_PREV}}-01 |
| **Date/Time** | {{MEETING_DATE_PREV}} {{MEETING_TIME_PREV}} |
| **Attendees** | {{ATTENDEES_PREV}} |
| **Absent** | {{ABSENTEES_PREV}} |
| **Venue/Format** | {{MEETING_VENUE_PREV}} |
| **Related cluster** | {{CLUSTER_REFS_PREV}} |
| **Meeting Type** | R1 / in progress |

### §2-1 Agenda

1. {{agenda item 1}}
2. {{agenda item 2}}

### §2-2 Discussion Summary

- **Agenda 1 — {{agenda item 1}}**: {{discussion summary}}
- **Agenda 2 — {{agenda item 2}}**: {{discussion summary}}

### §2-3 Decisions

<!-- col-widths: 10%, 40%, 15%, 20%, 15% -->
| Decision ID | Decision Content | Decider | Impact Scope (cluster) | Effective Date |
|---|---|---|---|---|
| **DEC-003** | {{decision statement}} | {{decider}} | {{PR-02}} | {{YYYY-MM-DD}} |

### §2-4 Action Items

<!-- col-widths: 10%, 45%, 15%, 15%, 15% -->
| Action ID | Content | Owner | Deadline | Status |
|---|---|---|---|---|
| **ACT-003** | {{action content}} | {{owner}} | {{YYYY-MM-DD}} | ✅ |

### §2-5 Open Items / Open Questions

- **OQ-003** {{open question}} — resolved in the §1 meeting (see DEC-001)
:::

::: {.panel section="§3 Meeting — {{MEETING_DATE_R0}} Kickoff"}
## §3 Meeting — {{MEETING_DATE_R0}} Kickoff

---

<!-- col-widths: 20%, 80% -->
| Item | Content |
|---|---|
| **Meeting ID** | MTG-{{YYYYMMDD_R0}}-01 |
| **Date/Time** | {{MEETING_DATE_R0}} {{MEETING_TIME_R0}} |
| **Attendees** | {{ATTENDEES_R0}} |
| **Absent** | {{ATTENDEES_R0_ABS}} |
| **Venue/Format** | {{MEETING_VENUE_R0}} |
| **Related cluster** | All (Phase 0 scope) |
| **Meeting Type** | R0 / kickoff |

### §3-1 Agenda

1. Finalize project scope
2. Assign roles
3. Agree on milestones

### §3-2 Discussion Summary

- **Scope**: {{scope agreement content}}
- **Roles**: {{role-assignment outcome}}
- **Milestones**: {{milestone agreement content}}

### §3-3 Decisions

<!-- col-widths: 10%, 40%, 15%, 20%, 15% -->
| Decision ID | Decision Content | Decider | Impact Scope (cluster) | Effective Date |
|---|---|---|---|---|
| **DEC-004** | {{PRODUCT_NAME}} Phase 1 scope will be {{scope}} | {{decider}} | All | {{MEETING_DATE_R0}} |
| **DEC-005** | The PM will be {{owner}}, and the dev lead will be {{owner}} | {{decider}} | All | {{MEETING_DATE_R0}} |

### §3-4 Action Items

<!-- col-widths: 10%, 45%, 15%, 15%, 15% -->
| Action ID | Content | Owner | Deadline | Status |
|---|---|---|---|---|
| **ACT-004** | Draft the requirements | {{owner}} | {{YYYY-MM-DD}} | ✅ |
| **ACT-005** | Draft the policy | {{owner}} | {{YYYY-MM-DD}} | ✅ |

### §3-5 Open Items / Open Questions

- none (kickoff complete)
:::

::: {.panel section="Meeting-Notes Index" style="info"}
## Meeting-Notes Index

---

<!-- col-widths: 15%, 15%, 35%, 20%, 15% -->
| Meeting ID | Date/Time | Topic | Related cluster | Key Decision Count |
|---|---|---|---|---|
| **MTG-{{YYYYMMDD_LATEST}}-01** | {{MEETING_DATE_LATEST}} | {{MEETING_TOPIC_LATEST}} | {{CLUSTER_REFS_LATEST}} | 2 |
| **MTG-{{YYYYMMDD_PREV}}-01** | {{MEETING_DATE_PREV}} | {{MEETING_TOPIC_PREV}} | {{CLUSTER_REFS_PREV}} | 1 |
| **MTG-{{YYYYMMDD_R0}}-01** | {{MEETING_DATE_R0}} | Kickoff | All | 2 |
:::
