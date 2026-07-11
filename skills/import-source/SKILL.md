---
name: import-source
description: |
  A multi-source entry point that pulls arbitrary markdown from external sources
  (Confluence / GitLab / Notion / local files), analyzes and normalizes it, then admits it into
  reference-docs/{ACTIVE_PREFIX}/{A,B,C}. Implements the multi-tenant SaaS principle "first-user
  entry priority #1 = external source import." It is a generalization of from-url
  (Confluence-only) into a higher-level skill.

  Pipeline: fetch → import_normalize (recordize) → frontmatter_detect (metadata normalization)
    → layer_classify (auto A/B/C classification) → term_extract (terminology candidate queue)
    → dependency_infer (candidate dependency edges) → PM confirmation gate → promotion.

  This skill **only reads/analyzes** external documents. Promotion to the canonical
  reference-docs and reflecting changes into glossary terms.yml happen only after PM confirmation
  (never auto-forced).
triggers:
  - "import"
  - "pull this in"
  - "analyze this document"
  - "bring this document in"
  - "gitlab"
  - "notion"
  - "notion"
  - "external document"
  - "import-source"
phase: any
effort: medium
model: direct
user-invocable: true
---

## Bootstrap cache guard

Load `CONTEXT/_session-bootstrap.md` only once per session, on first entry (do not re-read it).
If the cache is missing or stale, refresh it before proceeding:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```


## 1. Entry conditions

- The user presents an external source (a Confluence/GitLab/Notion URL, or a local .md) along
  with a verb like "import/pull in/analyze/admit"
- intent-router routes an import intent
- The PM invokes it directly with `/import-source <URL|path> --product <p>`

Simple reflow of a single Confluence URL is also possible with the existing `/from-url`. Use
this skill when **multi-source + automatic analysis (classification/terminology/dependency)**
is needed.


## 2. Source determination

| Source | Signal | Fetch method |
|---|---|---|
| `confluence` | `confluence.../pages/{id}` | Query (get) via the wiki connector (Confluence family) → snapshot JSON → convert to MD with `storage_to_md.py --from-snapshot` |
| `gitlab` | `gitlab.../-/raw/.../*.md`, a `.md` repo path | Repo connector or raw URL fetch — **MD-native, no conversion needed** |
| `notion` | `notion.so/...`, a page ID | Page fetch via the wiki connector (Notion family) → markdown — **MD-native** |
| `file` | Local path / pasted content | Used as-is |

`{id}` is the stable identifier per source (page_id / repo-path-slug / notion-page-id / file stem).
If `{product}` is unspecified, confirm with the PM which `PROJECTS/{product}` to admit it into.


## 3. Fetch (model/tool responsibility)

Authentication and external calls are performed by the model via tools (scripts do analysis
only — the same separation as from-url). Per-source connectors are verified using the
CONNECTORS.md detection protocol (prefer the `CONTEXT/connectors.md` mapping; auto-detect if absent).

- **Confluence-family wiki**: fetch the page_id `{ID}` page via the wiki connector's query (get)
  operation, save it as snapshot JSON including id/title/version/body (storage XML) to
  `/tmp/{ID}.snapshot.json`, then convert locally:

  ```bash
  python ${CLAUDE_PLUGIN_ROOT}/scripts/storage_to_md.py \
    --input /tmp/{ID}.snapshot.json --from-snapshot --output /tmp/{ID}.md
  ```

- **GitLab**: obtain the `.md` body via the repo connector or a raw URL fetch and save it to `/tmp/{ID}.md`.
- **Notion-family wiki**: save the wiki connector's page fetch result (markdown) to `/tmp/{ID}.md`.
- **file**: use the input path as-is.

Report fetch failures (401/403/network) clearly, and guide the user to a manual export →
`--input` workaround.


## 4. Recordization (import_normalize)

Load the fetched MD into a standard import record (lossless body, normalized frontmatter):

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/import_normalize.py \
  --hub-root . --product {product} --source {source} --id {ID} \
  --input /tmp/{ID}.md --source-url "{URL}" --intent context
```

Output:
- `PROJECTS/{product}/inputs/imports/{source}/{ID}.md` (reference frontmatter + body)
- `PROJECTS/{product}/inputs/imports/{source}/{ID}.meta.json`

Do not overwrite an existing meta.json (only warn if content has changed).


## 5. Analysis pipeline

Using the record MD as input, run 3 analyses and produce a **recommendation report**.

```bash
REC=PROJECTS/{product}/inputs/imports/{source}/{ID}.md

# 5-A. Auto layer classification (A/B/C; low confidence → unknown → PM confirmation)
python ${CLAUDE_PLUGIN_ROOT}/scripts/layer_classify.py --input $REC --json

# 5-B. Term extraction → candidate queue (do not edit terms.yml directly)
python ${CLAUDE_PLUGIN_ROOT}/scripts/term_extract.py \
  --hub-root . --input $REC --source {source} --write-candidates

# 5-C. Dependency inference → candidate edges
python ${CLAUDE_PLUGIN_ROOT}/scripts/dependency_infer.py \
  --hub-root . --input $REC --doc-id {ID} \
  --out PROJECTS/{product}/inputs/imports/{source}/{ID}.edges.json
```

If the classification is `unknown` or confidence is low (below the 0.34 threshold), do not
guess — ask the PM back for the layer in one line. If a complex boundary judgment is needed,
delegate it to the advisor (CLAUDE.md routing — classification is batch, only boundary judgment
goes to the advisor).


## 6. PM confirmation gate → promotion

Present the report in the following format and get PM confirmation (no auto-promotion):

```
[import-source proposal — {ID}]
- Layer: B (confidence 0.82) · signals: policy phrasing x9, common reference x2
- New term candidates: 3 (term-candidates.yml)
- Dependency candidate: SELF → inherits_from → G2-B-002 (high)
- Proposed location: CONTEXT/reference-docs/{ACTIVE_PREFIX}/B/{ID}.md
Approve? (the layer can be corrected)
```

After PM approval:
1. Move the record MD to `CONTEXT/reference-docs/{ACTIVE_PREFIX}/{layer}/{ID}.md`.
2. Register `{ID}: {stem}` in `master-id-map.yml` (if needed).
3. Regenerate caches: `build_b_cache` / `build_b_index` / `build_a_index` / `build_c_index`.
4. Term candidates (term-candidates.yml) and dependency edges are reflected into `terms.yml` /
   the graph only after PM review.


## 7. Usage examples

```bash
# Import GitLab raw markdown → analyze
/import-source https://gitlab.example.com/x/-/raw/main/policy.md --product dbaas

# Import a Notion page
/import-source https://www.notion.so/team/account-policy-abc123 --product dbaas

# Analyze a local file only
/import-source ./inbox/legacy-policy.md --product dbaas --source file
```


## 8. Cautions

- **No auto-forcing**: layer promotion, term registration, and edge confirmation all happen only
  after passing the PM confirmation gate.
- **Lossless**: import_normalize never modifies the body (only attaches metadata).
- **Closed-glossary relaxation**: new terms are staged in `term-candidates.yml` + accumulated in
  `unknown_terms.log`. The canonical `terms.yml` is updated manually only after PM approval.
- **PREFIX scope**: the promotion location is always under `ACTIVE_PREFIX`. To admit into a
  different PREFIX, switch `ACTIVE_PREFIX` in `layer-config.md` first.


## 9. Workflow connections

```
[external source] ─→ /import-source ─→ import_normalize ─→ frontmatter_detect
                                      ↓
        layer_classify ─ term_extract ─ dependency_infer ─→ recommendation report
                                      ↓ (PM confirmation)
        reference-docs/{ACTIVE_PREFIX}/{A,B,C}/  +  cache regeneration
```

- **Precedes**: `intent-router` (detects import intent) or direct PM invocation
- **Related**: `/from-url` (simple Confluence reflow), `/ingest` (precedes for a new product)
- **Reused scripts**: `storage_to_md.py`, `migrate_draft_frontmatter.py` (parsing),
  `build_a_index.extract_terms`, `drift_scan`/`master-id-map` (edge resolution)


## 10. Output file list

| File | Creation condition | Content |
|---|---|---|
| `inputs/imports/{source}/{ID}.md` | Always | reference frontmatter + body (lossless) |
| `inputs/imports/{source}/{ID}.meta.json` | On a new import | source/url/intent/content_sha |
| `inputs/imports/{source}/{ID}.edges.json` | Analysis 5-C | Dependency candidate edges |
| `CONTEXT/glossary/term-candidates.yml` | Analysis 5-B | Term candidate queue (before PM approval) |
