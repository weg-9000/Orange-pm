---
name: sc
description: Summarizes the current session's work and records it in session-log.md. Generates RESUME.md so the next session can resume without needing context. Presents the PM with pending confirmations and recommended next actions.
triggers:
  - "sc"
  - "save session"
  - "close session"
  - "session close"
phase: any
effort: low
model: haiku
user-invocable: true
---

## Bootstrap cache guard (Improvement F — CONTEXT_OPTIMIZATION.md)

On first entry to a session, load `CONTEXT/_session-bootstrap.md` exactly once.
If this file has already been read in the same session, do not re-read it.
If the cache is missing or stale, refresh it with the following command before proceeding:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```

This guard replaces re-loading the 6 source files layer-config / about-pm / project-rules /
brand-voice / doc-layer-schema / team-members individually.
Reading the source files directly is allowed only when strictly required for this skill's core task.


## Execution steps

### Step 1 — Collect current project state

Read the following files:
- `session-log.md`: current Phase and prior history
- `open-issues.md`: full list of open items
- `decisions.md`: recent decision history
- `work-orders/index.md` (if present): WO progress status
- `reports/integration-summary.md` (if present): latest integration verification results

Run `/lc {product}` to collect the current gate pass status.


### Step 2 — Generate this session's work summary

Extract the skills executed and key changes made in this session.
Judge this based on items added to session-log.md since this session started.

Aggregate the following items:

| Item | Content |
|---|---|
| Skills executed | List of skills invoked in this session |
| Files created/modified | List of files created or modified in this session |
| New open-issues registered | Count of each P0/P1/P2 |
| New decisions registered | Count |
| Phase change | Starting Phase → Ending Phase |


### Step 3 — Append session block to session-log.md

Append a session summary block in the following format to session-log.md:

```markdown
---
## Session Summary — {UTC date}

**Phase**: {start} → {end}
**Skills executed**: {skill list}

### Completed work
{list of completed items}

### New open-issues this session
{list of new items or "none"}

### New decisions this session
{list of new items or "none"}
---
```


### Step 4 — Check open-issues.md and decisions.md status

**Check open-issues.md:**
- If P0 items exist, print the list and warn the PM.
- If items are marked complete (`[x]`) but not yet cleaned up, move them to the "Completed" section.

**Check decisions.md (DEC table SSoT — see [[CONTEXT/dec-schema]]):**

1. **Print list of unapproved (⬜) DECs**:
   - Scan the table and list every row where the `Status` cell is `⬜` or `🟡`.
   - Ask the PM per item: `[Y] ✅ approve / [N] ❌ reject / [H] 🟡 hold / [S] defer to next session`.
   - Update the cell according to the PM's response. (This is the same interactive batch processing as `/dec-approve`.)

2. **Check for auto-capture gaps during the session**:
   - Ask the PM whether any decisive statements from this session went unrecorded by any skill.
   - When adding one, append a candidate row to the DEC table (`Status=⬜`, or `✅ {pm_id}` if the PM approves it on the spot).
   - If it can't be registered (ambiguous case), register it in open-issues.md as P2.

3. **Output format**:
   ```
   Unapproved DECs: {N}
   ├─ DEC-077 [🎯] Card shadow z-index +1 — /critique r2
   ├─ DEC-078 [💰] Commitment 30% → 35% (reverses DEC-031) — /su mattermost
   └─ DEC-079 [🏗️] Adopt micro-frontend architecture — /write WO-POL-01

   Handle each item: [Y/N/H/S] →
   ```


### Step 5 — Generate RESUME.md

Generate `PROJECTS/{product}/RESUME.md` (overwriting the existing file).
This lets Claude Code automatically read this file at the start of the next session to restore context.

```markdown
# RESUME — {product}

> Last session: {UTC timestamp}
> Read this file first when starting the next session.

## Current Phase

{Phase value} — {Phase name}

## Project core info

- PREFIX: {PREFIX}
- graph_hash: {latest hash or N/A}
- {PREFIX}-B version: {version or N/A}

## Gate status

| Gate | Status |
|---|---|
| discovery-exit-gate | PASS / FAIL |
| policy-entry-gate | PASS / FAIL |
| graph-exit-gate | PASS / FAIL |
| draft-complete-gate | PASS / FAIL |
| integration-exit-gate | PASS / FAIL |

## Work completed in the last session

{list of completed items}

## Currently open P0 items

{P0 list or "none"}

## Currently open P1 items

{P1 list (max 5 items)}

## Pending PM confirmations

{list of items not yet confirmed by the PM this session}

## Recommended next actions

1. {priority 1 action — skill name + reason}
2. {priority 2 action}
3. {priority 3 action}

## WO progress status (if Phase 1-3)

| WO ID | Type | Status |
|---|---|---|
```

Include the WO progress status only if `work-orders/index.md` exists.


### Step 6 — Print PM summary

Before ending the session, print the following to the PM:

```
Session saved: {product}

Completed work:
  {list of work}

Notes:
  P0 items: {N} {if N > 0, "— needs immediate resolution"}
  Pending PM confirmations: {N}

Recommended next actions:
  1. {skill or action}
  2. {skill or action}

How to resume the next session:
  Start by reading PROJECTS/{product}/RESUME.md first.
```


## Output files

| File | Content |
|---|---|
| `session-log.md` | This session's summary block appended |
| `RESUME.md` | Context for resuming the next session (overwritten with latest state) |
| `open-issues.md` | Completed items cleaned up / unrecorded decisions registered as P2 |
| `decisions.md` | Unrecorded finalized items added (after PM confirmation) |
