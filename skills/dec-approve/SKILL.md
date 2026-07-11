---
name: dec-approve
description: Marks pending (⬜) or on-hold (🟡) rows in the decisions.md DEC table as PM-approved. Use /dec-approve {DEC-ID,...} for multiple IDs, or the --all-pending option for bulk processing. Supports --reject to reject and --hold to hold.
triggers:
  - "dec approve"
  - "approve decision"
  - "approve DEC"
phase: any
effort: low
model: haiku
user-invocable: true
---

## Role of This Skill

Updates the `approval` column of the `decisions.md` DEC table under PM
authority.
An alternative to editing table cells directly, enabling bulk processing
in a CLI workflow.

This skill is the entry point for §4-2 (CLI bulk) of the approval
workflow in [[CONTEXT/dec-schema]] §4.

---

## Input Parameters

```
/dec-approve {DEC-ID,...}              # Approve ✅ multiple (comma-separated)
/dec-approve --all-pending             # All ⬜ → ✅
/dec-approve --all-hold                # All 🟡 → ✅
/dec-approve DEC-079 --reject "reason" # Reject ❌ a single DEC (reason required)
/dec-approve DEC-080 --hold            # Put a single DEC on hold 🟡 (decision required by the next session)
/dec-approve --list                    # Print only the pending/on-hold DEC list (no changes)
```

- Using `--reject` requires the `reason` argument (format:
  `❌ {pm_id}: {reason}`)
- `--hold` explicitly signals intent to hold — re-confirmation is forced in
  the next session's `/sc`
- The multi-ID options and `--reject`/`--hold` are mutually exclusive

---

## Precondition Checks

1. Check that `PROJECTS/{product}/decisions.md` exists. If not, ask the
   PM to confirm the project path.

2. Parse the DEC table — check that the header
   `| ID | Date | Domain | Key Decision | Reversal | Approval | Basis (skill/session) |`
   exists. If not, explain that `decisions.md` needs to be migrated to the
   [[CONTEXT/dec-schema]] format, and stop.

3. Check the `freeze: true` header line. If frozen, explain that entering
   a new freeze round or clearing `freeze: false` must happen first, and
   stop.

4. Confirm the PM identifier — obtain it from the `ORANGE_PM_ID`
   environment variable or user input. If unavailable, ask the PM to enter
   it.

---

## Execution Steps

### Step 1 — Parse the table and identify target rows

Parse the DEC table in `decisions.md` and load all rows into memory.

Determine target rows:
- `{DEC-ID,...}` specified: only the matching ID rows (a nonexistent ID is
  warned and skipped)
- `--all-pending`: all rows whose `approval` cell is `⬜`
- `--all-hold`: all rows whose `approval` cell is `🟡`
- `--list`: all pending (`⬜`) + on-hold (`🟡`) rows (no changes, output only)

If there are 0 target rows, print "No items to process" and stop.

### Step 2 — Print a preview of the change

```
About to process approval: {N} items

ID         | Domain | Key Decision                        | Current | After          | Basis
-----------|--------|-------------------------------------|---------|-----------------|----------------
DEC-077    | 🎯     | Card shadow z-index +1             | ⬜      | ✅ {pm_id}      | /critique r2
DEC-078    | 💰     | Commitment 30% → 35%                | ⬜      | ✅ {pm_id}      | /su mattermost
DEC-079    | 🏗️     | Adopt micro-frontends               | ⬜      | ❌ {pm_id}: ... | /write WO-POL-01

Proceed? [Y/n]:
```

If the PM responds `Y`, proceed to step 3. If `N`, stop without changes.

The `--list` option runs only through step 2, then finishes.

### Step 3 — Update the table rows

Update the `approval` cell of each target row using the following rules:

| Option | Change |
|---|---|
| (default) | `⬜` or `🟡` → `✅ {pm_id}` |
| `--reject "reason"` | `⬜` or `🟡` → `❌ {pm_id}: {reason}` |
| `--hold` | `⬜` → `🟡 on-hold` (no change if already 🟡) |

Use the `Edit` tool to atomically replace the matching row in
`decisions.md`.
Never touch any line outside the table.

### Step 4 — Notify follow-up triggers

Processing result summary:
```
✅ Approved: {N}
❌ Rejected: {N}
🟡 On-hold: {N}
─────────────
Remaining pending (⬜): {N}
Remaining on-hold (🟡): {N}
```

If any pending/on-hold items remain:
- Explain that they will be re-confirmed in step 4 of the next session's `/sc`
- Warn that entering `/confirm` requires 0 remaining items ([[CONTEXT/dec-schema]] §4-3)

For any approved DEC whose `reversal` column has a supersede target:
- Check whether the existing DEC row's `key decision` cell has
  `~~strikethrough~~` applied
- If not, apply strikethrough automatically

If an approved DEC's `key decision` cell has a `🔒` marker (= a **hard
DEC / gate decision**):
- This DEC is not a mere record — it is a blocking line **enforced by a
  gate** (fix-plan-track-routing P2). `/lc`'s track-gate and the
  preconditions of `/graph-gen`/`/fanout` read this row to block
  contradictory actions.
- When approving a track/authoring-model-related hard DEC (e.g. `🔒
  section WO deprecated · dossier is the master`), check that it is
  consistent with the track value in `graph/project-mode.json`, and if
  they mismatch, notify the PM (to keep the machine marker and the
  decision ledger's SSoT aligned).

### Step 5 — Record in session-log.md

```markdown
- {date} /dec-approve: {N} approved / {N} rejected / {N} on-hold / remaining ⬜{N}+🟡{N}
  Processed DECs: DEC-077,DEC-078,DEC-079
```

---

## Authority Boundaries

- This skill modifies **only the `approval` column** of `decisions.md`.
- Other columns (`ID`, `Date`, `Domain`, `Key Decision`, `Reversal`,
  `Basis`) must never be modified.
- Sections outside the table (header meta, Freeze Records) are read-only.
- Adding new DEC rows is out of scope for this skill (registration is done
  by each registering skill — see [[CONTEXT/dec-schema]] §5 registration
  authority matrix).

---

## Output Files

| File | Change |
|---|---|
| `decisions.md` | Updates only the DEC table's `approval` column |
| `session-log.md` | Adds a 1-line processing summary |

---

## Workflow Connections

- Upstream skills (DEC registration): [[skills/write]], [[skills/su]], [[skills/sc]], [[skills/critique]], [[skills/integrate]]
- Freeze-entry gate: [[skills/confirm]] (requires 0 pending/🟡 items)
- Validation dependency: [[agents/integrator]] (I-03), [[agents/reviewer]] (V-01)
- Schema SSoT: [[CONTEXT/dec-schema]]
- Operating rules: [[CONTEXT/project-rules]]
