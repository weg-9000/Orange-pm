#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""추론(챗) 모델 라우팅 공용 설정 — 역할 라벨 → provider/endpoint 단일 출처.

목적 (Tier 3 — 모델 비종속 / BYOK):
    스킬이 사용하는 역할 라벨(advisor/direct/batch)을 **어떤 추론 백엔드로 보낼지**
    한 곳에서 결정한다. Claude(Anthropic)뿐 아니라 로컬 vLLM/Ollama, OpenAI,
    Bedrock 등으로 라우팅할 수 있어 "Claude 제공 의무"를 제거(BYOK)한다.

    ⚠ 이 모듈은 **라우팅 설정만 해소**한다(임베딩 _embed_config 와 동일 철학).
       실제 호출은 하지 않는다 — 호출은 스킬 실행기/어댑터가 spec 을 받아 수행.

역할 라벨 (CLAUDE.md 라우팅 전략과 1:1):
    advisor : 복잡 판단(클러스터 발견·그래프 설계·정책 충돌) — 프론티어급
    direct  : 일반 대화·라우팅·중간 복잡도
    batch   : 인덱스 분류·요약 등 반복·저비용 — 로컬 소형으로 강등 적합

선택 우선순위 (높을수록 우선):
    1) env  ORANGE_MODEL_<ROLE>  ("provider:model" 또는 model 단독)
    2) tenant-config.yml  model_routing.<role>  (테넌트별 BYOK)
    3) DEFAULTS

provider 종류:
    anthropic : Anthropic API (ANTHROPIC_API_KEY)            — 클라우드, 기본
    openai    : OpenAI API (OPENAI_API_KEY)                  — 클라우드
    vllm      : OpenAI 호환 로컬 서버 (endpoint, 키 불요)    — 셀프호스트, $0 마진
    ollama    : Ollama 로컬 (endpoint, 키 불요)              — 셀프호스트, $0 마진
    bedrock   : AWS Bedrock (AWS 자격증명)                   — 클라우드

env:
    ORANGE_MODEL_ADVISOR / _DIRECT / _BATCH : 역할별 오버라이드
        예) "vllm:qwen3-32b", "ollama:qwen3:4b", "claude-opus-4-8"
    ORANGE_MODEL_ENDPOINT_VLLM   : vllm provider 기본 엔드포인트
    ORANGE_MODEL_ENDPOINT_OLLAMA : ollama provider 기본 엔드포인트
"""
from __future__ import annotations

import os
from typing import Any

ROLES = ("advisor", "direct", "batch")

# 역할 → 기본 spec. provider 미명시 모델은 anthropic 으로 간주(하위호환).
DEFAULTS: dict[str, dict] = {
    "advisor": {"provider": "anthropic", "model": "claude-opus-4-8"},
    "direct": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    "batch": {"provider": "anthropic", "model": "claude-haiku-4-5"},
}

# provider 별 기본 엔드포인트(로컬). env 로 덮어쓴다.
_LOCAL_ENDPOINTS = {
    "vllm": os.environ.get("ORANGE_MODEL_ENDPOINT_VLLM", "http://localhost:8000/v1"),
    "ollama": os.environ.get("ORANGE_MODEL_ENDPOINT_OLLAMA", "http://localhost:11434/v1"),
}

# 키가 필요 없는(셀프호스트) provider — BYOK/저비용 경로.
LOCAL_PROVIDERS = frozenset({"vllm", "ollama"})

_KNOWN_PROVIDERS = frozenset({"anthropic", "openai", "vllm", "ollama", "bedrock"})


def _parse_spec(raw: str) -> dict:
    """"provider:model" 또는 "model" 문자열을 spec dict 로 파싱.

    provider 가 생략되면 anthropic(하위호환). 로컬 provider 는 기본 엔드포인트 부착.
    """
    raw = raw.strip()
    if ":" in raw:
        head, _, tail = raw.partition(":")
        if head in _KNOWN_PROVIDERS:
            provider, model = head, tail.strip()
        else:
            # "claude-opus:..." 같은 모델명 자체의 콜론 — provider 미지정으로 간주
            provider, model = "anthropic", raw
    else:
        provider, model = "anthropic", raw
    spec: dict[str, Any] = {"provider": provider, "model": model}
    if provider in _LOCAL_ENDPOINTS:
        spec["endpoint"] = _LOCAL_ENDPOINTS[provider]
    return spec


def _normalize(spec: dict) -> dict:
    """dict 형태 라우팅 설정을 표준화(로컬 provider 엔드포인트 보강)."""
    out = dict(spec)
    provider = out.get("provider", "anthropic")
    out["provider"] = provider
    if provider in _LOCAL_ENDPOINTS and "endpoint" not in out:
        out["endpoint"] = _LOCAL_ENDPOINTS[provider]
    return out


def resolve_role(role: str, tenant_config: dict | None = None) -> dict:
    """역할 라벨을 실행 spec 으로 해소: {role, provider, model, endpoint?, local}.

    우선순위: env ORANGE_MODEL_<ROLE> > tenant_config.model_routing.<role> > DEFAULTS.
    `local` = True 면 키 불요 셀프호스트 백엔드(저비용/BYOK).
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
    """세 역할 전부 해소(거버넌스 viz·진단용)."""
    return {r: resolve_role(r, tenant_config) for r in ROLES}


def requires_api_key(spec: dict) -> str | None:
    """spec 이 요구하는 env 키 이름(없으면 None) — 셀프호스트는 None."""
    return {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
    }.get(spec.get("provider", ""))


if __name__ == "__main__":  # 간이 진단
    import json

    print(json.dumps(resolve_all(), ensure_ascii=False, indent=2))
