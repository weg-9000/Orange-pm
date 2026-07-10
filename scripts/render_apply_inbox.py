#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render apply inbox — Confluence drift merge-proposal 의 PM 결정 사항을 draft 에 적용.

설계 의도:
    render_sync_check.py --with-remote 가 Confluence 가 더 최신인 페이지를
    감지하면 reports/inbox/{WO_ID}.merge-proposal.md 를 생성한다.
    PM 이 proposal 에서 체크박스 선택 후 본 스크립트로 적용.

    LLM round-trip 의 lossy 특성 때문에 자동 적용은 위험. 본 스크립트는:
    - PM 이 명시적으로 "전체 본문 채택" 체크박스 선택 시에만 draft 덮어쓰기
    - 적용 직후 fact_preservation_check 즉시 실행 → fact 손실 시 차단·롤백
    - "수동 검토 완료" 체크 시 단순 archive (draft 미변경)
    - 양쪽 미체크 시 NOOP

체크박스 형식:
    - [x] **전체 본문 채택** ...    ← 적용 대상
    - [x] **수동 검토 완료** ...    ← archive only
    - [ ] **...**                   ← 무시

exit code:
    0 = 성공 (적용 또는 archive 또는 NOOP)
    1 = fact_preservation_check FAIL (적용 차단, draft 미변경)
    2 = 사용법/파일 오류
    3 = proposal 형식 오류 (체크박스 양립 — full+manual 동시 체크)
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
FACT_CHECK_SCRIPT = HERE / "fact_preservation_check.py"

# MEDIUM #12: BOM·CRLF·선행 공백 관용 — \A strict 매칭 실패 시 frontmatter 전체 손실 방지
FRONTMATTER_RE = re.compile(r"\A﻿?\s*---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
# MEDIUM #9: 체크박스 대소문자 양쪽 허용
CHECKED_FULL_RE = re.compile(
    r"^\s*-\s*\[[xX]\]\s*\*\*전체\s*본문\s*채택\*\*",
    re.MULTILINE,
)
CHECKED_MANUAL_RE = re.compile(
    r"^\s*-\s*\[[xX]\]\s*\*\*수동\s*검토\s*완료\*\*",
    re.MULTILINE,
)
# CRITICAL #2: 본문 추출은 HTML 주석 sentinel 사용 (``` 코드 펜스 충돌 방지)
# render_sync_check 의 _write_merge_proposal 가 다음 sentinel 쌍으로 감싸 작성.
CONFLUENCE_BODY_RE = re.compile(
    r"<!--\s*confluence-body:start\s*-->\s*\n(.*?)\n<!--\s*confluence-body:end\s*-->",
    re.DOTALL,
)
META_PAGE_RE = re.compile(r"page_id:\s*`([^`]+)`")


def _read_proposal(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"proposal 없음: {path}")
    text = path.read_text(encoding="utf-8")
    has_full = bool(CHECKED_FULL_RE.search(text))
    has_manual = bool(CHECKED_MANUAL_RE.search(text))
    body_m = CONFLUENCE_BODY_RE.search(text)
    page_m = META_PAGE_RE.search(text)
    return {
        "text": text,
        "has_full": has_full,
        "has_manual": has_manual,
        "remote_body": body_m.group(1) if body_m else "",
        "page_id": page_m.group(1) if page_m else "",
    }


def _replace_body_preserve_frontmatter(draft_text: str, new_body: str) -> str:
    """draft frontmatter 는 유지하고 본문만 교체."""
    m = FRONTMATTER_RE.match(draft_text)
    if not m:
        return new_body
    fm_block = draft_text[: m.end()]
    return fm_block + new_body.rstrip() + "\n"


def _archive(proposal_path: Path, suffix: str) -> Path:
    archive_dir = proposal_path.parent / "archived"
    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    archived = archive_dir / f"{proposal_path.stem}.{ts}.{suffix}.md"
    shutil.move(str(proposal_path), str(archived))
    return archived


def _run_fact_check(before: Path, after: Path, hub_root: Path, report: Path) -> int:
    """fact_preservation_check 실행. exit code 반환."""
    cmd = [
        sys.executable,
        str(FACT_CHECK_SCRIPT),
        "--before", str(before),
        "--after", str(after),
        "--hub-root", str(hub_root),
        "--report", str(report),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode


def apply_inbox(hub_root: Path, product: str, wo_id: str) -> int:
    proj = hub_root / "PROJECTS" / product
    proposal_path = proj / "reports" / "inbox" / f"{wo_id}.merge-proposal.md"
    draft_path = proj / "drafts" / f"{wo_id}.draft.md"

    if not proj.is_dir():
        print(f"[apply-inbox] FAIL: 프로젝트 없음 — {proj}", file=sys.stderr)
        return 2
    if not draft_path.is_file():
        print(f"[apply-inbox] FAIL: draft 없음 — {draft_path}", file=sys.stderr)
        return 2

    try:
        proposal = _read_proposal(proposal_path)
    except FileNotFoundError as exc:
        print(f"[apply-inbox] FAIL: {exc}", file=sys.stderr)
        return 2

    if proposal["has_full"] and proposal["has_manual"]:
        print("[apply-inbox] FAIL: '전체 본문 채택' 과 '수동 검토 완료' 가 동시 체크됨 — "
              "하나만 선택해주세요", file=sys.stderr)
        return 3

    # 1. NOOP: 양쪽 미체크
    if not proposal["has_full"] and not proposal["has_manual"]:
        print(f"[apply-inbox] NOOP: {wo_id} — 체크박스 미선택, proposal 유지")
        return 0

    # 2. archive only: 수동 검토 완료
    if proposal["has_manual"]:
        archived = _archive(proposal_path, "manual-reviewed")
        print(f"[apply-inbox] ARCHIVED (수동 검토): {wo_id} → {archived.relative_to(hub_root)}")
        return 0

    # 3. 전체 본문 채택
    remote_body = proposal["remote_body"].strip()
    if not remote_body:
        print(f"[apply-inbox] FAIL: proposal 에서 Confluence 본문 추출 실패", file=sys.stderr)
        return 2

    # 백업
    backup_path = draft_path.with_suffix(draft_path.suffix + ".bak")
    shutil.copy(str(draft_path), str(backup_path))

    original_text = draft_path.read_text(encoding="utf-8")
    new_text = _replace_body_preserve_frontmatter(original_text, remote_body)

    # 임시 파일에 새 본문 저장 → fact-check
    tmp_dir = proj / "reports" / "inbox" / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_after = tmp_dir / f"{wo_id}.candidate.md"
    tmp_after.write_text(new_text, encoding="utf-8")

    fact_report = proj / "reports" / "inbox" / f"{wo_id}.fact-check.md"
    rc = _run_fact_check(backup_path, tmp_after, hub_root, fact_report)

    if rc != 0:
        # fact 손실 발견 — 적용 차단, backup 으로 롤백
        # backup 은 이미 원본이므로 별도 작업 불필요
        backup_path.unlink(missing_ok=True)
        tmp_after.unlink(missing_ok=True)
        print(f"[apply-inbox] FAIL: {wo_id} — Confluence 본문 적용 시 fact 손실 발견. "
              f"draft 미변경. 누락 fact: {fact_report.relative_to(hub_root)}",
              file=sys.stderr)
        return 1

    # PASS: draft 갱신
    draft_path.write_text(new_text, encoding="utf-8")
    tmp_after.unlink(missing_ok=True)
    backup_path.unlink(missing_ok=True)

    archived = _archive(proposal_path, "applied")
    print(f"[apply-inbox] APPLIED: {wo_id} — fact-check PASS. "
          f"draft 갱신 + proposal archive → {archived.relative_to(hub_root)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="reports/inbox/{WO}.merge-proposal.md 의 PM 결정을 draft 에 적용"
    )
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", required=True)
    ap.add_argument("--wo", required=True, help="대상 WO_ID (예: WO-05)")
    args = ap.parse_args()

    if not args.hub_root.is_dir():
        print(f"[apply-inbox] FAIL: hub-root 없음 — {args.hub_root}", file=sys.stderr)
        return 2

    return apply_inbox(args.hub_root, args.product, args.wo)


if __name__ == "__main__":
    sys.exit(main())
