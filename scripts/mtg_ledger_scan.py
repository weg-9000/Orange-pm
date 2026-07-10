#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""회의 결정 원장 ↔ 화면 핀 결정적 교차검증 (WP8-4 · 계약 C-MTG).

목적:
    `meetings/mtg-ledger.md`(PM 정본)와 screen draft frontmatter
    `meeting_decisions: [MTG-NN]` 핀을 **결정적으로 교차검증만** 한다.
    회의록 산문에서 분류·요약을 **자동 생성/추출하지 않는다**(환각·C5 위반).
    원장은 PM 이 작성하며, 본 스크립트는 읽기·검증·큐 산출만.

검사 (전부 결정적):
    - SCREEN-DELEGATED 행:
        · open + 어떤 screen 도 meeting_decisions 에 미반영 → BLOCK(위임 미반영)
        · open + 기한(YYYY-MM-DD) < 오늘 → WARN(기한초과)
        · closed + 종결근거 공란 또는 미반영 → WARN(종결 불완전)
    - screen meeting_decisions 의 MTG-NN:
        · 원장에 없음 → FAIL(미등재 MTG 주장)
        · 원장에 있으나 분류 ≠ SCREEN-DELEGATED → WARN(오분류 주장)
    원장 부재 → INFO(미작성 — PM 작성 권고). 자동 생성 안 함.

사용법:
    python mtg_ledger_scan.py --hub-root <Hub> --product <p>

exit code: 0 BLOCK/FAIL 없음 / 1 BLOCK·FAIL≥1(게이트 차단) / 2 인자오류
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
MTG_ID = re.compile(r"^MTG-\d+$")
DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
CLASSES = {"POLICY-REFLECTED", "SCREEN-DELEGATED", "EXTERNAL-PENDING"}


def _fm(text: str) -> dict:
    m = FRONTMATTER.match(text)
    if not m:
        return {}
    d = {}
    for ln in m.group(1).splitlines():
        if ":" in ln:
            k, _, v = ln.partition(":")
            d[k.strip()] = v.strip()
    return d


def _list(raw) -> list[str]:
    raw = (raw or "").strip()
    if not raw or raw == "[]":
        return []
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [x.strip() for x in raw.split(",") if x.strip()]


def _parse_ledger(p: Path) -> list[dict]:
    """고정 7열 파이프 표에서 MTG 행 추출(위치 기반). 헤더·구분행 스킵."""
    rows = []
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cols = [c.strip() for c in s.strip("|").split("|")]
        if not cols or not MTG_ID.match(cols[0]):
            continue
        # 0:ID 1:출처 2:요약 3:분류 4:대상 5:상태 6:종결근거
        c = cols + [""] * (7 - len(cols))
        rows.append({
            "id": c[0], "src": c[1], "summary": c[2],
            "cls": c[3].upper(), "target": c[4],
            "status": c[5].lower(), "closure": c[6],
        })
    return rows


def scan(hub: Path, product: str) -> int:
    proj = hub / "PROJECTS" / product
    drafts = proj / "drafts"
    ledger = proj / "meetings" / "mtg-ledger.md"
    if not drafts.is_dir():
        sys.stderr.write(f"drafts not found: {drafts}\n")
        return 2

    qdir = proj / "reports"
    qdir.mkdir(parents=True, exist_ok=True)
    q = qdir / "mtg-queue.md"

    if not ledger.exists():
        q.write_text(
            f"# mtg-queue — {product}\n\n"
            f"> 생성: {datetime.now().isoformat(timespec='seconds')} · mtg_ledger_scan.py\n"
            f"> **INFO: mtg-ledger 미작성** — `meetings/mtg-ledger.md` 를 PM 이 "
            f"작성해야 C-MTG 추적 가능(템플릿: templates/mtg-ledger-template.md). "
            f"자동 생성하지 않음(환각 금지).\n",
            encoding="utf-8")
        print(f"[mtg_ledger_scan] {product}: ledger 미작성 — INFO(자동생성 안 함)")
        return 0

    led = _parse_ledger(ledger)
    led_ids = {r["id"]: r for r in led}

    # screen meeting_decisions 수집
    screen_pins: dict[str, list[str]] = {}   # MTG-ID → [draft...]
    for sd in sorted(drafts.glob("*.draft.md")):
        fm = _fm(sd.read_text(encoding="utf-8", errors="replace"))
        if fm.get("type") and fm["type"] != "screen":
            continue
        for mid in _list(fm.get("meeting_decisions", [])):
            screen_pins.setdefault(mid, []).append(sd.name)

    today = date.today()
    rows = []
    block = fail = 0

    for r in led:
        if r["cls"] not in CLASSES:
            rows.append((r["id"], r["cls"] or "(공란)", "WARN",
                         "분류 enum 아님(POLICY-REFLECTED/SCREEN-DELEGATED/EXTERNAL-PENDING)"))
            continue
        if r["cls"] != "SCREEN-DELEGATED":
            continue
        reflected = screen_pins.get(r["id"], [])
        if r["status"] != "closed" and not reflected:
            block += 1
            rows.append((r["id"], "SCREEN-DELEGATED", "BLOCK",
                         f"위임 open 미반영 — 어떤 screen 도 meeting_decisions 에 "
                         f"{r['id']} 핀 없음 (대상: {r['target'] or '?'})"))
            continue
        dm = DATE.search(r["target"])
        if r["status"] != "closed" and dm:
            try:
                dl = datetime.strptime(dm.group(1), "%Y-%m-%d").date()
                if dl < today:
                    rows.append((r["id"], "SCREEN-DELEGATED", "WARN",
                                 f"기한초과({dm.group(1)}) open — 반영: "
                                 f"{', '.join(reflected) or '없음'}"))
                    continue
            except ValueError:
                pass
        if r["status"] == "closed" and (not r["closure"] or not reflected):
            rows.append((r["id"], "SCREEN-DELEGATED", "WARN",
                         f"closed 이나 종결근거 공란 또는 화면 미반영 "
                         f"(근거:'{r['closure'] or '-'}' / 반영:{reflected or '없음'})"))
            continue
        rows.append((r["id"], "SCREEN-DELEGATED", "OK",
                     f"반영: {', '.join(reflected)} / 상태 {r['status']}"))

    for mid, ds in sorted(screen_pins.items()):
        if mid not in led_ids:
            fail += 1
            rows.append((mid, "(원장없음)", "FAIL",
                         f"화면 {', '.join(ds)} 이 미등재 {mid} 주장 — 원장 등재 필요"))
        elif led_ids[mid]["cls"] != "SCREEN-DELEGATED":
            rows.append((mid, led_ids[mid]["cls"], "WARN",
                         f"화면 {', '.join(ds)} 주장이나 원장 분류={led_ids[mid]['cls']} "
                         f"(SCREEN-DELEGATED 아님)"))

    n_w = sum(1 for r in rows if r[2] == "WARN")
    lines = [
        f"# mtg-queue — {product}",
        "",
        f"> 생성: {datetime.now().isoformat(timespec='seconds')} · mtg_ledger_scan.py (수정 금지)",
        f"> 원장 {len(led)}행 · screen 핀 {sum(len(v) for v in screen_pins.values())}건 · "
        f"**BLOCK: {block} · FAIL: {fail} · WARN: {n_w}**",
        "",
        "| MTG-ID | 분류 | 상태 | 사유 |",
        "|---|---|---|---|",
    ]
    if rows:
        for i, cls, st, why in rows:
            lines.append(f"| {i} | {cls} | **{st}** | {why} |")
    else:
        lines.append("| _(SCREEN-DELEGATED 없음)_ | — | OK | — |")
    lines += [
        "",
        "## 처리 기준 (gates/mtg-gate.md)",
        "- BLOCK: SCREEN-DELEGATED open 미반영 → 대응 화면 반영 전 Phase 전진 차단",
        "- FAIL: 화면이 미등재 MTG 주장 → 원장 등재(PM) 또는 핀 정정",
        "- WARN: 기한초과/종결 불완전/오분류 — 비차단, PM 확인",
        "- INFO: 원장 미작성 — PM 작성(자동 생성 안 함, 환각 금지)",
    ]
    q.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[mtg_ledger_scan] {product}: BLOCK={block} FAIL={fail} WARN={n_w} "
          f"→ {q.relative_to(hub)}")
    print(f"[mtg_ledger_scan] 완료 — 차단 {block + fail}건"
          + ("" if block + fail == 0 else " (mtg-gate 차단)"))
    return 1 if (block + fail) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="회의 원장↔화면 핀 교차검증 (C-MTG)")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", required=True)
    a = ap.parse_args()
    if not a.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {a.hub_root}\n")
        return 2
    return scan(a.hub_root, a.product)


if __name__ == "__main__":
    sys.exit(main())
