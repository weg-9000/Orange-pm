#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reviewer_precheck.py — deterministic pre-check for the reviewer agent (S2-1).

Purpose:
    reviewer.md's LLM verification (V-01~V-18) covers semantic checks that
    require inference (common §, vocabulary, conflicts), but before that stage
    there are **deterministic** preconditions — frontmatter format, required
    fields, status enum, referenced_master pin format, list-field YAML
    conformance. This script verifies those preconditions using only regex/YAML
    parsing, cutting LLM token consumption by ~20% and letting the reviewer
    focus on semantic verification (V-06~V-18).

    The P-codes this script verifies don't overlap with reviewer.md's V-codes;
    the reviewer agent can start from step 1 assuming P-01~P-05 already PASS.

P-codes (precheck — all deterministic):
    P-01  frontmatter block present (--- ... --- must be at the top of the file)
    P-02  required fields present (5 fields: wo_id, type, layer, status, last_updated)
    P-03  status enum value (empty | ai-draft | human-reviewed | frozen)
    P-04  referenced_master pin format ({doc_id}@{version} — may also be empty)
    P-05  list-field YAML conformance (referenced_policies / referenced_master /
          referenced_screens / related_decisions / meeting_decisions)

SKIP rule:
    A draft with status: empty is an empty shell right after fanout, so all
    P-codes are SKIPped for it.
    (The reviewer applies the same SKIP treatment in its own step-0 status branch.)

Usage:
    python reviewer_precheck.py --hub-root <Hub> --product <product>
    python reviewer_precheck.py --hub-root <Hub> --product <product> --draft <draft path>

Output:
    JSON to stdout. Shape:
    {
      "status": "PASS" | "FAIL",
      "checks": [
        {"code": "P-01", "draft": "...", "result": "PASS|FAIL|SKIP", "msg": "..."},
        ...
      ]
    }

Exit code:
    0 = all PASS (0 FAIL)
    1 = 1 or more FAIL
    2 = argument error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Tuple

# Force stdout/stderr encoding to UTF-8 so non-ASCII output renders correctly
# on the Windows console. Uses Python 3.7+'s reconfigure. Silently skipped on
# unsupported environments (e.g. PyPy).
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

# ----- Settings ------------------------------------------------------------
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)

REQUIRED_FIELDS = ["wo_id", "type", "layer", "status", "last_updated"]
VALID_STATUS = {"empty", "ai-draft", "human-reviewed", "frozen"}
LIST_FIELDS = [
    "referenced_policies",
    "referenced_master",
    "referenced_screens",
    "related_decisions",
    "meeting_decisions",
]
# referenced_master pin format: {doc_id}@{version}
# doc_id example: G2-B-001, orange-prod-B-A-001, etc. (alphanumeric + hyphen)
# version example: v1.3, v0.1, v10.2
PIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]*@v\d+(?:\.\d+)*$")


# ----- Lightweight YAML parser ----------------------------------------------------
def parse_frontmatter(text: str) -> Tuple[dict, str]:
    """Returns the frontmatter dict and the raw block. ({}, '') if absent.

    List fields only support the inline `[a, b]` / empty `[]` / `:` (no value)
    forms. P-05 verifies this format is followed.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, ""
    raw = m.group(1)
    data: dict = {}
    for line in raw.split("\n"):
        line = line.rstrip()
        if not line or line.startswith("#") or line.startswith(" "):
            # Indented lines are dict structure — out of scope for this check (skip)
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # strip trailing comment
        if val and "  #" in val:
            val = val.split("  #", 1)[0].strip()
        data[key] = val
    return data, raw


def parse_inline_list(raw_value: str) -> Tuple[list, bool]:
    """Parses `[a, b, c]`, `[]`, or an empty string.

    Returns: (list items, ok flag). ok=False means the format is invalid.
    """
    if raw_value == "" or raw_value == "[]":
        return [], True
    if not (raw_value.startswith("[") and raw_value.endswith("]")):
        return [], False
    inner = raw_value[1:-1].strip()
    if not inner:
        return [], True
    items = [s.strip().strip("'\"") for s in inner.split(",")]
    items = [s for s in items if s]
    return items, True


# ----- P-code check functions ---------------------------------------------------
def check_p01(text: str, path: Path) -> Tuple[str, str]:
    """P-01 frontmatter block present."""
    if FRONTMATTER_RE.match(text):
        return "PASS", "frontmatter block present"
    return "FAIL", (
        "frontmatter block missing — run `python scripts/migrate_draft_frontmatter.py "
        "--hub-root . --product <product>` and retry"
    )


def check_p02(data: dict, path: Path) -> Tuple[str, str]:
    """P-02 required fields present."""
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if not missing:
        return "PASS", "all 5 required fields present"
    return "FAIL", f"missing required fields: {', '.join(missing)}"


def check_p03(data: dict, path: Path) -> Tuple[str, str]:
    """P-03 status enum."""
    status = data.get("status", "")
    if status in VALID_STATUS:
        return "PASS", f"status={status}"
    if status == "":
        return "FAIL", "status field is empty — recommend running migrate_draft_frontmatter.py"
    return "FAIL", f"status={status} — not one of the allowed values {sorted(VALID_STATUS)}"


def check_p04(data: dict, path: Path) -> Tuple[str, str]:
    """P-04 referenced_master pin format ({doc_id}@{version})."""
    raw = data.get("referenced_master", "")
    items, ok = parse_inline_list(raw)
    if not ok:
        return "FAIL", f"referenced_master inline list format violation: {raw!r}"
    bad = [it for it in items if not PIN_RE.match(it)]
    if bad:
        return (
            "FAIL",
            "referenced_master pin format violation (e.g. G2-B-001@v1.3): " + ", ".join(bad),
        )
    return "PASS", f"referenced_master: {len(items)} pin(s) in valid format"


def check_p05(data: dict, path: Path) -> Tuple[str, str]:
    """P-05 list-field YAML conformance."""
    bad = []
    for f in LIST_FIELDS:
        if f not in data:
            continue  # optional fields may be absent (P-02 only enforces required ones)
        raw = data[f]
        _, ok = parse_inline_list(raw)
        if not ok:
            bad.append(f"{f}={raw!r}")
    if bad:
        return "FAIL", "list field format violation: " + "; ".join(bad)
    return "PASS", "all list fields conform to the inline YAML list format"


# ----- Driver ---------------------------------------------------------
def run_checks_on_draft(path: Path) -> list:
    """Runs P-01~P-05 on a single draft (all SKIP if status=empty)."""
    rel = path.as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [
            {
                "code": "P-01",
                "draft": rel,
                "result": "FAIL",
                "msg": f"failed to read file: {exc}",
            }
        ]

    # P-01 first
    p01_result, p01_msg = check_p01(text, path)
    checks = [{"code": "P-01", "draft": rel, "result": p01_result, "msg": p01_msg}]
    if p01_result == "FAIL":
        # without frontmatter, later checks are impossible — SKIP the rest
        for code in ("P-02", "P-03", "P-04", "P-05"):
            checks.append(
                {
                    "code": code,
                    "draft": rel,
                    "result": "SKIP",
                    "msg": "P-01 FAIL — cannot check without frontmatter",
                }
            )
        return checks

    data, _ = parse_frontmatter(text)

    # status=empty is an empty shell right after fanout → SKIP everything
    if data.get("status", "") == "empty":
        # re-record P-01 as SKIP too
        checks = [
            {
                "code": "P-01",
                "draft": rel,
                "result": "SKIP",
                "msg": "status=empty (fanout empty shell) — not subject to verification",
            }
        ]
        for code in ("P-02", "P-03", "P-04", "P-05"):
            checks.append(
                {
                    "code": code,
                    "draft": rel,
                    "result": "SKIP",
                    "msg": "status=empty — not subject to verification",
                }
            )
        return checks

    for code, fn in (
        ("P-02", check_p02),
        ("P-03", check_p03),
        ("P-04", check_p04),
        ("P-05", check_p05),
    ):
        result, msg = fn(data, path)
        checks.append({"code": code, "draft": rel, "result": result, "msg": msg})
    return checks


def collect_drafts(hub_root: Path, product: str, single: Path | None) -> list:
    if single is not None:
        if not single.is_file():
            print(
                json.dumps(
                    {
                        "status": "FAIL",
                        "checks": [
                            {
                                "code": "P-00",
                                "draft": single.as_posix(),
                                "result": "FAIL",
                                "msg": "the specified draft file does not exist",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            sys.exit(1)
        return [single]
    drafts_dir = hub_root / "PROJECTS" / product / "drafts"
    if not drafts_dir.is_dir():
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "checks": [
                        {
                            "code": "P-00",
                            "draft": drafts_dir.as_posix(),
                            "result": "FAIL",
                            "msg": "the drafts directory does not exist",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(1)
    return sorted(drafts_dir.glob("*.draft.md"))


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic pre-check for the reviewer agent (P-01~P-05)"
    )
    parser.add_argument("--hub-root", required=True, help="Planning-Agent-Hub path")
    parser.add_argument("--product", required=True, help="Product slug (e.g. cloud-calc)")
    parser.add_argument(
        "--draft", required=False, default=None, help="Specific draft file path (single check)"
    )
    args = parser.parse_args(argv)

    hub_root = Path(args.hub_root).resolve()
    single = Path(args.draft).resolve() if args.draft else None
    drafts = collect_drafts(hub_root, args.product, single)

    all_checks: list = []
    for d in drafts:
        all_checks.extend(run_checks_on_draft(d))

    overall_fail = any(c["result"] == "FAIL" for c in all_checks)
    out = {
        "status": "FAIL" if overall_fail else "PASS",
        "checks": all_checks,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if overall_fail else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "checks": [
                        {
                            "code": "P-00",
                            "draft": "",
                            "result": "FAIL",
                            "msg": f"internal error: {exc!r}",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(2)
