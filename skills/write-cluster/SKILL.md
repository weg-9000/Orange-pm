---
name: write-cluster
description: >-
  Writes the 4 panels (§1 Policy Decisions / §2 Screen Design / §3 Data & Dependencies / §4 Open Questions) of a cluster draft (Track A · type cluster_draft) under the lossless principle. The panel skeleton is fixed (transpose routing contract: §1→D2 policy document · §2→D3 screen design spec); the content inside each panel is fully variable to match the source facts. Complies with publication-syntax (`::: {.panel}` · automatic color cycling) and passes lint / round-trip validation. Node policy WOs use /write, node screen WOs use /flow.
triggers:
  - "write cluster"
  - "cluster draft"
  - "write-cluster"
phase: 2
effort: high
model: opus
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


## Scope — Track A cluster work unit

This skill writes a single `drafts/cluster_{cluster_id}.draft.md` file (with
`type: cluster_draft`) in place. Cluster mode retires the screen WO track
(Phase 5I) and §2 takes over responsibility for screen design, so **a single
cluster draft holds both policy (§1) and screen (§2)** together.

- Format SSoT: `orange-pm-plugin/templates/standard/cluster-draft.md`,
  `orange-pm-plugin/skills/render/publication-syntax.md`,
  `orange-pm-plugin/skills/render/publication-map.md` (transpose mapping).
- Node policy WOs (`type: policy`) use `/write`; node screen WOs (`type: screen`) use `/flow`.


## Design Principle — Fixed Skeleton + Variable Content (most important)

| Layer | Fixed/Variable | Rule |
|---|---|---|
| Format (syntax) | **Fixed** | `::: {.panel section="..."}` fenced div. No hand-written color spans (automatic cycling). Enforced by lint |
| Skeleton (core 4 panels) | **Fixed** | §1 Policy Decisions / §2 Screen Design / §3 Data & Dependencies / §4 OQ. Must never be changed — this is the transpose routing contract (§1→D2 · §2→D3 · §3/§4 excluded from publish) |
| §α technical panel | **Optional** | §α-API/§α-DB/§α-MIG → Dα. Add only when that technical deliverable exists; delete otherwise (the only panel where adding/deleting is allowed) |
| TOC (deliverable TOC) | Derived | D2/D3 chapters are auto-assembled by publication-map from the cluster composition (ordered by capability alphabet → cluster_id). This skill does not touch it |
| Content (inside panels) | **Variable** | Follows the doc-layer-schema lossless-reconstruction principle. Subsections (§1-1, etc.) are just a recommended default — expand or contract them to match the volume of source policy/screen facts. Do not force-fill empty tables or omit facts |

> **Lossless principle (top priority)**: Do not discard a single policy fact,
> figure, case, exception, UI copy line, or table from the source/input. Any
> fact that fits nowhere else is preserved verbatim under `### Unclassified
> Source Facts` at the end of §3. No invention — use `[needs-confirmation:
> {what}]`. Source contradictions → preserve both sides as `[policy conflict
> — {item}]`.


## Common Reference Guard (C0 · C-PIN · C-PIMPACT — gates/master-derivation-gate.md SSoT)

Apply before writing.

1. **Do not rewrite B**: For policies already present in G2-A/B, identify only
   candidate §s via `B-headings-index.json` (do not load the full source). If
   already present, reference it only via a `[{doc_id} §X] reference` link.
   render_assemble (C-RENDER) inlines the full body from the complete version
   at publish time.
2. **Follow A terminology**: Use `CONTEXT/reference-docs/{ACTIVE_PREFIX}/A/`
   G2-A-001 glossary as the standard. Tag unregistered terms as
   `[TBD:{term}]` (log to open-issues.md P1 after writing).
3. **Do not re-state numbers/formulas**: For unit prices, rates, and
   thresholds, reference the variable ID in `inputs/spec-catalog.md`
   (`[[spec-catalog {variable_id}]]`). Formulas are derived from G2-B Product
   Pricing & Billing Policy §— structure only, alongside a § link.
4. **C-PIN**: Pin the common reference in frontmatter `inherits_from` / (if
   present) `referenced_master`, based on the delta. Use the authoritative ID
   from master-id-map.yml.
5. **C-PIMPACT**: When §2 screen content references a §1 policy §, use only
   the standard `[[POL §X-Y]]` marker.


## Input/Output

- **Input**: `PROJECTS/{product}/drafts/cluster_{cluster_id}.draft.md`
  (the shell created by fanout --cluster-mode — frontmatter `status: empty`,
  `type: cluster_draft`, body contains the `::: {.panel}` 4-panel scaffolding
  + `{{...}}` placeholders)
- **Output**: the same file modified in place (`status: empty → ai-draft`,
  placeholders replaced with actual content, panel skeleton and `section=`
  attributes preserved)


## Precondition Checks

1. Confirm `drafts/cluster_{cluster_id}.draft.md` exists. If not, direct the
   user to `/fanout {product} --cluster-mode` (+ prerequisite
   `cluster_identify.py`) and stop.

2. Check frontmatter `type`:
   - `type: cluster_draft` → proceed.
   - `type: policy` → direct to `/write {WO_ID}` and stop.
   - `type: screen` → direct to `/flow {product} {screen_id}` and stop.

3. **Status branching (Option A lifecycle — same rule as /write):**
   - `empty` → proceed normally. Switch to `ai-draft` after writing.
   - `ai-draft` → warn about overwrite, then (Y/N).
     ```
     ⚠️ This cluster draft is already ai-draft. Rewriting will overwrite the body. (Y/N)
     ```
   - `human-reviewed` → reject unless `--force` is given.
   - `frozen` → reject (requires a new DEC + new version).
   - status missing → direct the user to re-run `/fanout --cluster-mode`
     (the shell includes status: empty) to refresh.

4. Confirm `decisions.md` exists (for cross-checking DEC conflicts). If
   missing, request its creation and stop.

5. Load `CONTEXT/layer-config.md` PREFIX +
   `CONTEXT/reference-docs/{ACTIVE_PREFIX}/A|B/` (prefer cache/excerpts —
   apply the same B-summary/B-headings-index rule as /write Step 1).


## Step 1 — Gather Cluster Context

Read the graph-gen-produced metadata in frontmatter (do not edit manually):
- `cluster.capability` / `cluster_id` / `cluster_name`, `members` (member policy nodes)
- `fr_refs` (D1 requirements citations — link only), `domain_objects`, `policy_axes`
- `primary_screen` / `related_screens` (basis for §2 screen design)
- `inherits_from` (parent B common / parent cluster), `research_refs` (D5 — link only)
- `deliverable_targets` (usually D2/D3; §α if Dα exists)

Gather the source material for each member policy node (requirements.md FRs,
decisions.md decisions, meeting delegations) as input for lossless writing.


## Step 2 — PM Confirmation of Delta/Content Scope (single checkpoint)

Print the following table and get PM confirmation (do not add serial
prompts — do it in one shot):

```
Cluster writing scope — {capability}/{cluster_id} {cluster_name}

┌─ §1 Policy Decisions (→D2) — B inheritance (no rewrite, link only) / this cluster's Delta policy ─┐
│  Inherited: {inherits_from § summary}  →  [{doc_id} §X reference]                                  │
│  Delta: {cluster-specific policy candidates from requirements/decisions, incl. [TBD]}              │
├─ §2 Screen Design (→D3) — 4-state & microcopy for primary/related_screens ──────────────────────────┤
│  Screens: {primary_screen, related_screens}                                                        │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Do not proceed to Step 3 without PM confirmation.


## Step 3 — Write the 4 Panels (fixed skeleton · lossless content)

**Preserve** the `::: {.panel section="..."}` fenced div, the `## §N`
headings, and the `section=` attribute, and replace the `{{...}}`
placeholders and example tables inside each panel with actual content.
Subsections expand or contract to match the volume of source material (not
a fixed count). Do not add, delete, or reorder panels.

### §1 Policy Decisions (→ D2 Policy Document)
- Use `### §1-1 Policy Scope/Applicability`, `### §1-2 Core Rules` (POL-N
  table), `### §1-3 State/Lifecycle`, `### §1-4 Errors/Exceptions` as the
  default skeleton, expanding subsections to match the number of source
  policies.
- Represent state × action as a matrix in §1-3 (cover every state — critique
  AXIS-09). This matrix is later deterministically converted by `/bdd` into
  acceptance criteria (.feature), so do not leave cells blank.
- For B common content use `[{doc_id} §X reference]`; for figures use
  `[[spec-catalog {variable_id}]]`. Follow A terminology.
- Cover every case branch: success/failure/cancellation/timeout/zero-count/
  duplicate/concurrent (AXIS-03).

### §2 Screen Design (→ D3 Screen Design Spec)
- `### §2-1 Key Screens/IDs`, `### §2-2 Screen Layout/Components`,
  `### §2-3 Interactions/Policy Links`, `### §2-4 Empty/Error States`,
  `### §2-5 Design Tokens (common shell reference)`.
- For each screen, cover the 4 states (idle/loading/success/error) with
  actual microcopy text (no placeholder tokens).
- Link how §1 policy is exposed on screen using the `[[POL §X-Y]]` marker
  (§2-3).
- Do not redefine design tokens — reference only the common shell cluster
  (G2-COMMON-*) (SSoT boundary).

### §α Technical Deliverables (optional — only for clusters with API/DB/migration → Dα)
- Write this only when the cluster has an exposed API / new schema / data
  migration. Otherwise, **delete the §α panel entirely** (no leftover empty
  placeholders — lint L5).
- `::: {.panel section="§α-API ..."}` / `§α-DB` / `§α-MIG` — the section
  label must start with `§α` and include a type keyword (API/DB/migration)
  so render_transpose can extract it into the corresponding Dα page (use the
  template label as-is).
- When written, add the corresponding `Da_api`/`Da_db`/`Da_migration` to
  frontmatter `deliverable_targets` (otherwise it is excluded from
  publishing).
- §α is the **published source of truth**; the §3 data model is an
  **internal sketch** — keep the authoritative schema only in §α-DB, with §3
  referencing it (no SSoT duplication).

### §3 Data/Dependencies (internal use · excluded from publish)
- Data model (mermaid classDiagram), external dependencies (other
  clusters/APIs/infrastructure), performance considerations.
- Lossless remainder: preserve verbatim, under `### Unclassified Source
  Facts`, any source fact that fits nowhere else.

### §4 Open Questions / Upstream Feedback (internal use · excluded from publish)
- `### §4-1 Open Questions` (OQ-N table, resolvable independently).
- `### §4-2 Upstream Feedback` — classify into the BLOCK categories that
  `/integrate` auto-recognizes: `#### REQ_MISSING` (add to D1) /
  `#### POLICY_CONFLICT` (new DEC) / `#### RESEARCH_GAP` (augment D5) /
  `#### TERM_AMBIGUOUS` (terms/spec-catalog).
- `### §4-3 Decision Trail` — PM decisions made while writing the cluster.
  Decisions that need a DEC entry are logged as `⬜` candidate rows in the
  decisions.md DEC table (schema [[CONTEXT/dec-schema]]; approval via
  /dec-approve).

**Color/placeholder rules**: Do not hand-write color spans (`[..]{.color-*}`)
— apply_color_cycling.py generates them automatically at publish time.
Replace every `{{...}}` placeholder (unreplaced ones trigger lint L5 WARN).


## Step 4 — Validation (lint → storage conversion → split check)

Run these in order immediately after writing.

1. **Publication syntax lint** (FAIL = blocking):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lint_publication_syntax.py --input drafts/cluster_{cluster_id}.draft.md
   ```
   - L1 panel class allowlist / L2 panel `section=` required / L3 allowed
     styles / L6 no nested color spans / L7 table column consistency =
     **fix and re-run if FAIL**. L4/L5 are WARN.

2. **Storage conversion + lint gate** (FAIL = blocking):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/md_to_storage.py --input drafts/cluster_{cluster_id}.draft.md --output /tmp/cluster_{cluster_id}.xml --validate
   ```
   - Converts MD → storage XML, and `--validate` re-runs publication-lint on
     the input MD (same rules as step 1). exit 1 = conversion failure /
     exit 2 = lint FAIL.
   - On failure, fix the location and re-run.

3. **Split threshold check** (advisory — non-blocking):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lazy_split_check.py --drafts drafts/cluster_{cluster_id}.draft.md
   ```
   If the body exceeds 1500 lines / §1+§2 items exceed 8 / accumulated R2
   BLOCKs exceed 5, a child-cluster split is recommended
   (`G2-K-{id}-a/-b`). Proceed only after PM approval.

> The round-trip golden test (`round_trip_test.py`) is a converter
> regression test (CI) — run it when the converter changes, not as part of
> writing an individual draft.


## Step 5 — Self-Verification Checklist

- [ ] Lossless: every source policy/screen fact is mapped (0 omissions, unclassified facts preserved in §3, contradictions kept as [policy conflict] on both sides)
- [ ] Core 4-panel (§1–§4) skeleton and `section=` attributes preserved, no reordering (only §α may be optionally added/deleted)
- [ ] If §α is written, `Da_*` is registered in frontmatter `deliverable_targets` / if not written, the §α panel is deleted
- [ ] §1-3 state × action matrix covers every state (no empty cells — for /bdd conversion)
- [ ] §2 4-state and microcopy use actual text (0 placeholder tokens)
- [ ] 0 B rewrites — only `[{doc_id} §X reference]` links / figures use [[spec-catalog]] variable IDs
- [ ] A terminology followed (deviations tagged [TBD:] + logged to open-issues P1)
- [ ] Only the standard `[[POL §X-Y]]` marker used (§2-3 policy linkage)
- [ ] Every `{{...}}` placeholder replaced (lint L5 WARN = 0)
- [ ] 0 lint FAILs · md_to_storage --validate passes
- [ ] §4 Upstream Feedback classified by category / decisions logged as DEC candidates
- [ ] No violations of decisions.md source of truth (`approved=✅`)


## Step 6 — Frontmatter Status Transition (Option A)

After passing self-verification, update in place:
- `status: empty` → `status: ai-draft` (rewrite cases keep ai-draft)
- Update `last_updated: {YYYY-MM-DD}`
- Do not modify cluster metadata (capability/cluster_id/members, etc.) or
  `color_state: null`.


## Step 7 — Completion Report and session-log

```
/write-cluster complete — {capability}/{cluster_id}

  draft: drafts/cluster_{cluster_id}.draft.md  (status: ai-draft)
  §1 policy rules: {N} / §2 screens: {N}
  lint: FAIL 0 / storage --validate: OK / split: {recommended or not}
  TBD: {N} (open-issues P1) · policy conflicts: {N} (P0) · DEC candidates: {N}
  Upstream Feedback: REQ_MISSING {N} · POLICY_CONFLICT {N} · RESEARCH_GAP {N} · TERM_AMBIGUOUS {N}

Next steps: /integrate {product} (R1–R3) → /bdd {product} (acceptance criteria) → /render --push (transpose)
```

Append to session-log.md:
```markdown
- {date} /write-cluster {cluster_id}: §1 {N} rules / §2 {N} screens / lint OK / TBD {N} / conflicts {N}
```


## Output File List

| File | Content |
|---|---|
| `drafts/cluster_{cluster_id}.draft.md` | Written 4-panel draft (status: empty → ai-draft, skeleton preserved · content lossless) |
| `decisions.md` | DEC `⬜` candidate rows from the §4-3 decision trail |
| `open-issues.md` | TBD (P1) / policy conflicts (P0) / semantic-B signals (RE handoff tracking) |
| `session-log.md` | Writing summary |


## Next Steps

```
/integrate {product}        # Resolve R1–R3 BLOCKs + classify UPSTREAM_GAP
/bdd {product}              # §1-3 matrix / §2 4-state → acceptance criteria (.feature)
/render --push {product}    # §1→D2 · §2→D3 transpose, then publish to Confluence
```
