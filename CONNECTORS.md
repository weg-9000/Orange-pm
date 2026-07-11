# External Integration Convention (Connector Convention)

This plugin **does not bundle its own MCP server or vendor-specific integration tools.**
All external system integration is handled entirely by detecting, at runtime, **MCP servers /
Claude connectors that the user has connected in their own environment**. If no integration
is connected, every workflow still works using local files only.

## Capability definitions

Skills and agents request integrations using the capability labels below, not vendor names.

| capability | purpose | example services (user-connected) |
|---|---|---|
| `wiki` | Publish/read documents, structure hierarchies | Confluence, Notion, GitHub Wiki, etc. |
| `chat` | Read team messenger messages, send notifications | Slack, Mattermost, Teams, etc. |
| `design` | Read design files/frames | Figma, Zeplin, etc. |
| `repo` | Read/create code repository MR/PRs and issues | GitLab, GitHub, etc. |
| `tasks` | Read schedules, tasks, assignees | Jira, Asana, groupware, etc. |

## Detection protocol (common to all skills)

When a step requires a capability, the skill follows this order:

1. **Check the mapping** — if the Hub's `CONTEXT/connectors.md` declares a preferred tool
   for that capability, use it first.
2. **Auto-detect** — search the list of MCP tools available in the current session
   (or via ToolSearch) for a tool matching the capability.
   - `wiki`: confluence / notion / wiki / page keywords
   - `chat`: slack / mattermost / message / channel keywords
   - `design`: figma / design / frame keywords
   - `repo`: gitlab / github / merge_request / pull_request / issue keywords
   - `tasks`: jira / task / calendar keywords
3. **Invoke** — call the discovered tool according to its schema. Adapt to
   vendor-specific parameter differences by reading the tool's schema.
4. **Graceful degradation when absent** —
   - **Optional-dependency step**: log `[{capability} not connected — skipping detection]` and proceed locally.
   - **Required-dependency skill** (`/su`, `/cr` remote publish, `/from-url`): print the guidance
     below and either stop or offer a `--local-only` alternative.

```
This step requires a {capability} connector.
Connecting an MCP server to Claude Code will make it available automatically:
  claude mcp add <name> ...     (or Claude Settings → Connectors)
Please re-run after connecting. To proceed local-only, use --local-only.
```

## Hub mapping file — `CONTEXT/connectors.md`

In environments where auto-detection is ambiguous (multiple tools for the same capability),
users can declare explicit mappings in the Hub's `CONTEXT/connectors.md`. `/init-hub` generates a template.

```markdown
# Connector mapping
| capability | tool/server name | notes |
|---|---|---|
| wiki   | (e.g. mcp__confluence__*) | Target publish space: XXX |
| chat   | (e.g. mcp__slack__*)      | Default channel: #product |
| design | (e.g. mcp__figma__*)      | |
| repo   | (e.g. mcp__github__*)     | |
| tasks  |                          | Not used |
```

## Principles

- **Scripts know nothing about the network** — `scripts/*.py` handle local file processing only.
  All external I/O is performed exclusively through model tool calls (separation of auth and global tools).
- **Vendor names are examples only** — SKILL.md bodies must not hardcode call paths that assume a specific vendor.
- **Failures are harmless** — a failed external call never changes the state of local deliverables.
