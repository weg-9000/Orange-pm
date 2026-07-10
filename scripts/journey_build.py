#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""journey_build — draft 산출물에서 표준 스토리보드를 결정적으로 생성 (자동화 빌더).

/journey 스킬(LLM)의 결정적 부분(화면 순서 재구성·draft 상태 수집)을 스크립트화한다.
PostToolUse 훅(--from-hook)이 drafts/*.draft.md 편집을 감지할 때마다 자동 실행되어
`reports/journey-latest.md` 를 갱신한다 — viz 프로토타입 뷰의 사용자 여정이
수동 /journey 호출 없이도 상시 최신으로 유지된다.

역할 분담:
    journey_build.py (자동)  — 표준 storyboard: 순서·상태·전환 골격 (LLM 토큰 0)
    /journey 스킬 (수동)     — --actor 필터·핵심 행동/전환 조건 서사 보강
    journey_emit.py          — 최신 journey-*.md → viz JSON (mtime 기준)

산출 형식은 skills/journey/SKILL.md 단계 4·5 와 동일 — journey_emit 이 그대로 파싱한다.
자동 생성본은 session-log 에 기록하지 않는다(편집마다 비대해지는 것을 방지).

CLI:
    python journey_build.py --hub-root <Hub> --product <name> [--output <path>]
    python journey_build.py --from-hook        # PostToolUse 페이로드(stdin) 모드
exit: 0 정상(또는 hook dormant) / 1 화면 소스 없음 / 2 인자 오류
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

ICONS = {"done": "✅", "draft": "📝", "sketch": "🔲", "todo": "⬜"}
OUTPUT_NAME = "journey-latest.md"

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
SCR_ID = re.compile(r"\b([A-Z]{2,}-\d+)\b")
SECTION2 = re.compile(r"^#{2,3}\s*§?\s*2\b.*$", re.MULTILINE)
HEADING = re.compile(r"^#{2,3}\s", re.MULTILINE)

HUB_MARKERS = (
    Path("CONTEXT") / "layer-config.md",
    Path("CONTEXT") / "_session-bootstrap.md",
)
DRAFT_PATH_RE = re.compile(
    r"PROJECTS[/\\](?P<product>[^/\\]+)[/\\]drafts[/\\][^/\\]+\.draft\.md$"
)


def _parse_frontmatter(text: str) -> dict:
    """평탄 key:value 파서 — nested 키(cluster.cluster_id 등)도 평탄화해 잡는다."""
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


def _extract_screen_items(text: str) -> list[str]:
    """draft 본문 §2 화면 섹션의 최상위 불릿 항목."""
    m = FRONTMATTER.match(text)
    body = text[m.end():] if m else text
    sec = SECTION2.search(body)
    if not sec:
        return []
    rest = body[sec.end():]
    nxt = HEADING.search(rest)
    section = rest[: nxt.start()] if nxt else rest
    items: list[str] = []
    for ln in section.splitlines():
        if re.match(r"^[-*]\s+\S", ln):
            items.append(re.sub(r"^[-*]\s+", "", ln).strip())
    return items


def _draft_status(fm: dict, has_items: bool) -> str:
    """SKILL.md 단계 2 — dossier draft 상태 → done/draft/todo."""
    rs = fm.get("review_status", "") or fm.get("status", "")
    if rs == "human-reviewed" or fm.get("reviewed", "").lower() == "true":
        return "done"
    if has_items:
        return "draft"
    return "todo"


def build_dossier_steps(pdir: Path) -> list[dict] | None:
    """dossier(Track A) 모델 — cluster_index 순서대로 §2 화면 항목 추출."""
    cidx = pdir / "work-orders" / "cluster_index.json"
    if not cidx.is_file():
        return None
    try:
        clusters = json.loads(cidx.read_text(encoding="utf-8")).get("clusters", [])
    except Exception:
        return None
    steps: list[dict] = []
    for c in clusters:
        cluster_id = c.get("cluster_id", "") or c.get("wo_id", "")
        capability = c.get("capability", "") or c.get("cluster_name", "")
        dp = c.get("draft_path", "")
        fm: dict = {}
        items: list[str] = []
        draft = pdir / dp if dp else None
        if draft is not None and draft.is_file():
            text = draft.read_text(encoding="utf-8", errors="replace")
            fm = _parse_frontmatter(text)
            items = _extract_screen_items(text)
        if items:
            status = _draft_status(fm, True)
            for n, it in enumerate(items, 1):
                m = SCR_ID.search(it)
                sid = m.group(1) if m else f"{cluster_id}-S{n}"
                label = SCR_ID.sub("", it).strip(" —-·:") or capability or sid
                steps.append({"id": sid, "label": label, "status": status,
                              "capability": capability})
        else:
            steps.append({"id": f"{cluster_id}-S1",
                          "label": f"{capability or cluster_id} [§2 미작성]",
                          "status": "todo", "capability": capability})
    return steps or None


def build_legacy_steps(pdir: Path) -> list[dict] | None:
    """section/screen(legacy) 모델 — screen-list.md 표의 SCR 행."""
    sl = pdir / "graph" / "screen-list.md"
    if not sl.is_file():
        return None
    steps: list[dict] = []
    for ln in sl.read_text(encoding="utf-8", errors="replace").splitlines():
        if not ln.strip().startswith("|") or "---" in ln:
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        sid = None
        for c in cells[:2]:
            m = SCR_ID.search(c)
            if m:
                sid = m.group(1)
                break
        if not sid:
            continue
        name_idx = 1 if cells and SCR_ID.search(cells[0]) else 2
        label = cells[name_idx] if len(cells) > name_idx else sid
        purpose = cells[name_idx + 1] if len(cells) > name_idx + 1 else ""
        steps.append({"id": sid, "label": label, "status": "todo", "purpose": purpose})
    return steps or None


def render_storyboard(product: str, steps: list[dict]) -> str:
    """SKILL.md 단계 4·5 형식의 storyboard MD (journey_emit 파싱 호환)."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    counts = {s: sum(1 for st in steps if st["status"] == s)
              for s in ("done", "draft", "sketch", "todo")}
    lines = [
        "---",
        f"generated_at: {now}",
        f"product: {product}",
        "actor: all",
        "from_screen: first",
        f"screen_count: {len(steps)}",
        f"draft_complete: {counts['done']}",
        f"draft_in_progress: {counts['draft']}",
        f"sketch_only: {counts['sketch']}",
        f"not_started: {counts['todo']}",
        "generated_by: journey_build.py (auto)",
        "---",
        "",
        f"고객 여정 스토리보드 — {product}",
        f"액터: 전체 / 생성 시각: {now}",
        f"총 {len(steps)}개 화면 ({counts['done']} ✅ / {counts['draft']} 📝 / "
        f"{counts['sketch']} 🔲 / {counts['todo']} ⬜)",
        "─" * 65,
        "",
    ]
    for i, st in enumerate(steps):
        icon = ICONS.get(st["status"], "⬜")
        lines.append(f"[{i + 1}] {st['id']} {st['label']}  {icon}")
        if st["status"] == "todo":
            if st.get("purpose"):
                lines.append(f"  목적: {st['purpose']}")
            lines.append("  전환: [미확정]")
        else:
            entry = "서비스 진입 (첫 화면)" if i == 0 else f"{steps[i - 1]['id']} 전환"
            lines.append(f"  진입 조건: {entry}")
            lines.append("  핵심 행동: [자동 생성 — /journey 로 보강]")
            if i + 1 < len(steps):
                lines.append(f"  전환:      → {steps[i + 1]['id']} ([전환 조건 미확정])")
        lines.append("")
    path_ids = " → ".join(st["id"] for st in steps)
    todo_list = ", ".join(st["id"] for st in steps if st["status"] == "todo") or "없음"
    lines += [
        "─" * 65,
        "여정 요약",
        f"  진입점:      {steps[0]['id']} {steps[0]['label']}",
        f"  핵심 경로:   {path_ids}",
        f"  미확정 구간: {todo_list}",
        "",
        "> 본 파일은 journey_build.py 가 draft 변경 시 자동 생성한 표준 storyboard 이다.",
        "> 액터 필터·전환 조건 서사 보강은 /journey {product} 로 생성한다.",
        "",
    ]
    return "\n".join(lines)


def _strip_volatile(text: str) -> str:
    """generated_at/생성 시각 라인 제외 본문 — 무변경 재기록 방지 비교용."""
    return "\n".join(
        ln for ln in text.splitlines()
        if not ln.startswith("generated_at:") and "생성 시각:" not in ln
    )


def build(hub_root: Path, product: str, output: Path | None = None,
          quiet: bool = False) -> int:
    pdir = hub_root / "PROJECTS" / product
    steps = build_dossier_steps(pdir) or build_legacy_steps(pdir)
    if not steps:
        if not quiet:
            sys.stderr.write(f"화면 소스 없음(cluster_index/screen-list): {pdir}\n")
        return 1
    md = render_storyboard(product, steps)
    out = output or (pdir / "reports" / OUTPUT_NAME)
    if out.is_file():
        try:
            if _strip_volatile(out.read_text(encoding="utf-8")) == _strip_volatile(md):
                return 0  # 실질 무변경 — 재기록·워처 트리거 방지
        except OSError:
            pass
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    if not quiet:
        print(f"[journey-build] {product}: {len(steps)} steps → {out}")
    return 0


# ── PostToolUse 훅 모드 (auto_assemble_on_draft_edit 패턴) ───────────────────

def _is_hub(cwd: Path) -> bool:
    return cwd.is_dir() and any((cwd / m).is_file() for m in HUB_MARKERS)


def _hook_main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}") or {}
    except Exception:
        payload = {}
    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    if not _is_hub(cwd):
        return 0
    if payload.get("tool_name", "") not in ("Write", "Edit", "MultiEdit"):
        return 0
    file_path = ((payload.get("tool_input") or {}).get("file_path") or "").replace("\\", "/")
    m = DRAFT_PATH_RE.search(file_path)
    if not m:
        return 0
    # 실패해도 PM 작업 흐름을 막지 않는다 — 항상 0 반환.
    try:
        rc = build(cwd, m.group("product"), quiet=True)
        if rc == 0:
            print(f"[auto-journey] {m.group('product')} {OUTPUT_NAME} 갱신")
    except Exception as exc:
        print(f"[auto-journey] WARN: {exc}", file=sys.stderr)
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="결정적 journey storyboard 빌더")
    ap.add_argument("--hub-root", type=Path)
    ap.add_argument("--product")
    ap.add_argument("--output", type=Path)
    ap.add_argument("--from-hook", action="store_true",
                    help="PostToolUse 페이로드(stdin) 모드 — draft 편집 시 자동 갱신")
    args = ap.parse_args(argv)
    if args.from_hook:
        return _hook_main()
    if not (args.hub_root and args.product):
        sys.stderr.write("--hub-root, --product 필요 (또는 --from-hook)\n")
        return 2
    return build(args.hub_root, args.product, args.output)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
