#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for the new build_a_index / build_c_index index builders (Phase 1)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import build_a_index as a
import build_c_index as c


# ── build_a_index: term-extraction heuristics ───────────────────────────────────────────

def test_extract_terms_from_table():
    md = (
        "# Terminology Rules\n\n"
        "| Term | Definition |\n"
        "|---|---|\n"
        "| Instance | VM-unit resource |\n"
        "| Project | resource bundle |\n"
    )
    terms = a.extract_terms(md, "G2/A/x.md")
    assert "Instance" in terms
    assert terms["Instance"]["def"] == "VM-unit resource"
    assert terms["Project"]["file"] == "G2/A/x.md"
    assert terms["Instance"]["line"] >= 1


def test_extract_terms_from_bold_def():
    md = "- **OTP**: one-time password\n**SSO** — unified authentication\n"
    terms = a.extract_terms(md, "f.md")
    assert terms["OTP"]["def"] == "one-time password"
    assert terms["SSO"]["def"] == "unified authentication"


def test_extract_terms_ignores_non_glossary_table():
    md = "| Item | Value |\n|---|---|\n| Price | 1000 |\n"
    # If the header has no term/definition hints, it isn't treated as a glossary.
    assert a.extract_terms(md, "f.md") == {}


def test_build_a_index_writes_json(tmp_path):
    hub = tmp_path / "Hub"
    (hub / "CONTEXT" / "reference-docs" / "G2" / "A").mkdir(parents=True)
    (hub / "CONTEXT" / "layer-config.md").write_text("ACTIVE_PREFIX: G2\n", encoding="utf-8")
    (hub / "CONTEXT" / "reference-docs" / "G2" / "A" / "terms.md").write_text(
        "| Term | Definition |\n|---|---|\n| Instance | VM |\n", encoding="utf-8"
    )
    assert a.build(hub) == 0
    out = hub / "CONTEXT" / ".template-cache" / "G2-a-terms-index.json"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["_meta"]["prefix"] == "G2"
    assert "Instance" in data["terms"]


# ── build_c_index: master index ───────────────────────────────────────────────

def _hub_with_prefixes(tmp_path: Path) -> Path:
    hub = tmp_path / "Hub"
    (hub / "CONTEXT").mkdir(parents=True)
    cfg = (
        "PREFIXES:\n"
        "  - id: G2\n"
        "    label: Private\n"
        "  - id: PG2\n"
        "    label: Public\n"
        "ACTIVE_PREFIX: G2\n"
    )
    (hub / "CONTEXT" / "layer-config.md").write_text(cfg, encoding="utf-8")
    return hub


def test_build_c_index_empty(tmp_path):
    hub = _hub_with_prefixes(tmp_path)
    assert c.build(hub) == 0
    data = json.loads(
        (hub / "CONTEXT" / ".template-cache" / "c-master-index.json").read_text(encoding="utf-8")
    )
    assert data["_meta"]["total_services"] == 0
    assert set(data["prefixes"]) == {"G2", "PG2"}
    assert data["prefixes"]["G2"]["label"] == "Private"


def test_build_c_index_with_service(tmp_path):
    hub = _hub_with_prefixes(tmp_path)
    svc = hub / "CONTEXT" / "reference-docs" / "G2" / "C" / "dbaas"
    svc.mkdir(parents=True)
    (svc / "metadata.json").write_text(
        json.dumps({"label": "DBaaS", "docs": ["d1", "d2"], "status": "archived",
                    "archived_at": "2026-03"}),
        encoding="utf-8",
    )
    assert c.build(hub) == 0
    data = json.loads(
        (hub / "CONTEXT" / ".template-cache" / "c-master-index.json").read_text(encoding="utf-8")
    )
    assert data["_meta"]["total_services"] == 1
    svc_meta = data["prefixes"]["G2"]["services"]["dbaas"]
    assert svc_meta["label"] == "DBaaS"
    assert svc_meta["docs"] == ["d1", "d2"]


def test_build_c_index_docs_inferred_from_md(tmp_path):
    hub = _hub_with_prefixes(tmp_path)
    svc = hub / "CONTEXT" / "reference-docs" / "G2" / "C" / "mail"
    svc.mkdir(parents=True)
    (svc / "d1-req.md").write_text("# req\n", encoding="utf-8")
    (svc / "README.md").write_text("# readme\n", encoding="utf-8")  # excluded
    assert c.build(hub) == 0
    data = json.loads(
        (hub / "CONTEXT" / ".template-cache" / "c-master-index.json").read_text(encoding="utf-8")
    )
    assert data["prefixes"]["G2"]["services"]["mail"]["docs"] == ["d1-req"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
