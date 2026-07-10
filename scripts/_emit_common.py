#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""시각 인터페이스 어댑터 공통 유틸 (--emit-json 계약).

모든 *_emit.py 어댑터는 Hub 산출물(raw)을 docs/visual-interface/01-data-contract.md
의 정규화 JSON 으로 변환해 stdout 으로 1개 객체를 출력한다. 읽기 전용.

규약:
    python <kind>_emit.py --hub-root <Hub> --product <name> --emit-json
    python <kind>_emit.py --from-fixture <path> --emit-json   # 픽스처 패스스루
exit code: 0 정상 / 1 원본 없음(빈 골격) / 2 인자 오류
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

# 큐 헤더 파서 (build_ssot_status 와 동일 규칙)
HEADER_NUM = re.compile(r"(?<![A-Za-z/])([A-Z]+(?:/[A-Z]+)?)\s*:\s*(\d+)")


def content_version(obj: object) -> str:
    """내용 해시 → 멱등 갱신 키."""
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "sha1:" + hashlib.sha1(raw).hexdigest()[:12]


def make_parser(kind: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=f"{kind}_emit — {kind} 어댑터")
    p.add_argument("--hub-root", type=str, default=None)
    p.add_argument("--product", type=str, default=None)
    p.add_argument("--from-fixture", type=str, default=None)
    p.add_argument("--emit-json", action="store_true")
    return p


def product_dir(hub_root: str, product: str) -> Path:
    return Path(hub_root) / "PROJECTS" / product


def load_fixture(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def emit(obj: dict) -> int:
    """version 재계산 후 출력. version 은 kind/version 제외 본문 기준."""
    body = {k: v for k, v in obj.items() if k not in ("version", "generated_at")}
    obj["version"] = content_version(body)
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return 0


def parse_header_counts(text: str) -> dict[str, int]:
    """큐 파일 본문에서 헤더 라인(라벨:숫자)을 찾아 맵 반환."""
    for raw in text.splitlines()[:30]:
        if "**" in raw and re.search(r"\*\*[A-Z]+:", raw):
            out: dict[str, int] = {}
            for m in HEADER_NUM.finditer(raw):
                try:
                    out[m.group(1).upper()] = int(m.group(2))
                except ValueError:
                    continue
            return out
    return {}


def read_frontmatter(text: str) -> dict[str, str]:
    """--- ... --- frontmatter 의 단순 key: value 파싱(중첩 미지원)."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


def read_publication_mode(proj_dir: Path) -> str:
    """{proj_dir}/graph/project-mode.json 의 publication_mode 단일 소스.

    유효값 {"dossier-page", "split-deliverable"} 가 아니거나 파일/키 없으면
    "dossier-page"(기존 동작) — 기존 프로젝트 회귀 가드.
    """
    p = proj_dir / "graph" / "project-mode.json"
    if p.is_file():
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            mode = str(m.get("publication_mode", "")).strip()
            if mode in ("dossier-page", "split-deliverable"):
                return mode
        except Exception:
            pass
    return "dossier-page"
