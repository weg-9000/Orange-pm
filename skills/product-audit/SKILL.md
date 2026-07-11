---
name: product-audit
description: Analyzes the state of your own product via the wiki·design·repo connectors the user has connected (CONNECTORS.md), and structures the existing feature list, pain points, and improvement opportunities. Completes the product-audit stream of the 3 Discovery streams.
triggers:
  - "product-audit"
  - "audit product"
  - "analyze product"
phase: -1
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

## Precondition check

1. Read PREFIX from `CONTEXT/layer-config.md`.
   If not present, guide the user to run `/ingest {product}`.

2. Check whether the `inputs/discovery/product-audit/` directory exists.
   If not, create it.

3. If existing files are present, confirm with the PM before overwriting.


## Execution steps

### Step 1 — Query documents (`wiki` connector)

Use the `wiki` connector (e.g. Confluence, Notion — CONNECTORS.md detection protocol) to query
the following items:

**Query targets:**
- Current service feature spec pages (prefer Approved documents)
- PRD / planning docs from previous development cycles
- API integration spec documents
- Known issue / bug record pages

**Items to collect:**
- Feature name, feature description, current status (in operation / in development / discontinued)
- Layer associated with each feature (policy / screen / system)
- Documented customer complaints or limitations

If the connector is absent or the connection fails, record
`[wiki skipped]` and continue.


### Step 2 — Query design (`design` connector)

Use the `design` connector (e.g. Figma — CONNECTORS.md detection protocol) to query the
current product design files.

**Items to collect:**
- Screen list (based on frame names)
- Status per screen (current UI / to be redesigned / deprecated)
- Key components and recurring patterns
- Screen flow (based on prototype links)

If the connector is absent or the connection fails, record
`[design skipped]` and continue.


### Step 3 — Query repository (`repo` connector)

Use the `repo` connector (e.g. GitLab, GitHub — CONNECTORS.md detection protocol) to query
the following items:

**Query targets:**
- Titles + labels of issues closed in the last 90 days
- Titles of MRs merged in the last 90 days
- README or CHANGELOG

**Items to collect:**
- Scope of recently changed features
- Recurring bug patterns
- Tech-debt-related labels (tech-debt, hotfix, etc.)

If the connector is absent or the connection fails, record
`[repo skipped]` and continue.


### Step 4 — Write existing-features.md

Write based on the collected data.

**Authoring criteria:**
- Classify each feature as in-operation, in-development, or discontinued.
- Split feature units by screen or API.
- If the design screen name and document feature name don't match, list both.

**File format:**
```markdown
# Existing Feature List — {product}

> Collection baseline date: {date}
> Sources: wiki / design / repo connectors (only successfully discovered sources listed)

## Features in operation

| Feature | Description | Related screen | Document source | Notes |
|---|---|---|---|---|

## Features in development

| Feature | Description | Expected completion | Source | Notes |
|---|---|---|---|---|

## Discontinued / Deprecated

| Feature | Reason for discontinuation | Replacement feature |
|---|---|---|

## Discovery gaps (features with unconfirmed source)

| Feature | Gap reason |
|---|---|
```

If there are 3+ "discovery gap" items, register them in open-issues.md as P2.


### Step 5 — Write pain-points.md

Classify collected issues, complaints, and limitations by type.

**Classification criteria:**

| Type | Definition |
|---|---|
| UX | inconvenient user flow, hard to understand, lack of feedback |
| Performance | response delay, error rate, processing limits |
| Business logic | policy inconsistency, unhandled exceptions, edge-case errors |
| Integration | unstable external system connections, API mismatch |
| Operations | lack of admin tools, no monitoring, requires manual handling |

**File format:**
```markdown
# Pain Points — {product}

> Collection baseline date: {date}
> Sources: wiki / repo issues / chat connector (only successfully discovered sources listed)

## UX pain points

| Item | Description | Source | Severity (H/M/L) |
|---|---|---|---|

## Performance pain points

...

## Business logic pain points

...

## Integration pain points

...

## Operations pain points

...
```

If any severity-H item exists, register it in open-issues.md as P1.


### Step 6 — Write overview.md

Write by cross-analyzing existing-features.md and pain-points.md.

**File format:**
```markdown
# Product Status Summary — {product}

## Status snapshot

| Item | Figure |
|---|---|
| Features in operation | {N} |
| Features in development | {N} |
| Total pain points | {N} (H: {N} / M: {N} / L: {N}) |
| Discovery gaps | {N} |

## Improvement opportunities identified

{Description of areas needing improvement, based on severity H/M items in pain-points.md}

### Requirements linkage potential

| Improvement opportunity | Expected requirements layer | Priority |
|---|---|---|
| {improvement item} | Layer 1 FR / Layer 2 NFR | H / M / L |

## Existing feature reuse potential

| Feature | Reuse scope | Notes |
|---|---|---|

## Discovery gaps and unconfirmed items

{Record which sources couldn't be explored and why}
```


### Step 7 — Verify minimum quality threshold

If the following criteria aren't met, confirm with the PM whether to supplement:

| Item | Criterion |
|---|---|
| existing-features.md feature count | 1+ in-operation feature |
| pain-points.md item count | 1+ total |
| overview.md improvement opportunities | 1+ |
| Discovery gap ratio | under 50% of total feature count |

If any item falls short, display a `[Quality shortfall]` warning and record it so the
synthesizer in /draft-req can decide whether to force progression.


### Step 8 — Update session-log.md and open-issues.md

Add to session-log.md:
```markdown
- {date} /product-audit: {N} features / {N} pain points (H: {N}) / {N} discovery gaps
```

Mark the `[DISC-03]` item complete in open-issues.md:
```markdown
- [x] [DISC-03] ~~Own product status assessment incomplete~~ → /product-audit complete
```

Add a P1 item per severity-H pain point.


## Result file list

| File | Content |
|---|---|
| `inputs/discovery/product-audit/existing-features.md` | feature status + classification |
| `inputs/discovery/product-audit/pain-points.md` | pain points by type + severity |
| `inputs/discovery/product-audit/overview.md` | status summary + improvement opportunities + requirements linkage |
| `open-issues.md` | DISC-03 complete / discovery gaps registered as P2 / severity-H registered as P1 |
| `session-log.md` | product-audit completion record |


## Next step

After all 3 Discovery streams are complete:
- `/draft-req {product}`: generate requirements.md draft
