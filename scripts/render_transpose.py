#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cluster Draft → Deliverable Transpose (Phase 5F).

발행 모드 의존 (fix-plan-dossier-publish-split):
    transpose() 는 **split-deliverable 발행 모드에서 재활성**된다
    (graph/project-mode.json `publication_mode: split-deliverable`).
    - dossier-page (기본)  : 기능정의서 1개 = 페이지 1개. transpose 미호출.
                             (render/SKILL.md 단계 3-A, publication-map.md §0)
    - split-deliverable    : dossier §1 → D2 정책정의서 / §2 → D3 화면설계서로
                             분할 발행. 본 모듈의 transpose() 가 그 조립을 담당.
    P3 파생 뷰(`render_fr_capability_view`·`render_cross_cutting_matrix`)는
    두 모드 모두에서 유효하다(링크 대상만 모드별로 다름).

    ⚠️ FLAG: §0/§5/§6 은 D2/D3 에 미반영(정책은 §1 에 self-contained). dossier 가
       deliverable_targets 에서 D2/D3 를 빼면 해당 cluster 가 누락된다 —
       render/SKILL.md 의 split 분기 주의 표기 참조.

목적:
    Track A (Full Product) 의 cluster work 산출물 (drafts/cluster_*.draft.md) 을
    publication 산출물 (D2 정책 / D3 화면 / Dα etc) 의 단일 페이지로
    어셈블하는 결정적 transpose 함수.

    cluster_draft 의 §1 / §2 / §α panel block 만 추출 → deliverable 별로
    capability + cluster_id 정렬 → 챕터 panel 로 재포장.
    §3 (데이터/의존성), §4 (OQ/UPSTREAM_GAP) 는 publish 제외.

사양 SSoT:
    - skills/render/publication-map.md §2 (transpose 매트릭스)
    - skills/render/publication-map.md §4 (함수 인터페이스)
    - skills/render/publication-map.md §7 (챕터 명명)
    - templates/standard/cluster-draft.md (cluster 4-section 양식)
    - templates/standard/D2_policy.md / D3_screen.md / Dα_*.md (목적 양식)

동작:
    1. cluster_draft 의 frontmatter 파싱 (cluster.capability / cluster_id /
       cluster_name + deliverable_targets)
    2. deliverable_targets 에 deliverable_type 포함된 cluster 만 선별
    3. deliverable_type 별 § 섹션 매핑:
         - D2          → cluster §1 panel block 추출
         - D3          → cluster §2 panel block 추출
         - Da_api      → cluster §α (api) panel block 추출
         - Da_db       → cluster §α (db) panel block 추출
         - Da_migration→ cluster §α (migration) panel block 추출
    4. 정렬 (deterministic): capability 알파벳 → cluster_id 자연 순
    5. 챕터 panel 어셈블 (publication-map.md §7 명명):
         ::: {.panel section="§{N} {Capability} / {ClusterName} ({cluster_id})"}
         ## §{N} {Capability} / {ClusterName} ({cluster_id})
         {원본 §1/§2/§α 본문 — 패널 wrapper 제거 후 채워넣음}
         :::
    6. D3 만: common_shell_clusters 의 §2 들을 별도 `§부록 A — 공통 셸` panel
    7. Frontmatter 어셈블 (target_template 이 있으면 그 frontmatter + 갱신,
       없으면 deliverable_type 기반 기본 frontmatter)
    8. 단일 MD 문자열 반환 — caller (예: render skill) 가 md_to_storage.py 로
       XML 변환

CLI:
    python render_transpose.py \\
        --cluster-drafts drafts/cluster_*.draft.md \\
        --deliverable D2 \\
        --output reports/render/D2_policy.assembled.md \\
        [--template orange-pm-plugin/templates/standard/D2_policy.md] \\
        [--common-shell drafts/cluster_common_*.draft.md]   # D3 만

exit code:
    0 = 성공
    1 = 파싱 오류 (cluster_draft frontmatter / panel 구조 위반)
    2 = 적합한 cluster 없음 (deliverable_targets 매칭 0건)
    3 = IO 오류
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml  # PyYAML 6.0.x — stdlib 외 (md_to_storage.py 와 동일 정책)
except Exception:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


# ── 상수 ─────────────────────────────────────────────────────────────────────

# 사양 §2 / §4 — deliverable_type 별 추출 대상 § 키워드
# 추출은 cluster panel section 속성 텍스트의 부분 매칭으로 수행
# (cluster-draft.md 의 panel section 라벨 참조)
DELIVERABLE_SECTION_MAP: dict[str, str] = {
    "D2": "§1",
    "D3": "§2",
    "Da_api": "§α",
    "Da_db": "§α",
    "Da_migration": "§α",
}

# Da_* 추가 키워드 (§α 안에서 api / db / migration 분리)
# cluster-draft.md 에 §α-API / §α-DB / §α-MIG panel 이 type 별로 존재(선택적).
# section 이 "§α" 로 시작하고 아래 키워드를 포함하는 panel 을 deliverable 별로 추출.
DA_TYPE_KEYWORDS: dict[str, list[str]] = {
    "Da_api": ["api", "API"],
    "Da_db": ["db", "DB", "데이터"],
    "Da_migration": ["migration", "마이그레이션"],
}

VALID_DELIVERABLES = set(DELIVERABLE_SECTION_MAP.keys())

# 정규식
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# panel 블록 — section 속성 캡처 + 본문
# fenced div: ::: {.panel section="..." style="..."}
#             ...
#             :::
PANEL_OPEN_RE = re.compile(
    r'^:::\s*\{\.panel\s+([^}]*)\}\s*$', re.MULTILINE
)
PANEL_SECTION_ATTR_RE = re.compile(r'section\s*=\s*"([^"]*)"')

# cluster_id 자연 순 정렬용 — 영문/숫자 분할
NATSORT_RE = re.compile(r"(\d+)|(\D+)")


# ── Frontmatter ──────────────────────────────────────────────────────────────


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """YAML frontmatter 파싱 → (dict, body).

    PyYAML 부재 시 매우 한정적 fallback (top-level scalar only) — cluster
    구조는 nested 이므로 yaml 필수. 부재 시 빈 dict 반환.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    body = text[m.end():]
    fm_text = m.group(1)
    if yaml is not None:
        try:
            data = yaml.safe_load(fm_text) or {}
            if not isinstance(data, dict):
                return {}, body
            return data, body
        except Exception:
            return {}, body
    return {}, body


def _render_frontmatter(fm: dict) -> str:
    """dict → YAML frontmatter MD 블록.

    PyYAML 사용 (allow_unicode, sort_keys=False).
    """
    if yaml is None:
        # naive fallback — top-level scalars only
        lines = ["---"]
        for k, v in fm.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                lines.append(f"{k}: {v if v is not None else 'null'}")
        lines.append("---")
        return "\n".join(lines) + "\n"
    body = yaml.safe_dump(
        fm, allow_unicode=True, sort_keys=False, default_flow_style=False
    )
    return f"---\n{body}---\n"


# ── Cluster 메타 로드 / 검증 ─────────────────────────────────────────────────


class TransposeError(Exception):
    """transpose 단계의 파싱·구조 오류."""


def _load_cluster_meta(path: Path) -> dict:
    """cluster_draft 파일 → 메타 dict.

    Returns:
        {
            "path": Path,
            "text": str,              # 전체 본문 (frontmatter 제외)
            "frontmatter": dict,      # 파싱된 frontmatter
            "capability": str,
            "cluster_id": str,
            "cluster_name": str,
            "deliverable_targets": list[str],
            "is_common_shell": bool,
            "title": str,             # frontmatter title
            "wo_id": str,             # frontmatter wo_id
        }

    Raises:
        TransposeError — frontmatter 또는 cluster 메타 누락 / 형식 오류
    """
    if not path.exists():
        raise TransposeError(f"cluster_draft 파일 없음: {path}")
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise TransposeError(f"cluster_draft 읽기 실패: {path} — {exc}")

    fm, body = _parse_frontmatter(raw)
    if not fm:
        raise TransposeError(
            f"cluster_draft frontmatter 파싱 실패: {path} — "
            "YAML 형식이거나 PyYAML 미설치"
        )

    cluster = fm.get("cluster")
    if not isinstance(cluster, dict):
        raise TransposeError(
            f"cluster_draft frontmatter 에 'cluster:' 블록 누락: {path}"
        )

    capability = str(cluster.get("capability", "")).strip()
    cluster_id = str(cluster.get("cluster_id", "")).strip()
    cluster_name = str(cluster.get("cluster_name", "")).strip()
    if not capability or not cluster_id:
        raise TransposeError(
            f"cluster.capability / cluster.cluster_id 누락: {path}"
        )

    targets_raw = fm.get("deliverable_targets") or []
    if isinstance(targets_raw, str):
        # 한 줄 표현 fallback
        targets = [t.strip() for t in targets_raw.strip("[]").split(",") if t.strip()]
    elif isinstance(targets_raw, list):
        targets = [str(t).strip() for t in targets_raw]
    else:
        targets = []

    is_common_shell = bool(fm.get("is_common_shell", False))

    # related_screens — D3 화면 단위 챕터(split-deliverable) 어셈블용.
    # list 또는 한 줄 "[a, b]" 표현 fallback 모두 지원.
    rs_raw = fm.get("related_screens") or []
    if isinstance(rs_raw, str):
        related_screens = [
            s.strip().strip('"').strip("'")
            for s in rs_raw.strip("[]").split(",")
            if s.strip()
        ]
    elif isinstance(rs_raw, list):
        related_screens = [str(s).strip() for s in rs_raw if str(s).strip()]
    else:
        related_screens = []

    return {
        "path": path,
        "text": body,
        "frontmatter": fm,
        "capability": capability,
        "cluster_id": cluster_id,
        "cluster_name": cluster_name or cluster_id,
        "deliverable_targets": targets,
        "is_common_shell": is_common_shell,
        "related_screens": related_screens,
        "primary_screen": str(fm.get("primary_screen") or "").strip(),
        "title": str(fm.get("title", "")).strip(),
        "wo_id": str(fm.get("wo_id", "")).strip(),
    }


# ── panel block 추출 ────────────────────────────────────────────────────────


def _iter_panel_blocks(body: str) -> list[tuple[str, str, str, int, int]]:
    """body 에서 모든 panel block 을 추출.

    Returns: list of (section_attr_text, attr_inner, inner_body, start, end)
        - section_attr_text: panel section 속성 값 (예: "§1 정책 결정 (D2 ...)")
        - attr_inner: panel `{...}` 내부 전체 (디버깅용)
        - inner_body: panel 내부 본문 (h2/하위 콘텐츠 — `:::` 제외)
        - start, end: body 내 raw 위치 (panel 전체 — `:::` 라인 포함)

    nested fenced div (예: panel 안 .info / .expand) 지원 — depth 카운터.
    """
    out: list[tuple[str, str, str, int, int]] = []
    lines = body.splitlines(keepends=True)
    # 라인 시작 오프셋 사전 계산
    offsets = [0]
    for ln in lines:
        offsets.append(offsets[-1] + len(ln))

    i = 0
    while i < len(lines):
        ln = lines[i].rstrip("\n")
        m = PANEL_OPEN_RE.match(ln)
        if m:
            attr_inner = m.group(1)
            sec_m = PANEL_SECTION_ATTR_RE.search(attr_inner)
            if not sec_m:
                # panel 인데 section 속성 없음 — skip (TBD 항목 등)
                i += 1
                continue
            section_attr = sec_m.group(1)
            # 닫는 ::: 찾기 — depth 카운터
            depth = 1
            j = i + 1
            body_lines: list[str] = []
            while j < len(lines):
                lj = lines[j].rstrip("\n")
                if lj.startswith(":::"):
                    # 여는 ::: { ... } 또는 닫는 :::
                    if re.match(r"^:::\s*\{", lj):
                        depth += 1
                        body_lines.append(lines[j])
                    elif re.match(r"^:::\s*$", lj):
                        depth -= 1
                        if depth == 0:
                            # 닫는 panel
                            inner = "".join(body_lines)
                            out.append(
                                (
                                    section_attr,
                                    attr_inner,
                                    inner,
                                    offsets[i],
                                    offsets[j + 1],
                                )
                            )
                            i = j + 1
                            break
                        body_lines.append(lines[j])
                    else:
                        body_lines.append(lines[j])
                else:
                    body_lines.append(lines[j])
                j += 1
            else:
                # 닫히지 않음 — 형식 위반
                raise TransposeError(
                    f"닫히지 않은 panel block (section={section_attr!r})"
                )
            continue
        i += 1
    return out


def _extract_panel_section(
    body: str, section_keyword: str, *, type_keywords: list[str] | None = None
) -> tuple[str, str] | None:
    """body 에서 section 속성이 `section_keyword` 로 시작하는 첫 panel 의 본문 반환.

    Args:
        body: cluster_draft 의 frontmatter 제외 본문
        section_keyword: 부분 매칭 키 (예: "§1", "§2", "§α")
        type_keywords: Da_* 의 경우 §α 안에서 type 분리용 부가 키 (예: ["api"])

    Returns:
        (section_attr_text, inner_body) 또는 None (해당 섹션 없음)
    """
    blocks = _iter_panel_blocks(body)
    for sec, _attr, inner, _s, _e in blocks:
        if not sec.startswith(section_keyword):
            # 일부 panel 은 "§1 정책 결정 (D2 → ...)" 형태이므로 startswith 매칭
            continue
        if type_keywords:
            # §α 의 경우 type 별 추가 키워드 매칭
            if not any(kw.lower() in sec.lower() for kw in type_keywords):
                continue
        return (sec, inner.rstrip() + "\n")
    return None


# ── 정렬 ────────────────────────────────────────────────────────────────────


def _natural_key(s: str) -> tuple:
    """자연 정렬 key — 'PR-01' < 'PR-02' < 'PR-10'.

    예: "PR-01" → (("PR-",), (1,))
    """
    out: list[Any] = []
    for m in NATSORT_RE.finditer(s):
        num, txt = m.group(1), m.group(2)
        if num is not None:
            out.append((1, int(num)))
        else:
            out.append((0, txt.lower()))
    return tuple(out)


def _sort_clusters(clusters: list[dict]) -> list[dict]:
    """publication-map.md §2 결정적 정렬:

        1차: capability 알파벳 순 (대소문자 무관)
        2차: cluster_id 자연 순 (PR-01 < PR-02 < PR-10)
    """
    return sorted(
        clusters,
        key=lambda c: (c["capability"].lower(), _natural_key(c["cluster_id"])),
    )


# ── P3 파생 뷰 (cluster_map.json 인덱스 → markdown 패널) ─────────────────────
# DEC-C / DEC-F: cluster_map.json 의 fr_index / module_index 를 SSoT 로 받아
# 결정적·순수(부수효과 없음)하게 markdown 패널을 합성한다. 산문 고정 TOC 없음 —
# 재군집(threshold 조절) 시 인덱스만 바뀌면 뷰가 자동 추종(수기 0).
# 어떤 모듈에도 일반적으로 동작(이메일/로깅/인증…) — 이메일 특화 하드코딩 없음.


def render_fr_capability_view(fr_index: dict[str, dict]) -> str:
    """D1 capability group-by 파생 뷰 (DEC-C).

    `cluster_map.json` 의 `fr_index` ({FR-id: {capability, cluster_id}}) 를
    capability 별로 묶어 각 capability 아래 FR 목록 + 해당 기능정의서
    (cluster_id) 앵커 링크를 나열하는 패널 markdown 을 반환한다.

    결정적 정렬:
        - capability 알파벳 순 (대소문자 무관)
        - 같은 capability 내 FR 은 자연 순 (FR-1 < FR-2 < FR-10)

    Args:
        fr_index: FR → {capability, cluster_id} 권위 인덱스 (SSoT).

    Returns:
        `::: {.panel section="..."}` 패널 markdown 문자열. 빈 입력이면
        안내 문구만 담긴 패널을 반환한다(결정적).
    """
    section = "§D1 capability별 FR 묶음 (cluster_map.fr_index 파생)"
    parts: list[str] = [
        f'::: {{.panel section="{section}"}}\n',
        f"## {section}\n\n",
        "> 본 뷰는 `cluster_map.json` `fr_index` 에서 자동 합성된다"
        "(수기 작성 금지 · 재군집 시 자동 추종).\n\n",
    ]

    # capability 별 group-by
    groups: dict[str, list[tuple[str, str]]] = {}
    for fr, meta in (fr_index or {}).items():
        cap = str((meta or {}).get("capability", "")).strip() or "(미지정)"
        cid = str((meta or {}).get("cluster_id", "")).strip()
        groups.setdefault(cap, []).append((str(fr), cid))

    if not groups:
        parts.append("_매핑된 FR 없음._\n")
        parts.append(":::\n")
        return "".join(parts)

    for cap in sorted(groups, key=lambda c: c.lower()):
        frs = sorted(groups[cap], key=lambda t: _natural_key(t[0]))
        parts.append(f"### {cap}\n\n")
        for fr, cid in frs:
            if cid:
                # 기능정의서(cluster) 앵커 — cluster_id 로 cross-link
                parts.append(f"- **{fr}** → [기능정의서 {cid}](#{cid})\n")
            else:
                parts.append(f"- **{fr}** → (cluster 미매핑)\n")
        parts.append("\n")

    parts.append(":::\n")
    return "".join(parts).rstrip("\n") + "\n"


def render_cross_cutting_matrix(
    module_index: dict[str, list[dict]],
    node_titles: dict[str, str] | None = None,
) -> str:
    """횡단 관심사 매트릭스 파생 뷰 (DEC-F).

    `cluster_map.json` 의 `module_index`
    ({모듈DocId: [{cluster_id, capability, source, via, section}, ...]}) 에서
    공유 모듈마다 "어느 기능(cluster)이 이 모듈을 참조하나"를 한눈에 보는
    매트릭스 패널을 합성한다. 어떤 모듈에도 일반적으로 동작한다
    (이메일·로깅·인증 등 — 특정 모듈 하드코딩 없음).

    각 모듈마다 1개의 markdown 테이블:
        | capability | cluster_id | source | via | section |
    행은 결정적으로 정렬(capability → cluster_id 자연 순 → source → via).
    모듈 자체는 docId 알파벳 순.

    Args:
        module_index: 모듈 → 참조 cluster 레코드 목록 (역인덱스, SSoT).
        node_titles: (선택) 모듈 docId → 사람이 읽는 제목 매핑. 있으면
            "제목 (docId)" 헤더로 표기, 없으면 docId 만 표기.

    Returns:
        `::: {.panel section="..."}` 패널 markdown 문자열. 빈 입력이면
        안내 문구만 담긴 패널을 반환한다(결정적).
    """
    section = "§횡단 관심사 매트릭스 (cluster_map.module_index 파생)"
    titles = node_titles or {}
    parts: list[str] = [
        f'::: {{.panel section="{section}"}}\n',
        f"## {section}\n\n",
        "> 공유 모듈을 참조하는 기능(cluster) 역인덱스. "
        "`cluster_map.json` `module_index` 에서 자동 합성된다(SSoT · 수기 금지).\n\n",
    ]

    modules = module_index or {}
    if not modules:
        parts.append("_횡단 참조 모듈 없음._\n")
        parts.append(":::\n")
        return "".join(parts)

    for module_id in sorted(modules):
        rows = modules[module_id] or []
        title = str(titles.get(module_id, "")).strip()
        heading = f"{title} ({module_id})" if title else module_id
        parts.append(f"### {heading}\n\n")

        if not rows:
            parts.append("_참조 기능 없음._\n\n")
            continue

        parts.append("| capability | cluster_id | source | via | section |\n")
        parts.append("|---|---|---|---|---|\n")
        sorted_rows = sorted(
            rows,
            key=lambda r: (
                str(r.get("capability", "")).lower(),
                _natural_key(str(r.get("cluster_id", ""))),
                _natural_key(str(r.get("source", ""))),
                str(r.get("via", "")),
            ),
        )
        for r in sorted_rows:
            cap = str(r.get("capability", "")).strip() or "—"
            cid = str(r.get("cluster_id", "")).strip() or "—"
            src = str(r.get("source", "")).strip() or "—"
            via = str(r.get("via", "")).strip() or "—"
            sec = str(r.get("section") or "").strip() or "—"
            parts.append(f"| {cap} | {cid} | {src} | {via} | {sec} |\n")
        parts.append("\n")

    parts.append(":::\n")
    return "".join(parts).rstrip("\n") + "\n"


# ── 챕터 어셈블 ─────────────────────────────────────────────────────────────


def _strip_first_h2(body: str) -> str:
    """추출된 panel 본문 첫 줄이 `## §...` 이면 제거.

    원본 §1 본문이 `## §1 정책 결정` h2 로 시작 — 챕터 panel 의 새 h2 가
    들어가므로 원본 h2 는 중복 회피.
    """
    lines = body.lstrip("\n").splitlines(keepends=True)
    if not lines:
        return body
    first = lines[0].rstrip("\n").strip()
    if re.match(r"^##\s+§", first):
        # h2 줄 + 직후 빈 줄도 함께 제거
        rest = lines[1:]
        while rest and rest[0].strip() == "":
            rest = rest[1:]
        return "".join(rest)
    return body


def _assemble_chapter(
    cluster: dict, section_body: str, chapter_num: int
) -> str:
    """단일 cluster 의 추출된 § 본문 → 챕터 panel MD.

    publication-map.md §7 명명:
        §{N} {Capability} / {ClusterName} ({cluster_id})
    """
    cap = cluster["capability"]
    name = cluster["cluster_name"]
    cid = cluster["cluster_id"]
    title = f"§{chapter_num} {cap} / {name} ({cid})"

    inner = _strip_first_h2(section_body).rstrip() + "\n"

    return (
        f'::: {{.panel section="{title}"}}\n'
        f"## {title}\n\n"
        f"{inner}"
        ":::\n"
    )


def _assemble_common_shell_appendix(
    common_clusters: list[dict], section_keyword: str
) -> str:
    """D3 공통 셸 부록 panel 어셈블.

    각 common_cluster 의 §2 추출 → 하위 §α / §α-1 형식으로 모음.
    """
    if not common_clusters:
        return ""

    parts = ['::: {.panel section="§부록 A — 공통 셸"}\n']
    parts.append("## §부록 A — 공통 셸\n\n")
    parts.append(
        "> 본 부록은 모든 cluster 가 공유하는 공통 화면 셸 "
        "(NavShell / AuthFlow 등) 의 화면 설계.\n\n"
    )
    sorted_common = _sort_clusters(common_clusters)
    for i, cluster in enumerate(sorted_common, start=1):
        extracted = _extract_panel_section(cluster["text"], section_keyword)
        if not extracted:
            sys.stderr.write(
                f"[render_transpose] WARN: 공통 셸 cluster "
                f"{cluster['cluster_id']} 에 {section_keyword} 섹션 없음 — 건너뜀\n"
            )
            continue
        _sec, inner = extracted
        title = (
            f"부록 A.{i} {cluster['cluster_name']} ({cluster['cluster_id']})"
        )
        inner = _strip_first_h2(inner).rstrip() + "\n\n"
        parts.append(f"### {title}\n\n")
        parts.append(inner)
    parts.append(":::\n")
    return "".join(parts)


# ── D3 화면 단위 챕터 (split-deliverable — fix-plan-dossier-publish-split) ────

# 화면 ID 토큰 — related_screens 가 비어도 §2 헤딩에서 화면 태깅을 감지하는 보조 패턴.
SCREEN_ID_RE = re.compile(r"\bSCR-[A-Za-z0-9]+\b")
HEADING_RE = re.compile(r"^(#{2,6})\s+(.*)$")


def _strip_first_heading(body: str) -> str:
    """본문 첫 줄이 임의 레벨 헤딩(## ~ ######)이면 제거(직후 빈 줄 포함)."""
    lines = body.lstrip("\n").splitlines(keepends=True)
    if lines and HEADING_RE.match(lines[0].rstrip("\n")):
        rest = lines[1:]
        while rest and rest[0].strip() == "":
            rest = rest[1:]
        return "".join(rest)
    return body


def _screen_name_from_heading(heading_text: str, sid: str) -> str:
    """헤딩 텍스트에서 화면명 추출 — 앞 §x-y 토큰·화면 ID·괄호 제거."""
    t = re.sub(r"^§\S+\s*", "", heading_text)  # 선행 §2-1 등 제거
    t = t.replace(f"({sid})", "").replace(sid, "")
    t = t.strip(" ()[]—-:·\t")
    return t or sid


def _split_by_screen_headings(
    body: str, screen_ids: list[str]
) -> list[tuple[str, str, str]]:
    """§2 본문에서 화면 ID 로 태깅된 헤딩 구간을 추출.

    헤딩(## ~ ######) 텍스트가 screen_ids(또는 SCR-패턴)를 포함하면 그 헤딩부터
    같은/상위 레벨 헤딩 직전까지를 한 화면 구간으로 본다.

    Returns: [(screen_id, heading_text, section_md), ...] (등장 순서)
    """
    lines = body.splitlines(keepends=True)
    idset = [s for s in screen_ids if s]
    heads: list[tuple[int, int, str, str | None]] = []  # (idx, level, text, sid)
    for i, ln in enumerate(lines):
        m = HEADING_RE.match(ln.rstrip("\n"))
        if not m:
            continue
        level, text = len(m.group(1)), m.group(2).strip()
        sid: str | None = None
        for s in idset:
            if s in text:
                sid = s
                break
        if sid is None:
            mm = SCREEN_ID_RE.search(text)
            if mm:
                sid = mm.group(0)
        heads.append((i, level, text, sid))

    sections: list[tuple[str, str, str]] = []
    for hi, (idx, level, text, sid) in enumerate(heads):
        if sid is None:
            continue
        end = len(lines)
        for (idx2, level2, _t2, _s2) in heads[hi + 1:]:
            if level2 <= level:
                end = idx2
                break
        section_md = "".join(lines[idx:end]).rstrip() + "\n"
        sections.append((sid, text, section_md))
    return sections


def _render_screen_index(
    screen_to_clusters: dict[str, list[dict]], screen_names: dict[str, str]
) -> str:
    """화면 인덱스 패널 — related_screens 합집합을 화면 ID 자연순으로 나열."""
    parts = [
        '::: {.panel section="§화면 인덱스"}\n',
        "## §화면 인덱스\n\n",
        "> 본 인덱스는 cluster_*.draft.md frontmatter 의 `related_screens` "
        "합집합에서 자동 합성된다(수기 작성 금지).\n\n",
        "| Screen ID | 화면명 | 출처 cluster |\n",
        "|---|---|---|\n",
    ]
    for sid in sorted(screen_to_clusters, key=_natural_key):
        clusters = screen_to_clusters[sid]
        src = " · ".join(
            f"{c['capability']} / {c['cluster_name']} ({c['cluster_id']})"
            for c in clusters
        ) or "—"
        parts.append(f"| {sid} | {screen_names.get(sid, '—') or '—'} | {src} |\n")
    parts.append(":::\n")
    return "".join(parts)


def _assemble_d3_screen_chapters(
    eligible: list[dict],
) -> tuple[str, list[str]] | None:
    """split-deliverable D3 — 화면 단위 챕터 어셈블.

    각 cluster 의 §2 본문에서 화면 ID 태깅 헤딩을 찾아 화면 단위로 재편한다.
    화면 태깅이 하나도 없으면 None 을 반환해 호출부가 cluster 단위 fallback 으로
    내려가게 한다(+WARN).

    Returns:
        (screen_index_md, [chapter_md, ...]) 또는 None(fallback 신호)
    """
    section_keyword = DELIVERABLE_SECTION_MAP["D3"]

    # 1. cluster 별 §2 추출
    per_cluster: list[tuple[dict, str]] = []
    for meta in eligible:
        extracted = _extract_panel_section(meta["text"], section_keyword)
        if not extracted:
            sys.stderr.write(
                f"[render_transpose] WARN: {meta['cluster_id']} 에 "
                f"{section_keyword} 섹션 없음 — 건너뜀\n"
            )
            continue
        per_cluster.append((meta, _strip_first_h2(extracted[1])))

    if not per_cluster:
        return None

    # 2. related_screens 합집합 → 출처 매핑
    screen_to_clusters: dict[str, list[dict]] = {}
    for meta in eligible:
        for s in meta["related_screens"]:
            screen_to_clusters.setdefault(s, []).append(meta)

    # 3. §2 화면 태깅 헤딩 수집
    universe = sorted(
        {s for meta in eligible for s in meta["related_screens"]},
        key=_natural_key,
    )
    by_screen: dict[str, dict] = {}
    screen_names: dict[str, str] = {}
    for meta, s2 in per_cluster:
        ids = meta["related_screens"] or universe
        for sid, htext, smd in _split_by_screen_headings(s2, ids):
            entry = by_screen.setdefault(sid, {"parts": []})
            entry["parts"].append((meta, smd))
            screen_names.setdefault(sid, _screen_name_from_heading(htext, sid))
            screen_to_clusters.setdefault(sid, [])
            if meta not in screen_to_clusters[sid]:
                screen_to_clusters[sid].append(meta)

    if not by_screen:
        # 화면 태깅 전무 — cluster 단위 fallback (WARN 은 호출부에서)
        return None

    # 4. 화면 단위 챕터 emit (Screen ID 자연순)
    chapters: list[str] = []
    for n, sid in enumerate(sorted(by_screen, key=_natural_key), start=1):
        name = screen_names.get(sid) or sid
        title = f"§{n} {name} ({sid})"
        body_parts: list[str] = []
        multi = len(by_screen[sid]["parts"]) > 1
        for meta, smd in by_screen[sid]["parts"]:
            inner = _strip_first_heading(smd).rstrip()
            if multi:
                body_parts.append(
                    f"### {meta['cluster_name']} ({meta['cluster_id']})\n\n{inner}\n"
                )
            else:
                body_parts.append(inner + "\n")
        chapters.append(
            f'::: {{.panel section="{title}"}}\n'
            f"## {title}\n\n"
            + "\n".join(body_parts).rstrip()
            + "\n:::\n"
        )

    screen_index_md = _render_screen_index(screen_to_clusters, screen_names)
    return screen_index_md, chapters


# ── target_template / 기본 frontmatter ──────────────────────────────────────


def _default_frontmatter(deliverable_type: str) -> dict:
    """target_template 없을 때 deliverable_type 기반 기본 frontmatter 생성.

    D2_policy.md / D3_screen.md / Dα_*.md 양식 따라 최소 골격.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    title_map = {
        "D2": "[정책정의서] {{PRODUCT_NAME}}",
        "D3": "[화면설계서] {{PRODUCT_NAME}}",
        "Da_api": "[API 스펙] {{PRODUCT_NAME}}",
        "Da_db": "[DB 스키마] {{PRODUCT_NAME}}",
        "Da_migration": "[마이그레이션 플랜] {{PRODUCT_NAME}}",
    }
    type_map = {
        "D2": "policy",
        "D3": "screen",
        "Da_api": "etc",
        "Da_db": "etc",
        "Da_migration": "etc",
    }
    related_links_map = {
        "D2": [
            "[[page:[요구사항 정의서] {{PRODUCT_NAME}}]]",
            "[[page:[화면설계서] {{PRODUCT_NAME}}]]",
        ],
        "D3": [
            "[[page:[요구사항 정의서] {{PRODUCT_NAME}}]]",
            "[[page:[정책정의서] {{PRODUCT_NAME}}]]",
        ],
        "Da_api": [
            "[[page:[정책정의서] {{PRODUCT_NAME}}]]",
            "[[page:[화면설계서] {{PRODUCT_NAME}}]]",
        ],
        "Da_db": [
            "[[page:[정책정의서] {{PRODUCT_NAME}}]]",
        ],
        "Da_migration": [
            "[[page:[정책정의서] {{PRODUCT_NAME}}]]",
        ],
    }
    related_block = "\n".join(
        f"            - {link}" for link in related_links_map[deliverable_type]
    )
    header_body = (
        f"**본 문서는 {{{{PRODUCT_NAME}}}}의 "
        f"{title_map[deliverable_type].split(']')[0][1:]} 정본이다.**\n\n"
        f"doc_id: {{{{DOC_ID}}}} 버전: {{{{VERSION}}}} 최종 수정: {{{{DATE}}}}"
    )
    return {
        "title": title_map[deliverable_type],
        "type": type_map[deliverable_type],
        "layer": "C",
        "version": 1.0,
        "last_updated": today,
        "publication": {
            "header": {"style": "info", "body": header_body},
            "meta": {
                "layout": "two_equal",
                "cells": [
                    {
                        "panel": {
                            "title": "참고 자료",
                            "body": (
                                "**관련 문서**\n\n"
                                + "\n".join(
                                    f"- {l}"
                                    for l in related_links_map[deliverable_type]
                                )
                            ),
                        }
                    },
                    {"change_history": 3},
                ],
            },
        },
        "transposed_from": "cluster_drafts (render_transpose.py)",
        "transposed_at": datetime.now().isoformat(timespec="seconds"),
    }


def _apply_template_frontmatter(
    template_path: Path, deliverable_type: str
) -> dict:
    """target_template 의 frontmatter 를 로드 + 갱신.

    - last_updated 를 오늘로 교체
    - transposed_from / transposed_at 메타 추가
    """
    if not template_path.exists():
        raise TransposeError(f"target_template 없음: {template_path}")
    try:
        raw = template_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise TransposeError(
            f"target_template 읽기 실패: {template_path} — {exc}"
        )
    fm, _body = _parse_frontmatter(raw)
    if not fm:
        # template frontmatter 가 없으면 기본 사용
        sys.stderr.write(
            f"[render_transpose] WARN: target_template frontmatter 없음 — "
            f"기본값 사용: {template_path}\n"
        )
        return _default_frontmatter(deliverable_type)
    fm["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    fm["transposed_from"] = "cluster_drafts (render_transpose.py)"
    fm["transposed_at"] = datetime.now().isoformat(timespec="seconds")
    return fm


# ── 메인 transpose 함수 ─────────────────────────────────────────────────────


def transpose(
    cluster_drafts: list[Path],
    deliverable_type: str,
    *,
    common_shell_clusters: list[Path] | None = None,
    target_template: Path | None = None,
) -> str:
    """cluster_draft 들에서 deliverable_type 섹션을 추출·어셈블 → MD source.

    Args:
        cluster_drafts: cluster_draft 파일 경로 목록
        deliverable_type: "D2" | "D3" | "Da_api" | "Da_db" | "Da_migration"
        common_shell_clusters: G2-COMMON-* cluster (D3 전용 — 다른 type 은 무시)
        target_template: 골격 frontmatter 출처 (선택)

    Returns:
        MD 문자열 (frontmatter + 챕터들 + 공통 셸 부록 D3 만)

    Raises:
        TransposeError — 파싱 / 매칭 / 구조 오류
        ValueError — deliverable_type 무효
    """
    if deliverable_type not in VALID_DELIVERABLES:
        raise ValueError(
            f"무효한 deliverable_type: {deliverable_type!r}. "
            f"허용: {sorted(VALID_DELIVERABLES)}"
        )

    # 1. cluster_draft 로드 + 필터링
    section_keyword = DELIVERABLE_SECTION_MAP[deliverable_type]
    type_keywords = DA_TYPE_KEYWORDS.get(deliverable_type)

    eligible: list[dict] = []
    for path in cluster_drafts:
        try:
            meta = _load_cluster_meta(path)
        except TransposeError as exc:
            sys.stderr.write(
                f"[render_transpose] WARN: {path} skip — {exc}\n"
            )
            continue
        if deliverable_type not in meta["deliverable_targets"]:
            continue
        if meta["is_common_shell"]:
            # is_common_shell 플래그가 켜진 cluster 는 일반 챕터에서 제외
            # (D3 부록은 별도 common_shell_clusters 인자로 받음)
            continue
        eligible.append(meta)

    # 2. 정렬
    eligible = _sort_clusters(eligible)

    # 3. 챕터 어셈블
    chapter_md: list[str] = []
    screen_index_md = ""

    # D3 는 화면 단위 챕터를 우선 시도(split-deliverable). 화면 태깅이 없으면
    # None 을 받아 cluster 단위 fallback 으로 내려간다(+WARN).
    if deliverable_type == "D3":
        screen_result = _assemble_d3_screen_chapters(eligible)
        if screen_result is not None:
            screen_index_md, chapter_md = screen_result
        else:
            sys.stderr.write(
                "[render_transpose] WARN: D3 §2 에 화면 ID 태깅 헤딩이 없어 "
                "화면 단위 분해 불가 — cluster 단위 챕터로 fallback\n"
            )

    if not chapter_md:
        chapter_num = 0
        for meta in eligible:
            extracted = _extract_panel_section(
                meta["text"], section_keyword, type_keywords=type_keywords
            )
            if not extracted:
                sys.stderr.write(
                    f"[render_transpose] WARN: {meta['cluster_id']} 에 "
                    f"{section_keyword}"
                    + (
                        f" ({'/'.join(type_keywords)})"
                        if type_keywords
                        else ""
                    )
                    + " 섹션 없음 — 건너뜀\n"
                )
                continue
            _sec, inner = extracted
            chapter_num += 1
            chapter_md.append(_assemble_chapter(meta, inner, chapter_num))

    if not chapter_md:
        raise TransposeError(
            f"deliverable_type={deliverable_type} 에 해당하는 cluster 0건 "
            f"(또는 모든 cluster 에 섹션 누락)"
        )

    # 4. 공통 셸 부록 (D3 만)
    appendix_md = ""
    common_metas: list[dict] = []
    if deliverable_type == "D3" and common_shell_clusters:
        for path in common_shell_clusters:
            try:
                meta = _load_cluster_meta(path)
            except TransposeError as exc:
                sys.stderr.write(
                    f"[render_transpose] WARN: common_shell {path} "
                    f"skip — {exc}\n"
                )
                continue
            common_metas.append(meta)
        appendix_md = _assemble_common_shell_appendix(
            common_metas, section_keyword
        )

    # 5. Frontmatter
    if target_template is not None:
        fm = _apply_template_frontmatter(target_template, deliverable_type)
    else:
        fm = _default_frontmatter(deliverable_type)
    # 기여 cluster 기록 — render_sync_check 가 deliverable 최신성을
    # 기여분 한정으로 판별한다(전체 draft max 비교의 false OUTDATED 방지).
    fm["source_clusters"] = [m["cluster_id"] for m in eligible + common_metas]

    fm_md = _render_frontmatter(fm)

    # 6. 최종 어셈블
    parts: list[str] = [fm_md, "\n"]
    if screen_index_md:
        parts.append(screen_index_md)
    parts.extend(chapter_md)
    if appendix_md:
        parts.append("\n")
        parts.append(appendix_md)
    return "\n".join(p.rstrip("\n") for p in parts) + "\n"


# ── CLI ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Cluster Draft → Deliverable Transpose (Phase 5F)"
    )
    ap.add_argument(
        "--cluster-drafts",
        nargs="+",
        required=True,
        type=Path,
        help="drafts/cluster_*.draft.md 목록 (1개 이상)",
    )
    ap.add_argument(
        "--deliverable",
        required=True,
        choices=sorted(VALID_DELIVERABLES),
        help="목적 deliverable_type",
    )
    ap.add_argument(
        "--output",
        required=True,
        type=Path,
        help="어셈블된 MD 출력 경로",
    )
    ap.add_argument(
        "--template",
        type=Path,
        default=None,
        help="목적 deliverable 양식 파일 (선택)",
    )
    ap.add_argument(
        "--common-shell",
        nargs="*",
        type=Path,
        default=None,
        help="D3 공통 셸 cluster draft 목록 (D3 전용)",
    )
    args = ap.parse_args(argv)

    # 입력 검증
    missing = [p for p in args.cluster_drafts if not p.exists()]
    if missing:
        sys.stderr.write(
            f"[render_transpose] ERROR: cluster_draft 없음: "
            f"{[str(p) for p in missing]}\n"
        )
        return 3

    if args.common_shell:
        missing_cs = [p for p in args.common_shell if not p.exists()]
        if missing_cs:
            sys.stderr.write(
                f"[render_transpose] ERROR: common_shell cluster 없음: "
                f"{[str(p) for p in missing_cs]}\n"
            )
            return 3

    if args.template is not None and not args.template.exists():
        sys.stderr.write(
            f"[render_transpose] ERROR: template 없음: {args.template}\n"
        )
        return 3

    # transpose
    try:
        result = transpose(
            cluster_drafts=list(args.cluster_drafts),
            deliverable_type=args.deliverable,
            common_shell_clusters=(
                list(args.common_shell) if args.common_shell else None
            ),
            target_template=args.template,
        )
    except TransposeError as exc:
        msg = str(exc)
        if "0건" in msg or "없음" in msg and "cluster" in msg.lower():
            sys.stderr.write(f"[render_transpose] {msg}\n")
            return 2
        sys.stderr.write(f"[render_transpose] 파싱 오류: {msg}\n")
        return 1
    except ValueError as exc:
        sys.stderr.write(f"[render_transpose] 인자 오류: {exc}\n")
        return 1

    # 출력
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"[render_transpose] IO 오류: {exc}\n")
        return 3

    n_chapters = result.count("::: {.panel section=")
    print(
        f"[render_transpose] {args.deliverable} → {args.output} "
        f"(panel 수={n_chapters})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
