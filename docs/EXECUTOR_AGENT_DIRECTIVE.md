# Executor Agent Directive Template

Use this template when assigning implementation work to an Executor Agent.

---

## Directive Header

- **Initiative Name:** `<short initiative title>`
- **Directive Owner:** Chief Agent
- **Executor Role:** Execute end-to-end implementation within this scope only
- **Repository:** `data-engine-x-api`
- **Primary Context Files:** `CLAUDE.md`, `docs/STRATEGIC_DIRECTIVE.md`, `docs/SYSTEM_OVERVIEW.md`

---

## 1) Mission

Implement `<initiative>` in production quality with tests and documentation updates.

The executor is expected to make strong engineering decisions **within scope**.  
Do not drift outside scope, do not deploy, and do not run irreversible/destructive commands.

---

## 2) Background

`<2-6 bullets of why this work matters and what breaks/costs/risk exists today>`

Example framing:
- Current behavior:
- Desired behavior:
- Why now:
- Success impact:

---

## 3) Scope (In)

`<explicit list of required work>`

Use concrete behavior, not vague intent.  
If sequencing matters, order the items.

---

## 4) Scope (Out)

`<explicit non-goals>`

Typical exclusions:
- No new providers unless explicitly requested
- No unrelated refactors
- No deploy commands
- No schema changes unless explicitly included
- No API contract expansion unless explicitly included

---

## 5) Files to Read First

List only high-signal files with why they matter.

- `<path>` — `<why it must be read>`
- `<path>` — `<why it must be read>`

Optional: include specific code regions by symbol/function name.

---

## 6) Deliverables (Atomic)

Each deliverable must be independently reviewable and testable.

### Deliverable 1 — `<name>`
- Build:
  - `<required change>`
  - `<required change>`
- Acceptance criteria:
  - `<observable outcome>`
  - `<observable outcome>`

### Deliverable 2 — `<name>`
- Build:
  - `<required change>`
- Acceptance criteria:
  - `<observable outcome>`

### Deliverable N — `<name>`
- Build:
  - `<required change>`
- Acceptance criteria:
  - `<observable outcome>`

---

## 7) Technical Constraints

- Preserve existing contracts unless this directive says otherwise.
- Keep behavior backward-compatible unless explicitly changed in scope.
- Favor deterministic logic over heuristics where correctness matters.
- Keep side effects isolated and auditable.
- Maintain tenant/org/company scoping rules.

---

## 8) Data / Contract Requirements

`<required request/response fields, schema rules, skip reasons, metadata shape, etc.>`

If changing canonical contracts, specify exact files in `app/contracts/` and required tests.

---

## 9) Testing Requirements

Required test coverage:
- Unit tests:
  - `<module + cases>`
- Integration/flow tests:
  - `<module + cases>`
- Regression tests:
  - `<specific known edge cases>`

Definition of done for tests:
- New tests pass.
- Existing relevant suite remains green.
- No reduction in coverage on touched logic.

---

## 10) Documentation Requirements

Update docs that become stale due to this change:
- `<doc path>`
- `<doc path>`

If no doc changes are needed, executor must explicitly state why.

---

## 11) Commit Strategy

`<choose one and keep it explicit>`

Option A (preferred for large initiatives):
- One commit per deliverable.
- No squash inside directive execution.

Option B:
- Single cohesive commit if scope is tightly coupled.

Rules:
- No push.
- Clear commit messages focused on intent.

---

## 12) Completion Report Format (Mandatory)

Executor must report back with:
1. What was implemented (by deliverable)
2. Files changed
3. Key behavioral changes
4. Test results (counts + suite names)
5. Risks or follow-ups
6. Any deviations from directive and why

---

## 13) Paste-Ready Directive Skeleton

Copy, fill, and send this block to an Executor Agent:

```md
Phase Directive: <initiative name>

Context:
You are working on `data-engine-x-api`.
Read `CLAUDE.md`, `docs/STRATEGIC_DIRECTIVE.md`, and `docs/SYSTEM_OVERVIEW.md` before coding.

Scope clarification on autonomy:
You are expected to make strong engineering decisions within the scope below.
Do not drift outside scope. Do not deploy. Do not run destructive commands.

Background:
<why this phase exists and why now>

Files to read before starting:
- <path> — <reason>
- <path> — <reason>

Deliverable 1: <name>
- Build:
  - <change>
- Acceptance:
  - <observable result>

Deliverable 2: <name>
- Build:
  - <change>
- Acceptance:
  - <observable result>

Testing requirements:
- Unit: <tests>
- Integration: <tests>
- Regression: <tests>

Out of scope:
- <non-goal>
- <non-goal>

Commit convention:
<one commit per deliverable OR single cohesive commit>. Do not push.

When done, report:
(a) implementation by deliverable
(b) files changed
(c) behavior changes
(d) tests run + results
(e) risks/follow-ups
(f) any deviations
```