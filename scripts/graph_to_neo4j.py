#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graph.json을 파싱해 Neo4j에 노드·관계를 MERGE로 적재한다.

[STANDALONE / OPTIONAL]
    어떤 스킬에서도 호출되지 않는 선택적 Neo4j 로더이다(현재 dormant).
    수동 적재 용도로만 유지하며, 호출될 경우를 대비해 정상 동작은 보장한다.

사용:
    python graph_to_neo4j.py --product <product_name> [--dry-run]
    python graph_to_neo4j.py --product <product_name> --neo4j-uri bolt://localhost:7687
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


VALID_NODE_TYPES = {"policy", "screen", "reference", "gate"}

EDGE_TYPE_MAP = {
    "inherits_from": "INHERITS_FROM",
    "includes": "INCLUDES",
    "blocks": "BLOCKS",
    "conflicts_with": "CONFLICTS_WITH",
    "verified_by": "VERIFIED_BY",
    "authored_in": "AUTHORED_IN",
    "implements": "IMPLEMENTS",
    "precondition": "PRECONDITION",
}


# ── 인수 파싱 ────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="graph.json → Neo4j MERGE 적재 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python graph_to_neo4j.py --product my-product
  python graph_to_neo4j.py --product my-product --dry-run
  python graph_to_neo4j.py --product my-product \\
      --neo4j-uri bolt://db.internal:7687 \\
      --neo4j-user admin
        """,
    )
    p.add_argument("--product", required=True,
                   help="PROJECTS/{product}/graph/graph.json 경로 결정")
    p.add_argument("--neo4j-uri", default="bolt://localhost:7687",
                   help="Neo4j Bolt URI (기본값: bolt://localhost:7687)")
    p.add_argument("--neo4j-user", default="neo4j",
                   help="Neo4j 사용자명 (기본값: neo4j)")
    p.add_argument("--neo4j-password", default=None,
                   help="Neo4j 비밀번호. NEO4J_PASSWORD 환경변수 우선 적용")
    p.add_argument("--dry-run", action="store_true",
                   help="실제 적재 없이 파싱 결과(노드·관계 수)만 출력")
    return p


# ── graph.json 로드 및 검증 ──────────────────────────────────────────────────

def load_graph(product: str) -> dict[str, Any]:
    graph_path = Path("PROJECTS") / product / "graph" / "graph.json"
    if not graph_path.exists():
        print(f"[ERROR] graph.json 을 찾을 수 없습니다: {graph_path}", file=sys.stderr)
        print(f"        /graph-gen {product} 를 먼저 실행하세요.", file=sys.stderr)
        sys.exit(1)

    try:
        with graph_path.open(encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ERROR] graph.json 파싱 실패: {e}", file=sys.stderr)
        sys.exit(1)

    # 봉투 정규화: 정본 {graph:{nodes,edges}} 와 레거시 평면 {nodes,edges} 모두 허용
    # (graph_emit.py 의 raw.get("graph", raw) 패턴과 동일).
    g = raw.get("graph", raw)

    for key in ("nodes", "edges"):
        if key not in g:
            print(f"[ERROR] graph.json 에 필수 키 '{key}' 가 없습니다.", file=sys.stderr)
            sys.exit(1)

    # nodes 는 dict(정본: {node_id: node}) 또는 list(레거시) 모두 허용 → list 로 정규화
    raw_nodes = g["nodes"]
    nodes = list(raw_nodes.values()) if isinstance(raw_nodes, dict) else raw_nodes
    edges = g["edges"]

    invalid = [
        n.get("doc_id") or n.get("screen_id")
        for n in nodes
        if n.get("node_type") not in VALID_NODE_TYPES
    ]
    if invalid:
        print(f"[ERROR] 유효하지 않은 node_type 노드 {len(invalid)}건: {invalid[:5]}", file=sys.stderr)
        print(f"        허용값: {VALID_NODE_TYPES}", file=sys.stderr)
        sys.exit(1)

    return {"nodes": nodes, "edges": edges}


# ── 노드·관계 분류 ───────────────────────────────────────────────────────────

def classify_nodes(nodes: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list] = {t: [] for t in VALID_NODE_TYPES}
    for n in nodes:
        ntype = n.get("node_type", "")
        result.setdefault(ntype, []).append(n)
    return result


# ── Neo4j 적재 ───────────────────────────────────────────────────────────────

def get_driver(uri: str, user: str, password: str):
    try:
        from neo4j import GraphDatabase  # type: ignore
    except ImportError:
        print("[ERROR] neo4j 패키지가 없습니다. pip install neo4j 를 실행하세요.", file=sys.stderr)
        sys.exit(1)

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        return driver
    except Exception as e:
        print(f"[ERROR] Neo4j 연결 실패: {e}", file=sys.stderr)
        print(f"        URI: {uri}, 사용자: {user}", file=sys.stderr)
        print("        Neo4j 서버가 실행 중인지, 연결 정보가 올바른지 확인하세요.", file=sys.stderr)
        sys.exit(1)


def merge_nodes(session, classified: dict[str, list[dict]]) -> dict[str, int]:
    counts: dict[str, int] = {}

    # Policy 노드
    for node in classified.get("policy", []):
        session.run(
            """
            MERGE (n:Policy {doc_id: $doc_id})
            SET n.title        = $title,
                n.layer        = $layer,
                n.delta_required = $delta_required,
                n.status       = $status,
                n.phase        = $phase
            """,
            doc_id=node.get("doc_id", ""),
            title=node.get("title", ""),
            layer=node.get("layer", ""),
            delta_required=node.get("delta_required", False),
            status=node.get("status", "draft"),
            phase=node.get("phase"),
        )
    counts["Policy"] = len(classified.get("policy", []))

    # Screen 노드
    for node in classified.get("screen", []):
        session.run(
            """
            MERGE (n:Screen {screen_id: $screen_id})
            SET n.title           = $title,
                n.state_count     = $state_count,
                n.component_count = $component_count,
                n.phase           = $phase
            """,
            screen_id=node.get("screen_id", node.get("doc_id", "")),
            title=node.get("title", ""),
            state_count=node.get("state_count", 0),
            component_count=node.get("component_count", 0),
            phase=node.get("phase"),
        )
    counts["Screen"] = len(classified.get("screen", []))

    # Reference 노드
    for node in classified.get("reference", []):
        session.run(
            """
            MERGE (n:Reference {doc_id: $doc_id})
            SET n.title       = $title,
                n.layer       = $layer,
                n.source_path = $source_path
            """,
            doc_id=node.get("doc_id", ""),
            title=node.get("title", ""),
            layer=node.get("layer", ""),
            source_path=node.get("source_path", ""),
        )
    counts["Reference"] = len(classified.get("reference", []))

    # Gate 노드
    for node in classified.get("gate", []):
        session.run(
            """
            MERGE (n:Gate {name: $name})
            SET n.phase      = $phase,
                n.conditions = $conditions
            """,
            name=node.get("name", node.get("doc_id", "")),
            phase=node.get("phase"),
            conditions=json.dumps(node.get("conditions", []), ensure_ascii=False),
        )
    counts["Gate"] = len(classified.get("gate", []))

    return counts


def merge_edges(session, edges: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}

    for edge in edges:
        raw_type = edge.get("type", "")
        rel_type = EDGE_TYPE_MAP.get(raw_type, raw_type.upper())
        source_id = edge.get("source", "")
        target_id = edge.get("target", "")

        cypher = f"""
            MATCH (a {{doc_id: $src}})
            MATCH (b {{doc_id: $tgt}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r.edge_id        = $edge_id,
                r.source_section = $source_section,
                r.target_section = $target_section
        """
        session.run(
            cypher,
            src=source_id,
            tgt=target_id,
            edge_id=edge.get("id", ""),
            source_section=edge.get("source_section", ""),
            target_section=edge.get("target_section", ""),
        )
        counts[rel_type] = counts.get(rel_type, 0) + 1

    return counts


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = build_parser().parse_args()

    password = os.environ.get("NEO4J_PASSWORD") or args.neo4j_password
    if not password and not args.dry_run:
        print("[ERROR] Neo4j 비밀번호가 없습니다.", file=sys.stderr)
        print("        NEO4J_PASSWORD 환경변수 또는 --neo4j-password 인수를 사용하세요.", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] graph.json 로드: PROJECTS/{args.product}/graph/graph.json")
    data = load_graph(args.product)

    nodes: list[dict] = data["nodes"]
    edges: list[dict] = data["edges"]
    classified = classify_nodes(nodes)

    print(f"[INFO] 노드 {len(nodes)}개, 관계 {len(edges)}개 파싱 완료")
    for ntype, lst in classified.items():
        if lst:
            print(f"       {ntype}: {len(lst)}개")

    if args.dry_run:
        print("\n[DRY-RUN] 실제 적재 없이 종료합니다.")
        edge_type_counts: dict[str, int] = {}
        for e in edges:
            t = EDGE_TYPE_MAP.get(e.get("type", ""), e.get("type", "").upper())
            edge_type_counts[t] = edge_type_counts.get(t, 0) + 1
        print("[DRY-RUN] 관계 타입별:")
        for rtype, cnt in edge_type_counts.items():
            print(f"       {rtype}: {cnt}개")
        return

    start = time.time()
    driver = get_driver(args.neo4j_uri, args.neo4j_user, password)

    try:
        with driver.session() as session:
            print("[INFO] Neo4j 노드 MERGE 시작...")
            node_counts = merge_nodes(session, classified)

            print("[INFO] Neo4j 관계 MERGE 시작...")
            edge_counts = merge_edges(session, edges)
    finally:
        driver.close()

    elapsed = time.time() - start
    print(f"\n[완료] 소요 시간: {elapsed:.1f}초")
    print("[완료] 적재 노드:")
    for label, cnt in node_counts.items():
        print(f"       :{label} {cnt}개")
    print("[완료] 적재 관계:")
    for rtype, cnt in edge_counts.items():
        print(f"       [{rtype}] {cnt}개")


if __name__ == "__main__":
    main()
