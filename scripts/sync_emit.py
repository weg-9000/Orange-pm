#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_emit — Confluence 동기화 상태 어댑터 (kind: sync, fix-plan-dossier-publish G1).

dossier 모델(1 capability = 1 기능정의서 = 1 Confluence 페이지)에서 각 dossier 의
동기화 상태를 viz 가 per-dossier 로 시각화·선택 push 할 수 있도록 정규화한다.

조인 소스(모두 읽기 전용):
    work-orders/cluster_index.json        — dossier 목록(wo_id·capability·draft_path)
    reports/sync-queue.md                 — render_sync_check 가 만든 상태 SSoT
    reports/inbox/{WO}.merge-proposal.md   — 원격 drift 대기 제안
    confluence-source/{doc}.meta.json      — per-dossier page_id (있으면)

상태(가장 심각한 것 우선): REMOTE-DRIFT > OUTDATED > PENDING > REMOTE-UNKNOWN
                           > UNKNOWN > SYNCED

CLI:
    python sync_emit.py --hub-root <Hub> --product <name> --emit-json
exit: 0 정상 / 1 cluster_index 없음(빈 골격) / 2 인자 오류
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import _emit_common as C
import wo_emit

# 상태 심각도(낮을수록 우선). viz 가 "가장 처리 필요한" 상태를 dossier 당 1개로 본다.
# SOURCE-ONLY: split-deliverable 모드의 dossier 정본 소스 — 발행 단위가 아니라
# actionable 제외(최저 우선). sync-queue.md 원본과 viz 표시의 정보 비대칭을 없앤다.
SEVERITY = {
    "REMOTE-DRIFT": 0,
    "OUTDATED": 1,
    "PENDING": 2,
    "REMOTE-UNKNOWN": 3,
    "UNKNOWN": 4,
    "SYNCED": 5,
    "SOURCE-ONLY": 6,
}
DEFAULT_STATUS = "PENDING"  # sync-queue 행이 없으면(미점검) 보수적으로 PENDING

_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
_BOLD_RE = re.compile(r"\*\*([A-Z-]+)\*\*")
_CODE_RE = re.compile(r"`([^`]+)`")


def parse_sync_queue(text: str) -> dict[str, str]:
    """sync-queue.md 표 → {doc_id: 가장 심각한 status}.

    행 형식: | 파일 | `doc_id` | meta | 기준값 | **STATUS** | 사유 |
    한 draft 가 순방향·역방향 2행을 가질 수 있어 doc_id 당 최심각 상태로 합친다.
    """
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("|") or "doc_id" in line or "---" in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        cid = _CODE_RE.search(cells[1])
        doc_id = cid.group(1) if cid else cells[1]
        st_m = _BOLD_RE.search(cells[4])
        status = st_m.group(1) if st_m else cells[4]
        if status not in SEVERITY:
            continue
        prev = out.get(doc_id)
        if prev is None or SEVERITY[status] < SEVERITY[prev]:
            out[doc_id] = status
    return out


def _doc_id_of(rec: dict) -> str:
    """cluster 레코드의 dossier doc_id (cluster_id == dossier 파일 stem).

    normalize_cluster_records 는 cluster_id 를 node_name 에 싣는다. raw cluster
    레코드(cluster_id 직접 보유)와 둘 다 지원하고, 최종 폴백은 draft_path stem.
    """
    return (rec.get("cluster_id") or rec.get("node_name")
            or Path(rec.get("draft_path", "")).stem.replace(".draft", "")
            or rec.get("wo_id", ""))


def transform_sync(
    product: str,
    dossiers: list[dict],
    queue_status: dict[str, str],
    inbox_docs: set[str],
    page_ids: dict[str, str],
) -> dict:
    """순수 함수(테스트용) — dossier 목록 + 상태 신호 → sync 계약.

    queue_status: {doc_id: status}, inbox_docs: merge-proposal 대기 doc_id 집합,
    page_ids: {doc_id: page_id}.
    """
    items: list[dict] = []
    for rec in dossiers:
        doc_id = _doc_id_of(rec)
        # _status 강제 레코드(SOURCE-ONLY 등)는 queue 조인을 건너뛴다.
        status = rec.get("_status") or queue_status.get(doc_id, DEFAULT_STATUS)
        page_id = page_ids.get(doc_id)
        # page_id 가 없으면 아직 페이지 미생성 → PENDING 으로 보정
        if not page_id and status == "SYNCED":
            status = "PENDING"
        items.append({
            "woId": rec.get("wo_id", ""),
            "docId": doc_id,
            "capability": rec.get("capability", ""),
            "clusterId": rec.get("cluster_id") or rec.get("node_name", ""),
            "draftPath": rec.get("draft_path", ""),
            "pageId": page_id or None,
            "status": status,
            "inboxPending": doc_id in inbox_docs,
        })
    items.sort(key=lambda it: (SEVERITY.get(it["status"], 9), it["docId"]))

    def _count(s: str) -> int:
        return sum(1 for it in items if it["status"] == s)

    totals = {
        "dossiers": len(items),
        "outdated": _count("OUTDATED"),
        "remoteDrift": _count("REMOTE-DRIFT"),
        "pending": _count("PENDING"),
        "synced": _count("SYNCED"),
        "inbox": sum(1 for it in items if it["inboxPending"]),
    }
    return {"kind": "sync", "product": product, "items": items, "totals": totals}


# split-deliverable 발행 단위 (render_sync_check.SPLIT_DELIVERABLES 와 정합)
SPLIT_DELIVERABLES = [("02-policy", "정책정의서"), ("03-screen-design", "화면설계서")]

# 발행 모드 무관 공통 발행 문서 (publication-map §0/§0-bis: D1/D4/D5 각 1페이지).
# (slug, 라벨, 소스 하위 디렉토리, 파일 glob) — 소스 파일이 없으면 항목 생략.
COMMON_DOCS = [
    ("01-requirements", "요구사항정의서", "inputs", "requirements*.md"),
    ("04-meetings", "회의록", "meetings", "*.md"),
    ("05-research", "타사조사", "inputs", "research*.md"),
]


def _collect_common(pdir: Path, product: str) -> tuple[list[dict], dict[str, str]]:
    """D1/D4/D5 공통 문서 레코드 + page_id. 소스 파일이 있는 문서만 포함한다.

    감사 2026-06-11 갭1: D1/D4/D5 는 발행 대상이지만 sync 뷰에 표시되지 않아
    PM 이 동기화 상태를 확인할 수 없었다. doc_id 는 meta 명명 규약과 동일한
    `{slug}-{product}` 정본 키를 쓴다(render_sync_check 와 정합).
    """
    src = pdir / "confluence-source"
    records: list[dict] = []
    page_ids: dict[str, str] = {}
    for slug, label, subdir, pattern in COMMON_DOCS:
        d = pdir / subdir
        files = [f for f in (sorted(d.glob(pattern)) if d.is_dir() else []) if f.is_file()]
        if not files:
            continue
        doc_id = f"{slug}-{product}"
        draft_path = f"{subdir}/{files[0].name}" if len(files) == 1 else f"{subdir}/"
        records.append({
            "wo_id": doc_id, "cluster_id": doc_id, "capability": label,
            "draft_path": draft_path,
        })
        pid = _meta_page_id(src, slug, product)
        if pid:
            page_ids[doc_id] = pid
    return records, page_ids


def _read_publication_mode(pdir: Path) -> str:
    """graph/project-mode.json 의 publication_mode. 파일/키 없으면 dossier-page.

    단일 소스(_emit_common.read_publication_mode)로 위임 — render_sync_check 와 정합.
    """
    return C.read_publication_mode(pdir)


def _meta_page_id(src: Path, slug: str, product: str) -> str | None:
    """confluence-source 에서 deliverable meta 의 page_id (플레이스홀더 제외)."""
    if not src.is_dir():
        return None
    cands = sorted(src.glob(f"{slug}-{product}.meta.json")) \
        or sorted(src.glob(f"{slug}*.meta.json"))
    for mf in cands:
        try:
            meta = json.loads(mf.read_text(encoding="utf-8"))
            pid = str(meta.get("id", ""))
            if pid and "{{" not in pid:
                return pid
        except Exception:
            pass
        break
    return None


def _collect_split(
    pdir: Path, product: str, queue_status: dict[str, str], inbox_docs: set[str],
    dossiers: list[dict],
) -> dict:
    """split-deliverable — 발행 단위 = D2 정책정의서 / D3 화면설계서 (+ 공통 D1/D4/D5).

    dossier 는 정본 소스이므로 발행 단위가 아니지만, sync-queue.md 원본과의 정보
    비대칭(감사 갭2)을 없애기 위해 SOURCE-ONLY 정보 행으로 함께 내보낸다
    (viz 는 체크박스 없는 정보 행으로 렌더 — 발행 액션 제외 유지).
    """
    src = pdir / "confluence-source"
    records: list[dict] = []
    page_ids: dict[str, str] = {}
    for slug, label in SPLIT_DELIVERABLES:
        doc_id = f"{slug}-{product}"
        records.append({
            "wo_id": doc_id, "cluster_id": doc_id, "capability": label,
            "draft_path": f"reports/render/{slug}.assembled.md",
        })
        pid = _meta_page_id(src, slug, product)
        if pid:
            page_ids[doc_id] = pid
    common_recs, common_pids = _collect_common(pdir, product)
    records.extend(common_recs)
    page_ids.update(common_pids)
    for rec in dossiers:
        records.append({
            "wo_id": rec.get("wo_id", ""), "cluster_id": _doc_id_of(rec),
            "capability": rec.get("capability", ""),
            "draft_path": rec.get("draft_path", ""),
            "_status": "SOURCE-ONLY",
        })
    return transform_sync(product, records, queue_status, inbox_docs, page_ids)


def _collect(pdir: Path, product: str) -> dict:
    # dossier 목록 (cluster_index.json)
    cidx = pdir / "work-orders" / "cluster_index.json"
    if not cidx.exists():
        return {"kind": "sync", "product": product, "items": [],
                "totals": {"dossiers": 0, "outdated": 0, "remoteDrift": 0,
                           "pending": 0, "synced": 0, "inbox": 0},
                "note": "cluster_index.json 없음 — dossier 모델 아님 또는 미생성"}
    dossiers = wo_emit.normalize_cluster_records(
        json.loads(cidx.read_text(encoding="utf-8")))

    # 상태 SSoT (sync-queue.md)
    sq = pdir / "reports" / "sync-queue.md"
    queue_status = parse_sync_queue(sq.read_text(encoding="utf-8")) if sq.exists() else {}

    # inbox 대기 제안 → doc_id 집합 (파일명 {WO_or_doc}.merge-proposal.md)
    inbox = pdir / "reports" / "inbox"
    inbox_docs: set[str] = set()
    if inbox.is_dir():
        for f in inbox.glob("*.merge-proposal.md"):
            inbox_docs.add(f.name.replace(".merge-proposal.md", ""))

    # 발행 모드 분기 (fix-plan-dossier-publish-split). split 이면 발행 단위가
    # D2/D3 2개(+공통 문서) + dossier SOURCE-ONLY 정보 행.
    if _read_publication_mode(pdir) == "split-deliverable":
        return _collect_split(pdir, product, queue_status, inbox_docs, dossiers)

    # per-dossier page_id (confluence-source/{doc}.meta.json)
    src = pdir / "confluence-source"
    page_ids: dict[str, str] = {}
    if src.is_dir():
        for rec in dossiers:
            doc_id = _doc_id_of(rec)
            for mf in sorted(src.glob("*.meta.json")):
                if doc_id.lower() in mf.stem.lower():
                    try:
                        meta = json.loads(mf.read_text(encoding="utf-8"))
                        pid = str(meta.get("id", ""))
                        if pid and "{{" not in pid:
                            page_ids[doc_id] = pid
                    except Exception:
                        pass
                    break

    # 공통 발행 문서(D1/D4/D5)도 dossier 와 함께 표시(감사 갭1).
    common_recs, common_pids = _collect_common(pdir, product)
    page_ids.update(common_pids)

    return transform_sync(product, dossiers + common_recs, queue_status, inbox_docs, page_ids)


def main(argv: list[str]) -> int:
    args = C.make_parser("sync").parse_args(argv)
    if args.from_fixture:
        return C.emit(C.load_fixture(args.from_fixture))
    if not (args.hub_root and args.product):
        sys.stderr.write("--hub-root, --product 필요\n")
        return 2
    pdir = C.product_dir(args.hub_root, args.product)
    result = _collect(pdir, args.product)
    return C.emit(result)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
