#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared config for inference (chat) model routing — single source of truth for role label -> provider/endpoint.

Purpose (Tier 3 — model-agnostic / BYOK):
    Decide in one place **which inference backend** a role label
    (advisor/direct/batch) used by skills gets routed to. Beyond Claude
    (Anthropic), it can route to local vLLM/Ollama, OpenAI, Bedrock, etc.,
    removing the "must use Claude" constraint (BYOK).

    Warning: this module **only resolves routing config** (same philosophy as
    the embedding _embed_config). It does not make the actual call — the
    call is made by the skill runner/adapter, which receives the resolved spec.

Role labels (1:1 with the routing strategy in CLAUDE.md):
    advisor : complex judgment (cluster discovery, graph design, policy
              conflicts) — frontier-tier
    direct  : general conversation/routing, medium complexity
    batch   : repetitive/low-cost work like index classification, summarizing
              — fine to downgrade to a small local model

Selection priority (higher wins):
    1) env  ORANGE_MODEL_<ROLE>  ("provider:model" or model alone)
    2) tenant-config.yml  model_routing.<role>  (per-tenant BYOK)
    3) DEFAULTS

provider types:
    anthropic : Anthropic API (ANTHROPIC_API_KEY)            — cloud, default
    openai    : OpenAI API (OPENAI_API_KEY)                  — cloud
    vllm      : OpenAI-compatible local server (endpoint, no key needed) — self-hosted, $0 margin
    ollama    : Ollama local (endpoint, no key needed)       — self-hosted, $0 margin
    bedrock   : AWS Bedrock (AWS credentials)                — cloud

env:
    ORANGE_MODEL_ADVISOR / _DIRECT / _BATCH : per-role override
        e.g. "vllm:qwen3-32b", "ollama:qwen3:4b", "claude-opus-4-8"
    ORANGE_MODEL_ENDPOINT_VLLM   : default endpoint for the vllm provider
    ORANGE_MODEL_ENDPOINT_OLLAMA : default endpoint for the ollama provider
"""
from __future__ import annotations

import os
from typing import Any

ROLES = ("advisor", "direct", "batch")

# Role -> default spec. A model with no provider specified is assumed to be anthropic (backward compat).
DEFAULTS: dict[str, dict] = {
    "advisor": {"provider": "anthropic", "model": "claude-opus-4-8"},
    "direct": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    "batch": {"provider": "anthropic", "model": "claude-haiku-4-5"},
}

# Default endpoint per provider (local). Overridable via env.
_LOCAL_ENDPOINTS = {
    "vllm": os.environ.get("ORANGE_MODEL_ENDPOINT_VLLM", "http://localhost:8000/v1"),
    "ollama": os.environ.get("ORANGE_MODEL_ENDPOINT_OLLAMA", "http://localhost:11434/v1"),
}

# Providers that need no key (self-hosted) — the BYOK/low-cost path.
LOCAL_PROVIDERS = frozenset({"vllm", "ollama"})

_KNOWN_PROVIDERS = frozenset({"anthropic", "openai", "vllm", "ollama", "bedrock"})


def _parse_spec(raw: str) -> dict:
    """Parse a "provider:model" or bare "model" string into a spec dict.

    If provider is omitted, defaults to anthropic (backward compat). Local
    providers get their default endpoint attached.
    """
    raw = raw.strip()
    if ":" in raw:
        head, _, tail = raw.partition(":")
        if head in _KNOWN_PROVIDERS:
            provider, model = head, tail.strip()
        else:
            # A colon that's part of the model name itself (e.g. "claude-opus:...")
            # — treat as provider not specified.
            provider, model = "anthropic", raw
    else:
        provider, model = "anthropic", raw
    spec: dict[str, Any] = {"provider": provider, "model": model}
    if provider in _LOCAL_ENDPOINTS:
        spec["endpoint"] = _LOCAL_ENDPOINTS[provider]
    return spec


def _normalize(spec: dict) -> dict:
    """Normalize a dict-form routing config (fills in local provider endpoint)."""
    out = dict(spec)
    provider = out.get("provider", "anthropic")
    out["provider"] = provider
    if provider in _LOCAL_ENDPOINTS and "endpoint" not in out:
        out["endpoint"] = _LOCAL_ENDPOINTS[provider]
    return out


def resolve_role(role: str, tenant_config: dict | None = None) -> dict:
    """Resolve a role label into an execution spec: {role, provider, model, endpoint?, local}.

    Priority: env ORANGE_MODEL_<ROLE> > tenant_config.model_routing.<role> > DEFAULTS.
    `local` = True means a key-free self-hosted backend (low-cost/BYOK).
    """
    if role not in ROLES:
        raise ValueError(f"unknown role: {role!r} (expected one of {ROLES})")

    env_val = os.environ.get(f"ORANGE_MODEL_{role.upper()}")
    if env_val:
        spec = _parse_spec(env_val)
    elif tenant_config and isinstance(tenant_config.get("model_routing"), dict) \
            and role in tenant_config["model_routing"]:
        routing = tenant_config["model_routing"][role]
        spec = _parse_spec(routing) if isinstance(routing, str) else _normalize(routing)
    else:
        spec = _normalize(DEFAULTS[role])

    spec["role"] = role
    spec["local"] = spec["provider"] in LOCAL_PROVIDERS
    return spec


def resolve_all(tenant_config: dict | None = None) -> dict[str, dict]:
    """Resolve all three roles (for governance viz / diagnostics)."""
    return {r: resolve_role(r, tenant_config) for r in ROLES}


def requires_api_key(spec: dict) -> str | None:
    """Name of the env key the spec requires (None if none) — self-hosted is None."""
    return {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
    }.get(spec.get("provider", ""))


if __name__ == "__main__":  # quick diagnostic
    import json

    print(json.dumps(resolve_all(), ensure_ascii=False, indent=2))
