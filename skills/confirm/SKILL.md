---
name: confirm
description: Freezes all WO drafts as v1.0-frozen and deploys them to external systems. Before execution, the conditions integrator PASS + 0 outstanding P0 items must both be satisfied.
triggers:
  - "confirm"
  - "freeze"
  - "deploy policy"
phase: 4
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

## Precondition Checks

Check the following 4 items in order. If any is not satisfied, stop execution
and explain how to resolve it.

1. Check that the final verdict in `reports/integration-summary.md` is PASS.
   If it is FAIL or the file does not exist, instruct the PM to re-run
   `/integrate {product}` and stop.

2. Check the number of P0 items in `open-issues.md`.
   If there is 1 or more P0 item, print the list and stop.

3. Cross-check all WOs registered in `work-orders/index.md` against the
   actual files in `drafts/`.
   If any draft is missing, print the list of WO IDs and stop.

4. Check whether the freeze status in `decisions.md` is false.
   If it is already frozen, print a double-freeze warning and re-confirm
   the PM's intent.


## Execution Steps

### Step 1 — Insert draft version tags

Iterate over all `drafts/*.draft.md` files.
Insert the following two lines into each file's header:

```
**version**: `v1.0-frozen`
**frozen_at**: `{UTC timestamp, ISO 8601}`
```

Insertion point: immediately below the file's first `---` divider.
If a version field already exists, overwrite it.


### Step 2 — Record the freeze in decisions.md

Append the following block to the bottom of `decisions.md`:

```markdown
## Freeze Record

- **frozen_at**: {UTC timestamp}
- **frozen_by**: auto-recorded by /confirm
- **total_wo**: {WO count}
- **policy_wo**: {policy WO count}
- **screen_wo**: {screen WO count}
- **graph_hash**: {first 12 characters of graph.json SHA256}
- **status**: FROZEN
```

Once `status: FROZEN` is set, direct edits to `decisions.md` are forbidden.


### Step 3 — Record the Phase in session-log.md

Add the following item to `session-log.md`:

```markdown
- {date} Entered Phase 4: /confirm complete, v1.0-frozen applied, {N} WOs
```


### Step 3-5 — Publication conversion + wiki push (forced, automatic)

> Entering Phase 4 is the point at which the frozen master copy is
> established, so a **clean copy that has gone through the publication
> conversion** must be uploaded to the wiki (e.g. Confluence) as the master.
> This runs automatically without an explicit PM invocation.

Recommend the following command to the PM (`--push` is included automatically;
`--style-example` is optional):

```bash
/render {product} --push --check-sync --verify
```

Internal behavior (see render SKILL.md, step 6-1):
1. Deterministic prefilter — strip process metadata
2. LLM tone normalization (only if the PM specified `--style-example`)
3. fact_preservation_check — verify 100% preservation of policy facts
4. markdown → wiki publication format conversion (e.g. Confluence Storage Format XML)
5. wiki push — update the existing page or create a new one
6. Update `_sync.last_published_version` in meta.json

On FAIL (fact-check FAIL or push failure):
- The overall /confirm process is not aborted — step 5 (repo MR/PR) still proceeds
- The error is logged to `reports/cr-error.log`
- The PM can manually retry `/render --push`


### Step 4 — (legacy) Call /cr — page hierarchy metadata only

Run `/cr {product}`. However, since **the body upload was already completed
in step 3-5**, this step now only performs the following side tasks:
- Create or look up the project root page (`{product} Policy Document v1.0`)
- Page hierarchy (placement under parent_page_id)
- Apply labels (`v1-frozen`, `policy`, `screen`)
- Update the index page body (list of links to all pages)

The body content itself is already reflected from the publication result in
step 3-5. Note: if `/cr` overwrites the body again, the publication
conversion is invalidated — `/cr` is planned to be split into a "metadata-only,
no body changes" mode in the future (currently it can re-push the same body).

On failure, log the error to `reports/cr-error.log` and do not skip step 5
(repo MR/PR creation proceeds regardless of wiki push failure).


### Step 5 — Create repo MR/PR

Detect the repo connector (an MCP tool the user has connected — e.g. GitLab,
GitHub) using the docs/CONNECTORS.md detection protocol, and create an MR/PR.
If absent, record `[no repo connector — MR/PR creation skipped]` and proceed
to the next step.
MR/PR title: `[{PREFIX}-C] {product} Policy Document v1.0-frozen`
Include the following items in the MR/PR description:
- Full WO list (policy / screen separated)
- graph.json hash
- decisions.md freeze timestamp
- wiki page link (if upload succeeded)
- open-issues.md WARN item count

If MR/PR creation fails, print an error message but do not abort the overall
process.


### Step 6 — chat completion notification

Detect the chat connector (an MCP tool the user has connected — e.g. Slack,
Mattermost) using the docs/CONNECTORS.md detection protocol, and send a
notification to the project channel.
If absent, record `[no chat connector — notification skipped]` and proceed
to the next step.
Notification content:
- Project name and frozen_at timestamp
- Policy WO count / screen WO count
- MR/PR URL (if created successfully)
- wiki upload result (success / failure)

If chat sending fails, print a warning to the console only and continue.


### Step 7 — Record in metrics.md

Record the following KPIs in `reports/metrics.md`:

```markdown
## {product} v1.0-frozen KPI

| Item | Value |
|---|---|
| frozen_at | {UTC timestamp} |
| total_wo | {N} |
| policy_wo | {N} |
| screen_wo | {N} |
| open_issues_p1 | {N} |
| open_issues_p2 | {N} |
| confluence_upload | SUCCESS / FAIL |
| gitlab_mr_url | {URL or FAIL} |
```

> **split-deliverable publication mode** (`graph/project-mode.json`
> `publication_mode: split-deliverable`, fix-plan-dossier-publish-split):
> the v1.0-frozen tag is applied to the dossier draft (the source of truth) —
> unchanged. The derived D2 policy definition / D3 screen design documents
> are deterministic projections of the frozen dossier; on push, the
> per-deliverable meta's `_sync.last_published_version` is incremented.
> Add a non-blocking `deliverables: D2,D3` note to metrics (not a KPI
> blocking condition).


## Output Files

| File | Change |
|---|---|
| `drafts/*.draft.md` | Insert version: v1.0-frozen + frozen_at |
| `decisions.md` | Add Freeze Record block |
| `session-log.md` | Record Phase 4 entry |
| `reports/metrics.md` | Add KPI table |
| `reports/cr-error.log` | Created only on wiki push error |


## Failure Handling Principles

- Steps 1–3 (local file operations): stop immediately on failure. Do not
  roll back changes; ask the PM to confirm manually.
- Steps 4–6 (external systems): on failure, log the error and continue to
  the next step. External system errors do not affect the local frozen
  state.
- Step 7 (metrics): on failure, print a warning and mark it complete.
