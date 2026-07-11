---
name: se
description: Extracts the screen list from the FR items in requirements.md and generates a graph/screen-list.md draft.
triggers:
  - "se"
  - "screen extract"
  - "extract screens"
phase: any
effort: low
model: haiku
user-invocable: true
---

## Phase 5 change — screen track retired / absorbed into Cluster §2 (5I)

> **After Track A (Full Product) adopted the cluster architecture**, the separate screen WO
> track was retired and the §2 screen design section of the cluster draft now produces
> the screen design spec (D3). This SKILL is **valid only for Track B/C and legacy paths
> that have not adopted clusters**.

### Applicability by track

| Track | Uses this SKILL | Screen decomposition unit | D3 output path |
|---|---|---|---|
| **A — Full Product (cluster)** | ✗ Retired | Owned by cluster §2 | render `transpose()` → assemble cluster §2s (publication-map.md) |
| **B — Single Deliverable** | ✓ When authoring a single D3 | This SKILL's SCR-NNN decomposition, unchanged | Single page published directly |
| **C — Template Copy** | ✓ When authoring a single D3 | This SKILL + extracted template | Single page published directly |
| **Legacy (existing products without clusters)** | ✓ Retained | This SKILL's SCR-NNN | Existing fanout flow |

### Reason for retirement (per spec discussion outcome)

- The **multiplicative combination** of Cluster × Screen was the core cause of draft-split explosion (40-50 items reduced to 14-16)
- Policy ↔ UI decisions are cognitively coupled for the PM — handling both within the same cluster's §1+§2 is more natural
- Producing the screen design spec (D3) is adequately covered by the cluster §2 transpose, with the common shell handled as a separate appendix (publication-map.md §8)

### Screen ID assignment after cluster adoption
- Keep the SCR-NNN format as-is within cluster §2 (reusable)
- The common shell is defined in the §2 of the `G2-COMMON-{NN}` cluster (assembled as a D3 appendix)

### Cases where this SKILL is still invoked
- When entering single-D3 authoring under Track B (cluster-bypass path)
- Maintaining the graph-gen / fanout flow for existing products (not on clusters)
- Verification / auxiliary work that needs the screen-list.md SSoT


## Bootstrap cache guard (Improvement F — CONTEXT_OPTIMIZATION.md)

On first entry to a session, load `CONTEXT/_session-bootstrap.md` exactly once.
If this file has already been read in the same session, do not re-read it.
If the cache is missing or stale, refresh it with the following command before proceeding:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```

This guard replaces re-loading the 6 source files layer-config / about-pm / project-rules /
brand-voice / doc-layer-schema / team-members individually.
Reading the source files directly is allowed only when strictly required for this skill's core task.

## Precondition checks

1. Check whether `inputs/requirements.md` exists.
   If not, direct the PM to run `/draft-req {product}` and stop.

2. Check whether Layer 1 FR items exist in requirements.md.
   If not, request a quality check of requirements.md and stop.

3. If `graph/screen-list.md` already exists, choose one of two modes:
   - **Update mode**: compare the existing screen-list.md with requirements.md and reflect only missing/added screens
   - **Regenerate mode**: fully regenerate screen-list.md based on requirements.md
   Confirm the mode with the PM.


## Execution steps

### Step 1 — Decompose FR items into screen units

Read all Layer 1 FR items in requirements.md.
Decompose each FR item into screen units using the following criteria:

**Screen decomposition criteria:**
- An independent UI state the user directly enters or transitions to
- If a single FR spans multiple screens, split each screen into a separate item
- Treat simple dialogs / modals as a sub-state of the parent screen
  (instead of a separate screen_id, denote as parent screen_id + state name)

**Screen ID assignment rule:**
- Format: `SCR-NNN` (sequential from 001)
- If an existing screen-list.md exists, keep its existing ID scheme and only continue numbering for new items


### Step 2 — Map design screens (optional)

If a `design` connector (e.g. Figma — see CONNECTORS.md detection protocol) is available:
look up existing screen frames in the design project file and
map a design link to each item in screen-list.md.

Mapping criteria:
- Screen name keyword match
- Whether the design frame name includes the REQ ID

For items that can't be mapped, mark the design link cell `[unmapped]`.
If the connector is absent or the connection fails, record `[design skipped]` and continue.


### Step 3 — Write graph/screen-list.md

```markdown
# Screen List — {product}

> Extracted from: requirements.md Layer 1 FR
> Generated on: {date}
> Total screens: {N}

| Screen ID | Screen Name | Purpose | Related REQ-NNN | Design Link | Status |
|---|---|---|---|---|---|
| SCR-001 | {screen name} | {one-line purpose} | REQ-NNN | {link or unmapped} | New / Existing / Revised |

## Parent-child screen relationships

| Parent Screen | Sub-state (modal/dialog) | Related REQ |
|---|---|---|

## FR items without a screen

The following FR items are system/background behaviors that don't decompose into screen units:

| REQ-NNN | Description | Notes |
|---|---|---|
```

"Status" item classification:
- New: a screen not in product-audit's existing feature list
- Existing: a screen already present in existing-features.md
- Revised: an existing screen that needs changes due to requirement changes


### Step 4 — Validation: if screen-list.md already exists

If `graph/graph.json` exists, compare the screen nodes in screen-list.md and graph.json:

| Item | Criterion | Result |
|---|---|---|
| Screen count vs. requirements.md FR | Every FR has at least 1 screen | PASS / list of missing items |
| Screen count vs. graph.json screen nodes | screen-list.md = graph.json screens | PASS / list of mismatches |
| Orphan screens (screens with no FR) | 0 | PASS / list |

If mismatches exist, register them in open-issues.md as P1 and
confirm with the PM whether to re-run `/graph-gen {product}`.


### Step 5 — Request PM confirmation

Print a summary of screen-list.md and request confirmation from the PM:

```
Screen list extraction complete: {product}

  Total screens: {N}
    New: {N}
    Existing: {N}
    Revised: {N}
  FRs without a screen: {N}
  Unmapped design links: {N}

Confirmation requested:
  1. Let me know if any screens are missing.
  2. Let me know if the screen name or purpose needs correction.
  3. Once confirmed, run /graph-gen or /fanout.
```


### Step 6 — Record in session-log.md

```markdown
- {date} /se: extracted {N} screens (new {N} / existing {N} / revised {N}) / {N} FRs unmapped
```


## Output files

| File | Content |
|---|---|
| `graph/screen-list.md` | Screen list + REQ links + design links + status |
| `open-issues.md` | P1 registered on graph.json mismatch |
| `session-log.md` | Screen extraction record |


## Next steps

After PM confirmation of screen-list.md:
- graph.json missing: `/graph-gen {product}` (screen-list.md is used as reference input)
- graph.json exists + no mismatch: proceed directly to `/fanout {product}`
- graph.json exists + mismatch found: re-running `/graph-gen {product}` is recommended
