#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""journey_emit unit tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import journey_emit as M  # noqa: E402

# NOTE: the field labels "진입 조건:"/"핵심 행동:"/"전환:"/"목적:" below are kept in
# Korean intentionally — they are a parsing contract with journey_emit.py's
# _DETAIL_KEYS/_DETAIL_RE (out of scope for this translation pass). Only the
# surrounding decorative text and detail values are translated.
STORYBOARD = """Customer journey storyboard — openapi
Actor: all / Generated at: 2026-05-30
Total 3 screens (done 1 ✅ / in-progress 1 📝 / not started 1 ⬜)
─────────────────────────────────────────────
[1] SCR-001 API key management screen  ✅
  진입 조건: After login
  핵심 행동: Issue key
  전환:      → SCR-002 (issuance complete)
[2] SCR-002 Usage dashboard  📝
  핵심 행동: View usage
[3] SCR-003 Partner console  ⬜
  목적: Delegated operations
─────────────────────────────────────────────
Journey summary
  Entry point: SCR-001
  Key path: SCR-001 → SCR-002 → SCR-003
"""


def test_parse_storyboard_steps():
    steps = M.parse_storyboard(STORYBOARD)
    assert [s["id"] for s in steps] == ["SCR-001", "SCR-002", "SCR-003"]
    assert steps[0]["label"] == "API key management screen"
    assert steps[0]["status"] == "done"
    assert steps[1]["status"] == "draft"
    assert steps[2]["status"] == "todo"


def test_ignores_non_screen_lines():
    # summary/separator/entry-condition lines are not captured as steps
    steps = M.parse_storyboard(STORYBOARD)
    assert len(steps) == 3


def test_order_sorted():
    shuffled = "[3] SCR-C Three\n[1] SCR-A One\n[2] SCR-B Two\n"
    steps = M.parse_storyboard(shuffled)
    assert [s["id"] for s in steps] == ["SCR-A", "SCR-B", "SCR-C"]


def test_transform_journey_shape():
    out = M.transform_journey(STORYBOARD, "openapi")
    assert out["kind"] == "journey"
    assert out["product"] == "openapi"
    assert len(out["steps"]) == 3


def test_parse_storyboard_details():
    steps = M.parse_storyboard(STORYBOARD)
    by = {s["id"]: s for s in steps}
    assert by["SCR-001"]["entry"] == "After login"
    assert by["SCR-001"]["action"] == "Issue key"
    assert by["SCR-001"]["transition"] == "SCR-002 (issuance complete)"
    assert by["SCR-002"]["action"] == "View usage"
    assert "entry" not in by["SCR-002"]            # absent keys are not added
    assert by["SCR-003"]["purpose"] == "Delegated operations"


def test_journey_build_roundtrip(tmp_path=None):
    """journey_emit parses journey_build's output as-is (pipeline compatibility)."""
    import json as _json
    import tempfile
    from pathlib import Path as _P
    import journey_build as B
    with tempfile.TemporaryDirectory() as d:
        hub = _P(d)
        pdir = hub / "PROJECTS" / "demo"
        (pdir / "work-orders").mkdir(parents=True)
        (pdir / "drafts").mkdir()
        (pdir / "work-orders" / "cluster_index.json").write_text(_json.dumps({
            "clusters": [
                {"cluster_id": "PR-01", "capability": "Provisioning",
                 "draft_path": "drafts/cluster_PR-01.draft.md"},
                {"cluster_id": "PR-02", "capability": "Billing",
                 "draft_path": "drafts/cluster_PR-02.draft.md"},
            ]}), encoding="utf-8")
        (pdir / "drafts" / "cluster_PR-01.draft.md").write_text(
            "---\nreview_status: human-reviewed\n---\n"
            "## §1 Policy\n- p\n\n## §2 Screens\n- SCR-001 Create instance\n- Topology view\n",
            encoding="utf-8")
        # PR-02: no draft → §2 not written, todo
        assert B.build(hub, "demo", quiet=True) == 0
        out = pdir / "reports" / "journey-latest.md"
        steps = M.parse_storyboard(out.read_text(encoding="utf-8"))
        ids = [s["id"] for s in steps]
        assert ids == ["SCR-001", "PR-01-S2", "PR-02-S1"]
        assert steps[0]["status"] == "done"
        assert steps[2]["status"] == "todo"
        assert steps[0]["entry"] == "Service entry (first screen)"  # journey_build.py entry value now translated (coordinated edit, see journey_build.py)
        # no-change rerun → idempotent (same file, exit 0)
        before = out.read_text(encoding="utf-8")
        assert B.build(hub, "demo", quiet=True) == 0
        assert out.read_text(encoding="utf-8") == before


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
