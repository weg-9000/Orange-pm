---
# Cluster Draft Standard Template — Track A (Full Product) Work Unit
#
# Usage:
#   1. The PM or /fanout duplicates this per cluster, based on graph-gen output
#   2. One file per cluster: drafts/cluster_{capability}_{cluster_id}.draft.md
#   3. PM authors it (or invokes the /write skill) → /integrate R1-R3 → transposed on /render --push
#
# Spec SSoT:
#   - publication-syntax.md §6 (color cycling)
#   - publication-map.md (cluster ↔ deliverable mapping convention)

# ───── Cluster Identification Metadata ─────
title: "Cluster {{CAPABILITY_NAME}} / {{CLUSTER_ID}} — {{CLUSTER_NAME}}"
wo_id: PX-K-{{CAP}}-{{CL}}        # e.g. PX-K-PR-01 (Provisioning / Cluster 1)
type: cluster_draft
layer: C                           # B (common) / C (product) / DIRECT (Track B/C single)
version: 1.0
status: empty                      # Option A lifecycle: empty→ai-draft(/write)→human-reviewed(/review)→frozen(/confirm)
last_updated: {{DATE}}

# ───── Cluster Classification (graph-gen output) ─────
cluster:
  capability: "{{CAPABILITY_NAME}}"  # e.g. "Provisioning" / "Pricing" / "Operations"
  cluster_id: "{{CLUSTER_ID}}"       # e.g. "PR-01" (capability prefix + sequence number)
  cluster_name: "{{CLUSTER_NAME}}"   # e.g. "InstanceCatalog" / "ResourceLimit"

  # 4-axis clustering score (produced by the graph-gen capability/cluster identification step)
  scores:
    decision_domain: 0.30    # shared decision domain (policy-axis alignment)
    domain_object:   0.20    # shared data object (Instance/Billing/Role, etc.)
    screen_surface:  0.20    # shared screen surface (same primary_screen)
    dependency_cone: 0.15    # 50%+ overlap in the dependency cone
    publication_fit: 0.15    # D2/D3 chapter fit (does it read naturally as one chapter)
  score_total: 0.85  # >= 0.55 merges the cluster (spec §4-axis weighting)

# ───── FR / Dependencies / References ─────
fr_refs:                # cited from D1 Requirements Definition (do not author here, link only)
  - "FR-101"
  - "FR-103"
  - "FR-108"
domain_objects: ["Instance", "InstanceSpec"]
policy_axes:    ["pricing axis", "resource-limit axis"]
primary_screen: "SCR-001"  # primary screen exposed (used when assembling D3)

inherits_from:           # upstream dependency (Phase -1 output / another cluster)
  - "{PREFIX}-B-001"     # common policy
  - "PX-K-PR-00"          # a parent cluster within the same capability

related_screens:         # affected screens (aids the D3 transpose)
  - "SCR-001"
  - "SCR-002"

research_refs:           # cited from D5 Competitor Research (do not author here, link only)
  - "research.md#aws-rds-instance-types"
  - "research.md#gcp-cloudsql-pricing"

# ───── Phase 4 Transpose Output Targets ─────
deliverable_targets:
  - D2          # Policy Definition (cluster §1 transpose)
  - D3          # Screen Design (cluster §2 transpose)
  # - Da_api      # only when a §α-API panel exists (render_transpose --deliverable Da_api)
  # - Da_db       # only when a §α-DB panel exists
  # - Da_migration# only when a §α-MIG panel exists

# Common-shell flag (split-deliverable publish mode only — fix-plan-dossier-publish-split).
# When true, this is excluded from D3 Screen Design's regular chapters and assembled instead into §Appendix A common shell.
# /fanout cluster-mode auto-emits this based on cluster_id(COMMON*) / capability(Common).
# dossier-page publish mode ignores this field (defaults to false, additive).
is_common_shell: false

# ───── Phase 3 Color-Cycling State ─────
# Auto-generated — do not set manually. Updated by apply_color_cycling.py at publish time.
color_state: null
---

::: {.panel section="§1 Policy Decisions (D2 → transposed into Policy Definition)"}
## §1 Policy Decisions

> This cluster's policy decisions. Assembled at publish time into D2 Policy Definition's cluster chapter.

### §1-1 Policy Scope / Applicability Conditions

Describes the conditions and boundaries under which this cluster's policy applies.

| Item | Content |
|---|---|
| **Applies To** | {{scope — e.g. from instance creation through termination}} |
| **Exceptions** | {{exception cases}} |
| **Priority** | {{decision principle in case of conflict}} |

### §1-2 Core Rules

<!-- col-widths: 20%, 30%, 50% -->
| Rule ID | Condition | Policy |
|---|---|---|
| POL-{{N}} | {{condition}} | {{rule body}} |
| POL-{{N+1}} | {{condition}} | {{rule body}} |

### §1-3 Status / Lifecycle

Status definitions handled by this cluster:

| Status | Definition | Entry Condition | Next Status |
|---|---|---|---|
| {{status name}} | {{definition}} | {{condition}} | {{transition}} |

### §1-4 Error / Exception Handling

| Error Code | Trigger Condition | Handling |
|---|---|---|
| ERR-{{N}} | {{condition}} | {{handling policy}} |

:::

::: {.panel section="§2 Screen Design (D3 → transposed into Screen Design)"}
## §2 Screen Design

> This cluster's UI surface. Assembled at publish time into D3 Screen Design's cluster chapter.
> The previous separate screen-WO track has been retired; this section is now responsible for producing the screen design.

### §2-1 Key Screens / Screen IDs

| Screen ID | Screen Name | Entry Path | Notes |
|---|---|---|---|
| SCR-{{NNN}} | {{screen name}} | {{where the user enters from}} | {{}} |

### §2-2 Screen Composition / Components

Core components, fields, and behaviors for each screen:

```
SCR-{{NNN}}
├─ Header: {{title / action buttons}}
├─ Body: {{input form / list / detail}}
└─ Footer: {{secondary actions}}
```

### §2-3 Interaction / Policy Linkage

How the §1 policy rules are exposed on the screen:

| Screen Area | Policy Reference | Exposure Method |
|---|---|---|
| {{area}} | POL-{{N}} | {{message / field state / button enable}} |

### §2-4 Empty States / Error Screens

| State | Display | Action |
|---|---|---|
| Empty list | {{copy}} | {{prompted action}} |
| No permission | {{copy}} | {{alternative}} |

### §2-5 Design Tokens (reference the common shell)

> Colors/typography/spacing reference the tokens of the common-shell cluster (PX-COMMON-NavShell).
> Redefining tokens in this cluster is prohibited — protects the SSoT boundary.

:::

<!-- ═══ §α Technical Deliverables (optional — only when this cluster has a technical deliverable) ═══ -->
<!-- render_transpose extracts panels whose section starts with "§α" and contains a type -->
<!-- keyword (API/DB/migration), assembling them into a separate page per Dα category. -->
<!-- If none exist, transpose safely skips with exit 2 (0 items for this cluster). The -->
<!-- corresponding Da_api / Da_db / Da_migration must also be registered in frontmatter deliverable_targets to become a publish target. -->
<!-- §3 (data/dependencies) is internal authoring metadata (excluded from publish), while §α is the canonical published content — do not duplicate. -->

::: {.panel section="§α-API API Spec (Dα → transposed into API Spec · optional)"}
## §α-API API Spec

> Author this only when this cluster exposes an API. Assembled at publish time into a Dα API Spec
> page (using the `Dα_api.md` template). Clusters that don't apply must delete this entire panel (no empty placeholders left behind).

### §α-API-1 Authentication / Common Headers
| Item | Value |
|---|---|
| Auth method | {{Bearer / API Key / OAuth}} |
| base URL | {{/api/v1/...}} |

### §α-API-2 Endpoints
<!-- col-widths: 12%, 28%, 30%, 30% -->
| Method | Path | Request | Response |
|---|---|---|---|
| {{GET}} | {{/resources}} | {{query/body}} | {{200 schema}} |

### §α-API-3 Error Codes
| Code | Condition | Handling |
|---|---|---|
| {{ERR-NN}} | {{condition}} | {{message/HTTP status}} |

:::

::: {.panel section="§α-DB DB Schema (Dα → transposed into DB Schema · optional)"}
## §α-DB DB Schema

> Author this only when this cluster defines new tables/schema. Assembled at publish time into a Dα DB Schema
> page (using the `Dα_db.md` template). This panel is the canonical schema; §3 Data Model is
> an internal dependency sketch (no duplication of canonical content — §3 should reference this panel).

### §α-DB-1 Table — {{TABLE}}
<!-- col-widths: 22%, 18%, 12%, 48% -->
| Column | Type | Constraint | Description |
|---|---|---|---|
| {{id}} | {{bigint}} | {{PK}} | {{}} |

### §α-DB-2 Index / FK
| Kind | Target | Notes |
|---|---|---|
| {{INDEX / FK}} | {{column · reference}} | {{}} |

:::

::: {.panel section="§α-MIG Migration (Dα → transposed into the Migration Plan · optional)" style="warning"}
## §α-MIG Migration

> Author this only when data migration or schema changes are required. Assembled at publish time into a Dα Migration Plan
> page (using the `Dα_migration.md` template). A rollback procedure is required.

### §α-MIG-1 Steps (Step-by-step)
| Step | Task | Verification | Rollback |
|---|---|---|---|
| {{S-01}} | {{}} | {{}} | {{R-01}} |

### §α-MIG-2 Preconditions / Impact
- {{target tables · downtime · impact scope}}

:::

::: {.panel section="§3 Data / Dependencies (internal use, excluded from publish)"}
## §3 Data / Dependencies

> This section is cluster-authoring metadata. It is removed by publication_prefilter, so it is not included in D2/D3.

### §3-1 Data Model

```mermaid
classDiagram
  class {{DomainObject1}} {
    +field1: type
    +field2: type
  }
  class {{DomainObject2}} {
    +field1: type
  }
  {{DomainObject1}} --> {{DomainObject2}}
```

### §3-2 External Dependencies

- Other cluster: {{cluster_id}} (§policy / §screen dependency)
- External API: {{api_endpoint}}
- Infrastructure: {{DB / cache / queue}}

### §3-3 Performance / Load Considerations

This cluster's impact on system load:

| Item | Expected | Threshold | Notes |
|---|---|---|---|
| QPS | {{}} | {{}} | {{}} |
| Response time | {{ms}} | {{ms}} | {{}} |

:::

::: {.panel section="§4 Open Questions / Upstream Feedback (internal use, excluded from publish)" style="tbd"}
## §4 Open Questions / Upstream Feedback

> This section covers questions found while authoring the cluster, and reflow requests to upstream deliverables (D1/D5).
> It is removed by publication_prefilter, so it is not included in D2/D3.
>
> Reflow flow: /integrate classifies it as an UPSTREAM_GAP BLOCK → /draft-req --upstream-feedback
>            revises D1/D5 to v++.

### §4-1 Open Questions (self-resolvable)

| OQ ID | Question | Owner | Target Date | Notes |
|---|---|---|---|---|
| OQ-{{N}} | {{one-line question}} | {{owner}} | {{date}} | {{}} |

### §4-2 Upstream Feedback (D1/D5 revision candidates)

Classified into the following BLOCK categories — auto-recognized by `/integrate`:

#### REQ_MISSING — Missing FR (D1 addition candidate)
- [ ] {{missing requirement found while authoring the cluster}}

#### POLICY_CONFLICT — Policy Conflict (new decisions.md DEC candidate)
- [ ] {{conflict with another cluster or common policy}}

#### RESEARCH_GAP — Competitor Research Gap (D5 enhancement candidate)
- [ ] {{insufficient competitor comparison data — consider rerunning research-auto}}

#### TERM_AMBIGUOUS — Ambiguous Term (spec-catalog / terms candidate)
- [ ] {{conflicting or missing term definition}}

### §4-3 Decision Trail (DEC registration candidates)

PM decisions made while authoring this cluster:

| Decision | Decider | Date | Affected Cluster | DEC ID (after registration) |
|---|---|---|---|---|
| {{one-line decision}} | {{PM}} | {{date}} | {{}} | DEC-{{}} |

:::

<!-- ────────────────────────────────────────────────────── -->
<!-- Below this is the cluster-authoring guide (removed by publication_prefilter) -->
<!-- ────────────────────────────────────────────────────── -->

<!--
## Authoring Guide (removed from the body by publication_prefilter)

### Fill-In Order
1. **frontmatter cluster metadata** — keep as produced by graph-gen (do not edit manually)
2. **§1 Policy Decisions** — the core work; spend the most time here
3. **§2 Screen Design** — how the §1 policy is exposed (PM should think in terms of policy ↔ UI coupling)
4. **§α Technical Deliverables** — only for clusters that have an API/DB/migration (delete the panel if none)
5. **§3 Data/Dependencies** — confirm boundaries with other clusters (internal metadata)
6. **§4 Open Questions** — keep adding continuously while authoring (if not self-resolvable, mark UPSTREAM_GAP)

### Validation (required)
- `python scripts/lint_publication_syntax.py --input drafts/cluster_*.draft.md`
- `python scripts/md_to_storage.py --input drafts/cluster_*.draft.md --output /tmp/x.xml --validate`
- `python scripts/round_trip_test.py`

### /integrate R1-R3 Cycle
- R1: first draft of this file → /integrate detects HARD/SOFT BLOCK
- R2: resolve BLOCKs + classify UPSTREAM_GAP → /draft-req --upstream-feedback (if needed)
- R3: final check → /confirm to freeze

### Transpose Targets by Section
- §1 → D2 Policy Definition (cluster chapter)
- §2 → D3 Screen Design (cluster chapter)
- §α-API / §α-DB / §α-MIG → separate page per Dα category (only when present, branched by type keyword)
- §3 → private (authoring metadata)
- §4 → private (developer notes / /integrate input)

### Color Cycling
At publish time, apply_color_cycling.py auto-generates this by reading the frontmatter color_state.
The PM must not manually author color spans (`[..]{.color-green}`, etc.) — auto-generated only.

### lazy-split Trigger
When a cluster draft exceeds the following thresholds, splitting into child clusters is recommended (spec 5D):
- body > 1500 lines
- number of policy/screen items in §1+§2 > 8
- accumulated R2 BLOCKs (HARD+SOFT) > 5
- PM explicitly passes the `--split` flag

On split, child cluster IDs: parent + suffix (e.g. PX-K-PR-01-a, PX-K-PR-01-b).

### Prohibited When Authoring
- Quoting another cluster's policy body (link only — `[[POL §X-Y]]`)
- Re-printing common ({PREFIX}-B) body content (render_assemble expands it inline)
- Redefining screen design tokens (reference the common-shell cluster instead)
- Placing self-verification / authoring metadata inside §1/§2 (put it in §3/§4 instead)
-->
