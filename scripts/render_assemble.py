#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""C-RENDER 완전판(후자) 결정적 조립기 (WP5).

목적:
    소스 draft(전자: Delta + [{doc_id} §X 참조] 링크)를 입력받아 공통
    (G2-A/G2-B) 참조분을 **결정적 텍스트 치환**으로 인라인 전개한
    기획자 정본(후자)을 생성한다. 모델 미관여 — 공통 텍스트 재출력 없음
    (토큰 경계·SSoT 정확성). 공통는 읽기 전용.

해소 체인:
    [{ID} ... §{sec} 참조]  /  기본 정책 완전 적용 — [{ID} ...] 참조
      → master-id-map.yml(핀ID→파일 stem)
      → B-headings-index.json(stem 키 → path·sections 라인범위)
      → 공통 파일 해당 §라인 슬라이스를 출처 태그와 함께 인라인.
    G2-A 용어: terms.yml(파생 캐시)에서 본문 등장 canonical 정의를 부록 전개.

산출:
    reports/render/{WO_ID}.complete.md  (단일)
    reports/render/{product}.full.complete.md  (--all)
    frontmatter rendered_from_master: [{id}@{version}] 핀 →
      drift_scan.py 가 완전판 stale 도 대조(WP5 연계).

사용법:
    python render_assemble.py --hub-root <Hub> --product <p> [--wo <WO_ID>] [--all]

exit code: 0 성공 / 1 입력 없음·치명 / 2 인자 오류
"""
from __future__ import annotations

import argparse
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
PIN = re.compile(r"^\s*([^@\s]+)\s*@\s*v?([0-9][0-9.]*)\s*$")
WHOLE_REF = re.compile(r"기본 정책 완전 적용\s*[—\-]\s*\[([^\]]+)\]\s*참조")
SEC_REF = re.compile(r"\[([^\]\n]+?)\]\s*§?\s*([A-Za-z0-9][\w.\-]*)?\s*참조")
ID_TOKEN = re.compile(r"([A-Za-z0-9]+-[ABC]-\d+|PLATFORM\.[A-Za-z.]+|common\.[\w.\-]+|[A-Za-z0-9_\-]+)")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = FRONTMATTER.match(text)
    if not m:
        return {}, text
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, text[m.end():]


def _parse_list(raw) -> list[str]:
    if isinstance(raw, list):
        return raw
    raw = (raw or "").strip()
    if not raw or raw == "[]":
        return []
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [x.strip() for x in raw.split(",") if x.strip()]


def _load_alias_map(hub: Path) -> dict:
    p = hub / "CONTEXT" / "reference-docs" / "master-id-map.yml"
    amap: dict = {}
    if not p.exists():
        return amap
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        amap[k.strip()] = v.strip().strip("'\"")
    return amap


def _active_prefix(hub: Path) -> str | None:
    cfg = hub / "CONTEXT" / "layer-config.md"
    if not cfg.exists():
        return None
    text = cfg.read_text(encoding="utf-8", errors="replace")
    m = (re.search(r"^ACTIVE_PREFIX:\s*([A-Za-z0-9_-]+)\s*$", text, re.M)
         or re.search(r"^PREFIX:\s*([A-Za-z0-9_-]+)\s*$", text, re.M))
    return m.group(1) if m else None


def _load_b_index(hub: Path) -> dict:
    cache_dir = hub / "CONTEXT" / ".template-cache"
    # PREFIX 네임스페이스 인덱스 우선, 없으면 레거시 무네임스페이스로 폴백.
    prefix = _active_prefix(hub)
    candidates = []
    if prefix:
        candidates.append(cache_dir / f"{prefix}-b-headings-index.json")
    candidates.append(cache_dir / "B-headings-index.json")
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8")).get("documents", {})
            except Exception:
                return {}
    return {}


def _load_terms(hub: Path) -> list[tuple[str, str]]:
    p = hub / "CONTEXT" / "glossary" / "terms.yml"
    if not p.exists():
        return []
    out: list[tuple[str, str]] = []
    cur = None
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        m = re.match(r"-\s*canonical_name\s*:\s*(.+)$", s)
        if m:
            cur = m.group(1).strip().strip("'\"")
            continue
        m = re.match(r"definition\s*:\s*(.+)$", s)
        if m and cur:
            out.append((cur, m.group(1).strip().strip("'\"")))
            cur = None
    return out


def _resolve_doc(token: str, amap: dict, bidx: dict) -> dict | None:
    stem = amap.get(token)
    if stem:
        for k, e in bidx.items():
            if k == stem or e.get("doc_id") == stem or Path(e.get("path", "")).stem == stem:
                return e
    if token in bidx:
        return bidx[token]
    for k, e in bidx.items():
        if e.get("doc_id") == token:
            return e
    low = token.lower()
    for k, e in bidx.items():
        if low in k.lower() or low in str(e.get("doc_id", "")).lower():
            return e
    return None


def _section_text(hub: Path, entry: dict, sec: str | None) -> tuple[str, str]:
    """(추출 텍스트, 라벨). sec 없으면 문서 전체(상한 400줄)."""
    fp = hub / entry["path"]
    if not fp.exists():
        return f"⚠️ 공통 파일 없음: {entry['path']}", "MISSING"
    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
    if sec:
        def _norm(x: str) -> str:
            return re.sub(r"[\s.\-]+", "", str(x)).lower()
        nsec = _norm(sec)
        secs = entry.get("sections", [])
        # 1) id 정확 일치  2) 제목 정규화 prefix/포함 (실측 공통는 A/B/B-1 알파섹션)
        for s in secs:
            if s["id"] == sec:
                seg = lines[s["line_start"] - 1: s["line_end"]]
                return "\n".join(seg).strip(), f"§{sec} {s.get('title','')}".strip()
        for s in secs:
            nt = _norm(s.get("title", ""))
            if nsec and (nt.startswith(nsec) or nsec in nt):
                seg = lines[s["line_start"] - 1: s["line_end"]]
                return "\n".join(seg).strip(), f"§{sec} {s.get('title','')}".strip()
        return (f"⚠️ §{sec} 미발견 — B-headings-index 갱신(build_b_index.py) "
                f"또는 핀·§표기 정정 필요", f"§{sec} (미발견)")
    seg = lines[:400]
    tail = "" if len(lines) <= 400 else "\n\n…(이하 생략 — 전체는 공통 원문 참조)"
    return "\n".join(seg).strip() + tail, "전체"


def _pin_version(token: str, pins: list[str], amap: dict) -> str:
    for p in pins:
        m = PIN.match(p)
        if not m:
            continue
        pid = m.group(1)
        if pid == token or amap.get(pid) == amap.get(token) or amap.get(token) == pid:
            return m.group(2)
    return "?"


def assemble_one(hub: Path, draft: Path, amap: dict, bidx: dict,
                 terms: list[tuple[str, str]]) -> tuple[str, list[str]]:
    raw = draft.read_text(encoding="utf-8", errors="replace")
    fm, body = _parse_frontmatter(raw)
    pins = _parse_list(fm.get("referenced_master", []))
    rendered_from: set[str] = set()

    def _inline(token_raw: str, sec: str | None) -> str:
        tok_m = ID_TOKEN.match(token_raw.strip())
        token = tok_m.group(1) if tok_m else token_raw.strip().split()[0]
        entry = _resolve_doc(token, amap, bidx)
        if entry is None:
            return (f"\n> ⟦전개 실패: '{token}' 해소 불가 — master-id-map.yml "
                    f"등록 또는 핀 정정 필요⟧\n")
        text, label = _section_text(hub, entry, sec)
        ver = _pin_version(token, pins, amap)
        rendered_from.add(f"{token}@v{ver}")
        return (f"\n> ⟦전개: {token}@v{ver} {label} — 출처 {entry['path']} "
                f"(자동 인라인, 수정은 소스에서)⟧\n\n{text}\n\n> ⟦/전개⟧\n")

    body = WHOLE_REF.sub(lambda m: _inline(m.group(1), None), body)
    body = SEC_REF.sub(lambda m: _inline(m.group(1), m.group(2)), body)

    used_terms = [(c, d) for (c, d) in terms if c and c in body]
    appendix = ""
    if used_terms:
        term_doc = f"{_active_prefix(hub) or 'PX'}-A-001"
        appendix = f"\n\n---\n\n## 부록 A. 용어 정의 ({term_doc} 전개)\n\n"
        appendix += "\n".join(f"- **{c}**: {d}" for c, d in used_terms[:80])
        rendered_from.add(f"{term_doc}@v?")

    rf = sorted(rendered_from)
    wo_id = fm.get("doc_id") or draft.stem.replace(".draft", "")
    header = (
        "---\n"
        f"source_doc_id: {wo_id}\n"
        f"type: {fm.get('type','')}\n"
        f"rendered_at: {datetime.now().isoformat(timespec='seconds')}\n"
        f"rendered_by: render_assemble.py (C-RENDER, 결정적·모델 미관여)\n"
        f"rendered_from_master: [{', '.join(rf)}]\n"
        f"source_referenced_master: [{', '.join(pins)}]\n"
        "---\n\n"
        "> **자동 전개 정본 뷰 (C-RENDER)** — render_assemble.py 가 소스 draft +\n"
        "> 공통(G2-A/B)를 결정적으로 인라인 전개한 기획자 정본이다.\n"
        "> 직접 수정 금지(이중 작성=SSoT 붕괴). 수정은 소스(/write·/flow)에서.\n"
        "> 공통 version↑ 시 drift_scan 이 stale 표시 → 재-render 필요.\n\n"
        "---\n"
    )
    return header + body + appendix + "\n", rf


def main() -> int:
    ap = argparse.ArgumentParser(description="C-RENDER 완전판 결정적 조립")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", required=True)
    ap.add_argument("--wo", default=None, help="단일 WO_ID (생략=전체 draft)")
    ap.add_argument("--all", action="store_true", help="추가로 {product}.full.complete.md 생성")
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2

    hub = args.hub_root
    proj = hub / "PROJECTS" / args.product
    drafts_dir = proj / "drafts"
    if not drafts_dir.is_dir():
        sys.stderr.write(f"drafts not found: {drafts_dir}\n")
        return 1

    amap = _load_alias_map(hub)
    bidx = _load_b_index(hub)
    terms = _load_terms(hub)
    if not bidx:
        print("[render_assemble] WARN: B-headings-index.json 없음 — "
              "build_b_index.py 실행 권고. §참조 인라인 제한됨")

    targets = (
        [drafts_dir / f"{args.wo}.draft.md"] if args.wo
        else sorted(drafts_dir.glob("*.draft.md"))
    )
    targets = [t for t in targets if t.exists()]
    if not targets:
        sys.stderr.write("대상 draft 없음\n")
        return 1

    out_dir = proj / "reports" / "render"
    out_dir.mkdir(parents=True, exist_ok=True)
    full_parts: list[str] = []
    for d in targets:
        doc, rf = assemble_one(hub, d, amap, bidx, terms)
        wo = d.stem.replace(".draft", "")
        (out_dir / f"{wo}.complete.md").write_text(doc, encoding="utf-8")
        full_parts.append(f"\n\n<!-- ===== {wo} ===== -->\n\n" + doc)
        print(f"[render_assemble] {wo}.complete.md ← rendered_from_master={rf or '[]'}")

    if args.all and not args.wo:
        (out_dir / f"{args.product}.full.complete.md").write_text(
            "".join(full_parts), encoding="utf-8")
        print(f"[render_assemble] {args.product}.full.complete.md ({len(targets)} draft)")

    print(f"[render_assemble] 완료 — {len(targets)}건 → "
          f"{(out_dir).relative_to(hub)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
