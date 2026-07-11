# Macro Annotation Reference (templates/standard/ Author Guide)

> **Purpose**: a practical guide collecting, in one place, the macro annotations available when authoring/extending `templates/standard/D*.md` templates.
> **Spec SSoT**: `orange-pm-plugin/skills/render/publication-syntax.md` (this document is a summary/practical excerpt of it).
> **Validation**: `scripts/lint_publication_syntax.py` (L1-L7).

## 0. Basic Principles

1. Markdown is canonical — do not author XML directly
2. Every macro is expressed as a fenced div (`::: {.class}`) or frontmatter
3. `md_to_storage.py` performs a deterministic conversion at publish time
4. Validation: recommended to run `lint_publication_syntax.py --input <file>` after authoring

---

## 1. Standard Frontmatter Structure

```yaml
---
title: "[D1 Title] {{PRODUCT_NAME}}"     # Confluence page title
wo_id: PX-DIRECT-D1                    # or Track A's cluster ID (Phase 5 active)
type: requirements                     # requirements|policy|screen|meetings|research|etc
layer: DIRECT                          # B (common) | C (product) | DIRECT (Track B/C single)
version: 1.0
last_updated: 2026-05-30

publication:
  # top info macro (optional)
  header:
    style: info                        # info|warning|note|tip
    body: |
      **{{PRODUCT_NAME}} Definition**

      doc_id: {{DOC_ID}} Version: {{VERSION}} Last updated: {{DATE}}

  # meta area — references/table of contents/change-history, etc. (optional)
  meta:
    layout: two_equal                  # single|two_equal|three_equal
    cells:
      - panel:
          title: "References"
          body: |
            - [[page:[Policy Definition] {{PRODUCT_NAME}}]]
      - change_history: 5

  # Phase 3 color state (automatic — do not set manually)
  color_state: null
---
```

**Whitelist (additional fields besides publication.*)**: `title`, `wo_id`, `type`, `layer`, `version`, `last_updated`.  
**Removed (prefilter)**: authoring metadata, self-verification sections, prohibitions, Workflow Connections, etc.

---

## 2. Body Macros

### 2.1 Panel — Section Container (most frequently used)

```markdown
::: {.panel section="§N Section Title"}
## §N Section Title

### §N-1 Subtitle
Body text ...
:::
```

**Style Mapping** (`style=` attribute):

| style | Color (border / title) | Use |
|---|---|---|
| `common` (default, can be omitted) | `#24FE00` / `#002FD5` | Common/product policy standard |
| `product` | `#0050E5` / `#FFFFFF` | Product-specific emphasis |
| `tbd` | `#FF4D4F` / `#FFFFFF` | TBD / needs review |
| `warning` | `#FAAD14` / `#FFFFFF` | Warning |
| `info` | `#1890FF` / `#FFFFFF` | Informational |

**Required**: `section="..."` (lint L2). **Optional**: `style="..."` (lint L3 — allowed values only).

### 2.2 Callouts — info / warning / note / tip

```markdown
::: {.info}
Informational message
:::

::: {.warning}
Caution
:::
```

→ `<ac:structured-macro ac:name="info|warning|note|tip">`. Placed inline in the body flow, with no layout wrapper.

### 2.3 Expand — Collapsible Area

```markdown
::: {.expand title="Details"}
Body text to hide
:::
```

### 2.4 Code Blocks

```markdown
​```python
def foo():
    return 42
​```
```

→ `<ac:structured-macro ac:name="code">` + `<ac:plain-text-body><![CDATA[...]]>`.  
Specifying a language fence is recommended (lint L4 — known languages): `python`, `bash`, `json`, `yaml`, `sql`, `javascript`, `typescript`, `markdown`, `xml`, `html`, `css`, `text`, `mermaid`, `plantuml`, `diff`, etc.

---

## 3. Inline Macros

### 3.1 Page Link — Reference Another Confluence Page

```markdown
[[page:[Policy Definition] {{PRODUCT_NAME}}]]
```

→ `<ac:link><ri:page ri:content-title="..."/></ac:link>`.  
For consistency, the title pattern should follow the `[D-type] {{PRODUCT_NAME}}` format.

### 3.2 Automatic Macros

| MD | XML Output | Use |
|---|---|---|
| `{{toc}}` | `<ac:structured-macro ac:name="toc"/>` | Auto-generates the body's table of contents |
| `{{change_history N}}` | `<ac:structured-macro ac:name="change-history">` + limit N | The N most recent change-history entries |

### 3.3 Placeholder — Substituted at Publish Time

| Notation | Substitution Timing | Source |
|---|---|---|
| `{{PRODUCT_NAME}}` | publish stage | product metadata |
| `{{DOC_ID}}` | publish stage | frontmatter |
| `{{VERSION}}` | publish stage | frontmatter |
| `{{DATE}}` | publish stage | publish date |
| `{{WO_ID}}` | publish stage | frontmatter |

These 5 are the allowed list for lint L5 WARN. Using any other `{{...}}` triggers a WARN → can be ignored if it is intentional to the template.

---

## 4. Writing Tables

```markdown
| Item | Content |
|---|---|
| **Purpose** | The purpose of this policy document |
| **Scope** | All |
```

→ `<table class="relative-table wrapped" style="width: 90%;">` + colgroup (evenly distributed by default).

**Specifying Column Widths** — HTML comment directive:

```markdown
<!-- col-widths: 15%, 85% -->
| Item | Content |
|---|---|
| Purpose | The purpose of this policy document |
```

**Validation**: the header and body rows must have the same number of columns (lint L7).

---

## 5. Phase 3 — Color Cycling (reserved)

Auto-generated once color cycling is active. **Template authors must not use this manually.**

```markdown
[changed text]{.color-green}      ← most recent change (#00B050)
[previous change text]{.color-blue}    ← previous change (#0050E5)
normal text                        ← default (black, no span applied)
```

The automatic cycling mechanism is injected at publish time by `md_to_storage.py` + `diff_blocks.py` once Phase 3 is active.

---

## 6. Template-Authoring Checklist

When adding a new deliverable template (e.g. D6, Dα_new):

1. **File location**: `orange-pm-plugin/templates/standard/{D-type}_{name}.md`
2. **Frontmatter**:
   - [ ] `title` pattern (`[D-type] {{PRODUCT_NAME}}`)
   - [ ] `type` category (`requirements|policy|screen|meetings|research|etc`)
   - [ ] `layer` (`DIRECT` by default, `C` when Track A applies)
   - [ ] `publication.header` (optional, when a page-top notice is needed)
   - [ ] `publication.meta` (optional, references/table of contents/change-history)
3. **Body**:
   - [ ] section separation by `::: {.panel section="..."}` units
   - [ ] consistent `## §N` heading pattern (matching the panel section)
   - [ ] consistent table column count (header ↔ body)
   - [ ] code-block language fence specified
   - [ ] use the 5 standard placeholders (note in the README if others are intentional to the template)
4. **Validation**:
   - [ ] `python scripts/lint_publication_syntax.py --input templates/standard/{file}.md` → FAIL 0
   - [ ] `python scripts/md_to_storage.py --input ... --output /tmp/x.xml --validate` → exit 0
   - [ ] `python scripts/round_trip_test.py` passes in full
5. **Documentation**:
   - [ ] update the file-listing table in `templates/standard/README.md`
   - [ ] register the new deliverable's Confluence page-title pattern

---

## 7. Frequently Asked Patterns

### Q. I want to add an extra callout inside a section

```markdown
::: {.panel section="§3 Policy"}
## §3 Policy

Body text ...

::: {.warning}
This policy will be deprecated starting from v2.0.
:::

Continuing body text ...
:::
```

Nesting is possible — info/warning etc. can be freely placed inside a panel.

### Q. Multi-line text inside a table

```markdown
| Item | Description |
|---|---|
| A | first line<br/>second line |
```

Use inline `<br/>` or simple spacing. If multiple paragraphs are needed, splitting into a panel is recommended.

### Q. Mixing Korean and English in a page title

```yaml
title: "[Policy Definition] DBaaS for Berkeley"
```

Within the quotes, Korean, English, spaces, and parentheses are all allowed. No backslash escaping is needed.

### Q. My template's placeholder shows up as a lint WARN

L5 (unresolved placeholder) is a WARN (non-blocking). If it is intentional to the template, leave it as-is. It should be substituted by the template's user at the draft stage.

---

## 8. Quick Converter / Lint Commands

```bash
# Template lint
python orange-pm-plugin/scripts/lint_publication_syntax.py \
   --input orange-pm-plugin/templates/standard/D1_requirements.md

# Template → XML conversion (with validation)
python orange-pm-plugin/scripts/md_to_storage.py \
   --input orange-pm-plugin/templates/standard/D2_policy.md \
   --output /tmp/D2.xml --validate

# Template round-trip stability (all templates in bulk)
python orange-pm-plugin/scripts/round_trip_test.py
```

---

## 9. References

- Spec SSoT: `orange-pm-plugin/skills/render/publication-syntax.md`
- Policy: `Planning-Agent-Hub/CONTEXT/project-rules.md` (Confluence sync procedure)
- Converters: `scripts/md_to_storage.py`, `scripts/storage_to_md.py`
- Validation: `scripts/lint_publication_syntax.py`, `scripts/render_verify.py`
