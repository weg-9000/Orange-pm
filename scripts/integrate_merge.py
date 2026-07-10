#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""drafts/*.draft.md를 수집해 integrator 입력 번들을 생성한다.

[STANDALONE / NOT-WIRED]
    이 스크립트는 어떤 스킬에서도 호출되지 않는다. /integrate(및 integrator
    에이전트)는 draft frontmatter 를 직접 스캔하므로 reports/integration-input.json
    번들을 거치지 않는다. 본 스크립트는 사람이 수동으로 통합 입력을 점검할 때
    쓰는 선택적 도구로만 유지한다(파이프라인 비연결은 의도된 상태).

변경 이력:
    v1.0: 최초 구현 (heading + 파일 크기만 추출)
    v2.0: type 분리 / WO 누락 감지 / decisions.md 해시 불일치 감지 /
          체크리스트 완료 여부 / graph 노드 ID / level 추출

실행:
    python integrate_merge.py <project-dir>

bundle 구조:
    {
      "generated_at": "...",
      "project": "...",
      "graph_hash": "...",
      "decisions_hash": "...",
      "summary": {
        "total": N,
        "policy": N,
        "screen": N,
        "missing": N,
        "stale": N,
        "checklist_incomplete": N
      },
      "missing_wos": ["WO-03", ...],
      "stale_wos": ["WO-05", ...],
      "drafts": [
        {
          "path": "drafts/WO-01.draft.md",
          "wo_id": "WO-01",
          "type": "policy",
          "title": "...",
          "graph_node": "...",
          "level": 0,
          "size_bytes": 1234,
          "decisions_hash_match": true,
          "checklist_total": 7,
          "checklist_unchecked": 0
        }
      ]
    }
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path


# ── 파싱 헬퍼 ─────────────────────────────────────────────────────────────────

def _extract_bold_field(text: str, field: str) -> str:
    """**field**: `value` 패턴에서 value를 추출한다."""
    pattern = rf"\*\*{re.escape(field)}\*\*:\s*`([^`]+)`"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def _extract_title(text: str) -> str:
    """첫 번째 H1에서 섹션 제목을 추출한다.

    예: # Work Order: WO-01 — 섹션 제목  →  섹션 제목
    """
    match = re.search(r"^\s*#\s+.+?—\s+(.+)$", text, flags=re.M)
    if match:
        return match.group(1).strip()
    match = re.search(r"^\s*#\s+(.+)$", text, flags=re.M)
    return match.group(1).strip() if match else "(no heading)"


def _extract_checklist(text: str) -> tuple[int, int]:
    """체크리스트 총 항목 수와 미완료(- [ ]) 항목 수를 반환한다."""
    total = len(re.findall(r"- \[[ xX]\]", text))
    unchecked = len(re.findall(r"- \[ \]", text))
    return total, unchecked


def _hash_file(path: Path) -> str:
    if not path.exists():
        return "n/a"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:12]


def _count_dec_status(decisions_path: Path) -> dict:
    """decisions.md DEC 표의 `승인` 칼럼을 파싱해 상태별 개수를 반환한다.

    스키마: CONTEXT/dec-schema.md
    | ID | 일자 | 도메인 | 핵심 결정 | 번복 | 승인 | 근거(스킬·세션) |

    승인 ENUM:
        ⬜              → pending
        ✅ {pm_id}      → approved
        ❌ {pm_id}: ... → rejected
        🟡 보류         → hold

    표 미존재·헤더 mismatch 시 모든 카운트를 -1 로 반환 (미적용).
    """
    if not decisions_path.exists():
        return {"total": -1, "pending": -1, "approved": -1, "rejected": -1, "hold": -1}

    text = decisions_path.read_text(encoding="utf-8", errors="replace")
    # 헤더 라인 탐지 (필수 5 칼럼 확인)
    header_re = re.compile(
        r"^\|\s*ID\s*\|\s*일자\s*\|\s*도메인\s*\|\s*핵심 결정\s*\|\s*번복\s*\|\s*승인\s*\|",
        re.M,
    )
    if not header_re.search(text):
        return {"total": -1, "pending": -1, "approved": -1, "rejected": -1, "hold": -1}

    # DEC 행 추출 (| DEC-NNN | ... | 승인셀 | ... |)
    row_re = re.compile(
        r"^\|\s*~?~?(DEC-\d+)~?~?\s*\|[^|\n]*\|[^|\n]*\|[^|\n]*\|[^|\n]*\|\s*([^|\n]*?)\s*\|",
        re.M,
    )
    counts = {"total": 0, "pending": 0, "approved": 0, "rejected": 0, "hold": 0}
    for match in row_re.finditer(text):
        approval_cell = match.group(2).strip()
        counts["total"] += 1
        if approval_cell.startswith("⬜"):
            counts["pending"] += 1
        elif approval_cell.startswith("✅"):
            counts["approved"] += 1
        elif approval_cell.startswith("❌"):
            counts["rejected"] += 1
        elif approval_cell.startswith("🟡"):
            counts["hold"] += 1
    return counts


# ── index.md에서 WO ID 목록 추출 ──────────────────────────────────────────────

def _load_index_wo_ids(project: Path) -> list[str]:
    """work-orders/index.md에서 WO-NN ID 목록을 추출한다."""
    index_path = project / "work-orders" / "index.md"
    if not index_path.exists():
        return []
    text = index_path.read_text(encoding="utf-8", errors="replace")
    return re.findall(r"`(WO-\d+)`", text)


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main() -> int:
    if len(sys.argv) != 2:
        print("usage: integrate_merge.py <project-dir>", file=sys.stderr)
        return 2

    project = Path(sys.argv[1]).resolve()
    drafts_dir = project / "drafts"

    if not drafts_dir.exists():
        print(
            f"[integrate_merge] FAIL: drafts/ 디렉토리 없음: {drafts_dir}",
            file=sys.stderr,
        )
        return 1

    # ── 현재 해시 계산 ──────────────────────────────────────────────────────────
    graph_hash = _hash_file(project / "graph" / "graph.json")
    decisions_path = project / "decisions.md"
    decisions_hash = _hash_file(decisions_path)
    dec_counts = _count_dec_status(decisions_path)

    # ── index.md 기준 WO 목록 로드 ─────────────────────────────────────────────
    index_wo_ids = _load_index_wo_ids(project)
    index_wo_set = set(index_wo_ids)

    # ── draft 파일 수집 ────────────────────────────────────────────────────────
    draft_files = sorted(drafts_dir.glob("*.draft.md"))
    draft_wo_set: set[str] = set()
    drafts: list[dict] = []

    for path in draft_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        wo_id = path.stem.replace(".draft", "")
        draft_wo_set.add(wo_id)

        wo_type = _extract_bold_field(text, "type") or "unknown"
        graph_node = _extract_bold_field(text, "문서명") or ""
        if not graph_node:
            # screen WO는 Screen ID 필드 사용
            graph_node = _extract_bold_field(text, "Screen ID") or ""

        level_parts = _extract_bold_field(text, "level").split()
        level_str = level_parts[0] if level_parts else ""
        try:
            level = int(level_str)
        except (ValueError, IndexError):
            level = -1

        wo_decisions_hash = _extract_bold_field(text, "decisions.md 스냅샷 해시")
        decisions_hash_match = (
            wo_decisions_hash == decisions_hash
            if wo_decisions_hash not in ("", "n/a")
            else None
        )

        checklist_total, checklist_unchecked = _extract_checklist(text)

        drafts.append({
            "path": str(path.relative_to(project)),
            "wo_id": wo_id,
            "type": wo_type,
            "title": _extract_title(text),
            "graph_node": graph_node,
            "level": level,
            "size_bytes": path.stat().st_size,
            "decisions_hash_match": decisions_hash_match,
            "checklist_total": checklist_total,
            "checklist_unchecked": checklist_unchecked,
        })

    # ── 누락 WO 탐지 ──────────────────────────────────────────────────────────
    missing_wos = sorted(index_wo_set - draft_wo_set) if index_wo_set else []

    # ── stale WO 탐지 (decisions.md 해시 불일치) ───────────────────────────────
    stale_wos = [
        d["wo_id"]
        for d in drafts
        if d["decisions_hash_match"] is False
    ]

    # ── 체크리스트 미완료 WO ───────────────────────────────────────────────────
    checklist_incomplete = [
        d["wo_id"]
        for d in drafts
        if d["checklist_unchecked"] > 0
    ]

    # ── type별 집계 ────────────────────────────────────────────────────────────
    policy_count = sum(1 for d in drafts if d["type"] == "policy")
    screen_count = sum(1 for d in drafts if d["type"] == "screen")

    # ── 번들 구성 ──────────────────────────────────────────────────────────────
    bundle = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "project": project.name,
        "graph_hash": graph_hash,
        "decisions_hash": decisions_hash,
        "dec_status": dec_counts,
        "summary": {
            "total": len(drafts),
            "policy": policy_count,
            "screen": screen_count,
            "missing": len(missing_wos),
            "stale": len(stale_wos),
            "checklist_incomplete": len(checklist_incomplete),
            "dec_pending": dec_counts["pending"],
            "dec_hold": dec_counts["hold"],
        },
        "missing_wos": missing_wos,
        "stale_wos": stale_wos,
        "checklist_incomplete_wos": checklist_incomplete,
        "drafts": drafts,
    }

    # ── 저장 ──────────────────────────────────────────────────────────────────
    out_dir = project / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "integration-input.json"
    out_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ── 콘솔 요약 ─────────────────────────────────────────────────────────────
    # 콘솔 stdout 인코딩이 utf-8 이 아니면 (Windows cp949 등) emoji 를 ASCII fallback
    use_emoji = (sys.stdout.encoding or "").lower().startswith("utf")
    if dec_counts["total"] < 0:
        dec_summary = "DEC: 표 미존재 또는 헤더 mismatch — 마이그레이션 필요"
    elif use_emoji:
        dec_summary = (
            f"DEC: total {dec_counts['total']} / "
            f"✅ {dec_counts['approved']} / ⬜ {dec_counts['pending']} / "
            f"🟡 {dec_counts['hold']} / ❌ {dec_counts['rejected']}"
        )
    else:
        dec_summary = (
            f"DEC: total {dec_counts['total']} / "
            f"approved {dec_counts['approved']} / pending {dec_counts['pending']} / "
            f"hold {dec_counts['hold']} / rejected {dec_counts['rejected']}"
        )
    print(
        f"[integrate_merge] bundle generated -> {out_path}\n"
        f"  drafts:      {len(drafts)} (policy: {policy_count} / screen: {screen_count})\n"
        f"  missing WO:  {len(missing_wos)} {missing_wos if missing_wos else ''}\n"
        f"  stale WO:    {len(stale_wos)} {stale_wos if stale_wos else ''}\n"
        f"  checklist incomplete: {len(checklist_incomplete)} "
        f"{checklist_incomplete if checklist_incomplete else ''}\n"
        f"  {dec_summary}"
    )

    # 누락 WO가 있으면 비정상 종료
    if missing_wos:
        print(
            f"[integrate_merge] FAIL: 누락 draft {missing_wos}. "
            "/integrate 실행 전 해당 WO 작성을 완료하세요.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
