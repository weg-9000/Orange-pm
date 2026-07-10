# -*- coding: utf-8 -*-
"""Hook scope guard.

Plugin hooks run in EVERY Claude Code session once the plugin is enabled,
regardless of working directory. This guard makes the orange-pm hooks dormant
unless the session's cwd is an actual Planning-Agent-Hub, so the plugin no
longer leaks its prompts into unrelated sessions.

Usage (from hooks.json command):
    python "${CLAUDE_PLUGIN_ROOT}/scripts/_hook_guard.py" <Event> [matcher]

Behavior:
    - reads the hook JSON payload from stdin (contains "cwd")
    - if cwd is not a Planning-Agent-Hub  -> exit 0, no output (dormant)
    - if it is a Hub                      -> emit the matching guidance text

PostToolUse SKIP rule (안 A — status:empty draft):
    When Write/Edit/MultiEdit touches PROJECTS/*/drafts/*.draft.md and the
    resulting file has  status: empty  in frontmatter, the fanout shell is
    not yet filled — running policy_impact_scan is meaningless at this stage.
    Guard returns 0 silently so no scan recommendation is emitted.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(HERE)
PROMPTS_FILE = os.path.join(PLUGIN_ROOT, "hooks", "prompts.json")

# Files that uniquely identify a Planning-Agent-Hub working directory.
HUB_MARKERS = (
    os.path.join("CONTEXT", "layer-config.md"),
    os.path.join("CONTEXT", "_session-bootstrap.md"),
)

_DRAFTS_SEG = "/drafts/"  # normalised path segment for drafts directory


def is_hub(cwd):
    if not cwd or not os.path.isdir(cwd):
        return False
    return any(os.path.isfile(os.path.join(cwd, m)) for m in HUB_MARKERS)


def read_payload():
    """Read JSON payload from stdin; return dict (may be empty)."""
    raw = ""
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    if raw.strip():
        try:
            return json.loads(raw) or {}
        except Exception:
            return {}
    return {}


def _frontmatter_status(file_path):
    """Return the value of the 'status:' frontmatter field, or '' on failure.
    Reads only the first 40 lines to avoid loading large draft bodies."""
    try:
        with open(file_path, encoding="utf-8") as fh:
            in_fm = False
            for i, line in enumerate(fh):
                if i > 40:
                    break
                stripped = line.strip()
                if i == 0:
                    if stripped != "---":
                        return ""
                    in_fm = True
                    continue
                if stripped == "---" and in_fm:
                    break  # end of frontmatter
                if stripped.startswith("status:"):
                    return stripped.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""


def is_empty_draft_write(payload, event, cwd):
    """Return True when the touched file is a status:empty draft shell.

    Condition: PostToolUse event + Write|Edit|MultiEdit tool
               + file path contains /drafts/
               + frontmatter status == empty (file on disk after write).
    """
    if event != "PostToolUse":
        return False
    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Write", "Edit", "MultiEdit"):
        return False
    tool_input = payload.get("tool_input") or {}
    raw_path = tool_input.get("file_path", "").replace("\\", "/")
    if _DRAFTS_SEG not in raw_path:
        return False
    # Resolve to absolute path for disk read
    if os.path.isabs(raw_path):
        abs_path = os.path.normpath(raw_path)
    else:
        abs_path = os.path.normpath(os.path.join(cwd, raw_path))
    return _frontmatter_status(abs_path) == "empty"


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    matcher = sys.argv[2] if len(sys.argv) > 2 else ""
    if not event:
        return 0

    payload = read_payload()
    cwd = payload.get("cwd") or os.getcwd()

    if not is_hub(cwd):
        return 0  # dormant in non-Hub sessions

    # [안 A] PostToolUse skip: status:empty draft = fanout empty shell
    # No policy content yet → policy_impact_scan recommendation is meaningless.
    if is_empty_draft_write(payload, event, cwd):
        return 0

    try:
        with open(PROMPTS_FILE, encoding="utf-8") as fh:
            prompts = json.load(fh)
    except Exception:
        return 0

    key = event + ("::" + matcher if matcher else "")
    text = prompts.get(key) or prompts.get(event)
    if not text:
        return 0

    sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
