---
name: explore
description: >-
  Parses the query and gathers context from local files and connectors the
  user has connected (chat, design, tasks — e.g. Mattermost, Figma, Jira),
  producing a cross-validated structured report. Can be called
  independently at any stage — Discovery, draft authoring, or review.
triggers:
  - "explore"
  - "search context"
  - "find info"
agent: explorer
phase: 2
effort: medium
user-invocable: true
---

## Bootstrap Cache Guard (Improvement F — CONTEXT_OPTIMIZATION.md)

Load `CONTEXT/_session-bootstrap.md` once on first entry to the session.
If this file has already been read in the same session, re-reading it is forbidden.
If the cache is missing or stale, refresh it with the following command before proceeding:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```

This guard replaces re-loading the 6 source files: layer-config / about-pm /
project-rules / brand-voice / doc-layer-schema / team-members.
Directly reading the source files is allowed only when strictly necessary
for this skill's core work.

## Precondition Checks

1. If `{query}` is empty, ask the PM about the purpose of the search.
   Present example formats:
   - Feature-related: `/explore payment cancellation policy scope`
   - Policy-related: `/explore {PREFIX}-B refund criteria`
   - UI-related: `/explore order list screen layout`
   - Issue-related: `/explore WO-07 reason for pending status`

2. Check the current project context.
   Read the active project PREFIX from `CONTEXT/layer-config.md`.
   If it cannot be determined, proceed with a full-scope search.


## Execution Steps

### Step 1 — Classify the query

Analyze the `{query}` text and classify the search intent:

| Intent type | Judgment criteria | Preferred search sources |
|---|---|---|
| Functional requirement | Contains feature name, behavior, user action | requirements.md → competitor/ → wiki |
| Policy/rule | Contains policy, criteria, restriction, prohibition | decisions.md → local files under CONTEXT/reference-docs/{ACTIVE_PREFIX}/B/ |
| Screen/UX | Contains screen, layout, button, state | screen-list.md → design → drafts/ |
| Issue/decision | Contains WO ID, issue, pending, reversal | open-issues.md → session-log.md → chat |
| Schedule/owner | Contains schedule, deadline, owner | tasks → chat |
| General search | Cannot be classified | sequentially search all sources |

Print the classification result in one line before starting the search.


### Step 2 — Search local files

Search the following files using the query keywords, in this search
priority order:

```
1. PROJECTS/{product}/inputs/requirements.md
2. PROJECTS/{product}/decisions.md
3. PROJECTS/{product}/open-issues.md
4. PROJECTS/{product}/inputs/research.md
5. PROJECTS/{product}/graph/screen-list.md
6. PROJECTS/{product}/drafts/*.draft.md
7. PROJECTS/{product}/inputs/discovery/**/*.md
8. CONTEXT/layer-config.md
```

Classify items found in each file with the following tags:
- `[confirmed]`: registered in decisions.md, or present in a v1.0-frozen draft
- `[draft]`: present in a draft but not yet confirmed
- `[reversal-history]`: the same keyword shows a trace of change in decisions.md


### Step 3 — Search local reference-docs

Load files related to the query from the
`CONTEXT/reference-docs/{ACTIVE_PREFIX}/A|B|C/` directories.
If no files exist, display `[no files at this layer — using local results
only]` and continue.
The wiki connector is not called in this step.


### Step 4 — Search the chat connector

Detect the chat connector (an MCP tool the user has connected — e.g.
Slack, Mattermost) using the docs/CONNECTORS.md detection protocol, and search
for the `{query}` keyword in project-related channels.
Search scope: messages from the last 90 days.
If the connector is absent or the connection fails, skip and record
`[chat skipped]`.

Attach a `[team discussion]` tag if a decision-related message is found.
If a decision is found that is not in decisions.md, recommend registering
it as P2 in `open-issues.md`.


### Step 5 — Search the design connector (only when intent type is screen/UX)

Detect the design connector (an MCP tool the user has connected — e.g.
Figma, Zeplin) using the docs/CONNECTORS.md detection protocol, and search
project design files for frames related to `{query}`.
If the connector is absent or the connection fails, skip and record
`[design skipped]`.

State the name, component list, and design file URL of any found frame
as the source.


### Step 6 — Search the tasks connector (only when intent type is schedule/owner)

Detect the tasks connector (a schedule/work management tool — e.g. Jira,
a groupware) using the docs/CONNECTORS.md detection protocol, and search for
related project tasks and owners.
If the connector is absent or the connection fails, skip and record
`[tasks skipped]`.


### Step 7 — Cross-validate and assemble the results

Cross-validate the items found across sources:

- If the same item agrees across multiple sources, attach a `[confirmed
  across multiple sources]` tag
- If content conflicts between sources, attach a `[cross-source conflict]`
  tag + note the conflicting content alongside it

If there are 0 search results, print "No items found — refine the query
or check the sources directly" and direct the user to the relevant skill.


### Step 8 — Output and save the report

**Inline output format:**
```markdown
## /explore Results: {query}

**Search intent**: {classification result}
**Search sources**: {list of sources searched}
**Items found**: {N}

### Key Findings

1. {item content} [`{tag}`] — source: {filename or URL}
2. ...

### Cross-Source Conflicts

{"None" if there are none}

### Not Found (search gaps)

{state any information related to the query that was not found in any source}

### Recommended Follow-up Actions

- {e.g. recommend registering P2 in open-issues.md}
- {e.g. recommend re-running /stakeholder {product} to supplement requirements}
```

**File save:**
Save the above report to `reports/explore-{YYYYMMDD-HHMM}.md`.


## Output Files

| File | Change |
|---|---|
| `reports/explore-{YYYYMMDD-HHMM}.md` | Search result report |
| `open-issues.md` | Auto-registers P1/P2 when a conflict or unregistered decision is found |
