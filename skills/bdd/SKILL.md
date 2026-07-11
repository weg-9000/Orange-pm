---
name: bdd
description: Deterministically transforms the policy WO's state × action matrix and the screen WO's 4-state interaction sequence into Gherkin .feature acceptance criteria, and validates coverage (screen-required 4-state, feature staleness). The model does not invent scenarios — it maps draft table cells directly to Given/When/Then (SSoT). [[POL §X-Y]] markers and referenced_policy pins are preserved as Gherkin tags, linking policy traceability through to the dev team's tests. When {WO_ID} is specified, only that WO is processed.
triggers:
  - "bdd"
  - "acceptance"
  - "acceptance criteria"
  - "gherkin"
  - "feature file"
phase: 2
effort: low
model: haiku
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


## Design Principle — Deterministic Compilation (C-BDD)

This skill **does not invent** scenarios. As with C-RENDER (complete version),
a script **deterministically** converts the draft's behavior-spec table into
Gherkin — nothing more.

- Conversion owner: `bdd_assemble.py` (the model is not involved). The model
  only reads the result summary.
- The output (`reports/bdd/*.feature`) **must not be hand-edited** — dual
  authorship = SSoT collapse. If a change is needed, edit the source draft
  (`/write`/`/flow`) and re-run `/bdd`.
- Mapping rules:
  - policy: non-empty cells in the `state × action matrix` → `Given state / When action / Then value`
  - screen: rows in the `4-state interaction sequence` → `Given screen state (+condition) / When user action / Then UI display`
  - **For a cluster_draft, extract both §1 matrix (policy) and §2 4-state
    (screen)** and merge them into one `.feature` (tagged `@type:cluster`,
    sections separated by `# ── §1/§2 ──`). Coverage is validated on both
    §1 density (WARN) and §2 4-state completeness (UNCOVERED).
- Traceability: cell/row `[[POL §X-Y]]` markers → scenario tags `@POL-§…`,
  frontmatter `referenced_policy` pins → feature tags. This traces which
  acceptance criteria a policy §change affects, all the way through to the
  dev team's tests.


## Precondition Checks

1. Check that the `PROJECTS/{product}/drafts/` directory exists.
   If not, instruct the PM to re-run `/fanout {product}` and stop.

2. Check that the target draft's frontmatter `status` is `ai-draft` or
   higher. A draft with `status: empty` has no behavior spec yet, so it is
   skipped (instruct the PM to run `/write` or `/flow` first).

3. If a `{WO_ID}` argument is given, check that `drafts/{WO_ID}.draft.md`
   exists. If not, print the list of valid WOs and stop.


## Execution Steps

### Step 1 — Deterministic generation of acceptance criteria (.feature)

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/bdd_assemble.py --hub-root . --product {product} [--wo {WO_ID}] [--all]
```

- If `{WO_ID}` is not specified, all drafts are processed. With `--all`, a
  combined `{product}.all.feature` is also generated.
- Output: `PROJECTS/{product}/reports/bdd/{WO_ID}.feature`
- Collect the per-WO `N scenarios` summary from stdout. Do not reload the
  full `.feature` body.

### Step 2 — Coverage validation

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/bdd_coverage_scan.py --hub-root . --product {product}
```

- Output: `PROJECTS/{product}/reports/bdd-coverage-queue.md`
- Read only the queue's **header row** (`UNCOVERED: N · STALE: N · WARN: N`).
- `CONTEXT/gates/bdd-coverage-gate.md` is the SSoT for pass/fail criteria.
  This skill does not embed its own criteria.

### Step 3 — Report results

```
BDD acceptance criteria generated — {product}

Generated: {N} drafts → {total N} scenarios
  | WO | Type | Scenarios | Coverage |

Coverage gate (bdd-coverage-gate):
  UNCOVERED: {N}   {0 → ✅ / 1+ → ❌ FAIL}
  STALE:     {N}   {0 → ✅ / 1+ → ❌ FAIL}
  WARN:      {N}   {undefined matrix cells — non-blocking}
```

On FAIL (UNCOVERED·STALE > 0), follow the "On FAIL" table in
`bdd-coverage-gate.md` to direct the PM back to the appropriate skill
(`/flow`/`/write`).

### Step 4 — Record in session-log

Add to `session-log.md`:
```markdown
- {date} /bdd: {product} acceptance criteria {N} feature files / {N} scenarios / UNCOVERED {N} · STALE {N}
```


## Output Files

| File | Content |
|---|---|
| `reports/bdd/{WO_ID}.feature` | Per-WO Gherkin acceptance criteria (deterministically generated — do not hand-edit) |
| `reports/bdd/{product}.all.feature` | Combined full version (with `--all`) |
| `reports/bdd-coverage-queue.md` | Coverage validation results (UNCOVERED·STALE·WARN) |
| `session-log.md` | Generation summary record |


## Next Steps

- To resolve a coverage FAIL: run `/flow {product} {screen_id}` or
  `/write {WO_ID}`, then re-run `/bdd {product}`
- For overall gate status: `/lc {product}` (includes bdd-coverage-gate)
- After PASS: hand off `reports/bdd/*.feature` to the dev team (runnable
  with Cucumber/Behave)
