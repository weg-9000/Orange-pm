---
title: "[DB Schema] {{PRODUCT_NAME}}"
type: etc
layer: DIRECT
version: 1.0
last_updated: 2026-05-30

publication:
  header:
    style: info
    body: |
      **{{PRODUCT_NAME}} DB Schema**

      doc_id: {{DOC_ID}} Version: {{VERSION}} Last updated: {{DATE}}
  meta:
    layout: two_equal
    cells:
      - panel:
          title: "Related Documents"
          body: |
            - [[page:[Policy Definition] {{PRODUCT_NAME}}]]
            - [[page:[Screen Design] {{PRODUCT_NAME}}]]
      - change_history: 5
---

::: {.panel section="§1 Schema Overview"}
## §1 Schema Overview

---

### §1-1 DBMS Type / Version

<!-- col-widths: 25%, 75% -->
| Item | Content |
|---|---|
| **DBMS** | {{PostgreSQL 15 / MySQL 8 / ...}} |
| **Charset / Collation** | {{utf8mb4 / utf8mb4_unicode_ci}} |
| **Timezone** | UTC (storage) / KST (display) |
| **Storage Engine** | {{InnoDB / heap}} |

### §1-2 Naming Conventions

<!-- col-widths: 20%, 35%, 45% -->
| Target | Rule | Example |
|---|---|---|
| Table | snake_case, plural | `instances`, `users` |
| Column | snake_case, singular | `created_at`, `owner_id` |
| Index | `idx_{table}_{cols}` | `idx_instances_owner_id` |
| Unique Index | `uq_{table}_{cols}` | `uq_users_email` |
| Foreign Key | `fk_{table}_{ref_table}` | `fk_instances_users` |

### §1-3 Common Columns

<!-- col-widths: 18%, 18%, 10%, 18%, 36% -->
| Column | Type | NULL | Default | Description |
|---|---|---|---|---|
| `id` | `bigint` | NO | autoincrement | Primary key |
| `created_at` | `timestamptz` | NO | `now()` | Creation time (UTC) |
| `updated_at` | `timestamptz` | NO | `now()` | Update time (UTC) |
| `deleted_at` | `timestamptz` | YES | NULL | Soft-delete time |

### §1-4 ERD Diagram

```mermaid
erDiagram
  USERS ||--o{ {{TABLE_1}} : owns
  {{TABLE_1}} ||--o{ {{TABLE_2}} : has
  USERS {
    bigint id PK
    varchar email
  }
  {{TABLE_1}} {
    bigint id PK
    bigint owner_id FK
    varchar name
  }
  {{TABLE_2}} {
    bigint id PK
    bigint parent_id FK
    varchar key
    text value
  }
```
:::

::: {.panel section="§2 Table — {{TABLE_1}}"}
## §2 Table — {{TABLE_1}}

---

### §2-1 Column Definitions

<!-- col-widths: 18%, 18%, 8%, 18%, 12%, 26% -->
| Column | Type | NULL | Default | Constraint | Description |
|---|---|---|---|---|---|
| `id` | `bigint` | NO | autoincrement | PK | Primary key |
| `owner_id` | `bigint` | NO | — | FK → users.id | Owner |
| `name` | `varchar(128)` | NO | — | UQ(owner_id, name) | Display name |
| `status` | `varchar(32)` | NO | `'pending'` | check | Status |
| `config` | `jsonb` | YES | `'{}'` | — | Configuration value |
| `created_at` | `timestamptz` | NO | `now()` | — | Creation time |
| `updated_at` | `timestamptz` | NO | `now()` | — | Update time |
| `deleted_at` | `timestamptz` | YES | NULL | — | soft delete |

### §2-2 Indexes

<!-- col-widths: 35%, 30%, 15%, 20% -->
| Index | Columns | Type | Purpose |
|---|---|---|---|
| `pk_{{TABLE_1}}` | (id) | btree (PK) | Primary key |
| `uq_{{TABLE_1}}_owner_name` | (owner_id, name) | unique | Prevent duplicate names per owner |
| `idx_{{TABLE_1}}_status` | (status) | btree | Status filter |
| `idx_{{TABLE_1}}_created_at` | (created_at desc) | btree | Sort by most recent |

### §2-3 Foreign Keys / Relationships

```mermaid
erDiagram
  USERS ||--o{ {{TABLE_1}} : "owner_id"
  {{TABLE_1}} ||--o{ {{TABLE_2}} : "parent_id"
```

- `owner_id` → `users.id` ON DELETE RESTRICT (blocked when the owner is deleted).
- `{{TABLE_2}}.parent_id` → `{{TABLE_1}}.id` ON DELETE CASCADE.

### §2-4 Business Rules

- `status` check constraint: `status IN ('pending', 'active', 'suspended', 'deleted')`.
- On soft delete, record `deleted_at`; lookup queries apply `WHERE deleted_at IS NULL` by default.
- When `name` changes, record before/after in the audit log table (trigger or application level).
:::

::: {.panel section="§3 Table — {{TABLE_2}}"}
## §3 Table — {{TABLE_2}}

---

### §3-1 Column Definitions

<!-- col-widths: 18%, 18%, 8%, 18%, 12%, 26% -->
| Column | Type | NULL | Default | Constraint | Description |
|---|---|---|---|---|---|
| `id` | `bigint` | NO | autoincrement | PK | Primary key |
| `parent_id` | `bigint` | NO | — | FK → {{TABLE_1}}.id | Parent resource |
| `key` | `varchar(64)` | NO | — | UQ(parent_id, key) | Attribute key |
| `value` | `text` | YES | NULL | — | Attribute value |
| `created_at` | `timestamptz` | NO | `now()` | — | Creation time |
| `updated_at` | `timestamptz` | NO | `now()` | — | Update time |

### §3-2 Indexes

<!-- col-widths: 35%, 30%, 15%, 20% -->
| Index | Columns | Type | Purpose |
|---|---|---|---|
| `pk_{{TABLE_2}}` | (id) | btree (PK) | Primary key |
| `uq_{{TABLE_2}}_parent_key` | (parent_id, key) | unique | Prevent duplicate keys |
| `idx_{{TABLE_2}}_parent_id` | (parent_id) | btree | Parent join |

### §3-3 Foreign Keys / Relationships

- `parent_id` → `{{TABLE_1}}.id` ON DELETE CASCADE.

### §3-4 Business Rules

- `key` allows only lowercase letters, digits, and `_` (`^[a-z][a-z0-9_]*$`).
- `value` size limit: 64KB (validated at the application level).
:::

::: {.panel section="§4 Indexing / Performance Policy"}
## §4 Indexing / Performance Policy

---

### §4-1 Frequently Used Query Patterns

<!-- col-widths: 25%, 50%, 25% -->
| Pattern | Example Query | Index Used |
|---|---|---|
| List by owner | `SELECT * FROM {{TABLE_1}} WHERE owner_id=? AND deleted_at IS NULL ORDER BY created_at DESC` | `idx_{{TABLE_1}}_created_at` + `owner_id` |
| Status filter | `SELECT * FROM {{TABLE_1}} WHERE status=? AND deleted_at IS NULL` | `idx_{{TABLE_1}}_status` |
| Attribute lookup | `SELECT key, value FROM {{TABLE_2}} WHERE parent_id=?` | `idx_{{TABLE_2}}_parent_id` |

### §4-2 Indexing Strategy

- Every foreign-key column is guaranteed a single-column index (for join / FK-validation performance).
- For multi-column indexes, place the higher-cardinality column first so the left prefix can be leveraged.
- For tables subject to soft delete, consider a partial index on the `deleted_at IS NULL` condition.

### §4-3 Partitioning

<!-- col-widths: 25%, 25%, 50% -->
| Table | Strategy | Notes |
|---|---|---|
| `{{TABLE_LARGE}}` | Monthly range (`created_at`) | Retain 1 year, then archive |
| Other | None | Single table |
:::

::: {.panel section="§5 Data Retention / Backup Policy" style="info"}
## §5 Data Retention / Backup Policy

---

### §5-1 Retention Period

<!-- col-widths: 30%, 25%, 45% -->
| Data Type | Retention Period | Handling |
|---|---|---|
| Operational data | Indefinite | soft delete + periodic archive |
| Audit log | 5 years | Migrated to cold storage |
| Temporary / cache | 7 days | Auto-expires via TTL |

### §5-2 Backup

<!-- col-widths: 25%, 25%, 50% -->
| Type | Frequency | Retention |
|---|---|---|
| Full backup | Once daily (02:00 UTC) | 30 days |
| Incremental backup | Hourly | 7 days |
| WAL / binlog | Continuous | 7 days (PITR possible) |

### §5-3 Recovery Objectives

- **RPO**: ≤ 1 hour
- **RTO**: ≤ 4 hours
- Perform a recovery rehearsal once per quarter; record the results in the meeting notes (D4).
:::
