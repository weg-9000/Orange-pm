---
name: draft-req
description: Passes the 3 Discovery streams to the synthesizer agent to generate requirements.md and research.md, and validates the discovery-exit-gate.
triggers:
  - "draft-req"
  - "synthesize requirements"
  - "make requirements"
agent: synthesizer
phase: -1
effort: high
model: opus
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
Directly reading the source files is allowed only when strictly necessary
for this skill's core work.


## Common Reference Guard (C0·C-PIN — gates/master-derivation-gate.md SSoT)

Applies when synthesizing requirements/spec-catalog. See
`CONTEXT/gates/master-derivation-gate.md` for details.

1. Common cross-check: policy/terminology already present in G2-A/B must
   not be rewritten in requirements/spec-catalog — reference only via a
   `[{doc_id} §X] reference` link (only candidate §s from the
   B-headings-index; do not load the full source text).
2. spec-catalog source classification: every input-variable row's
   `source` must be one of `G2-B §X | Product Delta | [needs-confirmation:reason]`.
   **Filling in by guessing or hallucination is forbidden** (a variable
   whose source is not secured gets [needs-confirmation] + an open-issues
   entry).
3. PM confirmation is consolidated into step 2 (receiving the generated
   result) — do not add a separate serial prompt.

## Precondition Checks

### 1. Check that the stream files exist

Check whether the following 6 files exist:
- `inputs/discovery/competitor/overview.md`
- `inputs/discovery/competitor/*.md` (1 or more)
- `inputs/discovery/stakeholder/overview.md`
- `inputs/discovery/stakeholder/*.md` (1 or more)
- `inputs/discovery/product-audit/overview.md`
- `inputs/discovery/product-audit/*.md` (1 or more)

If any stream is missing files, instruct the PM to run the corresponding
skill (`/research`, `/stakeholder`, `/product-audit`) and stop.


### 2. Check the minimum quality threshold for each stream

Read each file and check whether it meets the following criteria:

| Stream | Minimum requirement |
|---|---|
| competitor | 3+ rows in the comparison matrix / fewer than 50% `[not entered]` cells |
| stakeholder | 2+ stakeholders registered / 5+ requirement items |
| product-audit | 1+ existing feature listed / 1+ pain point |

If any stream falls short, print the specific shortfall and ask the PM
whether to proceed anyway.
If the PM chooses to force proceed, attach a `[quality below threshold —
forced]` warning to that stream and continue.


### 3. Check P0 items in open-issues.md

If there is 1 or more P0 item, print the list and stop.


### 4. Check whether the {PREFIX}-B common policy is accessible

Read the `{PREFIX}-B` document link (wiki) from `CONTEXT/layer-config.md`.
If the link is missing, or the wiki connector (an MCP tool the user has
connected — e.g. Confluence, Notion, checked via the CONNECTORS.md
detection protocol) is absent or fails to connect, register a P2 item in
open-issues.md and proceed with synthesis without {PREFIX}-B.
(In this case, items in requirements.md that duplicate {PREFIX}-B are
written out in full, without link handling.)


## Execution Steps

### Step 1 — Launch the synthesizer agent

Launch the synthesizer agent, passing it the following context:

```
Input files:
  - inputs/discovery/competitor/ (all)
  - inputs/discovery/stakeholder/ (all)
  - inputs/discovery/product-audit/ (all)

Settings:
  - PREFIX: {PREFIX} (loaded from layer-config.md)
  - {PREFIX}-B document link (wiki): {URL or N/A}

Output targets:
  - PROJECTS/{product}/inputs/requirements.md
  - PROJECTS/{product}/inputs/requirements.seeds.yml  (capability seed sidecar)
  - PROJECTS/{product}/inputs/research.md
  - PROJECTS/{product}/inputs/spec-catalog.md  (per templates/standard/spec-catalog-template.md)

Synthesis priority: stakeholder requirements first
Conflicting requirements handling: do not delete, record in open-issues.md
{PREFIX}-B duplicate items: mark as a Link only in requirements.md/spec-catalog (do not rewrite)
spec-catalog source rule: every input-variable row's `source` must be one
  of G2-B §X | Product Delta | [needs-confirmation:reason]. A variable
  whose source is not secured gets [needs-confirmation] + an open-issues
  entry.
  **Filling in by guessing or hallucination is strictly forbidden** (if a
  value is unknown, use [needs-confirmation], not a blank cell).
mode: state `calculation` in frontmatter for fee-formula type, `console`
  for console type.
FR capability seed (P1 — docs/fr-cluster-alignment.md DEC-A/B): create/update
  a sidecar `requirements.seeds.yml` in the same directory as
  requirements.md. Do not put inline cells in the FR table body (keep D1's
  FR table a clean 4 columns). The sidecar is a top-level map keyed by FR
  ID, giving each FR one `capability` hypothesis:
  ```yaml
  "FR-101":
    capability: "Provisioning"
    cluster_hint: "PR-01"   # optional
    lock: false             # optional, default false
  "FR-102":
    capability: "[needs-confirmation]"
  ```
  - `cluster_hint`/`lock` are optional. **The seed is a hypothesis, not a
    fixed boundary (DEC-B)** — the final boundary is settled by
    cluster_identify (5-axis, threshold), so do not hard-group FRs into
    capability prose sections. If capability is unclear, do not guess →
    write `capability: "[needs-confirmation]"` and register a P1 open
    issue.
  - For an untagged product, the sidecar can be bootstrapped after the
    fact with `cluster_seed_backfill` (P5).
```

The synthesizer performs its own internal discovery-exit-gate
self-validation.
(See `agents/synthesizer.md` for detailed synthesis procedures)


### Step 2 — Receive and record the generated result

After the synthesizer completes, check the following items:

- Whether `inputs/requirements.md` was created
- Whether `inputs/requirements.seeds.yml` was created (sidecar — capability
  seeds)
- Whether `inputs/research.md` was created
- Whether `inputs/spec-catalog.md` was created + 0 rows with an untagged
  (blank) source / count of [needs-confirmation] rows
- Layer 1–5 item counts (received from the synthesizer's self-validation
  result)
- **FR capability seed status** (P1): whether each FR ID key exists in the
  sidecar `requirements.seeds.yml` / count of FRs with no capability
  assigned (no key) / count of FRs with `[needs-confirmation]` capability.
  If keyless FRs remain, explain that the synthesizer can be re-run to
  fill them in, or the sidecar can be filled afterward via the
  `cluster_seed_backfill` bootstrap (P5). Confirm that
  `[needs-confirmation]` items are registered in open-issues.
- Number of newly registered open-issues.md items

#### Phase 5B — requirements.md FR metadata expansion (Track A cluster grouping input)

To be used by Track A (Full Product)'s cluster_identify.py and fanout's
cluster mode, add the following metadata fields to FR records
(backward-compatible — works fine without them).

```yaml
- id: FR-103
  layer: 1
  title: "DBaaS Instance Creation Policy"
  priority: P0
  # ── New fields in Phase 5B ──
  domain_object: ["Instance", "InstanceSpec"]   # object-sharing axis
  policy_axis: ["Instance Lifecycle", "Resource Limits"]  # policy-domain axis
  primary_screen: "SCR-001"                      # screen-surface axis
  cluster_ref: null                              # to be filled in (after cluster_identify)
  capability_hint: "Provisioning"                # capability candidate (optional)
```

Usage:
- **cluster_identify.py** — input for scoring the 4 axes (publication-map.md §1)
- **fanout --cluster-mode** — generates per-cluster WOs (applies the
  cluster-draft.md template)
- **cluster draft frontmatter** — the SSoT source for `fr_refs` /
  `domain_objects` / `policy_axes` / `primary_screen`

Behavior when unspecified:
- `cluster_identify.py` proceeds with default values + heuristics
- If `domain_object`/`policy_axis` are missing, the combination score is
  low → each node becomes its own independent cluster
- If `capability_hint` is missing, the default `"Default"` capability is
  used

Recommended PM authoring order:
1. When starting Track A, first write the FR list (basic fields)
2. Run `/cluster-identify {product}` → review the generated cluster summary
3. If the result is unsatisfactory, fill in the 5-axis fields above → re-run
   (keeps the same cluster_id — stable mapping)
4. Once finalized, proceed with `/fanout --cluster-mode`

Record the result in session-log.md:
```markdown
| 0 (Requirements) | {UTC timestamp} | /draft-req | FR: {N} / NFR: {N} / new open-issues: {N} |
```


### Step 3 — Close out Discovery items in open-issues.md

Mark the following items complete in `open-issues.md`:
- `[DISC-01]` Competitor analysis incomplete
- `[DISC-02]` Stakeholder requirements gathering incomplete
- `[DISC-03]` Own-product status assessment incomplete

Completion format: `- [x] [DISC-0N] ~~original content~~ → completed via /draft-req`


### Step 4 — Validate the discovery-exit-gate

Run `/lc {product}`.

exit-gate validation criteria:

| Item | Criterion | Action if not met |
|---|---|---|
| Layer 1 FR | 10 or more | re-run the synthesizer |
| Layer 2 NFR | 5 or more | re-explore product-audit, then supplement |
| Layer 4 actor definitions | complete | re-reference stakeholder |
| Layer 5 external integrations | list exists | mark TBD + register P1 |
| FR split by screen unit | fully checked | rewrite the item split correctly |
| spec-catalog source classification | every variable row's source tagged (0 blanks) | fill blank rows with [needs-confirmation] |
| open-issues P0 | 0 | report to PM and stop |

If the exit-gate passes, update the Phase to 0 and explain the next
step.
If the exit-gate does not pass, print the list of unmet items and ask
whether to re-run the synthesizer.


## Output Files

| File | Change |
|---|---|
| `inputs/requirements.md` | Layer 1–5 structure, REQ-NNN IDs, priority included (FR table stays a clean 4 columns) |
| `inputs/requirements.seeds.yml` | capability seed sidecar (FR ID → capability hypothesis, optional cluster_hint/lock) |
| `inputs/spec-catalog.md` | Input-variable SSoT (7 columns + source, calc/console mode). No guessing · [needs-confirmation] tracked |
| `inputs/research.md` | Competitor analysis summary + FR mapping + competitive rationale |
| `open-issues.md` | DISC-01~03 marked complete / new conflict/TBD items added |
| `session-log.md` | Records Phase 0 entry |


## Upstream Feedback Loop (Phase 4 R5 — cluster work → discovery revision)

> During cluster authoring in Phase 2–3 of Track A (Full Product), an
> item that `/integrate` classifies as an `UPSTREAM_GAP` BLOCK is a signal
> that the Phase -1 outputs (requirements.md / research.md / decisions.md)
> need revision.

### Trigger Conditions
Enter `--upstream-feedback` mode via any of the following:
- An `UPSTREAM_GAP` BLOCK is found when running `/integrate {product}` →
  re-invoking this skill is recommended
- Explicit PM invocation: `/draft-req {product} --upstream-feedback`
- There are items recorded in a cluster draft's §4 `Open Questions /
  Upstream Feedback` section

### Processing Procedure
1. **Collect**: gather feedback items from the following locations
   - `reports/integrate/{product}.upstream-gap.md` (produced by integrate)
   - each cluster_draft's §4 section (including manual PM entries)

2. **Classify**:
   - **REQ_MISSING** — a missing FR (needs to be added to requirements.md)
   - **POLICY_CONFLICT** — a policy conflict (candidate for a new DEC in decisions.md)
   - **RESEARCH_GAP** — insufficient competitor research (research.md needs
     supplementing; consider re-running research-auto)
   - **TERM_AMBIGUOUS** — ambiguous terminology (add to terms.yml / spec-catalog.md)

3. **PM Approval Gate**:
   - Automatic revision is forbidden — every feedback item requires
     individual PM approval
   - Confirm explicitly, e.g. "Add the following item to the D1
     Requirements Definition? [y/n]"
   - Only approved items are reflected in the v{n+1} revision

4. **Version Increment**:
   - requirements.md `version: X.Y` → `X.(Y+1)` (minor bump)
   - Same policy for research.md / decisions.md
   - Record the feedback source (cluster_id + UPSTREAM_GAP item ID) in the
     change history table

5. **Notify Affected Clusters to Revisit**:
   - After the revision, recommend running `/lc {cluster_id}` (re-running
     lifecycle validation) on the affected clusters
     (`feedback.affected_clusters`)

### Outputs
- `inputs/requirements.md` (v++) — when REQs are added/modified
- `inputs/research.md` (v++) — for RESEARCH_GAP feedback
- `decisions.md` (new DEC row) — for POLICY_CONFLICT feedback
- `reports/upstream-feedback/{date}.applied.md` — archive of the feedback processing result

### Differences from Track B/C
- Track B/C follows a single-deliverable linear path — `UPSTREAM_GAP` is
  unlikely to occur (no clusters)
- If it does occur, fix it directly within the single-deliverable template
  (no separate feedback procedure needed)


## Next Steps

Once the discovery-exit-gate passes:
- `/graph-gen {product}`: generate graph.json and design nodes/edges
