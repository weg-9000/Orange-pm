#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graph.json 검증 스크립트.

변경 이력:
    v1.0: 최초 구현
    v2.0: screen 노드 검증 / implements 방향 검증 /
          섹션 단위 순환 감지 / 엣지 ID 중복 감지 /
          policy 섹션 completeness 검사 / FAIL_EDGE_TYPES 활성화

검증 항목:
    [FAIL]
    1. JSON Schema 준수
    2. edges source/target 노드 실재
    3. edges source_section/target_section 실재
    4. 중복정의 엣지 0건
    5. 전제조건 엣지 서브그래프 DAG (섹션 단위)
    6. implements 엣지 방향 (screen → policy 강제)
    7. 엣지 id 중복 없음
    8. node_type 유효값 (policy | screen)

    [WARN]
    9.  고립 노드 (어떤 엣지와도 연결 없음)
    10. screen 노드 필수 필드 누락 (screen_name / purpose / req_id)
    11. policy 섹션 completeness (title / summary 누락)
    12. screen 노드에 implements 엣지 없음

exit code:
    0 = PASS (WARN만 있어도 0)
    1 = FAIL
    2 = 사용법 오류
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

# Windows 콘솔/파이프 인코딩 가드 (감사 2026-06-08 H2):
# 본 스크립트는 한글 FAIL/WARN 메시지를 print() 한다(_print_human·errors.append).
# Windows 기본 stdout 은 cp949 라, fanout step-1 게이트가 stdout 을 파이프로 캡처하면
# print() 가 UnicodeEncodeError 로 크래시 → 정상 PASS/FAIL exit code 가 가려진다.
# render_sync_check.py 와 동일한 reconfigure 가드로 utf-8 강제.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


VALID_NODE_TYPES = {"policy", "screen"}
VALID_EDGE_TYPES = {
    "전제조건", "양방향참조", "중복정의", "기능연동",
    "이벤트정의", "보안기준", "implements",
    "용어기준", "UX기준", "과금대상", "운영절차",
}
FAIL_EDGE_TYPES = {
    "중복정의",      # 중복 정의 자체가 FAIL
}
DIRECTIONAL_EDGE_TYPES = {
    "implements",   # 반드시 screen → policy 방향
}


class ValidationError(Exception):
    pass


# ── 로드 ──────────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValidationError(f"파일을 찾을 수 없음: {path}")
    except json.JSONDecodeError as e:
        raise ValidationError(f"JSON 파싱 실패 ({path}): {e}")


def _load_graph_or_split(graph_path: Path) -> dict[str, Any]:
    """graph.json 또는 분할 파일(개선안 C)을 감지해 통합 doc을 반환한다."""
    graph_dir = graph_path.parent
    policy_file = graph_dir / "graph.policy.json"

    if policy_file.exists():
        # 분할 모드: 4 파일 병합
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
        errors.append("schema: 최상위 'graph' 키 누락")
        return errors
    g = doc["graph"]
    for key in ("metadata", "nodes", "edges"):
        if key not in g:
            errors.append(f"schema: graph.{key} 누락")
    if "nodes" in g and not isinstance(g["nodes"], dict):
        errors.append("schema: graph.nodes는 객체여야 함")
    if "edges" in g and not isinstance(g["edges"], list):
        errors.append("schema: graph.edges는 배열이어야 함")
    return errors


# ── 2. 노드 타입 유효성 ────────────────────────────────────────────────────────

def _validate_node_types(graph: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for name, node in graph.get("nodes", {}).items():
        nt = node.get("node_type")
        if nt is None:
            # node_type 없는 노드는 sections 보유 여부로 판단 (v1.0 하위 호환)
            if not node.get("sections"):
                warnings.append(
                    f"node-type: '{name}' node_type 미지정이며 sections도 없음 — "
                    "policy 또는 screen 명시 권장"
                )
        elif nt not in VALID_NODE_TYPES:
            errors.append(
                f"node-type: '{name}' node_type='{nt}' 유효하지 않음 "
                f"(허용: {sorted(VALID_NODE_TYPES)})"
            )
    return errors, warnings


# ── 3. 엣지 참조 실재 + 섹션 실재 ────────────────────────────────────────────

def _validate_references(graph: dict) -> list[str]:
    errors: list[str] = []
    nodes: dict = graph.get("nodes", {})
    for i, edge in enumerate(graph.get("edges", [])):
        src = edge.get("source")
        tgt = edge.get("target")
        src_sec = edge.get("source_section") or ""
        tgt_sec = edge.get("target_section") or ""

        # 노드 실재
        if src not in nodes:
            errors.append(f"ref: edges[{i}] source 노드 '{src}' 없음")
        else:
            # screen 노드는 sections 없음 → src_sec이 비어 있어야 정상
            node_sections = nodes[src].get("sections") or {}
            if src_sec and nodes[src].get("node_type") == "screen":
                errors.append(
                    f"ref: edges[{i}] screen 노드 '{src}'에 "
                    f"source_section='{src_sec}' 지정 불가"
                )
            elif src_sec and src_sec not in node_sections:
                errors.append(
                    f"ref: edges[{i}] '{src}' 노드에 섹션 '{src_sec}' 없음"
                )

        if tgt not in nodes:
            errors.append(f"ref: edges[{i}] target 노드 '{tgt}' 없음")
        else:
            node_sections = nodes[tgt].get("sections") or {}
            if tgt_sec and nodes[tgt].get("node_type") == "screen":
                errors.append(
                    f"ref: edges[{i}] screen 노드 '{tgt}'에 "
                    f"target_section='{tgt_sec}' 지정 불가"
                )
            elif tgt_sec and tgt_sec not in node_sections:
                errors.append(
                    f"ref: edges[{i}] '{tgt}' 노드에 섹션 '{tgt_sec}' 없음"
                )
    return errors


# ── 4. 중복정의 엣지 0건 강제 ────────────────────────────────────────────────

def _validate_no_duplicate_def(graph: dict) -> list[str]:
    errors: list[str] = []
    for i, edge in enumerate(graph.get("edges", [])):
        if edge.get("type") == "중복정의":
            errors.append(
                f"duplicate-def: edges[{i}] "
                f"'{edge.get('source')}§{edge.get('source_section','')}' ↔ "
                f"'{edge.get('target')}§{edge.get('target_section','')}' — "
                "한쪽을 참조로 전환 후 graph-generator 재실행"
            )
    return errors


# ── 5. 전제조건 DAG 검증 (섹션 단위) ─────────────────────────────────────────

def _detect_cycle(graph: dict) -> list[str]:
    """전제조건 엣지를 (node, section) 튜플 단위로 Kahn 위상정렬해 순환을 감지한다."""
    errors: list[str] = []
    nodes: dict = graph.get("nodes", {})

    # 섹션 단위 키 집합 생성
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
        if e.get("type") != "전제조건":
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
            f"cycle: 전제조건 엣지에 순환 존재. 의심 노드: {stuck[:5]}"
            + (f" 외 {len(stuck) - 5}개" if len(stuck) > 5 else "")
        )
    return errors


# ── 6. implements 엣지 방향 강제 (screen → policy) ────────────────────────────

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
                f"direction: edges[{i}] implements source '{src}'의 "
                f"node_type='{src_type}'. screen이어야 함"
            )
        if tgt_type == "screen":
            errors.append(
                f"direction: edges[{i}] implements target '{tgt}'의 "
                f"node_type='screen'. policy이어야 함"
            )
    return errors


# ── 7. 엣지 ID 중복 ───────────────────────────────────────────────────────────

def _validate_edge_id_uniqueness(graph: dict) -> list[str]:
    errors: list[str] = []
    seen: dict[str, int] = {}
    for i, edge in enumerate(graph.get("edges", [])):
        eid = edge.get("id")
        if not eid:
            continue
        if eid in seen:
            errors.append(
                f"edge-id: edges[{i}] id='{eid}' 중복 "
                f"(최초: edges[{seen[eid]}])"
            )
        else:
            seen[eid] = i
    return errors


# ── 8~12. 경고 ────────────────────────────────────────────────────────────────

def _warn_isolated_nodes(graph: dict) -> list[str]:
    warnings: list[str] = []
    nodes: set[str] = set(graph.get("nodes", {}).keys())
    referenced: set[str] = set()
    for e in graph.get("edges", []):
        referenced.add(e.get("source", ""))
        referenced.add(e.get("target", ""))
    for n in nodes - referenced:
        warnings.append(f"isolated: 노드 '{n}' 이 어떤 엣지와도 연결되지 않음")
    return warnings


def _warn_screen_fields(graph: dict) -> list[str]:
    warnings: list[str] = []
    for name, node in graph.get("nodes", {}).items():
        if node.get("node_type") != "screen":
            continue
        for field in ("screen_name", "purpose", "req_id"):
            if not node.get(field):
                warnings.append(
                    f"screen-field: '{name}' 필수 필드 '{field}' 누락"
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
                f"no-implements: screen 노드 '{name}'에 implements 엣지 없음 — "
                "연관 policy 섹션 연결 권장"
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
                        f"completeness: '{name}§{sid}' 섹션 '{field}' 누락 — "
                        "WO 생성 시 fallback 텍스트가 삽입됨"
                    )
    return warnings


# ── 트랙↔토폴로지 정합 (fix-plan-track-routing P1) ──────────────────────────

def _warn_track_topology_mismatch(graph: dict, graph_path: Path) -> list[str]:
    """project-mode.json(track=A) 와 graph 의 cluster 토폴로지 정합을 검사한다.

    트랙이 A(dossier)인데 policy 노드에 capability/cluster_id 가 하나도 없으면,
    아직 cluster_identify.py 가 실행되지 않은 상태다. 이 graph 로 /fanout --cluster-mode
    를 돌리면 모든 노드가 DX-{node} fallback cluster 로 흩어진다. 선행 실행을 경고한다.
    """
    mode_path = graph_path.parent / "project-mode.json"
    if not mode_path.exists():
        return []
    try:
        mode = json.loads(mode_path.read_text(encoding="utf-8"))
    except Exception:
        return [f"track: project-mode.json 파싱 실패 ({mode_path})"]
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
            "track: project-mode.json 은 track=A(dossier)인데 graph 노드에 "
            "capability/cluster_id 가 없음 — /fanout --cluster-mode 전에 "
            "cluster_identify.py 를 먼저 실행하세요 (미실행 시 노드가 fallback "
            "cluster 로 흩어짐)"
        ]
    return []


# ── 통합 ──────────────────────────────────────────────────────────────────────

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


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="orange-plan graph.json validator")
    parser.add_argument("graph", type=Path, help="graph.json 경로")
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="graph-schema.json 경로 (생략 시 cwd(Hub)→graph 상위→플러그인 순 자동 탐색)",
    )
    parser.add_argument("--json", action="store_true", help="JSON 형식 출력")
    args = parser.parse_args(argv)

    schema = args.schema
    if schema is None:
        # templates/ 는 Planning-Agent-Hub 작업 디렉토리에 존재하며 플러그인에는
        # 번들되지 않는다. (1) cwd(Hub) → (2) graph.json 상위 디렉토리 → (3) 플러그인
        # 상대 경로 순으로 탐색하고, 어디에도 없으면 명확한 에러로 종료한다.
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
                "[ERROR] graph-schema.json 을 찾을 수 없습니다. "
                "Planning-Agent-Hub/templates/graph-schema.json 존재 여부를 확인하거나 "
                "--schema 로 경로를 직접 지정하세요.",
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
