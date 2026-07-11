#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bdd_coverage_scan unit tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bdd_assemble as A  # noqa: E402
import bdd_coverage_scan as M  # noqa: E402

FULL_4STATE = """## 2. 4-state

| Status | Condition | UI Display | User Action | Next Status |
|---|---|---|---|---|
| Empty | x | a | b | Loading |
| Loading | x | a | b | Loaded |
| Loaded | x | a | b | Loaded |
| Error | x | a | b | Loading |
"""

MISSING_ERROR = """## 2. 4-state

| Status | Condition | UI Display | User Action | Next Status |
|---|---|---|---|---|
| Empty | x | a | b | Loading |
| Loading | x | a | b | Loaded |
| Loaded | x | a | b | Loaded |
"""

MATRIX = """## 3. Status × Action matrix

| Status \\ Action | A1 | A2 |
|---|---|---|
| S1 | allow | deny |
| S2 | allow | allow |
"""

SPARSE_MATRIX = """## 3. Status × Action matrix

| Status \\ Action | A1 | A2 | A3 | A4 |
|---|---|---|---|---|
| S1 | allow |  |  |  |
"""


def _table(md, finder):
    return finder(A.extract_tables(md))


def test_full_4state_no_missing():
    assert M.screen_missing_states(_table(FULL_4STATE, A.find_state_table)) == []


def test_missing_error_state_detected():
    miss = M.screen_missing_states(_table(MISSING_ERROR, A.find_state_table))
    assert "error" in miss
    assert len(miss) == 1


def test_na_reason_exempts_missing():
    draft = MISSING_ERROR + "\n\nNote: error state N/A — this screen is static display only.\n"
    # screen_missing_states only looks at table data, so verify with an N/A row inside the table
    with_na = MISSING_ERROR.rstrip() + "| Error | N/A | - | - | - |\n"
    assert "error" not in M.screen_missing_states(_table(with_na, A.find_state_table))


def test_policy_full_matrix_ratio():
    filled, total = M.policy_empty_ratio(_table(MATRIX, A.find_matrix_table))
    assert (filled, total) == (4, 4)


def test_policy_sparse_matrix_ratio_under_half():
    filled, total = M.policy_empty_ratio(_table(SPARSE_MATRIX, A.find_matrix_table))
    assert filled == 1 and total == 4
    assert filled / total < 0.5


CLUSTER_FULL = """## §1
| Status \\ Action | A1 | A2 |
|---|---|---|
| S1 | allow | deny |
## §2
| Status | Condition | UI Display | User Action | Next Status |
|---|---|---|---|---|
| Empty | x | a | b | Loading |
| Loading | x | a | b | Loaded |
| Loaded | x | a | b | Loaded |
| Error | x | a | b | Loading |
"""

CLUSTER_MISSING_STATE = CLUSTER_FULL.replace("| Error | x | a | b | Loading |\n", "")


def test_cluster_both_tables_extracted():
    tables = A.extract_tables(CLUSTER_FULL)
    assert A.find_matrix_table_strict(tables) is not None      # §1 matrix
    assert A.find_state_table(tables) is not None              # §2 4-state
    # §2 4-state not mistaken for a strict matrix
    state = A.find_state_table(tables)
    assert M.screen_missing_states(state) == []                # all 4-states


def test_cluster_missing_4state_is_uncovered():
    tables = A.extract_tables(CLUSTER_MISSING_STATE)
    state = A.find_state_table(tables)
    miss = M.screen_missing_states(state)
    assert "error" in miss                                     # §2 error missing → UNCOVERED target


def _scan_one(tmp, *drafts, write_feature=False):
    """Lay out drafts under PROJECTS/p/drafts in tmp and run scan → (rc, queue text)."""
    import pathlib
    proj = pathlib.Path(tmp) / "PROJECTS" / "p"
    (proj / "drafts").mkdir(parents=True)
    (proj / "reports" / "bdd").mkdir(parents=True)
    for wo, body in drafts:
        (proj / "drafts" / f"{wo}.draft.md").write_text(body, encoding="utf-8")
        if write_feature:
            (proj / "reports" / "bdd" / f"{wo}.feature").write_text("Feature: x\n", encoding="utf-8")
    rc = M.scan(pathlib.Path(tmp), "p")
    return rc, (proj / "reports" / "bdd-coverage-queue.md").read_text(encoding="utf-8")


def test_screen_without_state_table_is_uncovered():
    """A screen draft without a 4-state table = UNCOVERED (false-green prevention regression)."""
    import tempfile
    no_tbl = "---\ntype: screen\n---\n\n## Screen description\n\n| Area | Value |\n|---|---|\n| a | b |\n"
    with tempfile.TemporaryDirectory() as tmp:
        rc, q = _scan_one(tmp, ("WO-99", no_tbl))
    assert "UNCOVERED: 1" in q
    assert "no table" in q
    assert rc == 1  # blocked


def test_cluster_draft_type_classified_as_screen():
    """cluster_draft type is normalized to screen — processed without crashing (regression)."""
    import tempfile
    cluster = "---\ntype: cluster_draft\n---\n\n" + FULL_4STATE
    with tempfile.TemporaryDirectory() as tmp:
        rc, q = _scan_one(tmp, ("cluster_X", cluster), write_feature=True)
    assert "UNCOVERED: 0" in q and "STALE: 0" in q
    assert rc == 0


LIFECYCLE_TABLE = """## §1-4 Status / lifecycle

| Status | Definition | Entry Condition | Next Status (possible) |
|---|---|---|---|
| closed (immutable) | snapshot fixed | quarterly close batch | retention expiry |
"""


def test_policy_lifecycle_table_not_detected_as_screen():
    """A policy lifecycle table (no UI/action columns) must not be mistaken for a screen 4-state table."""
    assert A.find_state_table(A.extract_tables(LIFECYCLE_TABLE)) is None


def test_na_subsection_exempts_missing_state():
    """'### error state' + 'N/A' prose exempts the missing error state (documented N/A)."""
    import tempfile
    body = (
        "---\ntype: screen\n---\n\n## 5. 4-State interaction sequence\n\n"
        "### 5-1. idle\n\n| Item | Content |\n|---|---|\n| entry | a |\n\n"
        "### 5-2. loading\n\n| Item | Content |\n|---|---|\n| trigger | a |\n\n"
        "### 5-3. success\n\n| Item | Content |\n|---|---|\n| finish | a |\n\n"
        "### error state\n\n- **N/A** — static recomputation, no standalone error.\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        rc, q = _scan_one(tmp, ("WO-NA", body), write_feature=True)
    assert "UNCOVERED: 0" in q
    assert "N/A:error" in q
    assert rc == 0


def test_wo_stub_skipped():
    """'# Work Order:' instruction stubs are not content drafts — excluded from scan/counts."""
    import tempfile
    stub = ("---\ntype: screen\n---\n\n# Work Order: WO-08 — calculator main screen\n\n"
            "## 1. Assigned scope\n\n## 7. Post-completion steps\n")
    with tempfile.TemporaryDirectory() as tmp:
        rc, q = _scan_one(tmp, ("WO-08", stub))
    assert "UNCOVERED: 0" in q
    assert rc == 0


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
