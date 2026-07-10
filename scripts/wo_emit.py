#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wo_emit — work-orders/index.json | cluster_index.json + draft frontmatter → 정규화 WO 계약 (§2).

두 fanout 트랙을 한 작업 보드로 흡수한다:
- node 모드(기본): work-orders/index.json (노드별 policy/screen WO).
- cluster 모드(Track A): index.json 부재 시 work-orders/cluster_index.json 폴백
  (cluster 단위 WO — capability/멤버수 노출).

WO 카드 배지용 BDD 정보(시나리오 수·커버리지)도 주입한다. feature·커버리지 키는
wo_id 가 아니라 **draft 파일 stem** 기준이다(cluster draft 는 cluster_{id}.draft.md
라 stem≠wo_id — node 모드는 stem==wo_id 라 하위호환).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import _emit_common as C

COV_ROW = re.compile(r"^\|\s*([^\s|][^|]*?)\s*\|.*\*\*(OK|UNCOVERED|STALE|WARN)\*\*", re.M)


def doc_id_of(draft_rel: str) -> str:
    """draft_path(상대경로) → BDD 산출물 키(doc_id stem). 'drafts/X.draft.md' → 'X'.
    WO 채번(WO-NN)≠draft 파일명일 때 .feature·커버리지 큐 매칭에 사용."""
    name = Path(draft_rel).name
    return name[:-len(".draft.md")] if name.endswith(".draft.md") else Path(name).stem


def parse_coverage(text: str) -> dict[str, str]:
    """bdd-coverage-queue.md 표 → {draft_stem: 상태}. 헤더·구분행은 자연히 미매치."""
    return {m.group(1).strip(): m.group(2) for m in COV_ROW.finditer(text or "")}


def _records(raw) -> list[dict]:
    """index.json 의 레코드 목록 추출(리스트 또는 키 래핑 모두 허용). 그 외 → []."""
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        return []
    for key in ("work_orders", "items", "wo", "records"):
        if isinstance(raw.get(key), list):
            return raw[key]
    return []


def normalize_cluster_records(raw) -> list[dict]:
    """cluster_index.json {clusters:[...]} → node-record 형태로 정규화.

    cluster draft 는 status frontmatter 가 없으므로(Phase 5 한계) 레코드의
    status(new/ai-draft/…)를 record_status 로 넘겨 폴백한다. members → linkedWos.
    """
    clusters = raw.get("clusters", []) if isinstance(raw, dict) else []
    out = []
    for c in clusters:
        members = c.get("members") or []
        out.append({
            "wo_id": c.get("wo_id", ""),
            "type": "cluster",
            "level": 0,
            "node_name": c.get("cluster_id", ""),
            "section_title": c.get("cluster_name", ""),
            "delta_required": False,
            "linked_wos": members,
            "members": members,
            "capability": c.get("capability", ""),
            "draft_path": c.get("draft_path", ""),
            "record_status": c.get("status"),
        })
    return out


# dossier §2 화면 섹션(자유 서술 불릿) 추출 — cluster(dossier) 모드 prototype/journey 입력.
# §2 는 구조화된 화면 목록이 아니라 서술 불릿이므로 화면 ID 를 만들지 않고 불릿 텍스트만 싣는다.
_SEC2_RE = re.compile(r"^##\s*§?\s*2\b[^\n]*\n(.*?)(?=^##\s|\Z)", re.S | re.M)


def extract_screen_notes(text: str) -> list[str]:
    """dossier 본문 → §2 화면 섹션의 최상위 불릿 텍스트 목록(빈/누락 graceful)."""
    m = _SEC2_RE.search(text or "")
    if not m:
        return []
    notes: list[str] = []
    for line in m.group(1).splitlines():
        # 최상위 불릿만(들여쓴 하위 불릿 제외). '- ' / '* ' 시작.
        if re.match(r"^[-*]\s+", line) and not line[:1].isspace():
            notes.append(re.sub(r"^[-*]\s+", "", line).strip())
    return notes


def _board_status(fm: dict) -> str:
    """draft frontmatter → 보드 status 어휘(empty/ai-draft/human-reviewed/frozen) 정규화.
    review_status 가 lifecycle 정본(ai-draft→human-reviewed→frozen, /review·/confirm 으로 전이).
    구버전 draft 는 status 필드에 비표준값(Draft·draft·no-delta)을 쓰므로 review_status 를 우선한다.
    둘 다 없으면 empty."""
    return fm.get("review_status") or fm.get("status") or "empty"


def transform_wo(raw, product: str = "", status_of=None, bdd_of=None, screens_of=None) -> dict:
    """raw index → 계약. status_of(wo_id)->dict|None 로 draft frontmatter 주입.
    bdd_of(wo_id)->dict 로 {scenarios:int, coverage:str|None} BDD 배지 정보 주입.
    screens_of(wo_id)->list[str] 로 cluster(dossier) §2 화면 불릿을 주입.
    cluster 레코드는 capability/memberCount/screens 를 추가로 싣고, frontmatter status 가
    없으면 record_status 로 폴백(new→empty 매핑)한다."""
    status_of = status_of or (lambda _wo: {})
    bdd_of = bdd_of or (lambda _wo: {})
    screens_of = screens_of or (lambda _wo: [])
    recs = _records(raw)
    items = []
    levels: set[int] = set()
    for r in recs:
        wid = r.get("wo_id", "")
        fm = status_of(wid) or {}
        bdd = bdd_of(wid) or {}
        lvl = int(r.get("level", 0))
        levels.add(lvl)
        # review_status 가 lifecycle 정본(ai-draft→human-reviewed→frozen, /review·/confirm 전이).
        # 구버전 draft 는 status 에 비표준값을 쓰므로 review_status 우선. cluster 는 record_status 폴백.
        raw_status = fm.get("review_status") or fm.get("status") or r.get("record_status") or "empty"
        status = "empty" if raw_status == "new" else raw_status
        members = r.get("members")
        items.append({
            "woId": wid,
            "type": r.get("type", "policy"),
            "level": lvl,
            "status": status,
            "title": r.get("section_title") or r.get("node_name", wid),
            "nodeName": r.get("node_name", ""),
            "sectionId": r.get("section_id", ""),
            "sectionTitle": r.get("section_title", ""),
            "nodeRole": r.get("node_role", "unknown"),
            "deltaRequired": bool(r.get("delta_required", False)),
            "linkedWos": r.get("linked_wos", []),
            "draftPath": r.get("draft_path") or f"drafts/{wid}.draft.md",
            "reviewedBy": fm.get("reviewed_by") or None,
            "reviewedAt": fm.get("reviewed_at") or None,
            "capability": r.get("capability") or None,
            "memberCount": len(members) if isinstance(members, list) else None,
            "screens": (screens_of(wid) if r.get("type") == "cluster" else []),
            "bddScenarios": int(bdd.get("scenarios", 0)),
            "bddCoverage": bdd.get("coverage") or None,
        })
    return {
        "version": "", "product": product, "kind": "work-orders",
        "levels": sorted(levels), "items": items,
    }


def _draft_stem(draft_path: str, wo_id: str) -> str:
    """draft 상대경로 → stem(파일명에서 .draft.md 제거). node: ==wo_id, cluster: cluster_{id}."""
    name = Path(draft_path or f"drafts/{wo_id}.draft.md").name
    return name[:-len(".draft.md")] if name.endswith(".draft.md") else Path(name).stem


def main(argv: list[str]) -> int:
    args = C.make_parser("wo").parse_args(argv)
    if args.from_fixture:
        return C.emit(C.load_fixture(args.from_fixture))
    if not (args.hub_root and args.product):
        sys.stderr.write("--hub-root, --product 필요\n")
        return 2
    pdir = C.product_dir(args.hub_root, args.product)
    idx = pdir / "work-orders" / "index.json"
    cidx = pdir / "work-orders" / "cluster_index.json"
    if idx.exists():
        records = _records(json.loads(idx.read_text(encoding="utf-8")))
    elif cidx.exists():
        records = normalize_cluster_records(json.loads(cidx.read_text(encoding="utf-8")))
    else:
        sys.stderr.write(f"index.json·cluster_index.json 모두 없음: {pdir / 'work-orders'}\n")
        return C.emit({"version": "empty", "product": args.product,
                       "kind": "work-orders", "levels": [], "items": []}) or 1

    path_of = {r.get("wo_id", ""): r.get("draft_path") or f"drafts/{r.get('wo_id','')}.draft.md"
               for r in records}
    stem_of = {wid: _draft_stem(dp, wid) for wid, dp in path_of.items()}

    def _doc_id(wo_id: str) -> str:
        # WO 채번(WO-NN)과 실제 draft 파일명(doc_id)이 다를 수 있다. BDD 산출물
        # (reports/bdd/{doc_id}.feature·커버리지 큐)은 draft stem(doc_id) 기준이므로
        # status_of 와 동일하게 draft_path 로 해소해야 배지가 매칭된다.
        return doc_id_of(path_of.get(wo_id) or f"drafts/{wo_id}.draft.md")

    def status_of(wo_id: str) -> dict:
        d = pdir / path_of.get(wo_id, f"drafts/{wo_id}.draft.md")
        if not d.exists():
            return {}
        return C.read_frontmatter(d.read_text(encoding="utf-8"))

    def screens_of(wo_id: str) -> list[str]:
        d = pdir / path_of.get(wo_id, f"drafts/{wo_id}.draft.md")
        if not d.exists():
            return []
        return extract_screen_notes(d.read_text(encoding="utf-8"))

    cov_q = pdir / "reports" / "bdd-coverage-queue.md"
    coverage = parse_coverage(cov_q.read_text(encoding="utf-8")) if cov_q.exists() else {}

    def bdd_of(wo_id: str) -> dict:
        # WO 채번(WO-NN)≠draft 파일명(doc_id)일 때 BDD 산출물 키 매칭(gitlab 회귀 수정).
        doc = _doc_id(wo_id)
        feat = pdir / "reports" / "bdd" / f"{doc}.feature"
        n = feat.read_text(encoding="utf-8").count("Scenario:") if feat.exists() else 0
        return {"scenarios": n, "coverage": coverage.get(doc)}

    return C.emit(transform_wo(records, args.product, status_of, bdd_of, screens_of))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
