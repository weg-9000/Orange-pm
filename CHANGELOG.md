# Changelog

All notable changes to this project are recorded here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versioning follows [SemVer](https://semver.org/).

- **MAJOR** — breaking changes: skill removal/rename, `graph.json` schema change, Hub structure change, namespace change
- **MINOR** — feature additions: new skills/agents, new capability, backward-compatible extensions
- **PATCH** — bug fixes, wording/doc fixes, performance improvements

Version bumps are performed with `python scripts/bump_version.py patch|minor|major`
(atomically syncs plugin.json + marketplace.json in 3 places).

## [Unreleased]

## [3.0.0] — 2026-07-11

### Changed
- Full English internationalization — all skills, agents, templates, scripts, and
  data-contract tokens are now English by default (see `VOCABULARY.md` for the
  canonical term list)
- **Breaking**: `graph.json` edge-type enum renamed to English
  (`prerequisite`, `bidirectional-ref`, `duplicate-definition`, `feature-link`,
  `event-definition`, `security-standard`, `implements`, `term-standard`,
  `ux-standard`, `billing-target`, `ops-procedure`). Existing `graph.json` files
  using the old Korean enum values must be migrated.
- **Breaking**: `decisions.md` table header and status-cell wording standardized
  to English (`| ID | Date | Domain | Key Decision | Reversal | Approval | Basis |`,
  `✅ approved` / `❌ rejected` / `🟡 on-hold` / `⬜ pending`)
- Document-type labels used by `/cr`, `/render`, `/sc` standardized to English
  (Policy Definition, Screen Design, Requirements Definition, Meeting Notes,
  Competitor Research)
- Sample `{PREFIX}` values in templates/docs changed from `G2` to a neutral `PX`

## [2.0.0] — 2026-07-10

### Added
- First release as a standalone repo (split out of the gabia-pm-work monorepo)
- `CONNECTORS.md` — capability-based (wiki/chat/design/repo/tasks) MCP connector auto-detection convention
- `/init-hub` — full Planning-Agent-Hub scaffolding (CONTEXT, gates, templates, connectors.md)
- 36 skills / 6 agents — Discovery → Graph → Fanout → Draft → Integrate → Confirm workflow

### Changed
- Removed all hardcoded vendor references (Confluence, GitLab, Mattermost, Figma) → switched to
  auto-detection of user-connected MCP servers/connectors. The entire workflow still runs locally
  without any connector
- Cleaned up environment variable namespace to `ORANGE_*`
