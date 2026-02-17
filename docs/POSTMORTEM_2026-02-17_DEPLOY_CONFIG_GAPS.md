# Postmortem: Incomplete Deploy Configuration Guidance

Date: 2026-02-17
Repo: `data-engine-x-api`
Severity: High process failure
Status: Corrective behavior applied immediately

## Core Issue

The overseeing agent had full knowledge of the system's runtime dependencies — which env vars are required, where they need to be set (Railway vs Trigger.dev), and which are needed for provider operations vs infrastructure auth. It failed to surface this as a complete checklist before the operator attempted live testing. The operator discovered missing configuration through runtime failures instead of upfront guidance.

## What Happened

1. Operator completed all build phases and was ready for first live end-to-end test.
2. Agent provided a deploy checklist (steps 1-7) but omitted provider API keys entirely.
3. Operator set infrastructure vars (internal API key, API URL, Trigger secret) correctly.
4. Operator submitted a live batch. Pipeline runs triggered but enrichment returned empty — all providers skipped due to missing API keys in Railway.
5. Debugging revealed `company_profile: null`, `source_providers: []` — zero provider keys were set.
6. Additional time lost on Trigger.dev `tr_dev_` vs `tr_prod_` secret key mismatch — also not caught proactively.
7. Operator had to context-switch from product testing to infrastructure debugging multiple times.

## Impact

- ~30 minutes of wasted operator time
- Momentum killed during the highest-energy moment (first live test)
- Trust erosion in agent's operational completeness
- Context-switching from "is my product working" to "why aren't my env vars set"

## Root Cause

The agent knew the full env var inventory (it exists in `.env.example`, `app/config.py`, and was documented in the Phase 4 deliverables). It failed to translate that knowledge into an actionable pre-deploy checklist at the moment the operator needed it — before step 1, not after step 7 failed.

Secondary: the agent treated Trigger.dev dev vs prod secret keys as something the operator would know, rather than flagging the `tr_dev_` prefix as an obvious mismatch during the deploy steps.

## Non-Negotiable Operating Rules (Additive)

1. Before any deploy or live test, provide a complete environment configuration checklist — every required var, where it goes (Railway / Trigger.dev / both), and what happens if it's missing.
2. Do not assume the operator knows which vars are infrastructure vs provider vs runtime. Be explicit.
3. If the agent has seen credentials or config in context, proactively verify completeness before the operator runs into a wall.
4. When providing deploy steps, the first step is always: "verify all required env vars are set in all runtimes." Not the last step. Not after failure.

## What Should Have Happened

Before the operator began testing, the agent should have provided:

```
Before you test, verify these Railway env vars are set:

Infrastructure (required):
- DATA_ENGINE_API_URL
- DATA_ENGINE_DATABASE_URL
- DATA_ENGINE_SUPABASE_URL
- DATA_ENGINE_SUPABASE_SERVICE_KEY
- DATA_ENGINE_INTERNAL_API_KEY
- DATA_ENGINE_JWT_SECRET
- DATA_ENGINE_SUPER_ADMIN_JWT_SECRET
- DATA_ENGINE_SUPER_ADMIN_API_KEY
- DATA_ENGINE_TRIGGER_SECRET_KEY (must be tr_prod_*, not tr_dev_*)
- DATA_ENGINE_TRIGGER_PROJECT_ID

Provider keys (at least one per operation you want to test):
- DATA_ENGINE_PROSPEO_API_KEY (company enrich, search)
- DATA_ENGINE_BLITZAPI_API_KEY (company enrich, search, phone)
- DATA_ENGINE_COMPANYENRICH_API_KEY (company enrich, search)
- DATA_ENGINE_LEADMAGIC_API_KEY (company enrich, email, phone)
- DATA_ENGINE_GEMINI_API_KEY (research operations)
- DATA_ENGINE_OPENAI_API_KEY (research fallback)
- [others as needed]

Trigger.dev env vars (Production environment):
- DATA_ENGINE_API_URL
- DATA_ENGINE_INTERNAL_API_KEY
```

This would have taken 30 seconds to write and saved 30 minutes of debugging.

## Accountability

Responsibility sits with the overseeing agent. The operator's job is product decisions and direction. The agent's job is operational completeness. This was an operational completeness failure.
