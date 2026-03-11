# Chief Agent Doc Authority Map

Use this file to understand which docs are authoritative, which are doctrine, and which are only reference or history.

## Reading Order

Read in this order before drafting directives or making architecture judgments:

1. `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
2. `docs/DATA_ENGINE_X_ARCHITECTURE.md`
3. `CLAUDE.md`
4. `docs/CHIEF_AGENT_DIRECTIVE.md`
5. `docs/WRITING_EXECUTOR_DIRECTIVES.md`
6. `docs/STRATEGIC_DIRECTIVE.md`
7. `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` when the work touches entity schema or dedicated intelligence tables

## Authority Buckets

### Production-Truth Reports

These are the authoritative baseline for what is live, healthy, broken, or verified:

- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
- `docs/DATA_ENGINE_X_ARCHITECTURE.md`
- `CLAUDE.md`

If another doc conflicts with these, these win.

### Normative Design / Doctrine

These describe rules, principles, and intended design direction. They are not by themselves proof that production matches the doctrine:

- `docs/STRATEGIC_DIRECTIVE.md`
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`

### Chief Agent Onboarding / Workflow

These define the Chief Agent role, reading order, and directive-writing process:

- `docs/CHIEF_AGENT_DIRECTIVE.md`
- `docs/WRITING_EXECUTOR_DIRECTIVES.md`
- this file: `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md`

### Technical Reference

Useful for broad codebase lookup, concepts, or older implementation context, but not for live-truth claims:

- `docs/SYSTEM_OVERVIEW.md`

### Historical / Lower-Authority Context

These are intentionally retained for historical reasoning, prior handoff context, or older architecture thinking. They should not be used as current production truth:

- `docs/ARCHITECTURE.md`
- `docs/AGENT_HANDOFF.md`
- `docs/COMPREHENSION.md`

They remain useful because they preserve earlier mental models, design assumptions, and implementation-era context that may still explain why parts of the repo look the way they do.

## Directive Files

`docs/EXECUTOR_DIRECTIVE_*.md` files are:

- task scopes for executor agents
- format/style calibration artifacts for future directives
- evidence of what work was planned or requested

They are not:

- proof the work was executed
- proof it was deployed
- proof it is healthy in production
- proof the described target architecture is now live

Treat directive files as intent and scope documents unless the production-truth reports independently confirm the outcome.

## Current Workstream Picture

A new Chief Agent should understand that the repo is not only about the early dedicated-workflow migration. Recent directive families materially include:

- dedicated workflow migration and fan-out routing
- schema split and post-split verification work
- production reliability investigation and deploy/runtime failure analysis
- FMCSA ingestion and mapping work across multiple feed families
- newer workflow families such as job-posting-led discovery

Those workstreams are visible in repo docs and directives, but their presence does not prove production completion.

## Files Updated By This Documentation Refresh

This refresh updates the surrounding navigation and onboarding surface directly:

- `CLAUDE.md`
- `docs/CHIEF_AGENT_DIRECTIVE.md`
- `docs/WRITING_EXECUTOR_DIRECTIVES.md`
- `docs/STRATEGIC_DIRECTIVE.md`
- `docs/SYSTEM_OVERVIEW.md`
- `docs/ARCHITECTURE.md`
- `docs/AGENT_HANDOFF.md`
- `docs/COMPREHENSION.md`
