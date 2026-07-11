#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tenant_emit / policy_emit governance-adapter regression tests (Phase 6)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import tenant_emit
import policy_emit


def _platform(tmp_path: Path) -> Path:
    hub = tmp_path / "Platform"
    hub.mkdir()
    (hub / "tenant-config.yml").write_text(
        "active_tenant: default\n\ntenants:\n"
        '  - id: default\n    label: Default\n    root: "."\n    gate_preset: standard\n'
        "  - id: acme\n    label: Acme\n    root: tenants/acme\n    gate_preset: strict\n",
        encoding="utf-8")
    return hub


def _tenant(tmp_path: Path) -> Path:
    hub = tmp_path / "Tenant"
    ref = hub / "CONTEXT" / "reference-docs" / "G2"
    (ref / "A").mkdir(parents=True)
    (ref / "B").mkdir(parents=True)
    (ref / "A" / "G2-A-001.md").write_text("# Glossary\n", encoding="utf-8")
    (ref / "B" / "G2-B-001.md").write_text("# Policy\n", encoding="utf-8")
    (ref / "B" / "README.md").write_text("# readme\n", encoding="utf-8")  # excluded
    (hub / "CONTEXT" / "gates").mkdir(parents=True)
    (hub / "CONTEXT" / "gates" / "_active-preset.txt").write_text("strict\n", encoding="utf-8")
    (hub / "CONTEXT" / "installed-packs.json").write_text(
        json.dumps([{"name": "p1", "version": "1.0.0", "prefixes": ["G2"]}]), encoding="utf-8")
    return hub


# ── tenant_emit ────────────────────────────────────────────────────────────────

def test_tenant_emit_transform(tmp_path):
    hub = _platform(tmp_path)
    out = tenant_emit.transform(str(hub))
    assert out["kind"] == "tenants" and out["activeTenant"] == "default"
    ids = {t["id"] for t in out["tenants"]}
    assert ids == {"default", "acme"}
    acme = next(t for t in out["tenants"] if t["id"] == "acme")
    assert acme["root"] == "tenants/acme" and acme["gatePreset"] == "strict"


# ── policy_emit ────────────────────────────────────────────────────────────────

def test_policy_emit_counts_and_packs(tmp_path):
    hub = _tenant(tmp_path)
    out = policy_emit.transform(str(hub))
    assert out["kind"] == "policy-packs" and out["gatePreset"] == "strict"
    g2 = next(p for p in out["prefixes"] if p["id"] == "G2")
    assert g2["a"] == 1 and g2["b"] == 1 and g2["c"] == 0   # README excluded
    assert out["installedPacks"][0]["name"] == "p1"


def test_policy_emit_empty_tenant(tmp_path):
    hub = tmp_path / "Empty"
    (hub / "CONTEXT").mkdir(parents=True)
    out = policy_emit.transform(str(hub))
    assert out["prefixes"] == [] and out["installedPacks"] == []
    assert out["gatePreset"] == "standard"   # default value when no marker


def test_policy_emit_finds_registry(tmp_path):
    # discover platform/packs/registry.json from an ancestor of the tenant
    platform = tmp_path / "P"
    (platform / "packs").mkdir(parents=True)
    (platform / "packs" / "registry.json").write_text(
        json.dumps({"policy_packs": [{"name": "example-policy-pack", "version": "1.0.0"}]}),
        encoding="utf-8")
    tenant = platform / "tenants" / "acme"
    (tenant / "CONTEXT").mkdir(parents=True)
    out = policy_emit.transform(str(tenant))
    assert any(p["name"] == "example-policy-pack" for p in out["availablePacks"])


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
