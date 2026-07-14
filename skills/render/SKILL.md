---
name: render
description: |
  Merges {PREFIX}-B common policy and {PREFIX}-C product delta to assemble a complete
  product policy document and outputs it in the user's desired format. Callable at any time
  during authoring; it only assembles and converts format, never modifying content.

  Key flags:
    --push            Upload to Confluence (publication conversion applied automatically)
    --only            Selective publish — push only the specified dossiers (WO_ID) (e.g.
                       --only G2-C-BDB-00,G2-C-BDB-03). Publishes all dossiers if unspecified.
                       Backend for the viz sync view's checkbox-based push.
    --style-example   Path to an example document for LLM tone/format normalization (used with --push)
    --stakeholder     Clean view for stakeholder sharing (publication-conversion shortcut mode)
    --check-sync      Check the Draft ↔ Confluence bidirectional sync gap
    --apply-inbox     Apply the reports/inbox/ patch generated from Confluence drift
    --check-ssot      Check for SSoT boundary (CONTEXT/ssot-boundary.yml) violations
    --parallel        Render independent WOs in parallel (concurrent multi-file processing)
    --verify          Automatically verify XML structure quality after --push
    --color-cycle     Apply change-tracking color cycling right before publish (optional, off by default)

  Automatic triggers (fired without an explicit PM invocation):
    - PostToolUse hook : only render_assemble (stage 1) runs silently when
                         drafts/*.draft.md are edited → refreshes reports/render/{WO_ID}.complete.md
    - /lc, /integrate  : stale complete.md check (required gate)
    - /confirm         : publication conversion + automatic Confluence push (frozen canonicalization)

  The LLM stage and push always run only on an explicit PM trigger (/render --push or /confirm).
triggers:
  - "render"
  - "full policy document"
  - "complete version"
  - "export policy"
  - "output policy document"
  - "format conversion"
  - "check sync status"
  - "sync check"
  - "check Confluence differences"
  - "bring in remote changes"
  - "fetch Confluence changes"
  - "apply merge proposal"
  - "verify upload"
  - "XML standard validation"
phase: any
effort: medium
user-invocable: true
---

## Natural-language intent → flag decision mapping (performed as priority 0 right after entering the skill)

On entering render, if the PM hasn't explicitly written a flag (e.g. `--push`) directly,
select the flag **deterministically** using the table below. Keywords are matched by partial
match·synonym inclusion.
Do not leave the decision to guesswork — treat this table as the SSoT.

| PM utterance intent (keywords) | Flag selected |
|---|---|
| "upload it", "push", "upload to Confluence", "make it canonical and upload", "reflect the finalized version" | `--push` |
| "for sharing", "clean version", "share with stakeholders/designers", "clean up for review" | `--stakeholder` |
| "sync status", "check sync", "diff between local and Confluence", "check if anything's out of sync", "gap check" | `--check-sync` |
| "bring in remote changes", "pull in what changed in Confluence", "reflect drift", "apply inbox/merge proposal" | `--apply-inbox` |
| "verify the uploaded version", "check XML standard compliance", "check internal format", "confirm quality after push" | `--verify` |
| "check SSoT violations", "boundary check" | `--check-ssot` |
| "in parallel", "faster, at the same time", "multiple WOs at once" | `--parallel` |
| (matches none of the above — "full version/format conversion/preview") | (no flag = local assembly only) |

**Decision rules:**
1. If multiple intents are mixed in one utterance, combine **all** matching flags.
   Example: "verify it and upload" → `--push --verify`.
2. `--verify` presupposes `--push`. If "verify" is spoken alone, correct it to
   `--push --verify`.
3. `--apply-inbox` is a **hard-to-reverse** action that feeds remote changes back into local,
   so even after selection it must always pass through the fact_preservation_check gate
   (step 3) and is never applied fully automatically.
4. For flags with external/irreversible effects like `--push` / `--apply-inbox`, confirm the
   target·scope with the PM in one line before execution. Read-only flags
   (`--check-sync`·`--verify`·`--check-ssot`) may proceed without confirmation.
5. If the intent is ambiguous between two or more options, don't guess — ask the PM which flag
   is meant.


## Track A/B/C branch handling (Phase 4 R6)

> render's behavior depends on the Track decided by intent-router.

### Track A — Full Product (dossier-based, v2.0 — fix-plan-dossier-publish)
- **Input**: dossier drafts. **The on-disk shape is `drafts/cluster_{cluster_id}.draft.md`,
  `type: cluster_draft`, `wo_id: {PREFIX}-K-{cluster_id}`** (fanout cluster-mode output,
  fanout_dag.py). "Dossier" is a conceptual name; the actual file/type/WO_ID are
  cluster_draft/G2-K-*. **Do not re-derive the filename** — use `clusters[].draft_path` /
  `wo_id` in `work-orders/cluster_index.json` as the SSoT for the list (2026-06-08 H6
  audit finding).
- **Processing (publish-mode branch — the `publication_mode` in `graph/project-mode.json`)**:
  1. Iterate over each dossier `draft_path` in `cluster_index.json`
  2. Convert each dossier → clean copy `reports/render/{WO_ID}.complete.md` (render_assemble,
     already generated)
  3. `dossier-page` (default): no transpose — publication-convert (prefilter→md_to_storage)
     each dossier as **one feature spec page** each, then push
  4. `split-deliverable`: transpose reactivated — synthesize all dossiers' §1→D2 policy
     document / §2→D3 screen design spec (render_transpose) and push **exactly 2 pages**
     (step 3-A-split)
- **D1·D5**: Phase -1 output, so published as-is (no change)
- **D4 meeting minutes**: chronological assembly of `meetings/*.md` + `mtg-ledger.md`, indexed
  by cluster tag
- **Invocation**: `/render {product} --push` (all dossiers) or `--only {WO_ID,...}` (selective
  publish)
- **Color cycling**: per dossier **page** (based on stable WO_ID)

### Track B — Single Deliverable
- **Input**: a single deliverable draft (e.g. `drafts/D2.draft.md`)
- **Processing**:
  1. Bypass cluster fanout (no transpose)
  2. Apply publication-syntax + direct md_to_storage conversion
  3. Push only that one page (URL_target)
- **Invocation**: `/render {product} --push --deliverable D2` or automatic single-page mode
- **Color cycling**: same (per page)

### Track C — Template Copy
- **Input**: a single deliverable draft + extracted template
  (`templates/extracted/{page_id}.template.md`)
- **Processing**:
  1. Fill the extract-template output skeleton as the base
  2. Bypass cluster fanout / transpose
  3. Push to the target URL page
- **Invocation**: `/render {product} --push --deliverable D2 --template-from pages/A`

### Track auto-detection
Without explicit flags (`--deliverable`, `--template-from`), on entering this skill:
- `cluster_drafts/*.md` exists + multiple → Track A
- only a single `drafts/D{N}.draft.md` → Track B
- accompanied by `templates/extracted/*.template.md` → Track C

If ambiguous, confirm with the PM in one line.


## Bootstrap Cache Guard (Improvement F — CONTEXT_OPTIMIZATION.md)

Load `CONTEXT/_session-bootstrap.md` once at the start of the session.
If a file has already been read in the same session, do not re-read it.
If the cache is missing or stale, refresh it with the following command before proceeding:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```

This guard replaces re-loading the 6 source files layer-config / about-pm / project-rules /
brand-voice / doc-layer-schema / team-members.
Reading the source files directly is only permitted when essential to this skill's core work.


## Precondition check

1. Verify `PROJECTS/{product}/` exists.
   If not, guide running `/ingest {product}` and stop.

2. Verify a {PREFIX}-B cache file exists under `CONTEXT/.template-cache/`.
   If not, guide running `/graph-gen {product}` and stop.
   (If the cache is absent, attempt a live Confluence load; stop if that also fails.)

### Confirm initial Confluence page creation (on --push)

If the `--push` flag is included, check meta.json for each document type.

```
PROJECTS/{product}/confluence-source/
  01-requirements-{product}.meta.json  ← check the "id" value
  02-policy-{product}.meta.json
  03-screen-design-{product}.meta.json
```

**If meta.json is missing or its `"id"` is still the `"{{CONFLUENCE_PAGE_ID}}"` placeholder:**
→ the Confluence page hasn't been created yet.
→ the page must first be created using the base template under `templates/standard/`.
   (The old `templates/confluence-xml/` was migrated to `templates/standard/` and retired
   in Phase 1F.)

Guide the PM through the following procedure and get confirmation before executing:

```bash
# 1) Copy the base template (including placeholder substitution)
#    01=requirements definition / 02=policy definition / 03=screen design spec
cp templates/standard/01-requirements.md \
   PROJECTS/{product}/confluence-source/01-requirements-{product}.md

# Placeholder substitution (via a python script or manually)
# {{PRODUCT_NAME}}, {{DOC_ID}}, {{VERSION}}, {{DATE}}, etc.
# md → Storage Format conversion is handled by md_to_storage.py

# 2) Create a new empty page in Confluence, then obtain the page_id
# 3) meta.json is initialized inline by /cr when the page is created.
#    Do not copy a separate template file.

# 4) Local conversion of the base template — before publishing to a Confluence-family
#    wiki, first convert md → Storage Format XML (md_to_storage.py runs locally)
python ${CLAUDE_PLUGIN_ROOT}/scripts/md_to_storage.py \
  PROJECTS/{product}/confluence-source/01-requirements-{product}.md \
  --output /tmp/01-requirements-{product}.xml
```

The conversion result is pushed by calling the page-update operation of the wiki connector
(a user-connected MCP tool — e.g. Confluence — confirmed via the docs/CONNECTORS.md detection
protocol) per its schema.
Domain info to pass: page_id `{CONFLUENCE_PAGE_ID}`, title `[Requirements Definition]
{PRODUCT_NAME}`, body = the converted Storage Format XML.

**Base template location:** `templates/standard/`
- `01-requirements.md` — requirements definition initial skeleton
- `02-policy.md` — policy definition initial skeleton
- `03-screen-design.md` — screen design spec initial skeleton
- meta.json is created inline by `/cr` when the page is created (no separate template file).

Once initial creation is complete and meta.json is filled with an actual `"id"`, subsequent
`--push` runs act as an update to the existing page.

3. **Legacy/node mode only** — when `work-orders/cluster_index.json` doesn't exist
   (node mode), check whether `work-orders/{WO_ID}.md` exists for the `{WO_ID}` argument; if
   not, output the list of valid WOs and stop. Track A (cluster mode,
   `cluster_index.json` present) doesn't create per-WO `.md` files, so this existence check
   doesn't apply (dossier WO_IDs are validated via `clusters[].wo_id` in `cluster_index.json`).

4. If a `--template` path is specified, verify that file exists.
   If not, guide re-checking the path and stop.


## Execution steps

### Step 1 — Determine render scope

> Improvement G (CONTEXT_OPTIMIZATION.md) — Track A uses
> `work-orders/cluster_index.json`, legacy/node mode uses `work-orders/index.json` as the
> listing SSoT.

```
WO_ID specified     → render only that one WO (dossier)
WO_ID unspecified   → Track A: render all of clusters[] in cluster_index.json
                       legacy/node: render all of wo[] in work-orders/index.json
                       (fall back to parsing the index.md table only if index.json is missing)
```

WO metadata loading rules:

1. **Track A (cluster mode)** — if `work-orders/cluster_index.json` exists, use the
   `clusters[]` array as the listing SSoT. Each item includes metadata needed for dossier
   publishing such as `wo_id` (`{PREFIX}-K-*`), `cluster_id`, `draft_path`.
   (Legacy `index.json`/`index.md` aren't generated in cluster mode, so don't reference them.)
2. **legacy/node mode** — if `cluster_index.json` is absent and `work-orders/index.json`
   exists, use the `wo[]` array as-is. Each item includes metadata such as `wo_id`, `type`,
   `level`, `node_name`, `draft_path`, `inherits_from`, `related_screen_wos`.
3. Only when `index.json` is missing, parse the `index.md` markdown table.
   Also guide re-running `python ${CLAUDE_PLUGIN_ROOT}/scripts/fanout_dag.py`
   (or `/fanout {product}`) so JSON is available from the next call onward.
4. Never quote the `index.md` body itself into context — it's meant for human reading.

Output the list of WOs targeted for rendering:

```
Starting render
  Product:   {product}
  Scope:     {WO_ID or all N items}
  Template:  {template path or default}
  Output:    reports/render/
  Confluence upload: {--push present or not}
```

WOs without an existing draft are marked "in progress (incomplete)" and rendering continues.
(Incomplete WOs aren't blocked, to allow invocation while writing is still underway.)


### Step 2 — Draft ↔ Confluence bidirectional sync check (--check-sync)

> Runs automatically when the `--check-sync` flag is present, or on entering `--push`, `/sc`,
> `/lc`.
> Bidirectional — checks both local→remote (push needed) and remote→local (drift detection).

#### 2-A. Pre-collect Confluence snapshot (model responsibility)

This script doesn't call Confluence directly (auth·global-skill separation principle — same
pattern as `/cr`). Instead, the model fetches each page's current version and saves it as a
snapshot, which the script then reads.

**Prerequisite — check wiki connector availability**

Confirm the wiki connector (a user-connected MCP tool — e.g. Confluence·Notion) via the
docs/CONNECTORS.md detection protocol. Prefer the `CONTEXT/connectors.md` mapping; otherwise
auto-detect.
Verify via schema whether the discovered tool supports a query (get) that includes page
version info·body (storage).

If the connector is absent, or if the query result can't produce the snapshot shape below:
- Skip snapshot pre-collection
- `render_sync_check.py` automatically handles this as REMOTE-UNKNOWN (graceful degradation)
- Give the PM a one-line note: "remote drift detection is disabled due to wiki connector
  absence/lack of support — only manual review is possible"

If supported, perform the following two steps in order:

```bash
# 1) Prepare the snapshot directory
mkdir -p PROJECTS/{product}/reports/.confluence-snapshot
```

2\) Iterate over the `id` field in `confluence-source/*.meta.json`, and for each page_id,
call the wiki connector's query (get) operation per its schema, and save the response into
`PROJECTS/{product}/reports/.confluence-snapshot/{PAGE_ID}.json` in the JSON shape below.

Expected snapshot JSON shape (the script only uses the following keys):
```json
{
  "id": "12345",
  "version": {"number": 7, "when": "2026-05-28T..."},
  "title": "...",
  "body": {"storage": {"value": "<xml>...</xml>"}}
}
```

If it differs from the shape above (e.g. only markdown output is supported), don't create the
snapshot file — an empty file or a different format lets the script safely classify it as
REMOTE-UNKNOWN.

#### 2-B. Run the sync-check script

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_sync_check.py \
  --hub-root . [--product {product}] --with-remote
```

Calling without `--with-remote` checks only the forward direction (OUTDATED/PENDING) as before.

Script behavior:
- **Forward** (existing): draft `updated_at` vs meta.json `_sync.last_published_at`
  - OUTDATED : draft is more recent → push needed → warning output
  - PENDING  : page_id placeholder → initial Confluence creation incomplete
- **Reverse** (new, when `--with-remote`): snapshot `version.number` vs
  meta.json `_sync.last_published_version`
  - REMOTE-DRIFT : Confluence is more recent → automatically generates
    `reports/inbox/{WO_ID}.merge-proposal.md`
  - REMOTE-UNKNOWN : no snapshot (pre-collection step wasn't run, or environment not
    configured)

Output:
- `reports/sync-queue.md` (combined forward+reverse status)
- `reports/inbox/{WO_ID}.merge-proposal.md` (one per REMOTE-DRIFT page)

Each merge-proposal.md structure:
```markdown
# Merge Proposal — WO-05 (REMOTE-DRIFT detected)

Difference between Confluence page v{N} (last pushed v{M}) and the local draft.
Select checkboxes, then run /render --apply-inbox WO-05.

## Change chunk 1 — §2. Policy body
- [ ] Apply
**Confluence (current):**
> Changed from last 5 times to last 10 times

**Local draft (current):**
> No reuse of the last 5 passwords used

## Change chunk 2 — §3. Table
...
```

Skipped when `--check-sync` is absent. When called together with `--push`, if PENDING,
re-guide **Step 0 (initial Confluence creation)** and proceed only after user confirmation.
If 1+ REMOTE-DRIFT items, recommend the PM run `--apply-inbox` before pushing.


### Step 2-2 — Apply inbox patch (--apply-inbox)

> Runs only when the `--apply-inbox {WO_ID}` option is specified.
> Applies the PM's decision from the Confluence-drift-generated merge proposal to the draft.

The PM opens `reports/inbox/{WO_ID}.merge-proposal.md`, selects one of the following two
checkboxes, then runs this command:

```markdown
- [x] **Adopt entire body** (overwrite the draft with the Confluence body)
- [x] **Manual review complete** (PM applied it manually, just archive the proposal)
```

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_apply_inbox.py \
  --hub-root . --product {product} --wo {WO_ID}
```

Script behavior:
1. Parse the proposal's checkboxes
2. **Neither checked** → NOOP (proposal is kept, shown again at the next sync check)
3. **Manual review complete** → draft unchanged, move the proposal to
   `reports/inbox/archived/`
4. **Adopt entire body**:
   - Back up the draft → keep the frontmatter, replace only the body with the Confluence body
   - **Automatically run fact_preservation_check** (original draft vs new draft)
   - PASS → update the draft + archive the proposal (`.applied.md` suffix)
   - FAIL → blocked, draft unchanged (backup discarded), save the list of missing facts to
     `reports/inbox/{WO_ID}.fact-check.md`

5. **Both checked simultaneously is an error** (exit 3) — exactly one must be selected

This step compensates for the lossy nature of an LLM round-trip with a PM approval gate.
A fully automatic round-trip is never performed (SSoT safety net).


### Step 2-1 — SSoT boundary check (--check-ssot)

> Runs only when the `--check-ssot` flag is present.

```bash
# Currently the model reads ssot-boundary.yml directly and judges
# (to be automated with a dedicated script in the future)
```

**SSoT boundary declaration file:** `CONTEXT/ssot-boundary.yml`
(If absent, automatically degrades to the inline judgment-criteria table below and continues
checking — a missing file does not hard-fail.)

Judgment criteria:
| Violation type | Level | Handling |
|---|---|---|
| HEX/px duplicated in both the screen design spec and the policy document | WARN | warn and continue |
| FR What content redefined in the policy document | FAIL | block — source must be corrected |
| Business rules described directly in the screen design spec without a POL marker | WARN | warn and continue |

If there's a FAIL, stop rendering and output the list of violations.
Skipped when `--check-ssot` is absent.


### Step 3-A — Track A publish (publish-mode gate)

> **Track A only** — `work-orders/cluster_index.json` exists (operational gate) + dossier
> draft (`type: cluster_draft`, fanout cluster-mode output).
> Track B/C·node mode skip this step and proceed to step 3 (render_assemble).

**Publish-mode branch (fix-plan-dossier-publish-split)** — read the `publication_mode` key
from `graph/project-mode.json` and enter one of two paths (`dossier-page` if file/key
absent):

| publication_mode | Publish unit | Entry |
|---|---|---|
| `dossier-page` (default) | 1 feature spec = 1 page | step 3-A body (below) |
| `split-deliverable` | D2 policy definition / D3 screen design spec, 2 pages | step 3-A-split |

```bash
# Check publish mode
python -c "import json,sys; p='PROJECTS/{product}/graph/project-mode.json'; \
import os; print(json.load(open(p,encoding='utf-8')).get('publication_mode','dossier-page') if os.path.exists(p) else 'dossier-page')"
```

#### Step 3-A (dossier-page) — 1 dossier = 1 page

> **transpose not called** — publish each dossier as 1 page.

Publish each dossier's clean copy as one page. There's no separate transpose-assembly step —
`render_assemble` has already created `reports/render/{WO_ID}.complete.md` for each dossier.

Read the list of publish-target dossiers from `cluster_index.json` (only the specified
WO_ID if `--only` is given):

```bash
# Check the dossier list (clusters[].wo_id / draft_path)
cat PROJECTS/{product}/work-orders/cluster_index.json

# Each dossier's clean copy is created by render_assemble (automatically on draft edit, or
# manually):
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_assemble.py --hub-root . \
  --product {product} --wo {WO_ID}      # → reports/render/{WO_ID}.complete.md
```

Publish step (once per dossier — only the selected ones if `--only`):
- Clean copy `reports/render/{WO_ID}.complete.md` → `publication_prefilter.py` →
  (optional color cycling · LLM tone) → `md_to_storage.py` → push as 1 page.
- Read the page id from `confluence-source/{WO_ID}.meta.json` (if absent, `/cr` creates the
  page and initializes the meta — held pending if Confluence isn't accessible).
- D1·D5 are input-type (published as-is). D4 meeting minutes are cumulative-type assembly
  (separate).
- Derived index views (D1 capability grouping·cross-cutting matrix) are synthesized via
  `render_transpose.py`'s `render_fr_capability_view`/`render_cross_cutting_matrix`, but link
  to the **dossier page** (publication-map.md §3-A).

**Exit code handling**: 0=success / 2=0 matching clusters (normal if no Dα — skipped) /
1=parsing·structural error (unclosed panel·missing cluster metadata → fix the cluster draft)
/ 3=IO. Exit 1 blocks — check the `::: {.panel section=}` structure of the cluster draft.

> In Track A, this step's `{deliverable}.assembled.md` becomes the input for step 6-1
> (publication conversion) · step 7 (push) (replacing node mode's `{WO_ID}.complete.md`). In
> other words step 3 (render_assemble) is skipped in Track A, and this step's output is fed
> directly into the publish pipeline.


#### Step 3-A-split (split-deliverable) — D2 policy definition / D3 screen design spec, 2 pages

> Only when `publication_mode: split-deliverable`. Dossier pages aren't pushed; instead all
> dossiers' §1 is **transposed** into D2 policy definition and §2 into D3 screen design spec
> (render_transpose.py reactivated — publication-map.md §0-bis).

a. Collect dossier draft paths from `cluster_index.json`. Dossier drafts with
   `is_common_shell: true` are passed separately as the D3 common shell (`--common-shell`).

```bash
DRAFTS=$(python -c "import json; d=json.load(open('PROJECTS/{product}/work-orders/cluster_index.json',encoding='utf-8')); \
print(' '.join('PROJECTS/{product}/'+c['draft_path'] for c in d['clusters']))")

# b. D2 policy definition (dossier §1 → chapters)
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_transpose.py \
  --cluster-drafts $DRAFTS --deliverable D2 \
  --template ${CLAUDE_PLUGIN_ROOT}/templates/standard/D2_policy.md \
  --output PROJECTS/{product}/reports/render/02-policy.assembled.md

# c. D3 screen design spec (dossier §2 → per-screen chapters + common-shell appendix)
#    common-shell drafts are separated via --common-shell (is_common_shell: true)
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_transpose.py \
  --cluster-drafts $DRAFTS --deliverable D3 \
  --common-shell <drafts with is_common_shell=true> \
  --template ${CLAUDE_PLUGIN_ROOT}/templates/standard/D3_screen.md \
  --output PROJECTS/{product}/reports/render/03-screen-design.assembled.md
```

d. Feed each `{02-policy|03-screen-design}.assembled.md` through the existing step 6-1
   (prefilter → [color/LLM] → fact-check) → step 7 (md_to_storage → push) unchanged. Only the
   input file differs, and **there are exactly 2 pages** (no feature-spec group page).
e. Page-id source: `confluence-source/02-policy-{product}.meta.json` /
   `03-screen-design-{product}.meta.json` (created by /cr's 1-D-split tier).
f. The per-dossier `{WO_ID}.complete.md` page loop is **not executed**.
g. Selective publish via `--only D2|D3`. Add a split row (2 URLs) to the step-8 summary.

> ⚠️ **Note (transpose scope)**: D2/D3 only reflect dossier §1/§2. §0/§5/§6 are not reflected,
> under the assumption that policy is self-contained within §1. If a dossier removes D2/D3
> from `deliverable_targets`, that cluster is omitted from the corresponding deliverable —
> check the frontmatter `deliverable_targets`.
> If D3 §2 uses screen-ID-tagged headings (`### §2-1 {SCR-ID}`), it becomes a per-screen
> chapter; otherwise it falls back to a per-cluster chapter (WARN output).


### Step 3 — Fully deterministic assembly (calling render_assemble.py) — Track B/C·node mode

> **C-RENDER (token boundary)** — the model **never performs** inline expansion of common
> content. `render_assemble.py` deterministically text-substitutes and assembles the source
> draft + common (G2-A/B) content (the model must not re-output common text — for SSoT
> accuracy·token savings).
> Track A (cluster mode) is replaced by step 3-A, so this step is skipped there.

Recommend the following run to the PM (the skill doesn't execute it directly — only guides
the command):

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_assemble.py \
  --hub-root . --product {product} [--wo {WO_ID}] [--all]
```

Script behavior (summary only, don't quote the body):
- Inlines `[{ID} §X reference]` / `Base policy fully applied — [{ID}] reference` as the
  common §text using `master-id-map.yml` (pinID→stem) + `B-headings-index.json` (§line
  ranges). Each block gets a `⟦expanded: {id}@{ver} … source⟧` source tag.
- G2-A terminology is expanded from `terms.yml`'s canonical form appearing in the body into
  "Appendix A. Glossary".
- The output frontmatter's `rendered_from_master: [{id}@{ver}]` pin lets `drift_scan.py`
  cross-check completed-version staleness too (re-render needed when version↑).
- Output: `reports/render/{WO_ID}.complete.md` (adds `{product}.full.complete.md` with
  `--all`).

If `B-headings-index.json` doesn't exist, the script warns → recommend the PM run
`python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_index.py --hub-root .` first.
WOs without a draft are automatically excluded by the script (allowing invocation while
writing is underway).

Incomplete drafts' `[TBD]` markers are exposed as-is in the complete version (the script only
assembles content, never edits it).


### Step 4 — Parallel rendering (--parallel)

> Runs when `--parallel` is combined with WO_ID unspecified (rendering everything).
> Files with no dependencies among WOs (inherits_from, related_screen_wos) are processed
> independently.

```
--parallel absent (default):  render WOs sequentially
--parallel present:           process dependency-free WOs concurrently → faster rendering
```

Dependency criterion (using `work-orders/index.json` wo[] metadata):
- `inherits_from: []` and `related_screen_wos: []` → independent WO → parallelizable
- WOs with inherits_from or related_screen_wos → processed sequentially

For parallel processing, call `render_assemble.py` independently per WO.
Output file follows the same rule (`reports/render/{WO_ID}.complete.md`).


### The --stakeholder flag

Generates a clean view for sharing with stakeholders (designers, developers, management,
etc.).
Runs the same merge logic; applies the following post-processing only at the output stage.

**Items removed (fully clean of internal tags):**
- All source tags removed: `[Common Policy]`, `[Product Applied]`, `[Product-Specific]`,
  `<!-- source: ... -->`
- All HTML comments removed

**Notation simplification:**
| Original notation | --stakeholder notation |
|---|---|
| `📝 [In progress — WO-05 incomplete]` | `⚠️ (under review)` |
| `⚠️ [{PREFIX}-B-NNN §N.N — load failed]` | `⚠️ (needs source check)` |
| `[TBD — product delta undetermined]` | `⚠️ (undetermined)` |

**Filename change:**
`{product}.full.complete.md` → `{product}.stakeholder.{date}.md`

**Document header added:**
```markdown
> **Review document** — includes content still in progress as of {date}.
> ⚠️-marked items are not yet finalized.
> Contact the planning team for the finalized version.
```

**When used together with `--push`:**
Upload to Confluence as a separate page.
Page title: `[{PREFIX}-C] {product} review-sharing copy ({date})`
Created separately from the existing finalized page.


### Step 6 — Save output file

Save the render result under `reports/render/`.

**Filename rules (render_assemble.py output = canonical):**

| Scope | Filename |
|---|---|
| Single WO | `reports/render/{WO_ID}.complete.md` |
| Whole product | `reports/render/{product}.full.complete.md` (`--all`) |
| After stakeholder post-processing | `reports/render/{product}.stakeholder.{YYYYMMDD}.md` (optional) |

The `*.complete.md` frontmatter is generated by the script (do not edit):
`source_doc_id` / `rendered_at` / `rendered_by` /
`rendered_from_master: [{id}@{ver}]` (pin for drift_scan cross-check) /
`source_referenced_master`. Do not add/edit a separate header.


### Step 6-1 — Publication conversion (on --push or --stakeholder)

> **Source vs Publication separation** — the Confluence canonical version must be a clean
> copy with process metadata removed. This step runs in-memory and doesn't produce disk
> output (use the `--save-published` flag to save explicitly if review is needed).

#### 6-1-A. Deterministic prefilter (required, always runs)

Recommend the following run to the PM (the script processes deterministically):

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/publication_prefilter.py \
  reports/render/{WO_ID}.complete.md --output /tmp/{WO_ID}.prefiltered.md
```

Items removed (all deterministic, no LLM used):
- HTML comments (`<!-- ... -->`) — includes render_assemble schema markers, DEC markers
- Self-verification checklist / prohibited items / post-completion procedures / Workflow
  Connections section
- Assignment-scope / immutable-input meta-blocks and other authoring-guide blocks
- Source tags (`⟦expanded: id@ver … source⟧`)
- Frontmatter slim-down (keeps only wo_id/type/layer/version/last_updated/title)

Substitution items:
- `[TBD — ...]` → `(undetermined)`
- `[needs confirmation: ...]` → `(under review)`
- `[policy conflict — ...]` → `(needs review — coexisting items preserved)`

Preserved (never touched): all table cells, body text, `[[POL §X-Y]]`, `[[WO-XX]]`,
`{PREFIX}-A` registered vocabulary.

#### 6-1-A2. Color cycling (only with `--color-cycle` — optional, off by default)

> Automatically injects change-tracking colors (latest change = green / previous = blue,
> 2-cycle decay) right before publish. The `apply_color_cycling.py` engine diffs against the
> previous publish state (`meta.json._color_state`) and produces the result deterministically
> (no LLM). **No color change unless explicitly specified** — use only when the published
> document needs visual change markers (publication-syntax.md §6 SSoT).

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/apply_color_cycling.py \
  --input /tmp/{WO_ID}.prefiltered.md \
  --output /tmp/{WO_ID}.colored.md \
  --meta-in  PROJECTS/{product}/confluence-source/{NN}-{type}-{product}.meta.json \
  --meta-out PROJECTS/{product}/confluence-source/{NN}-{type}-{product}.meta.json
```

- No `--meta-in` (first publish) → treated as baseline (no color injected, state
  initialized).
- The output `*.colored.md` becomes the input for step 7 (md_to_storage→push) (uses the
  prefilter result if unused).
- `meta.json._color_state` is updated and becomes the basis for the next publish's cycling
  (auto-expires after 2 cycles).
- Nested color spans are forbidden (lint L6) — the engine deterministically injects only
  1-depth.

#### 6-1-B. LLM tone/style normalization (only with `--style-example`)

If the `--style-example` option is specified, apply LLM conversion to the prefilter result.

Input: prefilter result + `--style-example {path}` + `CONTEXT/brand-voice.md`

LLM instruction principles (injected by this SKILL as the system prompt):
- Policy facts (numbers·status names·error codes·table cells·UI copy·POL/WO markers) are
  **100% preserved**
- Only vocabulary·sentence length·heading depth·table format are matched to the example
- brand-voice.md's active-voice·explicit-subject rules always apply
- No inventing content not in the source

#### 6-1-C. Fact preservation check (required if an LLM step ran)

Verify immediately after LLM conversion:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/fact_preservation_check.py \
  --before /tmp/{WO_ID}.prefiltered.md \
  --after  /tmp/{WO_ID}.llm-out.md \
  --hub-root . \
  --report reports/render/{WO_ID}.fact-check.md
```

Judgment:
- PASS → proceed to step 7
- FAIL → output list of missing facts + block push. Choose one of:
  - Retry the LLM (different prompt or different style-example)
  - Skip the LLM step with `--no-llm` and use only the prefilter result
  - Have the PM manually add the missing facts to the LLM result

If only the prefilter was used without `--style-example`, skip fact-check too (the prefilter
is deterministic, so its conversion loss is intentional).

#### 6-1-D. `--stakeholder` shortcut mode

The `--stakeholder` flag automatically applies:
- Forces the prefilter to run
- Additional substitutions: `📝 [In progress — WO-NN incomplete]` → `⚠️ (under review)` etc.
  (existing stakeholder rules)
- Filename: `reports/render/{product}.stakeholder.{date}.md` (separate disk output)
- When used with `--push`, uploaded as a separate Confluence page (title:
  `[{PREFIX}-C] {product} review-sharing copy ({date})`)


### Step 7 — Confluence upload (on --push flag)

Runs only when the `--push` flag is specified.
**The publication-conversion result (step 6-1)** is converted to XML and uploaded (not the
source draft).

- Updates the existing Confluence page if present, creates a new one otherwise
- Page title: `[{PREFIX}-C] {product} complete policy document ({date})`
- After upload, outputs the Confluence URL
- On successful upload, updates `meta.json._sync.last_published_version` (using the version
  from the Confluence response)
- On failure, the local file is kept and only the error content is output


### Step 7-1 — XML structural quality check (--verify)

> When the `--verify` flag is present, runs right after `--push` completes.
> When called alone without `--push`, runs against the existing confluence-source/*.xml
> files.

Recommend the following run to the PM:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_verify.py \
  --hub-root . [--product {product}]

# To verify a single file only:
python ${CLAUDE_PLUGIN_ROOT}/scripts/render_verify.py \
  --file PROJECTS/{product}/confluence-source/02-policy-{product}.xml
```

Script behavior (summary):
- F1: panel macro color rule (borderColor=#24FE00 / titleColor=#002FD5)
- F2: code block ac:plain-text-body + CDATA (rich-text-body forbidden)
- W1: FR number §-base 3-digit format
- W2: at least one ac:layout-section present
- W3: no remaining `{{...}}` placeholders
- Output: `reports/verify-report.md`

If there's a FAIL, include it as a warning block in the render summary.
WARN is non-blocking — shown as a list in the summary.
Skipped when `--verify` is absent.


### Step 8 — Output render summary

```
Render complete

  Output file:  reports/render/{filename}
  Total sections: {N}
    [Common Policy]:     {N} sections
    [Product Applied]:   {N} sections
    [Product-Specific]:  {N} sections
    [TBD]:               {N} sections
    [In progress]:       {N} WOs

  Sync status:  {OUTDATED {N} / all SYNCED}  ← --check-sync result
  SSoT check:   {FAIL {N} / WARN {N} / PASS}  ← --check-ssot result
  XML check:    {FAIL {N} / WARN {N} / PASS}  ← --verify result
  Confluence:   {upload URL or "no --push"}

Next steps:
  Continue writing drafts:  Track A: /write-cluster {product} {cluster_id} ·
                            legacy: /write {WO_ID} or /flow {product} {screen_id}
  Resolve sync gap:         /render {product} --push  (push OUTDATED documents)
  Full validation:          /integrate {product}
  Re-render:                /render {product}
```


## Result file list

| File | Creation condition | Content |
|---|---|---|
| `reports/render/{WO_ID}.complete.md` | always | render_assemble.py canonical output |
| `reports/render/{product}.full.complete.md` | on --all | whole-product complete version |
| `reports/render/{product}.stakeholder.{date}.md` | on --stakeholder | stakeholder-sharing copy |
| `reports/sync-queue.md` | on --check-sync | Draft↔Confluence sync status |
| `reports/verify-report.md` | on --verify | XML structural quality check result |


## Usage examples

```bash
# Check the complete version of a specific in-progress WO (default markdown)
/render dbaas WO-03

# Output the complete whole-product policy document
/render dbaas

# All the way to Confluence upload
/render dbaas --push

# Clean view for stakeholder sharing (possible even mid-authoring)
/render dbaas --stakeholder

# Share only a specific WO with a designer
/render dbaas WO-05 --stakeholder

# Share directly to Confluence as a review page
/render dbaas --stakeholder --push

# Only run the Draft → Confluence sync gap check
/render dbaas --check-sync

# Include the SSoT boundary violation check
/render dbaas --check-ssot

# Parallel render of independent WOs (whole product, faster)
/render dbaas --parallel

# push + XML quality check in one go
/render dbaas --push --verify

# Full pipeline (sync check + SSoT check + parallel render + push + verify)
/render dbaas --check-sync --check-ssot --parallel --push --verify
```


## Notes

- Inline expansion of common content is **performed deterministically by
  `render_assemble.py`**.
  The model doesn't re-output common text (C-RENDER token boundary·SSoT accuracy).
- The complete version is the **planner's canonical copy (latter), not a reference view**.
  However, **manual editing is forbidden**
  — edit only the source (former: /write·/flow) and re-render (dual authoring = SSoT
  collapse).
- `--stakeholder` applies only as **post-processing (tag cleanup)** on the scripted
  `*.complete.md` output (it doesn't redo inline expansion).
- Doesn't stop even if incomplete-draft WOs exist (the script auto-excludes them, allowing
  invocation while writing is underway)
- `--push` runs only when explicitly specified (no automatic upload)
- `--check-sync` only shows a warning when OUTDATED is found and doesn't stop rendering.
  (To stop, check sync-queue.md first, then prioritize running --push)
- FAIL in `--check-ssot` blocks rendering. WARN allows it to continue.
  The SSoT boundary declaration's SSoT is `CONTEXT/ssot-boundary.yml`.
- FAIL in `--verify` is included as a warning in the summary but doesn't roll back the push
  result.
  (The Confluence version is already uploaded — fix the XML and re-push)
- `render_sync_check.py` / `render_verify.py` are **read-only** — they don't modify source
  files.
