---
name: research
description: Performs competitor analysis and generates a comparison matrix + benchmarking insights. Completes the competitor stream of the 3 Discovery streams.
triggers:
  - "research"
  - "competitor analysis"
  - "market research"
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

2. Check whether the `inputs/discovery/competitor/` directory exists.
   If not, create it.

3. If an existing competitor file is present, confirm with the PM before overwriting.


## Execution steps

### Step 1 — Confirm the PM's research scope

Confirm the following items with the PM:

```
1. List of competitors to analyze (2 minimum, 5 recommended maximum)
   e.g. "Kakao T, Socar, Green Car"

2. Research focus areas (multiple selection)
   [ ] Feature composition (Core Feature Set)
   [ ] Pricing Model
   [ ] UX / user flow
   [ ] Technical constraints or integrations
   [ ] Customer complaints (reviews / community)

3. Research depth
   [ ] Quick scan (key characteristics only)
   [ ] Deep analysis (customer reviews + detailed comparison)
```

Do not start research without input.


### Step 2 — Launch the researcher agent

Pass the following context to the researcher agent:

```
Analysis targets: {competitor list entered by the PM}
Focus areas: {areas selected by the PM}
Research depth: {selected value}
Product context: {product} / PREFIX: {PREFIX}

Information collection source priority (connectors confirmed via the CONNECTORS.md
detection protocol; if absent, record `[{capability} skipped]` for that source and
skip it):
  1. wiki connector — internal competitor material (e.g. Confluence·Notion)
  2. web search (official sites, blogs, app-store reviews)
  3. chat connector — existing team analysis notes (e.g. Slack·Mattermost)

Output targets:
  - inputs/discovery/competitor/{name}.md (per competitor)
  - inputs/discovery/competitor/overview.md (comparison matrix)
  - inputs/research.md (benchmarking insights)
```

The agent generates a file with the Step 3 structure for each competitor.


### Step 3 — Generate per-competitor analysis files

For each competitor, generate `inputs/discovery/competitor/{name}.md`.

**File format:**
```markdown
# {Competitor name} Analysis

> Analysis baseline date: {date}
> Source: {internal wiki URL or web link}

## Product positioning

{1~2 sentences on core value proposition}

## Key feature list

| Feature | Description | Comparison to our product |
|---|---|---|
| {feature} | {description} | same / advantage / disadvantage / absent |

## Pricing policy

{pricing structure summary. Mark [unconfirmed] if unable to confirm}

## UX characteristics

{notable screen flows and usability characteristics}

## Customer complaints / weaknesses

| Complaint | Source | Severity (H/M/L) |
|---|---|---|

## Technical constraints or integrations

{known technical constraints or external integration characteristics}

## Implications

{2~3 key insights drawn from this competitor's analysis}
```

Mark items that couldn't be confirmed as `[unconfirmed]`. If the `[unconfirmed]` ratio is 50%
or higher, add a `[insufficient information — low confidence]` warning to that competitor's
file.


### Step 4 — Write the overview.md comparison matrix

Read all competitor files and write a comparison matrix.

**File format:**
```markdown
# Competitor Comparison Matrix — {product}

> Baseline date: {date}
> Analysis targets: {competitor list}

## Key feature comparison

| Feature | {us} | {Competitor A} | {Competitor B} | {Competitor C} |
|---|---|---|---|---|
| {feature name} | O / X / [unconfirmed] | ... |

## Pricing policy comparison

| Item | {us} | {Competitor A} | {Competitor B} |
|---|---|---|---|

## UX flow comparison

| Item | {us} | {Competitor A} | {Competitor B} |
|---|---|---|---|

## Market gaps (areas no competitor supports)

| Area | Description |
|---|---|

## Areas where we can differentiate

| Area | Description | Priority (H/M/L) |
|---|---|---|
```

If the comparison matrix has fewer than 3 rows, treat it as below the quality threshold.


### Step 5 — Write research.md benchmarking insights

Write based on the cross-analysis of overview.md.

**File format:**
```markdown
# Benchmarking Insights — {product}

> Based on competitor analysis. Referenced by the synthesizer during /draft-req.

## Competitive landscape summary

{2~3 sentences on overall market characteristics}

## Feature gap analysis

| Gap type | Content | Expected requirements layer |
|---|---|---|
| Feature we lack | {feature competitors have that we don't} | Layer 1 FR |
| Feature where we're weak | {feature where we're behind competitors} | Layer 1 FR / Layer 2 NFR |
| Market gap opportunity | {area no competitor supports} | Layer 1 FR |

## Improvement items based on customer complaints

{differentiation points derived from competitors' customer complaints}

## Expected FR mapping items

> This section is connected by the synthesizer in /draft-req to requirements.md's FR items.

| Insight | Expected FR item | Priority |
|---|---|---|
```


### Step 6 — Verify quality threshold

| Item | Criterion |
|---|---|
| Competitor file count | 2 or more |
| Comparison matrix rows | 3 or more |
| `[unconfirmed]` cell ratio | under 50% of all cells |
| Market gap items | 1 or more |
| Expected FR mapping items | 1 or more |

If any item falls short, display a `[Quality shortfall]` warning and record it so the
synthesizer in /draft-req can decide whether to force progression.


### Step 7 — Update session-log.md and open-issues.md

Add to session-log.md:
```markdown
- {date} /research: {N} competitors analyzed / {N} matrix rows / {N} market gaps
```

Mark the `[DISC-01]` item complete in open-issues.md:
```markdown
- [x] [DISC-01] ~~Competitor analysis incomplete~~ → /research complete
```

If any competitor has a high `[unconfirmed]` ratio, register it in open-issues.md as P2.


## Result file list

| File | Content |
|---|---|
| `inputs/discovery/competitor/{name}.md` | per-competitor analysis file |
| `inputs/discovery/competitor/overview.md` | comparison matrix + market gaps |
| `inputs/research.md` | benchmarking insights + expected FR mapping |
| `open-issues.md` | DISC-01 complete / insufficient-info items registered as P2 |
| `session-log.md` | research completion record |


## Next step

After all 3 Discovery streams are complete:
- `/draft-req {product}`: generate requirements.md draft

Skills that can run in parallel:
- `/stakeholder {product}`
- `/product-audit {product}`
