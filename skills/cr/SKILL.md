---
name: cr
description: |
  Builds the Confluence page hierarchy + applies labels/metadata for
  v1.0-frozen drafts.
  Body upload is handled by /render --push (a clean copy that has gone
  through the publication conversion), so this skill focuses on the page
  hierarchy, labels, index page, and session-log recording.
  Remote calls detect the wiki connector (an MCP tool the user has
  connected — e.g. Confluence, Notion) using the CONNECTORS.md detection
  protocol.
  When the --local-only flag is used, only local Markdown storage is
  performed, without a wiki connector.
triggers:
  - "cr"
  - "confluence upload"
  - "upload policy"
phase: 4
effort: medium
user-invocable: true
---

## Separation of Responsibilities (Source/Publication Architecture)

| Area | Owner |
|---|---|
| Body publication conversion (prefilter, LLM tone, fact-check) | `/render --push` |
| Body Markdown → Storage Format XML conversion | `/render --push` |
| Body Confluence page update API call | `/render --push` |
| Confluence page hierarchy (placement under parent_page_id) | **this skill** |
| Page labels (`v1-frozen`, `policy`, `screen`, etc.) | **this skill** |
| Index page body creation/update | **this skill** |
| session-log/metrics recording | **this skill** |

When `/confirm` is entered, `/render --push` runs first in step 3-5, so the
body is already published to Confluence as the master copy. This skill only
overlays the page structure and metadata on top of it (re-pushing the body
is forbidden — it would invalidate the publication conversion).

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

## Precondition Checks

1. Read the following values from `CONTEXT/layer-config.md`:
   - `confluence_space_key`: the target space key for upload
   - `confluence_parent_page_id`: the project root's parent page ID
   If missing, ask the PM to provide the values and stop.

2. Detect any files under `drafts/*.draft.md` that lack the
   `**version**: \`v1.0-frozen\`` tag.
   If any exist, print the list and exclude them from the upload target.
   If there are 0 frozen drafts, notify "There are no frozen drafts to
   upload" and stop.

3. Check whether the `--local-only` flag is set.
   If set, run only step 4 without a wiki connector, then finish.

4. Detect the wiki connector (an MCP tool the user has connected — e.g.
   Confluence, Notion) using the CONNECTORS.md detection protocol. Prefer
   the `CONTEXT/connectors.md` mapping; otherwise auto-detect. If the
   connector is absent or the connection fails, print the guidance from
   CONNECTORS.md and ask the PM whether to switch to `--local-only` mode.


## Execution Steps

### Step 1 — Classify upload targets (branch by authoring model)

First, determine the authoring model (fix-plan-dossier-publish):
- **dossier model (Track A)**: `work-orders/cluster_index.json` exists
  (operational gate) + a dossier draft (`type: cluster_draft`,
  `wo_id: {PREFIX}-K-{cluster_id}`, produced by fanout cluster-mode) →
  **dossier mode**. Branch further by `graph/project-mode.json`'s
  `publication_mode`:
  - `dossier-page` (default / key absent) → **1-D** (1 capability dossier
    = 1 page).
  - `split-deliverable` → **1-D-split** (2 pages: D2 policy definition /
    D3 screen design).
- **legacy model**: anything else → the existing policy/screen group split
  (1-L below).

#### 1-D. dossier mode (dossier-page) — 1 capability dossier = 1 page

Load `clusters[]` from `work-orders/cluster_index.json` as the page targets.
**Page hierarchy (no transpose split — D2/D3 policy/screen separation
deprecated):**

```
{product} Planning v1.0 (root, step 2)
├─ Capability Dossiers/ (group page)
│   ├─ {dossier 1}   ← cluster_index.clusters[0]  (draft_path clean-copy body)
│   ├─ {dossier 2}
│   └─ … (in cluster_id order)
├─ D1 Requirements Definition   (inputs/requirements.md)
├─ D4 Meeting Notes            (meetings/)
└─ D5 Competitor Research       (inputs/research.md)
```

Each dossier page's body is already uploaded by `/render --push` from
`reports/render/{WO_ID}.complete.md` (the clean copy). This skill focuses on
**page hierarchy, labels, and per-dossier meta.json**.

**Create per-dossier meta.json** — 1 dossier = `confluence-source/{WO_ID}.meta.json`:
```json
{ "id": "{created page_id or {{PLACEHOLDER}}}",
  "title": "{capability} Capability Dossier",
  "wo_id": "{WO_ID}", "doc_id": "{cluster_id}",
  "_sync": { "last_published_version": 0, "last_published_at": null } }
```
This file is the per-dossier state key for render_sync_check/sync_emit.
Before the page is created, keep `id` as `{{PLACEHOLDER}}`, and the sync
status is exposed as PENDING.

> **If Confluence is unreachable**: page creation and page_id acquisition
> are held. meta.json can be pre-created with a placeholder
> (`--local-only`). Actual page creation happens once access is restored.

#### 1-D-split. dossier mode (split-deliverable) — 2 pages, D2/D3

When `publication_mode: split-deliverable`. The dossier master is
**projected into 2 deliverable pages: D2 policy definition / D3 screen
design** (no capability dossier group page).

```
{product} Planning v1.0 (root, step 2)
├─ Policy Definition        ← dossier §1 → transpose D2 (reports/render/02-policy.assembled.md)
├─ Screen Design            ← dossier §2 → transpose D3, per-screen (03-screen-design.assembled.md)
├─ D1 Requirements Definition   (inputs/requirements.md)   ← unchanged
├─ D4 Meeting Notes            (meetings/)                 ← unchanged
└─ D5 Competitor Research       (inputs/research.md)        ← unchanged
```

Body push is handled by `/render --push`'s split path (step 3-A-split).
This skill only sets up the **page hierarchy, labels, index, and
per-deliverable meta**.

**Create per-deliverable meta.json** (2 files):
```json
// confluence-source/02-policy-{product}.meta.json
{ "id": "{page_id or {{PLACEHOLDER}}}", "title": "[Policy Definition] {product}",
  "deliverable": "D2", "_sync": { "last_published_version": 0, "last_published_at": null } }
// confluence-source/03-screen-design-{product}.meta.json
{ "id": "{page_id or {{PLACEHOLDER}}}", "title": "[Screen Design] {product}",
  "deliverable": "D3", "_sync": { "last_published_version": 0, "last_published_at": null } }
```

Page bootstrap templates: `templates/standard/02-policy.md` /
`templates/standard/03-screen-design.md`. There is no separate template for
meta.json — this skill writes it inline per the **Create per-deliverable
meta.json** block above. Labels: `{product},policy,v1-frozen` /
`{product},screen,v1-frozen`.

These 2 meta files are the per-deliverable state keys for
render_sync_check/sync_emit (distinct from a SOURCE-ONLY dossier). Before
the page is created, keep `id` as `{{PLACEHOLDER}}`.

#### 1-L. legacy mode — policy/screen groups (existing)

Load the draft list by scanning `drafts/*.draft.md` directly (default
path). `reports/integration-input.json` is a legacy optional input
referenced only if it exists, and is not required (integrate/integrator
scan draft frontmatter directly). Split drafts into two groups:
- `policy` group: WO drafts with type=policy
- `screen` group: WO drafts with type=screen

Upload order: complete all of policy first, then process screen.
(Order matters because screen pages reference policy page IDs via internal
links.)


### Step 2 — Create or look up the project root page

Use the wiki connector's lookup (get/search) operation to check whether a
page titled `{product} Policy Document v1.0` exists under
`confluence_parent_page_id`.
If it exists, reuse its page_id.
If not, create a new page and record the page_id.

Include the following items in the root page body:
- Project name, frozen_at timestamp
- graph.json hash
- policy WO count / screen WO count
- List of links to child pages to be created (updated after upload completes)


### Step 3 — Apply metadata to policy WO pages

> **The body has already been uploaded by /render --push.** This step
> only handles the page hierarchy, title, labels, and the draft frontmatter
> pin.

Process each draft in the policy group in order.

Perform the following operations with the wiki connector.

**First, inspect the connector schema — mandatory, since re-pushing the
body invalidates the publication conversion:**

Read the schema of the discovered wiki tool and check whether it supports
an operation (a metadata-only update) that can update the title, parent
page, and labels without touching the body.

Branch:

1. **Metadata update without body modification is supported** — call the
   operation per the schema. Domain information to pass:
   - Target page: `{page_id}`
   - Title: `{WO_ID} — {section title}`
   - Parent page: `{root_page_id}`
   - Labels: `{product}`, `policy`, `{WO_ID}`, `v1-frozen`

2. **Not supported (only an update including the body is possible)** —
   since `/render --push` has already correctly uploaded both the body and
   title, skip this entire step. If label/parent changes are needed, notify
   the PM:
   ```
   [cr] WARN: The connected wiki connector does not support a metadata
        update without body modification.
        Skipping metadata application to avoid the risk of re-pushing the
        body. If label/parent changes are needed, apply them directly in
        the wiki UI.
        page_id={page_id}, recommended items to apply: title, parent, labels
   ```
   After notifying, log it to reports/cr-error.log at INFO level.

**Forbidden**: calling a page update using raw source
(`drafts/{WO}.draft.md`) as the body — this would overwrite the wiki master
page with raw source that has not gone through the publication conversion,
exposing HTML comments, self-verification, and DEC markers on the master
page. Never do this under any circumstances.

On success, add the following fields to the draft file (not in
frontmatter, but in a meta block at the bottom of the body — the
publication prefilter removes it automatically):
```
**confluence_page_id**: `{page_id}`
**confluence_url**: `{page_url}`
**uploaded_at**: `{UTC timestamp}`
```

On failure, log it to `reports/cr-error.log` in the following format and
proceed to the next file:
```
[FAIL] {WO_ID} | {error code} | {error message} | {UTC timestamp}
```


### Step 4 — Apply metadata to screen WO pages

Process the screen group — same pattern as step 3, with these differences:

Page title: `{WO_ID} — {screen name} ({Screen ID})`
Labels: `{product}`, `screen`, `{Screen ID}`, `v1-frozen`

Related policy page links are already included in the body during the
publication conversion step (`[[POL §X-Y]]` marker → Confluence internal
link). No separate body modification is needed in this step.


### Step 5 — Update the index page

Update the root page body.
Insert the title + URL of every successfully uploaded page, split into
policy / screen sections.
Include failed items with an `[upload failed]` marker.


### Step 6 — local-only storage (with --local-only, or if Confluence fails entirely)

Create the `reports/confluence-export/` directory.
Copy each draft as-is, adding a timestamp to the filename:
`{WO_ID}_{YYYYMMDD}.draft.md`
Write the full file list to `reports/confluence-export/index.md`.


### Step 7 — Record in session-log.md

Add an upload result summary to `session-log.md`:
```
- {date} /cr complete: {N} succeeded / {N} failed, root page: {URL}
```

If there are any failures, register them as P2 in `open-issues.md`.


## Output Files

| File | Change |
|---|---|
| `drafts/*.draft.md` | Add confluence_page_id + confluence_url + uploaded_at |
| `session-log.md` | Record upload result summary |
| `reports/cr-error.log` | Records failures (created only on failure) |
| `reports/confluence-export/` | File copies, in local-only mode |


## Failure Handling Principles

- On individual file failure, log it and continue.
- If the wiki connector connection fails entirely, suggest switching to
  local-only mode.
- If root page creation fails, stop immediately and ask the PM to check
  permissions.
