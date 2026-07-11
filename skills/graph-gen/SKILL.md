---
name: graph-gen
description: >-
  Loads {PREFIX}-A/B/C from local files under CONTEXT/reference-docs/ and uses the
  graph-generator agent to generate graph.json + screen-list.md. Completes Phase 0 after
  validate_graph.py validation and PM approval.
triggers:
  - "graph-gen"
  - "generate graph"
  - "build graph"
agent: graph-generator
phase: 0
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

0. **Progress-state audit (fix-plan-track-routing P2 — Warm Start protection)**
   If any of the following exist, this project is **already in Phase 2+**.
   Regenerating the graph risks restarting the authoring model and orphaning existing artifacts.
   - `PROJECTS/{product}/drafts/cluster_*.draft.md` (dossier already written)
   - `PROJECTS/{product}/graph/project-mode.json` / `cluster_map.json`
   - `PROJECTS/{product}/work-orders/index.md` already has WO entries filled in

   If detected, **do not proceed with graph regeneration immediately** — first run
   `/plan-audit {product}` to confirm the track (A/legacy) and the appropriate entry phase, then
   get the PM's explicit regeneration approval. If approved, backing up the existing `graph/`,
   `work-orders/`, and `drafts/` is mandatory.

1. Check whether `PROJECTS/{product}/inputs/requirements.md` exists.
   If missing, direct the user to run `/draft-req {product}` and stop.

2. Check the number of P0 items in `open-issues.md`.
   If there is 1 or more P0 item, print the list and stop.

3. Read the following values from `CONTEXT/layer-config.md`:
   - PREFIX
   - Local source path (`CONTEXT/reference-docs/{ACTIVE_PREFIX}/A|B|C/`)
   If not present, ask the PM to confirm.

4. If `graph/graph.json` already exists, ask the PM whether to regenerate it.
   If regeneration is confirmed, back up the files under the existing `graph/`, `work-orders/`
   and proceed.
   Backup path: `graph/.backup-{YYYYMMDD-HHMM}/`


## Execution steps

### Step 1 — Verify the policy-entry-gate

Run `/lc {product}` to check whether the policy-entry-gate passes.

policy-entry-gate criteria:

| Item | Criterion |
|---|---|
| requirements.md Layer 1 FR | 10 or more |
| requirements.md Layer 2 NFR | 5 or more |
| requirements.md Layer 4 actor definitions | complete |
| requirements.md Layer 5 external integrations | list exists |
| discovery-exit-gate pass record | Phase 0 exists in session-log.md |
| open-issues.md P0 | 0 |

If any item fails, print the list and stop.
Direct the user to re-run `/draft-req {product}` or edit requirements.md directly.


### Step 2 — Load upper-layer documents

Read files from the local `CONTEXT/reference-docs/` directory.

| Layer | Local path | Required? | Handling when file is missing |
|---|---|---|---|
| {PREFIX}-A | `CONTEXT/reference-docs/{ACTIVE_PREFIX}/A/` | Recommended | Print `[{PREFIX}-A file not found — skipping vocabulary validation]` and continue |
| {PREFIX}-B | `CONTEXT/reference-docs/{ACTIVE_PREFIX}/B/` | Recommended | Print `[{PREFIX}-B file not found — cannot reference common policy]` and continue |
| {PREFIX}-C | `CONTEXT/reference-docs/{ACTIVE_PREFIX}/C/` | Optional | Print `[{PREFIX}-C file not found — skipping common-module reference]` and continue |

Read all `.md` files within each directory in full. Exclude README.md.
Exclude files whose header has `status: Deprecated` from loading. If found, print a `[Deprecated excluded]` warning.

If 1 or more files were loaded, merge and save them under `CONTEXT/.template-cache/`:
```
CONTEXT/.template-cache/{PREFIX}-A-{YYYYMMDD}.cache.md
CONTEXT/.template-cache/{PREFIX}-B-{YYYYMMDD}.cache.md
CONTEXT/.template-cache/{PREFIX}-C-{YYYYMMDD}.cache.md (if present)
```

For any layer with no files at all, skip the validation items that depend on that layer.
Do not stop execution even if no layer has any files.


### Step 3 — Launch the graph-generator agent

Pass the following context to the graph-generator agent:

```
Input documents:
  - {PREFIX}-A cache (vocabulary / principles)
  - {PREFIX}-B cache (common policy)
  - {PREFIX}-C cache (if present)
  - inputs/requirements.md
  - inputs/requirements.seeds.yml (capability seed sidecar — if present)

Output targets:
  - graph/graph.json
  - graph/screen-list.md
  - graph/graph-preview.md

Generation rules:
  - {PREFIX}-C policy nodes: split by section based on requirements.md Layer 1 FR
  - {PREFIX}-C screen nodes: apply the Layer 1 FR per-screen split criterion
  - inherits_from edges: {PREFIX}-C → {PREFIX}-B/C layer direction
  - implements edges: screen node → policy node
  - prerequisite edges: between nodes with a logical precedence relationship
  - delta_required: true only for policy nodes that differ in content from {PREFIX}-B
  - keep duplicate-definition edges at 0
  - capability seed injection: read the requirements.seeds.yml sidecar and fill in
    node.capability (+ cluster_hint) for each C/work node from the matching FR key. Seeds are
    a hypothesis (seed-not-lock, DEC-B), so cluster_identify consumes them as union-find initial
    values and finalizes the actual boundaries. If the sidecar is absent or the FR key is
    missing, leave capability blank (cluster_identify computes it).
```

### Step 3-A — Capability seed sidecar injection (P1 → cluster_identify link)

graph-generator reads `inputs/requirements.seeds.yml` (an FR ID → capability hypothesis map) and
sets each C/work node's `capability` (and `cluster_hint`) from the matching FR key. Sidecar schema:

```yaml
"FR-101":
  capability: "Provisioning"
  cluster_hint: "PR-01"   # optional
  lock: false             # optional, default false
"FR-102":
  capability: "[needs confirmation]"
```

- Seeds are **a hypothesis (seed-not-lock, DEC-B)** — injected as node.capability, and
  `cluster_identify` verifies them against the 5-axis/threshold check to finalize the actual
  cluster boundaries (graph-generator does not fix the boundaries).
- If the sidecar is absent or the matching FR key is missing, leave capability blank
  (cluster_identify computes it).

If the agent finds unresolved vocabulary (terms undefined between requirements.md and
{PREFIX}-A), record it in `graph/unresolved-decisions.md`.


### Step 4 — Run validate_graph.py

Run `scripts/validate_graph.py`:

```
Input: graph/graph.json
Options: --json
```

| Result | Action |
|---|---|
| PASS (0 WARNs) | Proceed to step 5 |
| PASS (WARNs present) | Print the WARN list and proceed after PM confirmation |
| FAIL | Print the FAIL item list. Confirm with the PM whether to re-run graph-generator |

If there are FAIL items, re-instruct graph-generator to focus the step-3 re-run only on fixing
the FAIL items. Maximum 2 re-runs. If FAIL persists after 2 attempts, stop.


### Step 5 — Request PM review

Print `graph/graph-preview.md` and have the PM confirm the following items:

**Items to confirm:**

| Item | What to confirm |
|---|---|
| Upper-layer reference | Whether {PREFIX}-A/B/C Reference nodes were fully loaded |
| Policy WO list | Number of {PREFIX}-C policy nodes and the doc_id list |
| Screen WO list | Number of {PREFIX}-C screen nodes and the screen-name list |
| 3-piece set composition | Whether each screen has a policy link (implements edge) |
| inherits_from direction | Directional consistency of {PREFIX}-C → {PREFIX}-B/C |
| duplicate-definition edges | Confirm 0 |
| unresolved-decisions | Count + list of unresolved vocabulary items |
| delta_required distribution | Number of true nodes / false nodes |

PM approval (confirmed) → proceed to step 6.
PM requests changes → fix the specific node/edge, then re-run step 4.


### Step 6 — Record in session-log.md and decisions.md

Append to session-log.md:
```markdown
| 0 (Graph) | {UTC timestamp} | /graph-gen | policy nodes: {N} / screen nodes: {N} / unresolved vocabulary: {N} |
```

Append to decisions.md:
```markdown
- {date}: /graph-gen complete. graph_hash: {12-char hash}. {PREFIX}-B version: {version}.
```

If `unresolved-decisions.md` has items, auto-register them in open-issues.md as P2.


## Result file list

| File | Content |
|---|---|
| `graph/graph.json` | Full graph of nodes + edges |
| `graph/screen-list.md` | Extracted screen-node list + REQ links |
| `graph/graph-preview.md` | Human-readable summary for PM review |
| `graph/unresolved-decisions.md` | Unresolved vocabulary items (if any) |
| `CONTEXT/.template-cache/` | {PREFIX}-A/B/C cache files |
| `open-issues.md` | Auto-registered WARN / unresolved-vocabulary items |
| `session-log.md` | Phase 0 Graph record |
| `decisions.md` | graph_hash + version record |


## Next steps

Once PM approval is complete:
- `/fanout {product}`: generate Work Orders based on graph.json
