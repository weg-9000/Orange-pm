#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""정책§ → 화면 영향 스캐너 (WP8-2 · 계약 C-PIMPACT).

목적:
    제품 정책서(POL draft)의 특정 §섹션이 변경됐을 때, 그 §를 참조하는
    화면 draft(S0N)를 §단위로 식별한다. 공통→제품 drift(drift_scan)의
    제품-내부 사촌 — 메커니즘은 §content-hash 스냅샷 diff(버전 아님).

    순수 스크립트(모델 미관여). 모델은 policy-impact-queue.md 요약만 읽는다.
    POL·screen draft 를 수정하지 않는다(읽기 전용 + 큐/스냅샷 산출만).

판정 (gates/policy-impact-gate.md SSoT):
    IMPACT  : 화면 참조 § ∩ 변경 § ≠ ∅ (정밀) → BLOCK
    COARSE  : §정밀 불가하나 referenced_policy 핀 version < POL 현재 → WARN
    WARN    : referenced_policy 핀 누락 / [[POL §X]] 비표준 마커(UNRESOLVED)
    OK      : 참조 § 중 변경 없음 & 핀 version 일치
    BASELINE: 스냅샷 부재 첫 실행 → 스냅샷 생성·판정 보류(INFO)

스냅샷: graph/policy-section-hashes.json (마지막 정합 기준).
재기준선: PM 이 화면 정합 완료 후 --rebaseline 로 현재 상태 재기록.

사용법:
    python policy_impact_scan.py --hub-root <Hub> --product <p> [--rebaseline]

exit code: 0 IMPACT 없음 / 1 IMPACT≥1(게이트 차단) / 2 인자오류
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
HEADING = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
# §id 토큰(섹션형만 추적): 4 / 4-1 / 4.1 / 4-1(3) / 4-6-2 / A / B-1.
# 비-§ 헤딩(목차·Workflow·부록·P1 등)은 토큰 미매치 → 미추적(노이즈 제거).
SEC_TOKEN = re.compile(
    r"^(?:§\s*)?("
    r"\d+(?:[-.]\d+)*(?:\([0-9A-Za-z]+\))?"   # 4, 4-1, 4.1, 4-6-2, 4-1(3)
    r"|[A-Z](?:-\d+)?"                          # A, B, B-1
    r")(?=[\s.\)]|$)"
)
POL_MARKER = re.compile(r"\[\[\s*POL\s*§?\s*([A-Za-z0-9][\w.\-()]*?)\s*\]\]")
VER = re.compile(r"v?([0-9]+(?:\.[0-9]+)*)")
VER_LINE = re.compile(r"(?:\*\*\s*버전\s*[:：]?\s*\*\*|^version\s*:|\*\*\s*version\s*[:：]?\s*\*\*)"
                      r"\s*[:：]?\s*`?v?([0-9]+(?:\.[0-9]+)*)`?", re.I | re.M)


def _norm(s: str) -> str:
    """§id 정규화 — 구분자(-.()) 보존(6-2 vs 4-6-2 vs 6.2 충돌 방지).
    공백·§·앞뒤 마침표만 제거하고 소문자화."""
    return str(s).strip().strip(".").replace("§", "").replace(" ", "").lower()


def _frontmatter(text: str) -> tuple[dict, str]:
    m = FRONTMATTER.match(text)
    if not m:
        return {}, text
    fm = {}
    for ln in m.group(1).splitlines():
        if ":" in ln:
            k, _, v = ln.partition(":")
            fm[k.strip()] = v.strip()
    return fm, text[m.end():]


def _ver_tuple(v: str):
    m = VER.search(v or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def _pol_version(text: str, fm: dict) -> str:
    if fm.get("version"):
        return fm["version"]
    m = VER_LINE.search(text[:4000])
    return m.group(1) if m else ""


def _sections(text: str) -> dict:
    """POL 본문 §섹션 → {norm_id: {title, hash}} (build_b_index 식 파싱)."""
    lines = text.splitlines()
    heads = []
    for i, ln in enumerate(lines):
        m = HEADING.match(ln)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    out = {}
    for hi, (li, depth, title) in enumerate(heads):
        tok = SEC_TOKEN.match(title)
        if not tok:
            continue  # 비-§ 헤딩(목차·Workflow·부록·P1 등) 미추적 — 노이즈 제거
        end = len(lines)
        for nj, nd, _ in heads[hi + 1:]:
            if nd <= depth:
                end = nj
                break
        sid = tok.group(1)
        key = _norm(sid)
        if key in out:                       # norm 충돌 시 덮어쓰기 금지
            n = 2
            while f"{key}#{n}" in out:
                n += 1
            key = f"{key}#{n}"
        body = "\n".join(lines[li:end]).strip()
        h = hashlib.sha256(body.encode("utf-8", "replace")).hexdigest()[:12]
        out[key] = {"raw_id": sid, "title": title[:80], "hash": h}
    return out


def _policy_drafts(drafts: Path):
    pol = []
    for d in sorted(drafts.glob("*.draft.md")):
        if "POL" in d.stem.upper():
            pol.append(d)
            continue
        fm, _ = _frontmatter(d.read_text(encoding="utf-8", errors="replace"))
        if fm.get("type") == "policy":
            pol.append(d)
    return pol


def scan(hub: Path, product: str, rebaseline: bool) -> int:
    proj = hub / "PROJECTS" / product
    drafts = proj / "drafts"
    if not drafts.is_dir():
        sys.stderr.write(f"drafts not found: {drafts}\n")
        return 2

    pol_drafts = _policy_drafts(drafts)
    cur_secs: dict = {}
    pol_version = ""
    for pd in pol_drafts:
        raw = pd.read_text(encoding="utf-8", errors="replace")
        fm, body = _frontmatter(raw)
        pol_version = pol_version or _pol_version(raw, fm)
        for k, v in _sections(body or raw).items():
            v["src"] = pd.name
            cur_secs[k] = v

    snap_path = proj / "graph" / "policy-section-hashes.json"
    snap_path.parent.mkdir(parents=True, exist_ok=True)

    if rebaseline or not snap_path.exists():
        snap_path.write_text(json.dumps({
            "_meta": {"product": product, "policy_version": pol_version,
                      "generated_at": datetime.now().isoformat(timespec="seconds"),
                      "source_drafts": [p.name for p in pol_drafts]},
            "sections": cur_secs,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[policy_impact_scan] {'재기준선' if rebaseline else 'baseline 생성'}"
              f" — {len(cur_secs)} §, v{pol_version or '?'} → {snap_path.relative_to(hub)}")
        if not rebaseline:
            print("[policy_impact_scan] 첫 실행: IMPACT 판정 보류(BASELINE).")
        return 0

    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    snap_secs = snap.get("sections", {})
    snap_ver = snap.get("_meta", {}).get("policy_version", "")
    changed = {k for k, v in cur_secs.items()
               if k not in snap_secs or snap_secs[k]["hash"] != v["hash"]}
    changed |= {k for k in snap_secs if k not in cur_secs}

    rows = []
    impact_n = 0
    for sd in sorted(drafts.glob("*.draft.md")):
        if sd in pol_drafts:
            continue
        raw = sd.read_text(encoding="utf-8", errors="replace")
        fm, body = _frontmatter(raw)
        if fm.get("type") and fm["type"] != "screen":
            continue
        refs = {_norm(m) for m in POL_MARKER.findall(body or raw)}
        pin = fm.get("referenced_policy", "")
        pin_ver = pin.split("@")[-1].lstrip("v@ ") if "@" in pin else ""
        if not refs and "[[POL" not in (body or raw) and "POL §" not in (body or raw):
            rows.append((sd.name, pin or "-", "—", "WARN",
                         "정책 §참조 마커 없음 — [[POL §X-Y]] 표준 마커 필요"))
            continue
        hit = sorted(refs & changed)
        if hit:
            impact_n += 1
            raw_hits = ", ".join(cur_secs.get(h, {}).get("raw_id", h) for h in hit)
            rows.append((sd.name, pin or "(핀없음)", f"변경§ {raw_hits}",
                         "IMPACT", "참조 정책 §변경 — 화면 재검토·재정합 필수"))
            continue
        if not pin:
            rows.append((sd.name, "(핀없음)", f"참조 {len(refs)}§", "WARN",
                         "referenced_policy 핀 누락 — C-PIMPACT 추적 불가"))
            continue
        pv, cv = _ver_tuple(pin_ver), _ver_tuple(pol_version)
        if pv and cv and pv < cv:
            rows.append((sd.name, pin, f"참조 {len(refs)}§", "COARSE",
                         f"핀 v{pin_ver} < POL v{pol_version} — §정밀 변경무, "
                         f"version 폴백 재검토 권고"))
            continue
        rows.append((sd.name, pin, f"참조 {len(refs)}§", "OK",
                     "참조 § 변경 없음 & 핀 일치"))

    qdir = proj / "reports"
    qdir.mkdir(parents=True, exist_ok=True)
    q = qdir / "policy-impact-queue.md"
    n_w = sum(1 for r in rows if r[3] in ("WARN", "COARSE"))
    lines = [
        f"# policy-impact-queue — {product}",
        "",
        f"> 생성: {datetime.now().isoformat(timespec='seconds')} · policy_impact_scan.py (수정 금지)",
        f"> POL v{pol_version or '?'} vs 스냅샷 v{snap_ver or '?'} · "
        f"변경 §: {len(changed)} · **IMPACT: {impact_n} · WARN/COARSE: {n_w}**",
        "",
        "| 화면 draft | referenced_policy | 참조/변경 § | 상태 | 사유 |",
        "|---|---|---|---|---|",
    ]
    if rows:
        for d, p, s, st, why in rows:
            lines.append(f"| {d} | `{p}` | {s} | **{st}** | {why} |")
    else:
        lines.append("| _(screen draft 없음)_ | — | — | OK | — |")
    lines += [
        "",
        "## 처리 기준 (gates/policy-impact-gate.md)",
        "- IMPACT(정밀): 해당 화면 재정합 전 Phase 전진 차단. 정합 후 --rebaseline",
        "- COARSE(version 폴백): 비차단 WARN — §정밀 변경 없음, 핀 version 갱신 권고",
        "- WARN: [[POL §X-Y]] 표준 마커·referenced_policy 핀 보강",
        f"- 변경 §목록: {', '.join(sorted(cur_secs.get(c,{}).get('raw_id',c) for c in changed)) or '없음'}",
    ]
    q.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[policy_impact_scan] {product}: IMPACT={impact_n} WARN/COARSE={n_w} "
          f"변경§={len(changed)} → {q.relative_to(hub)}")
    print(f"[policy_impact_scan] 완료 — IMPACT {impact_n}건"
          + ("" if impact_n == 0 else " (policy-impact-gate 차단)"))
    return 1 if impact_n else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="정책§→화면 영향 스캔 (C-PIMPACT)")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", required=True)
    ap.add_argument("--rebaseline", action="store_true",
                    help="현재 POL §해시를 정합 기준 스냅샷으로 재기록(PM 정합 완료 후)")
    a = ap.parse_args()
    if not a.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {a.hub_root}\n")
        return 2
    return scan(a.hub_root, a.product, a.rebaseline)


if __name__ == "__main__":
    sys.exit(main())
