---
name: su
description: >-
  Checks the latest messages from stakeholders in team messenger (chat connector — e.g. Mattermost, Slack) channels. Classifies new requirements, decisions, and questions, and confirms with the PM whether to reflect them in the relevant files. The default lookup range is since the last /su run, or the last 7 days.
triggers:
  - "su"
  - "stakeholder update"
  - "messenger check"
agent: researcher
phase: 4
effort: low
model: haiku
user-invocable: true
---

## Bootstrap Cache Guard (Improvement F — CONTEXT_OPTIMIZATION.md)

On first entry into a session, load `CONTEXT/_session-bootstrap.md` only once.
If this file has already been read in the same session, do not re-read it.
If the cache is missing or stale, refresh it with the following command before proceeding:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/build_bootstrap.py --hub-root .
```

This guard replaces reloading the 6 source files layer-config / about-pm / project-rules /
brand-voice / doc-layer-schema / team-members.
Reading the source files directly is allowed only when essential to this skill's core work.

## Precondition Checks

1. Check whether `CONTEXT/team-members.md` exists.
   If not, report that the team roster file is missing and stop.

2. Check for a chat connector (an MCP tool the user has connected — e.g. Slack, Mattermost)
   using the docs/CONNECTORS.md detection protocol. This skill has a **hard dependency** on the chat connector.
   If absent, print the required-dependency notice from docs/CONNECTORS.md and stop:
   ```
   This step requires a chat connector.
   Connect an MCP server to Claude Code and it will be used automatically:
     claude mcp add <name> ...     (or Claude Settings → Connectors)
   Please run again after connecting.
   ```

3. If the `--since {date}` option is not given, read the timestamp of the last /su run from session-log.md.
   If there is no record of a previous run, default the lookup start point to 7 days ago.

4. Tell the PM the lookup start point:
   ```
   Lookup range: {start date} ~ now ({N} days)
   ```


## Execution Steps

### Step 1 — Collect the channel list

Read the messenger channel info for stakeholders related to `{product}` from `CONTEXT/team-members.md`.

team-members.md format (the channel column name may vary depending on the messenger type — e.g. Mattermost channel):
```markdown
| Name | Team | Role | Messenger channel |
|---|---|---|---|
| {name} | {team} | {role} | {channel name} |
```

If no channel info is found, ask the PM to enter the channel name directly.


### Step 2 — Fetch messages

Fetch messages from each channel using the chat connector confirmed in the precondition checks.
Adapt to vendor-specific parameter differences by reading the tool schema (see docs/CONNECTORS.md).

Fetch conditions:
- Period: {lookup start point} ~ now
- Keyword filter: none (fetch all)
- Exclude bot messages and system messages

Up to 100 messages per channel. If exceeded, use the most recent 100.


### Step 3 — Classify messages

Classify the fetched messages into the following types:

| Type | Definition | Handling priority |
|---|---|---|
| REQ-NEW | New feature request or requirement addition | P1 |
| REQ-CHANGE | Change request for an existing requirement | P1 |
| DECISION | Confirmation or decision on a specific matter | P1 |
| QUESTION | Unanswered question directed at the PM or dev team | P1 |
| STATUS | Progress share or plain update | P3 |
| BLOCKER | Mention of an issue blocking progress | P0 |
| NOISE | Message unrelated to the work | Ignore |

Classification criteria:
- "please add", "we need", "should be" → REQ-NEW
- "change", "modify", "please switch to" → REQ-CHANGE
- "confirmed", "decided", "will proceed" → DECISION
- "?" or "how", "when", "is it possible" → QUESTION
- "blocked", "not possible", "waiting" → BLOCKER


### Step 4 — Output the PM report

Output the classification results in the following format:

```
Messenger lookup result: {product}
Lookup period: {start} ~ {end}
Channels analyzed: {N} / Messages: {N}

-- BLOCKER ({N}) --
[{channel name}] {speaker} ({date}):
  "{message excerpt summary}"
  → Suggested action: register in open-issues as P0

-- REQ-NEW ({N}) --
[{channel name}] {speaker} ({date}):
  "{message excerpt summary}"
  → Suggested action: add to stakeholder/{team name}.md or register in open-issues as P1

-- REQ-CHANGE ({N}) --
...

-- DECISION ({N}) --
[{channel name}] {speaker} ({date}):
  "{message excerpt summary}"
  → Suggested action: add to decisions.md

-- QUESTION ({N}) --
[{channel name}] {speaker} ({date}):
  "{message excerpt summary}"
  → Suggested action: register in open-issues as P1 (response needed)

-- STATUS ({N}) --
{show only a status-update summary}

Types with no results are omitted from the output.
```


### Step 5 — Confirm handling method with the PM

For BLOCKER / REQ-NEW / REQ-CHANGE / DECISION / QUESTION items,
confirm the handling method for each with the PM:

```
Please choose a handling method for the items above:

  For each item, choose one of:
  [A] Apply to file  — reflect immediately in the relevant file
  [B] Register issue — register in open-issues.md for later handling
  [C] Ignore         — do not handle in this session

  Or apply to all:
  [ALL-A] Apply all to file
  [ALL-B] Register all as issues
```


### Step 6 — Reflect in files per PM decision

**REQ-NEW / REQ-CHANGE → when [A] is chosen:**
Add the item to `inputs/discovery/stakeholder/{team name}.md`.
Type: FR, Priority: [unclassified], Source: messenger {channel name} {date}

If stakeholder.md changes as a result, tell the PM to re-run `/draft-req`.

**DECISION → when [A] is chosen:**
Auto-register a candidate row in the `decisions.md` DEC table (schema: [[CONTEXT/dec-schema]]):
```markdown
| DEC-{NNN} | {MM-DD} | {domain} | {content, compressed to 60 chars} | {reversal target or -} | ⬜ | /su {channel name} |
```

- `DEC-{NNN}`: the largest existing ID in the table + 1
- `domain`: auto-estimated from the channel topic (PM can correct)
- `Reversal` column: if the statement reverses an existing DEC, the superseded ID; otherwise `-`
- `Approval` cell = `⬜`. The PM approves via `/dec-approve {DEC-ID}` or by editing the cell directly
- The speaker (`{speaker}`) is often not the PM, so approval is a separate step
- Mark any related open-issues item as done


**BLOCKER / QUESTION → when [A] or [B] is chosen:**
Register in `open-issues.md`:
```markdown
- [ ] [SU-NN] {type}: {content} — source: {channel name} {date} / response needed from: {speaker}
```
Register BLOCKER as P0, QUESTION as P1.


### Step 7 — Record in session-log.md

```markdown
- {date} /su: checked {N} channels / BLOCKER {N} / REQ-NEW {N} / DECISION {N} / QUESTION {N}
```

This record is used as the lookup start point for the next /su run.


## Result File List (conditionally generated per PM's choice)

| File | Condition |
|---|---|
| `inputs/discovery/stakeholder/{team name}.md` | When [A] chosen for REQ-NEW / REQ-CHANGE |
| `decisions.md` | When [A] chosen for DECISION |
| `open-issues.md` | When [A] or [B] chosen for BLOCKER / QUESTION |
| `session-log.md` | Always recorded |


## Next Steps

If REQ-NEW / REQ-CHANGE was applied:
- Re-run `/draft-req {product}` if requirements need to be re-synthesized.

If a BLOCKER P0 was registered:
- Discuss the resolution with the PM immediately.
