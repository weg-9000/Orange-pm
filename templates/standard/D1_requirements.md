---
publication:
  header:
    style: info
    body: |
      **doc_id: {{DOC_ID}} Version: {{VERSION}} Last updated: {{DATE}}**
      
      {{DESCRIPTION}}
      
      **FR numbering scheme: FR-[section number][2-digit sequence][-sub-sequence] — §1→FR-1xx / §2→FR-2xx / ... / §9→FR-9xx**
  meta:
    layout: two_equal
    cells:
      - panel:
          title: "References"
          body: |
            **Related Documents**
            
            - [[page:[Policy Definition] {{PRODUCT_NAME}}]]
            - [[page:[Screen Design] {{PRODUCT_NAME}}]]
      - change_history: 5
---

::: {.panel section="1. Service Overview"}
## 1. Service Overview

---

**Write a one-sentence description of {{PRODUCT_NAME}}.**

<!-- col-widths: 20%, 80% -->
| Term | Definition |
|---|---|
| **{{term 1}}** | {{definition 1}} |
| **{{term 2}}** | {{definition 2}} |
:::

::: {.panel section="2. Background"}
## 2. Background

---

{{background body}}

### Current Problems

<!-- col-widths: 5%, 10%, 75%, 10% -->
|  | Category | Content | Source |
|---|---|---|---|
| P-01 | {{category}} | {{problem description}} | {{source}} |
:::

::: {.panel section="3. As-Is / To-Be"}
## 3. As-Is / To-Be

---

<!-- col-widths: 20%, 35%, 45% -->
| Category | As-Is (current) | To-Be (after improvement) |
|---|---|---|
| **{{item 1}}** | {{current state}} | {{improvement goal}} |
:::

::: {.panel section="Functional Requirements"}
## Functional Requirements (FR)

---

::: {.info}
**FR numbering scheme:** FR-[section number][2-digit sequence][-sub-sequence]

<!-- col-widths: 15%, 15%, 70% -->
| Section | Number Range | Topic |
|---|---|---|
| §1 | FR-1xx | {{§1 topic name}} |
| §2 | FR-2xx | {{§2 topic name}} |
| §3 | FR-3xx | {{§3 topic name}} |
| §4 | FR-4xx | {{§4 topic name}} |
| §5 | FR-5xx | {{§5 topic name}} |

FR content-writing principle: state **What** in one sentence. Delegate
details to the policy document / screen design.

The capability seed lives in the sidecar `requirements.seeds.yml`
(a hypothesis — consumed by cluster_identify, bootstrapped via cluster_seed_backfill)
:::

### §1 {{§1 topic name}}

<!-- col-widths: 8%, 15%, 67%, 10% -->
| FR ID | Requirement Name | Content (What) | Priority |
|---|---|---|---|
| **FR-101** | {{name}} | {{what the feature should do — one sentence}} | P0 |
| **FR-101-1** | {{name}} | {{FR-101 detailed condition}} | P0 |
| **FR-102** | {{name}} | {{content}} | P0 |

### §2 {{§2 topic name}}

<!-- col-widths: 8%, 15%, 67%, 10% -->
| FR ID | Requirement Name | Content (What) | Priority |
|---|---|---|---|
| **FR-201** | {{name}} | {{content}} | P0 |
| **FR-201-1** | {{name}} | {{detailed condition}} | P0 |
| **FR-202** | {{name}} | {{content}} | P1 |

### §3 {{§3 topic name}}

<!-- col-widths: 8%, 15%, 67%, 10% -->
| FR ID | Requirement Name | Content (What) | Priority |
|---|---|---|---|
| **FR-301** | {{name}} | {{content}} | P0 |

### §4 {{§4 topic name}}

<!-- col-widths: 8%, 15%, 67%, 10% -->
| FR ID | Requirement Name | Content (What) | Priority |
|---|---|---|---|
| **FR-401** | {{name}} | {{content}} | P1 |

### §5 {{§5 topic name}}

<!-- col-widths: 8%, 15%, 67%, 10% -->
| FR ID | Requirement Name | Content (What) | Priority |
|---|---|---|---|
| **FR-501** | {{name}} | {{content}} | P1 |
:::

::: {.panel section="Non-Functional Requirements"}
## Non-Functional Requirements (NFR)

---

<!-- col-widths: 8%, 15%, 67%, 10% -->
| NFR ID | Requirement Name | Content | Priority |
|---|---|---|---|
| NFR-001 | {{name}} | {{content}} | P0 |
:::

::: {.panel section="Constraints"}
## Constraints

---

<!-- col-widths: 12%, 23%, 65% -->
| CON ID | Constraint Item | Content |
|---|---|---|
| CON-001 | {{constraint item}} | {{content}} |
:::

::: {.panel section="Actor Definitions"}
## Actor Definitions

---

<!-- col-widths: 12%, 13%, 13%, 62% -->
| ACTOR ID | Actor Name | Type | Key Scenario |
|---|---|---|---|
| ACTOR-001 | {{actor name}} | Primary (external) | {{scenario}} |
| ACTOR-002 | {{actor name}} | Primary (internal) | {{scenario}} |
:::
