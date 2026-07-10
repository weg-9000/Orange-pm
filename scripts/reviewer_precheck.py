#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reviewer_precheck.py — reviewer 에이전트 사전 결정적 검증 (S2-1).

목적:
    reviewer.md 의 LLM 검증(V-01~V-18) 은 의미 추론(공통 §, 어휘, 충돌)이 필요한
    semantic 검사들이지만, 그 이전 단계에는 frontmatter 형식·필수 필드·status enum·
    referenced_master 핀 형식·list 필드 YAML 적합성 같은 **결정적(deterministic)**
    선행 조건이 존재한다. 이 스크립트는 그 선행 조건을 regex·yaml 파싱만으로 검증
    하여 LLM 토큰 소비를 ~20% 줄이고, reviewer 가 의미 검증(V-06~V-18)에 집중하도록
    한다.

    본 스크립트가 검증하는 P-코드는 reviewer.md 의 V-코드와 충돌하지 않으며,
    reviewer 에이전트는 P-01~P-05 가 PASS 라는 가정 하에 단계 1 부터 시작할 수 있다.

P-코드 (precheck — 모두 결정적):
    P-01  frontmatter 블록 존재 (--- ... --- 가 파일 최상단에 있어야 함)
    P-02  필수 필드 존재 (wo_id, type, layer, status, last_updated 5종)
    P-03  status enum 값 (empty | ai-draft | human-reviewed | frozen)
    P-04  referenced_master 핀 형식 ({doc_id}@{version} — 비어있어도 가능)
    P-05  list 필드 YAML 적합성 (referenced_policies / referenced_master /
          referenced_screens / related_decisions / meeting_decisions)

SKIP 규칙:
    status: empty 인 draft 는 fanout 직후 빈 셸이므로 모든 P-코드 SKIP 처리.
    (reviewer 도 단계 0 status 분기에서 동일하게 SKIP 처리한다.)

사용법:
    python reviewer_precheck.py --hub-root <Hub> --product <product>
    python reviewer_precheck.py --hub-root <Hub> --product <product> --draft <draft 경로>

출력:
    JSON to stdout. 형태:
    {
      "status": "PASS" | "FAIL",
      "checks": [
        {"code": "P-01", "draft": "...", "result": "PASS|FAIL|SKIP", "msg": "..."},
        ...
      ]
    }

Exit code:
    0 = 전체 PASS (FAIL 0건)
    1 = 1건 이상 FAIL
    2 = 인자 오류
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Tuple

# Windows 콘솔에서 한글 출력을 위해 stdout/stderr 인코딩을 UTF-8 로 강제.
# Python 3.7+ 의 reconfigure 사용. 미지원 환경(예: PyPy)은 silently skip.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

# ----- 설정 ------------------------------------------------------------
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
# referenced_master 핀 형식: {doc_id}@{version}
# doc_id 예: G2-B-001, orange-prod-B-A-001 등 (영숫자·하이픈)
# version 예: v1.3, v0.1, v10.2
PIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]*@v\d+(?:\.\d+)*$")


# ----- yaml 경량 파서 ----------------------------------------------------
def parse_frontmatter(text: str) -> Tuple[dict, str]:
    """frontmatter dict 와 raw block 을 반환. 없으면 ({}, '').

    list 필드는 인라인 `[a, b]` / 빈 `[]` / `:` 만 (값 없음) 형식만 지원.
    P-05 가 이 형식 준수를 검증한다.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, ""
    raw = m.group(1)
    data: dict = {}
    for line in raw.split("\n"):
        line = line.rstrip()
        if not line or line.startswith("#") or line.startswith(" "):
            # 들여쓰기 줄은 dict 구조이므로 본 검증 범위 밖 (스킵)
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # 주석 제거
        if val and "  #" in val:
            val = val.split("  #", 1)[0].strip()
        data[key] = val
    return data, raw


def parse_inline_list(raw_value: str) -> Tuple[list, bool]:
    """`[a, b, c]` 또는 `[]` 또는 빈 문자열을 파싱.

    반환: (리스트 항목, ok 플래그). ok=False 면 형식 위반.
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


# ----- P-코드 검사 함수 ---------------------------------------------------
def check_p01(text: str, path: Path) -> Tuple[str, str]:
    """P-01 frontmatter 블록 존재."""
    if FRONTMATTER_RE.match(text):
        return "PASS", "frontmatter 블록 존재"
    return "FAIL", (
        "frontmatter 블록 누락 — `python scripts/migrate_draft_frontmatter.py "
        "--hub-root . --product <product>` 실행 후 재시도"
    )


def check_p02(data: dict, path: Path) -> Tuple[str, str]:
    """P-02 필수 필드 존재."""
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if not missing:
        return "PASS", "필수 필드 5종 모두 존재"
    return "FAIL", f"필수 필드 누락: {', '.join(missing)}"


def check_p03(data: dict, path: Path) -> Tuple[str, str]:
    """P-03 status enum."""
    status = data.get("status", "")
    if status in VALID_STATUS:
        return "PASS", f"status={status}"
    if status == "":
        return "FAIL", "status 필드 비어있음 — migrate_draft_frontmatter.py 실행 권고"
    return "FAIL", f"status={status} — 허용값 {sorted(VALID_STATUS)} 외"


def check_p04(data: dict, path: Path) -> Tuple[str, str]:
    """P-04 referenced_master 핀 형식 ({doc_id}@{version})."""
    raw = data.get("referenced_master", "")
    items, ok = parse_inline_list(raw)
    if not ok:
        return "FAIL", f"referenced_master 인라인 list 형식 위반: {raw!r}"
    bad = [it for it in items if not PIN_RE.match(it)]
    if bad:
        return (
            "FAIL",
            "referenced_master 핀 형식 위반(예: G2-B-001@v1.3): " + ", ".join(bad),
        )
    return "PASS", f"referenced_master {len(items)}개 핀 형식 적합"


def check_p05(data: dict, path: Path) -> Tuple[str, str]:
    """P-05 list 필드 YAML 적합성."""
    bad = []
    for f in LIST_FIELDS:
        if f not in data:
            continue  # 선택 필드는 부재 허용 (P-02 가 필수만 강제)
        raw = data[f]
        _, ok = parse_inline_list(raw)
        if not ok:
            bad.append(f"{f}={raw!r}")
    if bad:
        return "FAIL", "list 필드 형식 위반: " + "; ".join(bad)
    return "PASS", "모든 list 필드 YAML 인라인 list 형식 적합"


# ----- 드라이버 ---------------------------------------------------------
def run_checks_on_draft(path: Path) -> list:
    """draft 1개에 대해 P-01~P-05 실행 (status=empty 면 모두 SKIP)."""
    rel = path.as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [
            {
                "code": "P-01",
                "draft": rel,
                "result": "FAIL",
                "msg": f"파일 읽기 실패: {exc}",
            }
        ]

    # P-01 먼저
    p01_result, p01_msg = check_p01(text, path)
    checks = [{"code": "P-01", "draft": rel, "result": p01_result, "msg": p01_msg}]
    if p01_result == "FAIL":
        # frontmatter 없으면 이후 검사 불가 — 나머지 SKIP
        for code in ("P-02", "P-03", "P-04", "P-05"):
            checks.append(
                {
                    "code": code,
                    "draft": rel,
                    "result": "SKIP",
                    "msg": "P-01 FAIL — frontmatter 부재로 검사 불가",
                }
            )
        return checks

    data, _ = parse_frontmatter(text)

    # status=empty 는 fanout 직후 빈 셸 → 전부 SKIP
    if data.get("status", "") == "empty":
        # P-01 도 SKIP 으로 다시 기록
        checks = [
            {
                "code": "P-01",
                "draft": rel,
                "result": "SKIP",
                "msg": "status=empty (fanout 빈 셸) — 검증 비대상",
            }
        ]
        for code in ("P-02", "P-03", "P-04", "P-05"):
            checks.append(
                {
                    "code": code,
                    "draft": rel,
                    "result": "SKIP",
                    "msg": "status=empty — 검증 비대상",
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
                                "msg": "지정된 draft 파일이 존재하지 않음",
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
                            "msg": "drafts 디렉터리가 존재하지 않음",
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
        description="reviewer 사전 결정적 검증 (P-01~P-05)"
    )
    parser.add_argument("--hub-root", required=True, help="Planning-Agent-Hub 경로")
    parser.add_argument("--product", required=True, help="제품 슬러그 (예: cloud-calc)")
    parser.add_argument(
        "--draft", required=False, default=None, help="특정 draft 파일 경로 (단독 검사)"
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
                            "msg": f"내부 오류: {exc!r}",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(2)
