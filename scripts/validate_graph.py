#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graph.json validation script.

Change history:
    v1.0: initial implementation
    v2.0: screen node validation / implements direction validation /
          section-level cycle detection / duplicate edge ID detection /
          policy section completeness check / FAIL_EDGE_TYPES enabled

Checks:
    [FAIL]
    1. JSON Schema compliance
    2. edges source/target nodes exist
    3. edges source_section/target_section exist
    4. zero duplicate-definition edges
    5. prerequisite edge subgraph is a DAG (section level)
    6. implements edge direction (screen → policy enforced)
    7. no duplicate edge ids
    8. node_type valid values (policy | screen)

    [WARN]
    9.  isolated nodes (not connected to any edge)
    10. screen node required fields missing (screen_name / purpose / req_id)
    11. policy section completeness (title / summary missing)
    12. screen node without an implements edge

exit code:
    0 = PASS (WARN-only still returns 0)
    1 = FAIL
    2 = usage error
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

# Windows console/pipe encoding guard (audit 2026-06-08 H2):
# This script print()s non-ASCII FAIL/WARN messages (_print_human · errors.append).
# Windows default stdout is cp949, so when the fanout step-1 gate captures stdout
# through a pipe, print() can crash with UnicodeEncodeError, masking the real
# PASS/FAIL exit code. Force utf-8 with the same reconfigure guard as
# render_sync_check.py.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


VALID_NODE_TYPES = {"policy", "screen"}
VALID_EDGE_TYPES = {
    "prerequisite", "bidirectional-ref", "duplicate-definition", "feature-link",
    "event-definition", "security-standard", "implements",
    "term-standard", "ux-standard", "billing-target", "ops-procedure",
}
FAIL_EDGE_TYPES = {
    "duplicate-definition",      # a duplicate definition is itself a FAIL
}
DIRECTIONAL_EDGE_TYPES = {
    "implements",   # must run screen → policy
}


class ValidationError(Exception):
    pass


# ── load ──────────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValidationError(f"file not found: {path}")
    except json.JSONDecodeError as e:
        raise ValidationError(f"JSON parse failure ({path}): {e}")


def _load_graph_or_split(graph_path: Path) -> dict[str, Any]:
    """Detect graph.json or split files (improvement C) and return a merged doc."""
    graph_dir = graph_path.parent
    policy_file = graph_dir / "graph.policy.json"

    if policy_file.exists():
        # split mode: merge 4 files
        def _r(fname: str) -> dict:
            p = graph_dir / fname
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

        p_doc = _r("graph.policy.json").get("graph", {})
        s_doc = _r("graph.screen.json").get("graph", {})
        e_doc = _r("graph.edges.json").get("graph", {})
        metadata = p_doc.get("metadata") or s_doc.get("metadata", {})

        merged_nodes: dict = {}
        merged_nodes.update(p_doc.get("nodes", {}))
        merged_nodes.update(s_doc.get("nodes", {}))

        return {"graph": {
            "metadata": metadata,
            "nodes": merged_nodes,
            "edges": e_doc.get("edges", []),
        }}

    return _load_json(graph_path)


# ── 1. JSON Schema ────────────────────────────────────────────────────────────

def _validate_schema(graph_doc: dict, schema_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        from jsonschema import Draft7Validator
        schema = _load_json(schema_path)
        for err in Draft7Validator(schema).iter_errors(graph_doc):
            path = "/".join(str(p) for p in err.absolute_path) or "(root)"
            errors.append(f"schema: {path}: {err.message}")
    except ImportError:
        errors.extend(_minimal_schema_check(graph_doc))
    return errors


def _minimal_schema_check(doc: dict) -> list[str]:
    errors: list[str] = []
    if "graph" not in doc:
        errors.append("schema: top-level 'graph' key missing")
        return errors
    g = doc["graph"]
    for key in ("metadata", "nodes", "edges"):
        if key not in g:
            errors.append(f"schema: graph.{key} missing")
    if "nodes" in g and not isinstance(g["nodes"], dict):
        errors.append("schema: graph.nodes must be an object")
    if "edges" in g and not isinstance(g["edges"], list):
        errors.append("schema: graph.edges must be an array")
    return errors


# ── 2. node type validity ─────────────────────────────────────────────────────

def _validate_node_types(graph: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for name, node in graph.get("nodes", {}).items():
        nt = node.get("node_type")
        if nt is None:
            # nodes without node_type are judged by whether they have sections (v1.0 back-compat)
            if not node.get("sections"):
                warnings.append(
                    f"node-type: '{name}' has no node_type and no sections — "
                    "declaring policy or screen is recommended"
                )
        elif nt not in VALID_NODE_TYPES:
            errors.append(
                f"node-type: '{name}' node_type='{nt}' is invalid "
                f"(allowed: {sorted(VALID_NODE_TYPES)})"
            )
    return errors, warnings


# ── 3. edge reference existence + section existence ──────────────────────────

def _validate_references(graph: dict) -> list[str]:
    errors: list[str] = []
    nodes: dict = graph.get("nodes", {})
    for i, edge in enumerate(graph.get("edges", [])):
        src = edge.get("source")
        tgt = edge.get("target")
        src_sec = edge.get("source_section") or ""
        tgt_sec = edge.get("target_section") or ""

        # node existence
        if src not in nodes:
            errors.append(f"ref: edges[{i}] source node '{src}' not found")
        else:
            # screen nodes have no sections → src_sec must be empty
            node_sections = nodes[src].get("sections") or {}
            if src_sec and nodes[src].get("node_type") == "screen":
                errors.append(
                    f"ref: edges[{i}] screen node '{src}' cannot take "
                    f"source_section='{src_sec}'"
                )
            elif src_sec and src_sec not in node_sections:
                errors.append(
                    f"ref: edges[{i}] node '{src}' has no section '{src_sec}'"
                )

        if tgt not in nodes:
            errors.append(f"ref: edges[{i}] target node '{tgt}' not found")
        else:
            node_sections = nodes[tgt].get("sections") or {}
            if tgt_sec and nodes[tgt].get("node_type") == "screen":
                errors.append(
                    f"ref: edges[{i}] screen node '{tgt}' cannot take "
                    f"target_section='{tgt_sec}'"
                )
            elif tgt_sec and tgt_sec not in node_sections:
                errors.append(
                    f"ref: edges[{i}] node '{tgt}' has no section '{tgt_sec}'"
                )
    return errors


# ── 4. enforce zero duplicate-definition edges ────────────────────────────────

def _validate_no_duplicate_def(graph: dict) -> list[str]:
    errors: list[str] = []
    for i, edge in enumerate(graph.get("edges", [])):
        if edge.get("type") == "duplicate-definition":
            errors.append(
                f"duplicate-def: edges[{i}] "
                f"'{edge.get('source')}§{edge.get('source_section','')}' ↔ "
                f"'{edge.get('target')}§{edge.get('target_section','')}' — "
                "convert one side to a reference and re-run graph-generator"
            )
    return errors


# ── 5. prerequisite DAG validation (section level) ────────────────────────────

def _detect_cycle(graph: dict) -> list[str]:
    """Kahn-topological-sort prerequisite edges at (node, section) tuple level to detect cycles."""
    errors: list[str] = []
    nodes: dict = graph.get("nodes", {})

    # build the section-level key set
    section_keys: set[tuple[str, str]] = set()
    for name, node in nodes.items():
        if node.get("node_type") == "screen":
            section_keys.add((name, ""))
        else:
            for sid in (node.get("sections") or {}):
                section_keys.add((name, sid))
            if not node.get("sections"):
                section_keys.add((name, ""))

    in_deg: dict[tuple[str, str], int] = {k: 0 for k in section_keys}
    out_adj: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)

    for e in graph.get("edges", []):
        if e.get("type") != "prerequisite":
            continue
        src = (e.get("source", ""), e.get("source_section") or "")
        tgt = (e.get("target", ""), e.get("target_section") or "")
        if src not in in_deg or tgt not in in_deg:
            continue
        out_adj[src].append(tgt)
        in_deg[tgt] += 1

    queue: deque[tuple[str, str]] = deque(
        [k for k, d in in_deg.items() if d == 0]
    )
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for nxt in out_adj[node]:
            in_deg[nxt] -= 1
            if in_deg[nxt] == 0:
                queue.append(nxt)

    if visited < len(section_keys):
        stuck = [
            f"{n}§{s}" if s else n
            for (n, s), d in in_deg.items()
            if d > 0
        ]
        errors.append(
            f"cycle: prerequisite edges contain a cycle. suspect nodes: {stuck[:5]}"
            + (f" and {len(stuck) - 5} more" if len(stuck) > 5 else "")
        )
    return errors


# ── 6. enforce implements edge direction (screen → policy) ────────────────────

def _validate_implements_direction(graph: dict) -> list[str]:
    errors: list[str] = []
    nodes: dict = graph.get("nodes", {})
    for i, edge in enumerate(graph.get("edges", [])):
        if edge.get("type") != "implements":
            continue
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        src_type = nodes.get(src, {}).get("node_type")
        tgt_type = nodes.get(tgt, {}).get("node_type")
        if src_type != "screen":
            errors.append(
                f"direction: edges[{i}] implements source '{src}' has "
                f"node_type='{src_type}'. must be screen"
            )
        if tgt_type == "screen":
            errors.append(
                f"direction: edges[{i}] implements target '{tgt}' has "
                f"node_type='screen'. must be policy"
            )
    return errors


# ── 7. duplicate edge IDs ─────────────────────────────────────────────────────

def _validate_edge_id_uniqueness(graph: dict) -> list[str]:
    errors: list[str] = []
    seen: dict[str, int] = {}
    for i, edge in enumerate(graph.get("edges", [])):
        eid = edge.get("id")
        if not eid:
            continue
        if eid in seen:
            errors.append(
                f"edge-id: edges[{i}] id='{eid}' duplicated "
                f"(first: edges[{seen[eid]}])"
            )
        else:
            seen[eid] = i
    return errors


# ── 8~12. warnings ────────────────────────────────────────────────────────────

def _warn_isolated_nodes(graph: dict) -> list[str]:
    warnings: list[str] = []
    nodes: set[str] = set(graph.get("nodes", {}).keys())
    referenced: set[str] = set()
    for e in graph.get("edges", []):
        referenced.add(e.get("source", ""))
        referenced.add(e.get("target", ""))
    for n in nodes - referenced:
        warnings.append(f"isolated: node '{n}' is not connected to any edge")
    return warnings


def _warn_screen_fields(graph: dict) -> list[str]:
    warnings: list[str] = []
    for name, node in graph.get("nodes", {}).items():
        if node.get("node_type") != "screen":
            continue
        for field in ("screen_name", "purpose", "req_id"):
            if not node.get(field):
                warnings.append(
                    f"screen-field: '{name}' required field '{field}' missing"
                )
    return warnings


def _warn_screen_no_implements(graph: dict) -> list[str]:
    warnings: list[str] = []
    nodes: dict = graph.get("nodes", {})
    impl_sources: set[str] = {
        e["source"]
        for e in graph.get("edges", [])
        if e.get("type") == "implements"
    }
    for name, node in nodes.items():
        if node.get("node_type") == "screen" and name not in impl_sources:
            warnings.append(
                f"no-implements: screen node '{name}' has no implements edge — "
                "linking a related policy section is recommended"
            )
    return warnings


def _warn_policy_section_completeness(graph: dict) -> list[str]:
    warnings: list[str] = []
    for name, node in graph.get("nodes", {}).items():
        if node.get("node_type") == "screen":
            continue
        for sid, section in (node.get("sections") or {}).items():
            for field in ("title", "summary"):
                if not section.get(field):
                    warnings.append(
                        f"completeness: '{name}§{sid}' section '{field}' missing — "
                        "fallback text will be inserted at WO generation"
                    )
    return warnings


# ── track ↔ topology consistency (fix-plan-track-routing P1) ─────────────────

def _warn_track_topology_mismatch(graph: dict, graph_path: Path) -> list[str]:
    """Check consistency between project-mode.json (track=A) and the graph's cluster topology.

    If the track is A (dossier) but no policy node has capability/cluster_id,
    cluster_identify.py has not run yet. Running /fanout --cluster-mode on this
    graph would scatter every node into DX-{node} fallback clusters. Warn to run
    it first.
    """
    mode_path = graph_path.parent / "project-mode.json"
    if not mode_path.exists():
        return []
    try:
        mode = json.loads(mode_path.read_text(encoding="utf-8"))
    except Exception:
        return [f"track: failed to parse project-mode.json ({mode_path})"]
    is_track_a = str(mode.get("track", "")).upper() == "A" or mode.get("model") == "dossier"
    if not is_track_a:
        return []
    has_cluster_meta = any(
        n.get("capability") or n.get("cluster_id")
        for n in graph.get("nodes", {}).values()
        if n.get("node_type") != "screen"
    )
    if not has_cluster_meta:
        return [
            "track: project-mode.json says track=A (dossier) but graph nodes "
            "have no capability/cluster_id — run cluster_identify.py before "
            "/fanout --cluster-mode (otherwise nodes scatter into fallback "
            "clusters)"
        ]
    return []


# ── aggregate ─────────────────────────────────────────────────────────────────

def validate(graph_path: Path, schema_path: Path) -> dict[str, Any]:
    doc = _load_graph_or_split(graph_path)
    graph = doc.get("graph", {})

    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(_validate_schema(doc, schema_path))
    nt_err, nt_warn = _validate_node_types(graph)
    errors.extend(nt_err)
    warnings.extend(nt_warn)
    errors.extend(_validate_references(graph))
    errors.extend(_validate_no_duplicate_def(graph))
    errors.extend(_detect_cycle(graph))
    errors.extend(_validate_implements_direction(graph))
    errors.extend(_validate_edge_id_uniqueness(graph))
    warnings.extend(_warn_isolated_nodes(graph))
    warnings.extend(_warn_screen_fields(graph))
    warnings.extend(_warn_screen_no_implements(graph))
    warnings.extend(_warn_policy_section_completeness(graph))
    warnings.extend(_warn_track_topology_mismatch(graph, graph_path))

    return {
        "path": str(graph_path),
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "nodes": len(graph.get("nodes", {})),
            "policy_nodes": sum(
                1 for n in graph.get("nodes", {}).values()
                if n.get("node_type") != "screen"
            ),
            "screen_nodes": sum(
                1 for n in graph.get("nodes", {}).values()
                if n.get("node_type") == "screen"
            ),
            "edges": len(graph.get("edges", [])),
            "by_type": _count_by_edge_type(graph),
        },
    }


def _count_by_edge_type(graph: dict) -> dict[str, int]:
    counter: dict[str, int] = defaultdict(int)
    for e in graph.get("edges", []):
        counter[e.get("type", "_unknown")] += 1
    return dict(counter)


def _print_human(result: dict[str, Any]) -> None:
    s = result["stats"]
    print(f"graph: {result['path']}")
    print(
        f"  nodes: {s['nodes']} "
        f"(policy: {s['policy_nodes']} / screen: {s['screen_nodes']}) "
        f"/ edges: {s['edges']}"
    )
    if s["by_type"]:
        print("  by edge type:")
        for t, c in sorted(s["by_type"].items()):
            print(f"    - {t}: {c}")
    if result["errors"]:
        print("\nERRORS:")
        for e in result["errors"]:
            print(f"  [FAIL] {e}")
    if result["warnings"]:
        print("\nWARNINGS:")
        for w in result["warnings"]:
            print(f"  [WARN] {w}")
    print()
    print("PASS" if result["ok"] else "FAIL")


# ── entry point ───────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="orange-plan graph.json validator")
    parser.add_argument("graph", type=Path, help="path to graph.json")
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="path to graph-schema.json (if omitted, auto-search cwd(Hub) → graph parents → plugin)",
    )
    parser.add_argument("--json", action="store_true", help="output in JSON format")
    args = parser.parse_args(argv)

    schema = args.schema
    if schema is None:
        # templates/ lives in the Planning-Agent-Hub working directory and is not
        # bundled with the plugin. Search (1) cwd(Hub) → (2) graph.json ancestor
        # directories → (3) plugin-relative path, and exit with a clear error if
        # none exists.
        candidates = [Path.cwd() / "templates" / "graph-schema.json"]
        candidates += [
            ancestor / "templates" / "graph-schema.json"
            for ancestor in args.graph.resolve().parents
        ]
        candidates.append(
            Path(__file__).resolve().parent.parent / "templates" / "graph-schema.json"
        )
        schema = next((c for c in candidates if c.is_file()), None)
        if schema is None:
            print(
                "[ERROR] graph-schema.json not found. "
                "Check that Planning-Agent-Hub/templates/graph-schema.json exists, "
                "or pass the path explicitly with --schema.",
                file=sys.stderr,
            )
            return 2

    try:
        result = validate(args.graph, schema)
    except ValidationError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human(result)

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
