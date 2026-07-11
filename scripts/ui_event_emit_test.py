#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui_event_emit unit tests."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import ui_event_emit as M  # noqa: E402


def test_build_event_fields():
    ev = M.build_event("PostToolUse", detail="S01.draft.md", agent=None, tool="edit",
                       ts="2026-06-03T10:00:00+09:00")
    assert ev["hook"] == "PostToolUse"
    assert ev["tool"] == "edit"
    assert ev["detail"] == "S01.draft.md"
    assert ev["ts"] == "2026-06-03T10:00:00+09:00"
    assert "agent" not in ev          # None fields are excluded


def test_append_creates_and_appends():
    with tempfile.TemporaryDirectory() as d:
        M.append_event(d, M.build_event("SubagentStop", None, "reviewer", None))
        M.append_event(d, M.build_event("PostToolUse", "x.md", None, "edit"))
        out = Path(d) / ".claude" / "ui-events.jsonl"
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["agent"] == "reviewer"
        assert json.loads(lines[1])["tool"] == "edit"


def test_append_truncates_to_max():
    with tempfile.TemporaryDirectory() as d:
        for i in range(10):
            M.append_event(d, M.build_event("PostToolUse", f"e{i}", None, "edit"), max_lines=5)
        out = Path(d) / ".claude" / "ui-events.jsonl"
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 5                      # tail preserved
        assert json.loads(lines[-1])["detail"] == "e9"


def test_detail_from_stdin():
    assert M.detail_from_stdin('{"prompt": "/fanout dbaas"}') == "/fanout dbaas"
    # multiple lines -> first line only, length-limited
    assert M.detail_from_stdin('{"prompt": "line1\\nline2"}') == "line1"
    assert M.detail_from_stdin('{"tool_name": "Edit"}') == "Edit"
    assert M.detail_from_stdin("not-json") is None      # graceful
    assert M.detail_from_stdin('{"prompt": ""}') is None
    long = M.detail_from_stdin(json.dumps({"prompt": "x" * 200}))
    assert long is not None and len(long) == 80          # limit 80


def test_main_never_fails():
    with tempfile.TemporaryDirectory() as d:
        rc = M.main(["--hook", "Stop", "--hub-root", d])
        assert rc == 0


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
