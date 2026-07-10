#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""drafts/*.draft.md 표준 frontmatter 적용 (개선안 H — CONTEXT_OPTIMIZATION.md).

목적:
    reviewer / integrator 가 본문 로드 전 1차 스캔으로 후보군을 좁힐 수 있도록
    모든 draft 파일 상단에 다음 형식의 frontmatter 를 보장한다.

    ---
    wo_id: {PREFIX}-C-001
    type: policy           # policy | screen
    layer: C
    status: draft          # draft | review | frozen
    referenced_policies: [G2-B-001, G2-B-005]
    referenced_master:   [G2-B-002@v1.3, G2-A-001@v1.1]
    referenced_screens:    []
    related_decisions:     []
    last_updated: 2026-05-06
    ---

    빠진 필드는 (deprecated) work-orders/{WO_ID}.md 에서 추론한다(존재 시).
    안 A(WO 템플릿 ↔ draft 1-파일화) 이후 work-orders/*.md 본문 파일은 더 이상
    표준 경로가 아니며, drafts/{WO_ID}.draft.md 만 정본이다. 호환을 위해 추론
    로직은 잔존하지만, 신규 프로젝트에서는 derive_from_wo() 호출이 빈 dict 를 반환한다.
    이미 frontmatter 가 있으면 누락 필드만 보강하고 기존 값은 보존한다.

    status 필드 자동 추가:
        기존 drafts/*.draft.md 마이그레이션 시 status 필드가 없으면 'ai-draft' 로 자동
        지정한다(역추론: 기존 draft 는 모두 ai-draft 단계로 간주).

사용법:
    python migrate_draft_frontmatter.py --hub-root <Hub> --product <product>
    python migrate_draft_frontmatter.py --hub-root <Hub> --product <product> --check
        (--check: 누락만 보고하고 파일 변경 없음. exit 1 = 누락 존재)
    python migrate_draft_frontmatter.py --hub-root <Hub> --product <product> --convert-wo-to-draft
        (안 A 마이그레이션: work-orders/{WO_ID}.md → drafts/{WO_ID}.draft.md 변환 후
         원본을 .archive/work-orders/ 로 이동. index.md/index.json 은 유지.)

exit code:
    0 = 모두 정상 또는 마이그레이션 완료
    1 = --check 모드에서 누락 발견
    2 = 인자 오류
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

FRONTMATTER_PATTERN = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
WO_ID_PATTERN = re.compile(r"^([A-Za-z0-9]+-[A-Z]-[A-Za-z0-9]+-\d{3,})$")
WO_TYPE_PATTERN = re.compile(r"^\*?\*?type\*?\*?\s*[:：]\s*[`']?(policy|screen)[`']?", re.MULTILINE)
WO_INHERITS_LINE = re.compile(r"\| inherits_from \| ([A-Za-z0-9-]+) ", re.MULTILINE)
WO_INCLUDES_LINE = re.compile(r"\| includes \| ([A-Za-z0-9-]+) ", re.MULTILINE)

REQUIRED_FIELDS = [
    "wo_id",
    "type",
    "layer",
    "status",
    "referenced_policies",
    "referenced_master",
    "referenced_screens",
    "related_decisions",
    "last_updated",
]


def parse_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}, text
    body = text[match.end() :]
    fm: dict = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip()
    return fm, body


def render_frontmatter(fm: dict) -> str:
    lines = ["---"]
    for key in REQUIRED_FIELDS:
        value = fm.get(key, "")
        if isinstance(value, list):
            inner = ", ".join(value)
            lines.append(f"{key}: [{inner}]")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def parse_list_value(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw or raw == "[]":
        return []
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [item.strip() for item in raw.split(",") if item.strip()]


def derive_from_wo(wo_path: Path) -> dict:
    if not wo_path.exists():
        return {}
    body = wo_path.read_text(encoding="utf-8")
    info: dict = {}
    type_match = WO_TYPE_PATTERN.search(body)
    if type_match:
        info["type"] = type_match.group(1)
    inherits = WO_INHERITS_LINE.findall(body)
    info["referenced_policies"] = inherits
    includes = WO_INCLUDES_LINE.findall(body)
    info["referenced_includes"] = includes
    return info


def derive_wo_id_from_filename(name: str) -> str | None:
    stem = name.replace(".draft.md", "")
    return stem if WO_ID_PATTERN.match(stem) else None


def merge(fm: dict, wo_id: str, wo_info: dict) -> dict:
    merged: dict = dict(fm)
    merged.setdefault("wo_id", wo_id)
    merged.setdefault("type", wo_info.get("type", "policy"))
    merged.setdefault("layer", "C")
    # 안 A: 기존 draft 는 모두 ai-draft 단계로 역추론.
    # 단, 'status' 가 이미 존재하면 절대 덮어쓰지 않는다(보존 우선).
    merged.setdefault("status", "ai-draft")

    pol_existing = parse_list_value(merged.get("referenced_policies", "")) if isinstance(
        merged.get("referenced_policies"), str
    ) else merged.get("referenced_policies", [])
    if not pol_existing and wo_info.get("referenced_policies"):
        pol_existing = wo_info["referenced_policies"]
    merged["referenced_policies"] = pol_existing or []

    mst_existing = parse_list_value(merged.get("referenced_master", "")) if isinstance(
        merged.get("referenced_master"), str
    ) else merged.get("referenced_master", [])
    merged["referenced_master"] = mst_existing or []

    scr_existing = parse_list_value(merged.get("referenced_screens", "")) if isinstance(
        merged.get("referenced_screens"), str
    ) else merged.get("referenced_screens", [])
    merged["referenced_screens"] = scr_existing or []

    dec_existing = parse_list_value(merged.get("related_decisions", "")) if isinstance(
        merged.get("related_decisions"), str
    ) else merged.get("related_decisions", [])
    merged["related_decisions"] = dec_existing or []

    merged.setdefault("last_updated", date.today().isoformat())
    return merged


def process(hub_root: Path, product: str, check_only: bool) -> int:
    project_dir = hub_root / "PROJECTS" / product
    drafts_dir = project_dir / "drafts"
    wo_dir = project_dir / "work-orders"
    if not drafts_dir.is_dir():
        sys.stderr.write(f"drafts dir not found: {drafts_dir}\n")
        return 1

    drafts = sorted(drafts_dir.glob("*.draft.md"))
    if not drafts:
        print(f"[migrate_draft_frontmatter] no drafts under {drafts_dir}")
        return 0

    missing: list[str] = []
    migrated = 0
    for draft in drafts:
        wo_id = derive_wo_id_from_filename(draft.name)
        if not wo_id:
            sys.stderr.write(f"[skip] cannot derive wo_id from {draft.name}\n")
            continue
        text = draft.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        existing_keys = set(fm.keys())
        absent = [key for key in REQUIRED_FIELDS if key not in existing_keys]

        if check_only:
            if absent:
                missing.append(f"{draft.name}: missing {','.join(absent)}")
            continue

        if not absent:
            continue

        wo_info = derive_from_wo(wo_dir / f"{wo_id}.md")
        merged = merge(fm, wo_id, wo_info)
        new_text = render_frontmatter(merged) + body
        draft.write_text(new_text, encoding="utf-8")
        migrated += 1
        print(f"[migrate] {draft.name} ← added: {','.join(absent)}")

    if check_only:
        if missing:
            sys.stderr.write("[check] frontmatter missing in:\n")
            for line in missing:
                sys.stderr.write(f"  - {line}\n")
            return 1
        print(f"[check] all drafts have frontmatter ({len(drafts)})")
        return 0

    print(f"[migrate_draft_frontmatter] migrated={migrated}/{len(drafts)}")
    return 0


STATUS_FIELD_PATTERN = re.compile(r"^status\s*:\s*(\S+)\s*$", re.MULTILINE)
VALID_STATUSES_PROMOTED = {"ai-draft", "human-reviewed", "frozen"}


def _read_status_field(text: str) -> str | None:
    """draft 본문에서 status 필드 값을 읽는다(frontmatter 영역 한정).

    frontmatter 가 없거나 status 필드가 없으면 None.
    """
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return None
    fm_block = match.group(1)
    status_match = STATUS_FIELD_PATTERN.search(fm_block)
    if not status_match:
        return None
    return status_match.group(1).strip()


def _ensure_status_field(text: str, status_value: str) -> str:
    """draft 본문에 frontmatter status 필드가 없으면 삽입한다(있으면 보존).

    - frontmatter 가 아예 없으면: 최소 frontmatter 블록을 새로 만들어 status 만 삽입.
    - frontmatter 는 있고 status 만 없으면: frontmatter 끝에 status 라인 추가.
    - frontmatter 와 status 모두 있으면: 원본 그대로 반환(덮어쓰기 금지).
    """
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        # frontmatter 없음 → 최소 블록 신설
        new_fm = f"---\nstatus: {status_value}\n---\n"
        return new_fm + text
    fm_block = match.group(1)
    if STATUS_FIELD_PATTERN.search(fm_block):
        return text  # 이미 status 존재 — 절대 덮어쓰지 않음
    body = text[match.end() :]
    new_fm = f"---\n{fm_block}\nstatus: {status_value}\n---\n"
    return new_fm + body


TYPE_FIELD_PATTERN = re.compile(r"^type\s*:\s*(\S+)\s*$", re.MULTILINE)
REVIEW_STATUS_FIELD_PATTERN = re.compile(r"^review_status\s*:", re.MULTILINE)


def _ensure_review_status_field(text: str, value: str = "ai-draft") -> str:
    """frontmatter 에 review_status(칸반 생애주기) 블록이 없으면 비파괴 삽입한다.

    status(문서 성숙도: draft|review|frozen)와 review_status(칸반 생애주기:
    empty|ai-draft|human-reviewed|frozen)는 별개 필드다. 작업 보드(wo_emit)는
    review_status 를 우선 읽으므로, 이 필드가 빠지면 status 값이 폴백되어 4-레인에
    매핑되지 못한다(카드 미표시). 이 함수는 그 누락만 메운다.

    - frontmatter 없음 → 변경 없음(dossier 는 frontmatter 전제).
    - review_status 이미 존재 → 변경 없음(보존 우선, 덮어쓰기 금지 → 멱등).
    - 없음 → status 라인 바로 뒤(없으면 frontmatter 끝)에
      review_status / reviewed_by / reviewed_at 3줄 삽입. 라인 삽입만 하므로
      doc_id·capability 등 dossier 고유 필드를 보존한다.
    """
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return text
    fm_block = match.group(1)
    if REVIEW_STATUS_FIELD_PATTERN.search(fm_block):
        return text
    body = text[match.end() :]
    inject = [f"review_status: {value}", "reviewed_by:", "reviewed_at:"]
    out: list[str] = []
    inserted = False
    for line in fm_block.split("\n"):
        out.append(line)
        if not inserted and re.match(r"^status\s*:", line):
            out.extend(inject)
            inserted = True
    if not inserted:
        out.extend(inject)
    new_fm = "---\n" + "\n".join(out) + "\n---\n"
    return new_fm + body


def ensure_dossier_review_status(hub_root: Path, product: str, dry_run: bool = False) -> int:
    """dossier(type: dossier) draft 에 review_status: ai-draft 블록을 보장한다(비파괴).

    process()/render_frontmatter 의 REQUIRED_FIELDS 재작성 경로(고유 필드 유실 위험)를
    타지 않고 라인 삽입만 수행한다. 이미 review_status 가 있으면 건너뛴다(멱등).
    """
    drafts_dir = hub_root / "PROJECTS" / product / "drafts"
    if not drafts_dir.is_dir():
        sys.stderr.write(f"drafts dir not found: {drafts_dir}\n")
        return 1
    changed = 0
    skipped = 0
    for draft in sorted(drafts_dir.glob("*.draft.md")):
        text = draft.read_text(encoding="utf-8")
        fm_match = FRONTMATTER_PATTERN.match(text)
        if not fm_match:
            skipped += 1
            continue
        type_match = TYPE_FIELD_PATTERN.search(fm_match.group(1))
        if not type_match or type_match.group(1) != "dossier":
            skipped += 1
            continue
        new_text = _ensure_review_status_field(text)
        if new_text == text:
            skipped += 1
            continue
        prefix = "[dry-run]" if dry_run else ""
        if not dry_run:
            draft.write_text(new_text, encoding="utf-8")
        print(f"{prefix}[review_status] {draft.name} → review_status: ai-draft")
        changed += 1
    print(
        f"[ensure_dossier_review_status] 보강 {changed} / 건너뜀 {skipped}"
        + (" (dry-run)" if dry_run else "")
    )
    return 0


def convert_wo_to_draft(hub_root: Path, product: str, dry_run: bool = False) -> int:
    """안 A 마이그레이션: work-orders/{WO_ID}.md → drafts/{WO_ID}.draft.md.

    절차:
        1. work-orders/{WO_ID}.md (index.md/index.json 제외) 수집
        2. drafts/{WO_ID}.draft.md 존재 여부 확인 후 분기:
           - 없음: work-orders 본문 복사 + frontmatter status: empty 부여
           - 있음 + status ∈ {ai-draft, human-reviewed, frozen}: draft 보존(work-orders 무시)
           - 있음 + status: empty 또는 status 없음: draft 본문 유지 + status 를 ai-draft 로 승격
        3. work-orders/{WO_ID}.md → .archive/work-orders/{WO_ID}.md 이동 (롤백 안전)
        4. work-orders/index.md, work-orders/index.json 은 유지 (이동 X)

    멱등성: 같은 명령을 두 번 실행해도 결과 동일 (이미 .archive 로 이동된 파일은 재처리 안 됨).
    """
    import shutil

    project_root = hub_root / "PROJECTS" / product
    wo_dir = project_root / "work-orders"
    drafts_dir = project_root / "drafts"
    archive_dir = project_root / ".archive" / "work-orders"

    if not wo_dir.exists():
        print(f"[convert_wo_to_draft] work-orders/ 없음 — skip ({wo_dir})")
        return 0

    if not dry_run:
        drafts_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)

    converted = 0
    preserved = 0
    skipped = 0

    for wo_file in sorted(wo_dir.glob("*.md")):
        if wo_file.name in ("index.md", "index.json"):
            skipped += 1
            continue  # 유지: 색인 파일은 이동 X
        wo_id = wo_file.stem
        draft_file = drafts_dir / f"{wo_id}.draft.md"

        if not draft_file.exists():
            # 신규 변환: work-orders 본문을 draft 로 복사 + status: empty 부여
            content = wo_file.read_text(encoding="utf-8")
            new_content = _ensure_status_field(content, "empty")
            if dry_run:
                print(f"[dry-run][convert] {wo_file.name} → {draft_file.name} (status: empty)")
            else:
                draft_file.write_text(new_content, encoding="utf-8")
                print(f"[convert] {wo_file.name} → {draft_file.name} (status: empty)")
            converted += 1
        else:
            existing = draft_file.read_text(encoding="utf-8")
            current_status = _read_status_field(existing)
            if current_status in VALID_STATUSES_PROMOTED:
                # 이미 ai-draft 이상 — draft 본문 보존, work-orders 본문 무시
                if dry_run:
                    print(f"[dry-run][preserve] {draft_file.name} (status: {current_status})")
                else:
                    print(f"[preserve] {draft_file.name} (status: {current_status})")
                preserved += 1
            else:
                # status: empty 또는 누락 → ai-draft 로 승격(draft 본문은 유지)
                new_content = _ensure_status_field(existing, "ai-draft")
                if dry_run:
                    print(f"[dry-run][promote] {draft_file.name} → status: ai-draft")
                else:
                    draft_file.write_text(new_content, encoding="utf-8")
                    print(f"[promote] {draft_file.name} → status: ai-draft")
                converted += 1

        # work-orders 본문 파일을 .archive/ 로 이동 (즉시 삭제 X — 롤백 안전)
        archive_target = archive_dir / wo_file.name
        if dry_run:
            print(f"[dry-run][archive] {wo_file} → {archive_target}")
        else:
            shutil.move(str(wo_file), str(archive_target))

    print(
        f"[convert_wo_to_draft] 완료: 변환/승격 {converted} / 보존 {preserved} / "
        f"index-skip {skipped}"
        + (" (dry-run)" if dry_run else "")
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply standard frontmatter to drafts")
    parser.add_argument("--hub-root", required=True, type=Path)
    parser.add_argument("--product", required=True, help="PROJECTS/<product> 디렉토리명")
    parser.add_argument("--check", action="store_true", help="검증만 수행, 파일 변경 없음")
    parser.add_argument(
        "--convert-wo-to-draft",
        action="store_true",
        help=(
            "안 A 마이그레이션: 기존 work-orders/{WO_ID}.md 를 drafts/{WO_ID}.draft.md 로 변환 후 "
            ".archive/work-orders/ 로 이동 (index.md/index.json 은 유지)"
        ),
    )
    parser.add_argument(
        "--ensure-dossier-review-status",
        action="store_true",
        help=(
            "dossier(type: dossier) draft 에 review_status: ai-draft 블록을 비파괴 삽입한다. "
            "작업 보드 칸반 생애주기(empty→ai-draft→human-reviewed→frozen) 누락 보정 — 멱등."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="--convert-wo-to-draft / --ensure-dossier-review-status 와 함께 사용 시 실제 파일 변경 없이 결과만 출력",
    )
    args = parser.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2

    if args.convert_wo_to_draft:
        return convert_wo_to_draft(args.hub_root, args.product, dry_run=args.dry_run)

    if args.ensure_dossier_review_status:
        return ensure_dossier_review_status(args.hub_root, args.product, dry_run=args.dry_run)

    return process(args.hub_root, args.product, args.check)


if __name__ == "__main__":
    sys.exit(main())
