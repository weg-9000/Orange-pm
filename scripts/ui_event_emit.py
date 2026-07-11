#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui_event_emit — Appends a single hook event line to <hub>/.claude/ui-events.jsonl.

Dedicated to the visual interface (M3 hook channel). A pure append-only side
effect, independent of the existing _hook_guard gate/guard logic (doesn't
affect blocking or exit codes).

Usage (added command in hooks.json, or run manually):
    python ui_event_emit.py --hook PostToolUse --detail "S01.draft.md" [--hub-root .]

Exits 0 even on exception (so this side-channel logging never blocks the
workflow).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

MAX_LINES = 500  # prevents unbounded growth (keeps only the tail)


def build_event(hook: str, detail: str | None, agent: str | None,
                tool: str | None, ts: str | None = None, session: str | None = None) -> dict:
    ev = {"ts": ts or datetime.now(timezone.utc).astimezone().isoformat(), "hook": hook}
    if tool:
        ev["tool"] = tool
    if agent:
        ev["agent"] = agent
    if session:
        ev["session"] = session
    if detail:
        ev["detail"] = detail
    return ev


def session_from_stdin(raw: str) -> str | None:
    """Extract session_id from hook stdin JSON (used to match background jobs). None on failure."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    sid = data.get("session_id") or data.get("sessionId")
    return str(sid) if sid else None


def append_event(hub_root: str, event: dict, max_lines: int = MAX_LINES) -> Path:
    out = Path(hub_root) / ".claude" / "ui-events.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    # Concurrency guard: concurrent hooks (PostToolUse, UserPromptSubmit)
    # racing on the same file with a lock-free read-modify-write can lose
    # events to last-writer-wins. We serialize with a best-effort O_EXCL
    # lock, same as auto_assemble_on_draft_edit.py.
    # If lock acquisition fails, retry briefly then proceed anyway (this
    # side-channel logging must never block the workflow).
    lock_path = out.with_suffix(out.suffix + ".lock")
    fd = None
    for _ in range(5):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            break
        except FileExistsError:
            time.sleep(0.02)
        except OSError:
            break  # if the lock itself fails, proceed without the guard

    try:
        lines = out.read_text(encoding="utf-8").splitlines() if out.exists() else []
        lines.append(json.dumps(event, ensure_ascii=False))
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                lock_path.unlink()
            except OSError:
                pass
    return out


def detail_from_stdin(raw: str, limit: int = 80) -> str | None:
    """Extract a human-friendly detail from hook stdin JSON (UserPromptSubmit=prompt,
    otherwise tool/agent).

    For a slash-command prompt, only the first line (e.g. '/fanout dbaas');
    for a regular prompt, the first `limit` characters. None on parse
    failure (graceful).
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    text = data.get("prompt") or data.get("tool_name") or data.get("message") or ""
    text = str(text).strip().splitlines()[0] if str(text).strip() else ""
    return text[:limit] or None


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="ui-events.jsonl append")
    p.add_argument("--hook", required=True)
    p.add_argument("--detail", default=None)
    p.add_argument("--agent", default=None)
    p.add_argument("--tool", default=None)
    p.add_argument("--hub-root", default=".")
    p.add_argument("--from-stdin", action="store_true",
                   help="extract detail from hook stdin JSON (e.g. UserPromptSubmit)")
    try:
        args = p.parse_args(argv)
        detail = args.detail
        session = None
        if args.from_stdin:
            raw = sys.stdin.read()  # stdin can only be read once (extract detail & session together)
            if not detail:
                detail = detail_from_stdin(raw)
            session = session_from_stdin(raw)
        append_event(args.hub_root, build_event(args.hook, detail, args.agent, args.tool, session=session))
    except Exception as e:  # side-channel logging must never block the workflow
        sys.stderr.write(f"[ui_event_emit] skipped: {e}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
