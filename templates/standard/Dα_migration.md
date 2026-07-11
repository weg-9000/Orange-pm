---
title: "[Migration Plan] {{PRODUCT_NAME}}"
type: etc
layer: DIRECT
version: 1.0
last_updated: 2026-05-30

publication:
  header:
    style: info
    body: |
      **{{PRODUCT_NAME}} Migration Plan**

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

::: {.panel section="§1 Migration Overview"}
## §1 Migration Overview

---

### §1-1 Target / Scope

<!-- col-widths: 20%, 80% -->
| Item | Content |
|---|---|
| **Target Data** | {{which tables / which resources}} |
| **Source** | {{environment / DBMS / location}} |
| **Target** | {{environment / DBMS / location}} |
| **Data Volume** | {{record count / size}} |
| **Transformation** | {{schema change / encoding conversion / identical}} |

### §1-2 Schedule / Phases

<!-- col-widths: 20%, 25%, 30%, 25% -->
| Phase | Timing | Task | Output |
|---|---|---|---|
| Preparation | {{YYYY-MM-DD}} | Checks, backup, script validation | Check report |
| Rehearsal | {{YYYY-MM-DD}} | Staging-environment dry run | Rehearsal report |
| Main operation | {{YYYY-MM-DD HH:MM}} | Production-environment migration | Execution log |
| Verification | main operation + 1h | Data / functional verification | Verification report |
| Stabilization | main operation + 7 days | Monitoring, resolving remaining issues | Closure report |

### §1-3 Owners / Approval

<!-- col-widths: 20%, 30%, 50% -->
| Role | Owner | Responsibility |
|---|---|---|
| **Execution Owner** | {{owner}} | Carries out the main operation / decision authority |
| **Approval** | {{approver}} | GO / NO-GO for the main operation |
| **Verification** | {{verifier}} | Data consistency / functional verification |
| **Rollback Decision** | {{decider}} | Authority to trigger rollback |

### §1-4 Impact Scope

<!-- col-widths: 25%, 75% -->
| Item | Content |
|---|---|
| **Downtime** | {{no downtime / partial outage N min / full outage N min}} |
| **User Impact** | {{read-only / some features blocked / no impact}} |
| **Notice** | {{D-7 notice / D-1 re-notice / banner right before the operation}} |
| **Related Systems** | {{list of external dependent systems}} |
:::

::: {.panel section="§2 Pre-flight Preparation"}
## §2 Pre-flight Preparation

---

### §2-1 Checklist

<!-- col-widths: 10%, 35%, 15%, 15%, 25% -->
| ID | Item | Owner | Status | Notes |
|---|---|---|---|---|
| PF-01 | Confirm source/target connectivity | {{owner}} | 📋 | — |
| PF-02 | Complete full backup / verify restore | {{owner}} | 📋 | based on RPO |
| PF-03 | Code review of migration scripts | {{owner}} | 📋 | — |
| PF-04 | At least 1 staging dry run | {{owner}} | 📋 | attach execution log |
| PF-05 | Rollback-procedure rehearsal | {{owner}} | 📋 | measure timing |
| PF-06 | Enable monitoring alerts | {{owner}} | 📋 | review thresholds |
| PF-07 | Send user notice | {{owner}} | 📋 | D-7, D-1 |
| PF-08 | Confirm GO from related departments / approver | {{owner}} | 📋 | — |

### §2-2 Backup Procedure

```bash
# Full backup of the source (e.g. PostgreSQL)
pg_dump -h {{SOURCE_HOST}} -U {{USER}} -Fc -f /backup/{{PRODUCT_NAME}}_pre_migration_$(date +%Y%m%d_%H%M).dump {{DB}}

# Verify backup integrity
pg_restore -l /backup/{{PRODUCT_NAME}}_pre_migration_*.dump | head
```

### §2-3 Pre-Verification of the Rollback Scenario

- On staging, run the main operation → forced rollback → source-restore cycle at least once.
- Measure rollback duration and reflect it in the §5-2 table.
- Prove 0 user-data loss through a sample comparison.
:::

::: {.panel section="§3 Migration Steps (Step-by-step)"}
## §3 Migration Steps (Step-by-step)

---

### §3-1 Execution Order

<!-- col-widths: 8%, 15%, 30%, 15%, 17%, 15% -->
| Step | Time (KST) | Task | Owner | Verification Method | Estimated Duration |
|---|---|---|---|---|---|
| S-01 | T+0:00 | Block new writes (read-only mode) | {{owner}} | Confirm API returns 503 | 5 min |
| S-02 | T+0:05 | Final snapshot of the source | {{owner}} | Snapshot file hash | 10 min |
| S-03 | T+0:15 | Export data | {{owner}} | Row count matches | 30 min |
| S-04 | T+0:45 | Apply schema (target) | {{owner}} | Schema diff 0 | 5 min |
| S-05 | T+0:50 | Import data | {{owner}} | Row count / sample comparison | 40 min |
| S-06 | T+1:30 | Rebuild indexes / statistics | {{owner}} | `ANALYZE` completes | 15 min |
| S-07 | T+1:45 | Switch application endpoints | {{owner}} | Smoke test passes | 5 min |
| S-08 | T+1:50 | Unblock writes | {{owner}} | Normal traffic received | immediate |

### §3-2 Key Commands / Scripts

```bash
# S-01 read-only
psql -h {{SOURCE_HOST}} -c "ALTER DATABASE {{DB}} SET default_transaction_read_only = on;"

# S-03 export
pg_dump -h {{SOURCE_HOST}} -Fc --data-only -f /tmp/data.dump {{DB}}

# S-05 import
pg_restore -h {{TARGET_HOST}} -d {{DB}} -j 4 /tmp/data.dump
```

```sql
-- S-04 apply schema (e.g. new column / index)
ALTER TABLE {{TABLE_1}} ADD COLUMN {{new_col}} varchar(64) DEFAULT NULL;
CREATE INDEX CONCURRENTLY idx_{{TABLE_1}}_{{new_col}} ON {{TABLE_1}}({{new_col}});
```
:::

::: {.panel section="§4 Verification Procedure (Post-migration)"}
## §4 Verification Procedure (Post-migration)

---

### §4-1 Data Consistency Verification

<!-- col-widths: 25%, 35%, 40% -->
| Verification Type | Method | Pass Criteria |
|---|---|---|
| Row count | Compare `SELECT count(*)` between source/target | 100% match |
| Checksum | Per-table hash comparison (`md5_agg`) | 100% match |
| Sample comparison | Raw comparison of 100 random records | 100% match |
| FK integrity | Count of FK-violating rows | 0 |

```sql
-- Example row-count comparison
SELECT '{{TABLE_1}}' AS t, count(*) FROM {{TABLE_1}}
UNION ALL SELECT '{{TABLE_2}}', count(*) FROM {{TABLE_2}};
```

### §4-2 Functional Regression Test

- Run the E2E smoke-test suite (≤ 15 min).
- Manually verify each core scenario in Policy Definition §1-§4 once.
- Confirm every endpoint in API Spec §3 and §4 returns 200/201/204.

### §4-3 Performance Comparison

<!-- col-widths: 30%, 25%, 25%, 20% -->
| Metric | Before Migration | After Migration | Pass Criteria |
|---|---|---|---|
| Average response time (p50) | {{ms}} | {{ms}} | ≤ +10% |
| p99 response time | {{ms}} | {{ms}} | ≤ +20% |
| Error rate | {{%}} | {{%}} | ≤ baseline |
:::

::: {.panel section="§5 Rollback Procedure" style="warning"}
## §5 Rollback Procedure

---

### §5-1 Rollback Trigger Conditions

If **any one** of the following occurs, review rollback immediately:

- Data-consistency verification fails (row-count / checksum / sample mismatch).
- Core functional regression test fails.
- Error rate stays at 2x or more of baseline for 30+ minutes.
- p99 response time worsens by 50% or more versus baseline.
- A security / integrity issue is found.

### §5-2 Rollback Steps (reverse order)

<!-- col-widths: 8%, 35%, 15%, 25%, 17% -->
| Step | Task | Owner | Verification Method | Estimated Duration |
|---|---|---|---|---|
| R-01 | Revert application endpoints | {{owner}} | Smoke test passes against the source | 5 min |
| R-02 | Block writes (read-only) | {{owner}} | API returns 503 | 5 min |
| R-03 | Temporarily preserve the target (retain evidence) | {{owner}} | Snapshot file hash | 10 min |
| R-04 | Restore the source as canonical | {{owner}} | Read-only lifted | 5 min |
| R-05 | User notice (rollback notification) | {{owner}} | Confirm notice was sent | immediate |

### §5-3 Post-Rollback Follow-up

- Hold a rollback root-cause meeting (within T+24h) — record the outcome as a DEC item in the meeting notes (D4).
- Decide whether to discard or retain the remaining data in the target environment.
- Derive a retry schedule and follow-up items, and update the §1-2 schedule in this document.
:::

::: {.panel section="§6 Post-Migration Monitoring" style="info"}
## §6 Post-Migration Monitoring

---

### §6-1 Monitoring Metrics

<!-- col-widths: 25%, 35%, 20%, 20% -->
| Metric | Definition | Threshold (warn / crit) | Channel |
|---|---|---|---|
| Error rate | Proportion of 5xx responses | 1% / 5% | Slack #alert |
| p99 response time | 99th-percentile response | {{ms}} / {{ms}} | Slack #alert |
| DB connection count | Active connections | 70% / 90% | PagerDuty |
| Replication lag | replica lag (if applicable) | 5s / 30s | PagerDuty |

### §6-2 Observation Period

- **Intensive observation**: main operation + 24 hours — owner on-call.
- **Stabilization observation**: main operation + 7 days — review metrics once daily.
- **Closure declaration**: main operation + 14 days — record a migration-closure DEC in the meeting notes (D4).

### §6-3 Response Procedure

- When the warn threshold is reached, the owner performs initial analysis and reports within 10 minutes.
- When the crit threshold is reached, immediately convene a GO/NO-GO meeting for the §5 rollback procedure.
- Label all alerts with the `MIG-{{YYYYMMDD}}-NN` identifier for traceability.
:::
