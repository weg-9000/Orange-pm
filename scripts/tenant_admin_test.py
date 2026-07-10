#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tenant_admin 회귀 테스트 — 멀티테넌시 생성/격리 (Phase 4)."""
from __future__ import annotations

from pathlib import Path

import pytest

import tenant_admin as ta


def _platform(tmp_path: Path) -> Path:
    """최소 플랫폼 hub: CONTEXT(+gates/_presets.yml) + tenant-config.yml."""
    hub = tmp_path / "Platform"
    ctx = hub / "CONTEXT"
    (ctx / "gates").mkdir(parents=True)
    (ctx / "reference-docs").mkdir(parents=True)
    (ctx / "layer-config.md").write_text("PREFIXES: []\n", encoding="utf-8")
    (ctx / "gates" / "_presets.yml").write_text(
        "presets:\n  standard:\n    gates:\n      - discovery-exit-gate\n"
        "  strict:\n    gates:\n      - discovery-exit-gate\n", encoding="utf-8")
    (hub / "tenant-config.yml").write_text(
        "active_tenant: default\n\ntenants:\n  - id: default\n    label: 기본\n"
        '    root: "."\n    gate_preset: standard\n', encoding="utf-8")
    return hub


def test_parse_registry_default(tmp_path):
    hub = _platform(tmp_path)
    reg = ta.parse_registry(hub)
    assert reg["active_tenant"] == "default"
    assert reg["tenants"][0]["id"] == "default"
    assert reg["tenants"][0]["root"] == "."


def test_list_preset_names(tmp_path):
    hub = _platform(tmp_path)
    assert set(ta.list_preset_names(hub)) == {"standard", "strict"}


def test_create_tenant_scaffolds_and_registers(tmp_path):
    hub = _platform(tmp_path)
    r = ta.create_tenant(hub, "acme", label="Acme", gate_preset="strict")
    assert r["status"] == "created" and r["root"] == "tenants/acme"
    # 격리된 CONTEXT 복사 확인
    assert (hub / "tenants/acme/CONTEXT/layer-config.md").exists()
    assert (hub / "tenants/acme/PROJECTS").is_dir()
    # 프리셋 마커
    assert (hub / "tenants/acme/CONTEXT/gates/_active-preset.txt").read_text(encoding="utf-8").strip() == "strict"
    # 레지스트리 등록
    reg = ta.parse_registry(hub)
    assert any(t["id"] == "acme" and t["root"] == "tenants/acme" for t in reg["tenants"])


def test_create_duplicate_rejected(tmp_path):
    hub = _platform(tmp_path)
    ta.create_tenant(hub, "acme")
    assert ta.create_tenant(hub, "acme")["status"] == "exists"


def test_create_bad_preset_rejected(tmp_path):
    hub = _platform(tmp_path)
    r = ta.create_tenant(hub, "acme", gate_preset="nope")
    assert r["status"] == "bad-preset" and "standard" in r["available"]


def test_tenant_root_resolution(tmp_path):
    hub = _platform(tmp_path)
    assert ta.tenant_root(hub, "default") == hub          # root "." → 플랫폼
    ta.create_tenant(hub, "acme")
    assert ta.tenant_root(hub, "acme") == hub / "tenants" / "acme"
    assert ta.tenant_root(hub, "ghost") is None


def test_isolation_between_tenants(tmp_path):
    hub = _platform(tmp_path)
    ta.create_tenant(hub, "a")
    ta.create_tenant(hub, "b")
    # a 에 데이터 추가 → b 에 영향 없음
    (hub / "tenants/a/CONTEXT/reference-docs/A-only.md").write_text("x", encoding="utf-8")
    assert (hub / "tenants/a/CONTEXT/reference-docs/A-only.md").exists()
    assert not (hub / "tenants/b/CONTEXT/reference-docs/A-only.md").exists()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
