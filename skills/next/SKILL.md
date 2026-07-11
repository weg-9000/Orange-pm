---
name: next
description: Gathers in-progress work state (queues·status·DEC·deliverables) and ranks the next action deterministically. Not a linear happy path — it presents blocker resolution (fix), upstream reflow (backward), and forward progress together. This is the work-control entry point that reduces the burden of the PM manually chaining repeated /lc calls. The model reports the routing decision from next_emit.py rather than guessing it.
triggers:
  - "next"
  - "what next"
  - "next action"
  - "what should I do"
  - "control"
  - "what next"
phase: any
effort: low
model: haiku
user-invocable: true
---

## Design principle — deterministic recommendation (not autonomous execution)

This skill is a **deterministic recommender**. `next_emit.py` gathers queue·status·DEC·deliverable
existence and ranks the next action (no model routing/guessing — the same deterministic
philosophy as gates/scanners).
**It never auto-executes an action** — the PM explicitly approves and invokes each move.

Ranking priority:
1. **fix** — resolve blocking gates (drift / policy-impact / mtg / bdd-coverage BLOCK)
2. **fix** — clean up unapproved DEC (⬜) (`/dec-approve`)
3. **backward** — integrate UPSTREAM_GAP → revise upstream (D1/D5) (`/draft-req --upstream-feedback`)
4. **forward** — advance phase·status (graph→fanout→write/flow/write-cluster→review→confirm→render)

> Work is not unidirectional. This skill shows "what's blocked now + what to reflow + what to
> advance" all at once, actively guiding the non-linear loops (draft↔review, policy
> change→re-screen, common↑→re-render, DEC reversal→rewrite).


## Execution steps

### Step 1 — Compute recommendation (deterministic)

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/next_emit.py --hub-root . --product {product} --emit-json
```

Output contract (recognize the summary only — do not re-quote source queues):
```json
{ "kind": "next-actions", "phase": 2, "phaseName": "Draft", "blockers": 2,
  "statusCounts": { "empty": 1, "ai-draft": 0, ... },
  "actions": [ { "rank": 1, "direction": "fix|backward|forward",
                 "severity": "BLOCK|WARN|INFO", "label": "...", "cmd": "/bdd",
                 "arg": "{product}", "reason": "...", "source": "bdd-coverage" } ] }
```

### Step 2 — Report

```
Work control — {product}  (phase {N} {name} · blockers {blockers})

  status: empty {N} · ai-draft {N} · reviewed {N} · frozen {N}

  Next actions:
   [1] 🔧 fix      {cmd} {arg}  — {reason}      (source: {gate/queue})
   [2] ↩ backward  {cmd} {arg}  — {reason}
   [3] →  forward  {cmd} {arg}  — {reason}

  ※ Not auto-executed — specify the action to run.
```

If `blockers = 0`, report "no blocked work — can proceed forward."
The viz work board's left-hand **work control** tab always shows the same recommendation
(one-click execution).


## Relationship to other skills

- `/lc` — **full gate verification·dashboard** (detailed). `/next` is a lightweight entry
  point that **compresses** that result into 1~N next actions. Use `/lc` when deeper gate
  analysis is needed.
- `/intent-router` — **new entry** (free-form input → Track decision). `/next` is the
  **next move** for **in-progress** work. Use intent-router for entry, next for ongoing
  control.
- This skill only decides — the actual work is done by the recommended follow-up skill.


## Result files
None (read-only recommendation — no file generated).


## Next step
The PM selects and executes one of the recommended actions. Re-invoke `/next` after execution
to check the updated next move.
