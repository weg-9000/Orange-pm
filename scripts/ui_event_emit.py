#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui_event_emit — hook 이벤트 1줄을 <hub>/.claude/ui-events.jsonl 에 append.

시각 인터페이스(M3 hook 채널) 전용. 순수 append-only 부가효과로, 기존
_hook_guard 의 게이트/가드 로직과 독립이다(차단·종료코드에 영향 주지 않음).

사용법(hooks.json 추가 커맨드 또는 수동):
    python ui_event_emit.py --hook PostToolUse --detail "S01.draft.md" [--hub-root .]

예외가 나도 0 으로 종료한다(부가 로깅이 워크플로우를 막지 않게).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

MAX_LINES = 500  # 무한 증가 방지(테일 보존)


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
    """hook stdin JSON 에서 session_id 추출(백그라운드 잡 매칭용). 실패 시 None."""
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

    # 동시성 가드: 동일 파일에 대한 concurrent hook(PostToolUse·UserPromptSubmit)이
    # lock-free read-modify-write 로 경합하면 last-writer-wins 로 이벤트가 유실된다.
    # auto_assemble_on_draft_edit.py 와 동일하게 O_EXCL best-effort 락으로 직렬화한다.
    # 락 획득 실패 시 짧게 재시도 후 그대로 진행한다(부가 로깅이 절대 막히지 않게).
    lock_path = out.with_suffix(out.suffix + ".lock")
    fd = None
    for _ in range(5):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            break
        except FileExistsError:
            time.sleep(0.02)
        except OSError:
            break  # 락 자체가 실패하면 가드 없이 진행

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
    """hook stdin JSON 에서 사람 친화 detail 추출 (UserPromptSubmit=prompt, 그 외 tool/agent).

    슬래시 커맨드 프롬프트면 첫 줄(예: '/fanout dbaas')만, 일반 프롬프트면 앞 limit 자.
    파싱 실패 시 None (graceful).
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
                   help="hook stdin JSON 에서 detail 추출(UserPromptSubmit 등)")
    try:
        args = p.parse_args(argv)
        detail = args.detail
        session = None
        if args.from_stdin:
            raw = sys.stdin.read()  # stdin 은 1회만 읽는다(detail·session 동시 추출)
            if not detail:
                detail = detail_from_stdin(raw)
            session = session_from_stdin(raw)
        append_event(args.hub_root, build_event(args.hook, detail, args.agent, args.tool, session=session))
    except Exception as e:  # 부가 로깅은 절대 워크플로우를 막지 않는다
        sys.stderr.write(f"[ui_event_emit] skipped: {e}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
