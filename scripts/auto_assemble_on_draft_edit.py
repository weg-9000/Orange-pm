#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostToolUse hook — automatically runs render_assemble when drafts/*.draft.md is edited.

Design intent:
    render_assemble.py is a deterministic master-inline stage (0 LLM tokens, no
    side effects). Every time /write, /flow, etc. update a draft, this hook
    auto-triggers so that reports/render/{WO_ID}.complete.md always stays
    current, without the PM having to explicitly call /render.

    LLM publication conversion and Confluence push are never auto-run.
    This hook only handles stage 1 (assemble).

Behavior:
    1. Read the PostToolUse payload from stdin.
    2. Dormant if cwd is not Planning-Agent-Hub.
    3. Skip if the file the previous tool modified is not PROJECTS/*/drafts/*.draft.md.
    4. Skip if frontmatter status is empty (fanout shell only, body not yet written).
    5. Extract WO_ID and product from the path.
    6. Silently run render_assemble.py --hub-root . --product {p} --wo {WO_ID}.
    7. Never blocks on failure (does not interrupt the PM's workflow). Errors go to stderr only.

stdout output:
    - success/skip: none (silent)
    - on change: a one-line notice ("[auto-assemble] {WO_ID} updated")

The non-Hub-session dormant pattern matches _hook_guard.py.
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

# wo group = the full draft filename stem (excluding the .draft.md extension). render_assemble.py
# interprets --wo as `drafts/{wo}.draft.md` and also outputs `{stem}.complete.md`
# (render_assemble.py:251,264), so passing the stem as-is stays consistent regardless of naming.
# Matches legacy WO-NN, Track A cluster_{id}, dossier G2-x-NN, etc. (H1 — audited 2026-06-08).
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
    """The draft's status field (empty string if absent)."""
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
    """Extract the draft-edit target from the payload. Returns None if not applicable."""
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
    # resolve absolute path
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

    # skip if status: empty (right after fanout, body not yet written)
    if _frontmatter_status(abs_path) == "empty":
        return 0

    if not ASSEMBLE_SCRIPT.is_file():
        # script not installed — silent fail
        return 0

    # HIGH #7: per-WO lock. When parallel hook calls target the same WO, the second
    # and later calls are skipped (the already-running subprocess reads the latest
    # draft state on exit — idempotent).
    # Timeout can be overridden via env var (for large WOs or many master inlines).
    lock_dir = abs_path.parent.parent / ".auto-assemble-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{wo_id}.lock"

    try:
        # O_EXCL lock — skip immediately if an in-flight call for the same WO exists
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        # stale check: force takeover if older than 5 minutes
        try:
            age = abs_path.stat().st_mtime - lock_path.stat().st_mtime
            if age < 300:
                # a live hook is about to write the result — skip
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
            f"[auto-assemble] TIMEOUT ({timeout_s}s): {wo_id} — complete.md update failed. "
            f"Adjustable via the ORANGE_PM_AUTO_ASSEMBLE_TIMEOUT env var. "
            f"Manual run recommended: python {ASSEMBLE_SCRIPT.name} --hub-root . --product {product} --wo {wo_id}\n"
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
        sys.stdout.write(f"[auto-assemble] {wo_id} → reports/render/{wo_id}.complete.md updated\n")
    elif rc != -1:
        # generic failure: show the PM both the last stderr line and the manual re-run command
        stderr_tail = (stderr_text).strip().splitlines()[-1:] or ["unknown"]
        sys.stderr.write(
            f"[auto-assemble] FAIL {wo_id}: {stderr_tail[0]}\n"
            f"  manual re-run: python orange-pm-plugin/scripts/render_assemble.py "
            f"--hub-root . --product {product} --wo {wo_id}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
