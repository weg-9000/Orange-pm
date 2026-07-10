#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wo_emit 유닛 테스트."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import wo_emit as M  # noqa: E402

RAW = {"work_orders": [
    {"wo_id": "G2-C-X-001", "type": "policy", "level": 0, "node_name": "G2-C-X",
     "section_id": "1.2", "section_title": "결제", "node_role": "feature",
     "delta_required": True, "linked_wos": ["G2-C-X-002"],
     "draft_path": "drafts/G2-C-X-001.draft.md"},
    {"wo_id": "G2-C-X-002", "type": "screen", "level": 1, "node_name": "S01"},
]}

FM = {
    "G2-C-X-001": {"status": "human-reviewed", "reviewed_by": "PM", "reviewed_at": "2026-06-03"},
    "G2-C-X-002": {"status": "empty"},
}


def test_status_merge_from_frontmatter():
    out = M.transform_wo(RAW, "demo", status_of=lambda w: FM.get(w, {}))
    it = {x["woId"]: x for x in out["items"]}
    assert it["G2-C-X-001"]["status"] == "human-reviewed"
    assert it["G2-C-X-001"]["reviewedBy"] == "PM"
    assert it["G2-C-X-002"]["status"] == "empty"


def test_review_status_preferred_over_status():
    # 구버전 draft: status 는 비표준(draft/no-delta), review_status 가 보드 어휘 정본
    fm = {
        "G2-C-X-001": {"status": "draft", "review_status": "ai-draft"},
        "G2-C-X-002": {"status": "no-delta", "review_status": "human-reviewed", "reviewed_by": "PM"},
    }
    out = M.transform_wo(RAW, "demo", status_of=lambda w: fm.get(w, {}))
    it = {x["woId"]: x for x in out["items"]}
    assert it["G2-C-X-001"]["status"] == "ai-draft"       # status:draft 무시, review_status 사용
    assert it["G2-C-X-002"]["status"] == "human-reviewed"  # status:no-delta 무시


def test_status_fallback_when_no_review_status():
    fm = {"G2-C-X-001": {"status": "frozen"}}  # review_status 없으면 status 폴백
    out = M.transform_wo(RAW, "demo", status_of=lambda w: fm.get(w, {}))
    it = {x["woId"]: x for x in out["items"]}
    assert it["G2-C-X-001"]["status"] == "frozen"


def test_levels_sorted_unique():
    out = M.transform_wo(RAW, "demo")
    assert out["levels"] == [0, 1]
    assert out["kind"] == "work-orders"


def test_default_status_empty_when_no_frontmatter():
    out = M.transform_wo(RAW, "demo")  # status_of 기본 → {}
    assert all(x["status"] == "empty" for x in out["items"])


def test_records_list_or_wrapped():
    assert len(M.transform_wo(RAW["work_orders"], "demo")["items"]) == 2  # 리스트
    assert len(M.transform_wo(RAW, "demo")["items"]) == 2                  # 래핑


def test_bdd_info_injected():
    bdd = {"G2-C-X-001": {"scenarios": 4, "coverage": "OK"},
           "G2-C-X-002": {"scenarios": 0, "coverage": "UNCOVERED"}}
    out = M.transform_wo(RAW, "demo", bdd_of=lambda w: bdd.get(w, {}))
    it = {x["woId"]: x for x in out["items"]}
    assert it["G2-C-X-001"]["bddScenarios"] == 4
    assert it["G2-C-X-001"]["bddCoverage"] == "OK"
    assert it["G2-C-X-002"]["bddCoverage"] == "UNCOVERED"


def test_bdd_defaults_when_no_injector():
    out = M.transform_wo(RAW, "demo")
    assert all(x["bddScenarios"] == 0 and x["bddCoverage"] is None for x in out["items"])


CLUSTER_IDX = {"clusters": [
    {"wo_id": "G2-K-PR-01", "type": "cluster", "capability": "Pricing",
     "cluster_id": "PR-01", "cluster_name": "요금 계산", "members": ["N1", "N2", "N3"],
     "draft_path": "drafts/cluster_PR-01.draft.md", "status": "new"},
    {"wo_id": "G2-K-PV-02", "type": "cluster", "capability": "Provisioning",
     "cluster_id": "PV-02", "cluster_name": "자원 생성", "members": ["N4"],
     "draft_path": "drafts/cluster_PV-02.draft.md", "status": "human-reviewed"},
]}


def test_normalize_cluster_records():
    recs = M.normalize_cluster_records(CLUSTER_IDX)
    assert [r["wo_id"] for r in recs] == ["G2-K-PR-01", "G2-K-PV-02"]
    assert recs[0]["type"] == "cluster"
    assert recs[0]["linked_wos"] == ["N1", "N2", "N3"]
    assert recs[0]["capability"] == "Pricing"
    assert recs[0]["record_status"] == "new"


def test_cluster_transform_capability_membercount_and_status():
    out = M.transform_wo(M.normalize_cluster_records(CLUSTER_IDX), "demo")
    it = {x["woId"]: x for x in out["items"]}
    assert it["G2-K-PR-01"]["type"] == "cluster"
    assert it["G2-K-PR-01"]["capability"] == "Pricing"
    assert it["G2-K-PR-01"]["memberCount"] == 3
    assert it["G2-K-PR-01"]["status"] == "empty"          # record_status "new" → empty
    assert it["G2-K-PV-02"]["memberCount"] == 1
    assert it["G2-K-PV-02"]["status"] == "human-reviewed"  # record_status 폴백


def test_node_records_have_null_cluster_fields():
    out = M.transform_wo(RAW, "demo")
    assert all(x["capability"] is None and x["memberCount"] is None for x in out["items"])


def test_cluster_live_frontmatter_status_overrides_record():
    recs = M.normalize_cluster_records(CLUSTER_IDX)  # PR-01 record_status "new"
    # cluster draft 의 라이브 frontmatter status 가 cluster_index record_status 보다 우선
    out = M.transform_wo(
        recs, "demo",
        status_of=lambda w: {"status": "ai-draft"} if w == "G2-K-PR-01" else {})
    it = {x["woId"]: x for x in out["items"]}
    assert it["G2-K-PR-01"]["status"] == "ai-draft"        # frontmatter 라이브 우선
    assert it["G2-K-PV-02"]["status"] == "human-reviewed"  # frontmatter 부재 → record 폴백


def test_parse_coverage_table():
    md = (
        "# bdd-coverage-queue — demo\n"
        "| WO | 유형 | 커버리지 | 상태 | 사유 |\n"
        "|---|---|---|---|---|\n"
        "| G2-C-X-001 | policy | 정의 4/4 셀 | **OK** | 주요 셀 정의됨 |\n"
        "| G2-C-X-002 | screen | 누락 error | **UNCOVERED** | 4-state 누락 |\n"
    )
    cov = M.parse_coverage(md)
    assert cov == {"G2-C-X-001": "OK", "G2-C-X-002": "UNCOVERED"}


def test_extract_screen_notes_top_level_bullets_only():
    # dossier §2 화면: 최상위 불릿만 추출, 하위 들여쓴 불릿·타 섹션 제외
    text = (
        "## §1 정책\n- 정책 불릿(제외)\n\n"
        "## §2 화면\n"
        "- 콘솔(상속): 목록·생성·상세\n"
        "- Delta: 복제 토폴로지\n"
        "  - 하위 불릿(제외)\n\n"
        "## §3 스펙\n- 스펙(제외)\n"
    )
    notes = M.extract_screen_notes(text)
    assert notes == ["콘솔(상속): 목록·생성·상세", "Delta: 복제 토폴로지"]


def test_extract_screen_notes_graceful():
    assert M.extract_screen_notes("") == []
    assert M.extract_screen_notes("## §1 정책\n- x\n") == []  # §2 없음


def test_cluster_screens_attached_in_transform():
    raw = [{"wo_id": "G2-K-C0", "type": "cluster", "level": 0, "node_name": "C0",
            "section_title": "Cap", "capability": "Cap", "draft_path": "drafts/C0.draft.md"}]
    out = M.transform_wo(raw, "p", screens_of=lambda _w: ["화면 A", "화면 B"])
    assert out["items"][0]["screens"] == ["화면 A", "화면 B"]
    # policy 레코드는 screens 비움
    raw2 = [{"wo_id": "P1", "type": "policy", "level": 0, "node_name": "P", "section_title": "s"}]
    out2 = M.transform_wo(raw2, "p", screens_of=lambda _w: ["무시"])
    assert out2["items"][0]["screens"] == []


def test_doc_id_of_resolves_draft_path():
    """WO-NN 채번 → draft_path stem(doc_id) 해소 — BDD 배지 키 매칭(회귀)."""
    assert M.doc_id_of("drafts/G2-C-CLOUD-CALC-S01.draft.md") == "G2-C-CLOUD-CALC-S01"
    assert M.doc_id_of("drafts/cluster_CL-X.draft.md") == "cluster_CL-X"
    assert M.doc_id_of("drafts/WO-08.draft.md") == "WO-08"


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
