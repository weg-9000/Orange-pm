---
tags: [skill, phase-any]
---
# critique
Critically evaluates policy documents and screen design specs in full, and
outputs the result in the format of a planning review meeting log.

## Workflow Connections
- Can run independently (callable from any Phase)
- Next step: [[write]], [[flow]] (re-evaluate after fixing BLOCK/FIX items)
- Related skills: [[review]] (draft self-completeness check), [[explore]] (upfront context gathering)

---

## Differences Between This Skill and /review

| Item | /review | /critique |
|---|---|---|
| Target | `drafts/*.draft.md` WO drafts | Policy documents · screen design specs (wiki URL / local file) |
| Evaluation perspective | Document structure, wording, SSoT compliance | Quality of planning decisions, operability, customer perspective |
| Output format | FAIL/WARN/PASS validation result table | Planning review meeting log (per-agenda-item discussion + action items) |
| Classification scheme | FAIL / WARN / INFO | BLOCK / FIX / HOLD / WARN / BACKLOG |
| Auto-fix | None | None (suggests fix direction only) |

---

## Input Parameters

```
/critique {target}
```

- Example forms of `{target}`:
  - A wiki page URL (e.g. `https://wiki.example.com/spaces/.../pages/123456`)
  - A local file path: `PROJECTS/dns/drafts/policy-WO-003.draft.md`
  - Multiple documents: separate URLs or paths with spaces (max 3)
  - `--context {background}`: supplemental evaluation context (optional)

---

## Precondition Checks

1. If the target is a wiki page URL, detect the wiki connector (an MCP
   tool the user has connected — e.g. Confluence, Notion) using the
   CONNECTORS.md detection protocol, and fetch the document as Markdown
   using the get operation.
   - If the wiki connector is absent: instruct the user to connect an MCP
     connector and stop (suggest a local file as an alternative input).
   - If the page lookup fails: print an error message and stop.

2. If the target is a local file, load it with the `Read` tool.
   - If the file does not exist: ask the PM to re-check the path.

3. After loading the target document, optionally load the following
   additional context (only if present):
   - `CONTEXT/layer-config.md` → to confirm the PREFIX
   - `CONTEXT/reference-docs/{ACTIVE_PREFIX}/B/` → common policy (comparison baseline)
   - `CONTEXT/reference-docs/{ACTIVE_PREFIX}/A/G2-A Terminology Rules.md` → official terminology list
   - `PROJECTS/{product}/decisions.md` → confirmed decisions

4. Automatically determine the target document type:
   - Policy document (policy): centered on policy, rules, and branching logic
   - Screen design spec (screen): centered on interaction, microcopy, and state
   - Mixed (mixed): includes both

---

## Running the Evaluation

### Step 1 — Initial document scan (structure, prerequisites)

While reading the target document, check the following:
- Document title, purpose, author, version
- Section structure and any missing sections
- Presence of a terminology definition section
- Whether a flowchart/User Journey is included
- Number of remaining TBD / unverified / "needs confirmation" items

### Step 2 — Full review across all 9 evaluation axes

Evaluate each axis independently and classify the findings.

> **Slimming-down HOLD (revamp v0.5 §7-3 / agenda 5)**: even though some
> mechanical checks (formula↔input 1:1, canonical terminology, unit
> boundaries, C-PIN drift) have been moved upstream to `/review`,
> `/integrate`, and `drift_scan`, **all 9 axes of this critique are
> retained**. Upstream validation relies on heuristics (LLM judgment,
> regex) and therefore has an error rate, so critique serves as the final
> judgment safety net. Reducing the number of axes will only be
> reconsidered by PM decision after the reliability of review's new checks
> has been empirically measured over N runs (currently on hold).

---

#### AXIS-01. Prerequisite Completeness (Prerequisites)

**Evaluation questions:**
- Is the terminology definition section at the very top of the document?
- Was a flowchart/User Journey created before the planning document was
  written?
- Were the case classification criteria established before the document
  was started?
- **(C-ATTEST) Is planner review attribution stated in the header? Was the
  AI output reviewed and signed off by a human rather than used as-is
  (review_status/reviewed_by/at, per-section review)? (MTG-05/06
  principle)**
- **(C-MTG) Is the meeting delegation decision traced? Is SCREEN-DELEGATED
  from the mtg-ledger (PM master copy) reflected in the corresponding
  screen's meeting_decisions, and is the MTG-NN claimed by the screen
  registered in the ledger? (mtg-queue BLOCK/FAIL = 0)**

**BLOCK criteria:**
- Core states/concepts are described with multiple mixed terms in the
  document, with no terminology definition
- Branching logic is described without a flowchart → high risk of missing
  cases

**FIX criteria:**
- A terminology definition exists, but the document actually uses
  different wording than declared
- A case classification table exists, but there is no coverage check
  system

**Checklist:**
```
□ A terminology definition section exists at the top of the document
□ Declared terms are used consistently throughout the rest of the document
□ Resource/target type branching criteria are explicitly stated
□ A flowchart or state-transition diagram was created beforehand
□ The document was not written while still in "in progress / unverified" state
□ (C-ATTEST) review_status: human-reviewed + reviewed_by/at and per-section review stated
□ (C-MTG) Meeting delegation (SCREEN-DELEGATED) reflected/pinned on the screen, mtg-queue BLOCK/FAIL = 0
□ No leftover deprecated policy (deprecated strings) — per deprecated.yml
```

---

#### AXIS-02. Terminology and Wording Consistency (Terminology)

**Evaluation questions:**
- Is the wording used for the same concept consistent throughout the
  document?
- Is there any wording that could mislead the customer?
- Are internal technical terms not used as-is in customer-facing copy?

**BLOCK criteria:**
- An action's wording within the service could be confused with the
  customer's general understanding (purchase, expiry, permanent deletion,
  etc.) and is used without correction
- The same action wording ("delete", "disconnect", etc.) actually refers
  to different processing but is used interchangeably without distinction

**FIX criteria:**
- UI copy such as "Connect"/"Change" is inconsistent across screens
- The state name in the policy document does not match the UI label in
  the screen design spec
- Internal technical phrasing such as "structurally not possible" is
  exposed in UI/policy copy
- Missing subject makes it ambiguous whether copy is a condition notice or
  a restriction notice

**WARN criteria:**
- Mixed writing style (noun-form/verb-form mixed)
- Abbreviation/localized/English notation for the same service or concept
  mixed across screens

**Checklist:**
```
□ The document uses a single unified expression for the same concept
□ No customer-misleading wording (purchase, delete, register, etc.)
□ Button labels/guidance copy/policy terms agree across all three
□ Internal technical terms are not included in customer-facing copy
□ Completion message, button label, and guidance copy use the same wording
  in the same context
```

---

#### AXIS-03. Policy Completeness (Policy Coverage)

**Evaluation questions:**
- Are all cases (branches) covered without omission?
- Is the edge-case handling policy stated?
- Is handling fully branched by resource type and by state?

**BLOCK criteria:**
- Case branching criteria exist, but the handling policy for some cases is
  not stated
- When the customer has deleted all items, the zero-count state handling
  policy is missing
- The host/resource count limit policy is completely missing

**FIX criteria:**
- An auto-expiry/auto-processing policy exists, but the handling outcome
  is not branched by resource type
- Per-case guidance copy for delete/disconnect is not written
- A state-transition trigger exists, but exception cases (rollback on
  failure) are not defined
- The impact scope on related services/resources is not described

**HOLD criteria:**
- A policy whose technical feasibility has not been confirmed is stated as
  a finalized value
- An item requiring business-unit confirmation remains unconfirmed

**Checklist:**
```
□ A case classification table exists and every case has a handling policy
□ Failure/cancellation/timeout cases are stated, not just the happy path
□ Handling is fully branched by resource type (each type has a handling
  policy)
□ A resource count limit policy exists
□ Edge cases (zero-count state, duplicate requests, concurrent processing,
  etc.) are stated
□ The impact scope on related services is described
```

---

#### AXIS-04. Document Consistency (Document Consistency) — including alignment with common (G2-A/B)

**Evaluation questions:**
- Is the same policy described differently between the policy document and
  the screen design spec?
- Is policy content correctly placed in the policy document, and screen
  description correctly placed in the screen design spec?
- Is pattern consistency maintained with other services/screens?
- **(C0) Does the product's G2-C avoid rewriting or deviating from
  policy/terminology already present in the common G2-B/G2-A, describing
  only Delta+`[[link]]`?**
- **(C-PIN) Does the draft frontmatter's `referenced_master` pin exist, and
  is the drift-queue not stale (BLOCK)? Does an opt-out (empty pin) have a
  decisions.md justification?**

**BLOCK criteria:**
- A policy not present in the policy document is described only in the
  screen design spec
- The state definition in the policy document does not match the state
  display in the screen design spec
- **The product policy document rewrites, without a common link, a policy
  already defined in G2-B (fee formula handling principles, discount
  application order, resource limits, notifications, etc.) on its own
  (SSoT bypass) — the common opt-out anti-pattern as in cloud-calc DEC-001**
- A BLOCK (common major drift) exists for this document in
  `reports/drift-queue.md`

**FIX criteria:**
- The same policy is described with different wording in the two documents
- The same pattern as another service (load balancer, WAF, etc.) but a
  different UI is used
- Guidance copy exists on one screen but not on another screen with the
  same context
- The `referenced_master` pin is missing, or the pin ID is not registered
  in `master-id-map.yml` (drift-queue UNRESOLVED)
- An input variable is duplicated in the policy document/screen spec
  instead of only in `spec-catalog.md`

**WARN criteria:**
- Identical content is copy-pasted repeatedly instead of using a common
  policy link reference
- A common policy such as name validation rules is described
  independently in an individual document
- `referenced_master` is an empty list (opt-out) but no decisions.md
  justification is recorded
- The complete version's (`*.complete.md`) `rendered_from_master` does not
  match the source pin (re-render needed)

**Checklist:**
```
□ State names, button labels, and guidance copy match between the policy
  document and the screen design spec
□ Policy content is placed in the policy document, UI description in the
  screen design spec
□ Consistency is maintained with the same pattern in existing other
  services
□ Common policy uses a link reference, no duplicate description
□ Back-office policy is also consistent with console policy
□ (C0) The product does not rewrite or deviate from policy already in
  G2-B/A (Delta+link only)
□ (C-PIN) referenced_master pin exists + drift-queue BLOCK = 0 + opt-out
  justification
□ Input variables are the spec-catalog SSoT; formulas derive from G2-B §B
  (no duplicate definitions)
```

---

#### AXIS-05. User-Centric Design (User-Centric Design)

**Evaluation questions:**
- Is the full flow (User Journey) of the customer's normal end-to-end
  usage designed?
- Does the created/completed state match the actual usable state?
- Is there a mechanism that guides the user to the next step?

**BLOCK criteria:**
- A status display (e.g. "Complete", "Running") actually reflects an
  incomplete state that requires further setup → the customer may mistake
  it for complete and neglect it, causing a surge in CS inquiries
- Only a feature list is enumerated, with no customer usage flow

**FIX criteria:**
- No mechanism (guidance message, link) to guide the next step after
  creation
- Benchmarking is a mere copy with no improvement points derived
- No guidance for points where the customer gets stuck (further setup
  needed, incomplete authentication, etc.)
- Exposure of information with security concerns (another user's owned
  resource list, personal information, etc.)

**WARN criteria:**
- The list page has status information but no guidance to help interpret
  it
- The delete modal has only a long warning message with no list of
  affected resources
- The error message does not explain the cause and how to resolve it

**Checklist:**
```
□ The full flow from the customer's first access to goal achievement is
  described
□ Creation-complete = actually-usable state are the same (explicit
  guidance if they differ)
□ A next-step guidance message/link exists
□ No dark patterns (customer-unfavorable auto-renewal, cancellation made
  difficult, etc.)
□ No exposure of security-sensitive information (full lists, other users'
  information, etc.)
□ Affected resources and the outcome are stated in the delete modal
```

---

#### AXIS-06. Technical Feasibility (Technical Feasibility)

**Evaluation questions:**
- Are items unconfirmed by the dev team not stated as finalized values?
- Do the figures stated in policy (interval, threshold, etc.) have a
  technical basis?
- Is the impact on related APIs/services analyzed?

**BLOCK criteria:**
- A policy whose technical feasibility has not been confirmed is stated as
  a finalized item
- Figures such as a 30-day cycle or 5-minute interval have an unclear
  basis and have not been reviewed by the dev team

**FIX criteria:**
- No impact analysis on related services/resources
- No handling policy for the intermediate state during resource
  replacement (existing disconnect → before new connect)
- Internal identifiers/codes requiring dev team consultation are not
  defined

**HOLD criteria:**
- There is an item that can only be finalized after waiting for a
  technical review result
- An item requiring dev team confirmation remains unconfirmed

**Checklist:**
```
□ Items marked "needs dev team confirmation" are actually confirmed and
  reflected in policy
□ Automation cycles/thresholds have a technical basis
□ The intermediate (mid-processing) state policy is stated
□ The impact of related service API changes is analyzed
□ Internal identifiers/codes requiring dev team consultation are stated
```

---

#### AXIS-07. Operations, Billing & Notification Policy (Operations & Billing)

**Evaluation questions:**
- Are the billing unit, calculation method, and branching all stated?
- Is the notification (EMS/SMS/email) policy defined down to the send
  timing, recipient, and content?
- Do "needs confirmation" items avoid conflating format with the amount?

**BLOCK criteria:**
- The service incurs billing, but the billing handling policy is not
  documented at all
- The EMS template has not been started + no follow-up setup guidance →
  the customer neglects the service

**FIX criteria:**
- An item marked "needs confirmation" doesn't even have its format
  (calculation method) written → if only the price is unconfirmed, the
  format can be written immediately
- Auto-expiry handling exists, but there is no customer pre-notification
  policy
- The billing start/end criteria and pro-rata calculation method are not
  defined
- The calculation method for mid-cycle sign-up/cancellation is not defined
- Whether a penalty policy exists is not stated

**WARN criteria:**
- The email send timing is ambiguous (real-time vs. batch, send condition
  unclear)
- Whether SMS is sent is left undecided

**Checklist:**
```
□ The billing unit (hour/day/month/year) is stated
□ The billing calculation method is described (including mid-cycle
  sign-up/cancellation)
□ The notification send event, timing, channel, recipient, and content
  are all defined
□ A policy exists to notify the customer if further setup is needed after
  creation
□ Whether D-N day advance notice before auto-expiry is mandatory is stated
□ Manual-operation scenarios the back-office operator must handle are
  described
```

---

#### AXIS-08. Security & Privacy (Security & Privacy)

**Evaluation questions:**
- Is customer information not exposed more than necessary?
- Is the authentication method stated and have security risks been
  reviewed?
- Is there a handling policy for sensitive information (account,
  password, ownership list, etc.)?

**BLOCK criteria:**
- The full list of resources owned by another account is exposed without
  authentication
- The account ID is displayed on-screen without masking

**FIX criteria:**
- Lookup results could include another person's information, but there is
  no masking policy
- Designed without confirming whether sensitive information
  (account/password) can be sent by email

**WARN criteria:**
- An item requiring prior security team confirmation is proceeding
  unconfirmed

**Checklist:**
```
□ The possibility of exposing another person's information is reviewed
  and masked
□ Items requiring prior security team confirmation are confirmed
□ The transmission method for sensitive information (password, account
  key, etc.) is defined
□ The authentication method (ownership verification, delegation
  verification, etc.) is stated
□ The principle of minimizing public exposure scope is followed
```

---

#### AXIS-09. State & Action Definition Completeness (State & Action Matrix)

**Evaluation questions:**
- Are the allowed actions fully defined for every state?
- Are the recovery cases from failure/error states broken down in enough
  detail?
- Does the state display match the actual behavior?

**BLOCK criteria:**
- Some states are missing from the per-state allowed-action table
- The post-failure recovery case is oversimplified into a single row
  (needs to be broken down by success/error and by related-resource
  connection status)

**FIX criteria:**
- A state-transition trigger exists, but the reverse-transition (rollback)
  scenario is not defined
- The console-displayed state name does not match the internal state name
  (code)
- No distinction between customer-visible/hidden event log entries
- An event log source that should be recorded as "API" is instead labeled
  "Console"

**WARN criteria:**
- Whether an event log entry is recorded on state transition is unclear
- The per-state email content is described with the same template (they
  should actually differ)

**Checklist:**
```
□ The full state list and the per-state allowed-action matrix are
  complete
□ Failure-recovery cases are broken down (success/error × related-resource
  connection status)
□ The displayed state name (console) matches the internal state name, or
  the mapping is stated
□ Event log customer-visible/hidden distinction exists
□ Event log source (console/API/automatic) is stated accurately
□ State-transition email content is written distinctly per state
```

---

### Step 3 — Synthesize and classify feedback

Classify the items found on each axis using the criteria below.

| Grade | Definition | Immediate action |
|---|---|---|
| **BLOCK** | Severe enough to cause customer confusion, malfunction, or a surge in CS inquiries at launch. Redesign required. | Must be fixed before the next review |
| **FIX** | Policy omission, unhandled case, or document error. Fix before the next review. | Fix before the next review |
| **HOLD** | Convert to FIX or BACKLOG after technical/business-unit confirmation. | A confirmation deadline must be set |
| **WARN** | A quality-degrading element. Fix is recommended but may proceed at PM's discretion. | Register as an open issue |
| **BACKLOG** | Future enhancement. Excluded from v1 and registered in the v2 plan. | Register in backlog |

---

### Step 4 — Output the result

Output the result in the format of a planning review meeting log, as
shown below.

---

```markdown
# Planning Review — {target document title}

| Item | Content |
|---|---|
| Reviewed target | {document URL or path} |
| Review date | {date} |
| Document type | {policy / screen design / mixed} |

---

## Overall Verdict

> **{BLOCK: N / FIX: N / HOLD: N / WARN: N / BACKLOG: N}**
>
> {one-line overall assessment — a direct evaluation at the level of "there
> is a critical gap in policy completeness and a redesign is needed before
> launch"}

---

## Discussion by Agenda Item

### Agenda 1. [AXIS-{number}] {evaluation axis name}: {issue title}
**Grade**: {BLOCK / FIX / HOLD / WARN / BACKLOG}

- **Discussion summary**:
  {Describe the found problem concretely. State which wording/content is
  problematic and how, and the risk that could actually occur.
  Write with concrete evidence ("§3 uses '{expression A}' and §5 uses
  '{expression B}'"), not an abstract remark ("the terminology is
  inconsistent").}

- **Decision**:
  {State the concrete fix direction. Write it as "fix by doing X", not
  "needs review".}

- **Open/pending items**:
  {State only if technical/business-unit confirmation is needed. Otherwise
  "none"}

[Repeat agenda item — for every finding]

---

## Action Items

| No. | Content | Grade | Owner |
|---|---|---|---|
| 1 | {concrete fix content} | BLOCK | {owner} |
| 2 | {concrete fix content} | FIX | {owner} |
| ... | | | |

---

## Pending Confirmations

| No. | What needs confirmation | Confirm with | Suggested deadline |
|---|---|---|---|
| 1 | {content requiring confirmation} | Dev team / Business unit / Security team | {deadline} |

---

## Backlog Items

| No. | Content | Recommended timing |
|---|---|---|
| 1 | {future enhancement content} | v2 / post-MVP | 

---

## Next Steps

- After fixing BLOCK items: re-run `/critique {target}`
- After fixing FIX items: schedule the next planning review
- HOLD items: reflect in the planning document after confirmation, then
  re-run `/critique`
```

---

### Step 4-5 — Auto-register DEC candidates (see [[CONTEXT/dec-schema]])

Automatically register the review meeting log's BLOCK/FIX/HOLD decisions
as candidate rows in the `decisions.md` DEC table.

**Registration targets:**

| Grade | DEC registration | Reason |
|---|---|---|
| BLOCK | ✅ Registered | A master planning-document change is needed → DEC required |
| FIX | ✅ Registered | The fix direction is a planning decision → DEC required |
| HOLD | ✅ Registered (approval = 🟡 on-hold) | Awaiting PM confirmation — registered in on-hold state |
| WARN | ❌ Not registered | Warning only — open-issues is sufficient |
| BACKLOG | ❌ Not registered | Backlog registration only |

**Registration format:**

```markdown
| DEC-{NNN} | {MM-DD} | {estimated domain} | {decision, compressed to 60 chars} | {reversal target or -} | ⬜ | /critique {round/axis} |
```

- For HOLD grade, register the `approval` column as `🟡 on-hold` (not ⬜)
- After registration, report the list of unapproved DECs to the PM and
  direct them to `/dec-approve`
- This step updates the decisions.md table directly, **separately** from
  the meeting-log markdown output

---

### Step 5 — Evaluation Principles (strictly enforced)

When critiquing, the following principles must be followed.

**1. Principle of specificity**
- "The terminology is inconsistent" → "§3 mixes '{expression A}' and §5
  uses '{expression B}'. Unify to one of the two expressions and register
  it in the terminology definition section."
- "The flow is insufficient" → "After creating {resource}, it does not
  actually work without {follow-up setup}, but the completion screen has
  no guidance to the next step. The customer is likely to mistake it for
  complete and neglect it."

**2. Principle of explicit risk**
- Always state why it is a problem and what outcome it could lead to.
- State concrete risks such as "possible surge in CS inquiries", "negative
  margin", "security risk".

**3. Principle of proposing a fix direction**
- Do not end with "needs review".
- Clearly instruct with "fix to X", "add X", "remove X".
- Directly propose an example of the fixed wording.

**4. Principle of clarifying priority**
- Every item must be assigned a grade (BLOCK/FIX/HOLD/WARN/BACKLOG).
- If any BLOCK item exists, state it in the first line of the overall
  assessment.

**5. Principle of benchmarking comparison**
- Compare against other companies (AWS, NHN, NCP, etc.) or other services
  (load balancer, WAF, etc.) to suggest a better direction.
- Use it from the perspective of deriving improvements, not simple
  copying.

---

## Output Files

| File | Content |
|---|---|
| N/A | The result is printed to the conversation. No separate file is created |
| (optional) `reports/critique-{document ID}-{date}.md` | Created when the PM requests it be saved |

---

## Next Steps

Based on the evaluation result:

```
After fixing BLOCK items: /critique {target}
After fixing FIX items:   /critique {target} (or schedule the next planning review)
Policy document fixes:    /write {WO_ID}
Screen design fixes:      /flow {product} {screen_id}
```
