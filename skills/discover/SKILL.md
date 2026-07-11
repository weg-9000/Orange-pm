---
name: discover
description: Creates the full project directory structure and initializes the Discovery phase (Phase -1). The first skill run for a new project.
triggers:
  - "discover"
  - "new project"
  - "init project"
phase: -1
effort: low
model: haiku
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

1. Read `CONTEXT/layer-config.md` and check whether `{product}` conflicts
   with an already-registered PREFIX.
   If it conflicts, instruct the PM to use a different name.

2. Check whether the `PROJECTS/{product}/` directory already exists.
   If it exists, present two options:
   - Continue the existing project (direct to the `SessionStart` flow)
   - Fully reinitialize (proceed only after explicit PM confirmation)


## Execution Steps

### Step 1 — Register PREFIX

Have the PM input the PREFIX value for this project.
Example input: `CLOUD`, `DBAAS`, `BILLING`
If no value is entered, use the uppercase of `{product}` as the default
and confirm with the PM.

Add the following items to `CONTEXT/layer-config.md`:
```markdown
## {product}
- PREFIX: {PREFIX}
- created_at: {UTC timestamp}
- phase: -1
```


### Step 2 — Create the full directory structure

Create the following directories in bulk:

```
PROJECTS/{product}/
├── inputs/
│   └── discovery/
│       ├── competitor/
│       ├── stakeholder/
│       └── product-audit/
├── graph/
├── work-orders/
├── drafts/
└── reports/
```

If the CONTEXT/ directory does not exist, create it as well.


### Step 3 — Initialize core files

**session-log.md**:
```markdown
# {product} Session Log

- PREFIX: {PREFIX}
- created_at: {UTC timestamp}

## Phase History

| Phase | Entry Time | Entry Skill | Notes |
|---|---|---|---|
| -1 (Discovery) | {UTC timestamp} | /discover | Project initialized |
```

**decisions.md**:
```markdown
# {product} Decisions

- PREFIX: {PREFIX}
- created_at: {UTC timestamp}
- freeze: false

> Decision management rule: when the agent detects a decisive statement,
> agreement, or reversal, it auto-registers a candidate row in the table
> (approval column = `⬜`).
> The PM either enters `✅ {pm_id}` directly in the "Approval" cell, or
> bulk-approves with `/dec-approve {DEC-ID,...}`.
> An unapproved DEC has no master-copy effect (INFO). See
> [[CONTEXT/dec-schema]] for column definitions and the approval workflow.

## DEC Ledger (SSoT)

| ID | Date | Domain | Key Decision | Reversal | Approval | Basis (skill/session) |
|---|---|---|---|---|---|---|
| _(none yet)_ | | | | | | |

## Freeze Records

_(none yet)_
```

**Domain ENUM**: 🏗️Infrastructure · 🧭LNB/Navigation · 🎯Screen Interaction · 💰Billing/Commitment · 📊Free tier/SSoT · 🔧Input Controls · 🎨Terminology/Visual · 🛡️Dependency/Resource · 📦Container · 🔗Sharing/Integration · 🤖Auto-recorded

**Approval ENUM**: `⬜` pending / `✅ {pm_id}` approved / `❌ {pm_id}: {reason}` rejected / `🟡 on-hold`

**open-issues.md**:
```markdown
# {product} Open Issues

## P0 — Requires Immediate Resolution

_(none)_

## P1 — Required Discovery Collection Items

- [ ] [DISC-01] Competitor analysis (at least 3 companies) incomplete → run `/research {product}`
- [ ] [DISC-02] Stakeholder requirements gathering incomplete → run `/stakeholder {product}`
- [ ] [DISC-03] Own-product status assessment incomplete → run `/product-audit {product}`
- [ ] [DISC-04] `{PREFIX}-B` common policy document Confluence link not registered

## P2 — Recommended Collection Items

- [ ] [DISC-05] Confirm legal/regulatory constraints
- [ ] [DISC-06] Draft a list of external systems to integrate with
```


### Step 4 — Create Discovery subdirectory templates

**inputs/discovery/competitor/overview.md**:
```markdown
# Competitor Analysis Overview

## Analysis Targets

| Competitor | Analysis Complete | Owner | Notes |
|---|---|---|---|
| (not entered) | | | |

## Feature Comparison Matrix

| Feature Item | Us | Competitor A | Competitor B | Competitor C |
|---|---|---|---|---|
| (not entered) | | | | |

## Key Findings

_(write after analysis is complete)_
```

**inputs/discovery/stakeholder/overview.md**:
```markdown
# Stakeholder Requirements Overview

## Stakeholder List

| Name | Title | Area of Interest | Interview Complete |
|---|---|---|---|
| (not entered) | | | |

## Requirements Summary

_(write after interviews are complete)_

## Open Requirements

_(not yet written)_
```

**inputs/discovery/product-audit/overview.md**:
```markdown
# Own-Product Status Overview

## Existing Feature List

| Feature | Implementation Status | Improvement Needed | Notes |
|---|---|---|---|
| (not entered) | | | |

## Recurring Issues (Pain Points)

| Item | Type (Performance/UX/Security) | Frequency | Priority |
|---|---|---|---|
| (not entered) | | | |

## Technical Constraints

_(not yet written)_
```


### Step 5 — Record completion in session-log.md

```markdown
| -1 (Discovery) | {UTC timestamp} | /discover complete | Directory structure created, templates initialized |
```


## Output Files

| File / Directory | Content |
|---|---|
| `CONTEXT/layer-config.md` | PREFIX registered |
| `PROJECTS/{product}/` | All 8 directories created |
| `session-log.md` | Records Phase -1 entry |
| `decisions.md` | Initial template (freeze: false) |
| `open-issues.md` | 6 required Discovery P1/P2 items |
| `inputs/discovery/competitor/overview.md` | Comparison matrix template |
| `inputs/discovery/stakeholder/overview.md` | Stakeholder list template |
| `inputs/discovery/product-audit/overview.md` | Status assessment template |


## Next Steps

The 3 Discovery skills can be run in parallel:
- `/research {product}`: competitor analysis
- `/stakeholder {product}`: stakeholder requirements gathering
- `/product-audit {product}`: own-product status assessment

After all 3 skills are complete → `/draft-req {product}`
