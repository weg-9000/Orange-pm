#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""C-BDD 수용 기준(.feature) 결정적 조립기 (WP-BDD).

목적:
    {PREFIX}-C draft 의 행위 명세 표 — policy WO 의 `상태 × 액션 매트릭스`,
    screen WO 의 `4-state 인터랙션 시퀀스` — 를 입력받아 Gherkin `.feature`
    수용 기준으로 **결정적 텍스트 변환**한다. 모델 미관여 — 표 셀을 그대로
    Given/When/Then 으로 사상할 뿐 창작하지 않는다(render_assemble 의 BDD 사촌).
    draft 는 읽기 전용. 산출물은 수기 수정 금지(이중 작성=SSoT 붕괴).

사상 규칙(결정적):
    policy 매트릭스 셀 (상태 Si, 액션 Aj, 값 V≠공백)
      → Scenario: Given 시스템이 "Si" 상태이고 / When "Aj" 시도 / Then 결과 "V"
    screen 4-state 행 (상태 / 조건 / UI 표현 / 사용자 액션 / 다음 상태)
      → Scenario: Given 화면 "상태"(+조건) / When 사용자 "액션" / Then "UI" 표시
    셀·행에 박힌 `[[POL §X-Y]]` 마커와 frontmatter `referenced_policy` 핀은
    Gherkin 태그(@POL-§…)로 보존 → 개발팀 테스트까지 정책 추적 연결.

산출:
    reports/bdd/{WO_ID}.feature                 (단일)
    reports/bdd/{product}.all.feature           (--all)
    헤더 주석에 source_referenced_master 핀 →
      drift / bdd_coverage_scan 이 stale·미커버 대조.

사용법:
    python bdd_assemble.py --hub-root <Hub> --product <p> [--wo <WO_ID>] [--all]

exit code: 0 성공 / 1 입력 없음·치명 / 2 인자 오류
"""
from __future__ import annotations

import argparse
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
POL_MARKER = re.compile(r"\[\[\s*POL\s*§?\s*([A-Za-z0-9][\w.\-()]*?)\s*\]\]")
# 매트릭스 표 헤더 식별: 첫 셀이 "상태"+"액션"(또는 \ / × 구분)을 포함.
MATRIX_HEAD = re.compile(r"상태.*[\\×xX].*액션|상태\s*\\\s*액션|state.*action", re.I)
# 화면 4-state 표 식별용 컬럼 키워드.
STATE_COL = re.compile(r"^\s*상태\s*$|^\s*state\s*$", re.I)
COND_COL = re.compile(r"조건|condition", re.I)
UI_COL = re.compile(r"UI|표현|화면", re.I)
ACT_COL = re.compile(r"액션|행동|동작|action", re.I)
NEXT_COL = re.compile(r"다음|전이|next", re.I)
EMPTY_CELL = re.compile(r"^[\s\-–—]*$")

# 화면 필수 상태 — flow(idle/loading/success/error)·템플릿(Empty/Loading/Loaded/Error)
# 양쪽 네이밍을 동의어 그룹으로 흡수. bdd_coverage_scan 과 공유하는 SSoT.
STATE_GROUPS = {
    "idle": re.compile(r"idle|empty|초기|대기(?!중)|빈\s*상태", re.I),
    "loading": re.compile(r"loading|로딩|진행|대기중", re.I),
    "success": re.compile(r"success|loaded|성공|완료|정상", re.I),
    "error": re.compile(r"error|오류|실패|에러", re.I),
}
# '### 5-1. idle (초기 진입)' 형식의 4-state 하위섹션 헤딩 (### 또는 ####).
SUBHEAD = re.compile(r"^\s{0,3}#{3,4}\s+(.+?)\s*$")
TOPHEAD = re.compile(r"^\s{0,3}#{1,2}\s+")
# 상태 N/A(해당 없음) 면제 표기 — bdd_coverage_scan 과 공유 SSoT.
NA = re.compile(r"해당\s*없음|N/?A|불필요|없음", re.I)
# fanout 이 생성한 WO 지시 템플릿(스텁) 식별 — 행위 명세가 아닌 작업 지시서다.
# 실제 산출물은 별도 콘텐츠 draft(예: S01)에 있으므로 BDD 대상에서 제외.
WO_STUB = re.compile(r"^#\s+Work Order:", re.M)


def is_wo_stub(body: str) -> bool:
    return bool(WO_STUB.search(body))


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


def _refs(text: str) -> list[str]:
    """셀·행 텍스트에 박힌 [[POL §X-Y]] 마커를 §id 리스트로 추출."""
    seen, out = set(), []
    for r in POL_MARKER.findall(text or ""):
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _tag(s: str) -> str:
    """Gherkin 태그용 정규화 — 공백·구분자를 하이픈으로(태그에 공백 불가)."""
    s = re.sub(r"\s+", "-", str(s).strip())
    s = re.sub(r"[^\w§.\-]", "", s)
    return s.strip("-") or "x"


def extract_tables(body: str) -> list[tuple[list[str], list[list[str]]]]:
    """본문에서 마크다운 표를 (헤더셀, 데이터행들) 목록으로 추출."""
    tables: list[tuple[list[str], list[list[str]]]] = []
    rows: list[list[str]] = []
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith("|") and line.endswith("|") and line.count("|") >= 2:
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows.append(cells)
            continue
        if rows:
            tables.append(_finalize_table(rows))
            rows = []
    if rows:
        tables.append(_finalize_table(rows))
    return [t for t in tables if t[0]]


def _finalize_table(rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    if not rows:
        return [], []
    header = rows[0]
    data = [r for r in rows[1:] if not all(re.fullmatch(r"[-:\s]*", c) for c in r)]
    return header, data


def find_matrix_table(tables) -> tuple[list[str], list[list[str]]] | None:
    for header, data in tables:
        if header and MATRIX_HEAD.search(header[0]):
            return header, data
        if header and ("상태" in header[0] and any("A" == c[:1] or "액션" in c for c in header[1:])):
            return header, data
    return None


def find_state_table(tables) -> tuple[list[str], list[list[str]]] | None:
    for header, data in tables:
        if not header:
            continue
        # 화면 4-state 표는 'UI 표현' 또는 '사용자 액션' 컬럼을 가진다. 정책
        # 라이프사이클 표(상태|정의|진입조건|다음상태 — UI·액션 없음)가 화면 표로
        # 오인식되지 않도록 UI/액션 컬럼을 필수로 요구한다.
        if STATE_COL.search(header[0]) and any(
            UI_COL.search(c) or ACT_COL.search(c) for c in header[1:]
        ):
            return header, data
    return None


def policy_scenarios(table) -> list[dict]:
    """매트릭스 → 비공백 셀별 시나리오 dict 목록."""
    header, data = table
    actions = header[1:]
    out: list[dict] = []
    for row in data:
        if not row:
            continue
        state = row[0].strip()
        for j, cell in enumerate(row[1:]):
            if j >= len(actions):
                break
            val = cell.strip()
            if EMPTY_CELL.match(val):
                continue
            out.append({
                "state": state,
                "action": actions[j].strip(),
                "value": POL_MARKER.sub(lambda m: f"§{m.group(1)}", val).strip(),
                "refs": _refs(val + " " + state),
            })
    return out


def screen_scenarios(table) -> list[dict]:
    """4-state 표 → 행별 시나리오 dict 목록 (컬럼 순서 무관, 헤더명으로 매핑)."""
    header, data = table

    def idx(pat):
        for i, c in enumerate(header):
            if pat.search(c):
                return i
        return None

    i_state, i_cond, i_ui = 0, idx(COND_COL), idx(UI_COL)
    i_act, i_next = idx(ACT_COL), idx(NEXT_COL)
    out: list[dict] = []
    for row in data:
        if not row or not row[0].strip():
            continue

        def cell(i):
            return row[i].strip() if i is not None and i < len(row) else ""

        out.append({
            "state": row[0].strip(),
            "cond": cell(i_cond),
            "ui": cell(i_ui),
            "action": cell(i_act),
            "next": cell(i_next),
            "refs": _refs(" ".join(row)),
        })
    return out


def match_state_group(text: str) -> str | None:
    """텍스트가 어느 필수 상태 그룹(idle/loading/success/error)인지 — 사전 순 첫 매칭."""
    for name, pat in STATE_GROUPS.items():
        if pat.search(text or ""):
            return name
    return None


def extract_state_subsections(body: str) -> list[tuple[str, list]]:
    """'### N-x. {state}' 형식 4-state 하위섹션 → [(heading, [표,...]), ...].

    단일 표준 표(`상태|조건|UI|...`) 대신 화면별 상태를 하위섹션으로 나눠 적는
    프로젝트 관습(cloud-calculator 등)을 인식한다. 상태 그룹에 매칭되고 표를
    1개 이상 가진 하위섹션만 반환(산문 헤딩·무관 섹션 노이즈 배제)."""
    subs: list[tuple[str, list]] = []
    head: str | None = None
    buf: list[str] = []

    def flush():
        nonlocal head, buf
        if head is not None and match_state_group(head):
            tbls = extract_tables("\n".join(buf))
            if tbls:
                subs.append((head, tbls))
        head, buf = None, []

    for ln in body.splitlines():
        m = SUBHEAD.match(ln)
        if m:
            flush()
            head = m.group(1)
        elif TOPHEAD.match(ln):
            flush()  # 상위(## / #) 섹션 진입 → 현재 하위섹션 종료
        elif head is not None:
            buf.append(ln)
    flush()
    return subs


def state_group_coverage(body: str) -> dict[str, str]:
    """4-state 하위섹션 형식의 상태 그룹별 커버리지 판정.

    {group: 'table'|'na'} 반환:
      - 'table': 해당 상태 하위섹션에 표가 있다(시나리오 생성 가능).
      - 'na'   : 표는 없으나 '해당 없음/없음/N/A' 류로 명시적 N/A 처리됨
                 (예: S02 우측 패널의 error/loading — 정적 재산출이라 독립 error 없음).
    표가 N/A 표기를 항상 우선(override)한다. 미등장 그룹은 dict 에 없음(=누락)."""
    cov: dict[str, str] = {}
    head: str | None = None
    buf: list[str] = []

    def flush():
        nonlocal head, buf
        if head:
            g = match_state_group(head)
            if g:
                txt = head + "\n" + "\n".join(buf)
                if extract_tables("\n".join(buf)):
                    cov[g] = "table"
                elif NA.search(txt) and cov.get(g) != "table":
                    cov[g] = "na"
        head, buf = None, []

    for ln in body.splitlines():
        m = SUBHEAD.match(ln)
        if m:
            flush()
            head = m.group(1)
        elif TOPHEAD.match(ln):
            flush()
        elif head is not None:
            buf.append(ln)
    flush()
    return cov


def screen_scenarios_from_subsections(body: str) -> list[dict]:
    """4-state 하위섹션 형식 → 시나리오 dict 목록(screen_scenarios 와 동일 스키마).

    각 상태 하위섹션의 표 행을 결정적으로 사상한다(셀 창작 없음):
      row[0](항목/트리거/오류유형) → cond, row[1:](내용/복구/메시지) → ui.
    상태는 헤딩에서 추출한 정본 그룹명(idle/loading/success/error)."""
    out: list[dict] = []
    for head, tables in extract_state_subsections(body):
        grp = match_state_group(head)
        for _header, data in tables:
            for row in data:
                if not row or not any(c.strip() for c in row):
                    continue
                label = row[0].strip()
                content = " — ".join(c.strip() for c in row[1:] if c.strip())
                if not content and not label:
                    continue
                out.append({
                    "state": grp,
                    "cond": label,
                    "ui": content,
                    "action": "",
                    "next": "",
                    "refs": _refs(" ".join(row)),
                })
    return out


def _scenario_block(title: str, tags: list[str], steps: list[tuple[str, str]],
                    trail: str) -> str:
    tag_line = "  " + " ".join(f"@{t}" for t in tags) + "\n" if tags else ""
    body = "\n".join(f"    {kw:<6}{txt}" for kw, txt in steps)
    return f"{tag_line}  Scenario: {title}\n{body}\n    # 추적: {trail}\n"


def _policy_blocks(scenarios: list[dict]) -> list[str]:
    blocks: list[str] = []
    for sc in scenarios:
        tags = [_tag(sc["state"]), _tag(sc["action"])] + [f"POL-{_tag(r)}" for r in sc["refs"]]
        steps = [
            ("Given", f'시스템이 "{sc["state"]}" 상태이고'),
            ("When", f'"{sc["action"]}" 을(를) 시도하면'),
            ("Then", f'결과는 "{sc["value"]}" 이다'),
        ]
        trail = ", ".join(f"[[POL §{r}]]" for r in sc["refs"]) or "(정책 §참조 없음)"
        blocks.append(_scenario_block(
            f'{sc["state"]} 상태에서 {sc["action"]} 시 {sc["value"]}', tags, steps, trail))
    return blocks


def _screen_blocks(scenarios: list[dict]) -> list[str]:
    blocks: list[str] = []
    for sc in scenarios:
        tags = [_tag(sc["state"])] + [f"POL-{_tag(r)}" for r in sc["refs"]]
        steps = [("Given", f'화면이 "{sc["state"]}" 상태이고')]
        if sc["cond"]:
            steps.append(("And", f'조건이 "{sc["cond"]}" 이면'))
        steps.append(("When", f'사용자가 "{sc["action"]}" 하면' if sc["action"]
                      else "화면이 표시되면"))
        steps.append(("Then", f'"{sc["ui"]}" 이(가) 표시된다' if sc["ui"]
                      else "정의된 UI 가 표시된다"))
        if sc["next"]:
            steps.append(("And", f'다음 상태는 "{sc["next"]}" 이다'))
        trail = ", ".join(f"[[POL §{r}]]" for r in sc["refs"]) or "(정책 §참조 없음)"
        blocks.append(_scenario_block(f'{sc["state"]} 상태 인터랙션', tags, steps, trail))
    return blocks


def _feature_header(wo_id: str, fm: dict, kind: str, label: str) -> str:
    pin = fm.get("referenced_policy", "").strip()
    feat_tags = [f"source:{_tag(wo_id)}", f"type:{kind}"]
    if pin:
        feat_tags.append(f"POL:{_tag(pin)}")
    return (
        "# ⟦자동 생성 — bdd_assemble.py (C-BDD, 결정적·모델 미관여)⟧\n"
        "# 직접 수정 금지(이중 작성=SSoT 붕괴). 수정은 소스 draft(/write·/flow·/write-cluster)에서.\n"
        f"# source_doc_id: {wo_id}\n"
        f"# generated_at: {datetime.now().isoformat(timespec='seconds')}\n"
        f"# source_referenced_master: [{fm.get('referenced_master', '')}]\n"
        f"# referenced_policy: {pin or '-'}\n"
        "# language: ko (Gherkin 키워드 영문 · 본문 한글 — Cucumber/Behave 기본 호환)\n\n"
        + " ".join(f"@{t}" for t in feat_tags) + "\n"
        f"Feature: {wo_id} 수용 기준 ({label})\n"
        f"  소스: drafts/{wo_id}.draft.md 의 {label} 표를 결정적 변환한 수용 기준.\n"
        "  draft 갱신 시 /bdd 재실행으로 동기화한다.\n\n"
    )


def render_feature(wo_id: str, fm: dict, kind: str, scenarios: list[dict]) -> str:
    blocks = _policy_blocks(scenarios) if kind == "policy" else _screen_blocks(scenarios)
    label = "상태 × 액션" if kind == "policy" else "4-state 인터랙션"
    header = _feature_header(wo_id, fm, kind, label)
    return header + "\n".join(blocks) + ("\n" if blocks else
        "  # ⚠️ 변환할 행위 명세 표 없음 — draft 에 매트릭스/4-state 표 작성 필요\n")


def render_cluster_feature(wo_id: str, fm: dict,
                           pol_scen: list[dict], scr_scen: list[dict]) -> str:
    """cluster_draft 전용 — §1 정책 매트릭스 + §2 화면 4-state 를 한 Feature 에 합본."""
    header = _feature_header(wo_id, fm, "cluster", "정책 매트릭스 + 화면 4-state")
    parts: list[str] = []
    if pol_scen:
        parts.append("  # ── §1 정책 결정 (상태 × 액션) ──")
        parts.extend(_policy_blocks(pol_scen))
    if scr_scen:
        parts.append("  # ── §2 화면 설계 (4-state) ──")
        parts.extend(_screen_blocks(scr_scen))
    if not parts:
        return header + "  # ⚠️ 변환할 §1 매트릭스·§2 4-state 표 없음\n"
    return header + "\n".join(parts) + "\n"


def find_matrix_table_strict(tables) -> tuple[list[str], list[list[str]]] | None:
    """엄격 매트릭스 탐지 — 헤더 첫 셀이 '상태 × 액션' 형태일 때만(MATRIX_HEAD).
    cluster 의 §2 4-state('사용자 액션' 컬럼 보유)를 매트릭스로 오인하지 않게 한다."""
    for header, data in tables:
        if header and MATRIX_HEAD.search(header[0]):
            return header, data
    return None


def assemble_one(text: str, wo_id: str) -> tuple[str, int, str]:
    """draft 본문 → (.feature 문자열, 시나리오 수, kind). 순수 함수(테스트용).
    cluster_draft 는 §1 매트릭스(정책)+§2 4-state(화면) 둘 다 추출해 합본한다."""
    fm, body = _parse_frontmatter(text)
    kind = (fm.get("type") or "").strip().lower()
    tables = extract_tables(body)
    if kind == "cluster_draft" or kind == "cluster":
        matrix = find_matrix_table_strict(tables)
        state = find_state_table(tables)
        pol = policy_scenarios(matrix) if matrix else []
        scr = screen_scenarios(state) if state else []
        return render_cluster_feature(wo_id, fm, pol, scr), len(pol) + len(scr), "cluster"
    if kind == "policy" or (not kind and find_matrix_table(tables)):
        kind = "policy"
        tbl = find_matrix_table(tables)
        scen = policy_scenarios(tbl) if tbl else []
    else:
        kind = "screen"
        tbl = find_state_table(tables)
        # 표준 단일 표 우선, 없으면 '### N-x. {state}' 4-state 하위섹션 형식 폴백.
        scen = screen_scenarios(tbl) if tbl else screen_scenarios_from_subsections(body)
    return render_feature(wo_id, fm, kind, scen), len(scen), kind


def main() -> int:
    ap = argparse.ArgumentParser(description="C-BDD 수용 기준(.feature) 결정적 조립")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", required=True)
    ap.add_argument("--wo", default=None, help="단일 WO_ID (생략=전체 draft)")
    ap.add_argument("--all", action="store_true", help="추가로 {product}.all.feature 생성")
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

    targets = (
        [drafts_dir / f"{args.wo}.draft.md"] if args.wo
        else sorted(drafts_dir.glob("*.draft.md"))
    )
    targets = [t for t in targets if t.exists()]
    if not targets:
        sys.stderr.write("대상 draft 없음\n")
        return 1

    out_dir = proj / "reports" / "bdd"
    out_dir.mkdir(parents=True, exist_ok=True)
    all_parts: list[str] = []
    total = 0
    skipped = 0
    for d in targets:
        wo = d.stem.replace(".draft", "")
        text = d.read_text(encoding="utf-8", errors="replace")
        if is_wo_stub(_parse_frontmatter(text)[1]):
            # WO 지시 스텁(행위 명세 아님) — feature 생성 안 함, 잔존 스텁 feature 제거.
            (out_dir / f"{wo}.feature").unlink(missing_ok=True)
            skipped += 1
            continue
        feature, n, kind = assemble_one(text, wo)
        (out_dir / f"{wo}.feature").write_text(feature, encoding="utf-8")
        all_parts.append(f"\n\n# ===== {wo} ({kind}) =====\n\n" + feature)
        total += n
        print(f"[bdd_assemble] {wo}.feature ← {kind} · 시나리오 {n}건")

    if args.all and not args.wo:
        (out_dir / f"{args.product}.all.feature").write_text(
            "".join(all_parts), encoding="utf-8")
        print(f"[bdd_assemble] {args.product}.all.feature ({len(targets)} draft)")

    print(f"[bdd_assemble] 완료 — {len(targets) - skipped}건 draft / 시나리오 {total}건"
          + (f" (WO 스텁 {skipped}건 제외)" if skipped else "")
          + f" → {out_dir.relative_to(hub)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
