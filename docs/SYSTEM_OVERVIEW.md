# System Overview: data-engine-x-api

Comprehensive documentation of the system as of 2026-02-22. Written for AI agents or human engineers who need full context to continue development.

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
| Signal pipelines | `ongoing-data-pulls` (separate repo) | FMCSA daily census diff feeds → stored in HQ database |

---

## Architecture

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

Internal endpoints: `/api/internal/entity-relationships/record`, `/record-batch`, `/invalidate`.
Query endpoint: `/api/v1/entity-relationships/query`.

**Entity Timeline:** Append-only log per entity capturing every step execution — which operation ran, which provider succeeded, which fields were updated, skip reasons. Queryable per entity, per run, or per submission.

**Operation Registry + AI Blueprint Assembler:** Formal metadata for all operations (inputs, outputs, cost tier, fan-out support). AI endpoint assembles blueprints from natural language or field checklists using Claude → OpenAI → Gemini fallback chain.

**Coverage Check:** Pre-outbound readiness assessment — "do I have enough enriched data for this prospect's TAM?"

---

## Operations (62 live)

### Company Enrichment (8)
| Operation ID | Provider(s) |
|---|---|
| `company.enrich.profile` | Prospeo, BlitzAPI, CompanyEnrich, LeadMagic |
| `company.enrich.technographics` | LeadMagic |
| `company.enrich.tech_stack` | TheirStack (job-posting-derived) |
| `company.enrich.hiring_signals` | TheirStack |
| `company.enrich.ecommerce` | StoreLeads |
| `company.enrich.locations` | Enigma (operating locations with addresses and open/closed status) |
| `company.enrich.card_revenue` | Enigma (GraphQL match → analytics) |
| `company.enrich.fmcsa` | FMCSA QCMobile API (3-call merge: base + BASIC scores + authority) |

### Company Search / Discovery (5)
| Operation ID | Provider(s) |
|---|---|
| `company.search` | Prospeo, BlitzAPI, CompanyEnrich |
| `company.search.ecommerce` | StoreLeads |
| `company.search.fmcsa` | FMCSA QCMobile API |
| `company.search.by_tech_stack` | TheirStack |
| `company.search.by_job_postings` | TheirStack |

### Company Research (11)
| Operation ID | Provider(s) |
|---|---|
| `company.research.resolve_g2_url` | Gemini → OpenAI |
| `company.research.resolve_pricing_page_url` | Gemini → OpenAI |
| `company.research.discover_competitors` | RevenueInfra |
| `company.research.find_similar_companies` | RevenueInfra |
| `company.research.lookup_customers` | RevenueInfra |
| `company.research.lookup_champions` | RevenueInfra |
| `company.research.lookup_champion_testimonials` | RevenueInfra |
| `company.research.lookup_alumni` | RevenueInfra |
| `company.research.check_vc_funding` | RevenueInfra |
| `company.research.fetch_sec_filings` | RevenueInfra |
| `company.research.check_court_filings` | CourtListener Search API |
| `company.research.get_docket_detail` | CourtListener Dockets API |

### Company Derive (5)
| Operation ID | Provider(s) |
|---|---|
| `company.derive.pricing_intelligence` | RevenueInfra (14 Gemini endpoints) |
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

### Person (8)
| Operation ID | Provider(s) |
|---|---|
| `person.search` | Prospeo, BlitzAPI (Employee Finder + Waterfall ICP), CompanyEnrich, LeadMagic (Employee Finder + Role Finder) |
| `person.search.sales_nav_url` | RapidAPI Sales Navigator scraper (accepts full Sales Nav URL, returns person results) |
| `person.enrich.profile` | Prospeo → (AmpleLeads if include_work_history) → LeadMagic |
| `person.contact.resolve_email` | LeadMagic → Icypeas → Parallel |
| `person.contact.verify_email` | MillionVerifier → Reoon |
| `person.contact.resolve_mobile_phone` | LeadMagic → BlitzAPI |
| `person.derive.intel_briefing` | Parallel.ai Deep Research (direct from Trigger.dev — person intelligence briefing for outreach) |
| `person.derive.detect_changes` | Internal (entity snapshot diff) |

### Resolution / CRM Cleanup (6)
| Operation ID | Provider(s) |
|---|---|
| `company.resolve.domain_from_email` | RevenueInfra HQ (reference.email_to_person + email domain extraction) |
| `company.resolve.domain_from_linkedin` | RevenueInfra HQ (core.companies) |
| `company.resolve.domain_from_name` | RevenueInfra HQ (extracted.cleaned_company_names) |
| `company.resolve.linkedin_from_domain` | RevenueInfra HQ (core.companies) |
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

## Database Schema (Migrations 001-017)

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

---

## Modal Micro-Operations (20 endpoints)

Deployed at `https://bencrane--data-engine-x-micro-fastapi-app.modal.run`

Parallel.ai-backed functions for fallback data resolution. 11 company + 8 person functions + 1 employee range.

---

## Signal Pipelines (separate repo: `ongoing-data-pulls`)

**FMCSA Daily Census Feeds:**
- 6 daily diff feeds ingested: carrier, auth_hist, boc3, insurance, revocation, out-of-service
- Stored in HQ database under `fmcsa` schema
- API endpoints for querying changes by date/feed type
- All 6 feeds confirmed working (6,000 test rows ingested)

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
| Batch orchestration | ✅ Live |
| Nested fan-out (recursive) | ✅ Live |
| Conditional step execution | ✅ Live |
| Entity deduplication (fan-out + freshness) | ✅ Live |
| Entity state accumulation (company, person, job) | ✅ Live |
| Entity snapshots + change detection | ✅ Live |
| Entity relationships (typed, directional, deduped) | ✅ Live |
| Per-step entity timeline | ✅ Live |
| Operation registry (62 ops) | ✅ Live |
| AI blueprint assembler (NL + fields) | ✅ Live |
| Coverage check endpoint | ✅ Live |
| Person entity filters (title, seniority, department) | ✅ Live |
| Job posting entity type + query endpoint | ✅ Live |
| Bright Data cross-source job validation (via HQ) | ✅ Live |
| Staffing enrichment blueprint (7-step, 2 fan-outs) | ✅ Live |
| Doppler secrets management | ✅ Live |
| Super-admin API key auth | ✅ Live |

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

---

## Live Blueprints

| Blueprint | Org | Steps | Purpose |
|---|---|---|---|
| CRM Cleanup v1 | Staffing Activation, Revenue Activation | 7 | Domain resolution cascade (email → LinkedIn → name), fill LinkedIn/location, verify email |
| CRM Enrichment v1 | Staffing Activation, Revenue Activation | 3 | Company profile enrichment, resolve email where missing, verify email |
| Staffing Enrichment v1 | Staffing Activation, Revenue Activation | 7 | Job search → validate active → company enrich → person search → email → verify → phone (2 fan-outs) |

---

## What's Not Built Yet

- **Sales Nav alumni search operation** — `person.search.sales_nav_alumni` via RapidAPI Sales Navigator scraper (HQ template table + endpoint exist, provider adapter not built)
- **Alumni Discovery blueprint** — chain CRM cleanup → alumni search → enrich → email (pending Sales Nav operation)
- **Output delivery** — push results to CRM, campaign tool, webhook, CSV
- **Input ingestion** — CRM pull, CSV upload validation, auto-derived input requirements
- **Bright Data connector** — automated puller/webhook to ingest Indeed + LinkedIn snapshots from Bright Data API (tables + ingestion endpoints exist in HQ, connector not wired)
- **Cross-source job matching automation** — scheduled comparison of TheirStack job postings against Bright Data to auto-update `posting_status`
- **ICP assessment operation** — LLM-based fit scoring
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
