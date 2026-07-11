---
name: review
description: >-
  Independently verifies the quality of {PREFIX}-C drafts via the reviewer agent. Reviews a single file when {draft_file} is specified, or all drafts in bulk with --all. If FAIL items are found, fix them and re-review. Runs in Phase 2.
triggers:
  - "review"
  - "check draft"
  - "validate draft"
agent: reviewer
phase: 2
effort: medium
user-invocable: true
---

## Bootstrap Cache Guard (Improvement F — CONTEXT_OPTIMIZATION.md)

On first entry into a session, load `CONTEXT/_session-bootstrap.md` only once.
If this file has already been read in the same session, do not re-read it.
If the cache is missing or stale, refresh it with the following command before proceeding:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```

This guard replaces reloading the 6 source files layer-config / about-pm / project-rules /
brand-voice / doc-layer-schema / team-members.
Reading the source files directly is allowed only when essential to this skill's core work.

## Precondition Checks

1. Check the `{draft_file}` argument.
   - If it is a single file path: confirm the file exists under `drafts/`.
   - If the `--all` option is given: set all of `drafts/*.draft.md` as the processing target.
   - If neither is given: ask the PM to provide a file path or the `--all` option.

2. Check whether the {PREFIX}-A / {PREFIX}-B cache files exist under `CONTEXT/.template-cache/`.
   If not, print a `[no cache — vocabulary/consistency verification unavailable]` warning and ask the PM whether to proceed anyway.

3. Check whether `graph/graph.json` exists.
   If not, print a `[no graph.json — inherits_from verification unavailable]` warning.


## Execution Steps

### Step 1 — Launch the reviewer agent

Pass the following context to the reviewer agent:

```
Review target: {draft_file or drafts/*.draft.md}

Reference files:
  - CONTEXT/.template-cache/{PREFIX}-A-*.cache.md
  - CONTEXT/.template-cache/{PREFIX}-B-*.cache.md
  - graph/integration-contract.md (frozen edge value reference — reviewer does not read graph.json directly)
  - decisions.md
  - brand-voice.md (if present)

Determine WO type:
  Read the type field in the draft header to branch into policy / screen
```


### Step 2 — Verification criteria by WO type

Check the WO type in the header of the draft under review.
Apply the following criteria based on the type.

#### Common criteria for policy WOs

| ID | Item | Criterion | Grade |
|---|---|---|---|
| RV-P01 | {PREFIX}-A vocabulary violation | Uses a status name or error code not registered in {PREFIX}-A | FAIL |
| RV-P02 | SSoT violation | Redefines {PREFIX}-B content directly (no Link used) | FAIL |
| RV-P03 | inherits_from contradiction | Content conflicts with a higher-layer policy | FAIL |
| RV-P04 | decisions.md violation | Inconsistent with a finalized project decision | FAIL |
| RV-P05 | frozen edge violation | Inconsistent with a frozen edge value in integration-contract.md (reviewer V-02) | FAIL |
| RV-P06 | Unresolved TBD | A TBD item exists and is not registered as P1 | WARN |
| RV-P07 | Incomplete section structure | A required section from the WO template is missing | WARN |
| RV-P08 | Security constraint violation | Missing rules related to personal data or authentication | WARN |
| RV-P09 | Style consistency | Mixed writing style (noun-form / verb-form mixed) | INFO |
| RV-P10 | FR↔cluster traceability | `fr_cluster_check.py` mismatch (i.e. fr_index↔cluster draft fr_refs inconsistency) → FAIL/BLOCK. orphan/unmapped are WARN. ([[CONTEXT/gates/fr-cluster-trace-gate]]) | FAIL |

#### Additional criteria for screen WOs

| ID | Item | Criterion | Grade |
|---|---|---|---|
| RV-S01 | Missing 4-state | One of idle / loading / success / error is undefined | FAIL |
| RV-S02 | Error code format | Does not follow the {PREFIX}-A error code format | FAIL |
| RV-S03 | Missing microcopy | Button label / error message / empty state not written | WARN |
| RV-S04 | Duplicate button label | Duplicate button labels within the same screen | WARN |
| RV-S05 | brand-voice non-compliance | Violates brand-voice.md criteria (if present) | WARN |
| RV-S06 | Related policy WO not referenced | Content from the implements-linked policy WO draft is not reflected | WARN |

#### Grade definitions

| Grade | Definition | Impact on /integrate |
|---|---|---|
| FAIL | Consistency/policy violation — must be fixed | Registered as BLOCK |
| WARN | Quality-degrading factor. Fix recommended | Can be allowed after PM confirmation |
| INFO | Style/readability improvement suggestion | No impact |


### Step 3 — Output the review results

For each draft file, output in the following format:

```
Review result: {draft_file}
WO type:   {policy / screen}

FAIL: {N}
WARN: {N}
INFO: {N}

FAIL items:
  [RV-P02] SSoT violation — Section 3 "Cancellation Policy" restates {PREFIX}-B-012 content directly.
            Fix: replace with a Link. Rewrite via `/write WO-03`.

WARN items:
  [RV-S03] Missing microcopy — error message not written for the error state.

INFO items:
  [RV-P09] Mixed style — Section 2 uses noun-form, Section 4 uses verb-form.
```

> **Review-attribution canonical field (C-ATTEST · reviewer V-16 · wo_emit work-board SSoT):**
> The canonical field for draft lifecycle is `review_status` (enum
> `empty→ai-draft→human-reviewed→frozen`). `wo_emit.py` (the work-board adapter)
> reads `review_status` first, and reviewer V-16 requires `review_status: human-reviewed`
> plus `reviewed_by` and `reviewed_at`. So on PASS confirmation, you
> **must transition `review_status`**. The legacy bare
> `reviewed: true/false` field is kept only as a backward-compatibility bridge (not a basis for new reads).

**FAIL 0 + WARN 0:**
Update the draft header as follows: `review_status: human-reviewed`, `reviewed_by: {ORANGE_PM_ID}`,
`reviewed_at: {UTC ISO 8601}` (+ backward-compatible `reviewed: true`).
Create `reports/review-{WO_ID}.md`.

**FAIL ≥ 1:**
Keep the draft header's `review_status` at `ai-draft` (+ backward-compatible `reviewed: false`).
For each FAIL item, specify the fix and the responsible skill.

**WARN ≥ 1 (FAIL 0):**
Present the list of WARN items to the PM and confirm whether they are accepted.
If accepted: set `review_status: human-reviewed` + `reviewed_by` + `reviewed_at` (+ `reviewed: true`),
and register in open-issues.md as P2.
If not accepted: fix and re-review.


### Step 4 — Generate reports/review-{WO_ID}.md

Generate this only when FAIL is 0:

```markdown
# review — {WO_ID}

**Reviewed at**: {UTC}
**WO type**: {policy / screen}
**Result**: PASS (FAIL 0 / WARN {N})

## Review item results

| ID | Item | Result |
|---|---|---|

## Accepted WARN items

| ID | Item | Registered in open-issues |
|---|---|---|
```


### Step 5 — Update open-issues.md

If there are FAIL items, register them in open-issues.md as P1:
```markdown
- [ ] [RV-{WO_ID}-FAIL] {WO_ID} FAIL: {item name} — fix and re-run /review
```

Register accepted WARN items as P2.


### Step 6 — Record in session-log.md

```markdown
- {date} /review {WO_ID}: FAIL {N} / WARN {N} / {PASS or FAIL}
```

When the `--all` option is used:
```markdown
- {date} /review --all: reviewed {N} / PASS {N} / FAIL present {N}
```


## Result File List

| File | Content |
|---|---|
| `reports/review-{WO_ID}.md` | Review results recorded on PASS confirmation |
| `drafts/{WO_ID}.draft.md` header | On PASS: `review_status: human-reviewed` + `reviewed_by` + `reviewed_at` updated (+ backward-compatible `reviewed: true`) / On FAIL: `review_status` stays `ai-draft` |
| `open-issues.md` | FAIL registered as P1 / accepted WARN registered as P2 |
| `session-log.md` | Review results recorded |


## Next Steps

After a single WO passes:
- Continue reviewing the next WO: `/review drafts/{next_WO_ID}.draft.md`

After all WOs pass:
- `/integrate {product}`: start integration verification
