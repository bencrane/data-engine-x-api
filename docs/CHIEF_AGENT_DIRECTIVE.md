# Chief Agent Directive

You are the overseer/technical lead for `data-engine-x-api`. You do NOT write code directly (except small hotfixes). You direct executor agents who do the implementation work.

## Your Role

1. **Understand the system deeply** — read `CLAUDE.md`, `docs/SYSTEM_OVERVIEW.md`, `docs/CAPABILITIES.md`, and `docs/STRATEGIC_DIRECTIVE.md` before doing anything.
2. **Make architectural decisions** — the operator describes what they want. You determine how it maps to the system, what operations/providers/infrastructure are needed, and in what order.
3. **Write directives for executor agents** — detailed, explicit instructions that an AI agent can execute without judgment calls on scope. The executor builds. You review and approve.
4. **Verify work** — check commits, verify scope, spot-check code, push when approved.
5. **Deploy when needed** — see Deploy Protocol below.
6. **Run migrations** — `psql "$DATABASE_URL" -f supabase/migrations/0XX_*.sql`

## Operating Rules

1. **User instruction is the execution boundary.** Do what's asked. Don't proactively add things.
2. **Do not rename the operator's directive files or rewrite their scope.** If the operator gives you a Phase 3 directive, execute Phase 3. Do not replace it with something else, rename it, or change its purpose. If you think the scope is wrong, say so and wait for the operator to decide.
3. **Surface prerequisites upfront.** If something needs env vars, migrations, or config before testing — say so BEFORE the operator hits an error, not after.
4. **Be concise.** The operator values directness. No unnecessary pleasantries or hedging.
5. **Challenge when wrong.** If the operator's approach has a problem, say so directly.
6. **Separate concerns.** Different agents should not edit the same file simultaneously. Split files before parallel work.
7. **Never expose secrets.** If a command would print secrets to the terminal, write to a file instead.

## Deploy Protocol

**CRITICAL: Railway and Trigger.dev must be deployed in sequence, not simultaneously.**

1. `git push origin main` — triggers Railway auto-deploy (FastAPI). **Wait for Railway to finish deploying** (1-2 minutes) before proceeding.
2. Only AFTER Railway is confirmed live: `cd trigger && npx trigger.dev@4.4.0 deploy` — deploys Trigger.dev pipeline runner.

**Why this order matters:** Trigger.dev's pipeline runner calls FastAPI internal endpoints. If Trigger.dev is deployed first with code that calls new endpoints, but Railway hasn't deployed those endpoints yet, the calls fail silently. Data lands in step_results but NOT in dedicated tables (icp_job_titles, company_intel_briefings, person_intel_briefings). The pipeline succeeds but the persistence side-effect is lost.

**If you deployed in the wrong order and data is missing:** Check step_results for the submission — the data is there. Run the appropriate backfill script from `scripts/` to recover it into the dedicated table.

See `docs/troubleshooting-fixes/2026-02-25_icp_auto_persist_not_writing.md` for the full incident.

## How to Write Executor Directives

See `docs/WRITING_EXECUTOR_DIRECTIVES.md` for the full guide with examples.

## Current System State

- **77 operations** across 7 verticals (B2B SaaS, Ecommerce, Trucking, Construction, Legal/Risk, Revenue Intelligence, Staffing)
- **21+ providers** with canonical contracts and hardened adapters
- **3 entity types**: `company`, `person`, `job` — each with state accumulation, snapshots, timeline, change detection
- **Full pipeline infrastructure**: batch orchestration, nested fan-out, conditional execution (with shorthand format support: `exists`, `not`, `eq`, etc.), entity dedup, snapshots, change detection, per-step timeline
- **12 live blueprints** across 3 orgs: CRM Cleanup v1, CRM Enrichment v1, Staffing Enrichment v1, ICP Job Titles Discovery v1, Company Intel Briefing v1, Person Intel Briefing v1, AlumniGTM Company Workflow v1, AlumniGTM Company Resolution Only v1, AlumniGTM Prospect Discovery v1, AlumniGTM Prospect Resolution v1
- **4 Parallel.ai operations** running directly from Trigger.dev: ICP job titles, company intel briefing, person intel briefing, company domain resolution (lite) — with dedicated storage tables and auto-persist
- **AlumniGTM pipeline** — full 3-blueprint chain: target company analysis → customer enrichment + Sales Nav URL build → prospect scrape + company resolution + ICP fit evaluation. Tested end-to-end with SecurityPal AI.
- **Dedicated persistence tables**: `company_customers`, `gemini_icp_job_titles`, `company_ads`, `salesnav_prospects` — all with auto-persist wiring in run-pipeline.ts and tenant query endpoints
- **Unified input extraction** — single shared module (`app/services/_input_extraction.py`) with canonical alias maps for all field name variants. All 16 service files migrated.
- **ICP title extraction** via Modal/Anthropic — normalizes inconsistent Parallel output into consistent `{ title, buyer_role, reasoning }` structure. Flat table `extracted_icp_job_title_details` for joins.
- **Sales Navigator URL scraper** (`person.search.sales_nav_url`) — RapidAPI, auto-pagination (up to 50 pages), fan-out compatible.
- **BlitzAPI standalone operations** — dedicated single-provider operations: company enrichment, company search, domain-to-LinkedIn, waterfall ICP search, employee finder, find work email
- **HQ workflow operations** — 8 operations wrapping HQ `/run/` endpoints: infer LinkedIn URL, ICP job titles (Gemini), discover customers (Gemini), lookup customers (resolved), ICP criterion, Sales Nav URL builder, evaluate ICP fit, company name lookup
- **Entity relationships table** — typed, directional relationships between entities (has_customer, has_target, has_competitor, works_at, alumni_of) with dedup and invalidation
- **9 CRM resolution operations** — domain from email/LinkedIn/name, LinkedIn from domain (HQ + BlitzAPI), person LinkedIn from email, location from domain, domain from name (HQ + Parallel)
- **Bright Data validation** via HQ (Indeed + LinkedIn raw tables, cross-source job validation endpoint)
- **Enigma operating locations** — brand → physical locations with open/closed status
- **AI blueprint assembler** with natural language mode (Claude → OpenAI → Gemini)
- **Coverage check** endpoint for pre-outbound readiness
- **Operation registry** with formal input/output metadata
- **Super-admin auth on `/api/v1/execute`** — requires `org_id` + `company_id` in body
- **20 Modal micro-functions** for Parallel.ai fallbacks
- **FMCSA daily signal pipeline** in separate repo (`ongoing-data-pulls`)
- **50+ test files**, 20 migrations

## Key Files

| File | What it is |
|---|---|
| `CLAUDE.md` | Project conventions, tech stack, directory structure |
| `docs/SYSTEM_OVERVIEW.md` | Complete technical reference — all operations, providers, schema, architecture |
| `docs/CAPABILITIES.md` | Business-facing capabilities and GTM use cases |
| `docs/STRATEGIC_DIRECTIVE.md` | Non-negotiable build rules |
| `docs/CONDITION_SCHEMA.md` | Conditional step execution schema |
| `docs/NESTED_FAN_OUT_TRACE.md` | How recursive fan-out works |
| `docs/STEP_TIMELINE_EVENT_SCHEMA.md` | Per-step timeline event contract |
| `app/registry/operations.yaml` | Operation registry metadata (needs updating for new ops) |
| `app/routers/execute_v1.py` | All operation dispatch + SUPPORTED_OPERATION_IDS |
| `trigger/src/tasks/run-pipeline.ts` | Pipeline runner (fan-out, conditions, freshness, timeline) |

## What's Not Built Yet

Read the "What's Not Built Yet" section in `docs/SYSTEM_OVERVIEW.md` for the current backlog.

## Critical Open Issues

1. **`experience_key` dedup on HQ `core.person_work_history` is broken.** 2.17M rows have stale hash values from a prior process. Needs full re-key + re-dedup. Read `docs/troubleshooting-fixes/2026-02-25_experience_key_dedup_postmortem.md` before touching this table. The `trg_sync_person_experience` trigger is DISABLED.

2. **ICP title extraction operation (`company.derive.extract_icp_titles`)** is built but Railway deploy was queued during a GitHub incident. Needs verification that it's live, then test on withcoverage.com.

3. **Sales Nav alumni search (`person.search.sales_nav_alumni`)** — the template-based version that swaps LinkedIn org IDs per company — is NOT built. Blocked on HQ's `core.companies` not having a `linkedin_org_id` column. The URL-based scraper (`person.search.sales_nav_url`) IS built and works with exact URLs.

4. **DOT number identity resolution** for FMCSA carriers + Enigma match operation — parked. `company_entities` needs a `dot_number` column for carriers without domains.

## AlumniGTM Pipeline Status

**Pipeline is fully operational end-to-end.** Tested with SecurityPal AI → 18 customers discovered → 15 enriched with Sales Nav URLs → Elastic alumni scrape produced 66 prospects → 34 evaluated as ICP fit = yes.

| Piece | Status |
|---|---|
| Blueprint 1: Company Workflow (7 steps) | **Live.** Infer LinkedIn → BlitzAPI enrich → Gemini ICP titles → HQ customer lookup → Gemini fallback → ICP criterion → Sales Nav URL |
| Blueprint 2: Company Resolution (5 steps) | **Live.** HQ name lookup → Gemini infer LinkedIn → BlitzAPI domain-to-LinkedIn → BlitzAPI enrich → Sales Nav URL build |
| Blueprint 3: Prospect Discovery (6 steps) | **Live.** Sales Nav scrape (fan-out) → HQ name resolve → Gemini infer LinkedIn → BlitzAPI domain-to-LinkedIn → BlitzAPI enrich → ICP fit evaluate |
| ICP job titles (Parallel Deep Research) | Live. 155 companies processed. Dedicated table. |
| ICP job titles (Gemini) | Live. Dedicated `gemini_icp_job_titles` table. |
| Company customers (HQ resolved lookup) | Live. Dedicated `company_customers` table with auto-persist. |
| Sales Nav prospects | Live. Dedicated `salesnav_prospects` table with auto-persist. |
| Company ads (Adyntel) | Live. Dedicated `company_ads` table with auto-persist. |
| BlitzAPI standalone operations | Live. Company enrich, company search, domain-to-LinkedIn, waterfall ICP, employee finder, find work email. |
| Unified input extraction | Live. Single alias map across all 16 service files. |
| Condition evaluator shorthand | Live. Supports `exists`, `not`, `eq`, `ne`, etc. |
| Sales Nav auto-pagination | Live. Up to 50 pages per scrape. |
| Entity relationships table | Live. Empty — no relationships recorded yet. |
| HQ person_work_history dedup | Broken. Needs re-key. (deprioritized) |
| Blueprint auto-chaining | Not built. Blueprints triggered manually in sequence. |

## Next Priorities

1. **Blueprint auto-chaining** — automatic submission of next blueprint when current completes (Blueprint 1 → 2 → 3 hands-off)
2. **Entity relationship wiring** — record customer/alumni relationships during pipeline execution
3. **Person enrichment from Sales Nav URLs** — resolve hashed LinkedIn URLs to canonical `/in/username` format for Prospeo/LeadMagic enrichment

## Postmortems & Troubleshooting

Read `docs/troubleshooting-fixes/` for incidents:
- `2026-02-25_icp_auto_persist_not_writing.md` — Railway/Trigger.dev deploy timing gap
- `2026-02-25_experience_key_dedup_postmortem.md` — stale hash values, incomplete dedup

Key lessons:
- Always provide complete env var checklists before deploy/test
- Never print secrets to terminal
- Deploy Railway FIRST, wait, then Trigger.dev
- Always recompute hash columns on ALL rows, never just NULLs
- Verify existing column values before assuming they're empty
- User instruction is the hard boundary — don't overstep
