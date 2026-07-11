---
name: research-auto
description: |
  Performs automated third-party research via web search + LLM summarization. Generates a
  draft of inputs/discovery/competitor/*.md + research.md (D5 format). Factual accuracy is
  not guaranteed — always requires a PM approval gate.

  When to use:
    - Automating new-product Phase -1 discovery
    - Entering Track B's "third-party research then write D1/D5" step
    - Supplementing an existing research.md (--augment)
triggers:
  - "after third-party research"
  - "competitor research"
  - "automated research"
  - "do third-party research"
  - "research-auto"
phase: -1
effort: high
model: opus
user-invocable: true
---

## 1. Entry conditions

This skill runs when one of the following applies:

- The user explicitly specifies the **"third-party research"** keyword + a product/topic
  keyword
- `intent-router` routes it: `"{product} third-party research then write"` →
  `research-auto` → `draft-req`
- A request to supplement the existing `inputs/discovery/competitor/` (`--augment` flag)

On entry, confirm the following with the PM once:

```
Running automated third-party research — confirming the following:
  - Product / topic: {product}
  - Domain keywords: {domain}
  - Research region: {domestic / global / both}
  - Handling of existing inputs/discovery/competitor/: [augment / replace]
```

---

## 2. Preconditions

### 2-1. Tool availability

| Tool | Purpose | Required |
|---|---|---|
| `WebSearch` | seed search / competitor identification | required |
| `WebFetch` | detailed collection from competitors' official pages | required |

If a tool is unavailable, stop immediately and report to the PM. Working around it or
filling in with estimates is absolutely forbidden.

### 2-2. Product / topic ambiguity check

If the product name is a common noun or could be a homonym, get supplementary keywords from
the PM.
(e.g. "DB" → whichever of "DBaaS / managed database / our own DBaaS" is meant)

### 2-3. Existing-file branch

If `Planning-Agent-Hub/PROJECTS/{product}/inputs/discovery/competitor/` exists:

| Flag | Behavior |
|---|---|
| `--augment` | keep existing files + add new competitors |
| `--replace` | back up existing files (`.bak`) then write fresh |
| (none) | ask the PM to choose a branch |

---

## 3. Research procedure

### 3-A. Seed search (WebSearch)

Collect the top 10~20 results using the following keyword combinations:

- `{product} competitors`
- `{product} alternatives`
- `{product} comparison vs`
- `{domain} market share`
- `{domain} pricing 2025`
- `{domain} top providers`
- `{product} domestic market` (if domestic research is included)

Keep (title, URL, snippet, search date) for each search result in the memory buffer.

### 3-B. Competitor identification

Extract the following from the collected seed results:

- Company name + product name
- Domain classification (e.g. global cloud / domestic IDC / SaaS specialist, etc.)
- Frequency (how many results mentioned it)

Sort by frequency and select the **top 3~5** competitors.
If the PM has pre-specified particular competitors, include them with priority.

### 3-C. Per-competitor detail fetch (WebFetch)

For each competitor, fetch the following pages in sequence:

1. Official site main / product page — company·product overview
2. Pricing page — rate-plan table
3. Features page — key features / differentiators
4. SLA / terms / integration page (if available)

⚠ **Source URL + collection date (UTC) must always be preserved**. Assign a `[REF-NN]` ID
to every cited value.

On collection failure (404 / robots-blocked / private), mark the row `[unconfirmed:reason]`.
Filling in with estimates is forbidden.

### 3-D. Market overview fetch

Fetch the following items separately:

- TAM / SAM / SOM (figures + source where possible) — 1st/2nd-party sources such as
  Gartner / IDC / Korean KISDI, etc.
- 3~5 market trends (demand / pricing / technology axes)
- Entry barriers / differentiation points (regulatory / capital / technical)

Mark unobtained figures `[needs confirmation]`.

---

## 4. Output files

```
Planning-Agent-Hub/PROJECTS/{product}/
├── inputs/discovery/competitor/
│   ├── overview.md          # market overview + comparison matrix
│   ├── {competitor_1}.md    # competitor 1 detail
│   ├── {competitor_2}.md
│   └── {competitor_3}.md
└── drafts/
    └── D5.draft.md          # research.md (D5 format) auto-filled draft
```

### 4-1. File frontmatter (required)

Insert the following frontmatter into each auto-generated file:

```yaml
---
generated_by: research-auto
generated_at: YYYY-MM-DD
product: {product}
sources:
  - id: REF-01
    url: https://...
    fetched_at: YYYY-MM-DD
    title: "..."
    reliability: 1st-party | 2nd-party | 3rd-party
status: draft  # locked to draft until PM approval
approved_by: null
approved_at: null
---
```

### 4-2. overview.md body structure

Write to meet the draft-req SKILL.md competitor threshold (comparison-matrix rows 3+ /
`[not entered]` cells under 50%):

- §1 Market definition (TAM/SAM/SOM)
- §2 Market trends (3~5)
- §3 Entry barriers / differentiation points
- §4 Competitor comparison matrix (3+ rows)

### 4-3. Per-competitor file body structure

Same structure as D5 §3~§5:

- Company / product overview
- Pricing policy (rate-plan table)
- Key features / differentiators
- Weaknesses / constraints
- Source ID mapping

---

## 5. Filling in the D5 format

Copy `templates/standard/D5_research.md` to
`Planning-Agent-Hub/PROJECTS/{product}/drafts/D5.draft.md`, then auto-substitute the
following placeholders:

| Placeholder | Substituted value |
|---|---|
| `{{PRODUCT_NAME}}` | product name |
| `{{DOC_ID}}` | auto-generated (e.g. `RES-{product}-001`) |
| `{{VERSION}}` | `1.0-draft` |
| `{{DATE}}` | generation date (YYYY-MM-DD) |
| `{{TAM}} / {{SAM}} / {{SOM}}` | extracted figures (`[needs confirmation]` if absent) |
| `{{COMPETITOR_1~3}}` | extracted competitor names |
| `{{REF}} / {{REF_1~3}}` | source URLs (linked to REF-NN IDs and the §7-1 source list) |
| `{{T-01~03}}` | trends (`[needs confirmation]` if absent) |

⚠ Filling with estimates·hallucination is forbidden. Mark unobtained areas
`[needs confirmation]` or `[unconfirmed:reason]`.

---

## 6. PM approval gate (required — no bypass)

Automated generation results **stop in draft state**. After outputting the following
notice, do not auto-transition to the next skill (draft-req / render):

```
✋ Automated third-party research complete — PM approval needed

Generated files:
  - inputs/discovery/competitor/overview.md (market overview)
  - inputs/discovery/competitor/{N}.md ({N} competitors)
  - drafts/D5.draft.md (D5 format auto-filled)

Collection statistics:
  - Seed search results: {NN}
  - Competitor fetch success: {N}/{M}
  - [needs confirmation] cells: {N}
  - 1st-party source ratio: {NN}%

Next steps:
  1. Review each file — especially pricing/feature figure accuracy
  2. Verify cited URLs (frontmatter sources)
  3. PM manually supplements [needs confirmation] cells
  4. Run the following command after PM approval:
     - /draft-req {product}     (synthesize the 3 discovery streams)
     - /render {product} --push (publish D5)

Approval command:  /research-auto --approve {product}
Regenerate:         /research-auto {product} --regenerate
Partial supplement:  /research-auto {product} --augment
```

At the moment of PM approval (`--approve`), update frontmatter `status: draft` →
`status: approved`, and record `approved_by` / `approved_at`.

---

## 7. Fact-check safety net

The automated generation result guarantees compatibility with
`scripts/fact_preservation_check.py` (if present):

- **Numeric/unit preservation**: preserve unit-price notations like "$0.018/GB per month"
  exactly as-is, without conversion
- **Table format preservation**: keep the D5 format's `<!-- col-widths: ... -->` comment
- **Source citation preservation**: every numeric/citation cell requires a `[REF-NN]` ID
- **Quote official text in double quotes**: use quotation marks + cite the source when
  quoting official documents

Per `project-rules.md`'s decision management / open-items / Confluence sync policy:

- Every item requiring a PM decision during automated generation is registered in
  `open-issues.md` with an `[RA-NN]` ID
- Confluence sync is performed only at the `/render --push` step after PM approval
  (research-auto itself never pushes)

---

## 8. Limitations

| Limitation | Mitigation |
|---|---|
| Web information freshness (as of search time) | specify `fetched_at` in frontmatter + recommend periodic re-run |
| Non-public pricing / negotiated rates | mark `[unconfirmed:non-public]` — PM manually supplements |
| Lack of domestic-market-specific information | separate via `--augment` for PM supplementation |
| LLM hallucination risk | every figure requires a source URL / mark unobtained ones `[needs confirmation]` |
| Dynamic page / SPA fetch failure | mark `[unconfirmed:fetch-fail]` |

**Automatic publishing is absolutely forbidden**. Bypassing the PM approval gate breaks the
integrity of this skill.

---

## 9. Workflow connections

```
intent-router
    ↓ ("{product} third-party research then write")
research-auto  ← this skill
    ↓ (PM approval gate)
draft-req      ← synthesizes 3 discovery streams (competitor / stakeholder / product-audit)
    ↓
render --push  ← publish D5 / D1
```

- **Precedes**: `intent-router` (routing branch)
- **Follows**:
  - `draft-req` — synthesizes the competitor stream with stakeholder / product-audit
  - `render --push` — publishes D5 (PM approval required)

---

## 10. Usage examples

```bash
# Automated third-party research for a new product (full fresh generation)
/research-auto dbaas
# → generates inputs/discovery/competitor/ + drafts/D5.draft.md

# Supplement existing research (add new competitors)
/research-auto dbaas --augment
# → keeps existing files + adds only new competitor .md files

# Full regeneration (back up existing, write fresh)
/research-auto dbaas --regenerate
# → backs up inputs/discovery/competitor/*.md → *.md.bak, then writes fresh

# PM approval (frontmatter status → approved)
/research-auto dbaas --approve

# Publish D5 after approval
/draft-req dbaas
/render dbaas --push
```

---

## 11. session-log record

When this skill runs, add one row to `session-log.md` in the following format:

```markdown
| -1 (Discovery / Auto) | {UTC timestamp} | /research-auto | {N} competitors / {NN} seed searches / {N} [needs confirmation] / status: draft |
```

Add a separate row in the same format upon PM approval (`status: approved`).
