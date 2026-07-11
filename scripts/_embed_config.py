#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared embedding model config — single source of truth for ingestion (embed_pipeline) and search (context_search).

Purpose:
    Decide "which embedding model to use" in one place, so that ingestion time
    and search time **always use the same model, same dimension**
    (prevents mismatch). The model dimension also auto-determines the
    Neo4j vector index dimension.

    Note: an embedding model is a dedicated "text -> vector" model, not a
    chat/coding LLM (Claude/Qwen-chat, etc.).
    'st' provider = sentence-transformers, runs **locally** (no key needed,
    auto-downloads on first run).
    'voyage' provider = Voyage AI **cloud API** (requires VOYAGE_API_KEY).

Selection priority:
    1) env ORANGE_EMBED_MODEL  (alias key or arbitrary HF model name)
    2) CLI --model (local -> default ST / anthropic -> voyage-3, legacy compat)
    3) DEFAULT_MODEL

env:
    ORANGE_EMBED_MODEL : alias (e.g. bge-m3) or arbitrary HF model path (e.g. "intfloat/e5-base")
    ORANGE_EMBED_DIM   : dimension to use for an unregistered model (default 768)
    VOYAGE_API_KEY    : required when using the voyage provider
"""
from __future__ import annotations

import os

# alias -> {provider, name(model identifier), dim}. All local (st) except voyage (cloud).
EMBED_MODELS: dict[str, dict] = {
    "bge-m3":     {"provider": "st", "name": "BAAI/bge-m3", "dim": 1024},
    "e5-large":   {"provider": "st", "name": "intfloat/multilingual-e5-large", "dim": 1024},
    "qwen3-0.6b": {"provider": "st", "name": "Qwen/Qwen3-Embedding-0.6B", "dim": 1024},
    "mpnet":      {"provider": "st", "name": "paraphrase-multilingual-mpnet-base-v2", "dim": 768},
    "voyage-3":   {"provider": "voyage", "name": "voyage-3", "dim": 1024},
}

DEFAULT_MODEL = "bge-m3"   # local, multilingual (strong Korean support), 1024-dim. CPU-capable.

# legacy mapping for CLI --model
_LEGACY = {"local": DEFAULT_MODEL, "anthropic": "voyage-3"}


def resolve_model(cli_model: str | None = None) -> dict:
    """Return the embedding spec to use: {key, provider, name, dim}.

    An unregistered key (arbitrary HF model name) is treated as the st
    provider, with dim from ORANGE_EMBED_DIM (default 768).
    """
    env_key = os.environ.get("ORANGE_EMBED_MODEL")
    key = env_key or _LEGACY.get(cli_model or "", cli_model) or DEFAULT_MODEL
    spec = EMBED_MODELS.get(key)
    if spec is None:
        dim = int(os.environ.get("ORANGE_EMBED_DIM", "768"))
        return {"key": key, "provider": "st", "name": key, "dim": dim}
    return {"key": key, **spec}
