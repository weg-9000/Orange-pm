---
publication:
  header:
    style: info
    body: |
      **This document is the screen design specification for {{PRODUCT_NAME}}. So that developers and stakeholders can read it standalone and implement from it, every piece of copy, layout, and interaction the screen displays is written out as actual text. For billing formulas, policy figures, and the like, see the policy definition.**
      
      doc_id: {{DOC_ID}} Version: {{VERSION}} Last updated: {{DATE}}
  meta:
    layout: two_equal
    cells:
      - panel:
          title: "References"
          body: |
            ::: {.expand}
            **Related Documents**
            
            - [[page:[Requirements Definition] {{PRODUCT_NAME}}]]
            - [[page:[Policy Definition] {{PRODUCT_NAME}}]]
            :::
      - change_history: 3
---

::: {.panel section="SCR-001 {{screen name}}"}
## SCR-001 {{screen name}}

---

### §1 Screen Overview

<!-- col-widths: 20%, 80% -->
| **Screen ID** | SCR-001 |
|---|---|
| **Screen Name** | {{screen name}} |
| **Entry Path** | {{entry path}} |
| **Related FR** | FR-001, FR-002 |
| **Related Policy** | Policy Definition §{{section number}} |

### §2 Layout Structure

{{layout description — area division, fixed/scrolling behavior, etc.}}

### §2-1 GNB (Global Navigation Bar)

<!-- col-widths: 20%, 40%, 40% -->
| Element | Displayed Copy / State | Behavior |
|---|---|---|
| {{element name}} | {{copy}} | {{behavior}} |

### §2-2 LNB (Left Navigation Bar)

<!-- col-widths: 20%, 40%, 40% -->
| Element | Displayed Copy / State | Behavior |
|---|---|---|
| {{element name}} | {{copy}} | {{behavior}} |

### §2-3 Main Content Area

<!-- col-widths: 20%, 80% -->
| Element | Content |
|---|---|
| {{element name}} | {{content}} |

### §2-4 Right Panel

{{description of the right panel's composition}}

### §2-5 Footer

{{footer composition}}

### §2-6 Responsive Handling

<!-- col-widths: 20%, 80% -->
| Breakpoint | Handling |
|---|---|
| {{px threshold}} | {{handling}} |

### §2-7 Design Tokens

<!-- col-widths: 20%, 20%, 60% -->
| Token Type | Value (HEX / px) | Applied Location |
|---|---|---|
| {{token name}} | {{value}} | {{applied location}} |

### §3 Interaction Specification

<!-- col-widths: 15%, 25%, 25%, 35% -->
| Trigger | Condition | Result | Exception Handling |
|---|---|---|---|
| {{trigger}} | {{condition}} | {{result}} | {{exception}} |

### §4 UI Copy Specification

<!-- col-widths: 20%, 45%, 35% -->
| Element | Copy (verbatim text) | Notes |
|---|---|---|
| {{button/label name}} | {{actual displayed copy}} | {{notes}} |

### §5 Error / Empty States

<!-- col-widths: 20%, 45%, 35% -->
| State | Displayed Content | Handling |
|---|---|---|
| {{error/empty state name}} | {{displayed copy}} | {{handling}} |
:::

::: {.panel section="SCR-002 {{screen name}}"}
## SCR-002 {{screen name}}

---

### §1 Screen Overview

<!-- col-widths: 20%, 80% -->
| **Screen ID** | SCR-002 |
|---|---|
| **Screen Name** | {{screen name}} |
| **Entry Path** | {{entry path}} |
| **Related FR** | {{FR list}} |
| **Related Policy** | Policy Definition §{{section number}} |

### §2 Layout Structure

{{layout description}}

### §2-7 Design Tokens

<!-- col-widths: 20%, 20%, 60% -->
| Token Type | Value | Applied Location |
|---|---|---|
| {{token name}} | {{value}} | {{applied location}} |

### §3 Interaction Specification

{{interaction specification}}

### §4 UI Copy Specification

{{copy specification}}
:::
