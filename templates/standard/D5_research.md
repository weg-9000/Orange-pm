---
title: "[Competitor Research] {{PRODUCT_NAME}}"
type: research
layer: DIRECT
version: 1.0
last_updated: 2026-05-30

publication:
  header:
    style: info
    body: |
      **Competitor research definition. Market positioning / competitor comparison / benchmark results for {{PRODUCT_NAME}}**

      doc_id: {{DOC_ID}} Version: {{VERSION}} Last updated: {{DATE}}
  meta:
    layout: two_equal
    cells:
      - panel:
          title: "Related Pages"
          body: |
            **Related Documents**

            - [[page:[Requirements Definition] {{PRODUCT_NAME}}]]
            - [[page:[Policy Definition] {{PRODUCT_NAME}}]]
      - change_history: 3
---

::: {.panel section="§1 Market Overview (Global)"}
## §1 Market Overview (Global)

---

### §1-1 Market Definition (TAM / SAM / SOM)

<!-- col-widths: 15%, 25%, 45%, 15% -->
| Category | Definition | Basis of Estimate | Size |
|---|---|---|---|
| **TAM** | {{TAM definition — total addressable market}} | {{basis of estimate / data source}} | {{TAM}} |
| **SAM** | {{SAM definition — serviceable available market}} | {{basis of estimate}} | {{SAM}} |
| **SOM** | {{SOM definition — serviceable obtainable market}} | {{basis of estimate / period}} | {{SOM}} |

### §1-2 Market Trends

<!-- col-widths: 10%, 25%, 50%, 15% -->
| ID | Trend | Content / Implication | Source |
|---|---|---|---|
| T-01 | {{trend name}} | {{trend content — focused on objective metrics}} | {{REF_1}} |
| T-02 | {{trend name}} | {{content}} | {{REF_2}} |
| T-03 | {{trend name}} | {{content}} | {{REF_3}} |

### §1-3 Entry Barriers / Differentiation Points

<!-- col-widths: 20%, 40%, 40% -->
| Category | Item | Content |
|---|---|---|
| **Entry Barrier** | {{barrier name}} | {{barrier detail — regulatory / capital / technical, etc.}} |
| **Differentiation Point** | {{point name}} | {{possible differentiation axis — based on objective facts}} |

### §1-4 Research Scope / Methodology

<!-- col-widths: 20%, 80% -->
| Item | Content |
|---|---|
| **Research Period** | {{research start date}} ~ {{research end date}} |
| **Research Target** | {{country / segment / price tier, etc.}} |
| **Data Source** | {{primary source — official docs / pricing page / disclosures}}, {{secondary source — research reports / articles}} |
| **Collection Method** | {{official-site collection / pricing-page capture / interviews / demos, etc.}} |
| **Limitations** | {{limitations — non-public pricing, areas that include estimates, timing mismatches, etc.}} |
:::

::: {.panel section="§2 Competitor Matrix (Competitor Comparison)"}
## §2 Competitor Matrix (Competitor Comparison)

---

### §2-1 Comparison Axis Definitions

<!-- col-widths: 15%, 25%, 60% -->
| Axis | Measurement Criteria | Notes |
|---|---|---|
| **Price** | {{measurement criteria — monthly fee / usage unit price, etc.}} | {{notes}} |
| **Core Features** | {{measurement criteria — number of supported features / automation scope, etc.}} | {{notes}} |
| **SLA** | {{measurement criteria — availability % / response time, etc.}} | {{notes}} |
| **Korea Support** | {{measurement criteria — Korean-language UI / KR region / Korean-language CS, etc.}} | {{notes}} |
| **Integration** | {{measurement criteria — number of API / SDK / external integrations}} | {{notes}} |
| **Operations** | {{measurement criteria — console / monitoring / backup, etc.}} | {{notes}} |
| **Security** | {{measurement criteria — authentication / encryption / compliance}} | {{notes}} |

### §2-2 Competitor Matrix

<!-- col-widths: 12%, 13%, 18%, 10%, 13%, 14%, 20% -->
| Competitor | Price | Core Features | SLA | Korea Support | Integration | Notes |
|---|---|---|---|---|---|---|
| **{{COMPETITOR_1}}** | {{price}} | {{core features}} | {{SLA}} | {{Korea support}} | {{integration}} | {{notes}} |
| **{{COMPETITOR_2}}** | {{price}} | {{core features}} | {{SLA}} | {{Korea support}} | {{integration}} | {{notes}} |
| **{{COMPETITOR_3}}** | {{price}} | {{core features}} | {{SLA}} | {{Korea support}} | {{integration}} | {{notes}} |

::: {.info}
Every table-cell value must be an objective metric whose source can be cited. Interpretation / evaluation is kept separate, in §6 Implications.
:::
:::

::: {.panel section="§3 Competitor Detail — {{COMPETITOR_1}}"}
## §3 Competitor Detail — {{COMPETITOR_1}}

---

### §3-1 Company / Product Overview

<!-- col-widths: 20%, 80% -->
| Item | Content |
|---|---|
| **Company Name** | {{company name}} |
| **HQ / Region** | {{HQ location / service region}} |
| **Product Name** | {{product name}} |
| **Launch Date** | {{launch year}} |
| **Target Segment** | {{target — SMB / enterprise / developers, etc.}} |
| **Source** | {{REF — official site URL}} |

### §3-2 Pricing Policy

<!-- col-widths: 20%, 25%, 35%, 20% -->
| Plan | Unit Price | Included Scope | Source |
|---|---|---|---|
| {{plan name}} | {{unit price}} | {{included features / usage limits}} | {{REF}} |

### §3-3 Core Features / Differentiators

<!-- col-widths: 25%, 50%, 25% -->
| Feature | Description (per official documentation) | Source |
|---|---|---|
| {{feature name}} | {{quoted or summarized from official documentation}} | {{REF}} |

### §3-4 Weaknesses / Constraints

<!-- col-widths: 25%, 50%, 25% -->
| Item | Content (fact-based) | Source |
|---|---|---|
| {{constraint item}} | {{constraint based on official announcements / user reports}} | {{REF}} |

### §3-5 Implications for Our Product, {{PRODUCT_NAME}}

{{our product's interpretation of the observed facts. Mark speculative areas with [needs-review].}}
:::

::: {.panel section="§4 Competitor Detail — {{COMPETITOR_2}}"}
## §4 Competitor Detail — {{COMPETITOR_2}}

---

### §4-1 Company / Product Overview

<!-- col-widths: 20%, 80% -->
| Item | Content |
|---|---|
| **Company Name** | {{company name}} |
| **HQ / Region** | {{HQ location / service region}} |
| **Product Name** | {{product name}} |
| **Launch Date** | {{launch year}} |
| **Target Segment** | {{target}} |
| **Source** | {{REF}} |

### §4-2 Pricing Policy

<!-- col-widths: 20%, 25%, 35%, 20% -->
| Plan | Unit Price | Included Scope | Source |
|---|---|---|---|
| {{plan name}} | {{unit price}} | {{included features / usage limits}} | {{REF}} |

### §4-3 Core Features / Differentiators

<!-- col-widths: 25%, 50%, 25% -->
| Feature | Description (per official documentation) | Source |
|---|---|---|
| {{feature name}} | {{quoted or summarized from official documentation}} | {{REF}} |

### §4-4 Weaknesses / Constraints

<!-- col-widths: 25%, 50%, 25% -->
| Item | Content (fact-based) | Source |
|---|---|---|
| {{constraint item}} | {{fact-based constraint}} | {{REF}} |

### §4-5 Implications for Our Product, {{PRODUCT_NAME}}

{{our product's interpretation of the facts. Mark speculative areas with [needs-review].}}
:::

::: {.panel section="§5 Competitor Detail — {{COMPETITOR_3}}"}
## §5 Competitor Detail — {{COMPETITOR_3}}

---

### §5-1 Company / Product Overview

<!-- col-widths: 20%, 80% -->
| Item | Content |
|---|---|
| **Company Name** | {{company name}} |
| **HQ / Region** | {{HQ location / service region}} |
| **Product Name** | {{product name}} |
| **Launch Date** | {{launch year}} |
| **Target Segment** | {{target}} |
| **Source** | {{REF}} |

### §5-2 Pricing Policy

<!-- col-widths: 20%, 25%, 35%, 20% -->
| Plan | Unit Price | Included Scope | Source |
|---|---|---|---|
| {{plan name}} | {{unit price}} | {{included features / usage limits}} | {{REF}} |

### §5-3 Core Features / Differentiators

<!-- col-widths: 25%, 50%, 25% -->
| Feature | Description (per official documentation) | Source |
|---|---|---|
| {{feature name}} | {{quoted or summarized from official documentation}} | {{REF}} |

### §5-4 Weaknesses / Constraints

<!-- col-widths: 25%, 50%, 25% -->
| Item | Content (fact-based) | Source |
|---|---|---|
| {{constraint item}} | {{fact-based constraint}} | {{REF}} |

### §5-5 Implications for Our Product, {{PRODUCT_NAME}}

{{our product's interpretation of the facts. Mark speculative areas with [needs-review].}}
:::

::: {.panel section="§6 Implications and Strategic Recommendations"}
## §6 Implications and Strategic Recommendations

---

### §6-1 Recommended Positioning for Our Product

<!-- col-widths: 20%, 40%, 40% -->
| Axis | Recommended Positioning | Basis (see §2 matrix) |
|---|---|---|
| **Price** | {{positioning — e.g. mid-tier / value-for-money in Korea}} | {{basis}} |
| **Features** | {{positioning — e.g. specialized in operations automation for Korea}} | {{basis}} |
| **Target** | {{recommended target segment}} | {{basis}} |

### §6-2 Differentiation Strategy

<!-- col-widths: 15%, 25%, 60% -->
| ID | Axis | Strategy Content |
|---|---|---|
| STR-01 | Price | {{strategy — e.g. KR payment / VAT shown separately}} |
| STR-02 | Features | {{strategy — e.g. integrated with our product's domain}} |
| STR-03 | Support | {{strategy — e.g. 24/7 Korean-language CS}} |

### §6-3 Priority Response Items (cluster reflow)

<!-- col-widths: 10%, 25%, 35%, 15%, 15% -->
| ID | Item | Content / Needs Review | Priority | Reflow Target |
|---|---|---|---|---|
| PRI-01 | {{response item}} | {{content — state any TBD portions}} | P0 | {{cluster_ref / requirements}} |
| PRI-02 | {{response item}} | {{content}} | P1 | {{cluster_ref}} |
:::

::: {.panel section="§7 Appendix — Data Sources / References" style="info"}
## §7 Appendix — Data Sources / References

---

### §7-1 Source List

<!-- col-widths: 10%, 30%, 35%, 12%, 13% -->
| ID | Item | Source URL | Collection Date | Reliability |
|---|---|---|---|---|
| REF-01 | {{item — e.g. AWS RDS pricing}} | {{URL}} | {{YYYY-MM-DD}} | Primary (official) |
| REF-02 | {{item — e.g. market-size research}} | {{URL}} | {{YYYY-MM-DD}} | Secondary (research) |
| REF-03 | {{item — e.g. user reviews}} | {{URL}} | {{YYYY-MM-DD}} | Tertiary (community) |

### §7-2 Reliability Classification Criteria

<!-- col-widths: 15%, 25%, 60% -->
| Tier | Classification | Examples |
|---|---|---|
| **Primary** | Official material | Official site / pricing page / official documentation / disclosures |
| **Secondary** | Verified third party | Research reports / major media articles |
| **Tertiary** | Unofficial | Community / user reviews / blogs |
:::
