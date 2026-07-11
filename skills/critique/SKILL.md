---
name: critique
description: |
  Performs a fully critical planning review of policy documents and screen
  design specs.
  Takes a wiki page URL or local file as input, analyzes it across 9
  evaluation axes, and outputs BLOCK/FIX/HOLD/WARN/BACKLOG feedback in the
  format of an actual planning review meeting log.
  Unlike the existing /review (draft self-completeness check), this
  evaluates the quality of planning decisions, operability, and the
  customer perspective as well.
  AXIS-04 also validates product G2-C ↔ common G2-B/G2-A consistency
  (C0·C-PIN, the common opt-out anti-pattern).
  All 9 axes are retained (slimming down deferred — this is the final
  judgment safety net for upstream validation).
triggers:
  - "critique"
  - "critical review"
  - "planning review"
  - "planning document evaluation"
  - "policy document evaluation"
  - "screen design evaluation"
  - "review critique"
phase: any
effort: high
model: opus
user-invocable: true
---
