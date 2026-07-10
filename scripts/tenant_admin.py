#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""테넌트 관리 — 생성/조회/경로 (멀티테넌트 SaaS Phase 4).

모델: **테넌트 = 하나의 hub 디렉토리.**
  - default: 플랫폼 CONTEXT 직접 사용(root ".") — 레거시 호환.
  - 신규: tenants/{id}/ 하위 독립 CONTEXT·PROJECTS(완전 파일 격리).
모든 스크립트가 --hub-root 로 테넌트 루트를 받으므로 코드 변경 없이 격리된다.

생성 절차(create):
  1. tenant-config.yml·_presets.yml 검증(중복 id 금지, 프리셋 존재)
  2. tenants/{id}/CONTEXT ← 플랫폼 CONTEXT 템플릿 복사(.template-cache·_session-bootstrap 제외)
  3. gates/_active-preset.txt 에 프리셋 기록, PROJECTS/ 생성
  4. tenant-config.yml 에 테넌트 등록(주석 보존 — 말미 블록 추가)
  5. (선택) --sample 로 샘플 데이터 적재

사용법:
  python tenant_admin.py create --hub-root <platform> --id acme [--label "Acme"] \
      [--gate-preset standard] [--sample orange]
  python tenant_admin.py list  --hub-root <platform>
  python tenant_admin.py path  --hub-root <platform> --id acme

exit code: 0 성공 / 1 검증 실패 / 2 인자 오류
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

_COPY_IGNORE = shutil.ignore_patterns(".template-cache", "_session-bootstrap.md")
_ACTIVE = re.compile(r"^active_tenant:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)


def _registry_path(hub_root: Path) -> Path:
    return hub_root / "tenant-config.yml"


def parse_registry(hub_root: Path) -> dict:
    """{active_tenant, tenants:[{id, root, gate_preset, label}]} 반환(경량 파서)."""
    p = _registry_path(hub_root)
    if not p.exists():
        return {"active_tenant": "default", "tenants": []}
    text = p.read_text(encoding="utf-8", errors="replace")
    active = _ACTIVE.search(text)
    tenants: list[dict] = []
    cur: dict | None = None
    for line in text.splitlines():
        m = re.match(r"^\s*-\s*id:\s*([A-Za-z0-9_-]+)\s*$", line)
        if m:
            cur = {"id": m.group(1), "root": "", "gate_preset": "", "label": ""}
            tenants.append(cur)
            continue
        if cur is not None:
            for field in ("root", "label", "gate_preset"):
                fm = re.match(rf'^\s+{field}:\s*"?(.+?)"?\s*$', line)
                if fm:
                    cur[field] = fm.group(1)
    return {"active_tenant": active.group(1) if active else "default", "tenants": tenants}


def list_preset_names(hub_root: Path) -> list[str]:
    p = hub_root / "CONTEXT" / "gates" / "_presets.yml"
    if not p.exists():
        return ["standard"]
    names: list[str] = []
    in_presets = False
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if re.match(r"^presets:\s*$", line):
            in_presets = True
            continue
        if in_presets:
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
            if m:
                names.append(m.group(1))
    return names or ["standard"]


def tenant_root(hub_root: Path, tenant_id: str) -> Path | None:
    for t in parse_registry(hub_root)["tenants"]:
        if t["id"] == tenant_id:
            root = t.get("root") or "."
            return hub_root if root == "." else hub_root / root
    return None


def create_tenant(hub_root: Path, tenant_id: str, *, label: str = "",
                  gate_preset: str = "standard") -> dict:
    reg = parse_registry(hub_root)
    if any(t["id"] == tenant_id for t in reg["tenants"]):
        return {"status": "exists", "id": tenant_id}
    presets = list_preset_names(hub_root)
    if gate_preset not in presets:
        return {"status": "bad-preset", "preset": gate_preset, "available": presets}

    dest = hub_root / "tenants" / tenant_id
    if dest.exists():
        return {"status": "dir-exists", "path": str(dest)}
    src_ctx = hub_root / "CONTEXT"
    dest.mkdir(parents=True)
    shutil.copytree(src_ctx, dest / "CONTEXT", ignore=_COPY_IGNORE)
    (dest / "PROJECTS").mkdir(exist_ok=True)
    gates_dir = dest / "CONTEXT" / "gates"
    gates_dir.mkdir(parents=True, exist_ok=True)
    (gates_dir / "_active-preset.txt").write_text(gate_preset + "\n", encoding="utf-8")

    block = (
        f"\n  - id: {tenant_id}\n"
        f"    label: {label or tenant_id}\n"
        f"    root: tenants/{tenant_id}\n"
        f"    gate_preset: {gate_preset}\n"
        f"    # 외부 연동은 테넌트 CONTEXT/connectors.md 의 capability 매핑으로 선언한다.\n"
        f"    # (wiki / chat / design / repo / tasks — 규약: 플러그인 CONNECTORS.md)\n"
    )
    reg_path = _registry_path(hub_root)
    if not reg_path.exists():
        reg_path.write_text("active_tenant: default\n\ntenants:\n", encoding="utf-8")
    with reg_path.open("a", encoding="utf-8") as fh:
        fh.write(block)

    return {"status": "created", "id": tenant_id, "root": f"tenants/{tenant_id}",
            "gate_preset": gate_preset}


def main() -> int:
    ap = argparse.ArgumentParser(description="테넌트 생성/조회/경로")
    ap.add_argument("command", choices=["create", "list", "path"])
    ap.add_argument("--hub-root", required=True, type=Path)
    ap.add_argument("--id", default=None)
    ap.add_argument("--label", default="")
    ap.add_argument("--gate-preset", default="standard")
    ap.add_argument("--sample", default=None, help="생성 후 샘플 적재(load_sample_tenant)")
    args = ap.parse_args()
    if not args.hub_root.is_dir():
        sys.stderr.write(f"hub-root not found: {args.hub_root}\n")
        return 2

    if args.command == "list":
        reg = parse_registry(args.hub_root)
        print(f"active_tenant: {reg['active_tenant']}")
        for t in reg["tenants"]:
            print(f"  - {t['id']} (root={t.get('root') or '.'}, preset={t.get('gate_preset') or '-'})")
        return 0

    if args.command == "path":
        if not args.id:
            sys.stderr.write("--id 필요\n")
            return 2
        r = tenant_root(args.hub_root, args.id)
        if r is None:
            sys.stderr.write(f"unknown tenant: {args.id}\n")
            return 1
        print(str(r))
        return 0

    if not args.id:
        sys.stderr.write("--id 필요\n")
        return 2
    r = create_tenant(args.hub_root, args.id, label=args.label, gate_preset=args.gate_preset)
    if r["status"] != "created":
        sys.stderr.write(f"[tenant_admin] 생성 실패: {r}\n")
        return 1
    print(f"[tenant_admin] created tenant '{r['id']}' → {r['root']} (preset={r['gate_preset']})")
    if args.sample:
        try:
            import load_sample_tenant as lst
            dest = args.hub_root / "tenants" / args.id
            sample_dir = lst._resolve_sample_dir(dest, args.sample, None)
            if sample_dir:
                rr = lst.load_tenant(dest, sample_dir)
                print(f"  샘플 적재: copied={rr['copied_prefixes']} active={rr['active_prefix']}")
            else:
                print(f"  (샘플 '{args.sample}' 미발견 — 수동 적재 필요)")
        except Exception as exc:
            print(f"  샘플 적재 생략({exc})")
    print(f"  다음: --hub-root tenants/{args.id} 로 스킬/스크립트 실행(완전 격리)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
