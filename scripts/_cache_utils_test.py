#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_cache_utils multi-PREFIX support regression tests (Phase 0-1).

Covers:
  - read_active_prefix: ACTIVE_PREFIX takes precedence, PREFIX as fallback
  - read_prefixes: PREFIXES block parsing, single-value fallback
  - read_prefix: backward-compat wrapper (= read_active_prefix)
  - discover_layer_sources: new nested / legacy flat dual-path lookup
  - discover_b_sources: backward compat (SystemExit on empty list)
"""
from __future__ import annotations

from pathlib import Path

import pytest

import _cache_utils as c


def _make_hub(tmp_path: Path, layer_config: str) -> Path:
    hub = tmp_path / "Hub"
    (hub / "CONTEXT").mkdir(parents=True)
    (hub / "CONTEXT" / "layer-config.md").write_text(layer_config, encoding="utf-8")
    return hub


def _add_doc(hub: Path, rel: str, body: str = "# doc\n") -> None:
    p = hub / "CONTEXT" / "reference-docs" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


# ── PREFIX parsing ────────────────────────────────────────────────────────────

def test_read_prefix_legacy_single(tmp_path):
    hub = _make_hub(tmp_path, "PREFIX: G2\n")
    assert c.read_active_prefix(hub) == "G2"
    assert c.read_prefix(hub) == "G2"
    assert c.read_prefixes(hub) == ["G2"]


def test_active_prefix_takes_precedence(tmp_path):
    cfg = "PREFIX: G2\nACTIVE_PREFIX: PG2\n"
    hub = _make_hub(tmp_path, cfg)
    assert c.read_active_prefix(hub) == "PG2"
    assert c.read_prefix(hub) == "PG2"  # wrapper reflects ACTIVE too


def test_read_prefixes_block(tmp_path):
    cfg = (
        "PREFIXES:\n"
        "  - id: G2\n"
        "    label: private\n"
        "  - id: PG2\n"
        "    label: public\n"
        "ACTIVE_PREFIX: G2\n"
    )
    hub = _make_hub(tmp_path, cfg)
    assert c.read_prefixes(hub) == ["G2", "PG2"]
    assert c.read_active_prefix(hub) == "G2"


def test_missing_prefix_exits(tmp_path):
    hub = _make_hub(tmp_path, "# no prefix here\n")
    with pytest.raises(SystemExit):
        c.read_active_prefix(hub)


# ── Dual-path source discovery ────────────────────────────────────────────────

def test_discover_legacy_flat(tmp_path):
    hub = _make_hub(tmp_path, "PREFIX: G2\n")
    _add_doc(hub, "B/G2-B-001.md")
    _add_doc(hub, "B/README.md")  # should be excluded
    got = c.discover_layer_sources(hub, "G2", "B")
    assert [p.name for p in got] == ["G2-B-001.md"]


def test_discover_nested_prefix(tmp_path):
    hub = _make_hub(tmp_path, "ACTIVE_PREFIX: PG2\n")
    _add_doc(hub, "PG2/B/PG2-B-001.md")
    got = c.discover_layer_sources(hub, "PG2", "B")
    assert [p.name for p in got] == ["PG2-B-001.md"]


def test_nested_takes_precedence_over_flat(tmp_path):
    hub = _make_hub(tmp_path, "ACTIVE_PREFIX: G2\n")
    _add_doc(hub, "B/legacy.md")          # legacy flat
    _add_doc(hub, "G2/B/nested.md")       # new nested
    got = c.discover_layer_sources(hub, "G2", "B")
    assert [p.name for p in got] == ["nested.md"]  # nested takes precedence


def test_discover_missing_returns_empty(tmp_path):
    hub = _make_hub(tmp_path, "PREFIX: G2\n")
    assert c.discover_layer_sources(hub, "G2", "C") == []


def test_discover_b_sources_wrapper_exits_when_empty(tmp_path):
    hub = _make_hub(tmp_path, "PREFIX: G2\n")
    with pytest.raises(SystemExit):
        c.discover_b_sources(hub)


def test_discover_b_sources_wrapper_ok(tmp_path):
    hub = _make_hub(tmp_path, "PREFIX: G2\n")
    _add_doc(hub, "B/G2-B-001.md")
    got = c.discover_b_sources(hub)
    assert [p.name for p in got] == ["G2-B-001.md"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
