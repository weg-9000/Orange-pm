# Built-in Standard Templates (templates/standard/)

> **Status**: Phase 1F migration output (Option A — MD-only canonical)
> **Predecessor**: `Planning-Agent-Hub/templates/confluence-xml/*.xml` (deprecated)

## Purpose

The **canonical MD templates** used when first creating a new product's
Confluence documents.
`md_to_storage.py` performs a deterministic, idempotent conversion to XML at
publish time.

Across Track A/B/C — this template is applied automatically even when the
user does not provide a separate "template URL" (Pattern 2's URL_A)
(spec: publication-syntax.md).

## File List

### Standard 5 (D1-D5)
| File | Deliverable | type | layer | Confluence Page-Title Pattern | LOC |
|---|---|---|---|---|---|
| `D1_requirements.md` | Requirements Definition | requirements | DIRECT | `[Requirements Definition] {{PRODUCT_NAME}}` | 156 |
| `D2_policy.md` | Policy Definition | policy | DIRECT | `[Policy Definition] {{PRODUCT_NAME}}` | 148 |
| `D3_screen.md` | Screen Design | screen | DIRECT | `[Screen Design] {{PRODUCT_NAME}}` | 141 |
| `D4_meetings.md` | Meeting Notes (rolling) | meetings | DIRECT | `[Meeting Notes] {{PRODUCT_NAME}}` | 198 |
| `D5_research.md` | Competitor Research | research | DIRECT | `[Competitor Research] {{PRODUCT_NAME}}` | 286 |

### etc Category (Dα — Optional)
| File | Deliverable | Use Case | LOC |
|---|---|---|---|
| `Dα_api.md` | API Spec | Products exposing a REST API | 252 |
| `Dα_db.md` | DB Schema | DBaaS / data-intensive products | 226 |
| `Dα_migration.md` | Migration Plan | System migration / data migration | 245 |

### Reference Documents
- `_macros.md` — macro annotation reference (template-author guide)

### D2/D3 in split-deliverable publication mode (fix-plan-dossier-publish-split)

Under Track A's `publication_mode: split-deliverable`, D2_policy.md /
D3_screen.md serve as the **skeleton frontmatter source** for
`render_transpose.py --template` (the body is filled from dossier §1/§2 via
transpose). In other words, the template itself is left as-is, and only the
frontmatter of the published outputs `reports/render/02-policy.assembled.md`
/ `03-screen-design.assembled.md` is taken from this template. The
`is_common_shell` field in `cluster-draft.md` determines the D3 common-shell
appendix routing.

## Non-Standard Placeholder Registry (intentional to the template)

Placeholders used by each template beyond the standard 5
(`{{PRODUCT_NAME}}`, `{{DOC_ID}}`, `{{VERSION}}`, `{{DATE}}`, `{{WO_ID}}`).
Even if these show up as lint L5 WARN, they can be ignored since they are
intentional to the template:

| Template | Key Non-Standard Placeholders |
|---|---|
| D4_meetings | `{{MEETING_DATE_*}}`, `{{MEETING_TIME_*}}`, `{{MEETING_TOPIC_*}}`, `{{ATTENDEES_*}}`, `{{ABSENTEES_*}}`, `{{MEETING_VENUE_*}}`, `{{CLUSTER_REFS_*}}`, `{{YYYYMMDD_*}}` |
| D5_research | `{{COMPETITOR_1~3}}`, `{{TAM/SAM/SOM}}`, `{{REF/REF_1~3/URL}}`, `{{SLA}}`, `{{TREND_*}}`, `{{feature name}}`, `{{unit price}}`, `{{plan name}}` |
| Dα_api | `{{ENDPOINT_GROUP_1~2}}`, `{{TOKEN}}`, `{{CLIENT_ID/SECRET}}`, `{{ERROR_CODE}}`, `{{access/refresh token TTL}}` |
| Dα_db | `{{TABLE_1~2}}`, `{{TABLE_LARGE}}` (also includes a DB-type placeholder) |
| Dα_migration | `{{YYYYMMDD}}`, `{{SOURCE_HOST}}`, `{{TARGET_HOST}}`, `{{DB}}`, `{{USER}}`, `{{ms}}`, `{{owner}}`, `{{approver}}`, `{{new_col}}` |

## How to Use

### New product initialization (Track A — Full Product)
```bash
# 1) Copy the standard templates
cp orange-pm-plugin/templates/standard/D1_requirements.md \
   Planning-Agent-Hub/PROJECTS/{product}/drafts/D1.draft.md
cp orange-pm-plugin/templates/standard/D2_policy.md \
   Planning-Agent-Hub/PROJECTS/{product}/drafts/D2.draft.md
cp orange-pm-plugin/templates/standard/D3_screen.md \
   Planning-Agent-Hub/PROJECTS/{product}/drafts/D3.draft.md

# 2) Substitute placeholders (PRODUCT_NAME, DOC_ID, VERSION, DATE, etc.)

# 3) Create the Confluence page, then enter the page_id in meta.json

# 4) Publish
python orange-pm-plugin/scripts/md_to_storage.py \
   --input PROJECTS/{product}/drafts/D2.draft.md \
   --output /tmp/D2.xml --validate
# → /render --push is called automatically (converts to publication-syntax standard macros)
```

### Single deliverable (Track B/C — Single / Template-Copy, Phase 4 active)
```bash
# For URL-entry users: the from-url skill (Phase 4) applies this template automatically
/render --from-url https://confluence.../pages/123 --target D2
```

## Template Structure (complies with publication-syntax.md spec §2-§7)

- **Frontmatter**:
  - `title`, `wo_id`, `type`, `layer`, `version`, `last_updated`
  - `publication.header` — top info macro
  - `publication.meta.layout` — references/table of contents/change-history layout
- **Body**:
  - Sections divided into `::: {.panel section="§N ..."}` blocks
  - Default style is common (#24FE00 / #002FD5) — spec §3.1
  - Tables specify column ratios via the `<!-- col-widths: ... -->` directive
  - Placeholders such as `{{PRODUCT_NAME}}` / `{{DOC_ID}}` / `{{VERSION}}` / `{{DATE}}`

## Validation

```bash
# MD-stage lint (pre-validation)
python orange-pm-plugin/scripts/lint_publication_syntax.py \
   --input orange-pm-plugin/templates/standard/D1_requirements.md

# XML conversion + round-trip validation
python orange-pm-plugin/scripts/md_to_storage.py \
   --input orange-pm-plugin/templates/standard/D2_policy.md \
   --output /tmp/D2.xml --validate
```

Every template must produce only publication-lint L1-L7 PASS or WARN
(allowed placeholders).

## Round-Trip Validation (Phase 1D)

`scripts/round_trip_test.py` validates MD→XML→MD idempotence and the actual
conversion of fixture XML. Since these templates are the output of the 1F
migration, round-trip stability is guaranteed.
