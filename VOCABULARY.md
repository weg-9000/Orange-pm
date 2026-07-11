# Vocabulary — Canonical Data-Contract Tokens

These tokens are **data contracts** shared by skills, agents, scripts, and tests.
They appear inside `graph.json`, Hub documents (`decisions.md`, drafts, reports),
and are matched by Python parsers. **Never rename them casually** — a change here
is a breaking (MAJOR) change and must update every consumer plus tests.

## Graph edge types (`graph.json` → `edges[].type`)

Validated by `scripts/validate_graph.py` (`VALID_EDGE_TYPES`), consumed by
`fanout_dag.py`, `graph_emit.py`, `build_bootstrap.py`.

| Token | Meaning |
|---|---|
| `prerequisite` | source must be decided/built before target |
| `bidirectional-ref` | mutual reference between two nodes |
| `duplicate-definition` | same value defined in both nodes (SSoT violation candidate) |
| `feature-link` | functional integration between features |
| `event-definition` | source defines events the target consumes |
| `security-standard` | source sets the security baseline for target |
| `implements` | screen implements a policy section |
| `term-standard` | source is the terminology authority |
| `ux-standard` | source sets UX conventions |
| `billing-target` | target is subject to billing rules in source |
| `ops-procedure` | operational procedure dependency |

Node types: `policy` | `screen` (unchanged).

## decisions.md table contract

Parsed by `scripts/session_emit.py`.

Canonical header row:

```
| ID | Decision | Decider | Date | Status |
```

Status cell tokens (emoji + word, either alone is recognized):

| Token | Meaning |
|---|---|
| `✅ approved` | approved by PM |
| `❌ rejected` | rejected |
| `🟡 on-hold` | held for later |
| `⬜ pending` | not yet reviewed |

## Inline markers (in drafts, reports, session logs)

| Marker | Used when |
|---|---|
| `[unverified]` | fact not yet cross-checked |
| `[draft]` | content still tentative |
| `[needs-review]` | interpretation/guess area |
| `[needs-confirmation]` / `[needs-confirmation:reason]` | unconfirmed/TBD value — guessing prohibited, register in open-issues |
| `[in-progress]` | deliverable not finished |
| `[low-quality-source]` | source credibility doubt |
| `[{capability} skipped]` | connector absent — step skipped (e.g. `[chat skipped]`) |
| `[reversal-history]` | decision was reversed before |

## Document-layer terms

| Term | English |
|---|---|
| 정책서 | policy document |
| 화면설계서 | screen design spec |
| 요구사항정의서 | requirements definition |
| 용어 사전 | glossary |
| 공통 정책 | common policy (`{PREFIX}-B`) |
| 제품 Delta | product delta (`{PREFIX}-C`) |
| 작업지시서 | Work Order (WO) |
| 초안 | draft |
| 확정 | frozen (`v1.0-frozen`) |

## Counting / empty expressions (parsed by `render_transpose.py`)

| Token | Meaning |
|---|---|
| `0 items` | zero count |
| `none` | empty |

Statuses `Draft` / `Approved` / `Deprecated`, phase names, gate file names,
capability labels (`wiki`/`chat`/`design`/`repo`/`tasks`) were already English.
