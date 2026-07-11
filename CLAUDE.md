# orange-pm Planning Automation — Session Configuration

## Advisor model routing strategy

This system uses the server-side `advisor_20260301` tool to dynamically route models within a session.
**When a new model is released, update only the `model` field in the Advisor config below.**

### Role label definitions

| Label | Model used | Purpose |
|--------|-----------|------|
| `advisor` | claude-opus-4-8 | Complex judgment, cluster discovery, graph design, policy structure analysis |
| `direct`  | claude-sonnet-4-6 (default) | General conversation, command routing, medium-complexity tasks |
| `batch`   | claude-haiku-4-5 | Index building, classification, summarization, repetitive/low-cost processing |

### Advisor tool configuration

When running a `model: advisor` skill, declare the following tool to delegate deep judgment to Opus:

```json
{
  "type": "advisor_20260301",
  "name": "advisor",
  "model": "claude-opus-4-8"
}
```

Beta header: `advisor-tool-2026-03-01`

### Responding to new model releases

1. Replace only the `"model": "claude-opus-4-8"` value above with the new model ID
2. Sync the VS Code setting `orangePmViz.modelAdvisor` (optional)
3. No changes needed to the 36 SKILL.md files, since they only reference labels (`advisor/direct/batch`)

### Per-skill model routing principle

- `effort: high` skills → `model: advisor` — Opus judges, Sonnet executes
- `effort: medium` skills → `model: direct` — Sonnet handles directly
- `effort: low` skills → `model: batch` — Haiku (lightweight, fast)

### Advisor tool usage guidance (for `model: advisor` skills)

Call the advisor tool when complex judgment is required:
- Identifying cluster boundaries and designing dependency graphs
- Detecting policy conflicts and determining Delta scope
- Planning multi-skill pipelines
- Cross-analyzing multiple documents

Simple progress steps (reading files, format conversion, status logging) are handled directly without calling the advisor.
