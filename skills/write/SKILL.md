---
name: write
description: Writes the policy WO draft. Before writing, always load the {PREFIX}-B common policy and confirm the Delta scope (this product's exceptions/extensions only) with the PM, then write. Content identical to {PREFIX}-B is never rewritten. For screen WO drafts, use the /flow skill.
triggers:
  - "write"
  - "write wo"
  - "draft policy"
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


## Common-reference guard (C0, C-PIN — gates/master-derivation-gate.md SSoT)

Applies before writing. See `CONTEXT/gates/master-derivation-gate.md` for detailed policy and judgment criteria.

1. Common cross-check: check whether the item being written already exists in G2-A/B by
   identifying only the candidate §section via `B-headings-index.json` (no loading the full
   source text — token boundary). If it already exists, do not rewrite it — replace it with a
   `[{doc_id} §X] reference` link instead. Ignoring B or restating it in your own words is also prohibited.
2. C-PIN: pin the common-policy basis for the Delta in the draft frontmatter
   `referenced_master: [{pin ID}@{version}]`. The pin ID is the authoritative ID from
   `CONTEXT/reference-docs/master-id-map.yml` (G2-A-001 / G2-B-001–004). Leaving it blank means
   opting out of common-policy reference → requires justification in decisions.md (otherwise WARN).
3. PM confirmation is folded into this skill's existing Delta-confirmation step (step 2)
   (do not add a separate serial prompt just for this guard — single checkpoint).


## I/O (Plan A — WO template ↔ draft single-file model)

- **Input**: `PROJECTS/{product}/drafts/{WO_ID}.draft.md`
  (an empty shell generated during the fanout step — frontmatter `status: empty`, body containing
  the standard `## 1.–7.` section skeleton plus a `<!-- wikilinks:start/end -->` block)
- **Output**: `PROJECTS/{product}/drafts/{WO_ID}.draft.md`
  (**modifies the same file** — `status: empty → ai-draft`, filling the standard section skeleton with content)

> The previous spec (read work-orders/{WO_ID}.md and create a new drafts/{WO_ID}.draft.md) has
> been deprecated. Since fanout pre-creates the empty shell, write modifies that shell in place.


## Prerequisite checks

1. Check whether `PROJECTS/{product}/drafts/{WO_ID}.draft.md` exists.
   If missing, direct the user to run `/fanout {product}` and stop.

2. **[status branch — Plan A unified schema]**
   Check the target draft's frontmatter `status` value:

   - `status: empty` → proceed normally. write fills the body and transitions to `status: ai-draft`.
   - `status: ai-draft` → proceed with the rewrite after user confirmation. Print the following warning:
     ```
     ⚠️ This draft is already in ai-draft status (result of a previous write run).
        Rewriting it will overwrite the existing body. Continue? (Y/N)
     ```
   - `status: human-reviewed` → refuse. Do not modify without PM approval.
     Requires the explicit `--force` flag to proceed. Otherwise, print the following notice and stop:
     ```
     ❌ This draft is in human-reviewed status (PM review complete).
        Use the explicit --force flag to modify it.
     ```
   - `status: frozen` → refuse. A v1.0 frozen document cannot be edited directly.
     It can only be modified by registering a new DEC and creating a new-version draft.
     Print the following notice and stop:
     ```
     ❌ This draft is in v1.0 frozen status.
        To modify it, register a new DEC in decisions.md and create a new-version draft.
     ```
   - Missing `status` field → recommend migration and stop:
     ```
     ⚠️ The frontmatter has no status field (a pre-Plan-A-schema draft).
        Migrate with the following command and re-run:
        python ${CLAUDE_PLUGIN_ROOT}/scripts/migrate_draft_frontmatter.py --hub-root . --product {product}
     ```
   - File itself absent → recommend running `/fanout {product}` and stop.

3. Read the draft file's frontmatter `type` value.
   - `type: screen` → direct the user to run `/flow {product} {screen_id}` and stop.
   - `type: cluster_draft` → direct the user to run `/write-cluster {product} {cluster_id}` and stop.
     (Track A cluster drafts use a 4-panel format, so their body structure differs from this
     skill's (node policy).)
   - `type: policy` → proceed.

4. Read `PROJECTS/{product}/graph/graph.json` and check the following fields of the
   corresponding WO_ID node:
   - `delta_required` value
   - `inherits_from` list (parent {PREFIX}-B doc_id list)
   - `includes` list ({PREFIX}-C doc_id list to reference)

5. Check whether `PROJECTS/{product}/decisions.md` exists.
   If missing, ask the PM to create it and stop.

6. Read PREFIX from `CONTEXT/layer-config.md`, and load the {PREFIX}-B file from
   `CONTEXT/reference-docs/{ACTIVE_PREFIX}/B/`.


## Step 1 — Load the {PREFIX}-B common policy (cache-first, section excerpt)

> **Improvements A, B (CONTEXT_OPTIMIZATION.md)** — loading the full source text is prohibited;
> load only the needed sections as excerpts, based on the cache/index.

**Load priority (must follow this order from top to bottom):**

1. **B-summary.md cache (Improvement A)**
   - If `CONTEXT/.template-cache/B-summary.md` exists and its mtime is the same as or newer than
     every file in `CONTEXT/reference-docs/{ACTIVE_PREFIX}/B/*.md`, load only the cache and end
     this step.
   - If the cache is missing or stale → refresh it with the following command and retry:
     `python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_cache.py --hub-root .`

2. **Heading-index-based section excerpt (Improvement B)**
   - Load `CONTEXT/.template-cache/B-headings-index.json`.
   - If the `inherits_from` entry in `graph.json` has an explicit value like `section: "3.2"`,
     find the item with `id == "3.2"` in that doc's `sections[]` and extract its `line_start` /
     `line_end`.
   - Use the `Read` tool to **partially load** only `offset=line_start`,
     `limit=(line_end - line_start + 5)`. Loading the full source text is prohibited.
   - If the index is stale, refresh it with
     `python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_index.py --hub-root .`.

3. **Fallback (only when neither cache nor index exists)**
   - Load the source text directly from `CONTEXT/reference-docs/{ACTIVE_PREFIX}/B/`. However,
     report the missing cache to the PM and direct them to re-run `/init-hub`. In a normal
     operating environment, this branch should never be reached.
   - If the file itself is absent, proceed after the notice `[{PREFIX}-B file not found]`.

**Print the load result in the following format:**

```
{PREFIX}-B common policy loaded (cache/excerpt mode)

  Source: .template-cache/B-summary.md (cache) + B-headings-index.json (excerpt locations)

  Sections this WO ({WO_ID}) inherits (excerpt-loaded):
  - {PREFIX}-B-001 §3.2 Resource limit calculation method (line 142-197, excerpt-loaded)
  - {PREFIX}-B-005 §2.1 Base billing unit             (line 88-119,  excerpt-loaded)
```

{PREFIX}-C documents in the `includes` list are also loaded under the same cache-first,
excerpt-based rules.


## Step 2 — Delta scope pre-confirmation (discuss with PM)

Branch according to the `delta_required` value.

### 2-A. When delta_required: false

```
⚠️ This node has delta_required: false.

  {WO_ID} ({document title}) fully applies the {PREFIX}-B common policy.
  No separate draft content is needed.

  Draft content to write:
  "Base policy fully applied — see [{PREFIX}-B-NNN document title]"

  Generate this one-line draft? (Y/N)
```

If PM answers Y → skip to step 5 and generate the one-line draft file.
If PM answers N → check the reason and inform the PM whether to modify delta_required in graph.json.

### 2-B. When delta_required: true

**Create a classification table of items by {PREFIX}-B section:**

```
Delta scope pre-analysis — {WO_ID}

┌─────────────────────────────────────────────────────────────────┐
│ Inherited document: {PREFIX}-B-NNN {document title}              │
│ Section: §{N}.{N} {section name}                                 │
├─────────────────────────────────────────────────────────────────┤
│ B-policy content (must not be rewritten in the draft):           │
│  · (summary of key provisions — based on {PREFIX}-B source text) │
│  · ...                                                           │
├─────────────────────────────────────────────────────────────────┤
│ Delta candidates (items that differ for this product):           │
│  · (exception candidates extracted from requirements.md,         │
│     decisions.md)                                                │
│  · (unconfirmed items tagged [TBD])                              │
└─────────────────────────────────────────────────────────────────┘
```

After printing the table, ask the PM to confirm:

```
Please review the Delta candidates above.

  Let me know if there are items to add.
  If there are items to remove, tell me the number.
  Drafting will begin once confirmation is complete.
```

Do not proceed to step 3 without PM approval.


## Step 2-C — Pre-registration of potentially conflicting Delta items

Among the Delta items finalized in step 2-B, detect
"items that logically conflict with a {PREFIX}-B rule."

**Detection criteria:**
- A Delta item defines a different value for the same target (behavior, condition, limit value,
  etc.) as the B-policy
- The Delta tries to allow a behavior that the B-policy "prohibits"
- This product changes a B-policy threshold (timeout, limit, etc.)

**If no conflict is detected:** proceed directly to step 3.

**If a conflict is detected:** confirm the following with the PM.

```
A potentially conflicting item was found.

  · {Delta item name}
    Conflict basis: conflicts with {PREFIX}-B-NNN §N.N "{summary of the B-policy provision}"
    Conflict type: {value change / prohibited behavior allowed / condition reversed}

Is this item an intentional exception based on a business decision?

  [Y] Pre-register it in decisions.md and continue writing
  [N] Reconsider the Delta item (return to step 2-B)
  [S] Don't decide now — tag it [TBD] and continue
      (register in open-issues.md as P1, must be resolved before /integrate)
```

**When [Y] is selected:**
Automatically register a candidate row in the `decisions.md` DEC table (schema: [[CONTEXT/dec-schema]]):
```markdown
| DEC-{NNN} | {MM-DD} | {domain} | {Delta item name} — {PREFIX}-B-NNN §N.N exception ({60-char basis summary}) | - | ⬜ | /write {WO_ID} |
```

- `DEC-{NNN}`: the largest ID in the table + 1 (3-digit zero-padded)
- `Domain`: auto-estimated from the WO-domain mapping (PM can correct it)
- The `Decision` cell states the conflicting target § + a condensed rationale
- `Status` cell = `⬜` (not approved). Only takes canonical effect once the PM edits the table
  directly or approves it with `/dec-approve`
- **Integrator handling**: when an I-03 violation is detected, only rows with `Status=✅` are
  treated as canonical. `⬜` rows are classified as INFO

Once recorded, proceed to step 3.

**When [S] is selected:**
Attach the `[TBD:unresolved-conflict]` tag to the item and proceed.
Register in open-issues.md as P1: `[WO_ID-conflict] {item name} — whether this is an intentional
exception is unresolved. Must be resolved before /integrate`


## Step 3 — Load the {PREFIX}-A vocabulary standard

Load the {PREFIX}-A-001 (glossary) file from `CONTEXT/reference-docs/{ACTIVE_PREFIX}/A/`.

On success → use it for terminology cross-checking in subsequent writing steps.
On failure → register in open-issues.md as P2 and continue.


## Step 4 — Write the policy draft

Write only the Delta scope confirmed by the PM in step 2 into the draft.

**Writing principles (absolute rules):**

| Principle | Action |
|---|---|
| Do not rewrite {PREFIX}-B content | State it in a single line: `see [{doc_id} document title] §NNN` |
| If there is no exception, use a one-line entry | `Base policy fully applied — see [{doc_id} document title]` |
| Do not use vocabulary not registered in {PREFIX}-A | If used, insert a `[TBD:{term}]` tag |
| Do not violate decisions.md | If a conflict is found, insert a `[policy conflict — {item name}]` tag |
| Record the C-PIN pin | State the Delta's common-policy basis `{pin ID}@{version}` in frontmatter `referenced_master` (authoritative ID from master-id-map.yml) |

**Open-item tag signal_type classification (classify as soon as found during writing):**

Open-item tags inserted during writing are classified into the following 3 signal_types.
State the classification result in the `signal_type` item of the step-6 completion report.

| signal_type | Tag format | Trigger condition | Outcome |
|---|---|---|---|
| TERM_MISSING | `[TBD:{term}]` | A term not registered in the `{PREFIX}-A` glossary is used | {PREFIX}-A supplementation candidate. Register in open-issues.md as P1. Type B signal → subject to manual PM handoff |
| POLICY_GAP | `[needs confirmation: B missing — {item}]` | An item that should exist in the `{PREFIX}-B` common policy is missing | {PREFIX}-B supplementation candidate. Register in open-issues.md as P1. Type B signal → subject to manual PM handoff |
| DEFINITION_CONFLICT | `[policy conflict — {item}]` | `{PREFIX}-B` definitions contradict or are mutually incompatible | Keep both sides. Register in open-issues.md as P0. Type B signal → subject to manual PM handoff |

> **Note**: POLICY_GAP / TERM_MISSING / DEFINITION_CONFLICT are **Type B signals** that require
> a supplement to the common layer ({PREFIX}-A/B). The PM hands these off manually, directly, to
> the relevant department's RE contact.
> **Creating an automatic file such as reverse-signal-queue.md is strictly prohibited** — keep the
> 1:1 per-department handoff model.
> A simple internal open item (Type A) is marked `[needs confirmation: {content}]` and closed out
> solely through open-issues.md P1/P0 handling.

**signal_type classification decision guide (Type A vs Type B judgment — γ-1):**

When inserting an open-item tag during writing, apply the following 3-step judgment in order.

```
Judgment 1: Is this item "a decision within this product's (C) scope" or "a common (A/B) layer
  decision"?
  - Resolvable within this product's scope (e.g. internal flow check, discussion with the dev team)
    → Type A (internal open item) — tag [needs confirmation: {content}] + close it out via
      open-issues.md P0/P1 handling.
  - Resolvable only if a common (A/B) definition exists
    → proceed to Judgment 2.

Judgment 2 (confirm the common-layer dimension): which common layer needs the supplement?
  - The term is missing from the {PREFIX}-A glossary
    → TERM_MISSING — tag [TBD:{term}]. {PREFIX}-A backfill candidate.
  - A common policy provision that should be in {PREFIX}-B is missing
    → POLICY_GAP — tag [needs confirmation: B missing — {item}]. {PREFIX}-B supplementation candidate.
  - {PREFIX}-B definitions contradict each other / are mutually incompatible
    → DEFINITION_CONFLICT — tag [policy conflict — {item}]. {PREFIX}-B definition-correction candidate.

Judgment 3 (boundary is ambiguous): "If this item were reported to the department's RE contact,
  would it be accepted as useful information (grounds for a common-layer supplement)?"
  - YES → Type B (apply signal_type classification, register in open-issues.md ## RE handoff tracking)
  - NO  → Type A (treat as an internal open item, register only in open-issues.md P0/P1)
```

> If the boundary judgment is difficult, apply Judgment 3 first.
> An item handled as Type A can later be reclassified as Type B if the context changes — handle
> this by editing open-issues.md.

**Additional rule for calculation-type (billing formula) products (C2 — master-derivation-gate):**

- Billing formulas are **derivations** of G2-B Product Billing Policy §B (formula-handling
  principles, discount-application order, pro-rated free traffic) and must not be redefined —
  attach the G2-B § link alongside the formula body.
- Formula variables cite **only the variable ID** from `inputs/spec-catalog.md` (free-form
  variable names are prohibited).
- After writing the draft, update `graph/formula-binding.md` (template:
  `templates/formula-binding-template.md`): a 1:1 binding of formula variables to spec-catalog
  fields. If even one UNBOUND item remains, self-BLOCK (step 5) → reinforce spec-catalog or
  correct the formula, then rewrite.
- Console-type (non-formula) products are not subject to this rule or to formula-binding.

**Draft structure (lossless, variable sections — gold-standard/critique 9-axis criteria):**

> **The fixed 8-section (●◐○ pattern) approach has been deprecated.** Fixed sections and
> "abbreviated entries/omissions" caused mass omission of source-policy facts. It now follows
> **lossless restructuring + a variable section library**.

**Lossless principle (top priority — violating it is the most serious defect):**
- Do not discard a single policy fact, figure, case, exception, UI phrase, or table from the
  source/input. This is not a summary — it is a **structural rearrangement**. Facts that don't
  fit anywhere must not be discarded — carry them over verbatim to the final
  `## Appendix Z. Unclassified source facts`.
- Do not abbreviate or omit content for the sake of length (there is no instruction to "keep it
  brief" — fit everything in using tables and nesting).
- Do not fabricate content absent from the source. If uncertain, use `[needs confirmation: {what}]`.
  If the source is self-contradictory, don't pick one side — **preserve both** with
  `[policy conflict — {item}]`.

Sections are **variable length** (not a fixed count). Add as many sections/subsections as the
source content requires. Items identical to {PREFIX}-B (common) are not rewritten — state them in
a single line as `see [{PREFIX}-B-NNN document title] §N` (keeping the Delta + link as SSoT).
Do not re-enter unit prices, rates, or figures — use the `inputs/spec-catalog.md` variable
ID/§reference instead (the C-RENDER full version expands them automatically).

```markdown
---
doc_id: {WO_ID}
type: policy
version: draft
written_at: {UTC timestamp}
inherits_from: [{PREFIX}-B-NNN, ...]
referenced_master: [{PREFIX}-B-NNN@{version}, {PREFIX}-A-001@{version}]
includes: [{PREFIX}-C-NNN, ...]
delta_required: true
pattern: {A|B|C}
---

**Tagging**
**doc_id:** {WO_ID}
**version:** {version}
**pattern:** {A|B|C}
**status:** draft
**owner:** Planner

---

# {document title}

> This document is the policy definition for {product name}.

---

## Meta block (top of document)

- **Document description** — 1–2 sentence purpose
- **Table of contents** — full list of sections/subsections
- **Related planning documents / reference documents** — known links (if none, `[needs confirmation: related documents]`)
- **Revision history** — | Version | Date | Changed by | Comment |

---

## 1. Policy overview

### 1-1. Purpose
### 1-2. Scope of application
### 1-3. Core principles
### 1-4. Term definitions (canonical terms)

| Canonical term | Definition | Non-canonical (prohibited) |
|---|---|---|
| (canonical term) | (definition) | (prohibited synonym) |

> This table is the SSoT. Afterward, the body/tables/UI copy use only canonical terms (no mixing
> in synonyms — critique AXIS-01/02).

---

## 2. Common policy

### 2-1. State definitions

Enumerate + define every state. State the console display name = internal code mapping explicitly.

### 2-2. Allowed actions by state

| State \ Action | (action 1) | (action 2) | … |
|---|---|---|---|
| (state) | allowed/not allowed | … | |

> Full state × action matrix. Break down failure-recovery cases (critique AXIS-09).

### 2-3. Access control by permission / role definitions
### 2-4. (Service-specific common rules)

---

## 3. Creation/application policy

### 3-1. Entry conditions / input items and validity

| Category | Item | Validity rule/restriction | Notes |
|---|---|---|---|
| (category) | (item) | (range/format/reserved words) | |

### 3-2. Processing flow by case

Normal / failure / cancellation / timeout / zero-count / duplicate / concurrent — **full accounting
of every branch** (critique AXIS-03).

### 3-3. Completion handling

Creation-complete = state whether the resource is actually usable + guide the next step (critique
AXIS-05).

---

## 4. Deletion/termination policy

### 4-1. Conditions for deletion
### 4-2. Deletion handling and data cleanup

Cascade/chained effects, scope of impact on related resources.

---

## (Optional section library — create a section whenever the source has corresponding content)

> **Add** as many sections/subsections as the source has features. For standard sections that don't apply, keep the heading + one line `Not applicable — {reason}`.

- `## Core operational policy` — by the service's core feature (record/IP/snapshot/parameter group/scaling, etc.). Split into N-x subsections matching the number of source features
- `## Delegation/integration policy` / `## Routing/network integration`
- `## Security/traffic policy` — masking, authentication, sensitive information (AXIS-08)
- `## Incident/recovery policy` — break down inter-state failure-recovery cases
- `## Product/billing policy` — units, calculations, mid-term enrollment, termination, pro-rating, penalties. Figures use spec-catalog § references; formula structure only (AXIS-07)
- `## Event log policy` — | Event | Content | Type | Source (console/API/automatic) | Customer-visible |
- `## Notification (email/SMS) dispatch policy` — list of dispatch events + **mail template spec per event × state** (subject/greeting/body/caveats/CTA + `{variable}`, full actual copy) + events not dispatched
- `## Back-office policy` — list-page policy + columns / detail page (by area). Must be consistent with the console policy
- `## Monitoring policy` — aggregation units, lookup items
- `## Future enhancement considerations` — BACKLOG (v2)

> **Service archetype hints** (weighting for optional sections — not a structural requirement): infrastructure type = staged validation, admin manual control / compute type (AutoScale, LB) = state-machine group, 2-tier member, reservation/threshold separation / security-application type = flow diagram, ops-portal API, manual procedure / snapshot type = tight coupling to the source doc_id's lifecycle / container type = platform vs. customer resource boundary, registry > image > artifact.

---

## Interface binding (if applicable)

Detailed API specs live in {PREFIX}-E. This section covers only the policy-level URL/portal
binding (if not applicable, heading + reason).

---

## Dependencies & scope of impact

State Upstream/Downstream **by doc_id**. Cross-validate bidirectional impact with the owners of
related products.

---

## Open items

### P1 open items — needs discussion

| ID | Content | Who to confirm with | Related policy |
|---|---|---|---|
| [TBD] | (content) | (dev team/business unit/security team) | §N |

### P2 open items — optional supplement

(If the source tracks discussions) `## Open discussion-item status` — | No | Section | Discussion item | Handling status | Notes |
(If unclassified source facts exist) `## Appendix Z. Unclassified source facts` — preserved verbatim from the source

---

## Workflow Connections

Related documents/next steps [[link]].

---
## Self-verification checklist

- [ ] Lossless: full mapping of source facts (0 omissions; unclassified items in Appendix Z; contradictions preserved on both sides with [policy conflict])
- [ ] No rewriting of {PREFIX}-B content — Delta + `[{PREFIX}-B-NNN] §N reference` link only
- [ ] 1-4 term definitions (canonical terms) table declared + only canonical terms used thereafter
- [ ] 2-2 state × action matrix covers every state (critique AXIS-09)
- [ ] 3-2 full accounting of case branches: normal/failure/cancellation/timeout/zero-count/duplicate/concurrent (AXIS-03)
- [ ] No re-entering figures/unit prices — spec-catalog variable ID/§ reference (calculation type: formula-binding UNBOUND count 0)
- [ ] frontmatter referenced_master pin recorded (if list is empty, decisions.md opt-out justification present)
- [ ] Delta scope confirmed by PM
- [ ] {PREFIX}-A vocabulary standard followed (if deviating, [TBD:] + open-issues P1)
- [ ] No decisions.md violations (if conflicting, [policy conflict] + open-issues P0)
- [ ] Dependencies stated bidirectionally by doc_id
- [ ] P1/P2 open-item tables written + linked to open-issues.md
- [ ] Passes critique 9-axis self-check (if not passed, reinforce and resubmit)
```

**Handling items found during writing:**
- `[TBD:{term}]` occurs → after finishing the draft, register in open-issues.md as P1
- `[policy conflict — {item name}]` occurs → register in open-issues.md as P0 and report to the PM immediately


## Step 4-B — Section-fill guidance (Plan A — work-order-template.md unified schema)

The draft body already contains the standard section skeleton pre-inserted by fanout
(the `## 1.–7.` numbered section headings from `<Hub root>/templates/work-order-template.md` —
a relative path based on the Hub working directory, not `${CLAUDE_PLUGIN_ROOT}`).
The `<!-- wikilinks:start -->` … `<!-- wikilinks:end -->` block at the bottom of the body is an
area that fanout auto-fills with linked-WO links, so write must not touch it arbitrarily.

**Section-fill rules:**

- When writing the body, fill in content precisely under each `## N. {section title}` heading.
- **Do not leave any standard section empty** — filling every section created by fanout is
  mandatory. If a section's content does not exist in the source, fill it with the one line
  `Not applicable — {reason}`.
- No unreplaced `{{...}}`-style placeholders (e.g. `{SECTION_SUMMARY}`) may remain — replace all
  of them with actual content.
- Additional sections beyond the standard template sections may be freely added (lossless principle).


## Step 5 — Perform self-verification

After completing the draft, check the following items in order.

| Verification item | Criterion | Verdict |
|---|---|---|
| {PREFIX}-B rewritten? | Detect paragraphs that copy an inherited section's content verbatim | FAIL → delete that paragraph |
| Delta declaration exists | Whether Section 0-2 is written | FAIL → write it and re-verify |
| C-PIN pin exists | Whether frontmatter `referenced_master` is recorded | FAIL → record the pin and re-verify (an empty list = opt-out passes if justified in decisions.md) |
| formula-binding (calculation type) | `graph/formula-binding.md` UNBOUND count is 0 | FAIL → reinforce spec-catalog / correct the formula (N/A for console type) |
| Number of TBD items | TBD in core-rule areas | FAIL → register as P1 |
| decisions.md conflicts | Number of conflict tags | FAIL → register as P0 |
| {PREFIX}-A vocabulary | Number of unregistered terms | WARN |
| Missing section fill (Plan A) | All standard template sections (`## 1.–7.`) written + 0 `{{...}}` placeholders | FAIL → fill empty sections / remove placeholders |
| [Self-verification] signal_type classification match | Does every open-item tag match the classification decision guide (Judgment 1-2-3)? For boundary-ambiguous items, confirm with the PM before finalizing classification | WARN → if mismatched, re-confirm with PM |


## Step 5-B — Frontmatter update (Plan A — status transition)

After passing self-verification, update the draft's frontmatter as follows (modify the same
file in place):

- `status: empty` → `status: ai-draft`
- `last_updated: {current ISO8601 timestamp}` (add if missing, update if present)
- `review_status: ai-draft` (keep or add new — do not auto-promote to human-reviewed)

> This step does not create a new `drafts/{WO_ID}.draft.md`. Modifying the shell created by
> fanout in place is the core of Plan A.


## Step 6 — Completion report and session-log entry

```
/write complete — {WO_ID}

  Draft location: drafts/{WO_ID}.draft.md
  Number of Delta items: {N}
  TBD items: {N} (registered in open-issues.md as P1)
  Policy conflicts: {N} (registered in open-issues.md as P0)
  {PREFIX}-B rewrites: 0 ✅

  signal_type summary:
    TERM_MISSING:        {N}  → {PREFIX}-A supplementation candidate (subject to manual PM handoff)
    POLICY_GAP:          {N}  → {PREFIX}-B supplementation candidate (subject to manual PM handoff)
    DEFINITION_CONFLICT: {N}  → {PREFIX}-B definition-correction candidate (subject to manual PM handoff)
    Internal open items (Type A): {N}  → closed out via open-issues.md handling

  Type B signal department RE handoff tracking (γ-2):
    Type B total: {N}
    {N > 0} → RH-NNN row registered in the open-issues.md ## RE handoff tracking section
    {N = 0} → no Type B signals (common-layer consistency confirmed ✅)
    * Actual handoff is done manually by the PM directly to the department's RE contact. No automatic sync.

Next step: /review drafts/{WO_ID}.draft.md
```

Append to session-log.md:
```markdown
- {date} /write {WO_ID}: policy draft created / Delta {N} / TBD {N} / conflicts {N}
```


## Result file list

| File | Content |
|---|---|
| `drafts/{WO_ID}.draft.md` | Delta-only policy draft |
| `open-issues.md` | TBD (P1) / policy conflict (P0) / {PREFIX}-B not loaded (P1) / RE handoff tracking (Type B signals) |
| `session-log.md` | Summary record of the draft |

**open-issues.md standard section structure (based on write-skill output):**

Keep the existing P0/P1 sections as-is. When a /write run produces 1 or more Type B signals,
add the following section at the end of `open-issues.md` (create it if missing, add a row if it
already exists).

```markdown
## RE handoff tracking (Type B signals)

> This section is where the PM manually tracks Type B signals that require a supplement to the
> common layer ({PREFIX}-A/B).
> No automatic sync — the PM hands these off directly to the department's RE contact and updates
> the status by hand.
> Type A (internal open item) items are handled in the existing P0/P1 sections and are not
> registered in this section.

| signal_id | signal_type | Discovery context | Common domain | Handoff status | Handoff date | Common-layer reflection confirmed date |
|---|---|---|---|---|---|---|
| RH-001 | POLICY_GAP | {WO_ID} draft §{section number} | {PREFIX}-B.{domain} | ⬜ not handed off | - | - |
```

**signal_id rule**: `RH-NNN` (Reverse Handoff, 3-digit sequence — project-wide running number)

**Handoff status enum (updated manually by PM):**
- `⬜ not handed off` — not yet delivered to the department's RE (default)
- `🟡 handed off` — PM has delivered it to the department's RE contact (handoff date recorded)
- `✅ reflected in common layer` — RE confirmed it has been reflected in {PREFIX}-A/B common layer (reflection-confirmation date recorded)

If there are 0 Type B signals, do not create this section (or, if it already exists, do not add a row).


## Next steps

```
/review drafts/{WO_ID}.draft.md
```
