---
name: graph-generator
description: |
  Generates an integrated multi-layer graph combining policy-document section
  nodes (type: policy) and screen-design nodes (type: screen), using
  requirements.md, screen-list.md, and the {PREFIX}-A/B/C documents as input.
  Invoked by the /generate-graph skill.
model: sonnet
effort: high
maxTurns: 40
---
Preload: CONTEXT/layer-config.md, CONTEXT/doc-layer-schema.md

7-step procedure:

Step 1 — Substitute {PREFIX}
Read the PREFIX value from layer-config.md and apply it to every reference
from this point on.
Use this value for all subsequent local file path references and node ID
generation.

Step 2 — Load Upper Layers
Read the {PREFIX}-A and {PREFIX}-B documents from the local
CONTEXT/reference-docs/ directory.
- {PREFIX}-A: all .md files under CONTEXT/reference-docs/A/ (common definitions / terminology standard)
- {PREFIX}-B: all .md files under CONTEXT/reference-docs/B/ (common policy)
Exclude README.md. Exclude files with status: Deprecated from loading.
If the directory or file does not exist → inform the PM that this layer is
absent and continue.
Register the loaded documents as Reference nodes in the graph.

Step 3 — Parse {PREFIX}-C Policy-Document Candidate Nodes
Extract functional units from inputs/requirements.md.
Generate doc_id: {PREFIX}-C-{PRODUCT_CODE}-{SEQ:03d}
node_type: policy
Two categories:
- Product spec: business-rule, data-processing, and integration-policy units
- Requirements definition: policy units based on actors, events, and constraints
Nodes containing only content identical to {PREFIX}-B → delta_required: false

Capability seed injection (P1 — docs/fr-cluster-alignment.md DEC-B):
If inputs/requirements.seeds.yml (FR ID → capability hypothesis map) exists,
read it and fill node.capability (and cluster_hint) from the FR key that
spawned the work node. Sidecar schema:
```yaml
"FR-101":
  capability: "Provisioning"
  cluster_hint: "PR-01"   # optional
  lock: false             # optional, default false
"FR-102":
  capability: "[needs-review]"
```
- The seed is a **hypothesis (seed-not-lock, DEC-B)** — inject it only into
  node.capability (do not lock cluster boundaries).
  The final cluster boundary is determined by cluster_identify (5 axes ·
  threshold), which consumes this as the union-find initial value.
- If the sidecar is absent or the FR key is missing, leave capability empty
  (cluster_identify computes it).

Step 4 — Parse Screen-Design Nodes
Extract each screen item from screen-list.md.
doc_id: SCR-NNN (use the Screen ID from screen-list.md as-is)
node_type: screen
Register the following edges from each item:
- Linked requirement ID → requires edge
- Linked policy ID (when not TBD) → implements edge
- TBD items → register in unresolved-decisions.md, then continue

Step 5 — Analyze Inheritance Relationships
For each policy node:
- Which {PREFIX}-B common policy it inherits from → inherits_from edge
- Which {PREFIX}-C module it includes → includes edge
For each screen node:
- Which policy node it is implemented from → implements edge
- Unresolved implements-edge items → register in unresolved-decisions.md

Step 6 — Infer Inter-Node Dependencies
Infer policy ↔ policy dependencies
Infer screen ↔ screen dependencies (based on screen-transition flow)
Infer bidirectional policy ↔ screen dependencies (detect screens affected by a policy change)
Undecidable items → register in unresolved-decisions.md

Step 7 — Verify Vocabulary Control
Cross-check the status names and error codes in requirements.md +
screen-list.md against {PREFIX}-A.
Unregistered vocabulary → register in unresolved-decisions.md

Outputs:
graph/graph.json              (policy nodes + screen nodes combined)
graph/graph-preview.md        (node/edge summary report)
graph/unresolved-decisions.md
graph/integration-contract.md


## Workflow Connections
- Invoked by skill: [[graph-gen]]
- Context read: [[layer-config]], [[doc-layer-schema]], [[reference-docs-B-README]], inputs/requirements.seeds.yml (capability seeds)
- Output path: PROJECTS/{product}/graph/
- Gate: [[graph-exit-gate]]
