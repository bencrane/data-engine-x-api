# Executor Agent Directive Template

Use this file as a convenience scaffold when assigning implementation work to an Executor Agent.

## Status

- Authority: secondary template reference
- Canonical standard: `docs/WRITING_EXECUTOR_DIRECTIVES.md`
- Use this for: a paste-ready aligned template after the Chief Agent has already grounded in the truth hierarchy
- Do not use this for: deciding production truth, overriding `docs/WRITING_EXECUTOR_DIRECTIVES.md`, or treating older directive files as deployment proof

If this file conflicts with `docs/WRITING_EXECUTOR_DIRECTIVES.md`, that file wins.

## Required Grounding

Before drafting a directive from this template, read in this order:

1. `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md`
2. `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
3. `docs/DATA_ENGINE_X_ARCHITECTURE.md`
4. `CLAUDE.md`
5. `docs/CHIEF_AGENT_DIRECTIVE.md`
6. `docs/WRITING_EXECUTOR_DIRECTIVES.md`

Use `docs/STRATEGIC_DIRECTIVE.md` and `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` for doctrine when relevant.

Use `docs/SYSTEM_OVERVIEW.md` only as secondary technical reference after the audited truth docs are already internalized.

`docs/EXECUTOR_DIRECTIVE_*.md` files are scope and style artifacts. They are not proof that the described work shipped, deployed, or is healthy in production.

## Non-Negotiables

- Use the standard scope clarification on autonomy verbatim.
- Follow the current template shape from `docs/WRITING_EXECUTOR_DIRECTIVES.md`.
- List the exact files the executor must read.
- Be explicit about out-of-scope boundaries.
- Treat one deliverable as one independently reviewable unit.
- Require a completion report.

## Paste-Ready Template

```md
**Directive: [Name]**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** [1-3 sentences on why this work matters]

**Existing code to read:**
- `[absolute-or-repo path]`
- `[absolute-or-repo path]`

---

### Deliverable 1: [Name]
[Exact instructions]
Commit standalone.

### Deliverable 2: [Name]
[Exact instructions]
Commit standalone.

[... more deliverables if needed ...]

---

**What is NOT in scope:** [Explicit exclusions]

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) ..., (b) ..., (c) ..., (d) ..., (e) anything to flag.
```

## Notes For Chief Agents

- If current-state claims matter, tie them to `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`, `docs/DATA_ENGINE_X_ARCHITECTURE.md`, or `CLAUDE.md`.
- If doctrine matters, cite `docs/STRATEGIC_DIRECTIVE.md` or `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` explicitly.
- If you use older directive files for examples, treat them as scope/style calibration only.