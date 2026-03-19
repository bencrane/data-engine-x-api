# Executor Directive: Enigma Integration Audit

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** Enigma is one of several third-party data providers integrated into the platform. The Enigma API documentation in the repo is extensive (30+ files covering GraphQL queries, KYB verification, screening, growth/GTM solutions, and MCP integration), but it's unclear how much of that API surface is actually implemented, wired into the execution pipeline, and callable in production. This audit maps the gap between what's documented and what's built, so we can make informed decisions about expanding or pruning the integration.

---

## Existing code to read

Before writing anything, read these files carefully. **Every claim in the audit must be grounded in what the code actually contains**, not what docs say should exist.

### Enigma API reference documentation

Read all files under `docs/api-reference-docs/enigma/`. These document the full Enigma API surface. The key sections are:

- `03-growth-and-gtm-solutions/` — business search, list enrichment, lead qualification, lead list building, market assessment. These are the most relevant to data-engine-x's use case.
- `06-query-enigma-with-graphql/` — the GraphQL API reference, quickstart, search patterns, aggregate queries. This is the API layer the existing adapter uses.
- `02-verification-and-kyb/` — Know Your Business verification packages. May or may not be relevant to current use cases.
- `05-screening/` — customer screening endpoints. May or may not be relevant.
- `08-reference/` — data attribute reference and GraphQL API reference. Essential for understanding what data Enigma can return.
- `04-resources/` — rate limits, pricing/credit use, card revenue evaluation. Important for understanding operational constraints.

### Provider adapter

- `app/providers/enigma.py` — the main Enigma provider adapter. Read every function. Document what GraphQL queries it sends, what Enigma endpoint it hits, what inputs it expects, and what it returns. Pay attention to:
  - The `search_brand()` / `match_business()` function (brand matching by name/domain)
  - The `get_card_analytics()` function (card revenue data retrieval)
  - Any other functions that exist or are stubbed out
  - The GraphQL query strings embedded in the code
  - Error handling patterns

### Contracts and output models

- `app/contracts/company_enrich.py` — find the `CardRevenueOutput` model and any other Enigma-related Pydantic models. Document the output shape.

### Operation service

- `app/services/company_operations.py` — find the `execute_company_enrich_card_revenue` function. Trace how it calls the Enigma adapter, what inputs it passes, and how it transforms the response into the canonical output.

### Execute router (operation wiring)

- `app/routers/execute_v1.py` — confirm that `company.enrich.card_revenue` is in `SUPPORTED_OPERATION_IDS` (it is, at line 158). Check for any other Enigma-related operation IDs. Trace the dispatch logic at line 615-616.

### Configuration

- `app/config.py` — find the `enigma_api_key` setting. Note how it's loaded (env var name, default, required/optional).

### Trigger.dev integration

- Search `trigger/src/tasks/` and `trigger/src/workflows/` for any references to `enigma`, `card_revenue`, or `company.enrich.card_revenue`. Note: the exploration agent found zero Trigger.dev references to Enigma. Confirm this independently.

### Existing directives and tests

- `docs/EXECUTOR_DIRECTIVE_ENIGMA_LOCATIONS.md` — a directive that scopes a `company.enrich.locations` operation using Enigma's location data. Read it to understand what's planned but not built.
- `tests/test_card_revenue.py` — test suite for the card revenue operation.
- `tests/test_enigma_locations.py` — test for the locations operation (may be a stub or may contain implementation tests for a not-yet-built feature).

### Production usage

- `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md` (if it exists by the time you run) or `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — check the "never called in production" operations list. Has `company.enrich.card_revenue` ever been called? Has `company.enrich.locations` ever been called?

---

## Deliverable 1: Enigma Integration Audit Document

Create `docs/ENIGMA_INTEGRATION_AUDIT.md`.

Add a last-updated timestamp at the top:

```markdown
# Enigma Integration Audit

**Last updated:** 2026-03-18T[HH:MM:SS]Z
```

Use the actual UTC time when you finish writing.

### Required sections

---

#### Section 1: Enigma API Surface (What's Documented)

List every Enigma API capability documented in `docs/api-reference-docs/enigma/`. Organize by category:

| Category | Capability | Documented In | API Type |
|---|---|---|---|
| Growth/GTM | Search for a specific business | `03-growth-and-gtm-solutions/01-...` | GraphQL |
| Growth/GTM | Enrich customer/prospect lists | `03-growth-and-gtm-solutions/02-...` | GraphQL |
| Growth/GTM | Qualify an inbound lead | `03-growth-and-gtm-solutions/03-...` | GraphQL |
| Growth/GTM | Build targeted lead lists | `03-growth-and-gtm-solutions/04-...` | GraphQL |
| Growth/GTM | Assess market position | `03-growth-and-gtm-solutions/05-...` | GraphQL |
| KYB | KYB verification packages | `02-verification-and-kyb/...` | REST/GraphQL |
| Screening | Customer screening | `05-screening/...` | REST |
| Data | Card revenue evaluation | `04-resources/04-...` | GraphQL |
| ... | ... | ... | ... |

For each capability, note the specific GraphQL queries or REST endpoints documented (e.g., `search(searchInput: ...)`, `verify(...)`, etc.).

---

#### Section 2: What's Built (Provider Adapter Inventory)

Document every function in `app/providers/enigma.py`:

| Function | What It Does | Enigma Endpoint | GraphQL Query | Inputs | Returns |
|---|---|---|---|---|---|
| `search_brand()` or `match_business()` | ... | `POST /graphql` | `search(searchInput: ...)` | ... | ... |
| `get_card_analytics()` | ... | `POST /graphql` | ... | ... | ... |
| ... | ... | ... | ... | ... | ... |

For each function, note:
- Is it complete and tested, or stubbed out?
- What error handling does it have?
- What rate limiting or retry logic exists?

---

#### Section 3: What's Wired (Operation Pipeline Integration)

| Operation ID | In SUPPORTED_OPERATION_IDS? | Service Function | Provider Function | Callable via /execute? | Used in Blueprints? | Called in Production? |
|---|---|---|---|---|---|---|
| `company.enrich.card_revenue` | Yes | `execute_company_enrich_card_revenue` | `enigma.search_brand` + `enigma.get_card_analytics` | Yes | ? | ? |
| `company.enrich.locations` | ? | ? | ? | ? | ? | ? |

Trace the full call chain for each Enigma-related operation: execute_v1.py dispatch → service function → provider adapter → Enigma API.

---

#### Section 4: Trigger.dev Integration

- Are any Enigma operations referenced in Trigger.dev task files or workflows?
- Is Enigma used in any blueprint definitions (check `docs/blueprints/` for any blueprints that include Enigma operation IDs)?
- Is Enigma used in any dedicated workflow files?
- Is there any scheduled/automated Enigma data collection?

If the answer to all of these is "no," state that clearly. Enigma is currently only reachable via ad-hoc `/api/v1/execute` calls.

---

#### Section 5: Gap Analysis

The core deliverable. Compare what's documented against what's built.

##### Documented but not built

For each Enigma API capability in Section 1 that has no corresponding provider adapter or operation:

| Capability | Enigma API | Status | Notes |
|---|---|---|---|
| Business search | `search(searchInput: ...)` | Partially built | `search_brand()` exists but only for brand matching, not general business search |
| Lead list building | aggregate/filter queries | Not built | No adapter for Enigma aggregate queries |
| KYB verification | `verify(...)` | Not built | No adapter, no operation |
| Customer screening | REST endpoints | Not built | No adapter, no operation |
| ... | ... | ... | ... |

##### Built but not wired

Any provider adapter functions that exist but are not reachable through an operation in `execute_v1.py`.

##### Wired but never called

Cross-reference against the operational reality check's never-called operations list.

##### Planned but not built

Document the `company.enrich.locations` directive — what it scopes, whether any code exists for it yet (check if `tests/test_enigma_locations.py` contains real tests or just stubs).

---

#### Section 6: Credential & Configuration Status

| Setting | Env Var Name | Configured In | Present in Production? | Notes |
|---|---|---|---|---|
| Enigma API key | `ENIGMA_API_KEY` (or whatever `app/config.py` uses) | Doppler / env | ? | Check if it's referenced in Doppler config names |

Note: the executor cannot verify Doppler production secrets, but can confirm:
- The env var name from `app/config.py`
- Whether the code has a default/fallback if the key is missing
- Whether there are any references to Enigma keys in Docker/Railway config files

---

#### Section 7: Rate Limits & Credit Considerations

Summarize from `docs/api-reference-docs/enigma/04-resources/`:
- What are Enigma's rate limits?
- What is the credit/pricing model?
- Are there per-query costs that would affect production usage at scale?

This section is informational — just extract the key facts from the reference docs.

---

#### Section 8: Recommendations (Informational Only)

Based on the gap analysis, categorize the undocumented capabilities into:

1. **High-value, low-effort** — capabilities where the adapter pattern already exists and extending it would be straightforward (e.g., locations if the directive is already scoped)
2. **High-value, medium-effort** — capabilities that would require new adapter functions and operations but address clear use cases (e.g., business enrichment, lead qualification)
3. **Low-priority** — capabilities that don't align with current workstreams (e.g., KYB verification, screening)
4. **Not applicable** — capabilities documented in the API reference that don't fit data-engine-x's architecture (e.g., MCP integration — the repo is a backend, not an AI assistant)

**Do not implement any recommendations.** This section is informational for the chief agent.

---

### Evidence standard

- Every "built" claim must reference a specific file and function name.
- Every "not built" claim must be supported by a search showing no matching code exists.
- Every "wired" claim must trace the dispatch path from `execute_v1.py` to the provider adapter.
- Every "called in production" claim must come from the operational reality check or be marked as "unknown — check operational reality check."
- If the executor cannot determine something (e.g., whether a Doppler secret exists), state what's unknown and why.

Commit standalone.

---

## Deliverable 2: Work Log Entry

Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file.

Summary should note: created `docs/ENIGMA_INTEGRATION_AUDIT.md` covering Enigma API surface inventory, provider adapter analysis, operation wiring, Trigger.dev integration status, gap analysis (documented vs built vs wired vs called), credential configuration, rate limits, and recommendations. Note the key finding: how many documented capabilities are implemented vs not.

Add a last-updated timestamp at the top of each file you create or modify, in the format `**Last updated:** 2026-03-18T[HH:MM:SS]Z`.

Commit standalone.

---

## What is NOT in scope

- **No code changes.** This is a documentation-only directive.
- **No new adapters, operations, or services.** Document the gaps, do not fill them.
- **No deploy commands.** Do not push.
- **No changes to existing documentation files.** Only create the new audit doc and append to the work log.
- **No changes to `CLAUDE.md`.** The chief agent will decide if/when to reference the audit.
- **No testing or calling the Enigma API.** This is a code audit, not a live integration test. Do not make any API calls to Enigma.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Audit doc: full path, section count
(b) API surface: total Enigma capabilities documented in the reference docs
(c) Built: number of provider adapter functions, number of operations wired into execute pipeline
(d) Gap summary: number of documented capabilities with no adapter, number of adapters with no operation, number of operations never called
(e) Trigger.dev: whether any Trigger.dev integration exists (yes/no)
(f) Credentials: env var name, whether it appears to be configured
(g) Anything to flag — especially: dead code, stale adapters that call deprecated Enigma endpoints, test files for features that don't exist yet, or discrepancies between the API reference docs and the actual Enigma API (if detectable from the code)
