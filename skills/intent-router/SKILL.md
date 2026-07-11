---
name: intent-router
description: |
  Determines Track A / B / C from natural-language intent + URL count + context, and routes to
  the appropriate follow-up skill. Serves as the entry point when the user requests work with
  1–2 URLs plus free-form speech.

  Track model:
    Track A — Full Product (full cluster fanout)
              A brand-new product from scratch + all deliverables (D1–D5+α)
    Track B — Single Deliverable (bypasses clustering)
              1 URL + "write D{N} on this page" → a single deliverable
    Track C — Template Copy (URL_A's format applied to URL_B)
              2 URLs + "write based on this format" → 1–3 deliverables

  Only Track A uses cluster fanout. B/C follow a direct single-deliverable path.

triggers:
  - "at this URL"
  - "on this page"
  - "report in this format"
  - "write from scratch"
  - "new product policy"
  - "write after competitor research"
  - "routing"
  - "what should I do"

phase: any
effort: low
model: haiku
user-invocable: true
---

## 0. Role

This skill is a **decision router**. It does not perform work directly — it parses user intent
and delegates to the appropriate follow-up skill. If ambiguous, it asks the PM a clarifying question.

Follow-up skill categories:
- `from-url` — URL-pull entry (common precursor for Track B/C)
- `extract-template` — extract URL_A's format (Track C only)
- `research-auto` — automated competitor research (Track A/B Phase -1)
- `draft-req` — generate requirements.md (Track A Phase -1)
- `graph-gen` + `fanout` — cluster grouping (Track A only)
- `render` — publish (terminus of every Track)
- `write` / `flow` — author cluster draft bodies (Track A)

## 1. Track decision matrix (SSoT)

User utterance + URL count → Track decision:

| Utterance intent (keywords) | URL count | Decided Track | Deliverable scope |
|---|---|---|---|
| "from scratch", "new product", "all documents", "all deliverables" | 0–1 | **A — Full Product** | D1–D5 + α |
| "competitor research then requirements", "D1/D5 on this URL", "write this page" (a single D explicitly named) | 1 | **B — Single Deliverable** | 1–2 named D's |
| "write URL_B in URL_A's format", "in this format", "same format" | 2 | **C — Template Copy** | 1–3 named D's |
| Only a URL given, intent unclear | 1+ | **Ambiguous → clarifying question** | — |
| No URL + "write everything" | 0 | A — Full Product | D1–D5 + α |
| No URL + "competitor research only" | 0 | B — Single (D5) | D5 |

## 2. Clarifying-question matrix

When ambiguous, delegate the decision to the PM:

| Ambiguous situation | Question |
|---|---|
| 1 URL + intent unclear | "What would you like to do with this URL? (a) write a new deliverable (b) augment the existing page (c) just reference it as a format source (d) use it only as context input" |
| 2 URLs + unclear which is template / target | "Is URL_A ({short_A}) the format and URL_B ({short_B}) the target to write, or are both pages targets to write?" |
| Target deliverable unclear | "Which deliverable should I write? D1 (requirements)/D2 (policy)/D3 (screen)/D4 (meeting notes)/D5 (competitor research)/Dα (API/DB/migration)" |
| Track A but no product name | "Please provide a product name (e.g. dbaas). Work will proceed under PROJECTS/{product name}/." |
| "competitor research then write" — D1 only? D5 only? Both? | "(a) D5 competitor research only (b) D1 requirements too (c) everything (switch to Track A)" |

Ask **at most 1** question at a time. After the response, ask another if a new ambiguity is found.

## 3. Decision output (structured)

Output the routing decision in the following structure (for internal model use + PM confirmation):

```yaml
routing_decision:
  track: A | B | C
  product: dbaas | "..."
  urls:
    - role: target | template | context  # role
      page_id: "12345"                    # extracted from the URL
      short_title: "..."
  deliverables:
    - D1 | D2 | D3 | D4 | D5 | Da_api | Da_db | Da_migration
  upstream_actions:                       # Phase -1 automation
    - research-auto                       # automated competitor research
    - draft-req                           # requirements synthesis
  next_skill: from-url | extract-template | research-auto | draft-req | render
  confirmation_required: true | false      # true for irreversible actions
  notes: "(additional notes)"
```

## 4. Follow-up skill flow per Track

### Track A — Full Product (cluster fanout)
```
1. (if needed) research-auto  → inputs/discovery/competitor/
2. draft-req               → requirements.md (D1) + research.md (D5)
3. graph-gen + fanout       → 12–14 cluster WOs
4. write / flow             → cluster draft bodies
5. integrate                → 3-round BLOCK management
6. render --push            → Phase 4 transpose → D2/D3 + α
```

### Track B — Single Deliverable
```
1. from-url URL --target D{N}  → wiki page pull + meta.json generation
2. (if D5) research-auto  → automated competitor research
3. (if D1) draft-req      → automated requirements extraction
4. write D{N}                  → fill in the format
5. render D{N} --push          → publish (clustering bypassed)
```

### Track C — Template Copy
```
1. from-url URL_A --as-template  → pull the format source
2. extract-template URL_A         → templates/extracted/{id}.template.md
3. from-url URL_B --target D{N} --template-from URL_A
4. write D{N} (using the extracted format)     → fill in the format
5. render D{N} --push             → publish
```

## 5. Entry procedure (model behavior guidance)

On skill entry, perform the following **in order**:

1. **Parse the message**:
   - Extract URLs (a URL matching the wiki page URL pattern — e.g. `pages/(\d+)`)
   - Extract explicit deliverable keywords (D1/D2/D3/D4/D5/Dα)
   - Extract intent keywords (based on the §1 matrix above)

2. **Decide the Track**:
   - Apply the matrix → choose A/B/C
   - If ambiguous, ask 1 question from §2 first and stop

3. **Output the decision**:
   - Generate `routing_decision` in the §3 structure
   - Confirm with the PM (especially when `confirmation_required: true`)

4. **Invoke the follow-up skill**:
   - Delegate to next_skill per the §4 flow table
   - This skill only decides — actual work is done by the follow-up skill

5. **Confirmation gate**:
   - Always confirm with a one-line prompt immediately before an irreversible action (--push,
     --apply-inbox, an actual wiki write)
   - Read-only actions (URL pull, lint, verify) proceed without confirmation

## 6. Coupling with other skills

### Tight coupling (must go through this skill's decision)
- `from-url`: needs the URL's role (target/template/context) decided
- `extract-template`: never triggers outside Track C
- `research-auto`: only when the PM's intent is "automated competitor research"

### Loose coupling (can bypass this skill when the PM calls directly)
- `render` — bypassed when the PM calls `/render --push` directly
- `lint_publication_syntax` — a validation tool, unrelated to this skill
- `verify` — a validation tool, unrelated to this skill

### Cases intent-router does not explicitly route
- When the user uses an explicit flag (`/render --push`, `/write WO-05`) → pass through as-is
- This skill activates **only** on free-form-speech entry without explicit flags

## 7. Usage examples

### Example 1 — Track A routing
```
PM: "Build the entire DBaaS for Berkeley policy document set from scratch"

intent-router:
  routing_decision:
    track: A
    product: dbaas-berkeley
    deliverables: [D1, D2, D3, D4, D5, Da_api, Da_db, Da_migration]
    upstream_actions: [research-auto, draft-req]
    next_skill: research-auto
    confirmation_required: true
    notes: "Full Product — starting from Phase -1. Need to create the new product PROJECTS/dbaas-berkeley/."

  → PM confirmation: "Start writing the entire document set for the new product dbaas-berkeley?
            Expected output: 12–14 clusters + 8 wiki pages."
```

### Example 2 — Track B routing
```
PM: "Do DBaaS competitor research then write the requirements definition doc at
     https://wiki.example.com/pages/12345"

intent-router:
  routing_decision:
    track: B
    product: dbaas
    urls:
      - role: target
        page_id: "12345"
    deliverables: [D1, D5]
    upstream_actions: [research-auto]
    next_skill: from-url
    confirmation_required: false  # pull is read-only
    notes: "Order: D5 competitor research → D1 requirements definition. Bypasses cluster fanout."

  → Follow-up: from-url 12345 --target D1 → research-auto dbaas → write D1
```

### Example 3 — Track C routing
```
PM: "Use the format from https://wiki.../pages/A to write the policy definition doc at
      https://wiki.../pages/B in the same format"

intent-router:
  routing_decision:
    track: C
    urls:
      - role: template
        page_id: "A"
      - role: target
        page_id: "B"
    deliverables: [D2]
    upstream_actions: []
    next_skill: from-url
    confirmation_required: false
    notes: "Extract URL_A's format → write D2 at URL_B."

  → Follow-up: from-url A --as-template → extract-template A → from-url B --target D2 --template-from A
```

### Example 4 — Clarification needed
```
PM: "https://wiki.../pages/X"  (URL only, no intent)

intent-router:
  → Question: "What would you like to do with this URL?
          (a) write a new deliverable   (b) augment the existing page
          (c) just reference it as a format source  (d) use it only as context input"
```

## 8. Cautions

- This skill **only decides** — actual wiki calls / repo writes / pushes are prohibited
- Never guess when ambiguous — ask the PM one clarifying question at a time
- After deciding the Track, delegate **full context** to the follow-up skill (including
  URL/deliverable/upstream_actions)
- If the user's message explicitly states the Track (`Track A` / `Track B` etc.), ignore the
  matrix and follow it as stated
- If intent to violate the direct-wiki-editing prohibition (project-rules.md) is detected, warn
  and refuse to make a decision in this skill

## 9. Workflow connections

- Precedes: none (entry point)
- Follows: from-url / extract-template / research-auto / draft-req / render
- Bypassable: when an explicit flag is used (`/render --push`, `/write WO-05`)

## 10. Change history

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-05-30 | Phase 4 R1 — Track A/B/C routing matrix + clarifying questions + follow-up skill flow |
