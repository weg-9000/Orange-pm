#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""load_sample_tenant regression tests (multi-tenant SaaS — empty-default + sample loading)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import load_sample_tenant as lst


def _make_sample(tmp_path: Path) -> Path:
    s = tmp_path / "sample-tenant-x"
    (s / "reference-docs" / "G2" / "B").mkdir(parents=True)
    (s / "reference-docs" / "G2" / "A").mkdir(parents=True)
    (s / "reference-docs" / "PG2" / "B").mkdir(parents=True)
    (s / "reference-docs" / "G2" / "B" / "G2-B-001.md").write_text("# Policy\n", encoding="utf-8")
    (s / "reference-docs" / "G2" / "A" / "G2-A-001.md").write_text("# Glossary\n", encoding="utf-8")
    (s / "reference-docs" / "master-id-map.yml").write_text(
        "G2-A-001: G2-A-001\nG2-B-001: G2-B-001\n", encoding="utf-8")
    (s / "layer-config.md").write_text(
        "PREFIXES:\n  - id: G2\n    label: Private\n  - id: PG2\n    label: Public\n"
        "ACTIVE_PREFIX: G2\nPREFIX: G2\n", encoding="utf-8")
    (s / "tenant.json").write_text(json.dumps({
        "sample": "x", "active_prefix": "G2",
        "reference_docs": "reference-docs", "layer_config": "layer-config.md",
    }), encoding="utf-8")
    return s


def _empty_hub(tmp_path: Path) -> Path:
    hub = tmp_path / "Hub"
    (hub / "CONTEXT" / "reference-docs").mkdir(parents=True)
    (hub / "CONTEXT" / "layer-config.md").write_text("PREFIXES: []\n", encoding="utf-8")
    return hub


def test_load_copies_prefixes_and_replaces_config(tmp_path):
    sample = _make_sample(tmp_path)
    hub = _empty_hub(tmp_path)
    r = lst.load_tenant(hub, sample)
    assert sorted(r["copied_prefixes"]) == ["G2", "PG2"]
    assert r["map_entries_added"] == 2
    assert r["layer_config"] == "replaced"  # empty hub -> replaced with sample config
    # verify copy
    assert (hub / "CONTEXT/reference-docs/G2/B/G2-B-001.md").exists()
    # verify map merge
    mp = (hub / "CONTEXT/reference-docs/master-id-map.yml").read_text(encoding="utf-8")
    assert "G2-B-001" in mp


def test_load_is_nondestructive_without_force(tmp_path):
    sample = _make_sample(tmp_path)
    hub = _empty_hub(tmp_path)
    # existing G2 data present
    (hub / "CONTEXT/reference-docs/G2/B").mkdir(parents=True)
    (hub / "CONTEXT/reference-docs/G2/B/mine.md").write_text("# Mine\n", encoding="utf-8")
    r = lst.load_tenant(hub, sample)
    assert "G2" in r["skipped_prefixes"]      # existing G2 preserved
    assert "PG2" in r["copied_prefixes"]      # only new copied
    assert (hub / "CONTEXT/reference-docs/G2/B/mine.md").exists()  # not overwritten


def test_map_merge_dedups(tmp_path):
    sample = _make_sample(tmp_path)
    hub = _empty_hub(tmp_path)
    hub_map = hub / "CONTEXT/reference-docs/master-id-map.yml"
    hub_map.write_text("G2-A-001: existing-value\n", encoding="utf-8")
    added = lst._merge_master_id_map(sample / "reference-docs/master-id-map.yml", hub_map)
    assert added == 1  # G2-A-001 already exists -> only G2-B-001 added
    assert "existing-value" in hub_map.read_text(encoding="utf-8")  # existing preserved


def test_hub_prefixes_empty_detection(tmp_path):
    hub = _empty_hub(tmp_path)
    assert lst._hub_prefixes_empty(hub / "CONTEXT/layer-config.md") is True
    (hub / "CONTEXT/layer-config.md").write_text(
        "PREFIXES:\n  - id: G2\n    label: x\n", encoding="utf-8")
    assert lst._hub_prefixes_empty(hub / "CONTEXT/layer-config.md") is False


def test_resolve_sample_dir_by_name(tmp_path):
    # search hub_root.parent/examples/sample-tenant-foo
    (tmp_path / "examples" / "sample-tenant-foo").mkdir(parents=True)
    hub = tmp_path / "Hub"
    (hub).mkdir()
    got = lst._resolve_sample_dir(hub, "foo", None)
    assert got == tmp_path / "examples" / "sample-tenant-foo"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
