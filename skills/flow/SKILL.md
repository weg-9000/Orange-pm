---
name: flow
description: Generates a per-screen interaction sequence (4-state) and microcopy from screen-list.md and the screen WO template, and writes the screen WO draft file. Loads the {PREFIX}-B common policy before writing and confirms the Delta scope with the PM. Common policy content is never rewritten — only referenced via reference links. When {screen_id} is given, only that screen is processed alone. With the --sketch flag, prerequisite checks are skipped and the skill runs in free sketch mode.
triggers:
  - "flow"
  - "write screen"
  - "interaction sequence"
  - "sketch"
  - "sketch screen"
phase: 2
effort: high
model: opus
user-invocable: true
---

## Bootstrap cache guard (Improvement F — CONTEXT_OPTIMIZATION.md)

Load `CONTEXT/_session-bootstrap.md` only once per session, on first entry.
Do not re-read it if it was already read in the same session.
If the cache is missing or stale, refresh it with the following command before proceeding:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```

This guard replaces reloading the 6 source files layer-config / about-pm / project-rules / brand-voice /
doc-layer-schema / team-members. Reading the source files directly is allowed only when it is essential
to this skill's core task.


## Common-reference guard (C0, C-PIN, C3 — gates/master-derivation-gate.md SSoT)

Applies before writing a screen draft (except in `--sketch` mode). See `CONTEXT/gates/master-derivation-gate.md` for details.

1. Common cross-check: policy already covered in G2-A/B must not be rewritten — reference it only
   with a `[{doc_id} §X]` link (candidate §s from the B-headings-index only, no loading the full
   source text — token boundary).
2. C-PIN: pin `referenced_master: [{pin ID}@{version}]` in the draft frontmatter
   (authoritative ID from master-id-map.yml). Leaving it blank is an opt-out that requires
   justification in decisions.md.
3. Screen re-transcription self-check (C3): do not restate policy/formulas/commitment rates/input
   validation in the body — policy references use **only the standard marker** `[[POL §X-Y]]`
   (no non-standard notation), and input references use `[[spec-catalog variable-ID]]`.
   If re-transcription is detected, the self-check FAILs.
4. C-PIMPACT: record the frontmatter pin `referenced_policy: {POL doc_id}@{version}`
   (WP8-1 standard). When a policy § changes, policy_impact_scan uses this pin and the
   `[[POL §]]` marker to identify affected screen §s (reviewer V-17, policy-impact-gate).
5. PM confirmation is folded into the existing Delta/content confirmation step (do not add a
   separate serial prompt).


## I/O (Plan A — WO template ↔ draft single-file model)

- **Input**: `PROJECTS/{product}/drafts/{WO_ID}.draft.md`
  (an empty shell generated during the fanout step — frontmatter `status: empty`, `type: screen`,
  body containing the standard `## 1.–7.` section skeleton — the task-instruction section holds
  the requirement to write the interaction sequence (4-state) and microcopy, plus a
  `<!-- wikilinks:start/end -->` block)
- **Output**: `PROJECTS/{product}/drafts/{WO_ID}.draft.md`
  (**modifies the same file** — `status: empty → ai-draft`, filling the standard section skeleton with content)

> The previous spec (read work-orders/{WO_ID}.md and create a new drafts/{WO_ID}.draft.md) has
> been deprecated. Since fanout pre-creates the empty shell, flow modifies that shell in place.
> This I/O spec applies only to the formal execution mode — `--sketch` mode keeps its own separate
> sketches/ path.


## --sketch mode branch

If the `--sketch` flag is present, skip all of the prerequisite checks below (items 1–5) entirely
and run only the procedure in this section.

### Sketch prerequisites
The `{screen_id}` argument is required. If absent, ask the PM to provide a screen name (or a
temporary ID). Temporary ID format: `SKT-NNN` (sequential from 001, does not collide with
existing SCR-NNN).

### Sketch execution
1. Create the `sketches/` directory if it does not exist.
2. Create the file `sketches/{screen_id}.sketch.md`.
   - Record only content the PM provides, without referencing graph.json, WO, or decisions.md.
   - Do not perform B-policy validation, Delta confirmation, or vocabulary validation.
3. File header:
   ```markdown
   ---
   sketch_id: {screen_id}
   status: sketch
   promoted: false
   created_at: {UTC timestamp}
   note: This file is not a formal draft. Convert it with /promote {screen_id}.
   ---
   ```
4. Guide the PM to freely write screen ideas, interaction flows, and microcopy drafts.
   No structure is enforced — the 4-state format need not be followed.

### Sketch completion notice
```
Sketch saved: sketches/{screen_id}.sketch.md

This file is excluded from /review and /integrate validation.
It is not counted toward draft completion rate in /lc gate calculations.

To convert it into a formal draft:
  /promote {screen_id}   (run once graph.json and the WO are ready)
```

Sketch mode ends here. It does not proceed to prerequisite checks or the formal execution steps.

---
## Prerequisite checks

0. **Track audit (cluster-mode awareness — same signal as `/fanout` prerequisite 0)**
   If any of the following exist, this project is the **cluster(dossier) model = Track A**.
   - `PROJECTS/{product}/graph/project-mode.json` (track=A / model=dossier)
   - `PROJECTS/{product}/graph/cluster_map.json` or `graph.clustered.json`
   - `PROJECTS/{product}/drafts/cluster_*.draft.md` (dossier already written)

   If detected, **do not proceed with `/flow`.** In Track A, screen design is written as §2 of
   the cluster draft (fixed skeleton, `/write-cluster`) — there is no separate screen WO to fill.
   Direct the PM to `/write-cluster {product} {cluster_id}` instead (per
   `plan-audit` Step 3: "screen drafts not started → Track A: handled by dossier §2, no
   separate screen WO").
   If uncertain which track applies, run `/plan-audit {product}` first to confirm.

1. Check whether `PROJECTS/{product}/graph/screen-list.md` exists.
   If missing, direct the user to re-run `/graph-gen {product}` and stop.

2. Read the list of WOs with `type: screen` from `work-orders/index.md`.
   If there are 0 screen WOs, direct the user to re-run `/fanout {product}` and stop.

3. Check whether `decisions.md` exists.
   If missing, ask the PM to create decisions.md and stop.

4. Read PREFIX from `CONTEXT/layer-config.md`.
   Load the `{PREFIX}-A` terminology standard file from `CONTEXT/reference-docs/{ACTIVE_PREFIX}/A/`.
   If missing, proceed without vocabulary validation and register it in open-issues.md as P2.

5. If the `{screen_id}` argument is given, check whether that Screen ID exists in screen-list.md.
   If not, print the list of valid Screen IDs and stop.

6. **[status branch — Plan A unified schema]**
   For each screen WO to be processed, judge the `drafts/{WO_ID}.draft.md` file and its
   frontmatter `status` value against the following criteria (applied per-WO in step 1):

   - `status: empty` → proceed normally. flow fills the body and transitions to `status: ai-draft`.
   - `status: ai-draft` → proceed with the rewrite after user confirmation. Print the following warning:
     ```
     ⚠️ This draft is already in ai-draft status (result of a previous flow run).
        Rewriting it will overwrite the existing body. Continue? (Y/N)
     ```
   - `status: human-reviewed` → refuse. Do not modify without PM approval.
     Requires the explicit `--force` flag to proceed. Otherwise, print the following notice and
     skip this WO:
     ```
     ❌ This draft is in human-reviewed status (PM review complete).
        Use the explicit --force flag to modify it.
     ```
   - `status: frozen` → refuse. A v1.0 frozen document cannot be edited directly.
     It can only be modified by registering a new DEC and creating a new-version draft.
     Print the following notice and skip this WO:
     ```
     ❌ This draft is in v1.0 frozen status.
        To modify it, register a new DEC in decisions.md and create a new-version draft.
     ```
   - Missing `status` field → recommend migration and skip this WO:
     ```
     ⚠️ The frontmatter has no status field (a pre-Plan-A-schema draft).
        Migrate with the following command and re-run:
        python ${CLAUDE_PLUGIN_ROOT}/scripts/migrate_draft_frontmatter.py --hub-root . --product {product}
     ```
   - File itself absent → recommend running `/fanout {product}` and skip this WO.

   In single mode (`{screen_id}` specified), check only the 1 target WO and stop if rejected.
   In full mode, add rejected WOs to the skip count and proceed to the next WO.


## Execution steps

### Step 1 — Finalize the target screen WO list

If `{screen_id}` is specified → process only that 1 WO.
If unspecified → read all screen WOs from `work-orders/index.md`.

**Plan A branch applies:** apply the status-branch rules from prerequisite 6 per WO, and finalize
only processable WOs (`empty`, or user-approved `ai-draft`/`--force human-reviewed`) as the actual
targets. The previous rule "skip if a draft already exists" has been absorbed into the status
branch (judged by the status value).

Print the number of target WOs and the number of skipped WOs (by reason), and get a start
confirmation from the PM.


### Step 2 — Gather per-screen context

For each screen WO, gather context from the following sources:

**Read the screen-list.md entry:**
- Screen ID, screen name, purpose, linked REQ-NNN ID, associated policy WO ID

**Reference the associated policy WO draft:**
- If `drafts/{policy_WO_ID}.draft.md` exists, read its content.
- Extract the key rules and constraints from that policy section.
- If the draft does not exist, use the section summary from `work-orders/{policy_WO_ID}.md` instead.

**Reference the {PREFIX}-B common policy (cache-first, excerpt mode):**

> Improvements A, B (CONTEXT_OPTIMIZATION.md) — do not load the full source text.

1. Read the `inherits_from` list and `section` value of the associated policy WO.
2. **B-summary.md cache (Improvement A)**: if `CONTEXT/.template-cache/B-summary.md` is newer
   than the source, load only the cache. If stale or missing, refresh it with
   `python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_cache.py --hub-root .`.
3. **Heading-index excerpt (Improvement B)**: from `CONTEXT/.template-cache/B-headings-index.json`,
   extract the `line_start` / `line_end` for the section.id specified among that doc_id's
   sections, and load an excerpt with `Read offset=line_start limit=(line_end - line_start + 5)`.
4. Fallback (neither cache nor index available): after the notice
   `[{PREFIX}-B cache not generated — re-run /init-hub is recommended]`, load the source text from
   `CONTEXT/reference-docs/{ACTIVE_PREFIX}/B/`. If the file itself is absent,
   proceed after `[{PREFIX}-B file not found — skipping common policy reference]`.
5. From the loaded section, extract only the common policy provisions relevant to this screen.
6. **Do not rewrite** extracted items in the screen draft — mark them with a reference link only.
7. If all paths fail, register a P1 item in open-issues.md and continue.

**Extract related decisions from decisions.md:**
- Read decision items related to this screen name or REQ-NNN.

**Read the corresponding REQ-NNN item from requirements.md:**
- Read the user-behavior-based functional unit text from the Layer 1 FR item.


### Step 2-B — Delta pre-confirmation

After completing step 2's data gathering, confirm the Delta scope with the PM before writing
the screen draft.

Print the following table:

```
Delta pre-confirmation — {Screen ID} {screen name}

┌─────────────────────────────────────────────────────────────────┐
│ Common policy items applied (must not be rewritten in the draft) │
│  Source: {PREFIX}-B-NNN §N.N                                     │
│  · (common policy provision summary)                             │
│  → Draft notation: see [{PREFIX}-B-NNN] §N.N                     │
├─────────────────────────────────────────────────────────────────┤
│ Delta items specific to this screen (written directly in draft)  │
│  · (screen-specific behavior based on requirements.md / decisions.md) │
│  · [TBD] tag: items that need confirmation                       │
└─────────────────────────────────────────────────────────────────┘
```

Do not proceed to step 3 without PM confirmation.
If the PM adds or removes Delta items, update the table before starting to write.


### Step 3 — Write the 4-state interaction sequence

Define the following 4 states for each screen.
The rules from the associated policy WO must be reflected in each state definition.

**idle state:**
- Entry conditions (which user, via which path)
- Initial UI composition (information shown, active buttons)
- Exit methods (cancel, back navigation, external exit)

**loading state:**
- Trigger conditions (which action causes loading)
- UI changes (spinner, skeleton, button disabling, etc.)
- Timeout handling criteria (use the value in decisions.md if present, otherwise TBD)

**success state:**
- Result display method
- Next-action list (move to next screen, restart, complete processing)
- Success message text (written as microcopy in step 4)

**error state:**
- List of error types (auth error, permission error, server error, input error, etc. as fits
  the screen's characteristics)
- Recovery method for each error type
- Error message text + `{PREFIX}-A` error code (written in step 4)

Define exit/cancel/back-navigation flows as separate items.


### Step 4 — Write microcopy

Write the UI text elements for each screen.

**Writing rules:**
- No duplicate button labels within the same screen
- If `brand-voice.md` exists, apply its tone-and-manner standard
  (otherwise apply a formal, concise default and register it in open-issues.md as P2)
- Must use vocabulary registered in `{PREFIX}-A` (tag with TBD when terminology deviates)

**Items to write:**

| Element | Content |
|---|---|
| Button labels | All primary action buttons (including cancel/confirm) |
| Input fields | Placeholder + inline guidance text |
| Success message | success-state feedback text |
| Error message | Per-error-type message + `{PREFIX}-A` error code |
| Tooltip | Explanatory text shown when the user clicks the question-mark/? icon |
| Empty state | Title + guidance text shown when there is no data |


### Step 5 — Fill in the screen WO draft file body (lossless, gold-standard structure)

**Modify in place** `drafts/{WO_ID}.draft.md` (the empty shell created by fanout).
Do not create a new file — this is the core of the Plan A unified schema.

Update/confirm the following frontmatter fields (add if missing, update if present):
```markdown
version: draft
screen_id: {Screen ID}
written_at: {UTC timestamp}
policy_ref: {associated policy WO ID}
req_ref: {REQ-NNN}
binding_policy: Content owned by the screen (layout, 4-state, microcopy, guidance text,
  dependency list) is resolved into actual text. Only policy figures/formulas reference
  the policy document §X-Y / spec-catalog (drift-blocked).
```

> This step does not create a new `drafts/{WO_ID}.draft.md`. Modifying the shell created by
> fanout in place is the core of Plan A. The `status` transition is handled in step 6.

**Draft body structure (lossless — full accounting of source-screen facts, variable):**
- `## Overall screen-flow structure` — entry/transition flow between screens (text flow/table).
  Starting point of the User Journey.
- Repeat `# Screen N. {screen name}` per screen (once per screen in the source, none omitted):
  - `## N.1 Layout` — area composition/dimensions (actual container/column/header specs; if
    unknown, `[needs confirmation:]`), component placement
  - `## N.x Details by {functional area}` — behavior/rules/branches/display conditions. Policy
    figures use `see policy document §X-Y`
  - `## N.x Modals/popups/confirmation dialogs` — each modal separately: trigger, layout, buttons,
    copy. For delete modals, state the affected resource and outcome explicitly
  - `## N.x 4-State` — idle/loading/success/error (result of step 3)
  - `## N.x Microcopy (actual copy)` — | element | copy | full actual string (result of step 4,
    no token placeholders)
- `# Appendix A. Policy figure/formula reference index` — | referenced item (figures/formulas
  only) | source of truth (policy doc § / spec-catalog) |
- `# Appendix B. Open items` — | ID | content | owner | (resolve with `~~ID~~` strikethrough +
  resolution rationale/date)

Fill in the self-verification checklist as the completion criteria:
- Lossless: full mapping of source-screen facts (0 omissions; unclassified items go to
  `Appendix Z`, contradictions keep both sides tagged `[policy conflict]`) → confirm
- Matches screen-list.md entries / 0 screens omitted → confirm
- Overall screen-flow structure written → confirm
- 4-state defined for every screen → confirm
- Actual copy written for every microcopy item (no placeholder tokens) → confirm
- Appendix A policy figure/formula reference index / Appendix B open items written → confirm
- No rewriting of {PREFIX}-B common policy/policy figures (reference link only) → confirm
- Delta scope confirmed with PM → confirm
- No unfilled sections (Plan A): all standard template sections (`## 1.–7.`) written +
  0 unreplaced `{{...}}` placeholders → confirm
- 4-state fill obligation: idle/loading/success/error all filled (or a valid N/A reason stated) → confirm
- Policy reference notation: common policy citations use only the `[[POL §X-Y]]` standard marker → confirm
- If TBD items remain, leave the check unmarked + register in open-issues.md as P1

If content conflicting with a decisions.md rule is found during writing, insert a
`[policy conflict — {decisions.md item name}]` tag and register it in open-issues.md as P1.


### Step 5-B — Section-fill guidance (Plan A — work-order-template.md unified schema)

The draft body already contains the standard section skeleton pre-inserted by fanout
(the `## 1.–7.` numbered section headings from `<Hub root>/templates/work-order-template.md` —
a relative path based on the Hub working directory, not `${CLAUDE_PLUGIN_ROOT}` —
covering scope, reference contracts, task instructions (interaction sequence/microcopy),
self-verification, etc.).
The `<!-- wikilinks:start -->` … `<!-- wikilinks:end -->` block at the bottom of the body is an
area that fanout auto-fills with linked-WO links, so flow must not touch it arbitrarily.

**Section-fill rules:**

- When writing the body, fill in content precisely under each `## N. {section title}` heading.
- **Do not leave any standard section empty** — filling every section created by fanout is
  mandatory. If a section's content does not exist in the source, fill it with the one line
  `Not applicable — {reason}`.
- No unreplaced `{{...}}`-style placeholders (e.g. `{PURPOSE}`) may remain — replace all of them
  with actual content.
- Additional sections beyond the standard template sections (variable sections depending on the
  number of screens in the source) may be freely added (lossless principle).

**4-state fill obligation (the interaction-sequence item under `## 4. Task instructions`):**

- Fill in all 4 states: idle / loading / success / error.
- The notation `Not applicable — {valid reason}` is allowed only when a given state genuinely
  does not occur for that screen (e.g., no async call, so loading is unnecessary) (e.g. "this
  screen is static display only, no async calls").
- Unmet 4-state requirements (missing state + no reason) FAIL the step-6 self-verification.

**Policy reference notation (for common policy citation items):**

- Common policy citations use **only** the `[[POL §X-Y]]` **standard marker** (no non-standard notation).
- Do not restate policy figures/formulas in the body — reference the policy doc § or
  `[[spec-catalog variable-ID]]`.
- C-PIMPACT: record the frontmatter pin `referenced_policy: {POL doc_id}@{version}` (WP8-1 standard).


### Step 5-C — Frontmatter update (Plan A — status transition)

After passing self-verification, update the draft's frontmatter as follows (modify the same file in place):

- `status: empty` → `status: ai-draft`
  (keep `ai-draft` in the rewrite case)
- `last_updated: {current ISO8601 timestamp}` (add if missing, update if present)
- `review_status: ai-draft` (keep or add new — do not auto-promote to human-reviewed)

> This step does not create a new `drafts/{WO_ID}.draft.md`. Modifying the shell created by
> fanout in place is the core of Plan A.


### Step 6 — Completion report and session-log entry

Print a table of results per processed WO:
```
| WO ID | Screen ID | Screen name | TBD items | Policy conflicts | Result |
```

Append to session-log.md:
```markdown
- {date} /flow: {N} screen WO drafts generated / TBD {N} / policy conflicts {N}
```


## Result file list

| File | Content |
|---|---|
| `drafts/{WO_ID}.draft.md` (screen type) | Draft including screen flow, layout, 4-state, microcopy, Appendix A/B (lossless, variable; fanout shell modified in place — status: empty → ai-draft) |
| `open-issues.md` | TBD / policy conflict / brand-voice not registered P1/P2 |
| `session-log.md` | Summary record of screen draft generation |


## Next steps

For each screen draft: `/review drafts/{WO_ID}.draft.md`
Once all WOs (policy + screen) are complete: `/integrate {product}`
