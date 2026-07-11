#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Topologically sort graph.json and generate Work Order files.

Change history:
    v1.0: initial implementation (policy nodes only)
    v2.0: policy + screen dual-track support / {PREFIX}-A scheme /
          edge ID numbering / index.md track split / WO type field added
    v2.1: index.json emitted alongside (improvement G — render/integrate
          consume WO metadata directly without parsing markdown tables)

Behavior:
    1. load graph.json + assign edge IDs
    2. collect policy section nodes and screen nodes separately
    3. compute levels (parallelizable groups) via unified Kahn topological sort
    4. pre-assign WO IDs (policy first, screen after)
    5. generate policy WO files (DEFAULT_POLICY_TEMPLATE)
    6. generate screen WO files (SCREEN_TEMPLATE)
    7. generate work-orders/index.md (tracks split)
    8. generate work-orders/index.json (machine-readable)

exit code:
    0 = success
    1 = graph.json load/validation failure
    2 = usage error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


# ── templates ─────────────────────────────────────────────────────────────────

DEFAULT_POLICY_TEMPLATE = """\
# Work Order: {WO_ID} — {SECTION_TITLE}

**Project**: `{PRODUCT_NAME}`
**type**: `policy`
**Generated at**: `{GENERATED_AT}`
**graph.json hash**: `{GRAPH_HASH}`
**level**: {LEVEL} (topological-sort parallelizable group)

---

## 1. Assigned scope

- **Document**: `{NODE_NAME}` (role: `{NODE_ROLE}`)
- **Section number**: `{SECTION_ID}`
- **Section title**: `{SECTION_TITLE}`
- **Authoring mode**: `NEW`
- **Output file**: `drafts/{WO_ID}.draft.md`

---

## 2. Immutable inputs

- **decisions.md snapshot hash**: `{DECISIONS_HASH}`
- **graph.json hash**: `{GRAPH_HASH}`

---

## 3. Reference contract

### 3.1 Edges this section **references** (precondition, frozen)

{OUTGOING_EDGES}

### 3.2 Edges that **reference** this section

{INCOMING_EDGES}

### 3.3 Related screen WOs

{RELATED_SCREEN_WOS}

---

## 4. Work instructions

### 4.1 Section summary

{SECTION_SUMMARY}

### 4.2 Prerequisite completion conditions

{LEVEL_DEPS}

---

## 5. Self-verification checklist

- [ ] no violation of the canonical `decisions.md` DEC table (`Approval=✅`) (conflict with pending `⬜` is WARN — see CONTEXT/dec-schema)
- [ ] frozen values from the reference contract reflected verbatim
- [ ] terminology matches the `{PREFIX_VAL}-A` vocabulary standard
- [ ] TBD items registered in `open-issues.md`
- [ ] self-contained (this section reads meaningfully on its own)
- [ ] no layer-boundary violation
- [ ] terminology/rule consistency with related screen WOs verified

---

## 6. Prohibited

- adding new dependencies not in the reference contract
- crossing layer boundaries
- editing other WO drafts
- editing the `decisions.md` DEC table directly (DEC registration via /write·/su·/sc etc.; approval only via /dec-approve — CONTEXT/dec-schema §5)

---

## 7. Post-completion steps

1. save `drafts/{WO_ID}.draft.md`
2. `/review drafts/{WO_ID}.draft.md`
3. `/lc {PRODUCT_NAME}` → `/sc {PRODUCT_NAME}`

---

## Workflow Connections

<!-- wikilinks:start -->
[WIKILINKS_PLACEHOLDER]
<!-- wikilinks:end -->
"""

SCREEN_TEMPLATE = """\
# Work Order: {WO_ID} — {SCREEN_NAME}

**Project**: `{PRODUCT_NAME}`
**type**: `screen`
**Generated at**: `{GENERATED_AT}`
**graph.json hash**: `{GRAPH_HASH}`
**level**: {LEVEL} (topological-sort parallelizable group)

---

## 1. Assigned scope

- **Screen ID**: `{SCREEN_ID}`
- **Screen name**: `{SCREEN_NAME}`
- **Purpose**: {PURPOSE}
- **Linked requirement ID**: `{REQ_ID}`
- **Related policy WO ID**: {POLICY_WO_ID}
- **Output file**: `drafts/{WO_ID}.draft.md`

---

## 2. Immutable inputs

- **decisions.md snapshot hash**: `{DECISIONS_HASH}`
- **graph.json hash**: `{GRAPH_HASH}`

---

## 3. Reference contract

### 3.1 Related policy WO implements edges

{IMPLEMENTS_EDGES}

### 3.2 Adjacent screen dependency edges

{SCREEN_EDGES}

---

## 4. Work instructions

### 4.1 Interaction sequence authoring requirements

Define all 4 states:
- **idle**: initial entry state (UI composition + entry conditions)
- **loading**: async-processing state (spinner/skeleton and other UI changes)
- **success**: normal completion state (result display + next actions)
- **error**: error state (error message + error code)

Define exit/cancel/back handling as separate items.

### 4.2 Microcopy authoring requirements

- button labels (no duplicates within the same screen)
- input field placeholders + helper text
- success/error/warning messages (including `{PREFIX_VAL}-A` error codes)
- tooltips and empty-state copy

### 4.3 Prerequisite completion conditions

{LEVEL_DEPS}

---

## 5. Self-verification checklist

- [ ] screen name/purpose match the `{SCREEN_ID}` entry in `screen-list.md`
- [ ] all 4 states idle·loading·success·error defined
- [ ] exit/cancel/back handling defined
- [ ] key rules of related policy WOs reflected
- [ ] no violation of `brand-voice.md` standards
- [ ] uses `{PREFIX_VAL}-A` registered vocabulary (including error codes)
- [ ] no violation of the canonical `decisions.md` DEC table (`Approval=✅`) (conflict with pending `⬜` is WARN — see CONTEXT/dec-schema)
- [ ] TBD items registered in `open-issues.md`

---

## 6. Prohibited

- editing related policy WO drafts directly
- editing the `decisions.md` DEC table directly (DEC registration via /write·/su·/sc etc.; approval only via /dec-approve — CONTEXT/dec-schema §5)
- editing other WO drafts

---

## 7. Post-completion steps

1. save `drafts/{WO_ID}.draft.md`
2. `/review drafts/{WO_ID}.draft.md`
3. `/lc {PRODUCT_NAME}` → `/sc {PRODUCT_NAME}`

---

## Workflow Connections

<!-- wikilinks:start -->
[WIKILINKS_PLACEHOLDER]
<!-- wikilinks:end -->
"""

INDEX_TEMPLATE = """\
# Work Orders index

**Project**: `{PRODUCT_NAME}`
**Generated at**: `{GENERATED_AT}`
**graph.json hash**: `{GRAPH_HASH}`
**Total Work Orders**: {TOTAL_WO} (policy: {TOTAL_POLICY} / screen: {TOTAL_SCREEN})
**Total levels**: {TOTAL_LEVELS}

---

## Execution-order notes

The following Work Orders have prerequisite edges and must start only after the preceding WO's draft is complete.

{PRECONDITION_NOTES}

---

## Policy document Work Orders (type: policy)

Work Orders within a level can run in parallel. Level N+1 starts after level N completes.

{POLICY_LEVEL_GROUPS}

---

## Screen design Work Orders (type: screen)

Work Orders within a level can run in parallel. Level N+1 starts after level N completes.

{SCREEN_LEVEL_GROUPS}

---

## Summary cards

{SUMMARY_CARDS}
"""


# ── markers ──────────────────────────────────────────────────────────────────

WIKILINKS_START = "<!-- wikilinks:start -->"
WIKILINKS_END = "<!-- wikilinks:end -->"
WO_MAP_FILENAME = ".fanout-wo-map.json"
WO_MAP_SCHEMA_VERSION = 1


# ── exceptions ────────────────────────────────────────────────────────────────

class FanoutError(Exception):
    pass


# ── utilities ─────────────────────────────────────────────────────────────────

def _load(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        raise FanoutError(f"failed to load graph.json: {exc}") from exc


def _hash_file(path: Path) -> str:
    if not path.exists():
        return "n/a"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:12]


def _assign_edge_ids(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign E-{NN} ids to edges that lack an id field."""
    result = []
    for idx, edge in enumerate(edges, start=1):
        e = dict(edge)
        if not e.get("id"):
            e["id"] = f"E-{idx:02d}"
        result.append(e)
    return result


# ── node iterators ────────────────────────────────────────────────────────────

def _iter_section_nodes(
    graph: dict[str, Any],
) -> Iterator[tuple[str, dict[str, Any], str, dict[str, Any]]]:
    """Iterate policy nodes that have a sections key."""
    nodes = graph["graph"]["nodes"]
    for node_name, node in nodes.items():
        if node.get("node_type") == "screen":
            continue
        sections = node.get("sections") or {}
        for section_id, section in sections.items():
            yield node_name, node, section_id, section


def _iter_screen_nodes(
    graph: dict[str, Any],
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Iterate nodes whose node_type is screen."""
    nodes = graph["graph"]["nodes"]
    for node_name, node in nodes.items():
        if node.get("node_type") == "screen":
            yield node_name, node


# ── Phase 5C — cluster-mode node iterator ─────────────────────────────────
def _iter_cluster_nodes(
    graph: dict[str, Any],
) -> Iterator[tuple[str, str, str, list[tuple[str, dict[str, Any]]]]]:
    """Iterate policy nodes grouped by (capability, cluster_id).

    Each cluster group carries the metadata assigned by cluster_identify.py
    (capability + cluster_id + cluster_name) and collects all policy nodes of
    the same cluster as members.

    Yields:
        (capability, cluster_id, cluster_name, [(node_name, node), ...])

    Nodes without a cluster_id are treated as standalone clusters under
    capability="Default" (fallback when cluster_identify.py hasn't run).
    """
    nodes = graph["graph"]["nodes"]
    by_cluster: dict[tuple[str, str], dict] = {}

    for node_name, node in nodes.items():
        if node.get("node_type") == "screen":
            continue
        capability = node.get("capability") or "Default"
        cluster_id = node.get("cluster_id")
        cluster_name = node.get("cluster_name") or node_name

        # no cluster_id assigned: each node becomes its own fallback cluster (DX-{node_name})
        if not cluster_id:
            cluster_id = f"DX-{node_name[:16]}"
            cluster_name = node_name

        key = (capability, cluster_id)
        if key not in by_cluster:
            by_cluster[key] = {
                "capability": capability,
                "cluster_id": cluster_id,
                "cluster_name": cluster_name,
                "members": [],
            }
        by_cluster[key]["members"].append((node_name, node))

    # deterministic order — sort by capability + cluster_id (publication-map.md §2)
    for key in sorted(by_cluster.keys()):
        ci = by_cluster[key]
        yield ci["capability"], ci["cluster_id"], ci["cluster_name"], ci["members"]


def _generate_cluster_draft_content(
    capability: str,
    cluster_id: str,
    cluster_name: str,
    members: list[tuple[str, dict[str, Any]]],
    *,
    product_name: str,
    graph_hash: str,
    now_iso: str,
    prefix_val: str,
) -> str:
    """Generate the cluster-draft.md style body for one cluster.

    Aggregates the member nodes' sections / fr_refs / domain_object /
    policy_axis / primary_screen into the frontmatter and the §1 Policy
    Decisions / §2 Screen Design bodies.
    """
    # metadata aggregation
    fr_refs: list[str] = []
    domain_objects: set[str] = set()
    policy_axes: set[str] = set()
    primary_screens: set[str] = set()
    inherits: set[str] = set()
    research_refs: set[str] = set()
    related_screens: set[str] = set()
    deliverable_targets: set[str] = set()
    section_summaries: list[tuple[str, str, str]] = []  # (node_name, section_id, title)

    for node_name, node in members:
        for fr_id in (node.get("fr_refs") or []):
            if fr_id not in fr_refs:
                fr_refs.append(fr_id)
        for d in (node.get("domain_object") or []):
            domain_objects.add(d)
        for p in (node.get("policy_axis") or []):
            policy_axes.add(p)
        if node.get("primary_screen"):
            primary_screens.add(node["primary_screen"])
        for t in (node.get("deliverable_targets") or ["D2", "D3"]):
            deliverable_targets.add(t)
        for ih in (node.get("inherits_from") or []):
            inherits.add(ih)
        for rr in (node.get("research_refs") or []):
            research_refs.add(rr)
        for rs in (node.get("related_screens") or []):
            related_screens.add(rs)
        # collect section summaries
        sections = node.get("sections") or {}
        for sid, sec in sections.items():
            section_summaries.append((node_name, sid, sec.get("title", sid)))

    # WO ID (cluster level, publication-map.md §7 naming)
    cap_prefix = "".join(
        c.upper() for c in capability if c.isalpha()
    )[:2] or "XX"
    wo_id = f"{prefix_val or 'PX'}-K-{cluster_id}"

    # common-shell determination (GAP1 — fix-plan-dossier-publish-split):
    # in split-deliverable publishing, render_transpose routes normal chapters
    # vs the D3 common-shell appendix by this flag. A cluster is a common shell
    # when cluster_id starts with COMMON or capability is Common (cross-cutting
    # shell). dossier-page mode ignores this field.
    is_common_shell = (
        cluster_id.upper().startswith("COMMON")
        or capability.strip().lower() == "common"
    )

    # frontmatter (consistent with cluster-draft.md)
    yaml_block = (
        f"---\n"
        f"title: \"Cluster {capability} / {cluster_id} — {cluster_name}\"\n"
        f"wo_id: {wo_id}\n"
        f"type: cluster_draft\n"
        f"layer: C\n"
        f"version: 1.0\n"
        f"status: empty\n"          # plan-A lifecycle entry point (empty→ai-draft→human-reviewed→frozen)
        f"last_updated: {now_iso[:10]}\n"
        f"\n"
        f"cluster:\n"
        f"  capability: \"{capability}\"\n"
        f"  cluster_id: \"{cluster_id}\"\n"
        f"  cluster_name: \"{cluster_name}\"\n"
        f"\n"
        f"fr_refs: {json.dumps(sorted(fr_refs), ensure_ascii=False)}\n"
        f"domain_objects: {json.dumps(sorted(domain_objects), ensure_ascii=False)}\n"
        f"policy_axes: {json.dumps(sorted(policy_axes), ensure_ascii=False)}\n"
        f"primary_screen: "
        f"{json.dumps(sorted(primary_screens)[0] if primary_screens else None, ensure_ascii=False)}\n"
        f"\n"
        f"inherits_from: {json.dumps(sorted(inherits), ensure_ascii=False)}\n"
        f"related_screens: {json.dumps(sorted(related_screens), ensure_ascii=False)}\n"
        f"research_refs: {json.dumps(sorted(research_refs), ensure_ascii=False)}\n"
        f"\n"
        f"deliverable_targets: {json.dumps(sorted(deliverable_targets), ensure_ascii=False)}\n"
        f"is_common_shell: {str(is_common_shell).lower()}\n"
        f"\n"
        f"color_state: null\n"
        f"graph_hash: \"{graph_hash[:12]}\"\n"
        f"members: {json.dumps([m[0] for m in members], ensure_ascii=False)}\n"
        f"---\n"
    )

    # §1 Policy Decisions — section_summaries as a table
    section_rows = "\n".join(
        f"| {sid} | {nname} | {title} |"
        for nname, sid, title in section_summaries
    ) or "| _(no sections)_ | | |"

    body = f"""
::: {{.panel section="§1 Policy Decisions (D2 → transpose to policy definition)"}}
## §1 Policy Decisions

> Policy decisions of this cluster. Assembled into the cluster chapter of the D2 policy definition at publish.

### §1-1 Policy scope / applicability

Conditions and boundaries where this cluster's ({cluster_id}) policies apply.

| Item | Content |
|---|---|
| **Applies to** | {{targets — e.g.: {', '.join(sorted(domain_objects)) or '(TBD)'}}} |
| **Exceptions** | {{exception cases}} |
| **Priority** | {{conflict-resolution principle}} |

### §1-2 Policy section list (from graph.json)

| Section ID | Source node | Title |
|---|---|---|
{section_rows}

### §1-3 Key rules

<!-- col-widths: 20%, 30%, 50% -->
| Rule ID | Condition | Policy |
|---|---|---|
| POL-{{N}} | {{condition}} | {{rule body — see graph sections summary}} |

### §1-4 Status / lifecycle

| Status | Definition | Entry Condition | Next Status |
|---|---|---|---|
| {{status name}} | {{definition}} | {{condition}} | {{transition}} |

### §1-5 Errors / exception handling

| Error code | Trigger condition | Handling |
|---|---|---|
| ERR-{{N}} | {{condition}} | {{handling policy}} |

:::

::: {{.panel section="§2 Screen Design (D3 → transpose to screen design spec)"}}
## §2 Screen Design

> Since Phase 5I this section owns D3 screen design spec output (separate screen WO track retired).

### §2-1 Main screens

| Screen ID | Screen Name | Entry Path | Notes |
|---|---|---|---|
{chr(10).join(f"| {s} | {{screen name}} | {{entry}} | |" for s in sorted(related_screens)) or "| {{SCR-NNN}} | {{screen name}} | {{}} | |"}

### §2-2 Screen composition / components

Key components, fields, and behavior of each screen:

```
{sorted(related_screens)[0] if related_screens else '{{SCR-NNN}}'}
├─ header: {{title / action buttons}}
├─ body: {{input form / list / detail}}
└─ footer: {{secondary actions}}
```

### §2-3 Policy ↔ UI mapping

| Screen area | Policy ref | Exposure |
|---|---|---|
| {{area}} | POL-{{N}} | {{message/field state/button enable}} |

:::

::: {{.panel section="§3 Data / Dependencies (internal, excluded from publish)"}}
## §3 Data / Dependencies

> publication_prefilter removes this section — not included in D2/D3.

### §3-1 Data objects

{chr(10).join(f"- `{d}`" for d in sorted(domain_objects)) or "- _(not specified in graph)_"}

### §3-2 Dependencies (from graph.json)

**inherits_from**:
{chr(10).join(f"- `{ih}`" for ih in sorted(inherits)) or "- _(none)_"}

### §3-3 Cluster member nodes

{chr(10).join(f"- `{name}`" for name, _ in members)}

:::

::: {{.panel section="§4 Open Questions / Upstream Feedback (internal, excluded from publish)" style="tbd"}}
## §4 Open Questions / Upstream Feedback

> /integrate classifies these as UPSTREAM_GAP BLOCK → /draft-req --upstream-feedback
> triggers a D1/D5 v++ revision.

### §4-1 Open Questions

| OQ ID | Question | Owner | Due |
|---|---|---|---|
| OQ-{{N}} | {{question}} | {{owner}} | {{date}} |

### §4-2 Upstream Feedback

#### REQ_MISSING — missing FR (D1 addition candidates)
- [ ] {{missing requirement}}

#### POLICY_CONFLICT — policy conflicts
- [ ] {{conflicting item}}

#### RESEARCH_GAP — insufficient competitor research
- [ ] {{item needing reinforcement}}

#### TERM_AMBIGUOUS — ambiguous terms
- [ ] {{term}}

:::
"""
    return yaml_block + body




# ── topological sort ──────────────────────────────────────────────────────────

def _topological_levels(
    all_keys: list[tuple[str, str]],
    edges: list[dict[str, Any]],
) -> dict[tuple[str, str], int]:
    """Compute levels from prerequisite edges. Raises on a cycle."""
    in_deg: dict[tuple[str, str], int] = {key: 0 for key in all_keys}
    graph_out: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)

    for edge in edges:
        if edge.get("type") != "prerequisite":
            continue
        src = (edge["source"], edge.get("source_section", ""))
        tgt = (edge["target"], edge.get("target_section", ""))
        if src not in in_deg or tgt not in in_deg:
            continue
        graph_out[src].append(tgt)
        in_deg[tgt] += 1

    queue: deque[tuple[str, str]] = deque(
        [k for k, d in in_deg.items() if d == 0]
    )
    level: dict[tuple[str, str], int] = {k: 0 for k in queue}
    visited = 0

    while queue:
        node = queue.popleft()
        visited += 1
        for nxt in graph_out[node]:
            in_deg[nxt] -= 1
            level[nxt] = max(level.get(nxt, 0), level[node] + 1)
            if in_deg[nxt] == 0:
                queue.append(nxt)

    if visited != len(all_keys):
        raise FanoutError("prerequisite edges contain a cycle.")
    return level


# ── rendering helpers ─────────────────────────────────────────────────────────

def _render_edge_row(edge: dict[str, Any]) -> str:
    return (
        f"| `{edge['id']}` | {edge['type']} | "
        f"`{edge['source']}.§{edge.get('source_section', '')}` | "
        f"`{edge['target']}.§{edge.get('target_section', '')}` | "
        f"{edge.get('description', '')} |"
    )


def _edges_table(rows: list[str]) -> str:
    if not rows:
        return "_(none)_"
    header = "| Edge ID | Type | source | target | Description |\n|---|---|---|---|---|"
    return header + "\n" + "\n".join(rows)


def _level_deps_text(level: int) -> str:
    if level == 0:
        return "_none (top level, can start immediately)_"
    return f"_start after all level-{level - 1} WO drafts are complete_"


def _level_group_text(groups: dict[int, list[str]]) -> str:
    if not groups:
        return "_(none)_"
    return "\n".join(
        f"**Level {lvl}** ({len(wos)}): " + ", ".join(wos)
        for lvl, wos in sorted(groups.items())
    )


def _policy_summary_card(
    wo_id: str,
    node_name: str,
    section_id: str,
    section_title: str,
    summary: str,
    edges: list[dict[str, Any]],
) -> str:
    edge_lines = [
        f"  - [{e['type']}] {e['id']}: "
        f"{e['source']}.§{e.get('source_section', '')} → "
        f"{e['target']}.§{e.get('target_section', '')}"
        for e in edges[:3]
    ]
    edge_block = "\n".join(edge_lines) if edge_lines else "  - _(no edges)_"
    return (
        f"### {wo_id} `policy` — {node_name}.§{section_id} · {section_title}\n"
        f"- **Summary**: {summary}\n"
        f"- **Key edges (max 3)**:\n{edge_block}\n"
        f"- **Output**: `drafts/{wo_id}.draft.md`\n"
    )


def _screen_summary_card(
    wo_id: str,
    screen_id: str,
    screen_name: str,
    purpose: str,
    policy_wo_text: str,
    edges: list[dict[str, Any]],
) -> str:
    edge_lines = [
        f"  - [{e['type']}] {e['id']}: {e['source']} → {e['target']}"
        for e in edges[:3]
    ]
    edge_block = "\n".join(edge_lines) if edge_lines else "  - _(no edges)_"
    return (
        f"### {wo_id} `screen` — {screen_id} · {screen_name}\n"
        f"- **Purpose**: {purpose}\n"
        f"- **Related policy WO**: {policy_wo_text}\n"
        f"- **Key edges (max 3)**:\n{edge_block}\n"
        f"- **Output**: `drafts/{wo_id}.draft.md`\n"
    )


# ── main logic ────────────────────────────────────────────────────────────────

def _init_draft_frontmatter(wo_id: str, wo_type: str, layer: str, level: int, graph_hash: str) -> str:
    """Plan A: generate the standard frontmatter for a new draft file (status: empty)."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return f"""---
wo_id: {wo_id}
status: empty
type: {wo_type}
layer: {layer}
referenced_policies: []
referenced_master: []
referenced_screens: []
related_decisions: []
delta_required: true
last_updated: "{now}"
created_by: fanout_dag.py
review_status: ai-draft
reviewed_by: ""
reviewed_at: ""
level: {level}
graph_hash: "{graph_hash}"
---

"""


def _check_existing_draft_status(draft_path) -> str:
    """Plan A idempotency: read and return the existing draft's status. 'absent' if missing."""
    if not draft_path.exists():
        return "absent"
    try:
        text = draft_path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return "no-frontmatter"
        end = text.find("---", 3)
        if end < 0:
            return "no-frontmatter"
        fm = text[3:end]
        for line in fm.splitlines():
            line = line.strip()
            if line.startswith("status:"):
                return line.split(":", 1)[1].strip()
        return "no-status"
    except Exception:
        return "read-error"


def _inject_status_field(text: str, status: str) -> str:
    """Surgically insert a single status line if the frontmatter lacks one (body and other fields preserved).

    A safe migration that avoids re-rendering a cluster draft's nested YAML
    (cluster:) and JSON arrays. Returns the text unchanged if there is no
    frontmatter (handled separately upstream)."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end < 0:
        return text
    head, rest = text[:end], text[end:]
    if re.search(r"(?m)^\s*status\s*:", head):
        return text  # already present — preserve
    # insert after the type line (or after the first frontmatter line if absent)
    lines = head.splitlines()
    insert_at = next((i + 1 for i, ln in enumerate(lines)
                      if ln.strip().startswith("type:")), 1)
    lines.insert(insert_at, f"status: {status}")
    return "\n".join(lines) + rest


# ── stable numbering (persistent WO map) ──────────────────────────────────────

def _canonical_key(node_type: str, node_name: str, section_id: str) -> str:
    """Stable identification key for a node. Same node → same key regardless of graph.json iteration order.

    policy: policy::{node_name}::{section_id}
    screen: screen::{node_name}
    """
    if node_type == "screen":
        return f"screen::{node_name}"
    return f"policy::{node_name}::{section_id}"


def _load_wo_map(output_dir: Path) -> dict[str, Any]:
    """Load the persistent WO map. Returns an empty map if absent or corrupt."""
    path = output_dir / WO_MAP_FILENAME
    if not path.exists():
        return {"version": WO_MAP_SCHEMA_VERSION, "next_counter": 1, "map": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "map" not in data:
            raise ValueError("invalid schema")
        data.setdefault("version", WO_MAP_SCHEMA_VERSION)
        data.setdefault("next_counter", 1)
        data.setdefault("map", {})
        return data
    except Exception as exc:
        print(
            f"[fanout] WARN: failed to load {WO_MAP_FILENAME} ({exc}). starting with a fresh map.",
            file=sys.stderr,
        )
        return {"version": WO_MAP_SCHEMA_VERSION, "next_counter": 1, "map": {}}


def _save_wo_map(output_dir: Path, wo_map: dict[str, Any]) -> None:
    """Save the persistent WO map — atomic (MEDIUM #15: tmp + os.replace)."""
    import os
    path = output_dir / WO_MAP_FILENAME
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(wo_map, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(str(tmp_path), str(path))


def _assign_wo_ids_stable(
    policy_keys: list[tuple[str, str]],
    screen_keys: list[tuple[str, str]],
    wo_map: dict[str, Any],
    now_iso: str,
) -> dict[tuple[str, str], str]:
    """Assign WO IDs stably using the persistent map.

    - node already in the map → reuse its existing wo_id
    - new node → assign a new wo_id starting from next_counter
    - vanished node → tombstone with removed:true (wo_id never reused)
    """
    canonical_to_key: dict[str, tuple[str, str]] = {}
    for key in policy_keys:
        canonical_to_key[_canonical_key("policy", key[0], key[1])] = key
    for key in screen_keys:
        canonical_to_key[_canonical_key("screen", key[0], key[1])] = key

    current_canonical = set(canonical_to_key.keys())
    prior_map: dict[str, dict[str, Any]] = dict(wo_map.get("map", {}))

    # collect all numbers in use (tombstones included) — prevents reuse
    used_numbers: set[int] = set()
    for entry in prior_map.values():
        wo_id = entry.get("wo_id", "")
        if wo_id.startswith("WO-"):
            try:
                used_numbers.add(int(wo_id[3:]))
            except ValueError:
                pass

    key_to_wo: dict[tuple[str, str], str] = {}

    # step 1: current nodes already mapped → reuse existing wo_id + clear tombstone
    for canonical, key in canonical_to_key.items():
        if canonical in prior_map:
            entry = prior_map[canonical]
            key_to_wo[key] = entry["wo_id"]
            entry["removed"] = False
            entry["last_seen_at"] = now_iso

    # step 2: new nodes → assign the next available number
    next_counter = max(wo_map.get("next_counter", 1), 1)
    # deterministic order: policy first, then screen, input order within each group
    new_order: list[tuple[str, tuple[str, str], str]] = []
    for key in policy_keys:
        canonical = _canonical_key("policy", key[0], key[1])
        if canonical not in prior_map:
            new_order.append((canonical, key, "policy"))
    for key in screen_keys:
        canonical = _canonical_key("screen", key[0], key[1])
        if canonical not in prior_map:
            new_order.append((canonical, key, "screen"))

    for canonical, key, node_type in new_order:
        while next_counter in used_numbers:
            next_counter += 1
        wo_id = f"WO-{next_counter:02d}"
        used_numbers.add(next_counter)
        key_to_wo[key] = wo_id
        prior_map[canonical] = {
            "wo_id": wo_id,
            "type": node_type,
            "first_seen_at": now_iso,
            "last_seen_at": now_iso,
            "removed": False,
        }
        next_counter += 1

    # step 3: vanished nodes → tombstone
    for canonical in list(prior_map.keys()):
        if canonical not in current_canonical:
            entry = prior_map[canonical]
            if not entry.get("removed"):
                entry["removed"] = True
                entry["removed_at"] = now_iso

    wo_map["map"] = prior_map
    wo_map["next_counter"] = next_counter
    wo_map["version"] = WO_MAP_SCHEMA_VERSION

    return key_to_wo


# ── delta_required handling ──────────────────────────────────────────────────

def _node_no_delta(node: dict[str, Any]) -> bool:
    """Whether the policy node fully applies the common policy (excluded from WO generation)."""
    return node.get("delta_required") is False


def _write_no_delta_list(
    output_dir: Path,
    no_delta_sections: list[tuple[str, dict, str, dict]],
    prefix: str,
    generated_at: str,
) -> None:
    """Record delta_required: false nodes in work-orders/no-delta-list.md."""
    path = output_dir / "no-delta-list.md"
    lines = [
        "# No-Delta node list",
        "",
        f"generated: {generated_at}",
        "",
        f"The following nodes fully apply the `{prefix}-B` common policy; no separate WO is generated.",
        "On Confluence upload they are recorded automatically as \"[{doc_id} default policy fully applied]\".",
        "",
    ]
    if not no_delta_sections:
        lines.append("_(no no-delta nodes — every policy node is a Delta authoring target)_")
    else:
        lines.extend([
            "| Node | Section ID | Section Title | inherits_from |",
            "|---|---|---|---|",
        ])
        for node_name, node, section_id, section in no_delta_sections:
            inherits = ", ".join(node.get("inherits_from", [])) or "_(unspecified)_"
            title = section.get("title", section_id)
            lines.append(
                f"| `{node_name}` | `{section_id}` | {title} | {inherits} |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── body wikilinks dangling audit ─────────────────────────────────────────────

WIKILINK_WO_PATTERN = re.compile(r"\[\[(WO-\d+)\]\]")


DRAFT_FILENAME_PATTERN = re.compile(r"^(WO-\d+)\.draft\.md$")


def _scan_wikilinks_dangling(
    drafts_dir: Path,
    wo_map: dict[str, Any],
) -> list[dict[str, str]]:
    """Report [[WO-XX]] links in draft bodies and the draft files themselves against the active map.

    Body-reference classification:
    - active: exists in the active WO map (normal, excluded from the report)
    - tombstoned: in the map but removed:true (references a deleted node)
    - dangling: not in the map (LLM-invented or leftover old numbering)
    - *-orphan-file: either case above where drafts/WO-XX.draft.md actually exists

    File classification (draft="<filename>", ref="-"):
    - orphan-file-tombstoned: file exists but the node was deleted (tombstoned)
    - orphan-file-unknown: file exists but is not registered in the map
    """
    findings: list[dict[str, str]] = []
    if not drafts_dir.is_dir():
        return findings

    active_wo_ids = {
        e["wo_id"]
        for e in wo_map.get("map", {}).values()
        if not e.get("removed") and "wo_id" in e
    }
    tombstoned_wo_ids = {
        e["wo_id"]
        for e in wo_map.get("map", {}).values()
        if e.get("removed") and "wo_id" in e
    }

    for draft_path in sorted(drafts_dir.glob("*.draft.md")):
        # scan body references
        try:
            text = draft_path.read_text(encoding="utf-8")
        except Exception:
            continue
        refs = sorted(set(WIKILINK_WO_PATTERN.findall(text)))
        for wo_id in refs:
            if wo_id in active_wo_ids:
                continue
            target_file = drafts_dir / f"{wo_id}.draft.md"
            if wo_id in tombstoned_wo_ids:
                kind = "tombstoned-orphan-file" if target_file.exists() else "tombstoned"
            else:
                kind = "dangling-orphan-file" if target_file.exists() else "dangling"
            findings.append({
                "draft": draft_path.name,
                "ref": wo_id,
                "kind": kind,
            })
        # check whether the file itself is missing from the active map (orphan file)
        m = DRAFT_FILENAME_PATTERN.match(draft_path.name)
        if m:
            file_wo_id = m.group(1)
            if file_wo_id not in active_wo_ids:
                kind = "orphan-file-tombstoned" if file_wo_id in tombstoned_wo_ids else "orphan-file-unknown"
                findings.append({
                    "draft": draft_path.name,
                    "ref": "-",
                    "kind": kind,
                })
    return findings


def _write_wikilinks_audit(
    output_dir: Path,
    findings: list[dict[str, str]],
    generated_at: str,
) -> None:
    """Write wikilinks-audit.md."""
    path = output_dir / "wikilinks-audit.md"
    if not findings:
        path.write_text(
            "# Wikilinks audit report\n\n"
            f"generated: {generated_at}\n\n"
            "✅ every `[[WO-XX]]` link matches the active WO map.\n",
            encoding="utf-8",
        )
        return

    action_map = {
        "tombstoned": "references a deleted node — recommend removing from the body",
        "tombstoned-orphan-file": "tombstoned + orphan draft file remains — remove from body + clean up orphan file",
        "dangling": "references a WO absent from the active map — recommend removing from the body",
        "dangling-orphan-file": "not in the map but the file exists — remove from body + review file cleanup",
        "orphan-file-tombstoned": "the draft file itself is orphaned — node deleted. review archiving or manual deletion",
        "orphan-file-unknown": "draft file not registered in the map — manual file or old fanout leftover. review cleanup",
    }
    lines = [
        "# Wikilinks audit report",
        "",
        f"generated: {generated_at}",
        "",
        f"⚠️ {len(findings)} dangling/tombstoned references found:",
        "",
        "| draft | Referenced WO | Kind | Recommended action |",
        "|---|---|---|---|",
    ]
    for f in findings:
        action = action_map.get(f["kind"], "needs review")
        lines.append(f"| `{f['draft']}` | `{f['ref']}` | `{f['kind']}` | {action} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── body wikilinks resync (marker-based) ──────────────────────────────────────

def _replace_wikilinks_block(text: str, new_inner: str) -> str:
    """Replace the content between the body's wikilinks markers.

    Without markers (legacy draft), only the *body* of the
    `## Workflow Connections` section is replaced; content after the next H2
    section (if any) is preserved. If the section itself is absent, append at
    the end of the file.
    """
    s_idx = text.find(WIKILINKS_START)
    e_idx = text.find(WIKILINKS_END)
    if s_idx >= 0 and e_idx > s_idx:
        before = text[: s_idx + len(WIKILINKS_START)]
        after = text[e_idx:]
        return f"{before}\n{new_inner}\n{after}"

    # CRITICAL #3: legacy draft fallback — replace only up to the next H2, preserve the rest
    workflow_idx = text.rfind("## Workflow Connections")
    new_block = (
        f"## Workflow Connections\n\n{WIKILINKS_START}\n{new_inner}\n{WIKILINKS_END}\n"
    )
    if workflow_idx >= 0:
        # the existing section spans up to the next H2 (or EOF)
        next_h2_match = re.search(r"^##\s+(?!Workflow\s+Connections)", text[workflow_idx + 1:], re.MULTILINE)
        section_end = workflow_idx + 1 + next_h2_match.start() if next_h2_match else len(text)
        before = text[:workflow_idx].rstrip()
        trailing = text[section_end:]
        # before + new_block + trailing (preserves all PM-authored sections after)
        result = (before + "\n\n" if before else "") + new_block
        if trailing.strip():
            result = result.rstrip() + "\n\n" + trailing.lstrip()
        else:
            result = result + trailing
        return result
    return text.rstrip() + "\n\n" + new_block


def _detect_cluster_signals(
    graph_path: Path, graph: dict[str, Any], output_dir: Path
) -> list[str]:
    """Collect signals indicating this project is a cluster(dossier) model (Track A).

    If any is detected, legacy section-WO fanout must fail closed
    (P0 — fanout fail-closed guard, fix-plan-track-routing). The return value is
    a list of human-readable signal descriptions; empty means legacy entry is
    considered safe.
    """
    signals: list[str] = []
    graph_dir = graph_path.parent
    drafts_dir = output_dir.parent / "drafts"

    # ① persistent track marker (P1 — written by cluster_identify / plan-audit)
    mode_path = graph_dir / "project-mode.json"
    if mode_path.exists():
        try:
            mode = json.loads(mode_path.read_text(encoding="utf-8"))
        except Exception:
            mode = {}
        if str(mode.get("track", "")).upper() == "A" or mode.get("model") == "dossier":
            signals.append(
                f"project-mode.json (track={mode.get('track')}, model={mode.get('model')})"
            )

    # ② cluster_identify.py outputs (cluster topology already built)
    if (graph_dir / "cluster_map.json").exists():
        signals.append("graph/cluster_map.json")
    if (graph_dir / "graph.clustered.json").exists():
        signals.append("graph/graph.clustered.json")

    # ③ capability/cluster_id metadata present on graph nodes
    nodes = graph.get("graph", {}).get("nodes", {})
    if any(n.get("capability") or n.get("cluster_id") for n in nodes.values()):
        signals.append("capability/cluster_id assigned on graph nodes")

    # ④ dossier(cluster) drafts already written — the key signal of the incident
    if drafts_dir.exists():
        dossiers = sorted(drafts_dir.glob("cluster_*.draft.md"))
        if dossiers:
            signals.append(
                f"{len(dossiers)} dossier drafts in drafts/ (cluster_*.draft.md)"
            )

    return signals


VALID_PUBLICATION_MODES = ("dossier-page", "split-deliverable")


def _apply_publication_mode(graph_dir: Path, publication_mode: str | None) -> None:
    """Read-modify-write publication_mode into graph/project-mode.json.

    fix-plan-dossier-publish-split — pins the publication mode into the
    persistent marker right after cluster fanout. Other keys
    (track/decided_by/section_wo_retired …) are preserved. None means no change
    (existing value / default dossier-page kept) — regression guard for existing
    projects like dbaas.
    """
    if not publication_mode:
        return
    if publication_mode not in VALID_PUBLICATION_MODES:
        raise FanoutError(
            f"invalid publication_mode: {publication_mode!r}. "
            f"allowed: {list(VALID_PUBLICATION_MODES)}"
        )
    path = graph_dir / "project-mode.json"
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["publication_mode"] = publication_mode
    data.setdefault("track", "A")
    data.setdefault("model", "dossier")
    data["updated_at"] = datetime.utcnow().isoformat() + "Z"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def fanout(
    graph_path: Path,
    output_dir: Path,
    product_name: str,
    prefix: str = "",
    *,
    cluster_mode: bool = False,
    force_legacy: bool = False,
    publication_mode: str | None = None,
) -> None:
    """Work Order generation entry point.

    cluster_mode=True (Phase 5C — Track A Full Product):
        Generates cluster-level WOs for policy nodes using the graph.json
        capability/cluster_id metadata. Each cluster = 1 draft
        (templates/standard/cluster-draft.md format). The screen WO track is
        retired (Phase 5I) — cluster §2 owns D3 output.

    cluster_mode=False (default — Track B/C/Legacy):
        Legacy behavior — section-level policy WOs + screen-level screen WOs.
        However, if cluster(dossier) model signals are detected, it fails closed
        (bypass only via force_legacy=True — fix-plan-track-routing P0).
    """
    graph = _load(graph_path)
    graph_hash = _hash_file(graph_path)
    decisions_hash = _hash_file(graph_path.parent.parent / "decisions.md")

    # Phase 5C — cluster mode branch (Track A)
    if cluster_mode:
        return _fanout_cluster_mode(
            graph, output_dir, product_name, prefix, graph_hash,
            publication_mode=publication_mode,
        )

    # P0 — fail-closed guard: abort if cluster(dossier) model signals exist but
    # legacy entry is attempted. Prevents the recurrence of the incident where
    # legacy fanout run on a Track A project mass-produced empty WO shells and
    # orphaned the existing dossiers (fix-plan-track-routing).
    cluster_signals = _detect_cluster_signals(graph_path, graph, output_dir)
    if cluster_signals and not force_legacy:
        signal_lines = "\n".join(f"      - {s}" for s in cluster_signals)
        raise FanoutError(
            "this project is identified as a cluster(dossier) model (Track A). "
            "aborting legacy section-WO generation.\n"
            f"    detected signals:\n{signal_lines}\n"
            "    → if you intend cluster WO generation: add --cluster-mode.\n"
            "    → if you really intend to force legacy: pass --force-legacy "
            "(section/screen WO shells will be created next to existing dossiers)."
        )

    raw_edges = graph["graph"].get("edges", [])
    edges = _assign_edge_ids(raw_edges)

    # ── node collection ───────────────────────────────────────────────────────
    policy_sections_all = list(_iter_section_nodes(graph))
    screen_nodes = list(_iter_screen_nodes(graph))

    # policy nodes with delta_required: false are excluded from WO generation
    # and recorded in no-delta-list.md (screen nodes ignore delta_required).
    policy_sections = [t for t in policy_sections_all if not _node_no_delta(t[1])]
    no_delta_sections = [t for t in policy_sections_all if _node_no_delta(t[1])]

    if not policy_sections and not screen_nodes:
        raise FanoutError("graph.json has no nodes to process.")

    # ── unified key list ──────────────────────────────────────────────────────
    # policy key: (node_name, section_id)
    # screen key: (node_name, "")
    policy_keys = [(n, sid) for (n, _, sid, _) in policy_sections]
    screen_keys = [(n, "") for (n, _) in screen_nodes]
    all_keys = policy_keys + screen_keys

    # ── topological sort ──────────────────────────────────────────────────────
    levels = _topological_levels(all_keys, edges)

    # ── WO ID pre-assignment (persistent map — same node gets the same WO ID on re-run) ──
    output_dir.mkdir(parents=True, exist_ok=True)
    wo_map = _load_wo_map(output_dir)
    now_iso = datetime.utcnow().isoformat() + "Z"
    key_to_wo = _assign_wo_ids_stable(policy_keys, screen_keys, wo_map, now_iso)

    # ── edge index construction ───────────────────────────────────────────────
    outgoing: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    incoming: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for e in edges:
        src = (e["source"], e.get("source_section", ""))
        tgt = (e["target"], e.get("target_section", ""))
        outgoing[src].append(e)
        incoming[tgt].append(e)
        if e.get("type") == "bidirectional-ref":
            outgoing[tgt].append(e)
            incoming[src].append(e)

    # implements-edge based cross-reference maps
    # screen → related policy WO ID list
    screen_to_policy_wo: dict[str, list[str]] = defaultdict(list)
    # policy section key → related screen WO ID list
    policy_to_screen_wo: dict[tuple[str, str], list[str]] = defaultdict(list)
    for e in edges:
        if e.get("type") != "implements":
            continue
        s_key = (e["source"], "")
        p_key = (e["target"], e.get("target_section", ""))
        # register the cross-ref only when both sides are in the active WO map
        # (guards no-delta nodes and dangling edges right after graph changes)
        if s_key in key_to_wo and p_key in key_to_wo:
            screen_to_policy_wo[e["source"]].append(key_to_wo[p_key])
            policy_to_screen_wo[p_key].append(key_to_wo[s_key])

    # ── prepare output directory (output_dir already created during numbering) ─
    (output_dir.parent / "drafts").mkdir(parents=True, exist_ok=True)

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    prefix_val = prefix or "PREFIX"
    summary_cards: list[str] = []
    precondition_notes: list[str] = []
    policy_level_groups: dict[int, list[str]] = defaultdict(list)
    screen_level_groups: dict[int, list[str]] = defaultdict(list)
    # improvement G — machine-readable index.json records (CONTEXT_OPTIMIZATION.md)
    wo_records: list[dict[str, Any]] = []

    # ── policy WO file generation ─────────────────────────────────────────────
    for node_name, node, section_id, section in policy_sections:
        key = (node_name, section_id)
        wo_id = key_to_wo[key]
        lvl = levels[key]
        policy_level_groups[lvl].append(f"`{wo_id}` ({node_name}.§{section_id})")

        out_rows = [_render_edge_row(e) for e in outgoing[key]]
        in_rows = [_render_edge_row(e) for e in incoming[key]]

        related_screens = policy_to_screen_wo.get(key, [])
        related_screen_text = (
            "\n".join(f"- `{wid}`" for wid in related_screens)
            if related_screens
            else "_(none)_"
        )

        content = DEFAULT_POLICY_TEMPLATE.format(
            WO_ID=wo_id,
            SECTION_TITLE=section.get("title", section_id),
            PRODUCT_NAME=product_name,
            GENERATED_AT=now,
            GRAPH_HASH=graph_hash,
            LEVEL=lvl,
            NODE_NAME=node_name,
            NODE_ROLE=node.get("role", "unknown"),
            SECTION_ID=section_id,
            DECISIONS_HASH=decisions_hash,
            OUTGOING_EDGES=_edges_table(out_rows),
            INCOMING_EDGES=_edges_table(in_rows),
            RELATED_SCREEN_WOS=related_screen_text,
            SECTION_SUMMARY=section.get("summary", "_(no summary in graph.json)_"),
            LEVEL_DEPS=_level_deps_text(lvl),
            PREFIX_VAL=prefix_val,
        )
        # Wikilinks: collect related WO IDs then replace placeholder
        linked_wo_ids: set[str] = set(related_screens)
        for e in incoming[key]:
            if e.get("type") == "prerequisite":
                pred_key = (e["source"], e.get("source_section", ""))
                if pred_key in key_to_wo:
                    linked_wo_ids.add(key_to_wo[pred_key])
        for e in outgoing[key]:
            if e.get("type") == "prerequisite":
                tgt_key = (e["target"], e.get("target_section", ""))
                if tgt_key in key_to_wo:
                    linked_wo_ids.add(key_to_wo[tgt_key])
        wikilinks_lines = [f"- linked WO: [[{wid}]]" for wid in sorted(linked_wo_ids)]
        wikilinks_str = "\n".join(wikilinks_lines) or "_(no linked WOs)_"
        content = content.replace("[WIKILINKS_PLACEHOLDER]", wikilinks_str)
        # Plan A: generate drafts/{WO_ID}.draft.md directly, idempotency guaranteed
        draft_path = output_dir.parent / "drafts" / f"{wo_id}.draft.md"
        existing_status = _check_existing_draft_status(draft_path)
        if existing_status in ("ai-draft", "human-reviewed", "frozen"):
            # preserve body + deterministically resync only the wikilinks marker block (prevents dangling)
            existing_text = draft_path.read_text(encoding="utf-8")
            new_text = _replace_wikilinks_block(existing_text, wikilinks_str)
            if new_text != existing_text:
                draft_path.write_text(new_text, encoding="utf-8")
        else:
            # new or empty/no-frontmatter: full overwrite
            frontmatter = _init_draft_frontmatter(wo_id, "policy", "C", lvl, graph_hash[:12])
            draft_path.write_text(frontmatter + content, encoding="utf-8")
        # work-orders/{WO_ID}.md generation removed (Plan A)

        summary_cards.append(_policy_summary_card(
            wo_id, node_name, section_id,
            section.get("title", section_id),
            section.get("summary", "-"),
            outgoing[key] + incoming[key],
        ))

        wo_records.append({
            "wo_id": wo_id,
            "type": "policy",
            "level": lvl,
            "node_name": node_name,
            "section_id": section_id,
            "section_title": section.get("title", section_id),
            "node_role": node.get("role", "unknown"),
            "delta_required": node.get("delta_required"),
            "inherits_from": node.get("inherits_from", []),
            "includes": node.get("includes", []),
            "related_screen_wos": list(related_screens),
            "linked_wos": sorted(linked_wo_ids),
            "draft_path": f"drafts/{wo_id}.draft.md",
        })

        for e in outgoing[key]:
            if e.get("type") == "prerequisite":
                tgt_key = (e["target"], e.get("target_section", ""))
                tgt_wo = key_to_wo.get(tgt_key, "?")
                precondition_notes.append(
                    f"- `{wo_id}` → waits for `{tgt_wo}` "
                    f"({e['target']}.§{e.get('target_section', '')})"
                )

    # ── screen WO file generation ─────────────────────────────────────────────
    for node_name, node in screen_nodes:
        key = (node_name, "")
        wo_id = key_to_wo[key]
        lvl = levels[key]
        screen_level_groups[lvl].append(f"`{wo_id}` ({node_name})")

        impl_rows = [
            _render_edge_row(e)
            for e in edges
            if e.get("type") == "implements" and e["source"] == node_name
        ]
        screen_edge_rows = [
            _render_edge_row(e)
            for e in outgoing[key] + incoming[key]
            if e.get("type") != "implements"
        ]

        policy_wo_ids = screen_to_policy_wo.get(node_name, [])
        policy_wo_text = (
            ", ".join(f"`{p}`" for p in policy_wo_ids)
            if policy_wo_ids
            else "`TBD`"
        )

        content = SCREEN_TEMPLATE.format(
            WO_ID=wo_id,
            SCREEN_ID=node_name,
            SCREEN_NAME=node.get("screen_name", node_name),
            PURPOSE=node.get("purpose", "_(no purpose in graph.json)_"),
            REQ_ID=node.get("req_id", "TBD"),
            POLICY_WO_ID=policy_wo_text,
            PRODUCT_NAME=product_name,
            GENERATED_AT=now,
            GRAPH_HASH=graph_hash,
            LEVEL=lvl,
            DECISIONS_HASH=decisions_hash,
            IMPLEMENTS_EDGES=_edges_table(impl_rows),
            SCREEN_EDGES=_edges_table(screen_edge_rows),
            LEVEL_DEPS=_level_deps_text(lvl),
            PREFIX_VAL=prefix_val,
        )
        # Wikilinks: collect related WO IDs then replace placeholder
        linked_screen_wo_ids: set[str] = set(policy_wo_ids)
        for e in outgoing[key] + incoming[key]:
            if e.get("type") == "implements":
                continue
            for candidate_key in [(e["source"], ""), (e["target"], "")]:
                if candidate_key != key and candidate_key in key_to_wo:
                    linked_screen_wo_ids.add(key_to_wo[candidate_key])
        wikilinks_screen_lines = [f"- linked WO: [[{wid}]]" for wid in sorted(linked_screen_wo_ids)]
        wikilinks_screen_str = "\n".join(wikilinks_screen_lines) or "_(no linked WOs)_"
        content = content.replace("[WIKILINKS_PLACEHOLDER]", wikilinks_screen_str)
        # Plan A: generate drafts/{WO_ID}.draft.md directly, idempotency guaranteed
        draft_path = output_dir.parent / "drafts" / f"{wo_id}.draft.md"
        existing_status = _check_existing_draft_status(draft_path)
        if existing_status in ("ai-draft", "human-reviewed", "frozen"):
            # preserve body + deterministically resync only the wikilinks marker block (prevents dangling)
            existing_text = draft_path.read_text(encoding="utf-8")
            new_text = _replace_wikilinks_block(existing_text, wikilinks_screen_str)
            if new_text != existing_text:
                draft_path.write_text(new_text, encoding="utf-8")
        else:
            frontmatter = _init_draft_frontmatter(wo_id, "screen", "C", lvl, graph_hash[:12])
            draft_path.write_text(frontmatter + content, encoding="utf-8")
        # work-orders/{WO_ID}.md generation removed (Plan A)

        summary_cards.append(_screen_summary_card(
            wo_id, node_name,
            node.get("screen_name", node_name),
            node.get("purpose", "-"),
            policy_wo_text,
            outgoing[key] + incoming[key],
        ))

        wo_records.append({
            "wo_id": wo_id,
            "type": "screen",
            "level": lvl,
            "node_name": node_name,
            "screen_name": node.get("screen_name", node_name),
            "purpose": node.get("purpose"),
            "req_id": node.get("req_id"),
            "related_policy_wos": list(policy_wo_ids),
            "implements": [e["target"] for e in edges
                           if e.get("type") == "implements" and e["source"] == node_name],
            "linked_wos": sorted(linked_screen_wo_ids),
            "draft_path": f"drafts/{wo_id}.draft.md",
        })

        for e in outgoing[key]:
            if e.get("type") == "prerequisite":
                tgt_key = (e["target"], e.get("target_section", ""))
                tgt_wo = key_to_wo.get(tgt_key, "?")
                precondition_notes.append(
                    f"- `{wo_id}` → waits for `{tgt_wo}` ({e['target']})"
                )

    # ── index.md generation ───────────────────────────────────────────────────
    all_levels = set(policy_level_groups) | set(screen_level_groups)
    pre_text = (
        "\n".join(precondition_notes)
        if precondition_notes
        else "_(no prerequisite edges — all WOs can start simultaneously)_"
    )

    index_text = INDEX_TEMPLATE.format(
        PRODUCT_NAME=product_name,
        GENERATED_AT=now,
        GRAPH_HASH=graph_hash,
        TOTAL_WO=len(policy_sections) + len(screen_nodes),
        TOTAL_POLICY=len(policy_sections),
        TOTAL_SCREEN=len(screen_nodes),
        TOTAL_LEVELS=len(all_levels),
        PRECONDITION_NOTES=pre_text,
        POLICY_LEVEL_GROUPS=_level_group_text(policy_level_groups),
        SCREEN_LEVEL_GROUPS=_level_group_text(screen_level_groups),
        SUMMARY_CARDS="\n".join(summary_cards),
    )
    (output_dir / "index.md").write_text(index_text, encoding="utf-8")

    # improvement G — emit machine-readable index.json alongside (CONTEXT_OPTIMIZATION.md)
    index_payload = {
        "_meta": {
            "product": product_name,
            "generated_at": now,
            "graph_hash": graph_hash,
            "decisions_hash": decisions_hash,
            "totals": {
                "wo": len(policy_sections) + len(screen_nodes),
                "policy": len(policy_sections),
                "screen": len(screen_nodes),
                "levels": len(set(policy_level_groups) | set(screen_level_groups)),
            },
        },
        "wo": wo_records,
    }
    (output_dir / "index.json").write_text(
        json.dumps(index_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # improvement C — write split graph.json files (CONTEXT_OPTIMIZATION.md)
    _write_split_graph(graph_path.parent, graph)

    # save the persistent WO map (guarantees same node → same WO ID on re-run)
    _save_wo_map(output_dir, wo_map)

    # no-delta node list (SKILL.md step 2 spec)
    _write_no_delta_list(output_dir, no_delta_sections, prefix_val, now)

    # body wikilinks dangling audit (detects LLM-invented refs and old-numbering leftovers)
    audit = _scan_wikilinks_dangling(output_dir.parent / "drafts", wo_map)
    _write_wikilinks_audit(output_dir, audit, now)

    tombstoned = sum(1 for e in wo_map.get("map", {}).values() if e.get("removed"))
    print(
        f"[fanout] done — "
        f"policy WO: {len(policy_sections)} / "
        f"screen WO: {len(screen_nodes)} / "
        f"no-delta: {len(no_delta_sections)} / "
        f"tombstone: {tombstoned} / "
        f"wikilinks-audit: {len(audit)} → {output_dir}"
    )


def _write_split_graph(graph_dir: Path, graph_doc: dict) -> None:
    """Split graph.json into 4 files by node_type and edges."""
    g = graph_doc.get("graph", {})
    all_nodes: dict = g.get("nodes", {})
    all_edges: list = g.get("edges", [])
    metadata: dict = g.get("metadata", {})

    policy_nodes = {k: v for k, v in all_nodes.items() if v.get("node_type") != "screen"}
    screen_nodes = {k: v for k, v in all_nodes.items() if v.get("node_type") == "screen"}

    # collect inherits_from references as refs
    refs: list[dict] = []
    for node_name, node in all_nodes.items():
        for ref in node.get("inherits_from", []):
            refs.append({"from": node_name, "to": ref})

    (graph_dir / "graph.policy.json").write_text(
        json.dumps({"graph": {"metadata": metadata, "nodes": policy_nodes}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (graph_dir / "graph.screen.json").write_text(
        json.dumps({"graph": {"metadata": metadata, "nodes": screen_nodes}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (graph_dir / "graph.edges.json").write_text(
        json.dumps({"graph": {"edges": all_edges}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (graph_dir / "graph.refs.json").write_text(
        json.dumps({"graph": {"refs": refs}},
                   ensure_ascii=False, indent=2), encoding="utf-8")


# ── Phase 5C — cluster mode main ──────────────────────────────────────────
def _fanout_cluster_mode(
    graph: dict[str, Any],
    output_dir: Path,
    product_name: str,
    prefix: str,
    graph_hash: str,
    *,
    publication_mode: str | None = None,
) -> None:
    """Cluster-level WO generation (Track A — Full Product).

    One draft per cluster (capability + cluster_id) in graph.json:
        drafts/cluster_{cluster_id}.draft.md

    cluster_identify.py must have run beforehand so node metadata carries
    capability/cluster_id. Unassigned nodes get DX-{node_name} fallback clusters.
    """
    cluster_groups = list(_iter_cluster_nodes(graph))
    if not cluster_groups:
        raise FanoutError("graph.json has no policy nodes to process (cluster mode).")

    output_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir = output_dir.parent / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    now_iso = datetime.utcnow().isoformat() + "Z"
    prefix_val = prefix or "PX"
    cluster_records: list[dict[str, Any]] = []

    for capability, cluster_id, cluster_name, members in cluster_groups:
        draft_path = drafts_dir / f"cluster_{cluster_id}.draft.md"
        wo_id = f"{prefix_val}-K-{cluster_id}"

        # existing draft lifecycle handling (Plan A status consistency)
        existing_status = _check_existing_draft_status(draft_path)
        record_status = existing_status

        if existing_status in ("ai-draft", "human-reviewed", "frozen"):
            # authoring/review in progress — preserve content (idempotency). member-change refresh is future 5D.
            pass
        elif existing_status in ("no-status", "no-frontmatter"):
            # legacy draft (no status) — preserve content, surgically inject status only.
            # may already be authored, so assume ai-draft (back-inference, same as the migrate rule).
            existing_text = draft_path.read_text(encoding="utf-8")
            draft_path.write_text(_inject_status_field(existing_text, "ai-draft"),
                                  encoding="utf-8")
            record_status = "ai-draft"
        else:
            # absent / empty / read-error: create a fresh empty shell (status: empty built in)
            content = _generate_cluster_draft_content(
                capability=capability,
                cluster_id=cluster_id,
                cluster_name=cluster_name,
                members=members,
                product_name=product_name,
                graph_hash=graph_hash,
                now_iso=now_iso,
                prefix_val=prefix_val,
            )
            draft_path.write_text(content, encoding="utf-8")
            record_status = "empty"

        cluster_records.append({
            "wo_id": wo_id,
            "type": "cluster",
            "capability": capability,
            "cluster_id": cluster_id,
            "cluster_name": cluster_name,
            "members": [m[0] for m in members],
            "draft_path": str(draft_path.relative_to(output_dir.parent)),
            "status": record_status,
        })

    # cluster_index.json — input for downstream steps (render transpose etc.)
    index_path = output_dir / "cluster_index.json"
    index_path.write_text(
        json.dumps(
            {
                "product": product_name,
                "generated_at": now_iso,
                "graph_hash": graph_hash[:12],
                "clusters": cluster_records,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    # persist the publication mode (fix-plan-dossier-publish-split) — read-modify-write.
    # pinned into graph/project-mode.json so render/cr/sync read the track instead of inferring it.
    _apply_publication_mode(output_dir.parent / "graph", publication_mode)

    print(
        f"[fanout] cluster mode: {len(cluster_records)} clusters → {drafts_dir}"
        + (f" (publication_mode={publication_mode})" if publication_mode else ""),
        file=sys.stderr,
    )


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Topologically sort graph.json and generate Work Order files."
    )
    parser.add_argument("graph", type=Path, help="path to graph/graph.json")
    parser.add_argument("--output", type=Path, required=True, help="work-orders/ output directory")
    parser.add_argument("--product", type=str, default="unknown", help="project name")
    parser.add_argument("--prefix", type=str, default="", help="{PREFIX} value (e.g. CLOUD)")
    parser.add_argument(
        "--cluster-mode",
        action="store_true",
        help="Phase 5C — cluster-level WO generation (Track A Full Product). The graph "
             "must carry capability/cluster_id (run cluster_identify.py first).",
    )
    parser.add_argument(
        "--force-legacy",
        action="store_true",
        help="Force legacy section/screen WO generation even when cluster(dossier) "
             "model signals are detected. Explicitly bypasses the fail-closed guard "
             "(P0) — WO shells are created next to existing dossiers, so use only "
             "when the intent is confirmed.",
    )
    parser.add_argument(
        "--publication-mode",
        choices=list(VALID_PUBLICATION_MODES),
        default=None,
        help="Publication mode (cluster-mode only, fix-plan-dossier-publish-split). "
             "dossier-page (default): 1 feature definition = 1 page. "
             "split-deliverable: transpose-splits dossier §1/§2 into the D2 policy "
             "definition / D3 screen design spec. Persisted in "
             "graph/project-mode.json. If omitted, the existing value is kept "
             "(dossier-page when absent).",
    )
    parser.add_argument(
        "--delta",
        type=Path,
        default=None,
        help="(not implemented) selective regeneration based on decisions.md changes",
    )
    parser.add_argument(
        "--regenerate",
        type=str,
        default=None,
        help="(not implemented) regenerate a specific WO only (e.g. WO-07)",
    )
    args = parser.parse_args()

    if not args.prefix:
        print("[fanout] WARN: --prefix not given. {PREFIX}-A in templates will render as 'PREFIX-A'.", file=sys.stderr)

    if args.delta or args.regenerate:
        print(
            "[fanout] WARN: --delta / --regenerate currently behave the same as full regeneration.",
            file=sys.stderr,
        )

    try:
        fanout(
            args.graph,
            args.output,
            args.product,
            prefix=args.prefix,
            cluster_mode=args.cluster_mode,
            force_legacy=args.force_legacy,
            publication_mode=args.publication_mode,
        )
    except FanoutError as exc:
        print(f"[fanout] FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
