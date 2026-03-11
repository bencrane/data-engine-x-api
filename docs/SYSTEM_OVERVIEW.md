# System Overview: data-engine-x-api

Technical reference snapshot originally written on 2026-02-22 and updated with production reality notes on 2026-03-10.

## Status

- Status: active technical reference
- Authority: lower than the audited production-truth docs
- Use this for: broad system lookup, feature/reference orientation, and codebase surface area
- Do not use this for: proving deployment status, proving production health, or resolving contradictions with audited reports

This file is useful, but it is **not** the sole source of truth for live production state.

It is a broad technical reference, not a direct production audit. If you read it as if every built capability is working cleanly in production, you will be misled.

For reading order across the Chief Agent docs, start with `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md`.

For factual, current, production-state truth, use:

1. `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
2. `docs/DATA_ENGINE_X_ARCHITECTURE.md`
3. `CLAUDE.md`

If this file conflicts with those documents, the production audit and architecture report are correct.

---

## What This System Is

`data-engine-x-api` is a multi-tenant entity intelligence pipeline. It takes company domains, carrier DOT numbers, permit IDs, or person identifiers as input, runs them through configurable sequences of enrichment, research, and discovery operations, and produces structured, persisted intelligence as output.

The system supports multiple product surfaces on the same infrastructure:
- **CRM Enrichment**: Client gives their data → system cleans/enriches/scores → returns it better
- **Outbound Intelligence**: Define a target segment → discover companies and people → get contact info → output is campaign-ready
- **Trigger-Based Outbound**: Government filings (FMCSA, building permits, bankruptcy) detected as buying signals → enrich → contact → outbound
- **Market Intelligence**: Geographic analytics for construction, trucking, and ecommerce verticals

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| API | FastAPI (Python) on Railway | Auth, routing, validation, persistence, operation execution |
| Orchestration | Trigger.dev (TypeScript) | Pipeline execution, step sequencing, fan-out, conditional execution, retries |
| Database | Supabase (Postgres) | Tenant data, blueprints, submissions, run state, step results, entity state, snapshots, timeline |
| Secrets | Doppler → Docker | All secrets injected at container startup via `doppler run --` |
| Micro-operations | Modal (Python) | Parallel.ai-backed micro-functions for fallback data resolution |
| External providers | 21+ provider APIs | Enrichment, search, verification, research, ads, technographics, revenue, permits, court filings |
| Signal pipelines | mixed repo history | older FMCSA signal work lived in `ongoing-data-pulls`; this repo now also contains newer FMCSA ingestion directives, mappings, and task files whose presence does not by itself prove production deployment |

---

## Architecture

Production reality note as of `2026-03-10`: the execution flow below is the intended active loop and it does run in production, but pipeline success does **not** guarantee that every side-effect landed. Dedicated-table auto-persist is partially broken in production. See `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`.

### Execution Flow

```
Client → POST /api/v1/batch/submit
  → Creates submission + pipeline runs (one per entity)
  → Triggers Trigger.dev run-pipeline task per run
    → Runner reads blueprint snapshot
    → For each step:
      → Evaluates condition (skip if not met)
      → Checks entity freshness (skip if recent data exists)
      → Derives entity_type from operation_id prefix
      → Calls POST /api/v1/execute on FastAPI (internal HTTP)
      → FastAPI routes to operation service → provider waterfall
      → Result merges into cumulative context
      → If fan_out step: creates child runs (recursive — nested fan-out supported)
        → Child runs execute remaining steps per fan-out entity
    → On completion: captures entity snapshot → upserts entity state → writes timeline events
  → Client polls POST /api/v1/batch/status for results (recursive tree display)
  → Client queries POST /api/v1/entities/* for accumulated intelligence
  → Client checks POST /api/v1/coverage/check for data readiness
```

### Key Architectural Patterns

**Output Chaining (Cumulative Context):** Each step's canonical output is shallow-merged into a cumulative context dict. Subsequent steps read from this context.

**Fan-Out (Nested):** A step marked `fan_out: true` that returns a `results` array creates child pipeline runs — one per result. Child runs can themselves fan-out, creating grandchild runs. Recursive to arbitrary depth.

**Conditional Step Execution:** Steps can include a `condition` in `step_config` evaluated against cumulative context. Supports: `exists`, `eq`, `ne`, `lt`, `gt`, `lte`, `gte`, `contains`, `icontains`, `in`, plus `all` (AND) and `any` (OR) logical groups. Skipped steps don't fail the run.

**Entity Deduplication:** Two levels — within a batch (fan-out dedup by identifier) and across batches (freshness check against entity state with `skip_if_fresh` in step_config).

**Entity State Accumulation:** Completed pipeline runs upsert canonical entity records. Upserts are additive — non-null overwrites, null preserves. Identity resolution is deterministic via UUIDv5 from natural keys.

**Entity Snapshots:** Before each entity upsert, the previous state is captured as an append-only snapshot. Enables change detection ("employee_count went from 50 to 65").

### Entity Relationships

The `entity_relationships` table records typed, directional relationships between entities. Each relationship has a source entity (identified by domain or LinkedIn URL), a relationship type (e.g., `has_customer`, `has_competitor`, `works_at`, `alumni_of`), and a target entity. Relationships are org-scoped, deduplicated on (source, relationship, target), and support invalidation for time-bounded facts like employment.

Production reality note as of `2026-03-10`: this capability exists in code and schema, but the production table has `0` rows. It has never been used in production.

Internal endpoints: `/api/internal/entity-relationships/record`, `/record-batch`, `/invalidate`.
Query endpoint: `/api/v1/entity-relationships/query`.

**Entity Timeline:** Append-only log per entity capturing every step execution — which operation ran, which provider succeeded, which fields were updated, skip reasons. Queryable per entity, per run, or per submission.

**Operation Registry + AI Blueprint Assembler:** Formal metadata for all operations (inputs, outputs, cost tier, fan-out support). AI endpoint assembles blueprints from natural language or field checklists using Claude → OpenAI → Gemini fallback chain.

**Coverage Check:** Pre-outbound readiness assessment — "do I have enough enriched data for this prospect's TAM?"

---

## Operations (77 FastAPI-registered ops in code)

Production reality note as of `2026-03-10`: only `36` operations have ever been called against real production data. `46` executable operations in the current code catalog have never been called in production. That larger never-called count includes the `4` Trigger-direct operations that live outside the `77` FastAPI operation registry rows in this table. See `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` for the audited call set.

### Company Enrichment (9)
| Operation ID | Provider(s) |
|---|---|
| `company.enrich.profile` | Prospeo, BlitzAPI, CompanyEnrich, LeadMagic |
| `company.enrich.profile_blitzapi` | BlitzAPI (dedicated single-provider company enrichment with linkedin_id) |
| `company.enrich.technographics` | LeadMagic |
| `company.enrich.tech_stack` | TheirStack (job-posting-derived) |
| `company.enrich.hiring_signals` | TheirStack |
| `company.enrich.ecommerce` | StoreLeads |
| `company.enrich.locations` | Enigma (operating locations with addresses and open/closed status) |
| `company.enrich.card_revenue` | Enigma (GraphQL match → analytics) |
| `company.enrich.fmcsa` | FMCSA QCMobile API (3-call merge: base + BASIC scores + authority) |

### Company Search / Discovery (6)
| Operation ID | Provider(s) |
|---|---|
| `company.search` | Prospeo, BlitzAPI, CompanyEnrich |
| `company.search.blitzapi` | BlitzAPI (company search with keyword, industry, location, size, type, founded year filters + pagination) |
| `company.search.ecommerce` | StoreLeads |
| `company.search.fmcsa` | FMCSA QCMobile API |
| `company.search.by_tech_stack` | TheirStack |
| `company.search.by_job_postings` | TheirStack |

### Company Research (16)
| Operation ID | Provider(s) |
|---|---|
| `company.research.resolve_g2_url` | Gemini → OpenAI |
| `company.research.resolve_pricing_page_url` | Gemini → OpenAI |
| `company.research.discover_competitors` | RevenueInfra |
| `company.research.find_similar_companies` | RevenueInfra |
| `company.research.lookup_customers` | RevenueInfra |
| `company.research.lookup_customers_resolved` | RevenueInfra (HQ resolved DB lookup) |
| `company.research.infer_linkedin_url` | RevenueInfra (HQ Gemini) |
| `company.research.icp_job_titles_gemini` | RevenueInfra (HQ Gemini) |
| `company.research.discover_customers_gemini` | RevenueInfra (HQ Gemini) |
| `company.research.lookup_champions` | RevenueInfra |
| `company.research.lookup_champion_testimonials` | RevenueInfra |
| `company.research.lookup_alumni` | RevenueInfra |
| `company.research.check_vc_funding` | RevenueInfra |
| `company.research.fetch_sec_filings` | RevenueInfra |
| `company.research.check_court_filings` | CourtListener Search API |
| `company.research.get_docket_detail` | CourtListener Dockets API |

### Company Derive (8)
| Operation ID | Provider(s) |
|---|---|
| `company.derive.pricing_intelligence` | RevenueInfra (14 Gemini endpoints) |
| `company.derive.icp_criterion` | RevenueInfra (HQ Gemini) |
| `company.derive.salesnav_url` | RevenueInfra (HQ Claude tool) |
| `company.derive.evaluate_icp_fit` | RevenueInfra (HQ Gemini) |
| `company.derive.icp_job_titles` | Parallel.ai Deep Research (direct from Trigger.dev — long-running async) |
| `company.derive.extract_icp_titles` | Modal/Anthropic (extracts consistent title/buyer_role/reasoning from raw Parallel ICP output) |
| `company.derive.intel_briefing` | Parallel.ai Deep Research (direct from Trigger.dev — company intelligence briefing framed through client lens) |
| `company.derive.detect_changes` | Internal (entity snapshot diff) |

### Company Analyze (3)
| Operation ID | Provider(s) |
|---|---|
| `company.analyze.sec_10k` | RevenueInfra Modal (Gemini) |
| `company.analyze.sec_10q` | RevenueInfra Modal (Gemini) |
| `company.analyze.sec_8k_executive` | RevenueInfra Modal (Gemini) |

### Company Signals (1)
| Operation ID | Provider(s) |
|---|---|
| `company.signal.bankruptcy_filings` | CourtListener Dockets API |

### Company Ads (3)
| Operation ID | Provider(s) |
|---|---|
| `company.ads.search.linkedin` | Adyntel |
| `company.ads.search.meta` | Adyntel |
| `company.ads.search.google` | Adyntel |

### Person (11)
| Operation ID | Provider(s) |
|---|---|
| `person.search` | Prospeo, BlitzAPI (Employee Finder + Waterfall ICP), CompanyEnrich, LeadMagic (Employee Finder + Role Finder) |
| `person.search.waterfall_icp_blitzapi` | BlitzAPI (dedicated cascade ICP search with tier matching) |
| `person.search.employee_finder_blitzapi` | BlitzAPI (dedicated employee search with level/function/location filters) |
| `person.search.sales_nav_url` | RapidAPI Sales Navigator scraper (accepts full Sales Nav URL, returns person results) |
| `person.enrich.profile` | Prospeo → (AmpleLeads if include_work_history) → LeadMagic |
| `person.contact.resolve_email` | LeadMagic → Icypeas → Parallel |
| `person.contact.resolve_email_blitzapi` | BlitzAPI (dedicated work email finder from LinkedIn URL) |
| `person.contact.verify_email` | MillionVerifier → Reoon |
| `person.contact.resolve_mobile_phone` | LeadMagic → BlitzAPI |
| `person.derive.intel_briefing` | Parallel.ai Deep Research (direct from Trigger.dev — person intelligence briefing for outreach) |
| `person.derive.detect_changes` | Internal (entity snapshot diff) |

### Resolution / CRM Cleanup (9)
| Operation ID | Provider(s) |
|---|---|
| `company.resolve.domain_from_email` | RevenueInfra HQ (reference.email_to_person + email domain extraction) |
| `company.resolve.domain_from_linkedin` | RevenueInfra HQ (core.companies) |
| `company.resolve.domain_from_name` | RevenueInfra HQ (extracted.cleaned_company_names) |
| `company.resolve.domain_from_name_hq` | RevenueInfra HQ (`/run/lookup-company-by-name`) |
| `company.resolve.domain_from_name_parallel` | Parallel.ai lite (resolve company domain + LinkedIn URL from name, direct from Trigger.dev) |
| `company.resolve.linkedin_from_domain` | RevenueInfra HQ (core.companies) |
| `company.resolve.linkedin_from_domain_blitzapi` | BlitzAPI (domain to LinkedIn URL lookup) |
| `person.resolve.linkedin_from_email` | RevenueInfra HQ (reference.email_to_person) |
| `company.resolve.location_from_domain` | RevenueInfra HQ (core.company_locations) |

### Construction / Permits (5)
| Operation ID | Provider(s) |
|---|---|
| `permit.search` | Shovels |
| `contractor.enrich` | Shovels |
| `contractor.search` | Shovels |
| `contractor.search.employees` | Shovels (fan-out capable) |
| `address.search.residents` | Shovels (fan-out capable) |

### Job Postings (2)
| Operation ID | Provider(s) |
|---|---|
| `job.search` | TheirStack (41-field mapping, 65+ filters, pagination, hiring team, embedded company) |
| `job.validate.is_active` | RevenueInfra HQ (cross-references Bright Data Indeed + LinkedIn snapshots) |

### Market Intelligence (5)
| Operation ID | Provider(s) |
|---|---|
| `market.search.cities` | Shovels |
| `market.search.counties` | Shovels |
| `market.search.zipcodes` | Shovels |
| `market.search.jurisdictions` | Shovels |
| `market.enrich.metrics_monthly` | Shovels (routes by geo_type) |
| `market.enrich.metrics_current` | Shovels (routes by geo_type) |
| `market.enrich.geo_detail` | Shovels (routes by geo_type) |
| `address.search` | Shovels |

---

## Providers (21+)

| Provider | Adapter File | Verticals |
|---|---|---|
| Prospeo | `app/providers/prospeo.py` | B2B SaaS |
| BlitzAPI | `app/providers/blitzapi.py` | B2B SaaS |
| CompanyEnrich | `app/providers/companyenrich.py` | B2B SaaS |
| LeadMagic | `app/providers/leadmagic.py` | B2B SaaS |
| Icypeas | `app/providers/icypeas.py` | B2B SaaS |
| MillionVerifier | `app/providers/millionverifier.py` | B2B SaaS |
| Reoon | `app/providers/reoon.py` | B2B SaaS |
| Parallel AI | `app/providers/parallel_ai.py` | B2B SaaS |
| Adyntel | `app/providers/adyntel.py` | B2B SaaS |
| Gemini | `app/providers/gemini.py` | LLM |
| OpenAI | `app/providers/openai_provider.py` | LLM |
| Anthropic | `app/providers/anthropic_provider.py` | LLM (blueprint assembler) |
| AmpleLeads | `app/providers/ampleleads.py` | B2B SaaS |
| StoreLeads (enrich) | `app/providers/storeleads_enrich.py` | Ecommerce |
| StoreLeads (search) | `app/providers/storeleads_search.py` | Ecommerce |
| Enigma | `app/providers/enigma.py` | Revenue intelligence (GraphQL) |
| FMCSA | `app/providers/fmcsa.py` | Trucking |
| TheirStack | `app/providers/theirstack.py` | B2B SaaS (hiring/tech stack) |
| Shovels | `app/providers/shovels.py` | Construction |
| CourtListener | `app/providers/courtlistener.py` | Legal/Risk |
| RevenueInfra | `app/providers/revenueinfra/` | Internal HQ (pricing, competitors, customers, champions, alumni, VC, SEC, similar companies) |

---

## Database Schema (Migrations 001-020)

| Migration | Purpose |
|---|---|
| 001 | Base multi-tenant schema: orgs, companies, users, api_tokens, super_admins, steps, blueprints, blueprint_steps, submissions, pipeline_runs, step_results |
| 002 | `users.password_hash` for tenant login |
| 003 | `api_tokens.user_id` ownership |
| 004 | Generic HTTP executor config on `steps` (legacy) |
| 005 | `operation_runs` + `operation_attempts` for durable execution history |
| 006 | `blueprint_steps.operation_id` + `step_config` JSONB, relaxed `step_id` nullability |
| 007 | `company_entities` + `person_entities` for canonical entity state |
| 008 | `companies.domain` field for tenant companies |
| 009 | `entity_timeline` for per-entity operation audit log |
| 010 | `pipeline_runs.parent_pipeline_run_id` + `blueprint_steps.fan_out` for fan-out |
| 011 | Entity timeline submission lookup index |
| 012 | `entity_snapshots` for canonical history / change detection |
| 013 | `job_posting_entities` for job posting entity state + `job` entity type constraints on entity_timeline, entity_snapshots, operation_runs |
| 014 | `entity_relationships` — typed, directional relationships between entities (companies and persons) with dedup and invalidation |
| 015 | `icp_job_titles` — raw Parallel.ai ICP research output per company (JSONB), one row per company per org |
| 016 | `company_intel_briefings` + `person_intel_briefings` — raw Parallel.ai intel briefing output, one row per entity per client lens |
| 017 | `extracted_icp_job_title_details` + `icp_job_titles.extracted_titles` column — extracted ICP titles in flat and JSONB form |
| 018 | AlumniGTM persistence layer — new `company_entities` columns (`company_linkedin_id`, `icp_criterion`, `salesnav_url`, `icp_fit_verdict`, `icp_fit_reasoning`) + `company_customers` and `gemini_icp_job_titles` tables |
| 019 | Adyntel ads persistence layer — new `company_ads` table for LinkedIn/Meta/Google ad intelligence (dedup on `(org_id, company_domain, platform, ad_id)` when `ad_id` is present) |
| 020 | Sales Navigator prospects persistence layer — new `salesnav_prospects` table for `person.search.sales_nav_url` output (dedup on `(org_id, source_company_domain, linkedin_url)` when `linkedin_url` is present) |

---

## Modal Micro-Operations (20 endpoints)

Deployed at `https://bencrane--data-engine-x-micro-fastapi-app.modal.run`

Parallel.ai-backed functions for fallback data resolution. 11 company + 8 person functions + 1 employee range.

---

## Signal Pipelines (separate repo: `ongoing-data-pulls`)

Historical note: this section originally described FMCSA work that lived in a separate repo.

Current Chief Agent guidance:

- treat this section as reference/history, not as a current production verification statement
- this repo now also contains substantial FMCSA ingestion directives, mapping docs, and Trigger task files
- the existence of those newer FMCSA docs/files does not itself prove production completion
- use `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`, `docs/DATA_ENGINE_X_ARCHITECTURE.md`, and `CLAUDE.md` for live-truth claims

---

## API Endpoints (Entity Relationships)

- `POST /api/internal/entity-relationships/record`
- `POST /api/internal/entity-relationships/record-batch`
- `POST /api/internal/entity-relationships/invalidate`
- `POST /api/v1/entity-relationships/query`

---

## Infrastructure Features

| Feature | Status |
|---|---|
| Batch orchestration | ✅ Used in production - production has `48` submissions and `837` pipeline runs. |
| Nested fan-out (recursive) | ✅ Used in production - child pipeline runs are present in production and active blueprints depend on fan-out. |
| Conditional step execution | ✅ Used in production - production has `990` skipped `step_results`, which reflects active conditional/skip behavior. |
| Entity deduplication (fan-out + freshness) | ⚠️ Built and active, but not fully trustworthy under current stuck-run and persistence-failure conditions. |
| Entity state accumulation (company, person, job) | ✅ Used in production - production has `88` `company_entities`, `503` `person_entities`, and `1` `job_posting_entities`. |
| Entity snapshots + change detection | ⚠️ Snapshots are live (`93` rows), but detect-changes operations have never been called in production. |
| Entity relationships (typed, directional, deduped) | 🔲 Never used in production - table exists but has `0` rows. |
| Per-step entity timeline | ✅ Used in production - production has `4345` `entity_timeline` rows. |
| Operation registry (77 ops) | ⚠️ Built, but production has only executed `36` operations. Most of the registry has never been used with real data. |
| AI blueprint assembler (NL + fields) | ⚠️ Built, but production usage was not verifiable from the database audit. |
| Coverage check endpoint | ⚠️ Built, but production usage was not verifiable from the database audit. |
| Person entity filters (title, seniority, department) | ⚠️ Built, but production usage was not verifiable from the database audit. |
| Job posting entity type + query endpoint | ✅ Used in production - production has job pipeline activity and `job_posting_entities` data, though only `1` row currently exists. |
| AlumniGTM dedicated persistence tables (`company_customers`, `gemini_icp_job_titles`) | ⚠️ Broken in prod - both tables exist but have `0` rows despite successful upstream step outputs. |
| Adyntel ads dedicated persistence table (`company_ads`) | ⚠️ Broken in prod - the table is missing entirely from production; migration `019` never landed. |
| Sales Navigator prospects dedicated persistence table (`salesnav_prospects`) | ⚠️ Broken in prod - table exists but has `0` rows despite successful upstream steps; context shape prevents auto-persist from firing. |
| Bright Data cross-source job validation (via HQ) | ✅ Used in production - `job.validate.is_active` has been executed successfully in production. |
| Staffing enrichment blueprint (7-step, 2 fan-outs) | ✅ Used in production - it has completed successfully in production. |
| Doppler secrets management | ✅ Used in production - the app runtime is using Doppler-injected secrets. |
| Super-admin API key auth | ⚠️ Built, but production usage was not verifiable from the database audit. |

---

## Testing

36+ test files in `tests/`. Run with `uv run --with pytest --with pytest-asyncio --with pyyaml pytest`.

---

## Build History

| Phase | What was built |
|---|---|
| 1-4 | Core cleanup, provider extraction, contracts, batch orchestration, entity state, docs |
| 5 | Live testing, Doppler, Dockerfile, super-admin auth, output flattening fixes |
| 6 | Fan-out, entity timeline, per-step entity_type derivation |
| 7 | Provider adapter audit (13 mismatches fixed across all providers) |
| 8 | Operation hardening (all operations safe against rich context) |
| 9 | Person enrich profile (Prospeo/AmpleLeads/LeadMagic waterfall) |
| 10 | Modal micro-functions (20 Parallel.ai endpoints) |
| 11 | RevenueInfra operations (pricing intelligence, competitors, customers, champions, alumni, VC funding, similar companies) |
| 12 | Person search upgrade (canonical inputs, 4 provider modes, LeadMagic/BlitzAPI new adapters) |
| 13 | StoreLeads ecommerce (enrich + search), Enigma card revenue (match → analytics) |
| 14 | Conditional step execution, nested fan-out verification |
| 15 | Per-step timeline observability, entity deduplication (fan-out + freshness) |
| 16 | Operation registry, AI blueprint assembler (NL + fields + Anthropic primary) |
| 17 | Coverage check endpoint, person entity filters |
| 18 | FMCSA operations (search + enrich via QCMobile API) |
| 19 | Entity snapshots + change detection (company + person) |
| 20 | SEC filing operations (fetch + 3 analysis via Modal/Gemini) |
| 21 | TheirStack operations (tech stack search, job posting search, technographics, hiring signals) |
| 22 | Shovels lead gen (permits, contractors, employees, residents) |
| 23 | CourtListener (court filing check, bankruptcy signals, docket detail) |
| 24 | Shovels market intelligence (city/county/zipcode/jurisdiction metrics + details) |
| 25 | FMCSA daily signal pipeline (separate repo, 6 feeds, all working) |
| 26 | Staffing vertical: TheirStack adapter enrichment (41 fields, `job.search` op, 65+ filters), job posting entity type, Bright Data validation, staffing enrichment blueprint |
| 27 | Enigma operating locations (`company.enrich.locations`), 6 CRM resolve operations (domain from email/LinkedIn/name, LinkedIn from domain, person LinkedIn from email, location from domain), CRM Cleanup + CRM Enrichment blueprints, super-admin auth on `/api/v1/execute` |
| 28 | AlumniGTM pipeline: BlitzAPI company enrichment (dedicated), 6 HQ workflow operations, 3 BlitzAPI person operations, BlitzAPI company search, HQ company name lookup, HQ resolved customer lookup, Parallel.ai company resolution |
| 29 | Persistence layer: `company_customers`, `gemini_icp_job_titles`, `company_ads`, `salesnav_prospects` tables + auto-persist + query endpoints. New columns on `company_entities`. |
| 30 | Infrastructure: unified input extraction (`_input_extraction.py`), condition evaluator shorthand, Sales Nav auto-pagination, HQ Gemini 300s timeouts |

---

## Defined Blueprints

Production reality note as of `2026-03-10`: these are the blueprints defined in the system, not a guarantee that they are actively used, healthy, or complete successfully in production. See `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` for actual usage counts and completion rates.

| Blueprint | Org | Steps | Purpose |
|---|---|---|---|
| CRM Cleanup v1 | Staffing Activation, Revenue Activation | 7 | Domain resolution cascade (email → LinkedIn → name), fill LinkedIn/location, verify email |
| CRM Enrichment v1 | Staffing Activation, Revenue Activation | 3 | Company profile enrichment, resolve email where missing, verify email |
| Staffing Enrichment v1 | Staffing Activation, Revenue Activation | 7 | Job search → validate active → company enrich → person search → email → verify → phone (2 fan-outs) |
| AlumniGTM Company Workflow v1 | AlumniGTM | 7 | Infer LinkedIn URL → BlitzAPI enrich → Gemini ICP titles → HQ customer lookup (→ Gemini fallback) → ICP criterion → Sales Nav URL |
| AlumniGTM Company Resolution Only v1 | AlumniGTM | 5 | HQ name lookup → Gemini infer LinkedIn → BlitzAPI domain-to-LinkedIn → BlitzAPI enrich → Sales Nav URL build |
| AlumniGTM Prospect Discovery v1 | AlumniGTM | 6 | Sales Nav scrape (fan-out) → HQ name resolve → Gemini infer LinkedIn → BlitzAPI domain-to-LinkedIn → BlitzAPI enrich → ICP fit evaluate |

---

## What's Not Built Yet

- **Blueprint auto-chaining** — automatic submission of next blueprint when current completes (Blueprint 1 → 2 → 3 hands-off)
- **Person enrichment from Sales Nav URLs** — resolve hashed LinkedIn URLs to canonical `/in/username` format for Prospeo/LeadMagic enrichment
- **Entity relationship wiring** — record customer/alumni/works_at relationships during pipeline execution
- **Output delivery** — push results to CRM, campaign tool, webhook, CSV
- **Input ingestion** — CRM pull, CSV upload validation, auto-derived input requirements
- **Bright Data connector** — automated puller/webhook to ingest Indeed + LinkedIn snapshots from Bright Data API (tables + ingestion endpoints exist in HQ, connector not wired)
- **Cross-source job matching automation** — scheduled comparison of TheirStack job postings against Bright Data to auto-update `posting_status`
- **Page content extraction** — scraping G2/pricing pages for structured intelligence
- **Google Maps scrape + owner identification** — for local/SMB lead gen
- **Website scrape for owner detection** — LLM-based owner identification from scraped content
- **Scheduled monitoring** — cron-based change detection triggers
- **FMCSA daily changes wired into data-engine-x** — endpoint exists in `ongoing-data-pulls`, needs provider adapter in data-engine-x

---

## Operational Notes

- **Deploy flow**: `git push origin main` → Railway auto-deploys. Trigger.dev: `cd trigger && npx trigger.dev@latest deploy`. Modal: `cd modal && modal deploy app.py`.
- **Migrations**: Run manually via `psql "$DATABASE_URL" -f supabase/migrations/0XX_*.sql`.
- **Key management**: All secrets in Doppler. Railway reads via `DOPPLER_TOKEN` + Dockerfile `doppler run`. Trigger.dev has its own env vars.
- **Verticals covered**: B2B SaaS, Ecommerce, Trucking, Construction, Legal/Risk, Revenue Intelligence, Staffing
