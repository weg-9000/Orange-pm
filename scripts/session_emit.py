#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""session_emit — RESUME/decisions/open-issues/session-log → 정규화 session 계약 (§5)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import _emit_common as C

_ROW = re.compile(r"^\|(.+)\|\s*$")


def _rows(text: str) -> list[list[str]]:
    """마크다운 표의 데이터 행(헤더·구분선 제외) → 셀 리스트."""
    out = []
    for line in text.splitlines():
        m = _ROW.match(line.strip())
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if not cells or all(set(c) <= {"-", ":", " "} for c in cells):
            continue  # 구분선
        if cells[0] in ("DEC ID", "ID", "#", "버전"):
            continue  # 헤더
        out.append(cells)
    return out


_HEADER_FIRST = {"ID", "DEC ID", "DEC", "결정 ID", "#", "번호"}


def _col(header: list[str], *names: str) -> int:
    """헤더에서 names 중 하나를 포함하는 첫 컬럼 인덱스(없으면 -1)."""
    for i, h in enumerate(header):
        for n in names:
            if n in h:
                return i
    return -1


def _decision_col(header: list[str]) -> int:
    """결정 내용 컬럼 인덱스. 구체 명칭 우선, 폴백은 'ID'/'결정자' 가 아닌 '결정' 컬럼.
    ('결정' 이 'DEC ID'/'결정 ID' 등 ID 컬럼에 잘못 매칭되는 것 방지)"""
    for i, h in enumerate(header):
        if any(k in h for k in ("결정 요지", "결정요지", "핵심 결정", "결정 내용", "결정 요약")):
            return i
    for i, h in enumerate(header):
        if "결정" in h and "ID" not in h.upper() and "결정자" not in h:
            return i
    return -1


def _approval_state(cell: str, has_col: bool = True) -> str:
    """승인 셀 → approved/pending/hold/rejected.
    승인 컬럼 자체가 없는 표(레거시)면 approved(기존 동작 유지)."""
    if not has_col:
        return "approved"
    if "✅" in cell:
        return "approved"
    if "❌" in cell or "반려" in cell:
        return "rejected"
    if "🟡" in cell or "보류" in cell:
        return "hold"
    if "⬜" in cell or "미승인" in cell:
        return "pending"
    return "approved" if cell.strip() else "pending"


def _approver(cell: str) -> str:
    """'✅ jeongdh' → 'jeongdh' (이모지/기호 뒤 식별자)."""
    m = re.search(r"[A-Za-z][\w.\-]+", cell)
    return m.group(0) if m else ""


def parse_decisions(text: str) -> list[dict]:
    """결정표 행 → {id,date,regType,title,detail,approval,approver,status}.
    표 단위로 처리한다: 헤더에 결정 컬럼(핵심 결정/결정 내용/결정 요지 등)이 있는 '결정표'만
    파싱하고 부속표(이슈/항목/사유 등)는 건너뛴다. 한 파일에 결정표가 여럿이어도 각자 헤더를 쓴다.
    컬럼은 헤더명으로 탐색(프로젝트별 레이아웃 상이 대응)."""
    res: list[dict] = []
    cols: dict | None = None      # 현재 결정표 컬럼. 표 밖/heading 뒤면 None
    last: dict | None = None      # 최근 결정표 레이아웃(헤더 없는 연속 DEC 행 폴백)
    suppressed = False            # 현재 표가 명시적 비결정표(이슈/항목/사유 …)면 True
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):              # 섹션(heading) 경계 → 표 컨텍스트만 리셋
            cols = None
            suppressed = False
            continue
        if not s.startswith("|"):          # 표 밖 prose/공백 → 컨텍스트 유지
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        is_sep = all(set(c) <= {"-", ":", " "} for c in cells)
        if cells and cells[0] in _HEADER_FIRST and not is_sep:   # 헤더 행
            i_dec = _decision_col(cells)
            if i_dec >= 0:
                cols = {
                    "date": _col(cells, "등재일", "확정일", "발효일", "일자"),
                    "dec": i_dec,
                    "reg": _col(cells, "상태"),
                    "appr": _col(cells, "승인"),
                    "by": _col(cells, "결정자"),
                    "det": _col(cells, "영향", "사유", "근거"),
                }
                last = cols
                suppressed = False
            else:                          # 비결정표(이슈/항목/사유) → 억제
                cols = None
                suppressed = True
            continue
        if is_sep:
            continue
        # 헤더 있으면 cols, 없는 연속 DEC 행이면 직전 결정표(last) 폴백.
        # 단 명시적 비결정표 안에서는 폴백 금지.
        active = cols if cols is not None else (None if suppressed else last)
        if active is None or "DEC" not in cells[0]:
            continue

        def get(i: int) -> str:
            return cells[i] if 0 <= i < len(cells) else ""

        cols = active  # (아래 블록 호환)
        appr_cell = get(cols["appr"])
        title = re.sub(r"~~", "", get(cols["dec"])).replace("**", "").strip()
        appr = _approval_state(appr_cell, cols["appr"] >= 0)
        res.append({
            "id": re.sub(r"~~", "", cells[0]).strip(),
            "date": get(cols["date"]),
            "regType": get(cols["reg"]),
            "title": title or get(cols["reg"]),
            "detail": get(cols["det"]),
            "approval": appr,
            "approver": _approver(appr_cell) or (get(cols["by"]) if cols["by"] >= 0 else ""),
            "status": appr,  # 하위호환(기존 소비처)
        })
    return res


# open-issues 체크박스 항목: "- [ ] 본문" (들여쓴 하위 항목·* 불릿 허용)
_CHECKBOX = re.compile(r"^\s*[-*]\s+\[(.)\]\s+(\S.*)$")
# 항목 선두 [ID] 토큰 — 굵게/취소선 래핑 허용 (**[ID]**, ~~**[ID]** …)
_ISSUE_ID = re.compile(r"^[\s*~_]*\[([^\[\]]{1,80})\]\s*")
# 본문 인라인 우선순위 표기: "(P1)" / "(P1 / …)" / "— P2 (…)"
_P_INLINE = re.compile(r"\(\s*P([0-2])\b|[—–-]\s*P([0-2])\s*[\(（—–-]")
# 우선순위 헤딩: "## P0 — …" / "### P1 …"
_P_HEAD = re.compile(r"^#{2,3}\s*P([0-2])\b")
# 이슈 표 헤더로 인정하는 첫 컬럼명 (그 외 헤더의 표는 본문 참조용으로 간주)
_ISSUE_TABLE_HEAD = ("ID", "DEC ID", "#", "번호")


def _md_plain(s: str) -> str:
    """굵게·취소선·코드 마크업 제거 + 공백 단일화."""
    return re.sub(r"\s+", " ", re.sub(r"\*\*|~~|`", "", s)).strip()


def parse_open_issues(text: str) -> list[dict]:
    """open-issues.md → 미해결 항목 [{id,p,title}]. 형식 다양성 수용:

    - 체크박스: `- [ ] **[ID]** …`(미결)·`- [~] …`(보류=미결 포함).
      `- [x]`(해소)·`- [i]`(정보성)는 제외. 들여쓴 하위 체크박스도 개별 항목.
    - 표: 헤더 첫 칸이 ID 계열(`ID`/`DEC ID`/`#`/`번호`)인 표의 데이터 행만.
      본문에 포함된 참조용 표(예: cloud-calculator 종속 모델 표)는 무시.

    우선순위: `## P0/P1/P2` 헤딩 추적 — 비-P `##` 헤딩은 기본 P1 리셋,
    `###` 는 상위 섹션 유지. 본문 인라인 `(P1)`/`— P2 (…)` 표기가 있으면 우선.
    """
    res: list[dict] = []
    cur_p = 1
    in_issue_table = False
    for line in text.splitlines():
        s = line.strip()
        mh = _P_HEAD.match(s)
        if mh:
            cur_p = int(mh.group(1))
            in_issue_table = False
            continue
        if s.startswith("#"):                      # 비-P 헤딩
            if not s.startswith("###"):            # ## 섹션 경계 → 기본 P1
                cur_p = 1
            in_issue_table = False
            continue
        mc = _CHECKBOX.match(line)
        if mc:
            in_issue_table = False
            mark, body = mc.group(1), mc.group(2)
            if mark in "xX✓i":                     # 해소·정보성 제외
                continue
            iid = ""
            mid = _ISSUE_ID.match(body)
            if mid:
                iid = _md_plain(mid.group(1))
                body = body[mid.end():]
            title = _md_plain(body)
            mp = _P_INLINE.search(title[:200])
            p = int(mp.group(1) or mp.group(2)) if mp else cur_p
            title = re.sub(r"^\(\s*P[0-2][^)]*\)\s*", "", title)
            if len(title) > 120:
                title = title[:119] + "…"
            res.append({"id": iid, "p": p, "title": title})
            continue
        m = _ROW.match(s)
        if not m:
            in_issue_table = False                 # 표 종료(공백/prose)
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if not cells or all(set(c) <= {"-", ":", " "} for c in cells):
            continue                               # 구분선(표 상태 유지)
        if cells[0] in _ISSUE_TABLE_HEAD:
            in_issue_table = True                  # 이슈 표 시작
            continue
        if not in_issue_table:
            continue                               # 참조용 표 행 무시
        res.append({"id": cells[0], "p": cur_p,
                    "title": cells[1] if len(cells) > 1 else ""})
    return res


def parse_resume(text: str) -> dict | None:
    """RESUME.md 에서 lastSkill/lastWo/savedAt 추출(키:값 또는 표)."""
    fm = C.read_frontmatter(text)
    if fm.get("last_skill") or fm.get("lastSkill"):
        return {"lastSkill": fm.get("last_skill") or fm.get("lastSkill"),
                "lastWo": fm.get("last_wo") or fm.get("lastWo", ""),
                "savedAt": fm.get("saved_at") or fm.get("savedAt", "")}
    return None


# hook event → timeline 라벨 매핑 (.claude/ui-events.jsonl, M3 hook 채널)
_HOOK_LABEL = {
    "SessionStart": ("skill", "세션 시작"),
    "Stop": ("skill", "세션 종료"),
    "SubagentStop": ("subagent", "subagent 완료"),
    "PostToolUse": ("edit", "편집"),
    "UserPromptSubmit": ("skill", "프롬프트"),
}


def parse_ui_events(text: str, limit: int = 50) -> list[dict]:
    """.claude/ui-events.jsonl (1줄 1 JSON) → timeline 이벤트 목록(최신 우선)."""
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind, default_label = _HOOK_LABEL.get(ev.get("hook", ""), ("skill", ev.get("hook", "")))
        detail = ev.get("detail") or ev.get("agent") or ev.get("tool") or default_label
        out.append({"ts": ev.get("ts", ""), "event": kind, "label": detail})
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out[:limit]


def transform_session(texts: dict[str, str], product: str = "",
                      ui_events: str = "") -> dict:
    return {
        "version": "", "product": product, "kind": "session",
        "resume": parse_resume(texts.get("RESUME.md", "")),
        "openIssues": parse_open_issues(texts.get("open-issues.md", "")),
        "decisions": parse_decisions(texts.get("decisions.md", "")),
        "timeline": parse_ui_events(ui_events),  # hook 채널 보강
    }


def main(argv: list[str]) -> int:
    args = C.make_parser("session").parse_args(argv)
    if args.from_fixture:
        return C.emit(C.load_fixture(args.from_fixture))
    if not (args.hub_root and args.product):
        sys.stderr.write("--hub-root, --product 필요\n")
        return 2
    pdir = C.product_dir(args.hub_root, args.product)
    names = ["RESUME.md", "open-issues.md", "decisions.md", "session-log.md"]
    texts = {n: (pdir / n).read_text(encoding="utf-8")
             for n in names if (pdir / n).exists()}
    # hook 채널: <hub-root>/.claude/ui-events.jsonl
    ui_path = Path(args.hub_root) / ".claude" / "ui-events.jsonl"
    ui_events = ui_path.read_text(encoding="utf-8") if ui_path.exists() else ""
    code = 0 if (texts or ui_events) else 1
    C.emit(transform_session(texts, args.product, ui_events))
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
