#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_emit unit tests (fix-plan-dossier-publish G1)."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import sync_emit as M  # noqa: E402

DOSSIERS = [
    {"wo_id": "G2-K-BDB-00", "node_name": "G2-C-BDB-00", "capability": "Overview",
     "draft_path": "drafts/G2-C-BDB-00.draft.md"},
    {"wo_id": "G2-K-BDB-01", "node_name": "G2-C-BDB-01", "capability": "Pricing",
     "draft_path": "drafts/G2-C-BDB-01.draft.md"},
]

SYNC_QUEUE = """# sync-queue — dbaas
> **OUTDATED: 1 · REMOTE-DRIFT: 0 · PENDING: 0**

| File | doc_id | meta.json | baseline | Status | Reason |
|---|---|---|---|---|---|
| G2-C-BDB-00.draft.md | `G2-C-BDB-00` | 00.meta.json | 2026-06-06 | **SYNCED** | ok |
| G2-C-BDB-01.draft.md | `G2-C-BDB-01` | 01.meta.json | 2026-06-07 | **OUTDATED** | push needed |
"""


def test_parse_sync_queue_picks_most_severe():
    st = M.parse_sync_queue(SYNC_QUEUE)
    assert st["G2-C-BDB-00"] == "SYNCED"
    assert st["G2-C-BDB-01"] == "OUTDATED"


def test_parse_sync_queue_two_rows_per_doc_takes_severe():
    text = SYNC_QUEUE + "| G2-C-BDB-00.draft.md | `G2-C-BDB-00` | 00 | v1/v2 | **REMOTE-DRIFT** | remote is newer |\n"
    st = M.parse_sync_queue(text)
    assert st["G2-C-BDB-00"] == "REMOTE-DRIFT"  # more severe than SYNCED -> promoted


def test_transform_sync_joins_status_and_pageid():
    st = {"G2-C-BDB-00": "SYNCED", "G2-C-BDB-01": "OUTDATED"}
    out = M.transform_sync("dbaas", DOSSIERS, st, set(), {"G2-C-BDB-00": "12345"})
    assert out["kind"] == "sync"
    by = {it["docId"]: it for it in out["items"]}
    assert by["G2-C-BDB-00"]["pageId"] == "12345"
    assert by["G2-C-BDB-00"]["status"] == "SYNCED"
    # a dossier with no page_id is corrected to PENDING even if SYNCED
    assert by["G2-C-BDB-01"]["status"] == "OUTDATED"  # keeps its original OUTDATED
    assert out["totals"]["outdated"] == 1


def test_no_pageid_synced_demoted_to_pending():
    st = {"G2-C-BDB-00": "SYNCED"}
    out = M.transform_sync("d", [DOSSIERS[0]], st, set(), {})  # no page_id
    assert out["items"][0]["status"] == "PENDING"


def test_missing_queue_row_defaults_pending():
    out = M.transform_sync("d", DOSSIERS, {}, set(), {})
    assert all(it["status"] == "PENDING" for it in out["items"])
    assert out["totals"]["pending"] == 2


def test_inbox_pending_flag_and_count():
    out = M.transform_sync("d", DOSSIERS, {"G2-C-BDB-01": "REMOTE-DRIFT"},
                           {"G2-C-BDB-01"}, {"G2-C-BDB-00": "1", "G2-C-BDB-01": "2"})
    by = {it["docId"]: it for it in out["items"]}
    assert by["G2-C-BDB-01"]["inboxPending"] is True
    assert by["G2-C-BDB-00"]["inboxPending"] is False
    assert out["totals"]["inbox"] == 1
    assert out["totals"]["remoteDrift"] == 1


def test_items_sorted_by_severity():
    st = {"G2-C-BDB-00": "SYNCED", "G2-C-BDB-01": "REMOTE-DRIFT"}
    out = M.transform_sync("d", DOSSIERS, st, set(),
                           {"G2-C-BDB-00": "1", "G2-C-BDB-01": "2"})
    assert out["items"][0]["status"] == "REMOTE-DRIFT"  # most severe first


# -- split-deliverable publication mode (fix-plan-dossier-publish-split) --------

def _scaffold_product(pdir: Path, publication_mode: str | None):
    """Minimal product directory — cluster_index + project-mode."""
    (pdir / "work-orders").mkdir(parents=True)
    (pdir / "reports").mkdir(parents=True)
    (pdir / "graph").mkdir(parents=True)
    (pdir / "work-orders" / "cluster_index.json").write_text(json.dumps({
        "product": "dbaas", "clusters": [
            {"wo_id": "G2-K-BDB-00", "cluster_id": "G2-C-BDB-00",
             "capability": "Overview", "cluster_name": "Overview",
             "draft_path": "drafts/G2-C-BDB-00.draft.md", "status": "ai-draft"},
            {"wo_id": "G2-K-BDB-01", "cluster_id": "G2-C-BDB-01",
             "capability": "Pricing", "cluster_name": "Pricing",
             "draft_path": "drafts/G2-C-BDB-01.draft.md", "status": "ai-draft"},
        ]}), encoding="utf-8")
    if publication_mode is not None:
        (pdir / "graph" / "project-mode.json").write_text(
            json.dumps({"track": "A", "publication_mode": publication_mode}),
            encoding="utf-8")


def test_collect_split_emits_two_deliverables():
    with tempfile.TemporaryDirectory() as d:
        pdir = Path(d)
        _scaffold_product(pdir, "split-deliverable")
        # 2 deliverable rows in sync-queue (mimics render_sync_check output)
        (pdir / "reports" / "sync-queue.md").write_text(
            "| File | doc_id | meta.json | baseline | Status | Reason |\n"
            "|---|---|---|---|---|---|\n"
            "| Policy Definition | `02-policy-dbaas` | m | x | **OUTDATED** | push needed |\n"
            "| Screen Design | `03-screen-design-dbaas` | m | x | **SYNCED** | ok |\n",
            encoding="utf-8")
        # per-deliverable meta (page_id present)
        src = pdir / "confluence-source"; src.mkdir()
        (src / "02-policy-dbaas.meta.json").write_text(
            json.dumps({"id": "111"}), encoding="utf-8")
        (src / "03-screen-design-dbaas.meta.json").write_text(
            json.dumps({"id": "222"}), encoding="utf-8")

        out = M._collect(pdir, "dbaas")
        assert out["kind"] == "sync"
        by = {it["docId"]: it for it in out["items"]}
        # publication units = 2 deliverables + dossier is a SOURCE-ONLY info row (audit gap 2)
        assert set(by) == {"02-policy-dbaas", "03-screen-design-dbaas",
                           "G2-C-BDB-00", "G2-C-BDB-01"}
        assert by["02-policy-dbaas"]["status"] == "OUTDATED"
        assert by["02-policy-dbaas"]["pageId"] == "111"
        assert by["03-screen-design-dbaas"]["status"] == "SYNCED"
        assert by["G2-C-BDB-00"]["status"] == "SOURCE-ONLY"
        assert by["G2-C-BDB-01"]["status"] == "SOURCE-ONLY"
        assert out["totals"]["outdated"] == 1
        # SOURCE-ONLY is lowest severity — sorts after the deliverables
        assert out["items"][-1]["status"] == "SOURCE-ONLY"


def test_collect_dossier_page_mode_unchanged():
    # no project-mode -> defaults to dossier-page -> publication unit = per-dossier
    with tempfile.TemporaryDirectory() as d:
        pdir = Path(d)
        _scaffold_product(pdir, None)
        out = M._collect(pdir, "dbaas")
        docs = {it["docId"] for it in out["items"]}
        assert docs == {"G2-C-BDB-00", "G2-C-BDB-01"}  # stays at dossier granularity


# -- common publication docs D1/D4/D5 (audit 2026-06-11 gap 1) ------------------

def test_collect_includes_common_docs_when_sources_exist():
    with tempfile.TemporaryDirectory() as d:
        pdir = Path(d)
        _scaffold_product(pdir, None)
        (pdir / "inputs").mkdir()
        (pdir / "inputs" / "requirements.md").write_text("# req", encoding="utf-8")
        (pdir / "inputs" / "research.md").write_text("# research", encoding="utf-8")
        (pdir / "meetings").mkdir()
        (pdir / "meetings" / "2026-06-01.md").write_text("# mtg", encoding="utf-8")
        src = pdir / "confluence-source"; src.mkdir()
        (src / "01-requirements-dbaas.meta.json").write_text(
            json.dumps({"id": "910"}), encoding="utf-8")

        out = M._collect(pdir, "dbaas")
        by = {it["docId"]: it for it in out["items"]}
        assert {"01-requirements-dbaas", "04-meetings-dbaas", "05-research-dbaas"} <= set(by)
        assert by["01-requirements-dbaas"]["pageId"] == "910"
        assert by["01-requirements-dbaas"]["capability"] == "Requirements Definition"
        # no queue row -> conservatively PENDING
        assert by["04-meetings-dbaas"]["status"] == "PENDING"


def test_common_docs_skipped_without_sources():
    with tempfile.TemporaryDirectory() as d:
        pdir = Path(d)
        _scaffold_product(pdir, "split-deliverable")
        out = M._collect(pdir, "dbaas")
        docs = {it["docId"] for it in out["items"]}
        assert not any(doc.startswith(("01-requirements", "04-meetings", "05-research"))
                       for doc in docs)


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
