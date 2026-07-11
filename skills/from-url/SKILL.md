---
name: from-url
description: |
  Takes a Confluence URL as the entry point and converts/reflows the page body into the repo's
  canonical MD. Invoked when the user expresses intent such as "research competitors then write
  to this URL" or "write URL_B in the format of URL_A" (routed by intent-router or called
  directly by the PM).

  Main behavior:
    1. Extract page_id from the URL (the https://confluence.../pages/{id} pattern)
    2. Query (get) the wiki connector → collect the snapshot JSON
    3. Convert to MD with storage_to_md.py (the reverse of the publication-syntax.md spec)
    4. Save to inputs/confluence-pulls/{page_id}.md (the canonical reflow entry point)
    5. Auto-generate meta.json (page_id, title, version, _color_state.baseline=true)
    6. Branch on URL intent (target / template / context) and recommend follow-up skills

  This skill **only reads** the Confluence page body. Publishing/editing is handled by
  `render --push` (direct Confluence editing is prohibited by policy — project-rules.md).
triggers:
  - "given a URL"
  - "this page"
  - "Confluence URL"
  - "https://confluence"
  - "report in this format"
  - "at this url"
  - "with this url"
  - "write to this page"
  - "write in this format"
  - "from-url"
phase: any
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


## 1. Entry conditions

This skill activates when any of the following hold:

- The user message contains 1–2 `https://confluence...` URLs together with an action verb
  such as "write/report/format/reference"
- Natural-language triggers: "write to this URL", "report on this page", "in this format",
  "write URL_B the same way as URL_A"
- intent-router detects URL-entry intent and routes to this skill
- The PM invokes it directly with `/from-url <URL>`

Even when there is no URL and only an ID is given, e.g. "page_id 12345", the skill behaves the
same starting from **Step 2** (URL parsing is skipped).


## 2. URL parsing

Deterministically extract the following information from the Confluence URL:

| Info | Regex | Example |
|---|---|---|
| `page_id` | `pages/(\d+)` | `pages/12345` → `12345` |
| `spaceKey` | `spaces/([^/]+)/pages` | `spaces/TEAMX/pages/...` → `TEAMX` |
| `title slug` | `pages/\d+/([^/?#]+)` | slug at the end of the URL (optional) |

Supported URL forms:
- `https://confluence.example.com/wiki/spaces/{SPACE}/pages/{PAGE_ID}/{TITLE}`
- `https://confluence.example.com/pages/viewpage.action?pageId={PAGE_ID}`
- `https://confluence.example.com/display/{SPACE}/{TITLE}` — this form has no page_id in the
  URL, so ask the PM to provide the page_id directly.

If extraction fails, give the PM a one-line prompt to enter the page_id directly, then stop.


## 3. Prerequisite checks

1. **Wiki connector availability**: verify the wiki connector (an MCP tool the user has
   connected — e.g. Confluence) using the CONNECTORS.md detection protocol. Prefer the
   `CONTEXT/connectors.md` mapping; auto-detect if absent. The discovered tool must support a
   query (get) that includes the page body (storage XML) and version, in order to build the
   snapshot JSON shape.

   If the connector is absent or unsupported, this skill does not operate (the snapshot JSON
   shape is required). Print the guidance from CONNECTORS.md and note that "manual export →
   the `--xml-file` option can be used as a workaround."

2. **PM Confluence permissions**: whether the page is readable. If the `get` attempt fails with
   401/403, report the permission issue + present the alternative (manual export → use this
   skill's `--xml-file` option as a workaround).

3. **User-intent branch** (decided by intent-router or PM utterance):

   | Intent | Meaning | Follow-up skill |
   |---|---|---|
   | **target URL** | The page to write to (empty or a new page) | `/render --push` |
   | **template URL** | Format source (structure only, discard the body) | `/extract-template` |
   | **context URL** | Reference material (competitor research/requirements-analysis input) | `/draft-req` or `/research` |

   Intent classification is decided from the user's utterance:

   - "write here" / "fill in this page" → **target**
   - "in this format" / "look at this and do the same" → **template**
   - "reference this" / "analyze based on this" → **context**

   If ambiguous, do not guess — ask the PM back with a one-line question.

4. **Product context**: if `{product}` is unspecified, confirm with the PM which PROJECTS
   subdirectory to reflow into. For a new product, recommend running `/ingest {product}` first.


## 4. Conversion steps

### 4-A. Snapshot collection (model's responsibility)

External calls are performed only through wiki-connector tool calls — scripts are for local
file processing only (the auth/tool separation principle, CONNECTORS.md — same pattern as
`/render`):

```bash
mkdir -p Planning-Agent-Hub/PROJECTS/{product}/inputs/confluence-pulls
```

Call the page query (get) operation matching the schema of the discovered wiki tool — target:
page_id `{PAGE_ID}`. From the response, extract id/title/version/body (storage XML) and save it
as JSON in the shape below to `/tmp/{PAGE_ID}.snapshot.json`.

Expected snapshot JSON shape (storage_to_md uses only these keys):

```json
{
  "id": "12345",
  "version": {"number": 7, "when": "2026-05-28T..."},
  "title": "...",
  "body": {"storage": {"value": "<xml>...</xml>"}}
}
```

### 4-B. Snapshot → MD reverse conversion

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/storage_to_md.py \
  --input /tmp/{PAGE_ID}.snapshot.json --from-snapshot \
  --output Planning-Agent-Hub/PROJECTS/{product}/inputs/confluence-pulls/{PAGE_ID}.md
```

The converter follows the `publication-syntax.md` §8 round-trip spec — body, tables, code
blocks, and panels are 100% preserved; user-defined macros edited directly in Confluence have
only their text preserved.

If exit code 1 (XML parse failure) or 2 (unsupported-macro warning) occurs, just report it to
the PM and continue to the next step (the text is still preserved).


## 5. Auto-generate meta.json

Immediately after reflowing, generate `{PAGE_ID}.meta.json` in the same directory.
Take `id` / `title` / `version.number` from the snapshot JSON and store them in the following structure:

```json
{
  "id": "12345",
  "title": "Original page title",
  "source_url": "https://confluence.../pages/12345",
  "pulled_at": "2026-05-30T...",
  "pulled_version": 7,
  "intent": "target | template | context",
  "_sync": {
    "last_published_version": null,
    "last_published_at": null
  },
  "_color_state": {
    "publish_round": 0,
    "previous_source_hash": null,
    "previous_green_regions": [],
    "baseline": true
  }
}
```

`_color_state.baseline = true` guarantees the first round of Phase 3 color cycling
(publication-syntax.md §6.4).

If a `{PAGE_ID}.meta.json` already exists, **do not overwrite it** — notify the PM of the
conflict with the existing metadata and confirm whether to update only `pulled_version`.


## 6. Follow-up guidance by branch

After saving, recommend a follow-up skill based on intent:

| Intent | Recommendation |
|---|---|
| **target** | If the page is empty, apply the format and write/publish with `/render {product} --push`. If existing content is present, apply the "overwrite gate" from step 8. |
| **template** | Extract the format with `/extract-template inputs/confluence-pulls/{PAGE_ID}.md` → register it in `templates/standard/{name}.md` or `templates/render/custom/{name}.md`. |
| **context** | Register as a source for `/draft-req {product}` (requirements-authoring input) or `/research {product}` (research input). Confirm with the PM which work order to feed it into. |

Print the recommendation as a one-line notice and do not auto-execute it.


## 7. Usage examples

```bash
# (1) New authoring — apply the format to an empty page, then fill it in
/from-url https://confluence.example.com/wiki/spaces/G/pages/12345 --target D2
# → inputs/confluence-pulls/12345.md (empty body)
# → follow-up: /render dbaas WO-POL-001 --push

# (2) Extract a format — write URL_B based on URL_A
/from-url https://confluence.../pages/A --as-template
# → inputs/confluence-pulls/A.md + intent=template
# → follow-up: /extract-template inputs/confluence-pulls/A.md
/from-url https://confluence.../pages/B --target D2 --template-from A
# → apply the A format to the B skeleton

# (3) Competitor research reference — context intent
/from-url https://confluence.../pages/77777 --as-context
# → inputs/confluence-pulls/77777.md + intent=context
# → follow-up: /research dbaas (registers this URL as a source)

# (4) Augmenting an existing page — sync-check guidance after reflow
/from-url https://confluence.../pages/12345 --augment
# → detects conflict with existing meta.json → after PM confirmation, update only pulled_version

# (5) When only the page_id is known
/from-url 12345 --product dbaas --target D1
```


## 8. Cautions

- **Direct Confluence editing is prohibited by policy (project-rules.md §Confluence sync)**:
  This skill only reflows the page body. If the PM has edited the body in the Confluence WebUI,
  it must be treated as REMOTE-DRIFT and absorbed via `/render --check-sync --with-remote` +
  `--apply-inbox`, not via this skill. This skill is only the reflow entry point for **new input
  material**.

- **Insufficient URL permissions** (`401/403`): give a clear error message + guidance on the
  alternative ("export from the Confluence WebUI → use the `--xml-file` option with the XML
  file path").

- **Overwrite gate when existing page content is present**:
  If the intent is target and the page body is not empty, explicitly confirm with the PM:
  - Overwrite: discard the existing body, apply the new format
  - Merge: existing body + append new sections (manual merge)
  - Append as appendix: preserve the existing body, append new sections at the end

  Hold off recommending render --push until one of the three options is clearly chosen.

- **Unsupported storage_to_md macros**: only the text is preserved and the macro structure is
  lost. Report the lost items to the PM and recommend manual augmentation.

- **page_id collision**: if two products reflow the same URL, `meta.json.id` becomes
  duplicated. This skill works around it via per-product directory isolation, but the
  render --push step may block it as an SSoT violation (see `CONTEXT/ssot-boundary.yml` —
  scaffolded by `/init-hub`). However, if this file does not exist or owner is empty,
  render --check-ssot only warns and passes (no hard-fail, graceful degrade) — this skill's
  reflow itself always runs regardless of whether ssot-boundary.yml exists.


## 9. Workflow connections

```
              ┌─── target  ──→  /render --push (step 6-1 publication conversion)
              │
[Confluence URL] ──→ /from-url ──┼─── template ──→  /extract-template
              │                        ↓
              │                  register in templates/standard/ or
              │                  templates/render/custom/
              │
              └─── context ──→  /draft-req | /research
                                  (registers the URL as an input source)
```

- **Precedes**: `intent-router` (detects URL entry → routes to this skill)
- **Precedes (when called directly)**: none — direct entry via PM utterance
- **Follow-up (by intent)**:
  - target → `/render` or `/render --push`
  - template → `/extract-template`
  - context → `/draft-req` / `/research` / `/research-auto`
- **Spec references**:
  - `publication-syntax.md` (syntax of the MD produced by storage_to_md)
  - `project-rules.md` §Confluence sync (canonical policy)


## 10. Output file list

| File | Creation condition | Content |
|---|---|---|
| `inputs/confluence-pulls/{PAGE_ID}.md` | Always | MD reflow of the snapshot body |
| `inputs/confluence-pulls/{PAGE_ID}.meta.json` | On a new reflow | page_id/title/version + `_color_state.baseline=true` |
| `/tmp/{PAGE_ID}.snapshot.json` | Always (temporary) | Raw JSON from the wiki connector query (get) |
| `inputs/confluence-pulls/{PAGE_ID}.warnings.log` | On storage_to_md warnings | List of unsupported-macro/parse warnings |
