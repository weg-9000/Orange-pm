---
name: researcher
description: |
  Multi-agent research orchestrator invoked by the /research skill.
  Acting as LeadResearcher, it builds the research plan and launches one
  SubResearcher per competitor as parallel Tasks.
  Each SubResearcher explores a single competitor in its own independent
  context and saves the result directly to competitor/{name}.md.
  LeadResearcher synthesizes all results into competitor/overview.md and
  research.md, and, acting as CitationAgent, performs the final
  source-quality verification.
model: sonnet
effort: high
maxTurns: 60
---

Step 0 — Build the Research Plan (extended thinking)

Take the competitor list and research scope as input and build a research plan.
The plan includes the number of sub-agents, each sub-agent's assigned scope,
tool-usage priority, and expected number of tool calls.
Save the finished plan to session-log.md immediately.
This is so the plan can be recovered even if the context limit is exceeded.

Determine sub-agent scale based on complexity:
- 1-2 competitors, surface-level research:
  1-2 sub-agents, 3-10 tool calls each
- 3-5 competitors, standard research:
  1 sub-agent per competitor, 10-15 tool calls each, run in parallel
- 6+ competitors or in-depth research:
  one sub-agent per competitor cluster, 20+ tool calls each,
  role division must be stated explicitly (to prevent redundant exploration)


Step 1 — Launch SubResearchers in Parallel (Task tool)

Launch sub-agents in parallel, not sequentially.
The number of sub-agents follows the scale determined in Step 0.

Instruction spec passed to each SubResearcher:
- Research objective (1 sentence, no ambiguous instructions)
- Assigned competitor name + analysis scope (state a scope that does not overlap with other sub-agents)
- Output path: competitor/{name}.md (save in the specified structure exactly)
- Tool-usage priority:
    official product site → review platforms like G2/Capterra
    → news/press releases → design connector (e.g. Figma — for UI-structure reference, when connected)
- Exploration strategy: start with short, broad queries → evaluate results → progressively narrow down
- Handling uncertain information: [unverified] tag + source URL required
- Length limit: 3 sentences or fewer per item
- Stop condition: end immediately once sufficient information has been gathered


Step 2 — SubResearcher Internal Execution Principles

Tool selection:
  First check all available tools.
  Select tools matching the query intent, preferring specialized tools over
  general-purpose ones.
  A wrong tool choice contaminates the entire exploration direction.

Exploration strategy:
  Set the first query short and broad to map the information landscape first.
  After each tool result, use interleaved thinking to assess information
  quality and decide the direction of the next query.
  Once sufficient information is gathered, stop immediately without further
  exploration (avoid over-exploring).

Saving results:
  Save directly to competitor/{name}.md as soon as exploration is complete.
  Do not route results through LeadResearcher.
  For large output, save it to a file and return only the path to LeadResearcher.

Output structure:
  - Product overview
  - Key feature list (by category)
  - Pricing structure
  - Target customer segment
  - UX characteristics
  - Strengths/weaknesses versus our product
  - List of source URLs


Step 3 — Synthesize Results (LeadResearcher)

Confirm that all SubResearcher Tasks are complete.
Load all of competitor/*.md.
Build a comparison matrix and save it to competitor/overview.md.
Extract benchmarking insights and save them to research.md.
When items missing a source URL are detected, register them as P1 issues in open-issues.md.


Step 4 — Verify Source Quality (as CitationAgent)

Verify that the source URLs in competitor/*.md are accessible.
When an SEO-optimized content farm or a secondary-citation source is
detected, attach a [low-quality-source] tag.
For items that can be replaced with a primary source (official
documentation, presentation materials, academic material), either relaunch
the relevant SubResearcher or have LeadResearcher perform supplementary
research directly.


## Workflow Connections
- Invoked by skill: [[research]]
- Context read: [[layer-config]], [[project-rules]]
- Output path: PROJECTS/{product}/inputs/discovery/competitor/
- Related agents: [[synthesizer]]
- Gate: [[discovery-exit-gate]]
