---
title: "[API 스펙] {{PRODUCT_NAME}}"
type: etc
layer: DIRECT
version: 1.0
last_updated: 2026-05-30

publication:
  header:
    style: info
    body: |
      **{{PRODUCT_NAME}} API 스펙**

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

::: {.panel section="§1 API 개요"}
## §1 API 개요

---

### §1-1 인증 방식

<!-- col-widths: 20%, 80% -->
| 항목 | 내용 |
|---|---|
| **인증 방식** | {{OAuth2 / API Key / mTLS / JWT}} |
| **토큰 수명** | {{access token TTL}} / {{refresh token TTL}} |
| **재발급 정책** | {{재발급 절차}} |

### §1-2 base URL / 환경

<!-- col-widths: 15%, 45%, 40% -->
| 환경 | base URL | 비고 |
|---|---|---|
| **prod** | `https://api.{{PRODUCT_DOMAIN}}` | 실 서비스 |
| **staging** | `https://api-stg.{{PRODUCT_DOMAIN}}` | QA / 통합 검증 |
| **dev** | `https://api-dev.{{PRODUCT_DOMAIN}}` | 개발자 샌드박스 |

### §1-3 rate limit / 쿼터

<!-- col-widths: 25%, 25%, 50% -->
| 구분 | 한도 | 적용 단위 |
|---|---|---|
| **기본 한도** | {{N}} req/min | API Key |
| **버스트** | {{M}} req/sec | API Key |
| **쿼터 초과** | HTTP 429 + `Retry-After` 헤더 | — |

### §1-4 공통 응답 포맷

```json
{
  "data": { },
  "meta": { "request_id": "req_xxx", "timestamp": "2026-05-30T12:00:00Z" },
  "error": null
}
```

에러 발생 시:

```json
{
  "data": null,
  "meta": { "request_id": "req_xxx", "timestamp": "2026-05-30T12:00:00Z" },
  "error": { "code": "{{ERROR_CODE}}", "message": "{{메시지}}", "details": { } }
}
```
:::

::: {.panel section="§2 공통 헤더 / 인증"}
## §2 공통 헤더 / 인증

---

### §2-1 공통 요청 헤더

<!-- col-widths: 25%, 10%, 35%, 30% -->
| 헤더명 | 필수 | 설명 | 예시 |
|---|---|---|---|
| `Authorization` | Y | Bearer 토큰 또는 API Key | `Bearer eyJhbGc...` |
| `Content-Type` | Y | 요청 본문 MIME | `application/json` |
| `X-Request-Id` | N | 클라이언트 추적 ID | `req_client_001` |
| `Accept-Language` | N | 응답 메시지 로케일 | `ko-KR` |

### §2-2 인증 토큰 발급 절차

```bash
curl -X POST https://api.{{PRODUCT_DOMAIN}}/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "{{CLIENT_ID}}",
    "client_secret": "{{CLIENT_SECRET}}",
    "grant_type": "client_credentials"
  }'
```

응답:

```json
{
  "access_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```
:::

::: {.panel section="§3 엔드포인트 — {{ENDPOINT_GROUP_1}}"}
## §3 엔드포인트 — {{ENDPOINT_GROUP_1}}

---

### §3-1 GET /api/{{ENDPOINT_GROUP_1}} — 목록 조회

<!-- col-widths: 20%, 15%, 10%, 55% -->
| 파라미터 | 위치 | 필수 | 설명 |
|---|---|---|---|
| `page` | query | N | 페이지 번호 (기본 1) |
| `size` | query | N | 페이지 크기 (기본 20, 최대 100) |
| `sort` | query | N | 정렬 필드 (예: `-created_at`) |

response 스키마:

```json
{
  "data": [
    { "id": "...", "name": "...", "created_at": "..." }
  ],
  "meta": { "page": 1, "size": 20, "total": 0 }
}
```

예시:

```bash
curl -X GET "https://api.{{PRODUCT_DOMAIN}}/api/{{ENDPOINT_GROUP_1}}?page=1&size=20" \
  -H "Authorization: Bearer {{TOKEN}}"
```

### §3-2 POST /api/{{ENDPOINT_GROUP_1}} — 생성

request 본문:

```json
{
  "name": "{{name}}",
  "config": { }
}
```

response: `201 Created` + 생성된 리소스.

### §3-3 GET /api/{{ENDPOINT_GROUP_1}}/{id} — 단건 조회

response: 단일 리소스 객체. 404 시 `RESOURCE_NOT_FOUND`.

### §3-4 PATCH /api/{{ENDPOINT_GROUP_1}}/{id} — 수정

부분 수정 지원. 변경 가능한 필드만 전달. response: `200 OK` + 갱신된 리소스.

### §3-5 DELETE /api/{{ENDPOINT_GROUP_1}}/{id} — 삭제

response: `204 No Content`. 종속 자원 처리는 정책정의서 §4 참조.

### §3-6 에러 코드

<!-- col-widths: 30%, 15%, 55% -->
| code | http_status | 발생 조건 |
|---|---|---|
| `{{GROUP1}}_NOT_FOUND` | 404 | 존재하지 않는 ID |
| `{{GROUP1}}_CONFLICT` | 409 | 동일 이름 중복 |
| `{{GROUP1}}_VALIDATION` | 422 | 입력 유효성 실패 |
:::

::: {.panel section="§4 엔드포인트 — {{ENDPOINT_GROUP_2}}"}
## §4 엔드포인트 — {{ENDPOINT_GROUP_2}}

---

### §4-1 GET /api/{{ENDPOINT_GROUP_2}} — 목록 조회

<!-- col-widths: 20%, 15%, 10%, 55% -->
| 파라미터 | 위치 | 필수 | 설명 |
|---|---|---|---|
| `{{filter}}` | query | N | {{필터 설명}} |

response:

```json
{ "data": [ ], "meta": { } }
```

### §4-2 POST /api/{{ENDPOINT_GROUP_2}} — 생성

```json
{ "{{field}}": "{{value}}" }
```

### §4-3 GET /api/{{ENDPOINT_GROUP_2}}/{id} — 단건 조회

### §4-4 PATCH /api/{{ENDPOINT_GROUP_2}}/{id} — 수정

### §4-5 DELETE /api/{{ENDPOINT_GROUP_2}}/{id} — 삭제
:::

::: {.panel section="§5 공통 에러 코드"}
## §5 공통 에러 코드

---

<!-- col-widths: 30%, 15%, 25%, 30% -->
| code | http_status | 의미 | 발생 조건 |
|---|---|---|---|
| `UNAUTHENTICATED` | 401 | 인증 실패 | 토큰 누락/만료 |
| `FORBIDDEN` | 403 | 권한 없음 | 역할/스코프 부족 |
| `NOT_FOUND` | 404 | 리소스 없음 | 경로/ID 미존재 |
| `METHOD_NOT_ALLOWED` | 405 | 허용 메서드 아님 | 잘못된 HTTP 메서드 |
| `VALIDATION_ERROR` | 422 | 입력 유효성 실패 | 스키마 위배 |
| `RATE_LIMITED` | 429 | 호출 한도 초과 | rate limit 초과 |
| `INTERNAL` | 500 | 서버 내부 오류 | 미처리 예외 |
| `UPSTREAM_UNAVAILABLE` | 503 | 종속 시스템 장애 | 외부 의존성 실패 |
:::

::: {.panel section="§6 변경 이력 / 버전 호환" style="info"}
## §6 변경 이력 / 버전 호환

---

### §6-1 버전 정책

- **메이저 (vN)** — 호환 불가 변경. URL prefix `/v{N}/` 변경 (예: `/v1/` → `/v2/`).
- **마이너** — 호환 가능 추가 (필드 추가, 새 엔드포인트). 기존 클라이언트 영향 없음.
- **패치** — 버그 수정. 동작 명세 무변경.

### §6-2 deprecation 절차

<!-- col-widths: 15%, 35%, 50% -->
| 단계 | 시점 | 처리 |
|---|---|---|
| 공지 | 폐지 ≥ 6개월 전 | response 헤더 `Deprecation`, 릴리스 노트 |
| 경고 | 폐지 ≥ 3개월 전 | response 헤더 `Sunset` (RFC 8594) |
| 폐지 | 폐지일 | HTTP 410 Gone |
:::
