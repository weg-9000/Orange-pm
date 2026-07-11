---
name: init-hub
description: Initializes the Planning-Agent-Hub working directory structure or diagnoses its current state. This is the first skill that must be run after the plugin is installed. If run from the wrong working directory, it guides the user to the correct setup.
triggers:
  - "init-hub"
  - "initialize hub"
  - "initial setup"
  - "setup hub"
  - "initialize hub"
phase: init
effort: low
model: haiku
user-invocable: true
---

## Step 1 — Verify the working directory

Check for the presence of the following items in the current working directory.

**Hub identification marker check:**

| Marker | Path | Check |
|---|---|---|
| CONTEXT directory | `./CONTEXT/` | check |
| PROJECTS directory | `./PROJECTS/` | check |
| layer-config | `./CONTEXT/layer-config.md` | check |
| CLAUDE.md | `./.claude/CLAUDE.md` | check |

**Judgment criteria:**

- 3 or more markers present → running inside the Hub directory (normal) → proceed to step 2
- 1–2 markers present → partially initialized → fill in the missing items in step 2
- 0 markers present and the current directory name is `orange-pm-plugin` or an internal plugin
  path such as `skills/` → print the **error guidance** and exit


## Step 1-E — Wrong-working-directory guidance (error path)

If 0 markers are present and the directory is judged not to be the Hub, print the following:

```
⚠️ Wrong working directory.

Current location: {absolute path of current directory}

The orange-pm plugin must be run with the Planning-Agent-Hub directory
set as the working directory.

Correct way to run it:
  1. Quit Claude Code.
  2. Reopen Claude Code from the Planning-Agent-Hub directory.
     - VS Code:     code /path/to/Planning-Agent-Hub
     - Terminal:    cd /path/to/Planning-Agent-Hub && claude
     - Claude app:  File → Open Folder → select Planning-Agent-Hub
  3. Run /init-hub again.

If you don't have a Planning-Agent-Hub directory yet:
  - Create an empty directory and open Claude Code inside it —
    /init-hub will auto-generate the full structure.
```

Exit. Do not run the subsequent steps.


## Step 2 — Diagnose Hub structure

Check the current initialization state of the Hub.

**CONTEXT/ item check:**

| File | Check | Notes |
|---|---|---|
| `CONTEXT/layer-config.md` | check | PREFIX configuration |
| `CONTEXT/about-pm.md` | check | PM profile |
| `CONTEXT/project-rules.md` | check | Planning principles |
| `CONTEXT/brand-voice.md` | check | Document tone |
| `CONTEXT/team-members.md` | check | Stakeholders |
| `CONTEXT/ssot-boundary.yml` | check | SSoT boundary (render --check-ssot) |
| `CONTEXT/connectors.md` | check | External integration mapping (optional) |
| `CONTEXT/gates/discovery-exit-gate.md` | check | Phase gate |
| `CONTEXT/gates/policy-entry-gate.md` | check | Phase gate |
| `CONTEXT/gates/graph-exit-gate.md` | check | Phase gate |
| `CONTEXT/gates/draft-complete-gate.md` | check | Phase gate |
| `CONTEXT/gates/integration-exit-gate.md` | check | Phase gate |

**templates/ item check:**

| File | Check | Notes |
|---|---|---|
| `templates/graph-schema.json` | check | Graph schema |
| `templates/work-order-template.md` | check | WO format |

**PROJECTS/ item check:**

| Item | Content |
|---|---|
| Number of registered projects | Number of subdirectories under `PROJECTS/` |
| Phase of each project | Phase of the last row in `session-log.md` |


## Step 3 — Create missing structure

Create the items found to be missing in step 2.
Never overwrite files that already exist.

### 3-A. Create directories

Create missing directories:

```
CONTEXT/
└── gates/
PROJECTS/
templates/
.claude/
```

### 3-B. Create CONTEXT files

**`CONTEXT/layer-config.md`** (only if missing):

```markdown
# Layer Architecture Configuration

## Department Prefix configuration (multi-PREFIX)
# Each PREFIX holds its own fully independent A/B/C. ACTIVE_PREFIX is the current work target.
PREFIXES:
  - id: (needs configuration)
    label: (needs configuration)
# Example additional department/product lines: PA(product line A) / PB(product line B) / SaaS / OSS

ACTIVE_PREFIX: (needs configuration)

# Legacy compatibility: for older tools that only read a single PREFIX. Kept in sync with ACTIVE_PREFIX.
PREFIX: (needs configuration)

## External integration
# Declare mappings for external integrations (wiki, messenger, design tools, etc.) in CONTEXT/connectors.md.
# (The entire workflow still runs locally even without any integration — see the CONNECTORS.md contract)

## {PREFIX}-A: Common definitions
| doc_id | Document title | Status |
|---|---|---|
| {PREFIX}-A-001 | Glossary | Draft |
| {PREFIX}-A-002 | Status reference | Draft |
| {PREFIX}-A-003 | Error code definitions | Draft |
| {PREFIX}-A-004 | Naming conventions | Draft |

## {PREFIX}-B: Common policy
| doc_id | Document title | Status |
|---|---|---|
| {PREFIX}-B-001 | Account/group/project policy | Draft |
| {PREFIX}-B-002 | Service subscription/cancellation policy | Draft |
| {PREFIX}-B-003 | Resource/limit policy | Draft |
| {PREFIX}-B-004 | Product default policy | Draft |
| {PREFIX}-B-005 | Fee calculation policy | Draft |
| {PREFIX}-B-006 | Billing statement policy | Draft |
| {PREFIX}-B-007 | Payment method policy | Draft |
| {PREFIX}-B-008 | Discount plans | Draft |

## {PREFIX}-C: Reusable blocks
| doc_id | Document title | Status |
|---|---|---|
| {PREFIX}-C-001 | LNB common module | Draft |
| {PREFIX}-C-002 | Email/SMS delivery module | Draft |
| {PREFIX}-C-003 | Login page module | Draft |
| {PREFIX}-C-004 | OTP common auth module | Draft |

## Weighting rules
Approved: 1.0 / Draft: 0.3 / Deprecated: 0 (excluded from index)

## doc_id generation rule
Format: {PREFIX}-C-{PRODUCT_CODE}-{SEQ:003d}
Example: {PREFIX}-C-DBAAS-001
```

If `layer-config.md` was newly created, ask the PM for the following items:
1. PREFIXES — the list of product lines to work on (id + label). If single, just 1. E.g. `PA/product-line-A`, `PB/product-line-B`
2. ACTIVE_PREFIX — the current session's work target (one of PREFIXES). Set the PREFIX line to match.
3. If using external system integration — the capability mapping in `CONTEXT/connectors.md` (optional)

**`CONTEXT/about-pm.md`** (only if missing):

```markdown
# PM Profile

## Basic information
- Name: (input needed)
- Affiliation: (input needed)
- Role: Product Manager

## Working style
- (input needed)

## Preferences
- (input needed)
```

**`CONTEXT/project-rules.md`** (only if missing):

```markdown
# Planning Principles

## Version-management principle
- All policy documents progress from v0.x (draft) → v1.0 (frozen).
- If changed after v1.0 is frozen, record the reason in decisions.md.

## Decision principle
- Items recorded in decisions.md are not reversed.
- If a reversal is needed, add a new entry.

## Synchronization principle
- Always sync the wiki (wiki connector) with local files after running /cr.
- Complete stakeholder notification on the team messenger (chat connector) after running /su.
```

**`CONTEXT/brand-voice.md`** (only if missing):

```markdown
# Document Tone Standard

## Basic principles
- Write concisely and clearly.
- Base technical terminology on the {PREFIX}-A-001 glossary.
- Prefer active voice over passive voice.

## Prohibited expressions
- (input needed)

## Recommended expressions
- (input needed)
```

**`CONTEXT/team-members.md`** (only if missing):

```markdown
# Stakeholder List

| Name | Affiliation / Role | Assigned project | Contact |
|---|---|---|---|
| (input needed) | | | |
```

**`CONTEXT/ssot-boundary.yml`** (only if missing):

```yaml
# SSoT boundary declaration (Single Source of Truth boundary)
#
# Declares which doc type owns the "source of truth (SSoT)" for which values.
# render --check-ssot reads this file and blocks a product Delta ({PREFIX}-C)
# as an SSoT violation if it redefines a value owned by another doc type.
#
# - design_tokens: SSoT for design tokens such as HEX/px (usually the screen-design doc/D2·D3)
# - policy_values: SSoT for limit/fee/policy values (usually the common policy {PREFIX}-B)
# If the value is empty or the file is missing, --check-ssot only warns and passes (graceful).

design_tokens:
  owner: ""        # e.g. D2 (screen design spec) — source of HEX/px design tokens
  patterns:        # value patterns to treat as SSoT (regex, optional)
    - "#[0-9A-Fa-f]{6}"
    - "\\d+px"

policy_values:
  owner: ""        # e.g. {PREFIX}-B (common policy) — source of limit/fee and other policy values
  patterns: []
```

**`CONTEXT/connectors.md`** (only if missing):

```markdown
# Connector Mapping

External system integration auto-detects and uses the MCP servers/connectors the user has
connected to Claude Code. If multiple tools share the same capability, or you want to force a
specific tool, declare it in the table below.
Leave it blank for auto-detection; if no tool is present, that step is skipped and the workflow
proceeds locally.
(Contract details: the plugin's CONNECTORS.md)

| capability | tool/server name | notes |
|---|---|---|
| wiki   | | Publish-target space/parent page: |
| chat   | | Default channel: |
| design | | |
| repo   | | |
| tasks  | | |
```

### 3-C. Create gates files

**`CONTEXT/gates/discovery-exit-gate.md`** (only if missing):

```markdown
# Discovery Exit Gate

Checked at: /research · /stakeholder · /product-audit complete → permits running /draft-req

| Item | Criterion |
|---|---|
| inputs/discovery/competitor/ | 1+ file + 3+ matrix rows in overview.md |
| inputs/discovery/stakeholder/ | 1+ file + 2+ stakeholders / 5+ requirements in overview.md |
| inputs/discovery/product-audit/ | 1+ file |
| open-issues.md P0 | 0 |
```

**`CONTEXT/gates/policy-entry-gate.md`** (only if missing):

```markdown
# Policy Entry Gate

Checked at: /draft-req complete → permits running /graph-gen

| Item | Criterion |
|---|---|
| requirements.md Layer 1 (FR) | 10 or more |
| requirements.md Layer 2 (NFR) | 5 or more |
| requirements.md Layer 4 (actors) | definition complete |
| requirements.md Layer 5 (external integration) | list exists |
| Whether FR items can be split per screen | fully confirmed |
| {PREFIX}-A/B URL | registered in layer-config.md |
| open-issues.md P0 | 0 |
```

**`CONTEXT/gates/graph-exit-gate.md`** (only if missing):

```markdown
# Graph Exit Gate

Checked at: /graph-gen complete → permits running /fanout

| Item | Criterion |
|---|---|
| graph/graph.json | file exists |
| graph/screen-list.md | file exists |
| validate_graph.py result | PASS record exists (session-log or decisions) |
| PM approval record | /graph-gen completion recorded in decisions.md |
| open-issues.md P0 | 0 |
```

**`CONTEXT/gates/draft-complete-gate.md`** (only if missing):

```markdown
# Draft Complete Gate

Checked at: all Phase 2 WO drafts complete → permits running /integrate

| Item | Criterion |
|---|---|
| drafts/ policy WO | a draft file exists for every policy WO in index.md |
| drafts/ screen WO | a draft file exists for every screen WO in index.md |
| open-issues.md P0 | 0 |
```

**`CONTEXT/gates/integration-exit-gate.md`** (only if missing):

```markdown
# Integration Exit Gate

Checked at: /integrate PASS → permits running /confirm

| Item | Criterion |
|---|---|
| reports/integration-summary.md | file exists |
| BLOCK count | 0 |
| decisions.md Phase 4 permission record | exists |
| open-issues.md P0 | 0 |
```

### 3-D. Create templates/ files

**`templates/graph-schema.json`** (only if missing):

> **Consistency caution (2026-06-08 H5 audit):** This schema **must match** `validate_graph.py`'s
> actual validation contract. The canonical graph.json is the envelope
> `{ "graph": { "metadata", "nodes": {object}, "edges": [array] } }`, where `nodes` is a
> **dictionary** of node name → node object (not an array), `node_type` is `policy | screen`,
> and edges use `source`/`target`/`type` (+ optional `source_section`/`target_section`). The
> schema below follows that shape. (validate_graph.py: `VALID_NODE_TYPES`·`VALID_EDGE_TYPES`·
> `_minimal_schema_check`)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "PM Planning Graph Schema",
  "type": "object",
  "required": ["graph"],
  "properties": {
    "graph": {
      "type": "object",
      "required": ["metadata", "nodes", "edges"],
      "properties": {
        "metadata": { "type": "object" },
        "nodes": {
          "type": "object",
          "description": "Mapping of node name → node object (not an array)",
          "additionalProperties": {
            "type": "object",
            "properties": {
              "node_type": { "type": "string", "enum": ["policy", "screen"] },
              "sections": {
                "type": "object",
                "description": "policy nodes: section ID → {title, summary, ...}. screen nodes do not have this.",
                "additionalProperties": { "type": "object" }
              },
              "inherits_from": { "type": "array", "items": { "type": "string" } },
              "fr_refs": { "type": "array", "items": { "type": "string" } },
              "capability": { "type": "string" },
              "cluster_id": { "type": "string" },
              "screen_name": { "type": "string" },
              "purpose": { "type": "string" },
              "req_id": { "type": "string" }
            }
          }
        },
        "edges": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["source", "target", "type"],
            "properties": {
              "source": { "type": "string" },
              "target": { "type": "string" },
              "source_section": { "type": "string" },
              "target_section": { "type": "string" },
              "type": {
                "type": "string",
                "enum": [
                  "prerequisite", "bidirectional-ref", "duplicate-definition", "feature-link",
                  "event-definition", "security-standard", "implements",
                  "term-standard", "ux-standard", "billing-target", "ops-procedure"
                ]
              }
            }
          }
        }
      }
    }
  }
}
```

**`templates/work-order-template.md`** (only if missing):

```markdown
# Work Order — {PREFIX}-C-{PRODUCT}-{SEQ}

## Section 0. Document identification

| Item | Value |
|---|---|
| doc_id | {PREFIX}-C-{PRODUCT}-{SEQ} |
| Type | policy / screen |
| Status | Draft |
| Created | {UTC date} |

### 0-1. Inheritance relationships

| Relationship type | Target doc_id |
|---|---|
| inherits_from | |
| includes | |

### 0-2. Delta scope

Describe only the exceptions that differ from the common policy ({PREFIX}-B).
If there are no exceptions, write "default policy fully applied" as a single line.

## Section 1. Scope and purpose
## Section 2. Input conditions
## Section 3. Contract terms
## Section 4. Task items
- [ ]
## Section 5. Validation criteria
## Section 6. Prohibited items
```

### 3-E. Create `.claude/CLAUDE.md`

**`.claude/CLAUDE.md`** (only if missing):

```markdown
# Global Instructions

## Role declaration
This agent is a partner to the PM planning team.
Its role is to author documents at the {PREFIX}-C (product spec) layer.
{PREFIX}-A/B/C upper-layer documents are read-only and never modified.

## decisions.md absolute rule
Never propose modifications to items recorded in decisions.md.
If a reversal is needed, the PM deletes it directly and gives new instructions.

## SSoT principle
Never rewrite content that already exists in {PREFIX}-B within {PREFIX}-C.
Report any duplicate definitions to the PM immediately.

---
# Folder Instructions

## Work-entry rule
At session start, read files in the following order.
1. CONTEXT/layer-config.md       → extract the PREFIX value
2. CONTEXT/about-pm.md           → load the PM's working style
3. CONTEXT/project-rules.md      → load planning principles
4. CONTEXT/brand-voice.md        → load the document tone standard
5. CONTEXT/team-members.md       → load the stakeholder list
6. CONTEXT/connectors.md         → load external integration mapping (if present)
7. PROJECTS/{project name}/session-log.md, decisions.md, open-issues.md

## Skills allowed per Phase
Phase -1: /discover /research /stakeholder /product-audit /draft-req
Phase  0: /ingest /graph-gen
Phase  1: /fanout
Phase  2: /explore /write /flow /screen-detail /review /render
Phase  3: /integrate
Phase  4: /confirm → /cr → /su
Anytime: /se /sc /lc /plan-audit /render /init-hub

## Operating rules
1. Confirm PREFIX first
2. Comply with SSoT
3. Delta principle — describe only exceptions to common policy
4. decisions.md absolute rule
5. 3-round convergence principle
6. Session-unit principle — 1 Work Order = 1 session, run /sc after completion
```


## Step 4 — PREFIX configuration guidance

If PREFIX in `CONTEXT/layer-config.md` is `(needs configuration)`, ask the PM for input:

1. **PREFIX** — department/product-line code (e.g. `PA`, `PB`, `S1`)


## Step 5 — Report external integration (connector) status

Check the MCP tools available in the current session per capability and print the result
(detection basis: the plugin's CONNECTORS.md contract):

```
External integration status (optional — the entire workflow still runs locally without them)

  wiki   (document publish/query)   : {detected tool or "not connected"}
  chat   (messenger query/notify)   : {detected tool or "not connected"}
  design (design-file query)        : {detected tool or "not connected"}
  repo   (MR/issues)                : {detected tool or "not connected"}
  tasks  (schedule/tasks)           : {detected tool or "not connected"}

To add an integration, connect an MCP server to Claude Code:
  claude mcp add <name> ...      (or Claude settings → Connectors)
To force a specific tool, declare a mapping in CONTEXT/connectors.md.

Impact when not connected: /cr (remote publish) and /su stop with guidance;
other skills proceed by simply skipping that source lookup.
```


## Step 5-B — Generate context cache (Improvements A, B, F — CONTEXT_OPTIMIZATION.md)

To prevent every skill from repeatedly reloading the same context on first session entry,
generate the following caches. This only runs once PREFIX is configured, and the cache is
namespaced (`{PREFIX}-...`) by ACTIVE_PREFIX.

```bash
# F. Merge the 6 CONTEXT files → the unified _session-bootstrap.md
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .

# A. {ACTIVE_PREFIX}-B common-policy summary cache (.template-cache/{PREFIX}-b-summary.md)
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_cache.py --hub-root .

# B. {ACTIVE_PREFIX}-B heading index (.template-cache/{PREFIX}-b-headings-index.json)
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_b_index.py --hub-root .

# A-idx. {ACTIVE_PREFIX}-A term reverse index (.template-cache/{PREFIX}-a-terms-index.json)
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_a_index.py --hub-root .

# C-idx. Cross-PREFIX C service master index (.template-cache/c-master-index.json)
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_c_index.py --hub-root .
```

Each script is idempotent. Only caches older (by mtime) than their source are regenerated, so
repeated runs cost almost nothing. If `reference-docs/{ACTIVE_PREFIX}/B/` is empty, A and B are
skipped with a warning and execution continues. When switching PREFIX, change `ACTIVE_PREFIX`
and then regenerate the caches above.
(For backward compatibility, `build_b_*` also writes non-namespaced mirrors
`B-summary.md`·`B-headings-index.json`.)

Generation result:

| Cache file | Purpose |
|---|---|
| `CONTEXT/_session-bootstrap.md` | Single per-session context-load entry point for every skill |
| `CONTEXT/.template-cache/B-summary.md` | Cache-first {PREFIX}-B load for `/write`, `/flow`, `/integrate` |
| `CONTEXT/.template-cache/B-headings-index.json` | Per-section excerpt loading (line_start/line_end) |

> These caches live under `.template-cache/` and it is recommended to exclude them from git
> tracking. If needed, add `Planning-Agent-Hub/CONTEXT/.template-cache/` to `.gitignore`.


## Step 6 — Print final diagnosis

```
Planning-Agent-Hub initialization complete

  Directory:     {current working directory}
  PREFIX:        {PREFIX value or "(needs configuration)"}
  Connectors:    {list of connected capabilities or "none (local only)"}

  CONTEXT files:
    layer-config.md        {existing / newly created}
    about-pm.md            {existing / newly created}
    project-rules.md       {existing / newly created}
    brand-voice.md         {existing / newly created}
    team-members.md        {existing / newly created}
    ssot-boundary.yml      {existing / newly created}
    connectors.md          {existing / newly created}
    gates/ (5 files)       {existing / newly created}

  templates/:
    graph-schema.json      {existing / newly created}
    work-order-template.md {existing / newly created}

  .claude/CLAUDE.md:       {existing / newly created}

  Context cache (Improvements A, B, F):
    _session-bootstrap.md          {generated / up to date}
    .template-cache/B-summary.md   {generated / up to date / N/A}
    .template-cache/B-headings-index.json {generated / up to date / N/A}

  Registered projects:
    {project list or "none"}

Next steps:
  {PREFIX not configured} → enter PREFIX in layer-config.md (integrations — connectors.md — optional)
  {no projects}            → start your first project with /discover {product name}
  {projects exist}         → check the current Phase with /lc {product name}
```


## Next steps

To start your first project after Hub initialization is complete:

```
/discover {product}
```
