# Proposed Workstreams

Notes on upcoming development priorities and system behavior.

---

## 1. Input Contracts for Blueprints

### Current Gap

Neither of these exists today:
- Blueprints don't declare "this is the minimum input I need"
- There's no pre-processing pipeline to normalize messy CRM data into canonical identifiers

### Recommendation: Build the Input Contract First

Add a `required_input_fields` array to blueprints (e.g., `["company_domain"]` or `["linkedin_url", "first_name", "last_name"]`).

**How it works:**
- The batch submit endpoint validates each entity against the required fields before accepting the submission
- The frontend reads it and renders the appropriate form/upload columns

This is a small addition with high leverage.

### Normalization as an Operation, Not Infrastructure

The normalization pipeline ("I have a company name but no domain — go resolve it") should be implemented as a real operation (`company.resolve.identity`) that you add as step 1 of blueprints expecting messy input.

Build that as a new operation when needed, not as special infrastructure. It's just another step in the sequence.

---

## 2. Live Testing Sequence

Test the foundation before adding more on top. Here's the sequence:

1. **Verify Railway deploy landed** — check the deploy logs
2. **Run migrations 006 and 007** against your live Supabase database
3. **Set `DATA_ENGINE_INTERNAL_API_KEY`** in both Railway env vars and Trigger.dev env vars (generate a random secret, same value in both places)
4. **Set `DATA_ENGINE_API_URL`** in Trigger.dev env vars (your Railway URL)
5. **Deploy the updated Trigger.dev task** — `cd trigger && npx trigger.dev@latest deploy`
6. **Create an org + company + API token** via the super-admin API (or use existing ones from prior testing)
7. **Run the smoke test:**
   ```bash
   python3 scripts/smoke_test_batch.py --api-url <railway-url> --api-token <token>
   ```

The smoke test will create a blueprint, submit 3 companies (Stripe, Notion, Figma), run the pipeline, and verify entity state persistence. If it passes, the system works end-to-end. If it fails, you'll know exactly where.

> The entity enrichment log, the Enigma provider, the micro-operations — all of that is higher value after you've confirmed the pipeline actually executes against live APIs and persists real data.

---

## 3. Entity Tracking: Current State

### What's Tracked Today

Entity tracking exists at different levels of granularity:

#### Per Pipeline Run (Step-Level Tracking)

When an entity goes through a blueprint, each step creates a `step_results` row storing:

| Field | Description |
|-------|-------------|
| `status` | `queued` → `running` → `succeeded`/`failed`/`skipped` |
| `input_payload` | The cumulative context passed INTO this step |
| `output_payload` | Contains `operation_result` (full v1 execute response including `provider_attempts`) and `cumulative_context` (merged state after this step) |
| `error_message` / `error_details` | If the step failed |

For a given pipeline run, you can reconstruct exactly: what input each step saw, what it returned, which providers were tried, and the full accumulated state at each point.

#### Per Operation Execution (Provider-Level Tracking)

Every call to `POST /api/v1/execute` — whether standalone or via pipeline — writes to:

**`operation_runs`** — one row per operation invocation:
- `operation_id`, `status`, canonical input/output, org/company context, timing

**`operation_attempts`** — one row per provider attempt within that operation:
- Provider name, action, status, `http_status`, `skip_reason`, duration, raw response

Example: If `company.enrich.profile` tried Prospeo (found), Blitz (skipped), CompanyEnrich (skipped), LeadMagic (skipped) — you'd see 4 attempt rows with their individual statuses.

#### On the Entity Record (Summary-Level Only)

The `company_entities` / `person_entities` tables store:

| Field | Description |
|-------|-------------|
| `last_operation_id` | Which operation last wrote to this entity |
| `last_run_id` | Which pipeline run last wrote to this entity |
| `last_enriched_at` | Timestamp |
| `source_providers` | Accumulated list of providers that contributed data |
| `canonical_payload` | The full merged state |

### What's NOT Tracked

The entity record doesn't have a full audit trail of every operation that ever touched it. It knows what it is now and who last enriched it, but not "on Jan 15 Prospeo enriched it, on Jan 18 LeadMagic added the phone, on Jan 20 MillionVerifier verified the email."

That history exists — it's in `operation_runs` and `step_results` — but it's keyed by run, not by entity. To answer "what's the full enrichment history for stripe.com?", you'd need to query `operation_runs` by the entity's domain/identifier and join across runs.

### The Gap: Entity-Level Timeline

There's no `entity_enrichment_log` or similar table that provides a per-entity timeline view like:

```
stripe.com entity timeline:
  2026-02-16 14:00 — company.enrich.profile via prospeo (found: name, domain, industry)
  2026-02-16 14:01 — company.research.resolve_g2_url via gemini (found: g2.com/products/stripe)
  2026-02-16 14:02 — company.research.resolve_pricing_page_url via gemini (found: stripe.com/pricing)
```

This would be a useful addition — essentially an append-only log per entity, written alongside the entity state upsert. It maps directly to `dx_operation_events_v1` in the export contract, which is already defined but not yet implemented.

**Future consideration:** Worth adding if you want entity-level observability beyond "what's the current state." The data to build it already flows through the system — it just isn't being captured in an entity-indexed shape yet.
