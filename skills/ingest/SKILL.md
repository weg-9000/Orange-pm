---
name: ingest
description: Scaffolds the project directory and initializes template files. Sets up layer-config.md and validates the quality of existing Discovery artifacts. Invoke this skill on a project's first run or when recovering the project structure.
triggers:
  - "ingest"
  - "init project"
  - "setup project"
phase: 0
effort: low
model: haiku
user-invocable: true
---

## Bootstrap cache guard (Improvement F — CONTEXT_OPTIMIZATION.md)

Load `CONTEXT/_session-bootstrap.md` only once per session, on first entry.
Do not re-read it if it was already read in the same session.
If the cache is missing or stale, refresh it with the following command before proceeding:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```

This guard replaces reloading the 6 source files layer-config / about-pm / project-rules / brand-voice /
doc-layer-schema / team-members. Reading the source files directly is allowed only when it is essential
to this skill's core task.

## Prerequisite checks

1. If the `{product}` argument is empty, ask for a project name.
   Only lowercase letters and hyphens are allowed (e.g. `orange-cloud`).

2. If `PROJECTS/{product}/` already exists, confirm with the PM whether to
   re-initialize (keep existing files + fill in missing structure) or
   initialize fresh (regenerate everything).
   On re-initialization, existing files are not overwritten.


## Execution steps

### Step 1 — Create the directory structure

Create the following directories (skip any that already exist):

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

CONTEXT/
└── .template-cache/
```


### Step 2 — Initialize template files

Create the following files only if they do not already exist (never overwrite existing files):

**session-log.md:**
```markdown
# session-log — {product}

| Phase | Timestamp | Skill run | Summary |
|---|---|---|---|
| Init | {UTC timestamp} | /ingest | Project initialized |
```

**open-issues.md:**
```markdown
# open-issues — {product}

## P0 (Blocker)

## P1 (High priority)

- [ ] [DISC-01] Competitor analysis not yet complete
- [ ] [DISC-02] Stakeholder requirements gathering not yet complete
- [ ] [DISC-03] Own-product status assessment not yet complete

## P2 (Normal)

## P3 (Low)

## Completed
```

**decisions.md:**
```markdown
# {product} Decisions

- PREFIX: {PREFIX}
- created_at: {UTC timestamp}
- freeze: false

> Decision management rule: when the agent detects decisive utterances, agreement, or reversal,
> it auto-registers a candidate row in the table (Approval column = `⬜`).
> The PM either enters `✅ {pm_id}` directly in the "Approval" cell, or bulk-approves with
> `/dec-approve {DEC-ID,...}`.
> An unapproved DEC has no canonical effect (INFO). See [[CONTEXT/dec-schema]] for column
> definitions and the approval workflow.

## DEC ledger (SSoT)

| ID | Date | Domain | Key Decision | Reversal | Approval | Basis (skill/session) |
|---|---|---|---|---|---|---|
| _(none yet)_ | | | | | | |

## Freeze Records

_(none yet)_
```

**Domain ENUM**: 🏗️Infrastructure · 🧭LNB/Navigation · 🎯Screen interaction · 💰Billing/Commitment · 📊Free tier/SSoT · 🔧Input controls · 🎨Terminology/Visual · 🛡️Dependency/Resources · 📦Container · 🔗Sharing/Integration · 🤖Auto-recorded

**Approval ENUM**: `⬜` pending / `✅ {pm_id}` approved / `❌ {pm_id}: {reason}` rejected / `🟡` on-hold


### Step 3 — Configure CONTEXT/layer-config.md

If `CONTEXT/layer-config.md` exists and ACTIVE_PREFIX (or PREFIX) is already filled in,
use the existing value. If empty, ask the PM for the following items:

```
1. PREFIXES (list of product-line id+label to work on, single is fine. e.g. G2/private, PG2/public)
2. ACTIVE_PREFIX (the target for the current session — one of PREFIXES)
3. {ACTIVE_PREFIX}-A Confluence URL (vocabulary / policy principles)
4. {ACTIVE_PREFIX}-B Confluence URL (common policy)
5. {ACTIVE_PREFIX}-C Confluence URL (optional layer, N/A if none)
6. brand-voice.md path or Confluence URL (N/A if none)
```

Generate `CONTEXT/layer-config.md` from the values entered:

```markdown
# layer-config

PREFIXES:
  - id: {ACTIVE_PREFIX}
    label: {label}
ACTIVE_PREFIX: {ACTIVE_PREFIX}
PREFIX: {ACTIVE_PREFIX}   # legacy compatibility — kept in sync with ACTIVE_PREFIX

{ACTIVE_PREFIX}-A URL: {input value}
{ACTIVE_PREFIX}-B URL: {input value}
{ACTIVE_PREFIX}-C URL: {input value or N/A}

brand-voice: {input value or N/A}
```

If the {PREFIX}-A / {PREFIX}-B URL is N/A, register it in open-issues.md as P0 and instruct that
it must be entered before running `/graph-gen`.


### Step 4 — Validate existing Discovery artifacts

Perform quality validation only for files that exist.
If a file does not exist, mark that item as "not yet generated" and skip it.

**Validate inputs/requirements.md:**

| Item | Criterion | Result |
|---|---|---|
| Layer 1 FR | Section exists | exists / missing |
| Layer 2 NFR | Section exists | exists / missing |
| Layer 4 actors | Section exists | exists / missing |
| Layer 5 external integrations | Section exists | exists / missing |
| Number of FR items | 10 or more | {N} |

**Validate inputs/research.md:**

| Item | Criterion | Result |
|---|---|---|
| Competitor analysis section | Exists | exists / missing |
| FR mapping | Exists | exists / missing |

**Validate discovery/ streams:**

| Stream | File count | overview.md |
|---|---|---|
| competitor/ | {N} | exists / missing |
| stakeholder/ | {N} | exists / missing |
| product-audit/ | {N} | exists / missing |


### Step 5 — Report initial status and next-step guidance

Print the validation results in the following format:

```
Project initialization complete: {product}

  Directory structure: complete
  PREFIX:         {PREFIX}
  {PREFIX}-A:     {registered / not registered (P0)}
  {PREFIX}-B:     {registered / not registered (P0)}
  {PREFIX}-C:     {registered / N/A}
  brand-voice:    {registered / N/A}

Discovery status:
  requirements.md:   {complete / partial / not generated}
  research.md:       {exists / not generated}
  competitor/:       {N} files
  stakeholder/:      {N} files
  product-audit/:    {N} files

Recommended next step:
  {no requirements.md}   → start with one of /research, /stakeholder, /product-audit
  {requirements.md complete} → /draft-req {product}
  {draft-req complete}       → /graph-gen {product}
```


### Step 6 — Update session-log.md

Update the Init row in session-log.md to its final state:
```markdown
| Init | {UTC timestamp} | /ingest | Scaffolding complete / PREFIX: {PREFIX} / requirements: {status} |
```


## Result file list

| File | Content |
|---|---|
| `PROJECTS/{product}/` | Full directory structure |
| `PROJECTS/{product}/session-log.md` | Init record |
| `PROJECTS/{product}/open-issues.md` | Initial DISC-01–03 registration |
| `PROJECTS/{product}/decisions.md` | Initialization record |
| `CONTEXT/layer-config.md` | PREFIX + Confluence URL + brand-voice |
| `CONTEXT/.template-cache/` | Empty cache directory (actual cache files are generated by `/graph-gen`) |


## Next steps

The discovery skills can be run in any order. Once all three are complete, run `/draft-req`.

> ⚠️ Saving the {PREFIX}-A/B/C cache files under `CONTEXT/.template-cache/` is handled by
> `/graph-gen`. `/ingest` only prepares the directory structure; cache-file generation happens
> in `/graph-gen` step 2.

- `/research {product}`: competitor analysis
- `/stakeholder {product}`: stakeholder requirements gathering
- `/product-audit {product}`: own-product status assessment
