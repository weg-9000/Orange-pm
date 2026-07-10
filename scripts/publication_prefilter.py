#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Publication prefilter — process metadata 결정적 제거 (Source → Publication 단계 1).

Source layer (drafts/*.draft.md) 는 DEC·open-issues·TBD·자기검증 체크리스트 등
process metadata 를 포함한다. Confluence 정본은 클린본이 필요하다.

본 스크립트는 LLM 없이 정규식 기반으로 제거·치환만 수행한다 (재현성·검증성).
LLM 어투 정규화는 별도 단계(/render --push --style-example)에서 처리한다.

제거 항목:
    - HTML 주석 (<!-- ... -->)
    - 자기 검증 체크리스트 섹션 ("## N. 자기 검증 체크리스트" 부터 다음 H2 직전까지)
    - 금지 사항 섹션
    - 작업 지시 메타블록 (RACI 등) — 정책 사실 아닌 작성 가이드
    - render_assemble 출처 태그 (⟦전개: {id}@{ver} … 출처⟧)
    - frontmatter slim down (wo_id/type/layer/version/last_updated만 유지)

치환 항목:
    - [TBD — ...]             → (미확정)
    - [확인 필요: ...]         → (검토 중)
    - [정책 충돌 — ...]        → (검토 필요 — 양립 항목 보존)
    - <!-- DEC: ... -->        → 제거

보존:
    - 모든 표 셀
    - 모든 정책 본문 텍스트
    - 모든 [[POL §X-Y]] 마커
    - 모든 [[WO-XX]] 마커 (Confluence 페이지 링크로 후속 변환됨)
    - {PREFIX}-A 등재 어휘

exit code:
    0 = 성공
    1 = 입력 파일 미존재 또는 파싱 오류
    2 = 사용법 오류
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ── 정규식 패턴 ──────────────────────────────────────────────────────────────

# HTML 주석 (multi-line 포함)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# render_assemble 출처 태그: ⟦전개: id@ver … 출처⟧
SOURCE_TAG_RE = re.compile(r"⟦전개:[^⟧]*⟧")

# TBD / 확인 필요 / 정책 충돌 마커
TBD_RE = re.compile(r"\[TBD[^\]]*\]")
CONFIRM_NEEDED_RE = re.compile(r"\[확인\s*필요[^\]]*\]")
POLICY_CONFLICT_RE = re.compile(r"\[정책\s*충돌[^\]]*\]")

# H2 섹션 헤더
H2_RE = re.compile(r"^##\s+(.+?)$", re.MULTILINE)

# Frontmatter 추출
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# 제거 대상 섹션 제목 패턴 (## N. <title> 형식 또는 ## <title>)
SECTION_REMOVE_PATTERNS = [
    re.compile(r"^##\s+\d+\.\s*자기\s*검증\s*체크리스트\s*$", re.MULTILINE),
    re.compile(r"^##\s+자기\s*검증\s*체크리스트\s*$", re.MULTILINE),
    re.compile(r"^##\s+\d+\.\s*금지\s*사항\s*$", re.MULTILINE),
    re.compile(r"^##\s+금지\s*사항\s*$", re.MULTILINE),
    re.compile(r"^##\s+\d+\.\s*완료\s*후\s*절차\s*$", re.MULTILINE),
    re.compile(r"^##\s+완료\s*후\s*절차\s*$", re.MULTILINE),
    re.compile(r"^##\s+Workflow\s+Connections\s*$", re.MULTILINE),
    re.compile(r"^##\s+불변\s*입력\s*$", re.MULTILINE),
    re.compile(r"^##\s+\d+\.\s*불변\s*입력\s*$", re.MULTILINE),
    re.compile(r"^##\s+할당\s*범위\s*$", re.MULTILINE),
    re.compile(r"^##\s+\d+\.\s*할당\s*범위\s*$", re.MULTILINE),
]

# Frontmatter 에서 publication 에 유지할 필드만 화이트리스트
PUBLICATION_FRONTMATTER_FIELDS = {
    "wo_id", "type", "layer", "version", "last_updated", "title",
}


def _strip_section(text: str, header_pattern: re.Pattern) -> str:
    """header_pattern 이 매칭하는 H2 섹션을 다음 H2 직전까지 (또는 EOF까지) 제거."""
    m = header_pattern.search(text)
    if not m:
        return text
    start = m.start()
    # 다음 H2 찾기 — 같은 레벨 헤더 또는 그 이상
    next_h2 = H2_RE.search(text, m.end())
    end = next_h2.start() if next_h2 else len(text)
    return text[:start] + text[end:]


def _slim_frontmatter(text: str) -> str:
    """frontmatter 에서 publication 화이트리스트 필드만 유지.

    HIGH #5: multi-line YAML 값(block list, folded scalar '>', literal '|',
    continuation indent) 도 보존. 키 라인은 colon 위치 + 들여쓰기 0 으로 판단,
    하위 들여쓰기 라인은 직전 키의 continuation 으로 취급.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return text
    fm_body = m.group(1)
    rest = text[m.end():]

    kept_lines: list[str] = []
    current_key_kept = False  # 직전 key 가 화이트리스트인지
    for line in fm_body.splitlines():
        stripped = line.strip()
        if not stripped:
            # 빈 줄 — 직전 키의 영역 종료
            current_key_kept = False
            continue
        if stripped.startswith("#"):
            continue
        # 들여쓰기 (continuation line) 여부
        is_indented = line and line[0] in (" ", "\t")
        if is_indented:
            if current_key_kept:
                kept_lines.append(line)
            continue
        # top-level 키 라인
        if ":" not in stripped:
            # 비정상 — 안전하게 skip
            current_key_kept = False
            continue
        key = stripped.split(":", 1)[0].strip()
        if key in PUBLICATION_FRONTMATTER_FIELDS:
            kept_lines.append(line)
            current_key_kept = True
        else:
            current_key_kept = False
    if not kept_lines:
        return rest
    return "---\n" + "\n".join(kept_lines) + "\n---\n" + rest


def _collapse_blank_lines(text: str) -> str:
    """연속 3개 이상 빈 줄을 2개로 압축."""
    return re.sub(r"\n{3,}", "\n\n", text)


def prefilter(text: str) -> str:
    """publication prefilter 적용 — process metadata 제거 + 마커 치환.

    멱등 보장: 두 번 호출해도 동일 결과.
    """
    # 1. frontmatter slim
    text = _slim_frontmatter(text)

    # 2. 섹션 단위 제거 (자기검증/금지/완료절차/Workflow Connections/불변입력/할당범위)
    for pattern in SECTION_REMOVE_PATTERNS:
        while pattern.search(text):
            new_text = _strip_section(text, pattern)
            if new_text == text:
                break
            text = new_text

    # 3. HTML 주석 제거 (render_assemble schema marker, DEC 마커 등 포함)
    text = HTML_COMMENT_RE.sub("", text)

    # 4. 출처 태그 제거 (⟦전개: ...⟧)
    text = SOURCE_TAG_RE.sub("", text)

    # 5. TBD/확인필요/정책충돌 → 단순 placeholder
    text = TBD_RE.sub("(미확정)", text)
    text = CONFIRM_NEEDED_RE.sub("(검토 중)", text)
    text = POLICY_CONFLICT_RE.sub("(검토 필요 — 양립 항목 보존)", text)

    # 6. 연속 빈 줄 압축
    text = _collapse_blank_lines(text)

    return text.strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Publication prefilter — process metadata 결정적 제거"
    )
    ap.add_argument("input", type=Path, help="입력 파일 (보통 reports/render/{WO}.complete.md)")
    ap.add_argument(
        "--output", "-o", type=Path, default=None,
        help="출력 파일 (생략 시 stdout)"
    )
    ap.add_argument(
        "--in-place", action="store_true",
        help="입력 파일을 결과로 덮어쓴다 (--output 와 함께 사용 금지)"
    )
    args = ap.parse_args()

    if not args.input.is_file():
        print(f"[prefilter] FAIL: 입력 파일 없음 — {args.input}", file=sys.stderr)
        return 1

    if args.in_place and args.output:
        print("[prefilter] FAIL: --in-place 와 --output 동시 사용 불가", file=sys.stderr)
        return 2

    text = args.input.read_text(encoding="utf-8")
    result = prefilter(text)

    if args.in_place:
        args.input.write_text(result, encoding="utf-8")
        print(f"[prefilter] OK: {args.input} (in-place)", file=sys.stderr)
    elif args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
        print(f"[prefilter] OK: {args.input} → {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
