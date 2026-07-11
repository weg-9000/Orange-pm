---
name: fanout
description: Validates graph.json with validate_graph.py, then runs fanout_dag.py to generate policy WOs and screen WOs and build work-orders/index.md. This is the Phase 1 entry skill.
triggers:
  - "fanout"
  - "generate work orders"
  - "make wo"
phase: 1
effort: medium
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

0. **Track audit (fix-plan-track-routing P2 — highest priority)**
   If any of the following exist, this project is the **cluster(dossier) model = Track A**.
   - `PROJECTS/{product}/graph/project-mode.json` (track=A / model=dossier)
   - `PROJECTS/{product}/graph/cluster_map.json` or `graph.clustered.json`
   - `PROJECTS/{product}/drafts/cluster_*.draft.md` (dossier already written)

   If detected, **do not proceed with legacy fanout.** Direct the PM to `/fanout --cluster-mode`.
   Only pass `--force-legacy` if the PM explicitly wants to force legacy (in this case, be sure to
   disclose that WO shells will be generated alongside the existing dossier).
   If uncertain, run `/plan-audit {product}` first to confirm the track.

   > fanout_dag.py itself detects this signal and fails closed, so skipping this item will not
   > mass-produce empty WO shells. Still, informing the PM of the track first is the correct order.

1. Check whether `PROJECTS/{product}/graph/graph.json` exists.
   If missing, direct the user to run `/graph-gen {product}` and stop.

2. Check the number of P0 items in `open-issues.md`.
   If there is 1 or more P0 item, print the list and stop.

3. Read PREFIX from `CONTEXT/layer-config.md`.
   If PREFIX is not registered, ask the PM for input.

4. Check whether `freeze: false` in `decisions.md`.
   If already frozen, confirm with the PM whether WO regeneration is intended.


## Execution steps

### Step 1 — Validate graph.json

Run `scripts/validate_graph.py`:
```
validate_graph.py  PROJECTS/{product}/graph/graph.json
                   --json
```
> Omit `--schema` (per the 2026-06-08 H5 audit). When no schema is given, validate_graph
> auto-discovers `templates/graph-schema.json` in this order: cwd (Hub) → graph.json's parent →
> the plugin. A literal `--schema templates/graph-schema.json` only resolves from the Hub cwd,
> so it fails with a false FileNotFoundError→exit 2 when cwd differs. Defer to auto-discovery,
> as in graph-gen step 4.

Parse the result:
- If there are FAIL items, print the error list and stop execution.
  Direct the user to re-run `/graph-gen {product}`.
- If there are WARN items, print the list and ask the PM whether to continue.
- If PASS, proceed to the next step.

Print validation statistics (node count, edge count, per-type aggregates) in one line.


### Step 2 — Handle nodes with delta_required: false

Collect policy nodes in graph.json with `delta_required: false`.
Exclude these nodes from WO generation and record them in
`work-orders/no-delta-list.md` in the following format:

```markdown
# No-Delta Node List

The following nodes fully apply the {PREFIX}-B common policy as-is and no separate WO is generated.
When uploaded to Confluence, they are auto-recorded as "[{doc_id} default policy fully applied]".

| doc_id | Document title | inherits_from | Notes |
|---|---|---|---|
| {doc_id} | {title} | {PREFIX}-B-{NNN} | delta_required: false |
```

Screen nodes are always subject to WO generation regardless of the `delta_required` field.


### Step 3 — Run fanout_dag.py

Run `scripts/fanout_dag.py`:
```
fanout_dag.py  PROJECTS/{product}/graph/graph.json
               --output  PROJECTS/{product}/work-orders/
               --product {product}
               --prefix  {PREFIX}
```

**Mode flags (fix-plan-track-routing):**
- (none) — **default = legacy**. Generates section policy WOs + screen WOs. However, if the
  cluster signal from prerequisite 0 is detected, it fails closed and stops.
- `--cluster-mode` — **Track A (Full Product)**. Generates WOs at cluster(dossier) granularity.
  `cluster_identify.py` must run first so the graph has capability/cluster_id.
- `--force-legacy` — Ignores the cluster signal and forces legacy (bypasses fail-closed).
  Use only after confirming intent, since WO shells will be generated alongside the existing dossier.
- `--publication-mode {dossier-page|split-deliverable}` — **cluster-mode only**
  publication mode (fix-plan-dossier-publish-split). Persisted in `graph/project-mode.json`
  and read by `/render`, `/cr`, and sync as the branching basis.
  - `dossier-page` (default): 1 feature definition doc = 1 Confluence page.
  - `split-deliverable`: dossier §1 → transposed and split-published as a D2 policy definition
    doc / §2 → a D3 screen design spec (2 pages).
  - If unspecified, the existing value is preserved (default `dossier-page` if none exists) —
    the authoring behavior itself is identical regardless of mode (the dossier draft format is
    unchanged). The mode only affects the **publication unit**.

Receive the execution result:
- Success: confirm the message `[fanout] complete — policy WO: {N} / screen WO: {N}`
- Failure: print the error message and stop.
  - `FAIL: this project is the cluster(dossier) model...` → fail-closed guard. Per prerequisite 0,
    re-run with `--cluster-mode` or (after confirming intent) `--force-legacy`.
  - Otherwise → direct the user to re-check the graph.json structure.


### Step 4 — Print generation result summary

The artifacts read and items reported differ depending on the execution mode.

**(A) cluster-mode (Track A) — `work-orders/cluster_index.json`**

cluster-mode does not generate `index.md`. Read `work-orders/cluster_index.json`
and report the dossier generation status per capability:

```
Dossier(cluster) generation complete

  dossier(cluster): {N}
  by capability:
    {capability}: {N} ({list of cluster_id, wo_id={PREFIX}-K-{cluster_id}})
    ...
  no-delta:  {N} (no WO generated)
```

**(B) legacy node-mode (non-cluster) — `work-orders/index.md`**

Read `work-orders/index.md` and report the following items to the PM:

```
Work Order generation complete

  policy WO: {N}
  screen WO: {N}
  no-delta:  {N} (no WO generated)
  total levels:   {N}

  parallel groups by level:
  level 0 ({N}): {list of WO IDs}
  level 1 ({N}): {list of WO IDs}
  ...

  WOs needing prerequisite attention:
  {list of WOs with prerequisite edges}
```


### Step 5 — Update session-log.md

Record the Phase 1 entry. Fill in the summary column matching the execution mode:
```markdown
# cluster-mode (Track A)
| 1 (Work Orders) | {UTC timestamp} | /fanout --cluster-mode | dossier(cluster) {N} / no-delta {N} |
# legacy node-mode
| 1 (Work Orders) | {UTC timestamp} | /fanout | policy WO {N} / screen WO {N} / no-delta {N} |
```


### Step 6 — Close graph-gen items in open-issues.md

Mark as resolved any items registered during the `/graph-gen` step in `open-issues.md`
that have now been resolved because graph.json was successfully generated.


## Result file list

| File | Change |
|---|---|
| `work-orders/WO-NN.md` | All policy + screen WOs generated |
| `work-orders/index.md` | Parallel groups by level + summary card |
| `work-orders/no-delta-list.md` | Record of nodes with delta_required: false |
| `session-log.md` | Phase 1 entry record |
| `open-issues.md` | graph-gen items marked resolved |


## Failure handling principles

- validate_graph.py FAIL: stop immediately. Direct the user to re-run `/graph-gen`.
- fanout_dag.py failure: print the error code and stop. Do not delete partially generated WO files.
- no-delta-list.md write failure: print a warning and continue.


## Next steps

Once WO generation is complete, start parallel work from the level-0 WOs:
- For each WO: `/write {WO_ID}` or have the PM author the draft directly
- Once all drafts are complete: `/integrate {product}`
