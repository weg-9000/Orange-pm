---
name: orange-pm:update
description: Updates the orange-pm plugin to the latest commit via git pull. Pulls directly from the local git repository, so no separate token is required.
triggers:
  - "update"
  - "plugin update"
  - "orange-pm update"
  - "update plugin"
phase: any
effort: low
model: haiku
user-invocable: true
---

## Execution steps

### Step 1 — Check for new commits

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/update_orange_pm.py" --check
```

- **exit 0**: up to date → print "You're on the latest version." and stop
- **exit 2**: new commits available → proceed to Step 2 along with the commit count
- **exit 1**: error → print the error and inform the PM

**Guidance if the source path can't be found:**
```
No 'orange-pm' entry found in ~/.claude/plugins/known_marketplaces.json.
If this is your first install, follow the team installation guide in the README.
```

### Step 2 — Request PM confirmation

If new commits exist, show the current status and ask whether to proceed:

```
orange-pm update available
  New commits: {N}
  Source: {source_dir}

Proceed with the update? [Y/N]
```

If the PM says N, stop.

### Step 3 — Run the update

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/update_orange_pm.py"
```

Show progress in real time:
- "Running git pull..."
- Display the raw git output (list of new/changed files)
- "Syncing plugin cache: N paths"

### Step 4 — Completion notice

```
✓ orange-pm update complete (vX.X.X)

Restart Claude Code to apply the new version.
  Mac: Cmd+Q, then relaunch
  Windows: close the window, then relaunch
```

## Error handling

| Situation | Action |
|---|---|
| No orange-pm entry in `known_marketplaces.json` | Guide the team member through first-time install |
| `.git` not found | Ask them to confirm the source path is a git repository |
| `git pull` conflict | Print the conflict message, guide manual resolution |
| Network error | Guide them to check git credentials/VPN |

## First-time install

Simplest method — install via the GitHub marketplace:

```
/plugin marketplace add weg-9000/Orange-pm
/plugin install orange-pm@orange-pm
```

Method for cloning the git repository directly and using it as a local marketplace (for development/internal mirrors):

```bash
# 1. Clone the repository (to your own fork or mirror URL)
git clone <repository URL> ~/orange-pm

# 2. Add the local marketplace to Claude Code
/plugin marketplace add ~/orange-pm
/plugin install orange-pm@orange-pm
```

After that, updating is as simple as running `/orange-pm:update`.
