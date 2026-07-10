---
name: search
description: >
  graph.json 키워드 매칭(BM25 근사)과 Neo4j 벡터 인덱스 kNN 검색을
  RRF로 결합해 관련 노드·청크를 반환한다.
  /explore 호출 전 사전 컨텍스트 파악, /integrate 충돌 후보 탐색,
  PM의 빠른 정책 위치 확인에 활용한다.
triggers:
  - /search {query}
  - /search {query} {product}
effort: low
model: haiku
---

## Bootstrap 캐시 가드 (개선안 F — CONTEXT_OPTIMIZATION.md)

세션 첫 진입 시 `CONTEXT/_session-bootstrap.md` 를 1회만 로드한다.
이미 같은 세션에서 본 파일을 읽었다면 재독을 금지한다.
캐시가 없거나 stale 이면 다음 명령으로 갱신한 뒤 진행한다:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```

본 가드는 layer-config / about-pm / project-rules / brand-voice /
doc-layer-schema / team-members 6개 원본 파일 재로드를 대체한다.
원본 파일 직접 Read 는 본 skill 의 핵심 작업에 필수인 경우에만 허용된다.


# /search

## 전제 조건
- graph.json 이 PROJECTS/{product}/graph/ 에 존재해야 한다.
- 벡터 검색은 선행 적재(`graph_to_neo4j.py`)+ 임베딩 파이프라인(`embed_pipeline.py`)
  실행을 전제로 한다. 자세한 조건은 단계 2 참조.
- Neo4j 미연결 또는 임베딩 인덱스 부재 시 BM25 단독 결과만 반환하고 [벡터 검색 생략] 표시.

## 실행 단계

### 단계 1 — BM25 근사 (로컬)
graph.json 의 모든 노드에서 title·description·tags 필드를 읽는다.
query 토큰 각각에 대해 TF 가중치로 점수를 계산한다.
Top-30 후보를 선정한다.

### 단계 2 — 벡터 kNN 검색 (Neo4j)

> **전제 (벡터 경로는 항상 사용 가능한 것이 아님)**
> 아래 Cypher 가 참조하는 `chunk_embedding` 벡터 인덱스와
> `(source)-[:HAS_CHUNK]->(chunk)` 관계는 오직 `embed_pipeline.py` 만 생성한다.
> 따라서 벡터 검색을 쓰려면 사전에 다음 두 스크립트를 순서대로 실행했어야 한다:
>   1. `graph_to_neo4j.py` — graph.json 을 Neo4j 로 베이스 적재
>   2. `embed_pipeline.py` — 청크 임베딩 + `chunk_embedding` 인덱스 생성
> 본 스킬·훅은 이 두 스크립트를 자동 호출하지 않는다(수동 선행 작업).
> 인덱스/임베딩이 없으면 벡터 경로는 동작하지 않으며,
> 이 경우 단계 1 의 BM25 단독 결과로 graceful 폴백한다([벡터 검색 생략] 표시).

Neo4j 연결 가능 + 위 전제 충족 시 아래 Cypher 를 실행한다.

```cypher
CALL db.index.vector.queryNodes(
  'chunk_embedding', 30, $query_embedding
)
YIELD node AS chunk, score
MATCH (source)-[:HAS_CHUNK]->(chunk)
RETURN source.doc_id AS doc_id,
       source.title   AS title,
       chunk.section_title AS section,
       score
ORDER BY score DESC
```

query_embedding 생성:
  ANTHROPIC_API_KEY 존재 시 → voyage-3
  미존재 시 → [벡터 검색 생략] 표시 후 단계 3으로

### 단계 3 — RRF 결합
score = Σ 1 / (60 + rank)
BM25 Top-30 + 벡터 Top-30 을 RRF 로 결합해 최종 순위 결정.

### 단계 4 — 결과 출력
| 순위 | doc_id | 제목 | layer | BM25순위 | 벡터순위 | 관련 섹션 |

Neo4j 미연결 시 BM25 순위만 표시.
결과 0건 시 query 축약 또는 /explore 사용 안내.

## 주의사항
- 이 스킬은 읽기 전용이다. 어떤 파일도 수정하지 않는다.
- Confluence MCP는 호출하지 않는다.
- 결과는 참고용이며 /explore·/write·/integrate 에서 실제 로드가 이루어진다.
