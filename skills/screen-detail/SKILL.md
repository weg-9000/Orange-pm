---
name: screen-detail
description: >-
  Writes a screen detail document at actual wiki-publication quality. The output format uses one of two options depending on screen type: - user-console: user console screens (Screen N. section structure) - backoffice:   back-office admin screens (4-column table structure) The project design system (loaded from the Hub's `CONTEXT/design-system.md`; falls back to general web component conventions if absent) is referenced internally for component selection and validation-rule decisions, and is never exposed as an output column.
triggers:
  - "screen-detail"
  - "screen detail"
  - "screen description"
  - "screen design"
  - "ui spec"
phase: 2
effort: medium
user-invocable: true
---

## Bootstrap Cache Guard (Improvement F — CONTEXT_OPTIMIZATION.md)

On first entry to a session, load `CONTEXT/_session-bootstrap.md` exactly once.
If this file has already been read in the same session, do not re-read it.
If the cache is missing or stale, refresh it with the following command before proceeding:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```

This guard replaces re-loading the 6 source files: layer-config / about-pm /
project-rules / brand-voice / doc-layer-schema / team-members.
Directly reading the source files is allowed only when essential to this
skill's core task.


## Common Reference Guard (C0 · C-PIN · C3 — gates/master-derivation-gate.md SSoT)

Apply before writing screen detail. See `CONTEXT/gates/master-derivation-gate.md` for details.

1. Common cross-check: do not rewrite policies already present in G2-A/B —
   reference them only via a `[{doc_id} §X] reference` link (only candidate
   §s from B-headings-index; do not load the full source — token boundary).
2. C-PIN: When adding Section 7, keep the draft frontmatter
   `referenced_master` pin (authoritative ID from master-id-map.yml). Leaving
   it empty is an opt-out → requires a decisions.md rationale.
3. Re-statement self-check (C3): do not restate input validation, formulas,
   contract rates, or policy rules in the screen detail body → for policy
   references use only the **standard `[[POL §X-Y]]` marker**, and for
   inputs use `[[spec-catalog variable_id]]`. Self-check FAILs if a
   restatement is detected.
4. C-PIMPACT: keep the draft frontmatter
   `referenced_policy: {POL doc_id}@{version}` pin (WP8-1 standard). When a
   policy § changes, policy_impact_scan identifies the affected screens at
   the § level (reviewer V-17 · policy-impact-gate).
5. PM confirmation is consolidated into Step 4 (PM proposal & confirmation) — do not add serial prompts.


## Output Format Decision

### Format Selection Criteria

| Format | Target Screens | Flag |
|---|---|---|
| `user-console` | user portal/console screens (button/layer/input section structure) | `--type user` (default) |
| `backoffice` | back-office/admin screens (item-list table structure) | `--type backoffice` |

If `--type` is not specified: auto-detect as `backoffice` if the screen name
in screen-list.md or the WO title contains "backoffice / admin /
management"; otherwise auto-detect as `user-console`.

---

## Precondition Checks

0. **Track audit (cluster-mode awareness — same signal as `/fanout` prerequisite 0)**
   If any of the following exist, this project is the **cluster(dossier) model = Track A**.
   - `PROJECTS/{product}/graph/project-mode.json` (track=A / model=dossier)
   - `PROJECTS/{product}/graph/cluster_map.json` or `graph.clustered.json`
   - `PROJECTS/{product}/drafts/cluster_*.draft.md` (dossier already written)

   If detected, **do not proceed with `/screen-detail`.** There is no standalone screen WO to
   attach a "Section 7. Screen Detail" to — screen design already lives in §2 of the cluster
   draft, written by `/write-cluster`. This skill's extra-detail table format is not yet ported
   to the cluster panel schema; add the needed detail directly inside that cluster draft's
   `§2-2 Screen Layout/Components` / `§2-3 Interactions/Policy Links` instead, or register the
   gap in `open-issues.md` as P2 if the table granularity is genuinely required.
   If uncertain which track applies, run `/plan-audit {product}` first to confirm.

1. Confirm the screen WO draft file corresponding to `{screen_id}` exists
   in `PROJECTS/{product}/drafts/`.
   If not, direct the user to run `/flow {product} {screen_id}` first.
   (However, with the `--pre-flow` flag, proceeding without a draft is
   allowed.)

2. Confirm the `{screen_id}` entry exists in
   `PROJECTS/{product}/graph/screen-list.md`.

3. Load the Hub's `CONTEXT/design-system.md` to confirm the project design
   system (name, version, component catalog location).
   If the file does not exist, proceed with general web component
   conventions instead of a specific design system.
   If a component catalog is declared, load
   `CONTEXT/design-system/stories.json` for internal reference; otherwise
   fall back to the component list in `CONTEXT/design-system/tokens.md`.


---

## Execution Steps

### Step 1 — Gather Screen Context

Gather the information needed for this screen from the following sources.

**screen-list.md entry:**
- Screen ID, screen name, purpose, URL path, GNB path

**screen WO draft (drafts/{WO_ID}.draft.md):**
- idle: initial UI layout, list of active buttons
- loading: what gets disabled, spinner/skeleton placement
- success: how results are displayed, next screen navigated to
- error: per-error-type messages (quoted), recovery method
- Microcopy: button labels, input placeholders, guidance text

**Items extracted internally (never exposed as an output column):**
- Design-system Button variant per button and its activation condition
  (default convention when no design system is specified: Filled/Outlined/Ghost/Danger)
- Validation rules and error messages per input field
- Select/Radio/Checkbox option lists and defaults
- Modal/layer display conditions and close triggers

This information is used to fill in the output document's content (button
behavior descriptions, guidance text, disallowed cases, etc.).


### Step 2 — Internal Design-System Reference

Internally map the collected screen elements to project design-system
components (based on `CONTEXT/design-system.md`; general web component
conventions if not specified). **The result of this step is used only to
determine output content (wording/rules/conditions), never as an output
column.**

**Mapping source priority:**
1. `.stories.tsx` files under `CONTEXT/design-system/stories/` → extract actual prop values from args/argTypes
2. `CONTEXT/design-system/stories.json` → confirm variant by story name
3. `CONTEXT/design-system/tokens.md` → Section 8 component list / Section 9 recommended mapping

**How the reference result is used:**
- Button variant → distinguishes "primary CTA" / "secondary" / "cancel" / "danger" in the button behavior description
- Input validation rules → used to write error cases and guidance text
- Select options → used to specify the option list
- Modal trigger conditions → used to write layer activation conditions


### Step 3 — Write the Screen Detail Draft

Write the draft according to the selected format.

---

#### [Format A] user-console — User Console Screens

Organize sections per screen. Each section can be opened independently.

**Output structure:**

```
Screen {N}. {screen name}

URL: {portal URL path}
GNB path: {GNB depth 1} > {GNB depth 2} > {screen name}

{N}.1 {section name — e.g. list, creation form, detail info}

  [Button behavior table]
  | Button | Activation condition | Action |
  |---|---|---|
  | {button name} | {condition — e.g. always / when 1+ selected} | {action description} |

  [If there is a layer/modal]
  {layer name} layer
  - Activation condition: {condition}
  - Guidance text: "{verbatim guidance text}"
  - Disallowed case: {disallowed-case description}
  - Buttons:
    | Button | Action |
    |---|---|
    | {button name} | {action} |

  [If there are input fields]
  - {field name}: {input rule}
    - Error: "{verbatim error message}"
  - {field name}: {input rule}

  [If there is a list/table]
  Displayed columns: {column1}, {column2}, {column3}
  Empty state: "{empty-state guidance text}"

{N}.2 {next section name}
  ...
```

**Writing rules:**
- Screen numbers (N) follow the order in screen-list.md
- Section numbers (N.1, N.2) are assigned by logical region order within the screen
- Write the button behavior table only when a section has 2+ buttons (use a description sentence for 1)
- Place the layer section directly below its trigger button
- Error messages and guidance text must always be quoted in double quotes
- Mark empty items (no empty state, no disallowed case, etc.) as "N/A"

---

#### [Format B] backoffice — Back-Office Admin Screens

Organize the entire page as a single 4-column table.
When section separation is needed, use a merged row (divider header) inside
the table.

**Output structure:**

```
{screen name}

| Item Name | UI Type | Detail | Notes |
|---|---|---|---|
| {item} | {Input / Select / Button / Table / ...} | {behavior/rule/displayed content} | {required?/condition/special notes} |
```

**UI type notation list** (default convention when no design system is
specified — mapped to the corresponding component name if a project design
system exists):

| Notation | Corresponding Component |
|---|---|
| Input | Input |
| Select | Select / Combobox |
| Multi Select | MultiSelect / GroupedMultiSelect |
| Radio | Radio / RadioGroup |
| Checkbox | Checkbox |
| Switch | Switch |
| DatePicker | DatePicker / Calendar |
| Table | Table / DataTable |
| Button | Button |
| Modal | Modal |
| Tab | Tabs |
| Pagination | Pagination |
| Toast | Toast |
| Text | Text / Title |

**Writing rules:**
- List items in screen order (top→bottom, left→right)
- Insert section-divider headers in the format `| **{section name}** | — | — | — |`
- Quote error messages in double quotes when they appear in the Detail column
- List Select/Radio options in the Detail column separated by slashes
- Mark required input items as `Required` in Notes; for conditionally required items, also state the condition

---

### Step 4 — PM Proposal and Confirmation

Show the written screen detail draft to the PM and request confirmation.

```
Screen detail proposal — {screen_id} {screen name} [{format}]

(full draft text)

Review requested:
  1. Please confirm the section layout matches the actual screen
  2. Please flag any button activation conditions/behaviors that need correction
  3. Please decide the direction for [TBD] items
```

Do not proceed to Step 5 without PM confirmation.
If the PM requests changes, revise only those items and re-propose.


### Step 5 — Add the Screen Detail Section to the screen WO draft

After PM approval, add a section to `drafts/{WO_ID}.draft.md`.

```markdown
---
## Section 7. Screen Detail

**Basis**: {design system name} v{version} | Format: {user-console | backoffice} | Written on: {date}

(the full screen detail text written in Step 3)

### 7-N. Open Items

| Item | Content | Priority |
|---|---|---|
| [TBD] items | ... | P1/P2 |

### Self-Verification

- [ ] All screen sections written
- [ ] Button behavior table activation conditions specified
- [ ] Error messages/guidance text quoted in double quotes
- [ ] Layer/modal activation conditions and disallowed cases specified
- [ ] [TBD] items registered in open-issues.md P1
```

Register TBD items in open-issues.md as P1.


### Step 6 — Completion Report

```
/screen-detail complete — {screen_id} {screen name}

  Format:          {user-console | backoffice}
  Screen sections: {N}
  Button actions:  {N} defined
  Layers/modals:   {N} defined
  TBD items:       {N} (open-issues.md P1)
  File added:      drafts/{WO_ID}.draft.md Section 7

Next step: /review drafts/{WO_ID}.draft.md
```

Append to session-log.md:
```markdown
- {date} /screen-detail {screen_id}: wrote screen detail [{format}] / {N} sections / TBD {N}
```


## Flags

| Flag | Behavior |
|---|---|
| `--type user` | force user-console format |
| `--type backoffice` | force backoffice format |
| `--pre-flow` | write an empty draft from screen-list.md alone, without a /flow draft |
| `--no-draft` | print to screen only, without adding to the draft (for review) |
| `--update` | overwrite if Section 7 already exists (default: stop and confirm) |


## Output File List

| File | Change |
|---|---|
| `drafts/{WO_ID}.draft.md` | Section 7. Screen Detail section added |
| `open-issues.md` | TBD items registered as P1 |
| `session-log.md` | screen-detail completion record |


## Position in the Phase 2 Workflow

```
/flow {product} {screen_id}
    → write 4-state interactions + microcopy
        ↓
/screen-detail {product} {screen_id}
    → write screen detail description (user-console | backoffice format)
        ↓
/review drafts/{WO_ID}.draft.md
    → full validation
```
