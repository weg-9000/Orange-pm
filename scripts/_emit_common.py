#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Common utilities for visual-interface adapters (--emit-json contract).

Every *_emit.py adapter converts raw Hub artifacts into the normalized JSON
described in docs/visual-interface/01-data-contract.md and prints a single
object to stdout. Read-only.

Contract:
    python <kind>_emit.py --hub-root <Hub> --product <name> --emit-json
    python <kind>_emit.py --from-fixture <path> --emit-json   # fixture passthrough
exit code: 0 ok / 1 no source (empty skeleton) / 2 argument error
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

# Queue header parser (same rule as build_ssot_status)
HEADER_NUM = re.compile(r"(?<![A-Za-z/])([A-Z]+(?:/[A-Z]+)?)\s*:\s*(\d+)")


def content_version(obj: object) -> str:
    """Content hash -> idempotent update key."""
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "sha1:" + hashlib.sha1(raw).hexdigest()[:12]


def make_parser(kind: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=f"{kind}_emit — {kind} adapter")
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
    """Recompute version, then print. version is based on the body excluding kind/version."""
    body = {k: v for k, v in obj.items() if k not in ("version", "generated_at")}
    obj["version"] = content_version(body)
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return 0


def parse_header_counts(text: str) -> dict[str, int]:
    """Find the header line (label:number) in a queue file body and return it as a map."""
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
    """Simple key: value parsing of --- ... --- frontmatter (no nesting support)."""
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
    """Single source for publication_mode from {proj_dir}/graph/project-mode.json.

    If the value isn't one of {"dossier-page", "split-deliverable"}, or the
    file/key is missing, return "dossier-page" (legacy behavior) — a
    regression guard for existing projects.
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
