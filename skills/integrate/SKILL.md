---
name: integrate
description: Runs integrated validation of all {PREFIX}-C drafts against the graph split files (graph.edges.json, graph.policy.json). Manages SSoT violations, vocabulary violations, layer contradictions, and cross-draft conflicts as BLOCKs, and permits entry into Phase 4 once 0 BLOCKs are achieved within 3 rounds.
triggers:
  - "integrate"
  - "final check"
  - "validate all"
agent: integrator
phase: 3
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

## Prerequisite checks

1. **Load the WO/dossier list (Improvement G — CONTEXT_OPTIMIZATION.md)**:
   - **Track A (cluster mode)** — if `work-orders/cluster_index.json` exists, read the full
     dossier list from its `clusters[]` array (`wo_id` / `cluster_id` / `draft_path`).
     `work-orders/index.json`/`index.md` are not generated in cluster mode — do not look for them.
   - **legacy/node mode** — if `cluster_index.json` is absent and `work-orders/index.json`
     exists, read the WO list from its `wo[]` array. Fall back to parsing the `index.md` table
     only if `index.json` is missing. Do not cite the body text.
   Check whether draft files exist for all of those WOs/dossiers under `drafts/`.
   If any drafts are missing, print the list and stop.
   Direct the user to run, per track: Track A → `/write-cluster {product} {cluster_id}` ·
   legacy → `/write {WO_ID}` or `/flow {product}`.

2. **Validate draft frontmatter (Improvement H)**:
   Confirm the standard frontmatter exists for all drafts with the following command:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/migrate_draft_frontmatter.py \
       --hub-root . --product {product} --check
   ```
   If exit code is 1 (missing items exist), print the list of missing files and stop.
   Direct the user to auto-fix by running the same command without `--check`, then retry.

3. Check the number of P0 items in `open-issues.md`.
   If there is 1 or more P0 item, print the list and stop.

4. Check whether `graph/graph.edges.json` + `graph/graph.policy.json` (Improvement C split files) exist.
   If the split files do not exist, fall back to the single `graph/graph.json`.
   If neither exists, direct the user to re-run `/graph-gen {product}` + `/fanout {product}` and stop.

5. **Validate the context cache (Improvements A, B)**:
   Check whether `CONTEXT/.template-cache/B-summary.md` and
   `CONTEXT/.template-cache/B-headings-index.json` exist.
   If either is missing or stale (older than `reference-docs/{ACTIVE_PREFIX}/B/*.md`),
   direct the user to first run
   `python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_cache.py --hub-root .` and
   `python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_index.py --hub-root .`.

6. Compute the current integrate round count from `session-log.md`.
   Count the number of `[integrate]` entries.
   If it exceeds 3 rounds, report the situation to the PM and confirm whether to force proceeding.


## Execution steps

### Step 1 — Launch the integrator agent

> Improvement H (CONTEXT_OPTIMIZATION.md) — scan frontmatter only, before loading bodies.

Pass the following context to the integrator agent:

```
Input files:
  - drafts/*.draft.md (scan frontmatter first → load bodies only after narrowing candidates)
  - work-orders/index.json (Improvement G — JSON instead of the markdown table)
  - graph/graph.edges.json + graph/graph.policy.json (Improvement C — use split files directly)
  - CONTEXT/.template-cache/B-summary.md (Improvement A — cache-first)
  - CONTEXT/.template-cache/B-headings-index.json (Improvement B — excerpt locations)
  - decisions.md
  - open-issues.md

Validation instructions:
  - Pass 1: scan only the frontmatter of drafts/*.draft.md (wo_id, type, layer,
    referenced_policies, referenced_screens, status) to group validation candidates
    (Improvement H).
  - From pass 2 onward, load bodies. Apply the 4 BLOCK criteria (see step 2)
  - Apply the 3 WARN criteria (see step 2)
  - Apply the 2 INFO criteria (see step 2)
  - Record cross-draft conflicts as WO ID pairs
  - Impact analysis: propagate based on implements / prerequisite edges in graph.edges.json
```


### Step 2 — Validation criteria classification

**BLOCK conditions (Phase 4 entry not permitted):**

| ID | Condition | Judgment criterion |
|---|---|---|
| BLK-01 | SSoT violation | {PREFIX}-B content directly redefined in a draft (no Link used) |
| BLK-02 | Layer contradiction | {PREFIX}-C content logically conflicts with a {PREFIX}-B rule. However, if the decisions.md DEC table has a DEC row for this item whose `Approval` cell is `✅`, exclude it from BLOCK → record as INFO instead. If only unapproved DECs (`⬜`·`🟡`) exist, keep it as BLOCK (PM approval required). See [[CONTEXT/dec-schema]] §4 approval gate. |
| BLK-03 | Vocabulary violation | Use of a status name/error code/term not registered in {PREFIX}-A |
| BLK-04 | Cross-draft conflict | Two WO drafts define conflicting rules for the same target |
| **BLK-05 (Phase 5H)** | **UPSTREAM_GAP** | 1 or more of: a missing FR (REQ_MISSING) / policy conflict (POLICY_CONFLICT) / insufficient competitor research (RESEARCH_GAP) / ambiguous terminology (TERM_AMBIGUOUS) recorded in the cluster draft's §4 (Open Questions / Upstream Feedback). Resolution path: revise D1/D5 (v++) via `/draft-req --upstream-feedback` and re-run. **Track A only** — this BLOCK does not apply to Track B/C. |
| **BLK-06 (P4)** | **FR↔cluster trace mismatch** | `fr_cluster_check.py` produces 1 or more mismatches (bidirectional) between fr_index and the cluster draft's `fr_refs` (`reports/fr-cluster-trace-queue.md` header `BLOCK: N` > 0, exit 2). Orphan/unmapped items are WARN (non-blocking). Resolution: augment/correct the cluster draft's `fr_refs`, or re-run `cluster_identify` re-clustering, then re-run. ([[CONTEXT/gates/fr-cluster-trace-gate]]) |

**WARN conditions (Phase 4 entry possible, PM confirmation required):**

| ID | Condition | Judgment criterion |
|---|---|---|
| WRN-01 | Dependency mismatch | A feature referenced by WO-A's draft is undefined in WO-B's draft |
| WRN-02 | Impact-propagation error | A policy WO change is not reflected in the implements-linked screen WO |
| WRN-03 | Missing dependency relationship | No edge exists in graph.edges.json, but the draft content implies a precedence relationship |

**INFO conditions (record only, does not affect proceeding):**

| ID | Condition |
|---|---|
| INF-01 | Tone-and-manner / style mismatch |
| INF-02 | Missing microcopy empty-state |
| INF-03 | BLK-02-excluded item — DEC table approved (`✅`) row (content: DEC-ID + item name + approver + date) |
| INF-04 | Remaining unapproved DECs — count of DEC rows with `Approval=⬜` or `🟡` (Phase 4 entry is still possible. 0 is required immediately before entering `/confirm` — [[CONTEXT/dec-schema]] §4-3) |


### Step 3 — Generate artifacts

**reports/integration-summary.md:**
```markdown
generated_at: {ISO8601}
# Integration Validation Summary — Round {N}

**Run time**: {UTC}
**Validation scope**: policy WO {N} / screen WO {N}
**Result**: BLOCK {N} / WARN {N} / INFO {N}

| Classification | Count | Phase 4 impact |
|---|---|---|
| BLOCK | {N} | Entry not permitted |
| WARN | {N} | Entry possible after PM confirmation |
| INFO | {N} | No impact |
```

> `generated_at:` must be recorded on **line 1** of the file. It is the criterion used by
> `/lc`'s master-derivation-gate STALE judgment.
> Format: `generated_at: 2026-05-24T09:30:00Z` (ISO 8601 UTC, no fractional seconds).
> ⚠ `generated_at:` must appear as line 1 with no `---` (YAML frontmatter delimiter) before it —
> to avoid confusing the YAML parser.
> If the file exists but has no `generated_at:`, `/lc` judges it STALE and requires re-running integrate.

**reports/conflict-report.md:**
Record the following details for each BLOCK item:
```markdown
## BLK-NN — {BLOCK ID} / {draft file name}

**Condition**: {BLK-01 – BLK-04}
**Violation details**: {specific content}
**Reference source**: {the violated standard document and item}
**Resolution method**: {what to fix and in which direction}
**Owning skill**: legacy — `/write {WO_ID}` or `/flow {product} {screen_id}` · Track A —
`/write-cluster {product} {cluster_id}`
```

**reports/impact-map.md:**
Based on the implements / prerequisite edges in graph.edges.json, record the WO connection
paths through which change impact propagates:
```markdown
## Impact Map

| Changed WO | Affected WO | Edge type | Reflected? |
|---|---|---|---|
```


### Step 4 — Per-round handling

**0 BLOCKs:**
- Permit entry into Phase 4.
- Add an auto-recorded row to the decisions.md DEC table (schema: [[CONTEXT/dec-schema]]):
  ```markdown
  | DEC-{NNN} | {MM-DD} | 🤖 | /integrate Round {N} passed · 0 BLOCKs · Phase 4 permitted | - | ✅ system | /integrate R{N} |
  ```
  - Auto-recorded (`🤖`) domain entries are registered as `✅ system` without PM approval
    ([[CONTEXT/dec-schema]] §5 registration-authority matrix)
- If unapproved (`⬜`·`🟡`) DECs remain, record them as INF-04 in the integration summary and
  direct the PM to `/dec-approve`.
- Proceed to step 5.

**1 or more BLOCKs:**
- Print conflict-report.md and report it to the PM.
- Present a list of the owning WO ID and fix skill for each BLOCK item.
- After the PM completes the fixes, re-run `/integrate {product}` (Round N+1).
- Present the WARN item list to the PM and confirm whether to accept them.
  If accepted, register them in open-issues.md as P2 and continue.
  If not accepted, fix the draft and re-run.

**BLOCKs still present after 3 rounds:**
- Escalate and register the BLOCK items in open-issues.md as P0.
- Present the PM with the following options:
  - Exclude the affected WO and proceed with a partial publish
  - Continue with additional rounds (Round 4+)
  - Freeze the affected WO as TBD and defer it to the next release cycle


### Step 5 — Record in session-log.md

```markdown
| 3 (Integrate) | {UTC timestamp} | /integrate Round {N} | BLOCK {N} / WARN {N} / {passed or not passed} |
```

If 0 BLOCKs, record the Phase as 4.


## Result file list

| File | Content |
|---|---|
| `reports/integration-summary.md` | Validation-result summary + round history |
| `reports/conflict-report.md` | BLOCK/WARN details + resolution methods |
| `reports/impact-map.md` | WO-to-WO impact-propagation map |
| `open-issues.md` | P2 registration on WARN acceptance / P0 registration when BLOCK exceeds 3 rounds |
| `decisions.md` | Phase 4 permission record on pass |
| `session-log.md` | Round N record |


## Next steps

Once 0 BLOCKs and all WARNs are accepted:
- `/confirm {product}`: v1.0-frozen finalization → Confluence upload → GitLab MR → announcement
