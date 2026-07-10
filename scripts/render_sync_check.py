#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Draft ↔ Confluence XML 양방향 동기화 스캐너 (C-SYNC).

목적:
    drift_scan.py 가 Master(G2-A/B)→Draft 방향의 버전 drift 를 잡는다면,
    본 스크립트는 Draft ↔ Confluence XML 양방향의 sync gap 을 잡는다.

상태 분류:
    SYNCED        : draft 와 Confluence 모두 마지막 push 와 동일
    OUTDATED      : draft 가 더 최신 (push 필요 — `/render --push`)
    REMOTE-DRIFT  : Confluence 가 더 최신 (PM 이 Confluence 에서 편집 — merge-proposal 생성)
    PENDING       : meta.json 없음이거나 page_id 가 플레이스홀더("{{" 포함)
    REMOTE-UNKNOWN: wiki snapshot 미존재 (모델이 wiki 커넥터 조회 미실행)
    UNKNOWN       : updated_at 또는 last_published_at 파싱 불가

Remote drift 감지 패턴 (wiki 커넥터 연동):
    본 스크립트는 직접 원격 API 를 호출하지 않는다 (인증·도구 분리 원칙 —
    외부 I/O 는 항상 모델의 wiki 커넥터 도구 호출로만 수행, CONNECTORS.md).
    대신 모델(/render --check-sync 또는 /lc 진입 시)이 sync-queue 의 page_id
    목록을 보고 wiki 커넥터(예: Confluence 등 MCP 도구)로 각 페이지를 조회해
    결과를 reports/.confluence-snapshot/{page_id}.json 에 저장한다.
    본 스크립트는 그 snapshot 파일과 meta.json._sync.last_published_version 을
    비교한다.

    snapshot JSON 기대 shape (wiki 커넥터가 저장한 스냅샷):
        {
          "id": "12345",
          "version": {"number": 7, "when": "2026-05-28T..."},
          "title": "...",
          "body": {"storage": {"value": "<xml>...</xml>"}}
        }

    snapshot 미존재 시: REMOTE-UNKNOWN (오류 아님, 경고만)
    snapshot version > meta.json._sync.last_published_version: REMOTE-DRIFT
        → reports/inbox/{WO_ID}.merge-proposal.md 자동 생성

출력:
    PROJECTS/{product}/reports/sync-queue.md         (모든 상태)
    PROJECTS/{product}/reports/inbox/{WO_ID}.merge-proposal.md (REMOTE-DRIFT 시)

exit code:
    0 = OUTDATED / PENDING / REMOTE-DRIFT 없음
    1 = 위 셋 중 1건 이상
    2 = 인자 오류

사용법:
    python render_sync_check.py --hub-root <Hub> [--product <name>] [--with-remote]
    (--with-remote: confluence snapshot 도 검사. 생략 시 순방향만)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import _emit_common as C

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
ISO_DATE = re.compile(r"(\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?)")
PLACEHOLDER = re.compile(r"\{\{")

# meta.json 에서 마지막 publish 시각을 담는 키 후보 (우선순위 순)
META_PUBLISHED_KEYS = [
    ("_sync", "last_published_at"),
    ("lastUpdatedAt",),
    ("version", "when"),
]


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


def _extract_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    m = ISO_DATE.search(s)
    if not m:
        return None
    raw = m.group(1)
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(raw[:len(fmt) + 2], fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError:
            continue
    return None


def _get_meta_published(meta: dict) -> datetime | None:
    """meta.json 에서 last_published_at 을 다중 키 전략으로 추출."""
    for key_path in META_PUBLISHED_KEYS:
        obj = meta
        for k in key_path:
            if isinstance(obj, dict) and k in obj:
                obj = obj[k]
            else:
                obj = None
                break
        if obj and isinstance(obj, str):
            dt = _extract_iso(obj)
            if dt:
                return dt
    return None


def _classify(draft_upd: datetime | None, pub: datetime | None) -> tuple[str, str]:
    if draft_upd is None:
        return "UNKNOWN", "draft updated_at 파싱 불가"
    if pub is None:
        return "UNKNOWN", "meta.json last_published_at 파싱 불가"
    if pub >= draft_upd:
        return "SYNCED", f"게시({pub.date()}) >= draft 수정({draft_upd.date()})"
    return "OUTDATED", f"draft 수정({draft_upd.date()}) > 마지막 게시({pub.date()}) — push 필요"


# ── 발행 모드 (fix-plan-dossier-publish-split) ──────────────────────────────

# split-deliverable 발행 단위: (transpose deliverable, meta slug, 표시 라벨)
SPLIT_DELIVERABLES = [
    ("D2", "02-policy", "정책정의서"),
    ("D3", "03-screen-design", "화면설계서"),
]

# 발행 모드 무관 공통 발행 문서 (publication-map §0/§0-bis: D1/D4/D5 각 1페이지).
# (slug, 라벨, 소스 하위 디렉토리, 파일 glob) — 소스 파일이 없으면 행 생략.
# doc_id 는 meta 명명 규약과 동일한 `{slug}-{product}` 정본 키(sync_emit 과 정합).
COMMON_DOCS = [
    ("01-requirements", "요구사항정의서", "inputs", "requirements*.md"),
    ("04-meetings", "회의록", "meetings", "*.md"),
    ("05-research", "타사조사", "inputs", "research*.md"),
]


def _scan_common_docs(proj: Path, src_dir: Path, product: str) -> tuple[list[tuple], int, int]:
    """D1/D4/D5 공통 문서 스캔 (감사 2026-06-11 갭1 — D4/D5 미스캔 해소).

    draft 측 기준값: 소스 파일들의 frontmatter updated_at 최댓값,
    frontmatter 가 없으면(회의록 등) 파일 mtime 으로 폴백.
    Returns: (rows, n_outdated, n_pending)
    """
    rows: list[tuple] = []
    n_out = n_pend = 0
    for slug, label, subdir, pattern in COMMON_DOCS:
        d = proj / subdir
        files = [f for f in (sorted(d.glob(pattern)) if d.is_dir() else []) if f.is_file()]
        if not files:
            continue
        doc_id = f"{slug}-{product}"
        fname = files[0].name if len(files) == 1 else f"{subdir}/{pattern} ({len(files)}건)"

        sides: list[datetime] = []
        for f in files:
            fm = _parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
            dt = _extract_iso(fm.get("updated_at", "") or fm.get("frozen_at", ""))
            if dt is None:
                try:
                    dt = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                except OSError:
                    continue
            sides.append(dt)
        draft_side = max(sides) if sides else None

        meta_path: Path | None = None
        if src_dir.is_dir():
            cands = sorted(src_dir.glob(f"{slug}-{product}.meta.json")) \
                or sorted(src_dir.glob(f"{slug}*.meta.json"))
            if cands:
                meta_path = cands[0]
        if meta_path is None:
            rows.append((fname, doc_id, "—", "meta.json 없음", "PENDING",
                         f"{slug}-{product}.meta.json 없음 — /cr 로 페이지 생성·초기화 필요"))
            n_pend += 1
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            rows.append((fname, doc_id, str(meta_path.name), str(e), "UNKNOWN",
                         "meta.json 파싱 오류"))
            continue
        page_id = str(meta.get("id", ""))
        if PLACEHOLDER.search(page_id) or not page_id:
            rows.append((fname, doc_id, meta_path.name, "id=PLACEHOLDER",
                         "PENDING", "Confluence 페이지 미생성"))
            n_pend += 1
            continue
        pub = _get_meta_published(meta)
        status, reason = _classify(draft_side, pub)
        if status == "OUTDATED":
            n_out += 1
        rows.append((fname, doc_id, meta_path.name,
                     (draft_side.date().isoformat() if draft_side else "?"),
                     status, reason))
    return rows, n_out, n_pend


def _parse_source_clusters(text: str) -> set[str] | None:
    """assembled.md frontmatter 의 source_clusters 목록(블록/인라인 YAML 리스트).

    없으면 None — 호출 측은 전체 draft 기준으로 폴백한다.
    """
    m = FRONTMATTER.match(text)
    if not m:
        return None
    out: set[str] = set()
    in_block = False
    for ln in m.group(1).splitlines():
        if ln.startswith("source_clusters:"):
            rest = ln.partition(":")[2].strip()
            if rest.startswith("["):
                for tok in rest.strip("[]").split(","):
                    tok = tok.strip().strip("'\"")
                    if tok:
                        out.add(tok)
                return out or None
            in_block = True
            continue
        if in_block:
            s = ln.strip()
            if s.startswith("- "):
                out.add(s[2:].strip().strip("'\""))
            elif s and not ln.startswith((" ", "\t")):
                break
    return out or None


def _deliverable_source_clusters(proj: Path, dtype: str, slug: str) -> set[str] | None:
    """deliverable 의 기여 cluster 집합 — reports/render/ 의 assembled 산출물에서.

    render_transpose 가 frontmatter 에 source_clusters 를 기록한다(감사 갭4 대응).
    산출물/필드가 없으면 None(전체 draft 기준 폴백 — 종전 동작).
    """
    render_dir = proj / "reports" / "render"
    if not render_dir.is_dir():
        return None
    cands = sorted(render_dir.glob(f"{slug}*.assembled.md")) \
        + sorted(render_dir.glob(f"{dtype}_*.assembled.md"))
    for f in cands:
        try:
            srcs = _parse_source_clusters(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if srcs:
            return srcs
    return None


def _read_publication_mode(proj: Path) -> str:
    """graph/project-mode.json 의 publication_mode 를 읽는다.

    단일 소스(_emit_common.read_publication_mode)로 위임 — sync_emit 과 정합.
    파일/키 없으면 "dossier-page"(기존 동작) — dbaas 등 기존 프로젝트 회귀 가드.
    """
    return C.read_publication_mode(proj)


def _scan_split(
    proj: Path, drafts_dir: Path, src_dir: Path, product: str
) -> tuple[list[tuple], int, int]:
    """split-deliverable 모드 스캔.

    dossier draft 는 정본 소스이므로 **SOURCE-ONLY**(최저 severity, actionable 제외)
    행으로만 표기해 허위 PENDING 을 막는다. 실제 발행 단위는 D2 정책정의서 /
    D3 화면설계서 2개 deliverable 이며, 그 최신성은 *기여 dossier draft 의
    updated_at 최댓값* vs deliverable meta.json 의 last_published_at 으로 분류한다.

    Returns: (rows, n_outdated, n_pending)
    """
    rows: list[tuple] = []
    # cluster_id → updated_at — deliverable 별 기여 cluster 한정 비교용(감사 갭4).
    draft_upd_by_cluster: dict[str, datetime] = {}
    if drafts_dir.is_dir():
        for draft in sorted(drafts_dir.glob("*.draft.md")):
            text = draft.read_text(encoding="utf-8", errors="replace")
            fm = _parse_frontmatter(text)
            doc_id = fm.get("doc_id", draft.stem)
            upd_str = fm.get("updated_at", "") or fm.get("frozen_at", "")
            dt = _extract_iso(upd_str)
            # naive frontmatter 파서는 nested cluster: 블록의 cluster_id 도 평탄화해 잡는다.
            cluster_id = fm.get("cluster_id", "") or draft.stem.replace(".draft", "").replace("cluster_", "")
            if dt:
                draft_upd_by_cluster[cluster_id] = max(
                    dt, draft_upd_by_cluster.get(cluster_id, dt))
            rows.append((draft.name, doc_id, "—", upd_str or "?", "SOURCE-ONLY",
                         "split 정본 소스 — 발행 단위는 D2/D3 (actionable 제외)"))
    all_side = max(draft_upd_by_cluster.values()) if draft_upd_by_cluster else None

    n_out = n_pend = 0
    for _dtype, slug, label in SPLIT_DELIVERABLES:
        doc_id = f"{slug}-{product}"
        # 기여 cluster 가 기록돼 있으면 그 부분집합의 최댓값만 비교(false OUTDATED 방지).
        sources = _deliverable_source_clusters(proj, _dtype, slug)
        if sources:
            scoped = [dt for cid, dt in draft_upd_by_cluster.items() if cid in sources]
            draft_side = max(scoped) if scoped else all_side
        else:
            draft_side = all_side
        meta_path: Path | None = None
        if src_dir.is_dir():
            cands = sorted(src_dir.glob(f"{slug}-{product}.meta.json")) \
                or sorted(src_dir.glob(f"{slug}*.meta.json"))
            if cands:
                meta_path = cands[0]
        if meta_path is None:
            rows.append((f"{label} (assembled)", doc_id, "—", "meta.json 없음",
                         "PENDING", f"{slug}-{product}.meta.json 없음 — /cr split 계층으로 생성 필요"))
            n_pend += 1
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            rows.append((f"{label} (assembled)", doc_id, meta_path.name, str(e),
                         "UNKNOWN", "meta.json 파싱 오류"))
            continue
        page_id = str(meta.get("id", ""))
        if PLACEHOLDER.search(page_id) or not page_id:
            rows.append((f"{label} (assembled)", doc_id, meta_path.name, "id=PLACEHOLDER",
                         "PENDING", "Confluence 페이지 미생성 — templates/standard/ 로 신규 생성 필요"))
            n_pend += 1
            continue
        pub = _get_meta_published(meta)
        status, reason = _classify(draft_side, pub)
        if status == "OUTDATED":
            n_out += 1
        rows.append((f"{label} (assembled)", doc_id, meta_path.name,
                     (draft_side.date().isoformat() if draft_side else "?"),
                     status, reason))
    return rows, n_out, n_pend


# ── Remote (Confluence) drift 감지 ───────────────────────────────────────────

def _snapshot_path(proj: Path, page_id: str) -> Path:
    return proj / "reports" / ".confluence-snapshot" / f"{page_id}.json"


def _load_remote_snapshot(proj: Path, page_id: str) -> dict | None:
    """모델이 wiki 커넥터 조회로 저장한 snapshot 을 로드. 없으면 None."""
    p = _snapshot_path(proj, page_id)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _classify_remote(meta: dict, snapshot: dict | None) -> tuple[str, str, int | None, int | None]:
    """remote version vs local last_published_version 비교.

    반환: (status, reason, local_ver, remote_ver)
    """
    if snapshot is None:
        return ("REMOTE-UNKNOWN",
                "wiki snapshot 없음 — 모델이 wiki 커넥터 조회 미실행",
                None, None)
    sync_block = meta.get("_sync") or {}
    local_ver = sync_block.get("last_published_version")
    remote_ver = (snapshot.get("version") or {}).get("number")
    if not isinstance(local_ver, int) or not isinstance(remote_ver, int):
        return ("REMOTE-UNKNOWN",
                f"version 필드 누락 (local={local_ver}, remote={remote_ver})",
                local_ver if isinstance(local_ver, int) else None,
                remote_ver if isinstance(remote_ver, int) else None)
    if remote_ver > local_ver:
        return ("REMOTE-DRIFT",
                f"Confluence v{remote_ver} > 마지막 push v{local_ver} — Confluence 에서 편집됨",
                local_ver, remote_ver)
    # MEDIUM #11: remote < local 은 Confluence 페이지 롤백 또는 페이지 ID 오류 — 회귀 신호
    if remote_ver < local_ver:
        return ("REMOTE-ROLLBACK",
                f"Confluence v{remote_ver} < 마지막 push v{local_ver} — 페이지 롤백 또는 page_id 불일치 의심",
                local_ver, remote_ver)
    return ("SYNCED", f"Confluence v{remote_ver} == 마지막 push v{local_ver}", local_ver, remote_ver)


def _convert_tables_to_markdown(xml: str) -> str:
    """<table><tr><td>...</td></tr></table> → markdown 표 형식 변환.

    fact_preservation_check 가 표 셀을 추출하려면 `| cell |` 형식이 필요하다.
    """
    def _table_repl(table_match: re.Match) -> str:
        table_body = table_match.group(1)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_body, re.DOTALL | re.IGNORECASE)
        if not rows:
            return "\n"
        md_lines: list[str] = []
        for i, row in enumerate(rows):
            cells = re.findall(
                r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.DOTALL | re.IGNORECASE,
            )
            # 셀 내부 태그 제거 + 줄바꿈 정리
            clean_cells = []
            for c in cells:
                c = re.sub(r"<[^>]+>", "", c)
                c = re.sub(r"\s+", " ", c).strip()
                clean_cells.append(c)
            if not clean_cells:
                continue
            md_lines.append("| " + " | ".join(clean_cells) + " |")
            # 첫 행 다음에 헤더 구분선 추가 (모든 셀이 th 였거나 첫 행)
            if i == 0:
                md_lines.append("|" + "|".join(["---"] * len(clean_cells)) + "|")
        return "\n" + "\n".join(md_lines) + "\n"

    return re.sub(
        r"<table[^>]*>(.*?)</table>",
        _table_repl,
        xml,
        flags=re.DOTALL | re.IGNORECASE,
    )


def _strip_storage_xml(xml: str) -> str:
    """Confluence Storage Format XML 을 검토용 markdown 으로 변환.

    표는 markdown 표 형식으로 보존 (fact_preservation_check 호환).
    완벽한 변환 아님 — merge-proposal 에서 PM 이 차이를 인지하는 용도.
    실제 본문 적용은 render_apply_inbox.py 에서 수행.
    """
    if not xml:
        return ""
    # ac:* / ri:* 매크로 태그 제거 (열고닫는 형태)
    text = re.sub(r"</?ac:[^>]+>", "", xml)
    text = re.sub(r"</?ri:[^>]+>", "", text)
    # CDATA 풀기 (코드 블록 본문 보존)
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
    # 표 → markdown 변환 (다른 태그 제거 전에 처리)
    text = _convert_tables_to_markdown(text)
    # 헤딩 → markdown 헤더
    for level in range(1, 7):
        text = re.sub(
            rf"<h{level}[^>]*>(.*?)</h{level}>",
            lambda m, lv=level: "\n" + ("#" * lv) + " " + re.sub(r"<[^>]+>", "", m.group(1)).strip() + "\n",
            text, flags=re.DOTALL | re.IGNORECASE,
        )
    # 리스트
    text = re.sub(r"<li[^>]*>(.*?)</li>", lambda m: "- " + re.sub(r"<[^>]+>", "", m.group(1)).strip() + "\n", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"</?[uo]l[^>]*>", "\n", text)
    # 단락·줄바꿈
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</p>", "\n\n", text)
    text = re.sub(r"<p[^>]*>", "", text)
    # 굵게·기울임 → markdown
    text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<i[^>]*>(.*?)</i>", r"*\1*", text, flags=re.DOTALL | re.IGNORECASE)
    # 나머지 태그 모두 제거
    text = re.sub(r"<[^>]+>", "", text)
    # 연속 빈 줄 압축
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _write_merge_proposal(
    proj: Path,
    wo_id: str,
    page_id: str,
    local_ver: int | None,
    remote_ver: int | None,
    remote_snapshot: dict,
    draft_text: str,
) -> Path:
    """REMOTE-DRIFT 감지 시 PM 검토용 merge-proposal 생성."""
    inbox_dir = proj / "reports" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    out_path = inbox_dir / f"{wo_id}.merge-proposal.md"

    remote_storage = ((remote_snapshot.get("body") or {}).get("storage") or {}).get("value", "")
    remote_text = _strip_storage_xml(remote_storage)

    # draft 본문에서 frontmatter 제거 (비교 용이)
    fm_match = FRONTMATTER.match(draft_text)
    local_body = draft_text[fm_match.end():] if fm_match else draft_text

    # CRITICAL #2: apply 가 추출하는 본문은 ``` 펜스가 아닌 HTML 주석 sentinel 로 감싼다
    # (Confluence 본문이 ``` 를 포함해도 추출이 안전하도록).
    remote_truncated = remote_text[:20000]
    remote_overflow = "" if len(remote_text) <= 20000 else f"\n\n_… 이하 생략 (전체 {len(remote_text)}자)_"
    local_truncated = local_body[:20000]
    local_overflow = "" if len(local_body) <= 20000 else f"\n\n_… 이하 생략 (전체 {len(local_body)}자)_"
    storage_truncated = remote_storage[:10000]
    storage_overflow = "" if len(remote_storage) <= 10000 else f"\n\n_… 이하 생략 (전체 {len(remote_storage)}자)_"

    lines = [
        f"# Merge Proposal — {wo_id} (REMOTE-DRIFT 감지)",
        "",
        f"> 생성: {datetime.now().isoformat(timespec='seconds')}",
        f"> page_id: `{page_id}`  ·  Confluence v{remote_ver}  vs  마지막 push v{local_ver}",
        f"> 자동 생성 (수정 금지) — render_sync_check.py",
        "",
        "## 처리 방법",
        "",
        "아래 두 본문을 비교 후 다음 중 하나 선택:",
        "",
        f"- [ ] **전체 본문 채택** (Confluence 본문으로 draft 덮어쓰기 — `/render --apply-inbox {wo_id}` 가 처리)",
        "- [ ] **수동 검토 완료** (PM 이 /write 등으로 수동 반영, 본 proposal 은 archive)",
        "",
        "두 항목 모두 미체크 상태로 `/render --apply-inbox` 호출 시 NOOP (proposal 유지).",
        "전체 본문 채택 선택 시 적용 직후 fact_preservation_check 자동 실행 — fact 손실 발견 시 차단.",
        "",
        "---",
        "",
        f"## Confluence (현재 v{remote_ver}) 본문 — apply 시 사용",
        "",
        "<!-- confluence-body:start -->",
        remote_truncated + remote_overflow,
        "<!-- confluence-body:end -->",
        "",
        "## Local draft 본문 (frontmatter 제외, 참고용)",
        "",
        "<!-- local-body:start -->",
        local_truncated + local_overflow,
        "<!-- local-body:end -->",
        "",
        "---",
        "",
        "## 원본 Confluence Storage Format (참고용 — apply 시 직접 사용 X)",
        "",
        "<!-- storage-xml:start -->",
        storage_truncated + storage_overflow,
        "<!-- storage-xml:end -->",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def scan(hub_root: Path, product: str | None = None, with_remote: bool = False) -> int:
    projects_root = hub_root / "PROJECTS"
    if not projects_root.is_dir():
        print(f"[sync_check] PROJECTS 없음: {projects_root} — 스캔 대상 없음")
        return 0

    products = (
        [projects_root / product]
        if product
        else sorted(p for p in projects_root.iterdir() if p.is_dir())
    )

    total_outdated = 0
    total_pending = 0
    total_remote_drift = 0
    total_remote_unknown = 0

    for proj in products:
        pname = proj.name
        drafts_dir = proj / "drafts"
        src_dir = proj / "confluence-source"
        rows: list[tuple] = []
        # 본 product 의 draft 본문 캐시 (merge-proposal 생성용)
        draft_text_cache: dict[str, str] = {}

        # 발행 모드 분기 (fix-plan-dossier-publish-split).
        pub_mode = _read_publication_mode(proj)

        # ── split-deliverable: dossier 는 SOURCE-ONLY, 발행은 D2/D3 2단위 ──
        if pub_mode == "split-deliverable":
            srows, s_out, s_pend = _scan_split(proj, drafts_dir, src_dir, pname)
            rows.extend(srows)
            total_outdated += s_out
            total_pending += s_pend

        # ── dossier-page (기본): draft 1개 = 페이지 1개 ──────────────────────
        elif drafts_dir.is_dir():
            for draft in sorted(drafts_dir.glob("*.draft.md")):
                text = draft.read_text(encoding="utf-8", errors="replace")
                fm = _parse_frontmatter(text)
                doc_id = fm.get("doc_id", draft.stem)
                upd_str = fm.get("updated_at", "") or fm.get("frozen_at", "")
                draft_upd = _extract_iso(upd_str)

                # 대응하는 meta.json 탐색 (per-dossier — fix-plan-dossier-publish).
                # dossier 모델은 dossier 1개 = 페이지 1개이므로 각 draft 는 자신의
                # meta.json 과만 매칭한다. "첫 meta 폴백" 은 모든 dossier 가 같은
                # 페이지로 잘못 매칭되므로 쓰지 않는다(meta 없으면 PENDING).
                #
                # H3 (감사 2026-06-08): 과거엔 meta **파일명** substring 으로만
                # 매칭해 cr 이 만든 {WO_ID}.meta.json(예: G2-K-PR-01) 과 draft stem
                # (cluster_PR-01) 이 어긋나 발행 후에도 영구 PENDING 으로 보고됐다.
                # 이제 sync_emit 과 동일하게 meta **내부 식별자**(wo_id/doc_id/cluster_id)
                # 로 조인한다. 레거시 파일명 substring 매칭도 폴백으로 유지.
                stem_hint = draft.stem.replace(".draft", "")
                wo_id_fm = fm.get("wo_id", "")
                draft_keys = {
                    k.lower() for k in (stem_hint, doc_id, wo_id_fm) if k
                }
                # 결정적 조인 (감사 2026-06-11 갭3): ① 내부 식별자 정확 일치
                # ② 파일명 stem 정확 일치 ③ 레거시 substring(후방 호환 폴백).
                # 종전엔 ①~③ 을 한 조건으로 합쳐 glob 정렬 첫 일치에 의존했고,
                # 유사 ID(PR-01 / PR-010)가 잘못 매칭될 수 있었다. 동일 tier 에서
                # 복수 일치 시 경고를 남기고 정렬 첫 항목을 쓴다(결정적).
                meta_path: Path | None = None
                meta: dict | None = None
                if src_dir.is_dir():
                    cands: list[tuple[Path, dict | None]] = []
                    for f in sorted(src_dir.glob("*.meta.json")):
                        try:
                            cand = json.loads(f.read_text(encoding="utf-8", errors="replace"))
                        except Exception:
                            cand = None
                        cands.append((f, cand if isinstance(cand, dict) else None))

                    def _internal_ids(c: dict | None) -> set[str]:
                        if not c:
                            return set()
                        return {str(c[mk]).lower()
                                for mk in ("wo_id", "doc_id", "cluster_id") if c.get(mk)}

                    tiers = [
                        [(f, c) for f, c in cands if draft_keys & _internal_ids(c)],
                        [(f, c) for f, c in cands if f.stem.lower() in draft_keys],
                        [(f, c) for f, c in cands
                         if any(dk in f.stem.lower() for dk in draft_keys)],
                    ]
                    for matched in tiers:
                        if matched:
                            if len(matched) > 1:
                                names = ", ".join(f.name for f, _ in matched)
                                print(f"[sync_check] WARN: {pname}/{draft.name} meta 다중 일치"
                                      f" ({names}) — 첫 항목 사용", file=sys.stderr)
                            meta_path, meta = matched[0]
                            break

                if meta_path is None:
                    rows.append((draft.name, doc_id, "—", "meta.json 없음", "PENDING",
                                 "이 dossier 의 meta.json 없음 — /cr 로 페이지 생성·초기화 필요"))
                    total_pending += 1
                    continue

                if meta is None:
                    rows.append((draft.name, doc_id, str(meta_path.name),
                                 "JSON 파싱 오류", "UNKNOWN", "meta.json 파싱 오류"))
                    continue

                # page_id 플레이스홀더 체크
                page_id = str(meta.get("id", ""))
                if PLACEHOLDER.search(page_id) or not page_id:
                    rows.append((draft.name, doc_id, meta_path.name, "id=PLACEHOLDER",
                                 "PENDING", "Confluence 페이지 미생성 — templates/standard/ 로 신규 생성 필요"))
                    total_pending += 1
                    continue

                pub = _get_meta_published(meta)
                status, reason = _classify(draft_upd, pub)
                if status == "OUTDATED":
                    total_outdated += 1
                # 순방향 행 추가
                rows.append((draft.name, doc_id, meta_path.name,
                             upd_str or "?", status, reason))

                # ── 역방향 (Confluence remote drift) 검사 ────────────────
                if with_remote and not PLACEHOLDER.search(page_id) and page_id:
                    snapshot = _load_remote_snapshot(proj, page_id)
                    r_status, r_reason, l_ver, r_ver = _classify_remote(meta, snapshot)
                    rows.append((
                        draft.name, doc_id, meta_path.name,
                        f"local v{l_ver} / remote v{r_ver}" if (l_ver or r_ver) else "—",
                        r_status, r_reason,
                    ))
                    if r_status == "REMOTE-DRIFT":
                        total_remote_drift += 1
                        # WO_ID 추출: drafts/WO-NN.draft.md → WO-NN
                        wo_id = draft.stem.replace(".draft", "")
                        try:
                            proposal_path = _write_merge_proposal(
                                proj, wo_id, page_id, l_ver, r_ver,
                                snapshot or {}, text,
                            )
                            print(f"[sync_check] {pname}: REMOTE-DRIFT {wo_id} "
                                  f"→ {proposal_path.relative_to(hub_root)}")
                        except Exception as exc:
                            print(f"[sync_check] WARN: merge-proposal 생성 실패 ({wo_id}): {exc}",
                                  file=sys.stderr)
                    elif r_status == "REMOTE-UNKNOWN":
                        total_remote_unknown += 1

        # ── 공통 발행 문서 스캔 (D1 요구사항 · D4 회의록 · D5 타사조사) ─────
        crows, c_out, c_pend = _scan_common_docs(proj, src_dir, pname)
        rows.extend(crows)
        total_outdated += c_out
        total_pending += c_pend

        # ── 보고서 저장 ──────────────────────────────────────────────────────
        reports = proj / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        out = reports / "sync-queue.md"

        n_out = sum(1 for r in rows if r[4] == "OUTDATED")
        n_pend = sum(1 for r in rows if r[4] == "PENDING")
        n_unk = sum(1 for r in rows if r[4] == "UNKNOWN")
        n_drift = sum(1 for r in rows if r[4] == "REMOTE-DRIFT")
        n_runk = sum(1 for r in rows if r[4] == "REMOTE-UNKNOWN")
        n_src = sum(1 for r in rows if r[4] == "SOURCE-ONLY")

        lines = [
            f"# sync-queue — {pname}",
            "",
            f"> 생성: {datetime.now().isoformat(timespec='seconds')}"
            f" · render_sync_check.py 자동 생성 (수정 금지)"
            + (f" · 발행 모드: {pub_mode}" if pub_mode != "dossier-page" else ""),
            f"> **OUTDATED: {n_out} · REMOTE-DRIFT: {n_drift} · PENDING: {n_pend}"
            f" · REMOTE-UNKNOWN: {n_runk} · UNKNOWN: {n_unk}**"
            + (f" · SOURCE-ONLY: {n_src}" if n_src else ""),
            "",
            "| 파일 | doc_id | meta.json | 기준값 | 상태 | 사유 |",
            "|---|---|---|---|---|---|",
        ]
        if rows:
            for fname, did, mname, upd, st, why in rows:
                lines.append(f"| {fname} | `{did}` | {mname} | {upd} | **{st}** | {why} |")
        else:
            lines.append("| _(대상 없음)_ | — | — | — | — | drafts/ 또는 inputs/ 비어있음 |")

        lines += [
            "",
            "## 처리 기준",
            "- **OUTDATED**: draft 수정 이후 push 미실시 — `/render --push` 로 동기화",
            "- **REMOTE-DRIFT**: Confluence 가 더 최신 (PM 이 Confluence 에서 편집) — `reports/inbox/{WO}.merge-proposal.md` 검토 후 `/render --apply-inbox {WO}` 또는 수동 반영",
            "- **PENDING**: Confluence 페이지 미생성 — templates/standard/ 기본 양식으로 신규 생성 후 meta.json 초기화",
            "- **REMOTE-UNKNOWN**: wiki snapshot 없음 — 모델이 wiki 커넥터로 페이지를 조회해 `reports/.confluence-snapshot/{id}.json` 에 저장하는 단계 미실행",
            "- **UNKNOWN**: updated_at/last_published_at 파싱 불가 — 날짜 형식 점검 (ISO 8601 권장)",
            "- **SYNCED**: 정상 — 추가 조치 불필요",
        ]
        if n_src:
            lines.append(
                "- **SOURCE-ONLY**: split-deliverable 모드의 dossier 정본 소스 — "
                "발행 단위가 아니므로 actionable 제외 (D2/D3 deliverable 행 참조)"
            )
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[sync_check] {pname}: OUTDATED={n_out} REMOTE-DRIFT={n_drift}"
              f" PENDING={n_pend} REMOTE-UNKNOWN={n_runk} UNKNOWN={n_unk}"
              f" → {out.relative_to(hub_root)}")

    total_actionable = total_outdated + total_pending + total_remote_drift
    print(f"[sync_check] 완료 — OUTDATED {total_outdated}건 REMOTE-DRIFT {total_remote_drift}건"
          f" PENDING {total_pending}건 REMOTE-UNKNOWN {total_remote_unknown}건"
          + ("" if total_actionable == 0 else " (sync 필요)"))
    return 1 if total_actionable > 0 else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Draft↔Confluence 양방향 동기화 스캔")
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--product", default=None, help="PROJECTS/<product> (생략=전체)")
    ap.add_argument("--with-remote", action="store_true",
                    help="reports/.confluence-snapshot/ 의 remote 버전과도 비교 (REMOTE-DRIFT 감지)")
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2
    return scan(args.hub_root, args.product, with_remote=args.with_remote)


if __name__ == "__main__":
    sys.exit(main())
