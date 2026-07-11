# Publication Map — Dossier ↔ Page Mapping Convention (v2.1)

> ## ⚠️ v2.1 — 2 publish modes (fix-plan-dossier-publish-split)
>
> The publish unit is determined by **`publication_mode`** in `graph/project-mode.json`
> (`dossier-page` if file/key absent):
>
> | publication_mode | Publish unit | transpose | Applicable § |
> |---|---|---|---|
> | **`dossier-page`** (default) | 1 feature spec = 1 page | not called | §0 |
> | **`split-deliverable`** | D2 policy definition / D3 screen design spec, 2 pages | **reactivated** | §0-bis, §1~§9 |
>
> - `dossier-page` is the v2.0 canonical (§0). DEC-BDB-008 (canonical authoring = Capability
>   Dossier).
> - `split-deliverable` **reactivates** the dossier §1→D2 / §2→D3 transpose.
>   So the §1~§9 transpose matrix below is **valid in `split-deliverable` mode** and
>   DEPRECATED (not called) in `dossier-page` mode — *conditionally active*.
> - §3-A derived views (D1 capability index·cross-cutting matrix) are valid in **both**
>   modes (only the link target differs per mode — dossier page / D2·D3 page).
> - Input-type (D1 requirements·D5 third-party research)·cumulative-type (D4 meeting minutes)
>   are unchanged regardless of mode.
>
> **`graph/project-mode.json` authoring convention** (2026-06-11 audit gap 5 — resolving
> undocumented behavior):
> ```jsonc
> {
>   "track": "A",                              // A(cluster fanout) | legacy
>   "publication_mode": "split-deliverable"    // "dossier-page"(default) | "split-deliverable"
> }
> ```
> - Written by: `/fanout --cluster-mode` or manually by the PM. Changes must occur before
>   publishing
>   (when switching modes, the existing page hierarchy is restructured via `/cr`).
> - Consumers (single source `_emit_common.read_publication_mode`): the render SKILL ·
>   `render_sync_check.py` · `sync_emit.py`. All assume `dossier-page` when the file/key is
>   absent.
> - Sync freshness: in split mode, D2/D3 determine OUTDATED only from the contributing
>   clusters in the assembled.md frontmatter `source_clusters` (recorded by render_transpose).

## §0. Canonical mapping (v2.0 — dossier = page)

| Work output | → Publication | Method | Page |
|---|---|---|---|
| Each dossier `cluster_{cluster_id}.draft.md` (`type: cluster_draft`, `wo_id: {PREFIX}-K-{cluster_id}`) | **feature spec page** | render_assemble→prefilter→md_to_storage (no transpose) | 1 dossier = 1 page |
| `inputs/requirements.md` | D1 requirements definition | direct conversion | 1 |
| `inputs/research.md` | D5 third-party research | direct conversion | 1 |
| `meetings/*.md` | D4 meeting minutes | chronological accumulation | 1 |

- Page hierarchy: `{product} Planning / Feature Specs / {dossier ...} + D1 + D4 + D5`
  (configured by /cr).
- Chapter naming·ordering: capability alphabetical → cluster_id natural order
  (cluster_index.json order).
- Color cycling: per dossier **page** (based on stable WO_ID — avoids the risk of chapter
  reordering).
- Selective publish: `/render --push {product} --only {WO_ID[,WO_ID]}` (viz checkbox
  backend).

---

## §0-bis. split-deliverable mapping (publication_mode: split-deliverable)

| Work output | → Publication | Method | Page |
|---|---|---|---|
| §1 (policy decisions) of every dossier | **D2 policy definition** | render_transpose --deliverable D2 → prefilter→md_to_storage | 1 |
| §2 (screen design) of every dossier | **D3 screen design spec** | render_transpose --deliverable D3 (+`--common-shell`) | 1 |
| `inputs/requirements.md` / `inputs/research.md` / `meetings/*.md` | D1 / D5 / D4 | same as §0 | 1 each |

- Assembled output: `reports/render/02-policy.assembled.md` /
  `03-screen-design.assembled.md`.
- meta naming: `confluence-source/02-policy-{product}.meta.json` /
  `03-screen-design-{product}.meta.json` (per-deliverable — created by /cr's 1-D-split
  tier).
- D3 first tries a **per-screen chapter** from the union of dossier `related_screens`,
  falling back to a per-cluster chapter (WARN) if §2 has no screen tagging
  (`### §2-1 {SCR-ID}`).
- Dossiers with `is_common_shell: true` are separated into D3 §Appendix A (common shell)
  (§8).
- Selective publish: `/render --push {product} --only D2|D3`.
- ⚠️ §0/§5/§6 aren't reflected in D2/D3 (premised on policy §1 being self-contained). If a
  dossier removes D2/D3 from `deliverable_targets`, that cluster is omitted.

---

## (Below, §1~§9 — the transpose model · active in `split-deliverable` / DEPRECATED in `dossier-page`)

> **Purpose**: the convention for transposing Track A's cluster work output into D2/D3 etc.
> **Active** in `publication_mode: split-deliverable` (render_transpose.py::transpose),
> not called in `dossier-page` (only §3-A derived views valid, link target = dossier page).

---

## 1. Separating the two axes (Work vs Publication)

```
                          Publication axis (Confluence)
                                  ↓
                ┌──────────────────────────────────────┐
                │ D1 Requirements │ D2 Policy │ D3 Screen │ D4 Minutes │ D5 3rd-party │ Dα etc │
                ├──────────────────────────────────────┤
   Work axis    │  (input-type)   │(output-type)│(output-type)│(cumulative-type)│(input-type)│(output-type)│
   (Cluster)    ├──────────────────────────────────────┤
   ─ Cluster_1  │     ─        │   §1     │   §2   │   ─      │     ─       │  §α   │
   ─ Cluster_2  │     ─        │   §1     │   §2   │   ─      │     ─       │  §α   │
   ─ Cluster_N  │     ─        │   §1     │   §2   │   ─      │     ─       │  §α   │
                └──────────────────────────────────────┘
```

- **Cluster 4 sections** (`cluster-draft.md`):
  - §1 Policy decisions → **D2 policy definition transpose target**
  - §2 Screen design → **D3 screen design spec transpose target**
  - §3 Data/dependencies → **excluded from publish** (removed by publication_prefilter)
  - §4 Open Questions / Upstream Feedback → **excluded from publish** (`/integrate` input)
- **Deliverable classification**:
  - **Input-type** (D1, D5): Phase -1 output. No transpose. Published as-is.
  - **Output-type** (D2, D3, Dα): Phase 4 transpose target. Assembles cluster sections.
  - **Cumulative-type** (D4): time axis. Chronological assembly of `meetings/*.md` +
    cluster-tag index.

---

## 2. Transpose matrix (canonical mapping table)

| Cluster Section | → Deliverable | Assembly method | Chapter structure |
|---|---|---|---|
| **§1 Policy decisions** (each cluster) | **D2 policy definition** | assembled in cluster_id order | "Capability {name} / Cluster {id} {cluster_name}" chapter |
| **§2 Screen design** (each cluster) | **D3 screen design spec** | assembled in cluster_id order + common-shell appendix | "Capability {name} / Cluster {id}" chapter + appendix |
| **§α (clusters that have it only)** | **Dα etc category** | separate page per type | e.g. API chapter, DB chapter, migration chapter |
| §3, §4 | **excluded from publish** | — | — |

**Assembly order (deterministic)**:
1. Capability alphabetical order (Pricing < Provisioning < ...)
2. Within the same capability, cluster_id natural order (PR-01 < PR-02 < ...)
3. Common shell (G2-COMMON-*) is a separate D3 appendix section

---

## 3. Input-type / cumulative-type processing

### D1 Requirements Definition (input-type — Phase -1)
- Source: `inputs/requirements.md` (draft-req output)
- Publish: direct `md_to_storage` conversion, no transpose
- Update timing: Phase -1 or UPSTREAM_GAP reflow (`/draft-req --upstream-feedback`)
- Cluster reference: each D1 FR cross-links to whichever cluster covers it via the
  `cluster_ref` metadata

### D5 Third-party Research (input-type — Phase -1)
- Source: `inputs/research.md` (draft-req output, auto-filled by research-auto)
- Publish: converted as-is
- Cluster reference: cited from cluster §1·§2 via `research_refs:` frontmatter

### D4 Meeting Minutes (cumulative-type — Phase 2~3 rolling)
- Source: `meetings/*.md` + `mtg-ledger.md`
- Publish: reverse-chronological assembly + cluster-tag-based index panel
- Meeting frontmatter `cluster_refs: [...]` is the key generating the index

---

## 3-A. P3 derived views — auto-synthesized from the cluster_map.json index (DEC-C / DEC-F)

The two views below are **never hand-written.** They're auto-synthesized by pure,
deterministic functions in `render_transpose.py` from `graph/cluster_map.json`'s `fr_index` /
`module_index` (SSoT — DEC-D). When re-clustering (adjusting threshold/`/fanout`) changes the
index, the views auto-follow (0 manual edits). No fixed prose TOC.

### (1) D1 capability group-by view (DEC-C)

Groups `fr_index` ({`FR-id`: {`capability`, `cluster_id`}}) by capability and cross-links
each FR to its feature-spec (cluster_id) anchor.

```python
render_fr_capability_view(fr_index: dict[str, dict]) -> str
```

Sort order: capability alphabetical → FR natural order. Sample:

```
::: {.panel section="§D1 FR groupings by capability (derived from cluster_map.fr_index)"}
## §D1 FR groupings by capability (derived from cluster_map.fr_index)

### Pricing

- **FR-101** → [Feature Spec PR-01](#PR-01)
- **FR-103** → [Feature Spec PR-01](#PR-01)
:::
```

### (2) Cross-cutting concern matrix view (DEC-F)

Synthesizes a matrix table from `module_index` ({`moduleDocId`: [{`cluster_id`,
`capability`, `source`, `via`, `section`}, …]}) showing, per **shared module**, "which
feature (cluster) references this module." **Works generically for any module** (email·
logging·auth, etc. — no hardcoding of a specific module). Rules (format·retry·opt-out) live
in one module/notification dossier; the matrix is a trigger reverse-index derived view.

```python
render_cross_cutting_matrix(
    module_index: dict[str, list[dict]],
    node_titles: dict[str, str] | None = None,
) -> str
```

Sort order: module docId alphabetical → rows by capability → cluster_id natural order →
source → via.
Sample:

```
::: {.panel section="§Cross-cutting concern matrix (derived from cluster_map.module_index)"}
## §Cross-cutting concern matrix (derived from cluster_map.module_index)

### Email·SMS sending module (DOC-EMAIL)

| capability | cluster_id | source | via | section |
|---|---|---|---|---|
| Account | PR-01 | NODE-A | references | §1 |
| Backup | PR-02 | NODE-B | references | §2 |
:::
```

Tests: `render_transpose_test.py` `TP3FrCapabilityView` / `TP3CrossCuttingMatrix`
(grouping·deterministic ordering·empty input·multiple modules).

---

## 4. transpose() function interface (implementation complete — render_transpose.py)

`scripts/render_transpose.py` (actual signature — the pseudocode below is a spec summary):

```python
def transpose(
    cluster_drafts: list[Path],     # list of drafts/cluster_*.draft.md
    deliverable_type: str,           # "D2" | "D3" | "Dα_{type}"
    *,
    common_shell_clusters: list[Path] = None,  # G2-COMMON-* (during D3 assembly)
) -> str:
    """
    Extract the target deliverable's section from cluster drafts → produce a single MD
    deliverable.

    Behavior:
      1. Check each cluster_draft's frontmatter → is it included in deliverable_targets?
      2. Extract that cluster's mapped section:
         - D2 → §1
         - D3 → §2 + (for D3, common-shell appendix)
         - Dα → §α
      3. Sort by capability + cluster_id
      4. Insert as chapters into the D{N} template skeleton
         (templates/standard/D2_policy.md, etc.)
      5. Update frontmatter (title, version, last_updated)
      6. Return the resulting MD (the input md_to_storage will convert to XML)

    Returns:
      str — the assembled MD source
    """
```

---

## 5. transpose metadata in cluster_draft frontmatter

The following fields in `cluster-draft.md` frontmatter are transpose's decision inputs:

```yaml
cluster:
  capability: "Pricing"       # chapter grouping key during transpose
  cluster_id: "PR-01"         # chapter ordering key
  cluster_name: "PlanMatrix"  # part of the chapter title

deliverable_targets:
  - D2     # §1 → assembled into D2
  - D3     # §2 → assembled into D3
  - Da_api # §α → assembled into Dα_api

related_screens:
  - "SCR-001"  # appendix index during D3 assembly
  - "SCR-002"

fr_refs:
  - "FR-101"   # which D1 FR this covers (used for D1 → cluster back-reference)
  - "FR-103"
```

---

## 6. Applying publication-map on Track branching

Only Track A applies publication-map. Track B/C is a direct single-deliverable path.

| Track | publication-map applied | Notes |
|---|---|---|
| A — Full Product | ✓ fully applied | cluster_drafts/ → D1~D5+α transpose |
| B — Single Deliverable | ✗ bypassed | single draft → direct single-deliverable publish |
| C — Template Copy | ✗ bypassed | template extraction + direct publish |

→ The render SKILL.md's Track auto-detection (Phase 4 R6) determines whether
publication-map is triggered.

---

## 7. Chapter naming convention (during D2/D3 assembly)

Each cluster chapter is named in the following format — for TOC generation·search
consistency:

```
§{N} {Capability} / {ClusterName} ({cluster_id})

e.g.
§1 Pricing / PlanMatrix (G2-K-PR-01)
§2 Pricing / PriceCalculator (G2-K-PR-02)
§3 Provisioning / InstanceCatalog (G2-K-PV-01)
...
```

§N is the natural internal order within the deliverable during transpose (the §2 sort rule
above). Chapter number stability is maintained as long as cluster_id doesn't change (also
affects color cycling's path stability).

---

## 8. Handling the common shell (G2-COMMON-*)

The D3 screen design spec places the common shell (NavShell / AuthFlow, etc.) as a separate
appendix:

```
D3 Screen Design Spec
├─ Capability 1 / Cluster 1.1
├─ Capability 1 / Cluster 1.2
├─ ...
├─ Capability N / Cluster N.M
└─ Appendix A — Common Shell
   ├─ NavShell (G2-COMMON-01)
   ├─ AuthFlow (G2-COMMON-02)
   └─ ...
```

The common shell is marked with `deliverable_targets: [D3]` + `is_common_shell: true`
frontmatter.

---

## 9. Impact of chapter reordering on color cycling

⚠ **Note**: if chapter order is rearranged due to e.g. a cluster-algorithm v2 change, all
color-cycling paths change, risking the appearance of a "wholesale move" (spec §3.3).

**Mitigation policy**:
- cluster_id is assigned once and kept stable (reused even if clustering results change)
- On algorithm change, recommend the PM explicitly run `/render --color-reset` — start a new
  baseline
- The chapter-order sort key is fixed to `capability + cluster_id` (automatic stability, not
  human sorting intent)

---

## 10. Implementation status / remaining gaps

With Phase 5F (`transpose()` — `render_transpose.py`) + Phase 5C (`fanout_dag.py
_iter_cluster_nodes`) complete, this mapping is **executable**.

Complete:
- ✓ Mapping convention SSoT confirmed (§2 transpose matrix)
- ✓ Consistent with the cluster_draft 4-section template (5E)
- ✓ Consistent with the Phase 4 R6 Track auto-detection
- ✓ transpose() code implemented (`render_transpose.py`, tested in
  `render_transpose_test.py`)
- ✓ /render step 3-A wired (D2/D3 execution + md_to_storage)

- ✓ **§α → Dα assembly activated**: added §α-API / §α-DB / §α-MIG **optional panels** to
  `cluster-draft.md` → clusters with technical deliverables write §α and register
  `Da_api|Da_db|Da_migration` etc. in `deliverable_targets` to get assembled into a separate
  page per type (guarded by render_transpose_test). Clusters without §α exit 2 safely
  skipped — independent of D2/D3.

---

## 11. Change history

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-05-30 | Phase 5G — established cluster ↔ deliverable mapping SSoT |
