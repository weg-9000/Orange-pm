#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_model_config regression tests — role label -> provider/endpoint routing (BYOK)."""
from __future__ import annotations

import pytest

import _model_config as mc


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for r in mc.ROLES:
        monkeypatch.delenv(f"ORANGE_MODEL_{r.upper()}", raising=False)
    monkeypatch.delenv("ORANGE_MODEL_ENDPOINT_VLLM", raising=False)
    monkeypatch.delenv("ORANGE_MODEL_ENDPOINT_OLLAMA", raising=False)
    yield


def test_defaults_are_anthropic_tiers():
    assert mc.resolve_role("advisor")["model"] == "claude-opus-4-8"
    assert mc.resolve_role("direct")["model"] == "claude-sonnet-4-6"
    assert mc.resolve_role("batch")["model"] == "claude-haiku-4-5"
    assert all(mc.resolve_role(r)["provider"] == "anthropic" for r in mc.ROLES)
    assert all(mc.resolve_role(r)["local"] is False for r in mc.ROLES)


def test_unknown_role_raises():
    with pytest.raises(ValueError):
        mc.resolve_role("nope")


def test_env_override_provider_colon_model(monkeypatch):
    monkeypatch.setenv("ORANGE_MODEL_BATCH", "ollama:qwen3:4b")
    spec = mc.resolve_role("batch")
    assert spec["provider"] == "ollama"
    assert spec["model"] == "qwen3:4b"   # colon inside model name is preserved
    assert spec["local"] is True
    assert spec["endpoint"].endswith("/v1")


def test_env_override_bare_model_defaults_anthropic(monkeypatch):
    monkeypatch.setenv("ORANGE_MODEL_ADVISOR", "claude-fable-5")
    spec = mc.resolve_role("advisor")
    assert spec["provider"] == "anthropic" and spec["model"] == "claude-fable-5"


def test_tenant_config_dict_routing():
    tc = {"model_routing": {"advisor": {"provider": "vllm", "model": "qwen3-32b"}}}
    spec = mc.resolve_role("advisor", tc)
    assert spec["provider"] == "vllm" and spec["local"] is True
    assert "endpoint" in spec


def test_tenant_config_string_routing():
    tc = {"model_routing": {"batch": "ollama:llama3.2"}}
    spec = mc.resolve_role("batch", tc)
    assert spec["provider"] == "ollama" and spec["model"] == "llama3.2"


def test_env_beats_tenant_config(monkeypatch):
    monkeypatch.setenv("ORANGE_MODEL_DIRECT", "openai:gpt-4o-mini")
    tc = {"model_routing": {"direct": "vllm:qwen3-32b"}}
    spec = mc.resolve_role("direct", tc)
    assert spec["provider"] == "openai" and spec["model"] == "gpt-4o-mini"


def test_local_endpoint_env_override(monkeypatch):
    import importlib
    monkeypatch.setenv("ORANGE_MODEL_ENDPOINT_VLLM", "http://vm-internal:9000/v1")
    importlib.reload(mc)
    try:
        spec = mc.resolve_role("advisor", {"model_routing": {"advisor": "vllm:qwen3-32b"}})
        assert spec["endpoint"] == "http://vm-internal:9000/v1"
    finally:
        importlib.reload(mc)


def test_requires_api_key():
    assert mc.requires_api_key({"provider": "anthropic"}) == "ANTHROPIC_API_KEY"
    assert mc.requires_api_key({"provider": "openai"}) == "OPENAI_API_KEY"
    assert mc.requires_api_key({"provider": "vllm"}) is None
    assert mc.requires_api_key({"provider": "ollama"}) is None


def test_resolve_all_covers_roles():
    allr = mc.resolve_all()
    assert set(allr) == set(mc.ROLES)
