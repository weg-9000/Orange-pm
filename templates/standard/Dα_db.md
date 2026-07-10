---
title: "[DB 스키마] {{PRODUCT_NAME}}"
type: etc
layer: DIRECT
version: 1.0
last_updated: 2026-05-30

publication:
  header:
    style: info
    body: |
      **{{PRODUCT_NAME}} DB 스키마**

      doc_id: {{DOC_ID}} 버전: {{VERSION}} 최종 수정: {{DATE}}
  meta:
    layout: two_equal
    cells:
      - panel:
          title: "관련 문서"
          body: |
            - [[page:[정책정의서] {{PRODUCT_NAME}}]]
            - [[page:[화면설계서] {{PRODUCT_NAME}}]]
      - change_history: 5
---

::: {.panel section="§1 스키마 개요"}
## §1 스키마 개요

---

### §1-1 DB 종류 / 버전

<!-- col-widths: 25%, 75% -->
| 항목 | 내용 |
|---|---|
| **DBMS** | {{PostgreSQL 15 / MySQL 8 / ...}} |
| **문자셋 / Collation** | {{utf8mb4 / utf8mb4_unicode_ci}} |
| **타임존** | UTC (저장) / KST (표시) |
| **스토리지 엔진** | {{InnoDB / heap}} |

### §1-2 명명 규칙

<!-- col-widths: 20%, 35%, 45% -->
| 대상 | 규칙 | 예시 |
|---|---|---|
| 테이블 | snake_case, 복수형 | `instances`, `users` |
| 컬럼 | snake_case, 단수 | `created_at`, `owner_id` |
| 인덱스 | `idx_{table}_{cols}` | `idx_instances_owner_id` |
| 유니크 인덱스 | `uq_{table}_{cols}` | `uq_users_email` |
| 외래키 | `fk_{table}_{ref_table}` | `fk_instances_users` |

### §1-3 공통 컬럼

<!-- col-widths: 18%, 18%, 10%, 18%, 36% -->
| 컬럼명 | 타입 | NULL | 기본값 | 설명 |
|---|---|---|---|---|
| `id` | `bigint` | NO | autoincrement | 기본키 |
| `created_at` | `timestamptz` | NO | `now()` | 생성 시각 (UTC) |
| `updated_at` | `timestamptz` | NO | `now()` | 갱신 시각 (UTC) |
| `deleted_at` | `timestamptz` | YES | NULL | soft delete 시각 |

### §1-4 ERD 다이어그램

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

::: {.panel section="§2 테이블 — {{TABLE_1}}"}
## §2 테이블 — {{TABLE_1}}

---

### §2-1 컬럼 정의

<!-- col-widths: 18%, 18%, 8%, 18%, 12%, 26% -->
| 컬럼명 | 타입 | NULL | 기본값 | 제약 | 설명 |
|---|---|---|---|---|---|
| `id` | `bigint` | NO | autoincrement | PK | 기본키 |
| `owner_id` | `bigint` | NO | — | FK → users.id | 소유자 |
| `name` | `varchar(128)` | NO | — | UQ(owner_id, name) | 표시 이름 |
| `status` | `varchar(32)` | NO | `'pending'` | check | 상태 |
| `config` | `jsonb` | YES | `'{}'` | — | 설정값 |
| `created_at` | `timestamptz` | NO | `now()` | — | 생성 시각 |
| `updated_at` | `timestamptz` | NO | `now()` | — | 갱신 시각 |
| `deleted_at` | `timestamptz` | YES | NULL | — | soft delete |

### §2-2 인덱스

<!-- col-widths: 35%, 30%, 15%, 20% -->
| 인덱스명 | 컬럼 | 유형 | 용도 |
|---|---|---|---|
| `pk_{{TABLE_1}}` | (id) | btree (PK) | 기본키 |
| `uq_{{TABLE_1}}_owner_name` | (owner_id, name) | unique | 소유자별 이름 중복 방지 |
| `idx_{{TABLE_1}}_status` | (status) | btree | 상태 필터 |
| `idx_{{TABLE_1}}_created_at` | (created_at desc) | btree | 최신순 정렬 |

### §2-3 외래키 / 관계

```mermaid
erDiagram
  USERS ||--o{ {{TABLE_1}} : "owner_id"
  {{TABLE_1}} ||--o{ {{TABLE_2}} : "parent_id"
```

- `owner_id` → `users.id` ON DELETE RESTRICT (소유자 삭제 시 차단).
- `{{TABLE_2}}.parent_id` → `{{TABLE_1}}.id` ON DELETE CASCADE.

### §2-4 비즈니스 규칙

- `status` check constraint: `status IN ('pending', 'active', 'suspended', 'deleted')`.
- soft delete 시 `deleted_at` 기록, 조회 쿼리는 `WHERE deleted_at IS NULL` 기본 적용.
- `name` 변경 시 audit log 테이블에 before/after 기록 (트리거 또는 애플리케이션 레벨).
:::

::: {.panel section="§3 테이블 — {{TABLE_2}}"}
## §3 테이블 — {{TABLE_2}}

---

### §3-1 컬럼 정의

<!-- col-widths: 18%, 18%, 8%, 18%, 12%, 26% -->
| 컬럼명 | 타입 | NULL | 기본값 | 제약 | 설명 |
|---|---|---|---|---|---|
| `id` | `bigint` | NO | autoincrement | PK | 기본키 |
| `parent_id` | `bigint` | NO | — | FK → {{TABLE_1}}.id | 상위 리소스 |
| `key` | `varchar(64)` | NO | — | UQ(parent_id, key) | 속성 키 |
| `value` | `text` | YES | NULL | — | 속성 값 |
| `created_at` | `timestamptz` | NO | `now()` | — | 생성 시각 |
| `updated_at` | `timestamptz` | NO | `now()` | — | 갱신 시각 |

### §3-2 인덱스

<!-- col-widths: 35%, 30%, 15%, 20% -->
| 인덱스명 | 컬럼 | 유형 | 용도 |
|---|---|---|---|
| `pk_{{TABLE_2}}` | (id) | btree (PK) | 기본키 |
| `uq_{{TABLE_2}}_parent_key` | (parent_id, key) | unique | 키 중복 방지 |
| `idx_{{TABLE_2}}_parent_id` | (parent_id) | btree | 부모 조인 |

### §3-3 외래키 / 관계

- `parent_id` → `{{TABLE_1}}.id` ON DELETE CASCADE.

### §3-4 비즈니스 규칙

- `key` 는 영문 소문자 + 숫자 + `_` 만 허용 (`^[a-z][a-z0-9_]*$`).
- `value` 크기 제한: 64KB (애플리케이션 레벨 검증).
:::

::: {.panel section="§4 인덱스 / 성능 정책"}
## §4 인덱스 / 성능 정책

---

### §4-1 자주 사용되는 쿼리 패턴

<!-- col-widths: 25%, 50%, 25% -->
| 패턴 | 예시 쿼리 | 활용 인덱스 |
|---|---|---|
| 소유자별 목록 | `SELECT * FROM {{TABLE_1}} WHERE owner_id=? AND deleted_at IS NULL ORDER BY created_at DESC` | `idx_{{TABLE_1}}_created_at` + `owner_id` |
| 상태 필터 | `SELECT * FROM {{TABLE_1}} WHERE status=? AND deleted_at IS NULL` | `idx_{{TABLE_1}}_status` |
| 속성 조회 | `SELECT key, value FROM {{TABLE_2}} WHERE parent_id=?` | `idx_{{TABLE_2}}_parent_id` |

### §4-2 인덱스 전략

- 모든 외래키 컬럼은 단일 컬럼 인덱스 보장 (조인 / FK 검증 성능).
- 다중 컬럼 인덱스는 좌측 prefix 활용 가능하도록 카디널리티 높은 컬럼을 앞에 배치.
- soft delete 대상 테이블은 `deleted_at IS NULL` 조건을 부분 인덱스로 고려.

### §4-3 파티셔닝

<!-- col-widths: 25%, 25%, 50% -->
| 테이블 | 전략 | 비고 |
|---|---|---|
| `{{TABLE_LARGE}}` | 월별 range (`created_at`) | 1년 보존, 이후 archive |
| 기타 | 없음 | 단일 테이블 |
:::

::: {.panel section="§5 데이터 보존 / 백업 정책" style="info"}
## §5 데이터 보존 / 백업 정책

---

### §5-1 보존 기간

<!-- col-widths: 30%, 25%, 45% -->
| 데이터 유형 | 보존 기간 | 처리 |
|---|---|---|
| 운영 데이터 | 무기한 | soft delete + 주기적 archive |
| 감사 로그 | 5년 | cold storage 이관 |
| 임시 / 캐시 | 7일 | TTL 자동 만료 |

### §5-2 백업

<!-- col-widths: 25%, 25%, 50% -->
| 유형 | 주기 | 보존 |
|---|---|---|
| 전체 백업 | 일 1회 (02:00 UTC) | 30일 |
| 증분 백업 | 시간당 | 7일 |
| WAL / binlog | 연속 | 7일 (PITR 가능) |

### §5-3 복구 목표

- **RPO**: ≤ 1시간
- **RTO**: ≤ 4시간
- 분기 1회 복구 리허설 수행, 결과는 회의록(D4)에 기록.
:::
