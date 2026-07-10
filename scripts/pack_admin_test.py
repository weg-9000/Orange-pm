#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pack_admin 회귀 테스트 — 정책팩 패키징/설치/조회 (Phase 5)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import pack_admin as pa


def _make_pack(packs: Path, name="p1") -> Path:
    d = packs / name
    (d / "reference-docs" / "EX" / "B").mkdir(parents=True)
    (d / "reference-docs" / "EX" / "A").mkdir(parents=True)
    (d / "reference-docs" / "EX" / "B" / "EX-B-001.md").write_text("# 정책\n", encoding="utf-8")
    (d / "reference-docs" / "EX" / "A" / "EX-A-001.md").write_text("# 용어\n", encoding="utf-8")
    (d / "reference-docs" / "master-id-map.yml").write_text(
        "EX-A-001: EX-A-001\nEX-B-001: EX-B-001\n", encoding="utf-8")
    (d / "pack.json").write_text(json.dumps({
        "name": name, "version": "1.0.0", "type": "policy", "prefixes": ["EX"],
        "doc_count": 2,
    }), encoding="utf-8")
    return d


def _tenant(tmp_path: Path) -> Path:
    hub = tmp_path / "Tenant"
    (hub / "CONTEXT" / "reference-docs").mkdir(parents=True)
    return hub


def test_list_packs(tmp_path):
    packs = tmp_path / "packs"
    _make_pack(packs, "p1")
    _make_pack(packs, "p2")
    got = pa.list_packs(packs)
    assert {p["name"] for p in got} == {"p1", "p2"}


def test_install_merges_and_records(tmp_path):
    packs = tmp_path / "packs"
    pack = _make_pack(packs, "p1")
    hub = _tenant(tmp_path)
    r = pa.install(hub, pack)
    assert r["status"] == "installed" and r["copied"] == ["EX"]
    assert (hub / "CONTEXT/reference-docs/EX/B/EX-B-001.md").exists()
    mp = (hub / "CONTEXT/reference-docs/master-id-map.yml").read_text(encoding="utf-8")
    assert "EX-B-001" in mp
    rec = json.loads((hub / "CONTEXT/installed-packs.json").read_text(encoding="utf-8"))
    assert rec[0]["name"] == "p1" and rec[0]["version"] == "1.0.0"


def test_install_skips_existing_prefix_without_force(tmp_path):
    packs = tmp_path / "packs"
    pack = _make_pack(packs, "p1")
    hub = _tenant(tmp_path)
    (hub / "CONTEXT/reference-docs/EX/B").mkdir(parents=True)
    (hub / "CONTEXT/reference-docs/EX/B/mine.md").write_text("# 내것\n", encoding="utf-8")
    r = pa.install(hub, pack)
    assert r["skipped"] == ["EX"]
    assert (hub / "CONTEXT/reference-docs/EX/B/mine.md").exists()  # 보존


def test_install_dedups_record_on_reinstall(tmp_path):
    packs = tmp_path / "packs"
    pack = _make_pack(packs, "p1")
    hub = _tenant(tmp_path)
    pa.install(hub, pack)
    pa.install(hub, pack, force=True)
    rec = json.loads((hub / "CONTEXT/installed-packs.json").read_text(encoding="utf-8"))
    assert len([r for r in rec if r["name"] == "p1"]) == 1  # 중복 제거(최신화)


def test_package_from_tenant(tmp_path):
    hub = _tenant(tmp_path)
    (hub / "CONTEXT/reference-docs/G2/B").mkdir(parents=True)
    (hub / "CONTEXT/reference-docs/G2/B/G2-B-001.md").write_text("# p\n", encoding="utf-8")
    out = tmp_path / "out"
    r = pa.package(hub, "g2-pack", out, prefixes=["G2"], version="2.1.0")
    assert r["status"] == "packaged" and r["doc_count"] == 1
    man = json.loads((out / "g2-pack" / "pack.json").read_text(encoding="utf-8"))
    assert man["version"] == "2.1.0" and man["prefixes"] == ["G2"]
    assert (out / "g2-pack" / "reference-docs/G2/B/G2-B-001.md").exists()


def test_real_example_pack_present():
    # 저장소에 커밋된 example-policy-pack 형식 검증
    packs_dir = Path(__file__).resolve().parents[2] / "packs"
    if not packs_dir.is_dir():
        pytest.skip("packs/ 디렉토리 없음(모노레포 외 환경)")
    names = {p["name"] for p in pa.list_packs(packs_dir)}
    assert "example-policy-pack" in names


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
