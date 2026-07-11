#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for render_sync_check.py (fix-plan-dossier-publish-split).

Verifies sync-queue output per publication mode (dossier-page / split-deliverable).
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import render_sync_check as M  # noqa: E402


def _scaffold(hub: Path, product: str, *, publication_mode: str | None,
              metas: dict[str, dict] | None = None) -> Path:
    """PROJECTS/{product} scaffold — 2 drafts + (optional) project-mode + meta."""
    proj = hub / "PROJECTS" / product
    (proj / "drafts").mkdir(parents=True)
    (proj / "graph").mkdir(parents=True)
    (proj / "confluence-source").mkdir(parents=True)
    for did, upd in (("G2-C-BDB-00", "2026-06-07"), ("G2-C-BDB-01", "2026-06-06")):
        (proj / "drafts" / f"{did}.draft.md").write_text(
            f"---\ndoc_id: {did}\nupdated_at: {upd}\n---\n# {did}\n",
            encoding="utf-8")
    if publication_mode is not None:
        (proj / "graph" / "project-mode.json").write_text(
            json.dumps({"track": "A", "publication_mode": publication_mode}),
            encoding="utf-8")
    for name, body in (metas or {}).items():
        (proj / "confluence-source" / name).write_text(
            json.dumps(body), encoding="utf-8")
    return proj


def _read_queue(proj: Path) -> str:
    return (proj / "reports" / "sync-queue.md").read_text(encoding="utf-8")


def test_split_emits_two_deliverable_rows_and_source_only():
    with tempfile.TemporaryDirectory() as d:
        hub = Path(d)
        proj = _scaffold(hub, "dbaas", publication_mode="split-deliverable", metas={
            # 02-policy: publish date is older than the draft's latest (2026-06-07) → OUTDATED
            "02-policy-dbaas.meta.json": {"id": "111", "_sync": {"last_published_at": "2026-06-01"}},
            # 03-screen: publish date is more recent → SYNCED
            "03-screen-design-dbaas.meta.json": {"id": "222", "_sync": {"last_published_at": "2026-06-09"}},
        })
        rc = M.scan(hub, "dbaas")
        q = _read_queue(proj)
        # 2 deliverable rows
        assert "02-policy-dbaas" in q and "03-screen-design-dbaas" in q
        assert "**OUTDATED**" in q
        # dossier is SOURCE-ONLY (excluded from actionable)
        assert "**SOURCE-ONLY**" in q
        assert "G2-C-BDB-00.draft.md" in q
        # 1 OUTDATED → actionable → exit 1
        assert rc == 1


def test_split_missing_meta_is_pending():
    with tempfile.TemporaryDirectory() as d:
        hub = Path(d)
        proj = _scaffold(hub, "dbaas", publication_mode="split-deliverable", metas={})
        M.scan(hub, "dbaas")
        q = _read_queue(proj)
        # no meta → both deliverables PENDING (verified via the summary header)
        assert "PENDING: 2" in q
        assert "02-policy-dbaas" in q and "03-screen-design-dbaas" in q
        # dossier is still SOURCE-ONLY
        assert "**SOURCE-ONLY**" in q


def test_dossier_page_mode_unchanged_no_source_only():
    with tempfile.TemporaryDirectory() as d:
        hub = Path(d)
        proj = _scaffold(hub, "dbaas", publication_mode=None, metas={})
        M.scan(hub, "dbaas")
        q = _read_queue(proj)
        # existing behavior — dossier draft is a direct row, no SOURCE-ONLY
        assert "**SOURCE-ONLY**" not in q
        assert "G2-C-BDB-00.draft.md" in q
        # no meta → each dossier PENDING (verified via the summary header)
        assert "PENDING: 2" in q


def test_dossier_page_meta_matches_by_internal_wo_id_not_filename():
    """H3 (audit 2026-06-08): even if the {WO_ID}.meta.json filename created by cr
    differs from the draft stem, it is matched by joining on the internal meta
    wo_id/doc_id (regression guard against permanent false PENDING)."""
    with tempfile.TemporaryDirectory() as d:
        hub = Path(d)
        proj = hub / "PROJECTS" / "dbaas"
        (proj / "drafts").mkdir(parents=True)
        (proj / "graph").mkdir(parents=True)
        src = proj / "confluence-source"; src.mkdir(parents=True)
        # fanout-produced dossier draft: filename stem = cluster_PR-01, internal wo_id = G2-K-PR-01
        (proj / "drafts" / "cluster_PR-01.draft.md").write_text(
            "---\nwo_id: G2-K-PR-01\ntype: cluster_draft\nupdated_at: 2026-06-01\n---\n# x\n",
            encoding="utf-8")
        # meta created by cr: filename = G2-K-PR-01.meta.json (stem mismatch), internal publish date is more recent
        (src / "G2-K-PR-01.meta.json").write_text(
            json.dumps({"id": "999", "wo_id": "G2-K-PR-01", "doc_id": "PR-01",
                        "_sync": {"last_published_at": "2026-06-09"}}), encoding="utf-8")
        M.scan(hub, "dbaas")
        q = (proj / "reports" / "sync-queue.md").read_text(encoding="utf-8")
        # match succeeds → summary PENDING 0, data row is SYNCED (publish date is more recent)
        assert "PENDING: 0" in q, q
        assert "| **SYNCED** |" in q
        assert "G2-K-PR-01.meta.json" in q  # meta joined via internal identifier


def test_read_publication_mode_defaults_dossier_page():
    with tempfile.TemporaryDirectory() as d:
        proj = Path(d)
        (proj / "graph").mkdir()
        assert M._read_publication_mode(proj) == "dossier-page"
        (proj / "graph" / "project-mode.json").write_text(
            json.dumps({"publication_mode": "split-deliverable"}), encoding="utf-8")
        assert M._read_publication_mode(proj) == "split-deliverable"


def _run() -> int:
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("PASS", name)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print("FAIL", name, "—", e)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
