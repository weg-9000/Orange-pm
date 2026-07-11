---
name: extract-template
description: |
  Extracts structural patterns (heading tree, panel pattern, table
  convention, terminology) from a wiki page (URL_A — e.g. Confluence) and
  converts them into a dynamic template. Triggered only by the URL_A
  option input of Track C (Template-Copy). The built-in template
  (templates/standard/) is the default — this skill is an override.

  Extracted items:
    1. Heading structure (§N pattern + depth)
    2. Panel usage pattern (style distribution, section naming convention)
    3. Table column convention (frequently occurring column names + width)
    4. Terminology (frequently occurring domain terms)
    5. Macro usage distribution (info/warning/expand frequency)
triggers:
  - "use this template"
  - "follow this template"
  - "URL_A"
  - "like this URL"
  - "write in this format"
  - "extract template"
phase: any
effort: medium
user-invocable: true
---

## 0. Position — an optional step in the Track C / Template-Copy path

```
[PM says]  "Look at the URL_A template and write it to URL_B"
   │
   ├─ from-url(URL_A, --as-template)   ← prerequisite (pulls the page → inputs/confluence-pulls/{ID}.md)
   │
   ├─ extract-template                 ← this skill (extract structure → templates/extracted/{ID}.template.md)
   │      └─ PM confirmation gate
   │
   ├─ from-url(URL_B, --target D2, --template-from pages/A)
   │
   └─ render / write / cluster draft   ← follow-up (uses the extracted template as the base)
```

**The default behavior is not to invoke this skill** — the built-in
template (`orange-pm-plugin/templates/standard/D*.md`) is the SSoT.
This skill is activated only when the user explicitly designates URL_A as
the template source.

---

## 1. Entry Conditions

| Condition | Required / Optional | Notes |
|---|---|---|
| The user **explicitly** designates URL_A (the template source) | Required | "follow this template", "like this URL", "--template-from" |
| The from-url skill has already pulled URL_A | Required | `inputs/confluence-pulls/{page_id}.md` exists |
| URL_A's body length / heading count ≥ threshold | Optional (recommended) | If headings < 3, extraction value is low — see §7 |
| Routed to "Track C / Template-Copy" by intent-router | Required | Non-explicit invocation is forbidden |

**Forbidden scenarios** (do not auto-invoke this skill):
- The normal authoring flow of Track A (cluster-based authoring)
- Track B single-definition-document authoring without URL_A specified
- A normal authoring request for which the built-in template suffices

---

## 2. Preconditions (Preflight)

1. **from-url prerequisite**: `inputs/confluence-pulls/{page_id}.md` must
   exist.
   - If not: this skill stops and instructs the PM to run from-url first.
     ```
     URL_A has not been pulled yet.
     First fetch the page with `/from-url <URL_A> --as-template`.
     ```
2. **publication-syntax standard compatibility check**: the pulled MD
   must use fenced divs (e.g. `::: {.panel}`) for high-precision
   extraction to be possible. If non-standard, fall back to the partial
   extraction mode in §7.
3. **Output directory**: create
   `orange-pm-plugin/templates/extracted/` if it does not exist.

---

## 3. Extraction Procedure

The full extraction is performed deterministically in 5 steps. Each step
is independent; on failure, only that item is marked missing and
processing continues.

### 3-A. Heading Structure Extraction

- Input: the body of `inputs/confluence-pulls/{page_id}.md`
- Regex: `^(#+)\s+(.+)$`
- Recognizes `§N` / `§N-M` patterns (`§` + number, with sub-levels
  separated by `-`)
- Output:
  - heading tree (depth + text + appearance order)
  - §N sequence (start number, end number, whether any are missing)

```
Example extraction result:
H2  §1 Policy Overview       (line 22)
H3  §1-1 Purpose             (line 27)
H3  §1-2 Scope of Application (line 35)
H2  §2 Common Policy         (line 54)
...
```

### 3-B. Panel Pattern Extraction

- Regex: `^:::\s*\{\.panel\s+section="([^"]+)"\s*(.*?)\}$`
- Extracted fields:
  - `section` value (full list of panel section names)
  - `style` attribute (normalized to `common` if absent)
- Statistics:
  - frequency by style (`common`/`product`/`tbd`/`warning`/`info`)
  - section naming convention (§N prefix? localized language? mixed with
    English?)

### 3-C. Table Convention Extraction

- Extract table header rows (line before is `|...|`, next line is
  `|---|---|`)
- Match the HTML comment `<!-- col-widths: ... -->` immediately preceding
  a table
- Statistics:
  - table count
  - average column count, max/min
  - frequently occurring column names (e.g. "Item/Content", "FR ID/Priority",
    "Decision/Owner/Deadline")
  - proportion of tables using the col-widths directive

### 3-D. Terminology Extraction

- Noun phrases by frequency (simple heuristic):
  - Extract 2–6 character noun phrases from the source language (strip
    particles/endings)
  - Collect English/abbreviations (e.g. `SLA`, `API`, `DBaaS`) separately
  - Cross-reference against the in-house domain dictionary
    (`CONTEXT/glossary.md`, if present)
- Save the top N (=20) as the result
- Note mixed English/local-language patterns (e.g. "DBaaS instance")
  separately

### 3-E. Macro Distribution

- Invocation counts:
  - frequency of each of `::: {.info}`, `{.warning}`, `{.note}`, `{.tip}`,
    `{.expand}`
  - classification of usage location (inside a panel / directly in the body)
- Code-block language distribution (`mermaid`, `python`, `bash`, ...)
- Inline macros: occurrence count of `{{toc}}`, `{{change_history N}}`,
  `[[page:...]]`

---

## 4. Output Format

### 4.1 File Location

```
orange-pm-plugin/templates/extracted/{page_id}.template.md
```

If the file already exists: ask the PM whether to overwrite it or add a
suffix (`.v2.template.md`).

### 4.2 File Structure (semi-template — placeholder skeleton)

```markdown
---
extracted_from:
  page_id: "{ID}"
  title: "{original page title}"
  extracted_at: YYYY-MM-DD
  source_pull: inputs/confluence-pulls/{page_id}.md

publication:
  header:
    style: info
    body: |
      **{{PRODUCT_NAME}} Definition Document (based on the URL_A template)**

      doc_id: {{DOC_ID}} Version: {{VERSION}} Last Modified: {{DATE}}
  meta:
    layout: two_equal          # inferred meta layout from the original
    cells:
      - panel:
          title: "Reference Materials"
          body: |
            - [[page:{{LINK_PLACEHOLDER}}]]
      - change_history: 3
---

<!-- ============================================ -->
<!-- HEADING TREE (extracted from the original, placeholder-ized) -->
<!-- ============================================ -->

::: {.panel section="§1 {SECTION_1_NAME}"}
## §1 {SECTION_1_NAME}

### §1-1 {SUBSECTION_1_1_NAME}

{{write content here}}

### §1-2 {SUBSECTION_1_2_NAME}

<!-- col-widths: {COL_WIDTHS_HINT} -->
| {COL_1_NAME} | {COL_2_NAME} |
|---|---|
| {{content}} | {{content}} |
:::

::: {.panel section="§2 {SECTION_2_NAME}"}
## §2 {SECTION_2_NAME}
...
:::

<!-- ============================================ -->
<!-- EXTRACTION STATISTICS (for PM review — removed at publication) -->
<!-- ============================================ -->
<!-- heading: H2=N, H3=M, max_depth=D -->
<!-- panel:  common=X, product=Y, tbd=Z, warning=W, info=V -->
<!-- table:  count=N, avg_cols=X, freq_cols=[item,content,...] -->
<!-- macro:  info=N, warning=M, expand=K, code_blocks=L -->
<!-- term:   top20=[SLA, DBaaS, instance, ...] -->
```

**Principles**:
- All free text is replaced with a `{{...}}` placeholder (lint L5 WARN —
  accepted, since this is the intended template behavior).
- Section/column names are also marked with `{...}` to indicate the PM can
  edit them.
- Statistics are preserved as HTML comments (`<!-- ... -->`) — removed by
  the publication-prefilter.

---

## 5. PM Confirmation Gate

Present the extraction result summary to the PM and get confirmation on
whether to proceed. Automatic proceeding is forbidden.

```
Extraction of URL_A "{original page title}" complete.

  Heading:   H2 = 5, H3 = 14, max depth = 3
  Panel:     common = 4, tbd = 1, info = 0  (total 5)
  Table:     8 (average 3 columns). Frequent columns: Item/Content, FR ID/Priority/Content
  Macro:     info = 2, warning = 1, expand = 3, code = 0
  Terms:     top — SLA, DBaaS, instance, backup, recovery, ...

→ templates/extracted/{page_id}.template.md created.

Proceed with authoring URL_B using this skeleton?
  (y) Proceed
  (e) Tell me what to change — add/remove headings, adjust style, etc.
  (n) Cancel — switch to the built-in template
```

Example handling of PM edit input:
- "Add §3" → insert `::: {.panel section="§3 {SECTION_3_NAME}"}` into the template
- "style tbd → warning" → bulk-change the panel attribute
- "Clean up table column names" → replace with the user-provided column names

---

## 6. Follow-up Routing

After PM approval, hand off this template to the following skill.

| Follow-up skill | Handoff method |
|---|---|
| `from-url` (pull URL_B) | pass this template's path via the `--template-from pages/{page_id}` flag |
| `write` / cluster draft | `--template templates/extracted/{page_id}.template.md` |
| `render` | same — `--template` flag |

The follow-up skill uses this template as the base **instead of the
built-in template**. publication-syntax validation applies identically.

---

## 7. Extraction Failure / Partial Extraction Cases

| Situation | Behavior |
|---|---|
| URL_A does not use fenced divs (only old-style storage XML exists) | Extract only heading + table; panel statistics are "n/a". Notify the PM: "non-standard area — skeleton only provided" |
| Heading count < 3 | Notify: "Low value in extracting a template. The built-in template (`templates/standard/D*.md`) is recommended", then stop this skill |
| from-url pull failed (permission / 404) | The from-url skill already errored → this skill refuses to enter at all |
| Empty page / 0-character body | Explicit error: "URL_A is empty — extraction not possible" |
| Multiple publication-syntax lint FAILs (missing panel section, etc.) | Partial extraction + print a warning. PM supplements manually |

---

## 8. Workflow Connections

```
Prerequisite (required):
  /from-url <URL_A> --as-template
     → inputs/confluence-pulls/{page_id}.md

This skill:
  /extract-template <page_id or URL_A>
     → templates/extracted/{page_id}.template.md
     → PM confirmation gate

Follow-up (choose one):
  /from-url <URL_B> --target D2 --template-from pages/{page_id}
  /write   --template templates/extracted/{page_id}.template.md
  /render  --template templates/extracted/{page_id}.template.md [--push]
```

---

## 9. Usage Examples

### 9.1 Standard Flow (URL_A → URL_B)

```bash
# 1. Pull the URL_A template page
/from-url https://wiki.example.com/pages/123456 --as-template

# 2. Extract the template (this skill)
/extract-template 123456
# → templates/extracted/123456.template.md created, PM confirmation gate

# 3. After PM approval, pull the URL_B page + apply the template
/from-url https://wiki.example.com/pages/789012 --target D2 \
         --template-from pages/123456

# 4. Final render + push
/render --push
```

### 9.2 PM Edit Scenario

```bash
/extract-template 123456
# At the PM confirmation gate:
#   "Change §3's panel style from tbd → warning
#    and add a §5 (Operations Policy) section"
# → applies the template edit, then re-shows the confirmation gate

# After approval, proceed with follow-up work
```

### 9.3 Non-Standard Page (Partial Extraction)

```bash
/from-url https://wiki.example.com/pages/000111 --as-template
# The pulled MD does not use panel fenced divs (old version)
/extract-template 000111
# → "Non-standard — only heading + table were extracted. Panel skeleton needs manual supplementation"
# → templates/extracted/000111.template.md (partial)
```

---

## 10. Constraints / Prohibitions

- **COMMIT / PUSH forbidden** — this skill only produces the extraction
  result as a local file. No remote operations.
- Do not overwrite the extracted template into `templates/standard/` —
  keep it separate from the built-in template.
- Keep extraction statistics only as HTML comments — adding statistics
  fields to frontmatter is forbidden (violates the publication whitelist).
- Color spans (e.g. `{.color-green}`) are entirely removed during
  extraction — Phase 3 cycling automatically re-injects them at
  publication time.
- Automatically proceeding past the PM confirmation gate is forbidden.

---

## 11. References

- Specification SSoT: `orange-pm-plugin/skills/render/publication-syntax.md`
- Template authoring guide: `orange-pm-plugin/templates/standard/_macros.md`
- Prerequisite skill: `orange-pm-plugin/skills/from-url/SKILL.md`
- Comparison target (built-in template): `orange-pm-plugin/templates/standard/D*.md`
- Validation: `scripts/lint_publication_syntax.py` (applies identically to extraction results)
