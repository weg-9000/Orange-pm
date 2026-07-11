---
publication:
  header:
    style: info
    body: |
      **This document is the service policy definition for {{PRODUCT_NAME}}. It is the canonical source for every rule and policy that {{PRODUCT_NAME}} displays.**
      
      doc_id: {{DOC_ID}} Version: {{VERSION}} Last updated: {{DATE}}
  meta:
    layout: two_equal
    cells:
      - panel:
          title: "References"
          body: |
            **Related Documents**
            
            - [[page:[Requirements Definition] {{PRODUCT_NAME}}]]
            - [[page:[Screen Design] {{PRODUCT_NAME}}]]
      - change_history: 3
---

::: {.panel section="§1 Policy Overview"}
## §1 Policy Overview

---

### §1-1 Purpose

<!-- col-widths: 15%, 85% -->
| **Purpose** | {{one-sentence purpose of this policy document}} |
|---|---|
| **Scope** | {{the scope this policy applies to}} |
| **Priority** | {{the priority principle in case of conflict}} |

### §1-2 Scope

{{scope details}}

### §1-3 Core Principles

<!-- col-widths: 20%, 80% -->
| Principle | Content |
|---|---|
| {{principle name}} | {{content}} |

### §1-4 Term Definitions

<!-- col-widths: 20%, 80% -->
| Term | Definition (canonical wording) |
|---|---|
| **{{term}}** | {{definition}} |
:::

::: {.panel section="§2 Common Policy"}
## §2 Common Policy

---

### §2-1 Status Definitions

<!-- col-widths: 20%, 50%, 30% -->
| Status | Definition | Entry Condition |
|---|---|---|
| **{{status name}}** | {{definition}} | {{entry condition}} |

### §2-2 Allowed-Actions-by-Status Matrix

<!-- col-widths: 20%, 20%, 20%, 40% -->
| Status | Allowed Actions | Prohibited Actions | Notes |
|---|---|---|---|
| {{status}} | {{allowed}} | {{prohibited}} | {{notes}} |

### §2-3 Permissions

<!-- col-widths: 20%, 80% -->
| Role | Allowed Scope |
|---|---|
| {{role}} | {{allowed scope}} |

### §2-4 Common Rules

{{describe the commonly applied rule}}
:::

::: {.panel section="§3 Creation / Request Policy"}
## §3 Creation / Request Policy

---

### §3-0 Exposure Scope

{{under what conditions creation/request is exposed}}

### §3-1 Input Validation

<!-- col-widths: 15%, 20%, 35%, 30% -->
| Field | Rule Type | Condition | Error Message / Handling |
|---|---|---|---|
| {{field name}} | {{required / format / range}} | {{condition}} | {{handling}} |

### §3-2 Case Branching

<!-- col-widths: 15%, 30%, 55% -->
| Case | Condition | Handling |
|---|---|---|
| C-001 | {{condition}} | {{handling}} |
:::

::: {.panel section="§4 Deletion / Termination Policy"}
## §4 Deletion / Termination Policy

---

### §4-1 Deletion Conditions

{{conditions and constraints under which deletion is possible}}

### §4-2 Deletion Handling Flow

<!-- col-widths: 10%, 30%, 60% -->
| Step | Actor | Handling |
|---|---|---|
| 1 | {{actor}} | {{handling}} |

### §4-3 Cascading Deletion / Dependent Resource Handling

{{rule for handling dependent resources}}
:::

::: {.panel section="Open Items"}
## Open Items

---

### P1 — Needs Discussion (blocking)

<!-- col-widths: 8%, 30%, 35%, 15%, 12% -->
| ID | Item | Status / Options | Owner | Target Date |
|---|---|---|---|---|
| OI-001 | {{item}} | {{status}} | {{owner}} | {{target date}} |

### P2 — Optional Enhancement (non-blocking)

<!-- col-widths: 8%, 30%, 35%, 15%, 12% -->
| ID | Item | Status | Owner | Target Date |
|---|---|---|---|---|
| OI-002 | {{item}} | {{status}} | {{owner}} | {{target date}} |
:::
