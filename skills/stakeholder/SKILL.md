---
name: stakeholder
description: Collects and classifies requirements per stakeholder and tags priority. Supports direct interviews, file uploads, team messenger (chat connector), and wiki (wiki connector) as input methods. Completes the stakeholder stream, one of the 3 Discovery streams.
triggers:
  - "stakeholder"
  - "collect requirements"
  - "interview stakeholder"
phase: -1
effort: medium
user-invocable: true
---

## Bootstrap Cache Guard (Improvement F — CONTEXT_OPTIMIZATION.md)

On first entry into a session, load `CONTEXT/_session-bootstrap.md` only once.
If this file has already been read in the same session, do not re-read it.
If the cache is missing or stale, refresh it with the following command before proceeding:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```

This guard replaces reloading the 6 source files layer-config / about-pm / project-rules /
brand-voice / doc-layer-schema / team-members.
Reading the source files directly is allowed only when essential to this skill's core work.

## Precondition Checks

1. Read PREFIX from `CONTEXT/layer-config.md`.
   If missing, instruct the PM to run `/ingest {product}`.

2. Check whether the `inputs/discovery/stakeholder/` directory exists.
   If not, create it.

3. If existing files are present, ask the PM whether to append to them or re-collect from scratch.


## Execution Steps

### Step 1 — Choose input method

Ask the PM to choose a collection method. Multiple selections allowed.

```
Choose a requirements collection method (multiple selections allowed):

  [A] Direct interview  — present a per-stakeholder questionnaire for the PM to fill in
  [B] File upload       — paste meeting notes, requirements docs, or email content
  [C] Team messenger    — auto-collect channel messages via a chat connector (e.g. Slack, Mattermost)
  [D] Wiki document     — load existing requirements docs via a wiki connector (e.g. Confluence, Notion)
```

After selection, run Steps 2–4 in order for each chosen method.


### Step 2A — Direct interview (if selected)

Present the following questionnaire to the PM for each stakeholder.
Repeat if there are multiple stakeholders.

```
Stakeholder info:
  Name / Title / Team:
  Role in the project (requester / decision-maker / end user / operator):

Requirements questions:
  1. What is the most important problem you want this product/feature to solve?
  2. What are the 3 features that must be included?
  3. What features would be nice to have but aren't required?
  4. Are there things that must absolutely not be included?
  5. What are the success criteria? (include quantitative metrics)
  6. Are there any deadlines or constraints?
```

Process the input using the classification criteria in Step 5.


### Step 2B — File upload (if selected)

Ask the PM to paste meeting notes, planning docs, email content, etc. as text.
Automatically extract the following from the pasted text:
- Speaker name or team → classify as stakeholder
- "request" / "need" / "want" → FR candidate
- "performance" / "speed" / "security" → NFR candidate
- "must not" / "cannot" / "restricted" → constraint candidate
- "deadline" / "due date" → schedule constraint

Tag uncertain extractions with `[inferred]` and ask the PM to confirm.


### Step 2C — Team messenger (if selected)

Check for a chat connector (an MCP tool the user has connected — e.g. Slack, Mattermost) via the
CONNECTORS.md detection protocol, and search the last 90 days of messages in the following channels:
- Project-dedicated channel
- Planning/PM channel
- Related team announcement channel

Search keywords: "requirement", "need", "want", "can't", "improve", "inconvenient", product name

Classify stakeholders by speaker and structure the data in Step 5.
If the connector is absent or the connection fails, record `[chat skipped]` and continue.


### Step 2D — Wiki document (if selected)

Check for a wiki connector (an MCP tool the user has connected — e.g. Confluence, Notion) via the
CONNECTORS.md detection protocol, and load project-related requirements documents.
Prefer Approved documents. Extract FR / NFR / constraint items from the documents found.
If the connector is absent or the connection fails, record `[wiki skipped]` and continue.


### Step 3 — Classify requirements and tag priority

Apply the following classification to all collected requirement items:

**Type classification:**

| Type | Definition |
|---|---|
| FR | A function the user performs directly, or that the system provides |
| NFR | Quality requirements such as performance, security, availability, accessibility |
| CON | Technical, business, or legal constraints |
| OOS | Out of scope for this iteration |

**Priority classification (MoSCoW):**

| Priority | Definition |
|---|---|
| Must | Product cannot ship without it |
| Should | Important but can ship without it |
| Could | Nice to have |
| Wont | Excluded from this release |

Tag uncertain classifications with `[unclassified]` and register them
in open-issues.md as P2.


### Step 4 — Detect conflicting requirements

Detect conflicts between stakeholders regarding the same feature or target.

**Conflict types:**

| Type | Definition |
|---|---|
| Direct conflict | Team A requests X, Team B opposes X |
| Priority conflict | Must vs. Could on the same item |
| Resource conflict | Mutually exclusive feature requests |

Register detected conflicts in open-issues.md:
- Direct conflict → P1
- Priority conflict → P2
- Resource conflict → P1

Format:
```markdown
- [ ] [STK-NN] Conflict: {feature name} — {Team A} Must vs {Team B} Wont. Decision needed.
```


### Step 5 — Generate a file per stakeholder

Generate `inputs/discovery/stakeholder/{team-name}.md` for each stakeholder:

```markdown
# {Stakeholder name / team name} Requirements

**Role**: {requester / decision-maker / end user / operator}
**Collection method**: {interview / file / team messenger (chat) / wiki}
**Collected as of**: {date}

## FR Requirements

| ID | Content | Priority | Notes |
|---|---|---|---|
| STK-{NN}-FR-01 | {content} | Must / Should / Could | |

## NFR Requirements

| ID | Content | Priority | Notes |
|---|---|---|---|

## Constraints

| ID | Content | Type (technical / business / legal) |
|---|---|---|

## Success Criteria

{success criteria defined by the stakeholder}

## Out of Scope Items

{items explicitly excluded from this release}
```


### Step 6 — Write overview.md

Write this by cross-analyzing all stakeholder files:

```markdown
# Stakeholder Requirements Summary — {product}

> Collected as of: {date}
> Stakeholders: {N} people / {N} teams

## Stakeholder List

| Name / Team | Role | Must FR count | Conflicting items |
|---|---|---|---|

## Consolidated Must Requirements

| Item | Requesting stakeholder | Type |
|---|---|---|

## Conflicting Requirements Matrix

| Item | {Stakeholder A} | {Stakeholder B} | Conflict type |
|---|---|---|---|

## Unclassified Items

| Item | Stakeholder | Reason |
|---|---|---|
```


### Step 7 — Check quality thresholds

| Item | Criterion |
|---|---|
| Number of stakeholder files | 2 or more |
| Number of FR items (including Must) | 5 or more |
| Number of Must items | 1 or more |
| Unclassified ratio | Less than 30% of all items |

If any threshold is not met, display a `[quality not met]` warning and
record it so the synthesizer in /draft-req can decide whether to force-proceed.


### Step 8 — Update session-log.md and open-issues.md

Add to session-log.md:
```markdown
- {date} /stakeholder: {N} stakeholders / {N} FR / {N} conflicts / {N} unclassified
```

Mark the `[DISC-02]` item as done in open-issues.md:
```markdown
- [x] [DISC-02] ~~Stakeholder requirements collection incomplete~~ → /stakeholder complete
```


## Result File List

| File | Content |
|---|---|
| `inputs/discovery/stakeholder/{team-name}.md` | Requirements per stakeholder |
| `inputs/discovery/stakeholder/overview.md` | Consolidated summary + conflict matrix |
| `open-issues.md` | DISC-02 done / conflicts registered as P1/P2 / unclassified as P2 |
| `session-log.md` | stakeholder completion recorded |


## Next Steps

After all 3 Discovery streams are complete:
- `/draft-req {product}`: generate the requirements.md draft

Skills that can run in parallel:
- `/research {product}`
- `/product-audit {product}`
