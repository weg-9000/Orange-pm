#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for _embed_config — single source of truth for the embedding model (ingest = search match)."""
from __future__ import annotations

import importlib

import pytest

import _embed_config as ec


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ORANGE_EMBED_MODEL", raising=False)
    monkeypatch.delenv("ORANGE_EMBED_DIM", raising=False)
    yield


def test_default_is_bge_m3_1024():
    spec = ec.resolve_model(None)
    assert spec["key"] == "bge-m3" and spec["dim"] == 1024 and spec["provider"] == "st"


def test_legacy_local_maps_to_default():
    assert ec.resolve_model("local")["key"] == ec.DEFAULT_MODEL


def test_legacy_anthropic_maps_to_voyage():
    spec = ec.resolve_model("anthropic")
    assert spec["key"] == "voyage-3" and spec["provider"] == "voyage" and spec["dim"] == 1024


def test_env_overrides_cli(monkeypatch):
    monkeypatch.setenv("ORANGE_EMBED_MODEL", "e5-large")
    spec = ec.resolve_model("anthropic")   # env takes priority
    assert spec["key"] == "e5-large" and spec["dim"] == 1024


def test_unknown_model_is_st_with_env_dim(monkeypatch):
    monkeypatch.setenv("ORANGE_EMBED_MODEL", "intfloat/e5-base-v2")
    monkeypatch.setenv("ORANGE_EMBED_DIM", "768")
    spec = ec.resolve_model(None)
    assert spec["provider"] == "st" and spec["name"] == "intfloat/e5-base-v2" and spec["dim"] == 768


def test_all_registry_entries_have_dim():
    for key, spec in ec.EMBED_MODELS.items():
        assert spec["dim"] > 0 and spec["provider"] in ("st", "voyage")


def test_qwen_embedding_available():
    assert "qwen3-0.6b" in ec.EMBED_MODELS  # Qwen embedding (not chat) local option


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
