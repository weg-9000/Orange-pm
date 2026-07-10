#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_a_index / build_c_index 신규 인덱스 빌더 회귀 테스트 (Phase 1)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import build_a_index as a
import build_c_index as c


# ── build_a_index: 용어 추출 휴리스틱 ───────────────────────────────────────────

def test_extract_terms_from_table():
    md = (
        "# 용어 규칙\n\n"
        "| 용어 | 정의 |\n"
        "|---|---|\n"
        "| 인스턴스 | VM 단위 자원 |\n"
        "| 프로젝트 | 자원 묶음 |\n"
    )
    terms = a.extract_terms(md, "G2/A/x.md")
    assert "인스턴스" in terms
    assert terms["인스턴스"]["def"] == "VM 단위 자원"
    assert terms["프로젝트"]["file"] == "G2/A/x.md"
    assert terms["인스턴스"]["line"] >= 1


def test_extract_terms_from_bold_def():
    md = "- **OTP**: 일회용 비밀번호\n**SSO** — 통합 인증\n"
    terms = a.extract_terms(md, "f.md")
    assert terms["OTP"]["def"] == "일회용 비밀번호"
    assert terms["SSO"]["def"] == "통합 인증"


def test_extract_terms_ignores_non_glossary_table():
    md = "| 항목 | 값 |\n|---|---|\n| 가격 | 1000 |\n"
    # 헤더에 용어/정의 힌트가 없으면 용어로 보지 않는다.
    assert a.extract_terms(md, "f.md") == {}


def test_build_a_index_writes_json(tmp_path):
    hub = tmp_path / "Hub"
    (hub / "CONTEXT" / "reference-docs" / "G2" / "A").mkdir(parents=True)
    (hub / "CONTEXT" / "layer-config.md").write_text("ACTIVE_PREFIX: G2\n", encoding="utf-8")
    (hub / "CONTEXT" / "reference-docs" / "G2" / "A" / "terms.md").write_text(
        "| 용어 | 정의 |\n|---|---|\n| 인스턴스 | VM |\n", encoding="utf-8"
    )
    assert a.build(hub) == 0
    out = hub / "CONTEXT" / ".template-cache" / "G2-a-terms-index.json"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["_meta"]["prefix"] == "G2"
    assert "인스턴스" in data["terms"]


# ── build_c_index: 마스터 인덱스 ───────────────────────────────────────────────

def _hub_with_prefixes(tmp_path: Path) -> Path:
    hub = tmp_path / "Hub"
    (hub / "CONTEXT").mkdir(parents=True)
    cfg = (
        "PREFIXES:\n"
        "  - id: G2\n"
        "    label: 민간\n"
        "  - id: PG2\n"
        "    label: 공공\n"
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
    assert data["prefixes"]["G2"]["label"] == "민간"


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
    (svc / "README.md").write_text("# readme\n", encoding="utf-8")  # 제외
    assert c.build(hub) == 0
    data = json.loads(
        (hub / "CONTEXT" / ".template-cache" / "c-master-index.json").read_text(encoding="utf-8")
    )
    assert data["prefixes"]["G2"]["services"]["mail"]["docs"] == ["d1-req"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
