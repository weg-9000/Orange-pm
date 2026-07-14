---
name: promote
description: Converts sketches/{screen_id}.sketch.md into a formal draft. Finds the WO connected to that screen in graph.json, maps it, and converts it into drafts/{WO_ID}.draft.md. Restructures the sketch content into the 4-state structure, with PM confirmation of each item.
triggers:
  - "promote"
  - "finalize sketch"
  - "sketch to draft"
  - "convert sketch"
phase: any
effort: medium
user-invocable: true
---

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


## Common reference guard (C0·C-PIN — gates/master-derivation-gate.md SSoT)

Applies during sketch → draft conversion. See `CONTEXT/gates/master-derivation-gate.md` for
details.

1. Common cross-check: verify the converted draft doesn't rewrite G2-A/B policy — rewritten
   portions are replaced with `[{doc_id} §X] reference` links (B-headings-index candidate §
   only).
2. Conversion self-check: resolve the sketch's placeholder links to actual POL §anchors /
   `[[spec-catalog variableID]]` (no unresolved placeholders may remain).
3. C-PIN: fill in `referenced_master: [{pinID}@{version}]` in the converted draft's frontmatter
   (master-id-map.yml authority ID). If left blank → opt-out → requires a decisions.md
   rationale.
4. Integrate PM confirmation into the existing item-confirmation step (do not add a separate
   serial prompt).


## Precondition check

0. **Track audit (cluster-mode awareness — same signal as `/fanout` prerequisite 0)**
   If any of the following exist, this project is the **cluster(dossier) model = Track A**.
   - `PROJECTS/{product}/graph/project-mode.json` (track=A / model=dossier)
   - `PROJECTS/{product}/graph/cluster_map.json` or `graph.clustered.json`
   - `PROJECTS/{product}/drafts/cluster_*.draft.md` (dossier already written)

   If detected, **the Step 1 WO-mapping flow below does not apply** — there is no standalone
   screen WO to promote into. Instead, identify the target `cluster_id` that owns this screen
   (via `graph/cluster_map.json` or `/plan-audit {product}`), then have the PM manually fold the
   sketch content into that cluster's `§2 Screen Design` panel through
   `/write-cluster {product} {cluster_id}`. Do not mark the sketch `promoted: true` until that
   cluster draft has actually been updated.
   If uncertain which track applies, run `/plan-audit {product}` first to confirm.

1. Verify `sketches/{screen_id}.sketch.md` exists.
   If not, output the list of valid sketch files and stop.

2. Check the `promoted: false` status in the file header.
   If already `promoted: true`, output "this sketch has already been converted" and stop.

3. Verify `PROJECTS/{product}/graph/graph.json` exists.
   If not, guide creating the graph.json needed for formal conversion, and stop.
   (Guide running `/graph-gen {product}` or the method of specifying a WO directly without
   graph.json)

4. Verify `PROJECTS/{product}/work-orders/index.md` exists.
   If not, guide running `/fanout {product}`, and stop.


## Execution steps

### Step 1 — WO mapping

If `{screen_id}` is in `SCR-NNN` format, find it directly among the screen nodes in graph.json.
If it's in `SKT-NNN` format (temporary ID), have the PM enter the SCR-NNN or WO ID to connect.

Output the mapping result:
```
Sketch → WO mapping
  Sketch ID:    {screen_id}
  Connected WO: {WO_ID} ({screen name})
  Connected REQ: {REQ-NNN}

Convert to this WO? (Y / specify a different WO)
```

Do not proceed to the next step without PM confirmation.


### Step 2 — Analyze sketch content and propose structure mapping

Read the content of `sketches/{screen_id}.sketch.md` and attempt to classify it into the
4-state (idle / loading / success / error) structure.

Output a classification proposal table:
```
Sketch content → 4-state mapping proposal

┌─────────────────────────────────────────────────────┐
│ Content classified as idle state:                    │
│  · (item extracted from sketch)                      │
│  · [unclassified] items shown if present              │
├─────────────────────────────────────────────────────┤
│ Content classified as loading state:                  │
│  · (item extracted from sketch)                      │
├─────────────────────────────────────────────────────┤
│ Content classified as success state:                  │
│  · (item extracted from sketch)                      │
├─────────────────────────────────────────────────────┤
│ Content classified as error state:                    │
│  · (item extracted from sketch)                      │
├─────────────────────────────────────────────────────┤
│ [Unclassified] — content that doesn't fit any state:  │
│  · (item list)                                        │
│  → needs a choice: delete / idle / separate open-issue │
└─────────────────────────────────────────────────────┘
```

Proceed to Step 3 once the PM revises the classification or handles unclassified items and
confirms.


### Step 3 — Generate the formal draft file

Based on the `work-orders/{WO_ID}.md` template structure, generate
`drafts/{WO_ID}.draft.md`.

File header:
```markdown
---
doc_id: {WO_ID}
type: screen
version: draft
written_at: {UTC timestamp}
screen_id: {SCR-NNN}
promoted_from: sketches/{screen_id}.sketch.md
promoted_at: {UTC timestamp}
reviewed: false
---
```

Content composition:
- Place the 4-state classification finalized in Step 2 into each state section.
- Mark B-policy reference items with the placeholder format `[{PREFIX}-B-NNN] §N.N reference`.
  (Formal B-policy loading happens via a normal `/flow` run, or the PM does it directly)
- Mark unconfirmed items with a `[TBD]` tag and register them in open-issues.md as P1.

Generate the self-verification checklist in an incomplete state:
```markdown
## Self-verification checklist
- [ ] Full 4-state definition complete (sketch conversion — some items may need supplementing)
- [ ] {PREFIX}-B common policy review and reference-link maintenance needed
- [ ] {PREFIX}-A vocabulary standard review needed
- [ ] No decisions.md violations
- [ ] TBD items registered in open-issues.md
```


### Step 4 — Update sketch file status

Update the `sketches/{screen_id}.sketch.md` header:
```markdown
promoted: true
promoted_to: drafts/{WO_ID}.draft.md
promoted_at: {UTC timestamp}
```

Preserve the file content (do not delete it).


### Step 5 — Completion report and session-log record

```
/promote complete — {screen_id}

  Sketch:            sketches/{screen_id}.sketch.md
  draft:             drafts/{WO_ID}.draft.md
  TBD items:         {N} (registered in open-issues.md as P1)
  Needs supplement:  B-policy reference links {N}

Recommended next steps:
  /flow {product} {SCR-NNN}  — maintain B-policy reference links and supplement microcopy
  /review drafts/{WO_ID}.draft.md  — verify the current state (pre-check before supplementing)
```

Add to session-log.md:
```markdown
- {date} /promote {screen_id}: sketches → drafts/{WO_ID}.draft.md conversion / TBD {N} items
```


## Result file list

| File | Content |
|---|---|
| `drafts/{WO_ID}.draft.md` | sketch-based formal draft (includes items needing supplementing) |
| `sketches/{screen_id}.sketch.md` | status updated to promoted: true |
| `open-issues.md` | TBD items registered as P1 |
| `session-log.md` | promote completion record |


## Next step

```
B-policy maintenance:  /flow {product} {SCR-NNN}
draft verification:    /review drafts/{WO_ID}.draft.md
```
