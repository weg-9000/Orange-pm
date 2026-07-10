<div align="center">

# Orange-pm

A Claude Code plugin for product-management planning automation.

No vendor lock-in: external integrations (wiki, chat, design, repo, tasks) are auto-detected from whatever MCP servers/connectors *you* have attached. 
With no connectors at all, the entire workflow still runs on local files.

![Claude Code Plugin](https://img.shields.io/badge/Claude_Code-Plugin-5A3FD6)
![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB)
![Platform](https://img.shields.io/badge/Platform-Windows_%7C_macOS_%7C_Linux-444)
![License](https://img.shields.io/badge/License-MIT-green)

</div>
---

## Installation

### 1. Install the plugin

In any Claude Code session:

```
/plugin marketplace add weg-9000/Orange-pm
/plugin install orange-pm@orange-pm
```

That's it — you do **not** need to clone this repository. The plugin ships everything, including the workspace scaffolding.

### 2. Create your workspace (Planning-Agent-Hub)

The plugin operates on a dedicated working directory called the **Planning-Agent-Hub**. Create an empty directory anywhere and open Claude Code in it:

```bash
mkdir my-planning-hub
cd my-planning-hub
claude
```

Then run:

```
/init-hub
```

This scaffolds the entire Hub structure in the current directory:

```
my-planning-hub/
├── CONTEXT/              # PM profile, planning rules, doc-tone, stakeholders
│   ├── layer-config.md   #   PREFIX & document-layer settings
│   ├── connectors.md     #   optional capability → MCP tool mapping
│   └── gates/            #   phase-gate criteria (5 files)
├── PROJECTS/             # all deliverables, one subdirectory per product
├── templates/            # graph schema, work-order format
└── .claude/CLAUDE.md     # session entry rules
```

> ⚠️ **Always run Claude Code from the Hub directory.** All skills and hooks resolve paths relative to the current working directory. Running from anywhere else will fail the environment check.

### 3. Connect external tools — optional

The plugin bundles **no** MCP servers and hardcodes **no** vendors. At runtime, skills detect whichever MCP servers/connectors you have attached and use them by *capability*:

| capability | Used for | Example services |
|---|---|---|
| `wiki` | publish & read documents | Confluence, Notion |
| `chat` | read messages, send notices | Slack, Mattermost |
| `design` | browse design files | Figma |
| `repo` | MRs/PRs & issues | GitLab, GitHub |
| `tasks` | schedules & assignments | Jira, Asana |

Attach connectors the normal Claude Code way (`claude mcp add <name> ...` or *Settings → Connectors*). Authentication lives in each MCP server's own config — the plugin never asks for tokens or environment variables.

If several tools serve the same capability, declare your preference in the Hub's `CONTEXT/connectors.md`. Full protocol (detection order, graceful degradation): [CONNECTORS.md](CONNECTORS.md).

**No connectors? No problem.** Every phase from Discovery through Integrate runs entirely on local files; publish/notify steps simply offer `--local-only` or are skipped with a marker.

---

## Quick Start

```
# Open Claude Code in your Hub directory
# → the SessionStart hook prints current phase & open items automatically

/discover dbaas          # Phase -1: start a new project
/research dbaas          # competitor analysis
/stakeholder dbaas       # collect stakeholder requirements
/product-audit dbaas     # audit your own product
/draft-req dbaas         # synthesize the requirements doc
/lc dbaas                # verify phase gates
/ingest dbaas            # Phase 0: project structure & doc sync
/graph-gen dbaas         # build the dependency graph
/fanout dbaas            # Phase 1: generate Work Orders
/flow dbaas S-001        # Phase 2: screen interaction sequences
/review draft.md         # validate a draft
/critique {URL or file}  # critical review of policy/screen specs
/integrate dbaas         # Phase 3: cross-validation
/confirm dbaas           # Phase 4: freeze v1.0
/cr dbaas                # publish to wiki (wiki connector · --local-only)
/su dbaas                # notify stakeholders (chat connector)
```

---

## Phase Flow

```
Phase -1  Discovery       /discover /research /stakeholder /product-audit /draft-req
    ↓ [discovery-exit-gate]
Phase  0  Ingest & Graph  /ingest /graph-gen
    ↓ [policy-entry-gate]
Phase  1  Fanout          /fanout
    ↓
Phase  2  Draft           /explore /flow /review /critique   (1 Work Order = 1 session)
    ↓
Phase  3  Integrate       /integrate   (max 3 rounds)
    ↓ [integration-exit-gate]
Phase  4  Confirm         /confirm → /cr → /su
```

Run `/lc {product}` before advancing — it validates every gate condition.

---

## Session Management

- **Session start** — the SessionStart hook prints the current phase, open P0 items, the last Work Order, and the next recommended skills.
- **Session end** — `/sc {product}` writes `session-log.md` and `RESUME.md`.
- **Session resume** — on the next launch, the SessionStart hook restores context from `RESUME.md`.

---

## Updating & Versioning

- The SessionStart hook checks for new commits (24 h TTL) and prints a one-line notice when an update is available.
- Update with `/orange-pm:update` or `/plugin marketplace update orange-pm`.
- Releases follow [SemVer](https://semver.org); see [CHANGELOG.md](CHANGELOG.md). Maintainers bump versions with `python scripts/bump_version.py patch|minor|major`.

---

## Requirements

- Claude Code v1.0+
- Python 3.10+ on PATH (hooks & validation scripts)
- An empty directory for the Hub (scaffolded by `/init-hub`)
- *(optional)* MCP servers/connectors for external integrations — see [CONNECTORS.md](CONNECTORS.md)
