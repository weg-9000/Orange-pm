---
title: "[API Spec] {{PRODUCT_NAME}}"
type: etc
layer: DIRECT
version: 1.0
last_updated: 2026-05-30

publication:
  header:
    style: info
    body: |
      **{{PRODUCT_NAME}} API Spec**

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

::: {.panel section="§1 API Overview"}
## §1 API Overview

---

### §1-1 Authentication Method

<!-- col-widths: 20%, 80% -->
| Item | Content |
|---|---|
| **Auth Method** | {{OAuth2 / API Key / mTLS / JWT}} |
| **Token Lifetime** | {{access token TTL}} / {{refresh token TTL}} |
| **Reissue Policy** | {{reissue procedure}} |

### §1-2 Base URL / Environments

<!-- col-widths: 15%, 45%, 40% -->
| Environment | Base URL | Notes |
|---|---|---|
| **prod** | `https://api.{{PRODUCT_DOMAIN}}` | Live service |
| **staging** | `https://api-stg.{{PRODUCT_DOMAIN}}` | QA / integration testing |
| **dev** | `https://api-dev.{{PRODUCT_DOMAIN}}` | Developer sandbox |

### §1-3 Rate Limit / Quota

<!-- col-widths: 25%, 25%, 50% -->
| Category | Limit | Applied Unit |
|---|---|---|
| **Default Limit** | {{N}} req/min | API Key |
| **Burst** | {{M}} req/sec | API Key |
| **Quota Exceeded** | HTTP 429 + `Retry-After` header | — |

### §1-4 Common Response Format

```json
{
  "data": { },
  "meta": { "request_id": "req_xxx", "timestamp": "2026-05-30T12:00:00Z" },
  "error": null
}
```

On error:

```json
{
  "data": null,
  "meta": { "request_id": "req_xxx", "timestamp": "2026-05-30T12:00:00Z" },
  "error": { "code": "{{ERROR_CODE}}", "message": "{{message}}", "details": { } }
}
```
:::

::: {.panel section="§2 Common Headers / Authentication"}
## §2 Common Headers / Authentication

---

### §2-1 Common Request Headers

<!-- col-widths: 25%, 10%, 35%, 30% -->
| Header | Required | Description | Example |
|---|---|---|---|
| `Authorization` | Y | Bearer token or API Key | `Bearer eyJhbGc...` |
| `Content-Type` | Y | Request body MIME | `application/json` |
| `X-Request-Id` | N | Client tracking ID | `req_client_001` |
| `Accept-Language` | N | Response message locale | `ko-KR` |

### §2-2 Auth Token Issuance Procedure

```bash
curl -X POST https://api.{{PRODUCT_DOMAIN}}/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "{{CLIENT_ID}}",
    "client_secret": "{{CLIENT_SECRET}}",
    "grant_type": "client_credentials"
  }'
```

Response:

```json
{
  "access_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```
:::

::: {.panel section="§3 Endpoints — {{ENDPOINT_GROUP_1}}"}
## §3 Endpoints — {{ENDPOINT_GROUP_1}}

---

### §3-1 GET /api/{{ENDPOINT_GROUP_1}} — List

<!-- col-widths: 20%, 15%, 10%, 55% -->
| Parameter | Location | Required | Description |
|---|---|---|---|
| `page` | query | N | Page number (default 1) |
| `size` | query | N | Page size (default 20, max 100) |
| `sort` | query | N | Sort field (e.g. `-created_at`) |

response schema:

```json
{
  "data": [
    { "id": "...", "name": "...", "created_at": "..." }
  ],
  "meta": { "page": 1, "size": 20, "total": 0 }
}
```

Example:

```bash
curl -X GET "https://api.{{PRODUCT_DOMAIN}}/api/{{ENDPOINT_GROUP_1}}?page=1&size=20" \
  -H "Authorization: Bearer {{TOKEN}}"
```

### §3-2 POST /api/{{ENDPOINT_GROUP_1}} — Create

request body:

```json
{
  "name": "{{name}}",
  "config": { }
}
```

response: `201 Created` + the created resource.

### §3-3 GET /api/{{ENDPOINT_GROUP_1}}/{id} — Get by ID

response: a single resource object. On 404, `RESOURCE_NOT_FOUND`.

### §3-4 PATCH /api/{{ENDPOINT_GROUP_1}}/{id} — Update

Supports partial updates. Send only the fields that change. response: `200 OK` + the updated resource.

### §3-5 DELETE /api/{{ENDPOINT_GROUP_1}}/{id} — Delete

response: `204 No Content`. See the policy definition §4 for handling of dependent resources.

### §3-6 Error Codes

<!-- col-widths: 30%, 15%, 55% -->
| code | http_status | Trigger Condition |
|---|---|---|
| `{{GROUP1}}_NOT_FOUND` | 404 | ID does not exist |
| `{{GROUP1}}_CONFLICT` | 409 | Duplicate name |
| `{{GROUP1}}_VALIDATION` | 422 | Input validation failed |
:::

::: {.panel section="§4 Endpoints — {{ENDPOINT_GROUP_2}}"}
## §4 Endpoints — {{ENDPOINT_GROUP_2}}

---

### §4-1 GET /api/{{ENDPOINT_GROUP_2}} — List

<!-- col-widths: 20%, 15%, 10%, 55% -->
| Parameter | Location | Required | Description |
|---|---|---|---|
| `{{filter}}` | query | N | {{filter description}} |

response:

```json
{ "data": [ ], "meta": { } }
```

### §4-2 POST /api/{{ENDPOINT_GROUP_2}} — Create

```json
{ "{{field}}": "{{value}}" }
```

### §4-3 GET /api/{{ENDPOINT_GROUP_2}}/{id} — Get by ID

### §4-4 PATCH /api/{{ENDPOINT_GROUP_2}}/{id} — Update

### §4-5 DELETE /api/{{ENDPOINT_GROUP_2}}/{id} — Delete
:::

::: {.panel section="§5 Common Error Codes"}
## §5 Common Error Codes

---

<!-- col-widths: 30%, 15%, 25%, 30% -->
| code | http_status | Meaning | Trigger Condition |
|---|---|---|---|
| `UNAUTHENTICATED` | 401 | Authentication failed | Token missing/expired |
| `FORBIDDEN` | 403 | No permission | Insufficient role/scope |
| `NOT_FOUND` | 404 | Resource not found | Path/ID does not exist |
| `METHOD_NOT_ALLOWED` | 405 | Method not allowed | Wrong HTTP method |
| `VALIDATION_ERROR` | 422 | Input validation failed | Schema violation |
| `RATE_LIMITED` | 429 | Call limit exceeded | Rate limit exceeded |
| `INTERNAL` | 500 | Internal server error | Unhandled exception |
| `UPSTREAM_UNAVAILABLE` | 503 | Dependent system failure | External dependency failure |
:::

::: {.panel section="§6 Change History / Version Compatibility" style="info"}
## §6 Change History / Version Compatibility

---

### §6-1 Versioning Policy

- **Major (vN)** — a breaking change. Changes the URL prefix `/v{N}/` (e.g. `/v1/` → `/v2/`).
- **Minor** — a backward-compatible addition (new field, new endpoint). No impact on existing clients.
- **Patch** — a bug fix. No change to behavior spec.

### §6-2 Deprecation Procedure

<!-- col-widths: 15%, 35%, 50% -->
| Stage | Timing | Handling |
|---|---|---|
| Notice | ≥ 6 months before retirement | response header `Deprecation`, release notes |
| Warning | ≥ 3 months before retirement | response header `Sunset` (RFC 8594) |
| Retirement | Retirement date | HTTP 410 Gone |
:::
