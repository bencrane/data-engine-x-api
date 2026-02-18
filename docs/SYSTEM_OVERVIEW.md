# System Overview: data-engine-x-api

Comprehensive documentation of the system as of 2026-02-18. Written for AI agents or human engineers who need full context to continue development.

---

## What This System Is

`data-engine-x-api` is a multi-tenant entity intelligence pipeline. It takes company domains (or person identifiers) as input, runs them through configurable sequences of enrichment, research, and discovery operations, and produces structured, persisted intelligence as output.

The system supports two product surfaces on the same infrastructure:
- **CRM Enrichment**: Client gives their data → system cleans/enriches/scores → returns it better
- **Outbound Intelligence**: Define a target segment → discover companies and people → get contact info → output is campaign-ready

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| API | FastAPI (Python) on Railway | Auth, routing, validation, persistence, operation execution |
| Orchestration | Trigger.dev (TypeScript) | Pipeline execution, step sequencing, fan-out, retries |
| Database | Supabase (Postgres) | Tenant data, blueprints, submissions, run state, step results, entity state |
| Secrets | Doppler → Docker | All secrets injected at container startup via `doppler run --` |
| Micro-operations | Modal (Python) | Parallel.ai-backed micro-functions for fallback data resolution |
| External providers | 13+ provider APIs | Enrichment, search, verification, research, ads, technographics, revenue data |

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
      → Derives entity_type from operation_id prefix
      → Calls POST /api/v1/execute on FastAPI (internal HTTP)
      → FastAPI routes to operation service → provider waterfall
      → Result merges into cumulative context
      → If fan_out step: creates child runs, triggers each
    → On completion: upserts entity state, writes timeline event
  → Client polls POST /api/v1/batch/status for results
  → Client queries POST /api/v1/entities/companies or /persons for accumulated intelligence
```

### Key Architectural Patterns

**Output Chaining (Cumulative Context):** Each step's canonical output is shallow-merged into a cumulative context dict. Subsequent steps read from this context. Step 1 produces `company_domain`, step 2 uses it. No manual wiring needed.

**Fan-Out:** A step marked `fan_out: true` that returns a `results` array creates child pipeline runs — one per result. Child runs execute remaining blueprint steps per item. Fan-out is recursive (nested fan-out supported).

**Conditional Step Execution:** Steps can include a `condition` in `step_config` that is evaluated against the cumulative context at runtime. If the condition is false, the step is skipped (not failed). Supports: `exists`, `eq`, `ne`, `lt`, `gt`, `lte`, `gte`, `contains`, `icontains`, `in`, plus `all` (AND) and `any` (OR) logical groups.

**Entity State Accumulation:** Completed pipeline runs upsert canonical entity records (`company_entities`, `person_entities`). Upserts are additive — non-null fields overwrite, null fields preserve existing. Identity resolution is deterministic via UUIDv5 from natural keys (domain for companies, linkedin_url/email for persons).

**Entity Timeline:** Append-only log per entity capturing which operations touched it, which provider succeeded, and which fields were updated. Queryable via `POST /api/v1/entities/timeline`.

**Provider Waterfall:** Operations call providers in priority order. First success wins (for most operations). Each provider attempt is logged with status, duration, and raw response. Providers that lack required inputs are skipped, not failed.

---

## Auth Model

Four auth paths, all producing authorization context:

| Method | Used By | How |
|---|---|---|
| **Tenant JWT** | Frontend users | `POST /api/auth/login` → JWT in `Authorization: Bearer` |
| **Tenant API Token** | Machine clients | Issued via super-admin, hashed at rest, `Authorization: Bearer` |
| **Super-Admin API Key** | Operator (you) | Env var `SUPER_ADMIN_API_KEY`, `Authorization: Bearer` |
| **Internal Service Auth** | Trigger.dev → FastAPI | Env var `INTERNAL_API_KEY` + `x-internal-org-id` + `x-internal-company-id` headers |

Super-admin auth works on all endpoints (batch submit, batch status, entity queries, plus all `/api/super-admin/*` CRUD).

---

## Multi-Tenancy

Hierarchy: `Org → Company → User`

- Every tenant-owned row includes `org_id`
- Company-scoped operations validate `company_id` belongs to `org_id`
- Blueprints are org-scoped
- Submissions, pipeline runs, step results, entity state are all org+company scoped

---

## Operations (25 live)

### Company Enrichment
| Operation ID | Provider(s) | What it does |
|---|---|---|
| `company.enrich.profile` | Prospeo → BlitzAPI → CompanyEnrich → LeadMagic | Core company profile (name, industry, employees, LinkedIn, description, revenue range) |
| `company.enrich.technographics` | LeadMagic | Website technology stack (analytics, CRM, hosting, frameworks) |
| `company.enrich.ecommerce` | StoreLeads | Ecommerce store intelligence (platform, plan, sales, apps, rankings) |
| `company.enrich.card_revenue` | Enigma (GraphQL) | Card transaction revenue, location count, market ranking |

### Company Search / Discovery
| Operation ID | Provider(s) | What it does |
|---|---|---|
| `company.search` | Prospeo → BlitzAPI → CompanyEnrich | Search companies by name, domain, or filters |
| `company.search.ecommerce` | StoreLeads | Search ecommerce stores by platform, country, installed apps, revenue range |

### Company Research
| Operation ID | Provider(s) | What it does |
|---|---|---|
| `company.research.resolve_g2_url` | Gemini → OpenAI | Find G2 review page URL |
| `company.research.resolve_pricing_page_url` | Gemini → OpenAI | Find pricing page URL |
| `company.research.discover_competitors` | RevenueInfra | Find top 3-5 direct competitors |
| `company.research.find_similar_companies` | RevenueInfra | Find similar companies with similarity scores |
| `company.research.lookup_customers` | RevenueInfra | Known customers from HQ database |
| `company.research.lookup_champions` | RevenueInfra | Case study champions (names, titles, companies) |
| `company.research.lookup_champion_testimonials` | RevenueInfra | Champions with testimonial quotes |
| `company.research.lookup_alumni` | RevenueInfra | Former employees now at other companies |
| `company.research.check_vc_funding` | RevenueInfra | VC funding status, investor list, founded date |

### Company Derive
| Operation ID | Provider(s) | What it does |
|---|---|---|
| `company.derive.pricing_intelligence` | RevenueInfra (14 Gemini endpoints) | Pricing model, free trial, sales motion, billing, tiers, enterprise tier, etc. |

### Company Ads
| Operation ID | Provider(s) | What it does |
|---|---|---|
| `company.ads.search.linkedin` | Adyntel | LinkedIn ad creatives |
| `company.ads.search.meta` | Adyntel | Meta/Facebook ad creatives |
| `company.ads.search.google` | Adyntel | Google ad creatives |

### Person Search
| Operation ID | Provider(s) | What it does |
|---|---|---|
| `person.search` | Prospeo, BlitzAPI (Employee Finder + Waterfall ICP), CompanyEnrich, LeadMagic (Employee Finder + Role Finder) | Find people at a company. Supports canonical inputs: `job_title`, `job_level`, `job_function`, `location`, `max_results`, `cascade`. Provider routing depends on available inputs. |

### Person Enrichment
| Operation ID | Provider(s) | What it does |
|---|---|---|
| `person.enrich.profile` | Prospeo → (AmpleLeads if `include_work_history`) → LeadMagic | Full person profile: title, seniority, work history, education, skills, email, phone |

### Person Contact
| Operation ID | Provider(s) | What it does |
|---|---|---|
| `person.contact.resolve_email` | LeadMagic → Icypeas → Parallel | Find and verify work email |
| `person.contact.verify_email` | MillionVerifier → Reoon | Verify an existing email |
| `person.contact.resolve_mobile_phone` | LeadMagic → BlitzAPI | Find mobile phone number |

---

## Providers (16)

| Provider | Adapter File | Used By |
|---|---|---|
| Prospeo | `app/providers/prospeo.py` | Company enrich, company search, person search, person enrich |
| BlitzAPI | `app/providers/blitzapi.py` | Company enrich, company search, person search (Employee Finder + Waterfall ICP), phone |
| CompanyEnrich | `app/providers/companyenrich.py` | Company enrich, company search, person search |
| LeadMagic | `app/providers/leadmagic.py` | Company enrich, email resolution, phone, person search (Employee Finder + Role Finder), technographics, person enrich |
| Icypeas | `app/providers/icypeas.py` | Email resolution (async polling, fallback) |
| MillionVerifier | `app/providers/millionverifier.py` | Email verification |
| Reoon | `app/providers/reoon.py` | Email verification (fallback) |
| Parallel AI | `app/providers/parallel_ai.py` | Email resolution (fallback) |
| Adyntel | `app/providers/adyntel.py` | LinkedIn/Meta/Google ads search |
| Gemini | `app/providers/gemini.py` | G2 URL, pricing page URL resolution |
| OpenAI | `app/providers/openai_provider.py` | Research operation fallback |
| AmpleLeads | `app/providers/ampleleads.py` | Person enrich (full work history) |
| StoreLeads (enrich) | `app/providers/storeleads_enrich.py` | Ecommerce store enrichment |
| StoreLeads (search) | `app/providers/storeleads_search.py` | Ecommerce store discovery |
| Enigma | `app/providers/enigma.py` | Card transaction revenue (GraphQL) |
| RevenueInfra | `app/providers/revenueinfra/` | Pricing intelligence (14 endpoints), competitors, customers, champions, alumni, VC funding, similar companies |

---

## Modal Micro-Operations (19 endpoints)

Deployed at `https://bencrane--data-engine-x-micro-fastapi-app.modal.run`

Parallel.ai-backed functions for fallback data resolution. Each wraps a Parallel.ai task spec with submit → poll → return lifecycle.

**Company (11):**
- Find company LinkedIn URL (by domain, by name+domain)
- Find company name (by domain, by LinkedIn URL)
- Find company domain (by LinkedIn URL, by name+LinkedIn URL)
- Find company description (by domain, by name+domain)
- Find company HQ location (by domain, by name+domain)
- Find company employee range (by name+domain+LinkedIn URL)

**Person (8):**
- Find person LinkedIn URL (by name+company, by name+company+domain)
- Find person work email (4 variants with different input combos)
- Find person email+LinkedIn URL (2 variants)
- Find person location (by name+LinkedIn URL)

Auth: `Authorization: Bearer <MODAL_INTERNAL_AUTH_KEY>` on all endpoints.

---

## Database Schema (Migrations 001-010)

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

---

## API Endpoints

### Tenant Operations
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/execute` | Execute a single operation |
| POST | `/api/v1/batch/submit` | Submit a batch of entities against a blueprint |
| POST | `/api/v1/batch/status` | Poll batch execution status (recursive tree) |
| POST | `/api/v1/entities/companies` | Query company entity state |
| POST | `/api/v1/entities/persons` | Query person entity state |
| POST | `/api/v1/entities/timeline` | Query entity operation timeline |
| POST | `/api/auth/login` | Tenant JWT login |
| POST | `/api/auth/me` | Verify auth |
| POST | `/api/blueprints/create` | Create blueprint (operation-native) |
| POST | `/api/blueprints/list` | List blueprints |
| POST | `/api/blueprints/get` | Get blueprint |
| POST | `/api/blueprints/update` | Update blueprint |
| POST | `/api/companies/list` | List companies |
| POST | `/api/companies/get` | Get company |
| POST | `/api/steps/list` | List steps |
| POST | `/api/steps/get` | Get step |
| POST | `/api/users/list` | List users |
| POST | `/api/users/get` | Get user |
| POST | `/api/submissions/list` | List submissions |
| POST | `/api/submissions/get` | Get submission |

### Super-Admin
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/super-admin/login` | Super-admin JWT login |
| POST | `/api/super-admin/orgs/create\|list\|get\|update` | Org CRUD |
| POST | `/api/super-admin/companies/create\|list\|get` | Company CRUD |
| POST | `/api/super-admin/users/create\|list\|get\|deactivate` | User CRUD |
| POST | `/api/super-admin/api-tokens/create\|list\|revoke` | Token management |
| POST | `/api/super-admin/blueprints/create\|list\|get\|update` | Blueprint CRUD (supports operation_id) |
| POST | `/api/super-admin/steps/register\|list\|get\|update\|deactivate` | Step registry |

### Internal (Trigger.dev → FastAPI)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/internal/pipeline-runs/get` | Fetch run + snapshot |
| POST | `/api/internal/pipeline-runs/update-status` | Update run status |
| POST | `/api/internal/pipeline-runs/fan-out` | Create child runs from fan-out results |
| POST | `/api/internal/step-results/update` | Update step result |
| POST | `/api/internal/step-results/mark-remaining-skipped` | Skip remaining steps |
| POST | `/api/internal/submissions/sync-status` | Sync submission status from run aggregate |
| POST | `/api/internal/entity-state/upsert` | Persist entity state on run completion |

---

## Directory Structure

```
app/
  auth/                  # AuthContext, JWT, API token, super-admin auth
  config.py              # Pydantic settings (no env prefix, Doppler-compatible)
  database.py            # Supabase client
  main.py                # FastAPI app, router mounting
  contracts/             # Pydantic output schemas per operation group
  models/                # DB models
  providers/             # One file per provider (or package for RevenueInfra)
    revenueinfra/        # Package: _common.py, pricing.py, competitors.py, customers.py, champions.py, alumni.py, vc_funding.py, similar_companies.py
  routers/               # API endpoints
    execute_v1.py        # /api/v1/execute, batch/submit, batch/status
    entities_v1.py       # /api/v1/entities/*
    internal.py          # /api/internal/* (Trigger callbacks)
    tenant_*.py          # Tenant CRUD endpoints
    super_admin_*.py     # Super-admin endpoints
  services/              # Operation logic
    email_operations.py
    search_operations.py
    company_operations.py
    research_operations.py
    adyntel_operations.py
    pricing_intelligence_operations.py
    person_enrich_operations.py
    operation_history.py
    entity_state.py
    entity_timeline.py
    submission_flow.py   # Batch creation, fan-out child creation
    trigger.py           # Trigger.dev HTTP client
  utils/
trigger/
  src/
    tasks/
      run-pipeline.ts    # Pipeline orchestrator (fan-out, conditions, context chaining)
    utils/
      evaluate-condition.ts  # Condition evaluator for step gating
modal/
  app.py                 # 19 Parallel.ai micro-function endpoints
supabase/
  migrations/            # 001-010 SQL migrations
scripts/
  smoke_test_batch.py    # Operator E2E validation tool
tests/                   # 50+ pytest tests (contracts, operations, hardening, flow)
docs/
  ARCHITECTURE.md
  AGENT_HANDOFF.md
  STRATEGIC_DIRECTIVE.md
  ENTITY_INTELLIGENCE_ARCHITECTURE.md
  EXPORT_CONTRACT_V1.md
  CONDITION_SCHEMA.md
  NESTED_FAN_OUT_TRACE.md
  PROPOSED_WORKSTREAMS.md
  POSTMORTEM_*.md
  SYSTEM_OVERVIEW.md     # This file
  api-reference-docs/    # Provider API documentation
Dockerfile               # Doppler CLI + FastAPI
railway.toml             # Railway deployment config
```

---

## Environment / Secrets

All secrets managed via Doppler. Railway container runs `doppler run -- uvicorn app.main:app`. Only `DOPPLER_TOKEN` is set in Railway directly.

No `DATA_ENGINE_` prefix on env vars. Config reads directly: `API_URL`, `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `INTERNAL_API_KEY`, `JWT_SECRET`, `SUPER_ADMIN_JWT_SECRET`, `SUPER_ADMIN_API_KEY`, `TRIGGER_SECRET_KEY`, `TRIGGER_PROJECT_ID`, plus all provider API keys.

Trigger.dev environment has its own vars: `DATA_ENGINE_API_URL` and `DATA_ENGINE_INTERNAL_API_KEY` (these keep the prefix because Trigger.dev is a separate runtime).

---

## Canonical Contracts

Every operation has a Pydantic output model in `app/contracts/`. These are validated at runtime via `Model.model_validate(...).model_dump()` — if a provider response doesn't match, it fails with a structured error, never a 500.

Contract files:
- `person_contact.py` — email, verify, phone outputs
- `search.py` — company search, person search, ecommerce search outputs
- `company_enrich.py` — profile, technographics, ecommerce, card revenue outputs
- `company_research.py` — G2, pricing URL, competitors, customers, champions, alumni, VC funding, similar companies outputs
- `company_ads.py` — LinkedIn, Meta, Google ads outputs
- `pricing_intelligence.py` — 14-field pricing analysis output
- `person_enrich.py` — full person profile output

---

## Testing

50+ tests in `tests/`. Run with `uv run --with pytest --with pytest-asyncio pytest` or install deps and use `pytest` directly.

Test categories:
- **Contract tests**: valid/invalid schema validation for all output models
- **Operation hardening tests**: every operation handles noisy rich context input without crashing
- **Flow tests**: batch creation, fan-out child creation, entity state merge/version logic
- **Provider routing tests**: person.search canonical input routing, conditional step behavior
- **Operation-specific tests**: per-operation success/failure/missing-input scenarios

---

## Key Design Decisions

1. **All endpoints are POST** — even queries. Convention from day 1.
2. **Provider order is config-driven for some, hardcoded for others.** Email resolution order is hardcoded (LeadMagic → Icypeas → Parallel). Company enrichment order is env-driven.
3. **Operations are waterfall unless explicitly merge-accumulate.** `company.enrich.profile` is the exception — it merges across providers. Everything else stops on first success.
4. **The pipeline runner lives in TypeScript (Trigger.dev), operations live in Python (FastAPI).** The boundary is HTTP. The runner calls `/api/v1/execute` for each step.
5. **Entity identity is deterministic.** UUIDv5 from natural keys ensures the same company/person always gets the same entity_id regardless of which pipeline produced it.
6. **Fan-out is generic.** Any step that returns a `results` array can fan out. The mechanism doesn't know if results are people, companies, or anything else.
7. **Conditions are evaluated in the runner, not the API.** The FastAPI layer doesn't know about conditions — it just executes operations. The Trigger.dev runner decides whether to call.

---

## Build History (Phases)

| Phase | What was built |
|---|---|
| 1: Cleanup + Structure | Dead code removal, provider extraction into `app/providers/`, canonical output contracts |
| 2: Batch Orchestration | Blueprint evolution (operation_id), batch submit/status endpoints, pipeline runner bridge |
| 3: Entity State + Tests | Entity tables, accumulation service, identity resolution, query endpoints, 26 initial tests |
| 4: Docs + Deploy Readiness | Documentation refresh, config hardening, migration manifest, smoke test script |
| 5: Live Testing + Fixes | Doppler integration, Dockerfile, super-admin API key auth, output flattening, research operation fixes |
| 6: Fan-Out | Entity timeline, fan-out schema/runner/endpoints, child run creation, batch status tree |
| 7: Provider Audit | All 11 provider adapters audited against API docs, 13 mismatches fixed |
| 8: Operation Hardening | All operations hardened against rich cumulative context inputs, 9 hardening tests added |
| 9: Person Enrich Profile | AmpleLeads adapter, person enrich operation with work_history flag, Prospeo → AmpleLeads → LeadMagic waterfall |
| 10: Modal Micro-Functions | Modal app scaffold, 19 Parallel.ai endpoints deployed, submit → poll → return lifecycle |
| 11: RevenueInfra Operations | Pricing intelligence (14 endpoints), competitors, customers, champions, champion testimonials, alumni, VC funding, similar companies |
| 12: Person Search Upgrade | Canonical input fields, LeadMagic Employee Finder + Role Finder, BlitzAPI Employee Finder + Waterfall ICP, provider routing by intent |
| 13: StoreLeads + Enigma | Ecommerce enrich, ecommerce search (StoreLeads), card revenue (Enigma GraphQL) |
| 14: Conditional Execution | Condition schema, evaluator utility, runner integration, skip-by-condition semantics |
| 15: Nested Fan-Out | Verified recursive fan-out, recursive batch status tree, depth-agnostic submission sync |

---

## What's Not Built Yet

- **Entity deduplication across runs** — skip enrichment if person already exists with recent data
- **Operation registry metadata** — formal declaration of inputs/outputs per operation for auto-assembly
- **AI blueprint assembler** — natural language → blueprint JSON
- **Output delivery** — export to CRM, campaign tool, webhook, CSV
- **Input ingestion** — CRM pull, CSV upload validation, auto-derived input requirements
- **Per-step timeline events** — timeline currently captures upsert + fan-out discovery, not every intermediate step
- **Page content extraction** — scraping G2/pricing pages for structured intelligence (endpoints exist in HQ, not yet wired)
- **`company.resolve.identity`** — normalize messy input (name → domain, etc.)

---

## Operational Notes

- **Deploy flow**: `git push origin main` → Railway auto-deploys. Trigger.dev requires separate `cd trigger && npx trigger.dev@latest deploy`. Modal requires `cd modal && modal deploy app.py`.
- **Migrations**: Run manually via `psql "$DATABASE_URL" -f supabase/migrations/0XX_*.sql`. Idempotent where possible.
- **Key rotation**: All secrets in Doppler. Rotate there, next Railway deploy picks up new values. Trigger.dev vars are separate.
- **Postmortems**: Two postmortems exist documenting agent execution discipline failures. Read them before operating.
