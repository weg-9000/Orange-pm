#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""공통(G2-A/B) ↔ 제품 draft referenced_master 핀 drift 스캐너 (WP2 — C-PIN).

목적:
    G2-A/G2-B 공통 정책이 지속 갱신될 때, 이미 작성된 제품 draft 가 어느
    버전 기준인지 frontmatter `referenced_master: [{id}@{ver}, ...]` 핀으로
    추적한다. 본 스크립트는 핀 ↔ 현재 공통 버전을 대조해 drift 를
    티어드 분류하고 reports/drift-queue.md 를 생성한다.

    순수 스크립트(모델 미관여). 모델은 drift-queue.md 요약만 읽는다.
    공통 문서는 읽기 전용 — 절대 수정하지 않는다.

티어 정책 (gates/drift-gate.md SSoT):
    OK         : 핀 버전 == 현재 버전
    WARN       : minor/patch 상승 · 핀>현재 이상 · 버전 미상(mtime 폴백) · 핀 미해소
    BLOCK      : major 상승 (참조 §섹션 변경 정밀 검출은 스냅샷 한계로 미지원 — 보수적)
    (빈 referenced_master = 공통 미참조 → drift 아님, 정보로만 집계.
     opt-out 정당성은 master-derivation-gate 소관)

공통 메타 다중 포맷 파서:
    1) YAML frontmatter  : `version:` / `doc_id:` / `last_updated:`
    2) bold inline       : `**버전:** 1.2.0` / `**문서 ID:** \`X\`` / `**최종 업데이트:** ...`
    3) markdown table    : `| **doc_id** | \`X\` |` / `| **version** | ... |`
    + 핀ID 해소: (a) CONTEXT/reference-docs/master-id-map.yml 별칭맵(있으면)
                 (b) 추출 doc_id 정확 일치  (c) 파일명/헤딩 부분 일치  (d) 미해소→WARN

사용법:
    python drift_scan.py --hub-root <Hub> [--product <name>]
    (--product 생략 시 PROJECTS/* 전체)

exit code:
    0 = BLOCK drift 없음 (WARN/UNRESOLVED 는 비차단)
    1 = BLOCK drift 1건 이상 (drift-gate 차단 대상)
    2 = 인자 오류
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

# Windows 기본 콘솔(cp949 등)에서 비ASCII print 가 크래시하지 않도록 UTF-8 강제.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
PIN = re.compile(r"^\s*([^@\s]+)\s*@\s*v?([0-9][0-9.]*)\s*$")
VER_TOKEN = re.compile(r"v?([0-9]+(?:\.[0-9]+)*)")


def _parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER.match(text)
    if not m:
        return {}
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm


def _parse_list(raw) -> list[str]:
    if isinstance(raw, list):
        return raw
    raw = (raw or "").strip()
    if not raw or raw == "[]":
        return []
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [x.strip() for x in raw.split(",") if x.strip()]


def _extract_master_meta(path: Path) -> dict:
    """공통 문서 1개에서 doc_id / version / 갱신시각을 다중 포맷으로 추출."""
    text = path.read_text(encoding="utf-8", errors="replace")
    head = text[:4000]
    doc_id = ""
    version = ""
    updated = ""

    fm = _parse_frontmatter(text)
    if fm:
        doc_id = fm.get("doc_id", "") or doc_id
        version = fm.get("version", "") or version
        updated = fm.get("last_updated", "") or updated

    # bold/table 포맷은 라벨과 닫는 ** 사이/밖 어디에든 콜론이 올 수 있다
    # (실측: `**문서 ID:** \`X\``, `**버전:** 1.2.0`, `| **doc_id** | \`X\` |`).
    if not doc_id:
        m = (re.search(r"\*\*\s*(?:문서\s*ID|doc_id)\s*[:：]?\s*\*\*\s*[:：]?\s*`?([A-Za-z0-9._-]+)`?", head, re.I)
             or re.search(r"\|\s*\*\*\s*doc_id\s*\*\*\s*\|\s*`?([A-Za-z0-9._-]+)`?", head, re.I))
        if m:
            doc_id = m.group(1).strip()
    if not version:
        m = (re.search(r"\*\*\s*(?:버전|version)\s*[:：]?\s*\*\*\s*[:：]?\s*`?([0-9]+(?:\.[0-9]+)*)`?", head, re.I)
             or re.search(r"\|\s*\*\*\s*(?:버전|version)\s*\*\*\s*\|\s*`?([0-9]+(?:\.[0-9]+)*)`?", head, re.I))
        if m:
            version = m.group(1).strip()
    if not updated:
        m = re.search(r"\*\*최종\s*업데이트\*\*\s*[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", head)
        if m:
            updated = m.group(1)

    # 계층 추출 — PREFIX 비종속(동적). 본문 `[G2-B]` 형 라벨 또는 경로에서 추출.
    # 경로는 신규 중첩(`reference-docs/{PREFIX}/B/`)·레거시 평면(`reference-docs/B/`) 모두 수용.
    layer = ""
    lm = (re.search(r"\[([A-Za-z0-9]+-[ABC])\]", head)
          or re.search(r"reference-docs[/\\](?:[A-Za-z0-9]+[/\\])?([ABC])[/\\]", str(path)))
    if lm:
        layer = lm.group(1)

    return {
        "path": path,
        "stem": path.stem,
        "doc_id": doc_id,
        "version": version,
        "updated": updated,
        "mtime": path.stat().st_mtime,
        "layer": layer,
    }


def _load_alias_map(hub_root: Path) -> dict:
    """선택적 별칭맵: CONTEXT/reference-docs/master-id-map.yml  (key: value 단순 파싱)."""
    p = hub_root / "CONTEXT" / "reference-docs" / "master-id-map.yml"
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


def _build_registry(hub_root: Path) -> list[dict]:
    """A/B/C 전 계층의 공통 문서 메타를 수집한다.

    듀얼 경로(점진 마이그레이션 안전망):
      - 신규 중첩: ``reference-docs/{PREFIX}/{A,B,C}/*.md`` (전 PREFIX 순회)
      - 레거시 평면: ``reference-docs/{A,B,C}/*.md``
    동일 파일이 양쪽에 잡히는 일은 없으나, 안전을 위해 resolve() 기준 중복 제거.
    """
    reg: list[dict] = []
    base = hub_root / "CONTEXT" / "reference-docs"
    if not base.is_dir():
        return reg

    search_dirs: list[Path] = [base / layer for layer in ("A", "B", "C")]  # 레거시 평면
    for prefix_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        search_dirs.extend(prefix_dir / layer for layer in ("A", "B", "C"))  # 신규 중첩

    seen: set[Path] = set()
    for d in search_dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            if f.name == "README.md":
                continue
            key = f.resolve()
            if key in seen:
                continue
            seen.add(key)
            reg.append(_extract_master_meta(f))
    return reg


def _resolve(pin_id: str, registry: list[dict], amap: dict) -> dict | None:
    if pin_id in amap:
        target = amap[pin_id]
        for e in registry:
            if e["stem"] == target or e["path"].name == target or e["doc_id"] == target:
                return e
    for e in registry:
        if e["doc_id"] and e["doc_id"] == pin_id:
            return e
    low = pin_id.lower()
    for e in registry:
        if low in e["stem"].lower() or (e["doc_id"] and low in e["doc_id"].lower()):
            return e
    return None


def _ver_tuple(v: str) -> tuple[int, ...] | None:
    m = VER_TOKEN.search(v or "")
    if not m:
        return None
    try:
        return tuple(int(x) for x in m.group(1).split("."))
    except ValueError:
        return None


def _classify(pinned: str, current: str, entry: dict) -> tuple[str, str]:
    pt, ct = _ver_tuple(pinned), _ver_tuple(current)
    if pt is None or ct is None:
        return "WARN", f"버전 파싱 불가(핀={pinned!r} 현재={current!r}) — mtime 폴백 권고"
    L = max(len(pt), len(ct))
    pt += (0,) * (L - len(pt))
    ct += (0,) * (L - len(ct))
    if pt == ct:
        return "OK", "핀 == 현재"
    if pt > ct:
        return "WARN", f"핀({pinned}) > 현재({current}) 이상 — 핀 표기 점검"
    idx = next(i for i in range(L) if pt[i] != ct[i])
    if idx == 0:
        return "BLOCK", f"major 상승 {pinned}→{current} — 재검증 필수"
    kind = "minor" if idx == 1 else "patch"
    return "WARN", f"{kind} 상승 {pinned}→{current} — 재검증 권고(비차단)"


def scan(hub_root: Path, product: str | None = None) -> int:
    registry = _build_registry(hub_root)
    amap = _load_alias_map(hub_root)
    projects_root = hub_root / "PROJECTS"
    if not projects_root.is_dir():
        print(f"[drift_scan] PROJECTS 없음: {projects_root} — 스캔 대상 없음")
        return 0

    products = (
        [projects_root / product]
        if product
        else sorted(p for p in projects_root.iterdir() if p.is_dir())
    )

    total_block = 0
    for proj in products:
        drafts_dir = proj / "drafts"
        if not drafts_dir.is_dir():
            continue
        rows: list[tuple] = []
        no_pin = 0
        for draft in sorted(drafts_dir.glob("*.draft.md")):
            fm = _parse_frontmatter(draft.read_text(encoding="utf-8", errors="replace"))
            pins = _parse_list(fm.get("referenced_master", []))
            if not pins:
                no_pin += 1
                continue
            for pin in pins:
                pm = PIN.match(pin)
                if not pm:
                    rows.append((draft.name, pin, "-", "WARN",
                                 "핀 형식 오류(기대: id@vX.Y[.Z])"))
                    continue
                pid, pver = pm.group(1), pm.group(2)
                entry = _resolve(pid, registry, amap)
                if entry is None:
                    rows.append((draft.name, pin, "-", "UNRESOLVED",
                                 f"'{pid}' reference-docs 해소 불가 — master-id-map.yml 등록 또는 핀 정정"))
                    continue
                cur = entry["version"] or ""
                if not cur:
                    rows.append((draft.name, pin,
                                 f"(버전미상, upd={entry['updated'] or '?'})",
                                 "WARN", f"{entry['path'].name} 버전 메타 없음 — mtime 폴백"))
                    continue
                status, reason = _classify(pver, cur, entry)
                if status == "BLOCK":
                    total_block += 1
                rows.append((draft.name, pin, cur, status, reason))

        # 완전판(C-RENDER 후자) rendered_from_master 핀 대조 (WP5 연계)
        rdir = proj / "reports" / "render"
        if rdir.is_dir():
            for comp in sorted(rdir.glob("*.complete.md")):
                cfm = _parse_frontmatter(
                    comp.read_text(encoding="utf-8", errors="replace"))
                rpins = _parse_list(cfm.get("rendered_from_master", []))
                if not rpins:
                    continue
                tag = f"render/{comp.name}"
                for pin in rpins:
                    if pin.strip().endswith("@v?") or "@v?" in pin:
                        rows.append((tag, pin, "-", "WARN",
                                     "[완전판] 전개 시점 버전 미상 — 소스 "
                                     "referenced_master 핀 후 재-render 권고"))
                        continue
                    pm = PIN.match(pin)
                    if not pm:
                        rows.append((tag, pin, "-", "WARN", "[완전판] 핀 형식 오류"))
                        continue
                    pid, pver = pm.group(1), pm.group(2)
                    entry = _resolve(pid, registry, amap)
                    if entry is None:
                        rows.append((tag, pin, "-", "UNRESOLVED",
                                     f"[완전판] '{pid}' 해소 불가 — master-id-map.yml"))
                        continue
                    cur = entry["version"] or ""
                    if not cur:
                        rows.append((tag, pin, "(버전미상)", "WARN",
                                     f"[완전판] {entry['path'].name} 버전 메타 없음"))
                        continue
                    status, reason = _classify(pver, cur, entry)
                    if status == "BLOCK":
                        total_block += 1
                    rows.append((tag, pin, cur, status,
                                 f"[완전판] {reason}"
                                 + (" — 재-render 필요" if status == "BLOCK" else "")))

        reports = proj / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        qpath = reports / "drift-queue.md"
        n_block = sum(1 for r in rows if r[3] == "BLOCK")
        n_warn = sum(1 for r in rows if r[3] in ("WARN", "UNRESOLVED"))
        lines = [
            f"# drift-queue — {proj.name}",
            "",
            f"> 생성: {datetime.now().isoformat(timespec='seconds')} · drift_scan.py 자동 생성(수정 금지)",
            f"> **BLOCK: {n_block} · WARN/UNRESOLVED: {n_warn} · 공통 미참조 draft: {no_pin}**",
            "",
            "| draft | 핀 | 현재 버전 | 상태 | 사유 |",
            "|---|---|---|---|---|",
        ]
        if rows:
            for d, pin, cur, st, why in rows:
                lines.append(f"| {d} | `{pin}` | {cur} | **{st}** | {why} |")
        else:
            lines.append("| _(drift 없음)_ | — | — | OK | 전 draft 핀 == 현재 |")
        lines += [
            "",
            "## 처리 기준 (gates/drift-gate.md)",
            "- BLOCK: 해당 draft 재검증 전 Phase 전진 차단",
            "- WARN/UNRESOLVED: 비차단, 다음 Phase 경계에서 일괄 재검증",
            "- 공통 미참조(핀 빈 목록): master-derivation-gate 에서 opt-out 정당성 확인",
        ]
        qpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[drift_scan] {proj.name}: BLOCK={n_block} WARN/UNRESOLVED={n_warn} "
              f"무참조={no_pin} → {qpath.relative_to(hub_root)}")

    print(f"[drift_scan] 완료 — 총 BLOCK {total_block}건"
          + ("" if total_block == 0 else " (drift-gate 차단)"))
    return 1 if total_block else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="공통↔draft referenced_master drift 스캔")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", default=None, help="PROJECTS/<product> (생략=전체)")
    ap.add_argument("--check", action="store_true",
                    help="(호환용) 동작 동일 — 항상 읽기 전용, drafts 미변경")
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    return scan(args.hub_root, args.product)


if __name__ == "__main__":
    sys.exit(main())
