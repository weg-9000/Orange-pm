#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bdd_assemble unit tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bdd_assemble as M  # noqa: E402

POLICY_DRAFT = """---
doc_id: G2-C-X-001
type: policy
referenced_policy: G2-C-X-POL@v1.2
referenced_master: G2-B-002@v1.3
---

## 3. Status × Action matrix

| Status \\ Action | create-resource | terminate |
|---|---|---|
| unpaid | deny [[POL §3-2]] | allow |
| normal | allow | allow |
"""

SCREEN_DRAFT = """---
doc_id: G2-C-X-002
type: screen
referenced_policy: G2-C-X-POL@v1.2
---

## 2. 4-state interaction sequence

| Status | Condition | UI Display | User Action | Next Status |
|---|---|---|---|---|
| Empty | 0 items | empty notice | click create | Loading |
| Loading | async | spinner | - | Loaded |
| Loaded | normal | list | click row | Loaded |
| Error | failure | error toast | retry | Loading |
"""


def test_policy_emits_scenario_per_nonempty_cell():
    feat, n, kind = M.assemble_one(POLICY_DRAFT, "G2-C-X-001")
    assert kind == "policy"
    assert n == 4  # 2 states × 2 actions, no blank cells
    assert feat.count("Scenario:") == 4
    assert 'the system is in "unpaid" state' in feat
    assert 'the result is "deny' in feat


def test_policy_skips_empty_cells():
    draft = POLICY_DRAFT.replace("| normal | allow | allow |", "| normal |  | allow |")
    _, n, _ = M.assemble_one(draft, "G2-C-X-001")
    assert n == 3  # one blank cell excluded


def test_policy_preserves_pol_marker_as_tag():
    feat, _, _ = M.assemble_one(POLICY_DRAFT, "G2-C-X-001")
    assert "@POL-3-2" in feat                 # cell [[POL §3-2]] → scenario tag
    assert "@POL:G2-C-X-POLv1.2" in feat      # frontmatter pin → feature tag (@ normalization)
    assert "[[POL §3-2]]" in feat             # trace comment preserved


def test_screen_emits_scenario_per_state_row():
    feat, n, kind = M.assemble_one(SCREEN_DRAFT, "G2-C-X-002")
    assert kind == "screen"
    assert n == 4
    assert 'the screen is in "Empty" state' in feat
    assert 'the user performs "click create"' in feat
    assert '"empty notice" is displayed' in feat
    assert 'the next state is "Loading"' in feat


def test_screen_column_order_independent():
    reordered = SCREEN_DRAFT.replace(
        "| Status | Condition | UI Display | User Action | Next Status |",
        "| Status | UI Display | Next Status | Condition | User Action |",
    ).replace(
        "| Empty | 0 items | empty notice | click create | Loading |",
        "| Empty | empty notice | Loading | 0 items | click create |",
    )
    feat, _, _ = M.assemble_one(reordered, "G2-C-X-002")
    assert '"empty notice" is displayed' in feat   # mapped by header name — order agnostic
    assert 'the next state is "Loading"' in feat


def test_no_table_emits_warning_feature():
    draft = "---\ntype: policy\n---\n\nbody without a table.\n"
    feat, n, _ = M.assemble_one(draft, "G2-C-X-009")
    assert n == 0
    assert "no behavior spec table to convert" in feat


CLUSTER_DRAFT = """---
doc_id: G2-K-AUTH-01
type: cluster_draft
referenced_policy: G2-C-X-POL@v1.0
---
::: {.panel section="§1 Policy Decisions"}
## §1 Policy Decisions
| Status \\ Action | call-API | revoke-key |
|---|---|---|
| normal | allow [[POL §1-2]] | allow |
| revoked | deny | deny |
:::
::: {.panel section="§2 Screen Design"}
## §2 Screen Design
| Status | Condition | UI Display | User Action | Next Status |
|---|---|---|---|---|
| idle | 0 keys | notice | issue | loading |
| success | issued | show key | copy | success |
:::
"""


def test_cluster_draft_extracts_both_policy_and_screen():
    feat, n, kind = M.assemble_one(CLUSTER_DRAFT, "G2-K-AUTH-01")
    assert kind == "cluster"
    # §1 matrix 4 cells (2 states × 2 actions) + §2 4-state 2 rows = 6 scenarios
    assert n == 6
    assert "@type:cluster" in feat
    assert "§1 Policy Decisions (Status × Action)" in feat   # policy section comment
    assert "§2 Screen Design (4-state)" in feat              # screen section comment
    # policy scenario (Given system state)
    assert 'the system is in "normal" state' in feat
    assert 'the result is "deny"' in feat
    # screen scenario (Given screen state)
    assert 'the screen is in "idle" state' in feat
    assert "@POL-1-2" in feat                           # §1 cell [[POL §1-2]] trace


def test_cluster_matrix_strict_not_confused_by_screen_action_column():
    # the 'User Action' column of §2 4-state must not be mistaken for a matrix
    screen_only = """---
type: cluster_draft
---
::: {.panel section="§2"}
| Status | Condition | UI Display | User Action | Next Status |
|---|---|---|---|---|
| idle | x | a | b | loading |
:::
"""
    feat, n, kind = M.assemble_one(screen_only, "G2-K-X")
    assert kind == "cluster"
    assert n == 1                                       # only 1 screen row (no matrix misfire)
    assert 'the screen is in "idle" state' in feat
    assert "§1 Policy Decisions (Status × Action)" not in feat     # no §1


def test_extract_tables_basic():
    tables = M.extract_tables("| a | b |\n|---|---|\n| 1 | 2 |\n\nprose\n\n| c |\n|---|\n| 3 |\n")
    assert len(tables) == 2
    assert tables[0][0] == ["a", "b"]
    assert tables[0][1] == [["1", "2"]]


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
