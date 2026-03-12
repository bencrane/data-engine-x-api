# Directive: Chief Agent Onboarding Surface Refresh

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** A brand-new Chief Agent should be able to land in this repo, read the key Markdown files in a clear order, and come away with an accurate understanding of: (1) which docs are authoritative for current production truth, (2) which docs are doctrine and intended design, (3) which docs are onboarding/workflow instructions, (4) which docs are lower-authority technical reference, and (5) which docs are historical context only. Right now, that onboarding path is still too easy to misread because some front-door docs and older templates still steer readers toward lower-authority or historical material before they internalize the truth hierarchy.

**Non-negotiable truth boundary:**

These are the current production-truth documents and must remain the authoritative factual baseline:

- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
- `docs/DATA_ENGINE_X_ARCHITECTURE.md`
- `CLAUDE.md`

Your job is to update the surrounding onboarding and reference docs so they clearly point to these, do not contradict them, and do not accidentally elevate lower-authority docs above them.

Do **not** rewrite those two dated audited reports as part of this work. Improve the onboarding surface around them.

**Existing code to read:**

- `/Users/benjamincrane/data-engine-x-api/CLAUDE.md`
- `/Users/benjamincrane/data-engine-x-api/README.md`
- `/Users/benjamincrane/data-engine-x-api/docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md`
- `/Users/benjamincrane/data-engine-x-api/docs/CHIEF_AGENT_DIRECTIVE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/WRITING_EXECUTOR_DIRECTIVES.md`
- `/Users/benjamincrane/data-engine-x-api/docs/EXECUTOR_AGENT_DIRECTIVE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/STRATEGIC_DIRECTIVE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`
- `/Users/benjamincrane/data-engine-x-api/docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
- `/Users/benjamincrane/data-engine-x-api/docs/DATA_ENGINE_X_ARCHITECTURE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/SYSTEM_OVERVIEW.md`
- `/Users/benjamincrane/data-engine-x-api/docs/ARCHITECTURE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/AGENT_HANDOFF.md`
- `/Users/benjamincrane/data-engine-x-api/docs/COMPREHENSION.md`
- `/Users/benjamincrane/data-engine-x-api/docs/EXECUTOR_DIRECTIVE_CHIEF_AGENT_DOCUMENTATION_REFRESH.md`

Read the recent directive refresh file only as a style/scope reference, not as proof that the onboarding surface is already correct.

---

### Deliverable 1: Lock the Chief Agent Reading Path

Update:

- `README.md`
- `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md`
- `docs/CHIEF_AGENT_DIRECTIVE.md`

Goals:

- make the first-click onboarding path for a new Chief Agent unambiguous
- ensure `README.md` points readers to the authority map and the audited truth docs instead of steering them first to historical architecture material
- make the Chief Agent read order consistent across the core onboarding docs
- clearly define the authority buckets:
  - production truth
  - doctrine
  - Chief Agent workflow
  - technical reference
  - historical/lower-authority context

Specific requirements:

- `README.md` must no longer center `docs/ARCHITECTURE.md` as the main architecture entrypoint
- `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md` must remain the clearest concise navigation doc for a new Chief Agent
- `docs/CHIEF_AGENT_DIRECTIVE.md` must make it unmistakable that directive files are intent/scope artifacts, not deployment proof
- the read order must consistently route a new Chief Agent through:
  - the authority map
  - the audited truth docs
  - `CLAUDE.md`
  - Chief Agent workflow/directive-writing docs

Commit standalone.

### Deliverable 2: Refresh Core Directive-Writing Docs

Update:

- `docs/WRITING_EXECUTOR_DIRECTIVES.md`
- `docs/EXECUTOR_AGENT_DIRECTIVE.md`
- `docs/STRATEGIC_DIRECTIVE.md` if needed for clarity/date-scoping

Goals:

- eliminate conflicting or competing directive-writing guidance
- make the current executor-directive template and Chief Agent workflow the clear standard
- prevent `docs/EXECUTOR_AGENT_DIRECTIVE.md` from re-elevating lower-authority docs as if they were the primary source of truth

Specific requirements:

- `docs/WRITING_EXECUTOR_DIRECTIVES.md` must explicitly reinforce that existing `docs/EXECUTOR_DIRECTIVE_*.md` files are scope/style artifacts, not production status documents
- `docs/EXECUTOR_AGENT_DIRECTIVE.md` must be brought into alignment with the current directive template and truth hierarchy
- if `docs/EXECUTOR_AGENT_DIRECTIVE.md` is still worth keeping, it must no longer instruct readers to treat `docs/SYSTEM_OVERVIEW.md` as primary context over the audited truth docs
- if portions of `docs/STRATEGIC_DIRECTIVE.md` still read like live roadmap claims rather than doctrine, reframe or date-scope them without weakening the doctrine itself

Commit standalone.

### Deliverable 3: Demote or Tighten Misleading Secondary Docs

Evaluate and clean up the lower-authority or historical docs that could still mislead a new Chief Agent:

- `docs/SYSTEM_OVERVIEW.md`
- `docs/ARCHITECTURE.md`
- `docs/AGENT_HANDOFF.md`
- `docs/COMPREHENSION.md`

You must choose and apply a consistent strategy:

- keep a doc active as lower-authority reference, but tighten its status banner and scope
- or clearly demote/archive it without deleting useful historical context

Requirements:

- use one coherent demotion strategy rather than ad hoc treatment
- if a file remains in place, its status banner and opening section must make its authority level impossible to miss
- if a file is effectively historical only, make that obvious enough that a new Chief Agent is unlikely to mistake it for current truth
- `docs/SYSTEM_OVERVIEW.md` is still useful and likely remains active, but it must read clearly as broad reference rather than as a production audit
- `docs/ARCHITECTURE.md`, `docs/AGENT_HANDOFF.md`, and `docs/COMPREHENSION.md` should be treated as historical/lower-authority context and labeled accordingly

Commit standalone.

### Deliverable 4: Final Consistency Pass Across the Onboarding Surface

Do a final pass across the refreshed Markdown onboarding surface and ensure:

- no updated doc contradicts:
  - `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
  - `docs/DATA_ENGINE_X_ARCHITECTURE.md`
  - `CLAUDE.md`
- the distinction between truth, doctrine, workflow, reference, and history is easy to understand
- the repo front door (`README.md`) and the executor/chief-agent docs all tell the same story
- the current workstream picture includes more than just the early dedicated-workflow migration and correctly reflects newer workstream families like:
  - schema split and verification
  - FMCSA ingestion and mapping
  - production reliability/runtime investigation
  - newer workflow families such as job-posting-led discovery
- links and file references still work after any doc moves or wording changes

If small final wording or link fixes are needed across touched docs, make them here.

Commit standalone.

---

**What is NOT in scope:** No code changes. No non-Markdown functional changes. No schema changes. No runtime/config/deploy work. Do not rewrite `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` or `docs/DATA_ENGINE_X_ARCHITECTURE.md`. Do not invent new production claims not supported by the audited reports. Do not weaken `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` just because current production reality has not fully caught up with the doctrine.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the exact list of key Markdown files updated, (b) how `README.md` and the core Chief Agent docs now route a new Chief Agent through the correct reading order, (c) what changed in `docs/EXECUTOR_AGENT_DIRECTIVE.md` and `docs/WRITING_EXECUTOR_DIRECTIVES.md`, (d) which lower-authority docs were tightened versus demoted, (e) how you clarified the difference between production truth, doctrine, reference, and history, (f) any file moves or archive decisions, and (g) anything to flag — especially any doc that is still high-risk for onboarding confusion even after the refresh.
