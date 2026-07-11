#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for wo_emit."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import wo_emit as M  # noqa: E402

RAW = {"work_orders": [
    {"wo_id": "G2-C-X-001", "type": "policy", "level": 0, "node_name": "G2-C-X",
     "section_id": "1.2", "section_title": "Payment", "node_role": "feature",
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
    # older draft: status is non-standard (draft/no-delta); review_status is the board-vocabulary source of truth
    fm = {
        "G2-C-X-001": {"status": "draft", "review_status": "ai-draft"},
        "G2-C-X-002": {"status": "no-delta", "review_status": "human-reviewed", "reviewed_by": "PM"},
    }
    out = M.transform_wo(RAW, "demo", status_of=lambda w: fm.get(w, {}))
    it = {x["woId"]: x for x in out["items"]}
    assert it["G2-C-X-001"]["status"] == "ai-draft"       # status:draft ignored, review_status used
    assert it["G2-C-X-002"]["status"] == "human-reviewed"  # status:no-delta ignored


def test_status_fallback_when_no_review_status():
    fm = {"G2-C-X-001": {"status": "frozen"}}  # falls back to status when review_status is absent
    out = M.transform_wo(RAW, "demo", status_of=lambda w: fm.get(w, {}))
    it = {x["woId"]: x for x in out["items"]}
    assert it["G2-C-X-001"]["status"] == "frozen"


def test_levels_sorted_unique():
    out = M.transform_wo(RAW, "demo")
    assert out["levels"] == [0, 1]
    assert out["kind"] == "work-orders"


def test_default_status_empty_when_no_frontmatter():
    out = M.transform_wo(RAW, "demo")  # status_of default -> {}
    assert all(x["status"] == "empty" for x in out["items"])


def test_records_list_or_wrapped():
    assert len(M.transform_wo(RAW["work_orders"], "demo")["items"]) == 2  # list
    assert len(M.transform_wo(RAW, "demo")["items"]) == 2                  # wrapped


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
     "cluster_id": "PR-01", "cluster_name": "Pricing Calculation", "members": ["N1", "N2", "N3"],
     "draft_path": "drafts/cluster_PR-01.draft.md", "status": "new"},
    {"wo_id": "G2-K-PV-02", "type": "cluster", "capability": "Provisioning",
     "cluster_id": "PV-02", "cluster_name": "Resource Provisioning", "members": ["N4"],
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
    assert it["G2-K-PR-01"]["status"] == "empty"          # record_status "new" -> empty
    assert it["G2-K-PV-02"]["memberCount"] == 1
    assert it["G2-K-PV-02"]["status"] == "human-reviewed"  # falls back to record_status


def test_node_records_have_null_cluster_fields():
    out = M.transform_wo(RAW, "demo")
    assert all(x["capability"] is None and x["memberCount"] is None for x in out["items"])


def test_cluster_live_frontmatter_status_overrides_record():
    recs = M.normalize_cluster_records(CLUSTER_IDX)  # PR-01 record_status "new"
    # the cluster draft's live frontmatter status takes priority over the cluster_index record_status
    out = M.transform_wo(
        recs, "demo",
        status_of=lambda w: {"status": "ai-draft"} if w == "G2-K-PR-01" else {})
    it = {x["woId"]: x for x in out["items"]}
    assert it["G2-K-PR-01"]["status"] == "ai-draft"        # live frontmatter takes priority
    assert it["G2-K-PV-02"]["status"] == "human-reviewed"  # no frontmatter -> falls back to record


def test_parse_coverage_table():
    md = (
        "# bdd-coverage-queue — demo\n"
        "| WO | Type | Coverage | Status | Reason |\n"
        "|---|---|---|---|---|\n"
        "| G2-C-X-001 | policy | 4/4 cells defined | **OK** | key cells defined |\n"
        "| G2-C-X-002 | screen | missing error | **UNCOVERED** | 4-state missing |\n"
    )
    cov = M.parse_coverage(md)
    assert cov == {"G2-C-X-001": "OK", "G2-C-X-002": "UNCOVERED"}


def test_extract_screen_notes_top_level_bullets_only():
    # dossier §2 screen: only top-level bullets are extracted; nested indented bullets/other sections excluded
    text = (
        "## §1 Policy\n- policy bullet (excluded)\n\n"
        "## §2 Screen\n"
        "- Console (inherited): list/create/detail\n"
        "- Delta: replication topology\n"
        "  - nested bullet (excluded)\n\n"
        "## §3 Spec\n- spec (excluded)\n"
    )
    notes = M.extract_screen_notes(text)
    assert notes == ["Console (inherited): list/create/detail", "Delta: replication topology"]


def test_extract_screen_notes_graceful():
    assert M.extract_screen_notes("") == []
    assert M.extract_screen_notes("## §1 Policy\n- x\n") == []  # no §2


def test_cluster_screens_attached_in_transform():
    raw = [{"wo_id": "G2-K-C0", "type": "cluster", "level": 0, "node_name": "C0",
            "section_title": "Cap", "capability": "Cap", "draft_path": "drafts/C0.draft.md"}]
    out = M.transform_wo(raw, "p", screens_of=lambda _w: ["Screen A", "Screen B"])
    assert out["items"][0]["screens"] == ["Screen A", "Screen B"]
    # a policy record leaves screens empty
    raw2 = [{"wo_id": "P1", "type": "policy", "level": 0, "node_name": "P", "section_title": "s"}]
    out2 = M.transform_wo(raw2, "p", screens_of=lambda _w: ["ignored"])
    assert out2["items"][0]["screens"] == []


def test_doc_id_of_resolves_draft_path():
    """WO-NN numbering -> resolving the draft_path stem(doc_id) — BDD badge key matching (regression)."""
    assert M.doc_id_of("drafts/G2-C-CLOUD-CALC-S01.draft.md") == "G2-C-CLOUD-CALC-S01"
    assert M.doc_id_of("drafts/cluster_CL-X.draft.md") == "cluster_CL-X"
    assert M.doc_id_of("drafts/WO-08.draft.md") == "WO-08"


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
