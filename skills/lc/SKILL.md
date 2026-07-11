---
name: lc
description: Automatically detects the project's current Phase and verifies whether all gates pass. When another skill needs to check only a specific gate, use the --gate option. Outputs a Phase dashboard together with recommended next skills.
triggers:
  - "lc"
  - "layer check"
  - "status"
  - "gate check"
phase: any
effort: low
model: haiku
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

## Execution steps

### Step 1 — Collect project context

Read the following files. If a file doesn't exist, treat that item as "not yet created":
- `PROJECTS/{product}/session-log.md`
- `PROJECTS/{product}/open-issues.md`
- `PROJECTS/{product}/decisions.md`
- `PROJECTS/{product}/inputs/requirements.md`
- `PROJECTS/{product}/graph/graph.json`
- `PROJECTS/{product}/work-orders/index.md`
- `PROJECTS/{product}/reports/integration-summary.md`
- `CONTEXT/layer-config.md`

Read the current Phase from session-log.md.
If there's no Phase record, treat it as Phase -1 (Init not complete).

If the `--gate {gate_name}` option is specified, run only that gate step and return.


### Step 2 — Verify checklists per gate

For each gate, the **verification criteria live in `CONTEXT/gates/` files as the single source
of truth**. lc doesn't embed the criteria — it reads them from the files.

#### discovery-exit-gate

Read `CONTEXT/gates/discovery-exit-gate.md`.
If the file doesn't exist, notify the PM that the gate file is missing and mark that gate SKIP.
Verify each row of the "## Required Conditions" section table in order, and record PASS / FAIL.

#### policy-entry-gate

Read `CONTEXT/gates/policy-entry-gate.md`.
If the file doesn't exist, mark that gate SKIP.
Verify each row of the "## Required Conditions" section table in order, and record PASS / FAIL.

#### graph-exit-gate

Read `CONTEXT/gates/graph-exit-gate.md`.
If the file doesn't exist, mark that gate SKIP.
Verify each row of the "## Required Conditions" section table in order, and record PASS / FAIL.

#### draft-complete-gate

Read `CONTEXT/gates/draft-complete-gate.md`.
If the file doesn't exist, mark that gate SKIP.
Verify each row of the "## Required Conditions" section table in order, and record PASS / FAIL.

#### integration-exit-gate

Read `CONTEXT/gates/integration-exit-gate.md`.
If the file doesn't exist, mark that gate SKIP.
Verify each row of the "## Required Conditions" section table in order, and record PASS / FAIL.


### Step 2-B — Verify script-output gates

**Do not reload source content (draft body · common policy body) — read only the header summary.**
If a queue file is missing, mark it `STALE` and output a "script not yet run" recommendation
(distinct from FAIL).

#### drift-gate

Read only the header line of `PROJECTS/{product}/reports/drift-queue.md`.
- Parse header `BLOCK: N` → if N > 0, **FAIL** (SOFT_BLOCK)
- If N = 0, **PASS**
- If file doesn't exist → **STALE** (script not run — recommend running
  `python ${CLAUDE_PLUGIN_ROOT}/scripts/drift_scan.py --hub-root . [--product {product}]`)

#### master-derivation-gate

Read the **1-line header** of `PROJECTS/{product}/reports/integration-summary.md` first.

Header format (mandatory integrator agent output):
```
generated_at: <ISO8601 timestamp>   <!-- e.g. generated_at: 2026-05-24T09:30:00Z -->
```

Judgment order:
1. File doesn't exist → **STALE** (recommend running the integrate skill)
2. File exists but no `generated_at:` header → **STALE** (script not run — recommend
   re-running integrate). Cannot distinguish from a clean state (`FAIL=0`), so do not mark PASS.
3. The header `generated_at` value is older than the most recent mtime among files under
   `drafts/` → **STALE** (drafts changed since — integrate needs to be re-run)
4. If the header timestamp is current, check reviewer V-06 / integrator I-02 FAIL counts in
   the body:
   - FAIL count > 0 → **WARN** (not a hard BLOCK — recommend reviewing the common derivation
     chain)
   - FAIL count = 0 → **PASS**

> ⚠️ **WARN grade**: this gate is not a blocking condition. Resolving it before entering the
> next Phase is recommended, but it's registered in the BLOCK queue at WARN grade only.

#### policy-impact-gate

Read only the header line of `PROJECTS/{product}/reports/policy-impact-queue.md`.
- Parse header `IMPACT: N` → if N > 0, **FAIL** (SOFT_BLOCK)
- If N = 0, **PASS**
- If file doesn't exist → **STALE** (script not run — recommend running
  `python ${CLAUDE_PLUGIN_ROOT}/scripts/policy_impact_scan.py --hub-root . [--product {product}]`)

#### bdd-coverage-gate

Read only the header line of `PROJECTS/{product}/reports/bdd-coverage-queue.md`.
- Parse header `UNCOVERED: N · STALE: N` → **PASS** if both are 0
- If either is > 0 → **FAIL** (SOFT_BLOCK)
- If file doesn't exist → **STALE** (script not run — recommend running `/bdd {product}`)

#### mtg-gate

Read only the header line of `PROJECTS/{product}/reports/mtg-queue.md`.
- Parse header `BLOCK: N · FAIL: N` → **PASS** if both are 0
- If either is > 0 → **FAIL** (SOFT_BLOCK)
- If file doesn't exist → **STALE** (script not run — recommend running
  `python ${CLAUDE_PLUGIN_ROOT}/scripts/mtg_ledger_scan.py --hub-root . [--product {product}]`)

#### render-freshness-gate

For each `drafts/{WO_ID}.draft.md` file, compare its mtime against the corresponding
`reports/render/{WO_ID}.complete.md` file's mtime. **Do not read the body — mtime only.**

- complete.md doesn't exist → **FAIL** (auto-assemble hook didn't run, or it's a new draft —
  recommend the PM run
  `python ${CLAUDE_PLUGIN_ROOT}/scripts/render_assemble.py --hub-root . --product {p} --wo {WO_ID}`)
- draft mtime > complete mtime → **FAIL** (complete.md is stale — the auto-assemble hook should
  have run but didn't. Recommend the same command)
- If every draft is paired with a current complete.md → **PASS**

This gate is a safety net verifying the PostToolUse hook (auto-assemble) ran correctly.
It's caught on `/lc` entry even if the hook fails.

#### sync-drift-gate

Inspect `PROJECTS/{product}/reports/sync-queue.md` and the `reports/inbox/` directory:
- If 1+ `reports/inbox/*.merge-proposal.md` exist → **WARN** (unresolved wiki (remote) drift —
  recommend `/render --apply-inbox {WO_ID}`)
- If `sync-queue.md` header `OUTDATED: N` is > 0 → **WARN** (push needed — recommend
  `/render --push`)
- If both are 0 or the file doesn't exist → **PASS**

This gate doesn't block Phase progression (WARN grade) but visualizes wiki (remote) ↔ Local
inconsistency.

#### track-gate (fix-plan-track-routing P2)

Verifies consistency between the authoring model (track) and the actual deliverables/decisions.
**Do not read the body — look only at `graph/project-mode.json`, file-existence signals, and
the hard DEC rows in decisions.md.**

1. **Track marker ↔ deliverable consistency**
   - If `graph/project-mode.json` says track=A (dossier) but `work-orders/index.md` is filled
     with legacy section/screen WOs → **FAIL** (model confusion — legacy WOs have contaminated
     the dossier track. Recommend re-confirming the track via `/plan-audit`).
   - If track=A but `drafts/cluster_*.draft.md` count is 0 and the graph has neither
     capability nor cluster_id → **WARN** (cluster_identify hasn't run — must precede
     `/fanout --cluster-mode`).
   - If project-mode.json doesn't exist but cluster signals (cluster_map.json · dossier draft)
     exist → **WARN** (missing track marker — recommend re-running cluster_identify or
     recording it manually).

2. **Enforce hard DEC (gate decisions)**
   - Collect as **hard DEC** any row in `decisions.md` where the `Decision` cell has a `🔒`
     marker and `Approved` is `✅` (e.g. "🔒 retire section WO · dossier is canonical").
   - If a deliverable contradicting the intent of an approved hard DEC is detected → **FAIL**
     (e.g. an approved hard DEC declares dossier canonical, but a legacy section WO exists).
   - If there's no contradiction → **PASS**.

**PASS** if all three items are consistent. FAIL is registered at SOFT_BLOCK grade.


### Step 2-C — Sort BLOCK priority queue

Collect all gate results from steps 2 and 2-B into a BLOCK queue and sort with the following
3-step algorithm.

#### Severity classification

| Grade | Applicable condition |
|---|---|
| **HARD_BLOCK** | ① integration-exit-gate FAIL (blocks the Phase 3→4 transition itself — `/confirm`·`/cr` cannot be called) ② environment SSoT damage: `master-id-map.yml` fails to parse, or both `graph.json` / `graph.edges.json`·`graph.policy.json` are missing (gate verification itself is impossible) |
| **SOFT_BLOCK** | orange-pm Phase-entry gate FAIL (excluding integration-exit-gate) / drift BLOCK / mtg BLOCK+FAIL / policy-impact IMPACT / bdd-coverage UNCOVERED·STALE / **track-gate FAIL (track confusion·hard DEC contradiction)** |
| **WARN** | master-derivation WARN / drift WARN·UNRESOLVED |
| **INFO** | ontology unresolved · embed stale · Neo4j disconnected |

> **HARD_BLOCK edge-case rule**
> - Even if HARD_BLOCK occurs in a lower Phase, **Severity takes absolute priority** — it's
>   sorted first regardless of Phase position.
> - Multiple HARD_BLOCKs at the same Severity and Phase are processed in **ascending effort
>   order (XS → XL)**.
> - SOFT_BLOCK means "work in the current Phase is possible, only entry to the next Phase is
>   blocked," while HARD_BLOCK means "work in the current Phase itself is impossible," so
>   immediate PM confirmation is required.

#### Phase-position order (front = higher)

```
discovery-exit → policy-entry → graph-exit → draft-complete
→ [drift / policy-impact / mtg / bdd-coverage / master-derivation]
→ integration-exit
```

Order among script-output gates within the same Phase:
`drift > policy-impact > mtg > bdd-coverage > master-derivation` (broadest impact scope first)

#### Effort tie-break

Apply ascending effort order (XS → S → M → L → XL) only within the same Severity + same Phase.
**No priority reversal**: even with lower effort, an item cannot overtake a higher
Severity/Phase item.

#### Recommendation output format

```
★ Recommended: {gate_id} — {one-line resolution guide}
   (Reason: Severity={grade} / Phase={position} / effort={XS|S|M|L|XL})
```

The recommendation outputs only the single #1 item after sorting.


### Step 3 — Output results

Output a dashboard in the following format:

```
Project status: {product}
Current Phase:  {Phase value} ({Phase name})
PREFIX:          {PREFIX}

Gate status (Phase-entry gates):
  discovery-exit-gate   [{PASS/FAIL/SKIP}]  {count of unmet items or "complete"}
  policy-entry-gate     [{PASS/FAIL/SKIP}]  {count of unmet items or "complete"}
  graph-exit-gate       [{PASS/FAIL/SKIP}]  {count of unmet items or "complete"}
  draft-complete-gate   [{PASS/FAIL/SKIP}]  {count of unmet items or "complete"}
  integration-exit-gate [{PASS/FAIL/SKIP}]  {count of unmet items or "complete"}

Gate status (script-output gates):
  drift-gate            [{PASS/FAIL/WARN/STALE}]  {BLOCK count or "no issues"}
  policy-impact-gate    [{PASS/FAIL/WARN/STALE}]  {IMPACT count or "no issues"}
  mtg-gate              [{PASS/FAIL/WARN/STALE}]  {BLOCK+FAIL count or "no issues"}
  bdd-coverage-gate     [{PASS/FAIL/STALE}]       {UNCOVERED+STALE count or "no issues"}
  master-derivation-gate[{PASS/WARN/STALE}]       {V-06/I-02 FAIL count or "no issues"} ※WARN only

Unresolved items:
  P0: {N} items  {progress blocked if N is nonzero}
  P1: {N} items
  P2: {N} items

BLOCK priority queue (total {N} items):           ← key items only, within 10 lines
  1. [{SOFT_BLOCK|WARN|INFO}] {gate_id}  {one-line summary}
  2. ...

★ Recommended: {gate_id} — {one-line resolution guide}
   (Reason: Severity={grade} / Phase={position} / effort={XS|S|M|L|XL})

Recommended next skill:
  {one recommendation based on current Phase and gate status}
```

### Ontology infrastructure status

- **Number of unresolved items in unknown_terms.log**
  Read `CONTEXT/glossary/unknown_terms.log` and count lines not starting with `#`.
  - 0 → ✅
  - 1+ → ⚠️ {N} unresolved vocabulary items (list the items)
  - File doesn't exist → [glossary not initialized — run Phase 3-A first]

- **Time of last embed_pipeline run**
  Based on the modification time of `PROJECTS/{product}/chunks.parquet`
  - Within 7 days → ✅ {date}
  - Over 7 days → ⚠️ {date} — recommend re-running embed_pipeline
  - File doesn't exist → [embedding not run — run embed_pipeline.py]

- **Neo4j connection status**
  Ping bolt://localhost:7687
  - Success → ✅ connected
  - Failure → ⚠️ not connected (/search vector mode disabled)

#### Phase name definitions:

| Phase value | Name |
|---|---|
| -1 | Init not complete |
| Init | Initialization complete |
| 0 | Discovery / Requirements / Graph |
| 1 | Fanout |
| 2 | Writing |
| 3 | Integration |
| 4 | Publication |

#### Recommended-skill decision logic:

| Condition | Recommended skill |
|---|---|
| layer-config.md doesn't exist or PREFIX not registered | `/ingest {product}` |
| discovery-exit-gate FAIL | whichever of `/research`, `/stakeholder`, `/product-audit` isn't complete |
| policy-entry-gate FAIL | `/draft-req {product}` |
| graph-exit-gate FAIL | `/graph-gen {product}` |
| draft-complete-gate FAIL | `/fanout {product}` or `/write {WO_ID}` |
| integration-exit-gate FAIL | `/integrate {product}` |
| all gates PASS | `/confirm {product}` |


### Step 4 — Output unresolved item detail

If 1+ gates are FAIL / WARN / STALE, output the list of unresolved items.
**Target: 30-second readability** — script-output gates show only header figures; do not
re-quote source text.

```
Unresolved item detail:

━━ Phase-entry gates ━━

[policy-entry-gate]
  - requirements.md Layer 1 FR: currently {N} (threshold: 10+)
  - ...

[draft-complete-gate]
  - Unwritten drafts: WO-03.draft.md, WO-07.draft.md

━━ Script-output gates ━━

[drift-gate]           {FAIL|STALE}
  - BLOCK: {N} items  →  check drift-queue.md, resolve, then re-run
  ※ If STALE: drift_scan.py not run — run
    `python ${CLAUDE_PLUGIN_ROOT}/scripts/drift_scan.py --hub-root . [--product {product}]` first

[policy-impact-gate]   {FAIL|STALE}
  - IMPACT: {N} items  →  check policy-impact-queue.md
  ※ If STALE: policy_impact_scan.py not run —
    `python ${CLAUDE_PLUGIN_ROOT}/scripts/policy_impact_scan.py --hub-root . [--product {product}]`

[mtg-gate]             {FAIL|STALE}
  - BLOCK: {N} items · FAIL: {N} items  →  check mtg-queue.md
  ※ If STALE: mtg_ledger_scan.py not run —
    `python ${CLAUDE_PLUGIN_ROOT}/scripts/mtg_ledger_scan.py --hub-root . [--product {product}]`

[master-derivation-gate]  {WARN|STALE}
  - V-06 FAIL: {N} items · I-02 FAIL: {N} items  →  see integration-summary.md
  ⚠️ WARN — not a hard BLOCK. Recommend resolving before entering the next Phase.
  ※ If STALE: /integrate skill hasn't run
```

When the `--gate {gate_name}` option is used, return only that gate's PASS/FAIL result and
its list of unresolved items, then finish.
This is a lightweight mode for calls from other skills.


## Result files

| File | Change |
|---|---|
| `reports/lc-{YYYYMMDD-HHMM}.md` | Saves the full gate-check result (manual invocation only) |

No file is created when called from another skill via the `--gate` option.
