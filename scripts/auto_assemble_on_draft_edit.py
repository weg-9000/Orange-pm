#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostToolUse hook — drafts/*.draft.md 편집 시 render_assemble 자동 실행.

설계 의도:
    render_assemble.py 는 결정적 master 인라인 단계 (LLM 토큰 0, 부작용 없음).
    /write, /flow 등으로 draft 가 갱신될 때마다 PM 이 명시적으로 /render 를
    호출하지 않아도 reports/render/{WO_ID}.complete.md 가 항상 최신 상태가
    되도록 자동 트리거한다.

    LLM publication 변환·Confluence push 는 절대 자동 실행하지 않는다.
    이 hook 은 오직 stage 1 (assemble) 만 담당한다.

동작:
    1. stdin 의 PostToolUse 페이로드를 읽는다.
    2. cwd 가 Planning-Agent-Hub 가 아니면 dormant.
    3. 직전 도구가 수정한 파일이 PROJECTS/*/drafts/*.draft.md 가 아니면 skip.
    4. frontmatter status 가 empty 이면 skip (fanout shell 만 채워진 상태).
    5. WO_ID 와 product 를 경로에서 추출.
    6. render_assemble.py --hub-root . --product {p} --wo {WO_ID} 를 silent 실행.
    7. 실패해도 차단하지 않는다 (PM 작업 흐름을 막지 않음). 오류만 stderr.

stdout 출력:
    - 성공·skip: 없음 (silent)
    - 변경 있음: 한 줄 안내 ("[auto-assemble] {WO_ID} updated")

비-Hub 세션 dormant 패턴은 _hook_guard.py 와 동일.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or HERE.parent)
ASSEMBLE_SCRIPT = PLUGIN_ROOT / "scripts" / "render_assemble.py"

HUB_MARKERS = (
    Path("CONTEXT") / "layer-config.md",
    Path("CONTEXT") / "_session-bootstrap.md",
)

# wo 그룹 = draft 파일 stem 전체 (확장자 .draft.md 제외). render_assemble.py 는
# --wo 를 `drafts/{wo}.draft.md` 로 해석하고 출력도 `{stem}.complete.md` 이므로
# (render_assemble.py:251,264), 어떤 명명이든 stem 그대로 넘기면 정합한다.
# legacy WO-NN, Track A cluster_{id}, dossier G2-x-NN 등 모두 매칭 (H1 — 감사 2026-06-08).
DRAFT_PATH_RE = re.compile(
    r"PROJECTS[/\\](?P<product>[^/\\]+)[/\\]drafts[/\\](?P<wo>[^/\\]+)\.draft\.md$"
)


def _is_hub(cwd: Path) -> bool:
    if not cwd.is_dir():
        return False
    return any((cwd / m).is_file() for m in HUB_MARKERS)


def _read_payload() -> dict:
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        return json.loads(raw) or {}
    except Exception:
        return {}


def _frontmatter_status(path: Path) -> str:
    """draft 의 status 필드 (없으면 빈 문자열)."""
    try:
        with path.open(encoding="utf-8") as fh:
            in_fm = False
            for i, line in enumerate(fh):
                if i > 40:
                    break
                s = line.strip()
                if i == 0:
                    if s != "---":
                        return ""
                    in_fm = True
                    continue
                if s == "---" and in_fm:
                    break
                if s.startswith("status:"):
                    return s.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""


def _extract_draft_target(payload: dict, cwd: Path) -> tuple[str, str, Path] | None:
    """페이로드에서 draft 편집 대상을 추출. 해당 안 되면 None."""
    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Write", "Edit", "MultiEdit"):
        return None
    tool_input = payload.get("tool_input") or {}
    file_path = (tool_input.get("file_path") or "").replace("\\", "/")
    if not file_path:
        return None
    m = DRAFT_PATH_RE.search(file_path)
    if not m:
        return None
    product = m.group("product")
    wo_id = m.group("wo")
    # 절대 경로 확보
    if os.path.isabs(file_path):
        abs_path = Path(file_path)
    else:
        abs_path = cwd / file_path
    return product, wo_id, abs_path.resolve()


def main() -> int:
    payload = _read_payload()
    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()

    if not _is_hub(cwd):
        return 0

    target = _extract_draft_target(payload, cwd)
    if not target:
        return 0
    product, wo_id, abs_path = target

    # status: empty 면 skip (fanout 직후, 본문 미작성)
    if _frontmatter_status(abs_path) == "empty":
        return 0

    if not ASSEMBLE_SCRIPT.is_file():
        # 스크립트 미설치 — silent fail
        return 0

    # HIGH #7: per-WO 락. 동일 WO 에 대한 parallel hook 호출 시 두 번째 이후는 skip
    # (이미 진행 중인 subprocess 가 종료될 때 최신 draft 상태를 읽음 — 멱등).
    # 타임아웃은 환경변수로 오버라이드 가능 (대형 WO 또는 master 인라인 다수일 때).
    lock_dir = abs_path.parent.parent / ".auto-assemble-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{wo_id}.lock"

    try:
        # O_EXCL 락 — 동일 WO 의 in-flight 호출이 있으면 즉시 skip
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        # stale 검사: 5분 초과 시 강제 인수
        try:
            age = abs_path.stat().st_mtime - lock_path.stat().st_mtime
            if age < 300:
                # 살아 있는 hook 이 곧 결과를 쓸 것 — skip
                return 0
        except OSError:
            return 0
        try:
            lock_path.unlink()
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except (FileExistsError, OSError):
            return 0

    try:
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
    except OSError:
        try:
            os.close(fd)
        except OSError:
            pass

    timeout_s = int(os.environ.get("ORANGE_PM_AUTO_ASSEMBLE_TIMEOUT", "120"))
    cmd = [
        sys.executable,
        str(ASSEMBLE_SCRIPT),
        "--hub-root", str(cwd),
        "--product", product,
        "--wo", wo_id,
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        rc = result.returncode
        stderr_text = result.stderr or ""
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"[auto-assemble] TIMEOUT ({timeout_s}s): {wo_id} — complete.md 갱신 실패. "
            f"ORANGE_PM_AUTO_ASSEMBLE_TIMEOUT 환경변수로 조정 가능. "
            f"수동 실행 권고: python {ASSEMBLE_SCRIPT.name} --hub-root . --product {product} --wo {wo_id}\n"
        )
        rc = -1
        stderr_text = "timeout"
    except Exception as exc:
        sys.stderr.write(f"[auto-assemble] ERROR: {wo_id} — {exc}\n")
        rc = -1
        stderr_text = str(exc)
    finally:
        try:
            lock_path.unlink()
        except OSError:
            pass

    if rc == 0:
        sys.stdout.write(f"[auto-assemble] {wo_id} → reports/render/{wo_id}.complete.md 갱신됨\n")
    elif rc != -1:
        # 일반 실패: PM 에게 stderr 마지막 줄과 수동 재실행 명령 모두 표시
        stderr_tail = (stderr_text).strip().splitlines()[-1:] or ["unknown"]
        sys.stderr.write(
            f"[auto-assemble] FAIL {wo_id}: {stderr_tail[0]}\n"
            f"  수동 재실행: python orange-pm-plugin/scripts/render_assemble.py "
            f"--hub-root . --product {product} --wo {wo_id}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
