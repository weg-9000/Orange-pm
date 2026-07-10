#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reference_submodule 회귀 테스트 — 명령 구성(URL 사용자 입력)."""
from __future__ import annotations

import reference_submodule as rs


def test_build_add_cmd_with_branch():
    cmd = rs.build_add_cmd("git@gitlab:planning/policy.git", "CONTEXT/reference-docs", "main")
    assert cmd == ["git", "submodule", "add", "-b", "main",
                   "git@gitlab:planning/policy.git", "CONTEXT/reference-docs"]


def test_build_add_cmd_without_branch():
    cmd = rs.build_add_cmd("url", "p", None)
    assert cmd == ["git", "submodule", "add", "url", "p"]


def test_build_update_cmd():
    assert rs.build_update_cmd(False) == ["git", "submodule", "update", "--init", "--recursive"]
    assert rs.build_update_cmd(True)[-1] == "--remote"


def test_prompt_url_uses_given():
    assert rs._prompt_url("  git@x/y.git ") == "git@x/y.git"  # 인자 우선·trim


def test_prompt_url_blank_returns_empty(monkeypatch):
    # 비대화형(EOF) 환경에서 빈 입력 → 빈 문자열(상위에서 오류 처리)
    monkeypatch.setattr("builtins.input", lambda *a, **k: (_ for _ in ()).throw(EOFError()))
    assert rs._prompt_url(None) == ""


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
