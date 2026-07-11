---
name: search
description: >
  Combines graph.json keyword matching (BM25 approximation) with Neo4j vector-index
  kNN search via RRF to return related nodes/chunks.
  Used to gather prior context before calling /explore, to find candidate conflicts
  for /integrate, and for the PM to quickly locate a policy.
triggers:
  - /search {query}
  - /search {query} {product}
effort: low
model: haiku
---

## Bootstrap cache guard (Improvement F — CONTEXT_OPTIMIZATION.md)

On first entry to a session, load `CONTEXT/_session-bootstrap.md` exactly once.
If this file has already been read in the same session, do not re-read it.
If the cache is missing or stale, refresh it with the following command before proceeding:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```

This guard replaces re-loading the 6 source files layer-config / about-pm / project-rules /
brand-voice / doc-layer-schema / team-members individually.
Reading the source files directly is allowed only when strictly required for this skill's core task.


# /search

## Preconditions
- graph.json must exist under PROJECTS/{product}/graph/.
- Vector search assumes prior loading (`graph_to_neo4j.py`) + the embedding pipeline
  (`embed_pipeline.py`) have already run. See Step 2 for details.
- If Neo4j is not connected or the embedding index is missing, return BM25-only results and show [vector search skipped].

## Execution steps

### Step 1 — BM25 approximation (local)
Read the title, description, and tags fields from every node in graph.json.
Compute a score for each query token using TF weighting.
Select the top-30 candidates.

### Step 2 — Vector kNN search (Neo4j)

> **Precondition (the vector path is not always available)**
> The `chunk_embedding` vector index and the `(source)-[:HAS_CHUNK]->(chunk)` relationship
> referenced by the Cypher below are created only by `embed_pipeline.py`.
> To use vector search, the following two scripts must have already been run, in order:
>   1. `graph_to_neo4j.py` — base-loads graph.json into Neo4j
>   2. `embed_pipeline.py` — generates chunk embeddings + the `chunk_embedding` index
> This skill/hook does not invoke these two scripts automatically (manual prerequisite work).
> If the index/embeddings are missing, the vector path won't function, and in that
> case it falls back gracefully to the Step 1 BM25-only results (shown as [vector search skipped]).

If Neo4j is reachable and the above preconditions are met, run the Cypher below.

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

Generating query_embedding:
  If ANTHROPIC_API_KEY exists → voyage-3
  If not → show [vector search skipped] and proceed to Step 3

### Step 3 — RRF combination
score = Σ 1 / (60 + rank)
Combine BM25 top-30 + vector top-30 via RRF to determine the final ranking.

### Step 4 — Output results
| Rank | doc_id | Title | layer | BM25 rank | Vector rank | Related section |

If Neo4j is not connected, show BM25 ranking only.
If there are 0 results, suggest shortening the query or using /explore.

## Notes
- This skill is read-only. It does not modify any files.
- It does not call the Confluence MCP.
- Results are for reference only; actual loading happens in /explore, /write, /integrate.
