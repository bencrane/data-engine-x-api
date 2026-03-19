# Chief Agent Doc Authority Map

**Last updated:** 2026-03-18T23:59:00Z

Use this as the first-click navigation file for Chief Agent onboarding.

## First Read Path

Start with this file, then continue in this order before drafting directives, judging architecture, or treating any repo claim as current fact:

1. `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md`
2. `docs/DATA_ENGINE_X_ARCHITECTURE.md`
3. `CLAUDE.md`
4. `docs/CHIEF_AGENT_DIRECTIVE.md`
5. `docs/WRITING_EXECUTOR_DIRECTIVES.md`
6. `docs/REPO_CONVENTIONS.md`
7. `docs/STRATEGIC_DIRECTIVE.md`
8. `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` when the work touches entity schema or dedicated intelligence tables

That is the canonical Chief Agent reading path. Do not start with older architecture snapshots, handoff notes, or individual executor directives.

## Authority Buckets

### Production Truth

These are the factual baseline for what is live, healthy, broken, or production-verified:

1. `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md`
2. `docs/DATA_ENGINE_X_ARCHITECTURE.md`
3. `CLAUDE.md`

If another doc conflicts with these, these win.

### Doctrine

These define intended design, build rules, and schema principles. They are authoritative about doctrine, not proof that production already matches the doctrine:

- `docs/STRATEGIC_DIRECTIVE.md`
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`

### Chief Agent Workflow

These define the Chief Agent role, reading order, and directive-writing standard:

- `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md`
- `docs/CHIEF_AGENT_DIRECTIVE.md`
- `docs/WRITING_EXECUTOR_DIRECTIVES.md`
- `docs/REPO_CONVENTIONS.md`
- `docs/EXECUTOR_AGENT_DIRECTIVE.md` as a secondary aligned template reference

### Technical Reference

Useful for broad lookup, system orientation, and codebase surface area after you understand the truth hierarchy:

- `docs/AUTH_MODEL.md`
- `docs/API_SURFACE.md`
- `docs/DEPLOY_PROTOCOL.md`
- `docs/SYSTEM_OVERVIEW.md`
- `docs/DATA_ACCESS_AND_AUTH_GUIDE.md` — auth paths, data visibility by auth type, practical access examples; grounded in code; more detailed than AUTH_MODEL.md
- `docs/PERSISTENCE_MODEL.md` — full persistence audit; all write paths, data loss risks, confirmed-write vs auto-persist distinction; read before persistence work
- `docs/ENIGMA_API_REFERENCE.md` — consolidated Enigma API reference from 61 source files; read before any Enigma adapter or operation work
- `docs/GLOBAL_DATA_MODEL_ANALYSIS.md` — analysis of moving from org-scoped to global entity model; decision pending

### Operational

Executor work history and tracking:

- `docs/EXECUTOR_WORK_LOG.md`

### Historical / Lower-Authority Context

Retained to preserve older mental models, handoff context, and prior planning artifacts. Do not use these as current production truth:

- `docs/ARCHITECTURE.md`
- `docs/AGENT_HANDOFF.md`
- `docs/COMPREHENSION.md`

## Directive Files

`docs/EXECUTOR_DIRECTIVE_*.md` files are:

- scope documents for executor work
- acceptance-criteria artifacts
- style and format calibration examples
- evidence of what work was requested or planned

They are not:

- proof the work was executed
- proof it was deployed
- proof it is healthy in production
- proof the target architecture described there is now live

Treat directive files as intent and scope unless the production-truth docs independently confirm the outcome.

## Current Workstream Picture

Do not infer the repo's current picture from only the early dedicated-workflow migration directives.

Recent documentation spans multiple workstream families, including:

- dedicated workflow migration and fan-out routing
- schema split work and post-split verification
- production reliability, runtime, and deploy-sequencing investigations
- FMCSA ingestion and mapping across multiple feed families
- newer workflow families such as job-posting-led discovery
- Enigma API full coverage — 17 operations wired, dedicated workflow, 2 new persistence tables, async brand discovery
- Standalone execute persistence — persist flag, persistence routing registry, response-level error surfacing
- Global data model analysis — documentation-only analysis; hybrid approach (global entities, org-scoped dedicated tables) recommended, deferred pending prerequisites

Those workstreams are present in the docs surface, but their presence does not prove production completion.
