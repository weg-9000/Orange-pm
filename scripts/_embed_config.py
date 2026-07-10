#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""임베딩 모델 공용 설정 — 적재(embed_pipeline)·검색(context_search) 단일 출처.

목적:
    "어떤 임베딩 모델을 쓰는가"를 한 곳에서 결정해, 적재 시점과 검색 시점이
    **항상 같은 모델·같은 차원**을 쓰도록 보장한다(불일치 방지). 모델 차원으로
    Neo4j 벡터 인덱스 차원도 자동 결정된다.

    ⚠ 임베딩 모델 = '텍스트→벡터' 전용 모델. 챗/코딩 LLM(Claude/Qwen-chat 등)이 아니다.
    'st' provider = sentence-transformers 로 **로컬 실행**(키 불요, 첫 실행 시 자동 다운로드).
    'voyage' provider = Voyage AI **클라우드 API**(VOYAGE_API_KEY 필요).

선택 우선순위:
    1) env ORANGE_EMBED_MODEL  (별칭 키 또는 임의 HF 모델명)
    2) CLI --model (local→기본 ST / anthropic→voyage-3, 하위호환)
    3) DEFAULT_MODEL

env:
    ORANGE_EMBED_MODEL : 별칭(bge-m3 등) 또는 임의 HF 모델 경로(예: "intfloat/e5-base")
    ORANGE_EMBED_DIM   : 미등록 모델 사용 시 차원 명시(기본 768)
    VOYAGE_API_KEY    : voyage provider 사용 시
"""
from __future__ import annotations

import os

# 별칭 → {provider, name(모델 식별자), dim}. 전부 로컬(st) — voyage 만 클라우드.
EMBED_MODELS: dict[str, dict] = {
    "bge-m3":     {"provider": "st", "name": "BAAI/bge-m3", "dim": 1024},
    "e5-large":   {"provider": "st", "name": "intfloat/multilingual-e5-large", "dim": 1024},
    "qwen3-0.6b": {"provider": "st", "name": "Qwen/Qwen3-Embedding-0.6B", "dim": 1024},
    "mpnet":      {"provider": "st", "name": "paraphrase-multilingual-mpnet-base-v2", "dim": 768},
    "voyage-3":   {"provider": "voyage", "name": "voyage-3", "dim": 1024},
}

DEFAULT_MODEL = "bge-m3"   # 로컬·다국어(한국어 우수)·1024차원. CPU 실행 가능.

# CLI --model 하위호환 매핑
_LEGACY = {"local": DEFAULT_MODEL, "anthropic": "voyage-3"}


def resolve_model(cli_model: str | None = None) -> dict:
    """사용할 임베딩 spec 반환: {key, provider, name, dim}.

    미등록 키(임의 HF 모델명)는 st provider 로 간주하고 dim 은 ORANGE_EMBED_DIM(기본 768).
    """
    env_key = os.environ.get("ORANGE_EMBED_MODEL")
    key = env_key or _LEGACY.get(cli_model or "", cli_model) or DEFAULT_MODEL
    spec = EMBED_MODELS.get(key)
    if spec is None:
        dim = int(os.environ.get("ORANGE_EMBED_DIM", "768"))
        return {"key": key, "provider": "st", "name": key, "dim": dim}
    return {"key": key, **spec}
