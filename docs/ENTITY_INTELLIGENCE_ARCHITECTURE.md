# Entity Intelligence Architecture (data-engine-x-api)

## Purpose

This document defines the operating model for `data-engine-x-api` based on your stated aim:

- Everything in the system acts on either a `company` or a `person`.
- Provider APIs are implementation details, not core architecture.
- Contracts are fixed first; endpoint naming can evolve later.

---

## Core Principle

The system is an **Entity Intelligence Pipeline (EIP)**:

1. Fetch/resolve/enrich data for an entity (`company` or `person`)
2. Normalize provider outputs to canonical contracts
3. Persist raw and canonical records with lineage
4. Derive higher-order intelligence (scores, labels, routing signals)
5. Orchestrate operation execution via blueprints/workflows

The architecture is entity-first, contract-first, and provider-agnostic.

---

## Canonical Ontology

Use this hierarchy:

- **Pipeline**: End-to-end business process
- **Workflow**: Coherent execution slice inside a pipeline
- **Operation**: Typed unit of work against an entity (e.g. fetch, resolve, verify, derive, persist)
- **Action**: Concrete implementation of an operation (provider adapter or internal implementation)

Important distinction:

- `Operation` is abstract and stable.
- `Action` is concrete and replaceable.

Example:

- Operation: `company.enrich.profile`
- Actions: `prospeo.company_enrich`, `clearbit.company_enrich` (future), `internal.company_merge`

---

## Why Raw Storage Alone Is Not Enough

Storing raw provider payloads is required for audit/debug/replay, but not sufficient for product reliability.

Without canonical normalization:

- every downstream function must understand every provider schema,
- provider changes create widespread regressions,
- comparisons and quality checks become inconsistent.

Therefore:

- **Raw payload** = source-of-truth history
- **Canonical object** = source-of-truth behavior for the rest of the system

---

## Adapter, Derive, Persist (Simple Model)

### Adapter

Adapter = translator from provider-specific shape to canonical shape.

- Input: canonical operation input
- External call: provider API
- Output: canonical operation output + raw payload

This should usually be a code module in the execution runtime, not a separate deployable service by default.

### Derive

Derive = compute new intelligence from canonical data.

- Examples: fit score, seniority bucket, data confidence, route priority
- Derive logic should be reusable; invocation policy can vary per workflow/blueprint

Derive is not a replacement for adapter.

### Persist

Persist writes data; it does not perform business interpretation.

- Writes raw payload, canonical output, lineage, run metadata
- Should not hide provider-to-canonical mapping rules

Rule: transform first (adapter/derive), write second (persist).

---

## Build Order Recommendation

1. **Lock contracts first**
   - `operation_id`
   - entity type (`company` or `person`)
   - strict input/output schema
   - error model
2. **Implement adapters/orchestrator against contracts**
3. **Persist raw + canonical + lineage**
4. **Add derive operations**
5. **Finalize endpoint naming**

Endpoint URLs are transport and can be renamed later.
Contracts are product-level commitments and expensive to change.

---

## Entity-Scoped Operation ID Pattern

Use consistent operation IDs:

- `company.resolve.identity`
- `company.enrich.profile`
- `company.signal.detect_ads`
- `person.resolve.identity`
- `person.contact.resolve_email`
- `person.verify.email_deliverability`
- `person.derive.priority_score`
- `company.persist.snapshot`
- `person.persist.snapshot`

Naming guidance:

- Prefix with entity (`company` or `person`)
- Use verb-domain semantics (`resolve`, `enrich`, `verify`, `derive`, `persist`)
- Avoid provider names in operation IDs

---

## Execution Pattern (Recommended Runtime Flow)

For each operation invocation:

1. Validate input against canonical contract
2. Select action (adapter) based on policy/priority/fallback
3. Execute action
4. Persist:
   - raw request/response
   - canonical mapped output
   - provider/action metadata
   - run lineage (`pipeline_run_id`, `workflow`, `operation_id`)
5. Optionally trigger derive operations
6. Return canonical output

This keeps provider coupling inside action modules and keeps orchestration deterministic.

---

## Blueprint/Workflow Relationship

- Blueprint stores execution intent (what operations should run, ordering, retry/fallback policy).
- Workflow executes that intent in runtime context.
- Derive logic can be global/reusable, while derive invocation (when/with-what-thresholds) is blueprint/workflow-scoped.

This separation avoids duplicate derive logic and still supports workflow-specific behavior.

---

## Anti-Patterns To Avoid

- Putting provider response parsing inside persistence layer
- Using provider field names as canonical contract fields
- Defining endpoints before operation contracts are stable
- Creating one-off provider-specific pipelines with no canonical layer
- Treating raw payload as directly usable downstream model

---

## What This Means For data-engine-x-api Now

Given the current FastAPI + Trigger.dev + Supabase stack:

- Keep FastAPI as auth, tenant boundary, contract validation, and orchestration trigger surface.
- Keep Trigger.dev as operation runner and retry/orchestration engine.
- Keep Supabase/Postgres as system of record for raw payloads, canonical entity state, and lineage.
- Shift step definitions toward operation/action semantics with explicit canonical contracts.

This aligns implementation with your goals: consistency, clarity, provider portability, and auditable entity intelligence execution.

