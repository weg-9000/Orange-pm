<!--
  spec-catalog authoring template (source of PROJECTS/{product}/inputs/spec-catalog.md)
  - Output location: PROJECTS/{product}/inputs/spec-catalog.md (not a Confluence publish target — a project inputs work artifact)
  - Producer: synthesizer (/draft-req). Consumers: reviewer (V-06), write · write-cluster · flow · screen-detail ([[spec-catalog variable ID]]), formula-binding (calculation type)
  - Every input variable of the product is defined exactly once in this document (C1 SSoT). The policy document / screen design only cite/link the variable ID.
  - Substitute {curly-brace} placeholders with actual values; blank cells are prohibited — for unknown values, write [needs-confirmation:reason] and register in open-issues.
-->
---
doc_id: {PREFIX}-C-{PRODUCT_CODE}-SPEC-CATALOG
title: Input Variable Catalog (SSoT)
status: draft
mode: calculation | console   # calculation=billing-formula type / console=input-validation type
referenced_master: [{PREFIX}-B-002@v1.3, {PREFIX}-A-001@v1.1]
last_updated: YYYY-MM-DD
---

# Input Variable Catalog — {product name}

> **C1 SSoT**: every input variable of the product is defined **exactly once** in this document.
> The policy document / screen design only cite and link the variable ID — they do not redefine it.
> **C5 Source Traceability**: every row's `Source` must be either a citation of common (PX-B §X),
> `product delta`, or `[needs-confirmation:reason]`. **Guessing or hallucinated entries are prohibited** (blank cells are prohibited).

## Usage Modes

| mode | Use | formula-binding |
|---|---|---|
| `calculation` | Billing-formula-type products (e.g. a calculator). Variable ↔ formula is 1:1 (C2) | required (WP5) |
| `console` | Console-type products. Single source of input validation (blocks duplicate re-entry) | not required |

---

## {Service/Entity Name — canonical term per PX-A-001}

| Field Name (Variable ID) | Input Type | Default | Range/Options | Unit | UI Guidance Copy | Error Message | Source |
|---|---|---|---|---|---|---|---|
| `{variable_id}` | Number/Select/Text/Checkbox | {default value} | {min~max or options} | {GB/count/month/…} | "{guidance}" | "{error}" | `{PREFIX}-B-002 §B-2` |
| `{variable_id}` | Number | `[needs-confirmation:no-source]` | — | — | — | — | `open-issues {ISSUE-ID}` |

### Dependencies · Flags
- requires: [`{variable_id}`]
- suggests: [`{variable_id}`]
- Commitment target: Y/N    · Billing unit: hour/day/month/count/none

### JSON Conversion Structure
```json
{ "{variable_id}": "<type>" }
```

---

## Source Notation Rules (C0 · C5)

| Notation | Meaning | Handling |
|---|---|---|
| `{PREFIX}-B-NNN §X` | Derived from common policy — copying the value is prohibited, link-reference only | complies with C0 |
| `product delta` | A definition unique to this product, absent from common | a decisions.md basis is recommended |
| `[needs-confirmation:reason]` | Source not yet secured — guessing is prohibited, register in open-issues | tracked by source-input-gate |

## Workflow Connections
- Canonical terminology: [[PX-A Terminology Rules]]
- Common policy: [[PX-B_ProductPricingPaymentPolicy]]
- Formula binding (calculation type): [[formula-binding-template]]
- Applicable skills: [[draft-req]], [[write]], [[review]]
