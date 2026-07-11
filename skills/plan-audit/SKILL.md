---
name: plan-audit
description: In a Warm Start scenario, fully scans the completeness of existing deliverables and determines the appropriate entry Phase and priority skills to run.
triggers:
  - "plan-audit"
  - "warm start audit"
  - "resume project"
agent: researcher
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


## Execution condition

Triggered after running `/discover {product}` and selecting the Warm Start scenario.
Also runs when the PM directly types `/plan-audit {product}`.

Warm Start condition: 1+ existing file under `PROJECTS/{product}/`.
Cold Start condition: no files at all → return to `/discover`.


## Execution steps

### Step 1 — Full scan of existing documents

Explore the following sources in order and collect the list of discovered documents.

**Source priority:**

| Source | Search target | Connector (docs/CONNECTORS.md capability) |
|---|---|---|
| Local inputs/ | all existing input files | — (read files directly) |
| Document wiki | requirements·planning·policy documents | `wiki` (e.g. Confluence, Notion) |
| Design tool | screen frame list | `design` (e.g. Figma) |
| Code repository | WO branches, MRs, commit history | `repo` (e.g. GitLab, GitHub) |

If a connector is absent or the connection fails, record
`[{capability} skipped]` and continue.
The local inputs/ search always runs without failure.

If a document discovered via an external connector (wiki·design·repo) is newer than the local
file, confirm with the PM whether to sync.


### Step 2 — Determine deliverable completeness

Judge each item as complete / incomplete / missing across 3 tiers.

#### 2-1. requirements.md

| Check item | Criterion | Judgment |
|---|---|---|
| File exists | `inputs/requirements.md` exists | complete / missing |
| Layer 1 FR | 1+ FR items + Must item exists | complete / incomplete |
| Layer 2 NFR | 1+ NFR items | complete / incomplete |
| Layer 3~5 | 1+ item in each layer | complete / incomplete |
| Remaining TBD | 0 TBD items in Layer 1 | complete / incomplete |
| Overall completeness | all 5 items above complete | **Complete / Incomplete** |

#### 2-2. screen-list.md

| Check item | Criterion | Judgment |
|---|---|---|
| File exists | `graph/screen-list.md` exists | complete / missing |
| Screen ID assigned | every row has SCR-NNN format ID | complete / incomplete |
| REQ reference | every row links REQ-NNN | complete / incomplete |
| [unconfirmed] ratio | under 30% of all cells | complete / incomplete |
| Overall completeness | all 4 items above complete | **Complete / Incomplete** |

#### 2-3. graph.json

| Check item | Criterion | Judgment |
|---|---|---|
| File exists | `graph/graph.json` exists | complete / missing |
| screen nodes | 1+ nodes | complete / incomplete |
| edges defined | 1+ edges | complete / incomplete |
| Overall completeness | all 3 items above complete | **Complete / Incomplete** |

#### 2-4. work-orders/index.md

| Check item | Criterion | Judgment |
|---|---|---|
| File exists | `work-orders/index.md` exists | complete / missing |
| WO item count | 1+ | complete / incomplete |
| Type specified | every WO has policy / screen type | complete / incomplete |
| Overall completeness | all 3 items above complete | **Complete / Incomplete** |

#### 2-5. drafts/ draft completion ratio

Aggregate across all files under `drafts/`:

| Item | Aggregation criterion |
|---|---|
| Total draft count | count of drafts/*.draft.md files |
| policy complete count | count of files with type: policy + reviewed: true |
| screen complete count | count of files with type: screen + reviewed: true |
| Incomplete WO list | list of file IDs with reviewed: false |


#### 2-6. Track determination (fix-plan-track-routing P3 — before Phase determination)

Confirm the authoring model (track) **before** Phase determination. Without knowing the
track, the wrong skill would be recommended (legacy `/fanout` vs `/fanout --cluster-mode`).

| Signal | Track determination |
|---|---|
| `graph/project-mode.json` track=A / model=dossier | **Track A (cluster/dossier)** |
| `drafts/cluster_*.draft.md` exists | **Track A** |
| `graph/cluster_map.json` · `graph.clustered.json` exists | **Track A** |
| An approved `🔒` hard DEC in `decisions.md` (e.g. dossier canonical) | **Track A** |
| `work-orders/index.md` filled with section/screen WOs + no signals above | **Legacy (section)** |
| None of the above signals present | **Undetermined** (requirements/graph stage) |

**Confusion detection**: if Track A signals and legacy WOs exist **simultaneously** → note
`⚠️ Track confusion` in the report and warn that legacy WOs may be misrouted deliverables
(this incident's pattern). If a track marker (project-mode.json) is missing, recommend
re-running cluster_identify or manually recording it once Track A is confirmed.


### Step 3 — Determine entry Phase

Determine the appropriate Phase based on the Step 2 judgment results.
**The priority skill to run branches on the Step 2-6 track determination.**

| Condition | Determined Phase | Priority skill (Legacy / Track A) |
|---|---|---|
| requirements.md **Incomplete** | Phase -1 (continue Cold Start) | `/draft-req {product}` |
| requirements.md **Complete**, graph.json **missing** | Phase 0 | `/se` → `/graph-gen` (common) |
| graph.json **complete**, WO **missing** | Phase 1 | Legacy: `/fanout` · Track A: `cluster_identify` → `/fanout --cluster-mode` |
| WO/dossier **created**, some drafts **incomplete** | Phase 2 (resume from incomplete) | Legacy: `/write {incomplete WO_ID}` · Track A: `/write-cluster {incomplete cluster}` |
| policy drafts **complete**, screen drafts **not started** | Phase 2 (screen-design track) | Legacy: `/flow {first screen WO_ID}` · Track A: handled by dossier §2 (no separate screen WO) |

If multiple conditions apply, choose the earliest Phase.
**If track confusion is detected, guide track cleanup (archiving confused WOs) before the
Phase recommendation.**


### Step 4 — Generate reports/plan-audit-report.md

```markdown
# plan-audit report — {product}

**Scan time**: {UTC timestamp}
**Scan sources**: local / {list of successfully discovered external sources}

---

## Track determination (fix-plan-track-routing P3)

**Authoring model**: Track A (cluster/dossier) / Legacy (section) / Undetermined
**Basis signal**: {whichever of project-mode.json · cluster_map.json · dossier draft · hard DEC was detected}
**Confusion**: none / ⚠️ Track confusion ({legacy WO N items + dossier M items coexist — suspected misrouting})

---

## Deliverable completeness summary

| Deliverable | Status | Detail |
|---|---|---|
| requirements.md | Complete / Incomplete / Missing | {incomplete item summary} |
| screen-list.md | Complete / Incomplete / Missing | |
| graph.json | Complete / Incomplete / Missing | |
| project-mode.json (track marker) | Present / Missing | {e.g. track=A} |
| work-orders/index.md | Complete / Incomplete / Missing | |
| drafts/ completion rate | policy {N}/{N} / screen {N}/{N} / cluster {N}/{N} | |

---

## Incomplete item detail

### requirements.md

{list of incomplete items. If none, "none"}

### Incomplete WO list

| WO ID | Type | Status |
|---|---|---|

---

## Judgment result

**Entry Phase**: Phase {N} — {Phase name}

**Basis for judgment**:
{condition explanation}

**Priority skills to run**:
1. {skill name} — {reason}
2. {skill name}

---
## PM approval request

Based on the above judgment, we will resume at Phase {N}.
Proceed? (Y / specify a different Phase)
```


### Step 5 — PM approval and Phase-entry guidance

Present the judgment result to the PM and request confirmation:

```
plan-audit complete: {product}

Determined entry Phase: Phase {N}
Priority skills to run:
  1. {skill name}
  2. {skill name}

Proceed?
  [Y] Resume at Phase {N}
  [number] Directly specify entry into a different Phase
  [N] Cancel and proceed manually
```

If the PM selects Y, immediately launch the priority skill.
If the PM specifies a different Phase, explain that Phase's entry conditions and launch it.


### Step 6 — Record in session-log.md

```markdown
- {date} /plan-audit: Warm Start / entry Phase {N} determined / PM approval {Y/N}
```


## Result file list

| File | Content |
|---|---|
| `reports/plan-audit-report.md` | completeness scan result + Phase judgment + incomplete-item list |
| `session-log.md` | audit completion record |
