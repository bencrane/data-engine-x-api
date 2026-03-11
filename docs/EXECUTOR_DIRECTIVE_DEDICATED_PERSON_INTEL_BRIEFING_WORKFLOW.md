# Directive: Dedicated Person Intel Briefing Workflow

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** This is the third and final Parallel.ai workflow. The ICP job titles workflow established the polling utility, prompt extraction pattern, and confirmed dual-write contract. The company intel briefing workflow proved the pattern works for client-scoped briefings. This directive builds the person variant — a deep research briefing about a specific person, framed through a client lens for outbound sales preparation.

The dedicated table (`person_intel_briefings`) is proven healthy in production with `1` row matching `1` successful upstream step. The Trigger-direct operation `person.derive.intel_briefing` has been called twice in production with 1 failure.

---

## The Problem

A person (identified by LinkedIn URL, name, and/or title) and client context go in. A deep research intel briefing about that person comes out. The briefing is framed through the client's lens — what matters about this person for this client's outreach. The workflow calls Parallel.ai directly, polls for completion using the shared polling utility, and persists the result to both entity state and the `person_intel_briefings` dedicated table with confirmed writes.

---

## Architectural Constraints

1. **New Trigger.dev task in `trigger/src/tasks/`.** Does NOT modify `run-pipeline.ts`.

2. **Reuse the Parallel.ai polling utility.** Same utility used by ICP job titles and company intel briefing. Do not create another polling implementation.

3. **Extract the person intel briefing prompt into a standalone file.** Follow the same prompt extraction pattern as the ICP job titles and company intel briefing workflows. The prompt currently lives in `run-pipeline.ts`. Do NOT modify `run-pipeline.ts`.

4. **Parallel.ai is called directly from Trigger.dev, not through FastAPI.** `PARALLEL_API_KEY` is in Trigger.dev env vars.

5. **Persist to both entity state and `person_intel_briefings` dedicated table.** Both writes must be confirmed. The dedicated table upsert goes through `POST /api/internal/person-intel-briefings/upsert`. Both endpoints exist and are healthy in production.

6. **Write to the `entities` schema.** Both target tables live in `entities` after the schema split. FastAPI handles schema-qualified queries.

7. **The briefing is client-scoped.** Same as the company briefing — the prompt and the persisted record are tied to both the target person and the client company. The workflow input must include client context.

8. **Person identity resolution uses LinkedIn URL as the primary natural key.** The entity state upsert endpoint resolves person identity deterministically. The workflow must pass sufficient person identifiers for resolution.

9. **Deploy protocol applies.** This directive does not include deployment. When deployed: Railway first, Trigger.dev second.

---

## Existing Code to Read Before Starting

- `CLAUDE.md` — project conventions, auth model, deploy protocol
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — person intel briefings auto-persist health (section 5), Trigger-direct operations (section 3: `person.derive.intel_briefing`, 2 executed, 1 failed)
- `trigger/src/tasks/run-pipeline.ts` — the existing person intel briefing implementation. Study the `executeParallelPersonBriefing` function (or equivalent block), the prompt, and the auto-persist block for `person_intel_briefings`. This is what you are rebuilding.
- `trigger/src/tasks/` — the company intel briefing workflow. This is the closest pattern to follow. The person variant should mirror its structure: prompt file, workflow task, confirmed dual writes, lineage tracking.
- `trigger/src/` — the shared utility modules, including the Parallel.ai polling utility and prompt files
- `app/routers/internal.py` — the `/api/internal/person-intel-briefings/upsert` endpoint (understand the expected request shape)
- `app/services/entity_state.py` — person entity identity resolution (LinkedIn URL as primary natural key)
- `supabase/migrations/016_intel_briefing_tables.sql` — the `person_intel_briefings` table schema

---

## Deliverable 1: Person Intel Briefing Prompt Extraction

Extract the person intel briefing prompt from `run-pipeline.ts` into a standalone file alongside the existing prompt files. Follow the same pattern. The prompt takes person context (name, title, LinkedIn URL, company) and client context as inputs. Do NOT modify `run-pipeline.ts`.

Commit standalone.

---

## Deliverable 2: Person Intel Briefing Workflow Task

Create a new Trigger.dev task in `trigger/src/tasks/` that produces a person intel briefing.

**Input:** At minimum, person identifiers (LinkedIn URL and/or name + title + company), client context (client company name, domain, description), and org/company context for auth. You decide the full input shape.

**Behavior:**
- Build the prompt using the template from Deliverable 1 and the provided person + client context
- Call Parallel.ai deep research using the shared polling utility
- On success, persist to both entity state and the `person_intel_briefings` dedicated table with confirmed writes
- Track lineage through `pipeline_runs` and `step_results`

**Persistence:** Both writes must be confirmed. Same contract as the company intel briefing workflow.

Commit standalone.

---

## Deliverable 3: Tests

Write tests that verify:
- The prompt template produces a valid prompt given person and client inputs
- The workflow uses the shared polling utility (not a custom polling loop)
- The workflow persists to both entity state and `person_intel_briefings` with confirmed writes
- A failed persistence write is surfaced, not swallowed
- Person identity fields (LinkedIn URL) are passed through for entity resolution

Mock all HTTP calls. Do not call production or Parallel.ai.

Commit standalone.

---

## What is NOT in scope

- No modifications to `run-pipeline.ts`
- No modifications to FastAPI endpoints
- No modifications to the Parallel.ai polling utility (unless a bug is found — report it)
- No modifications to the company intel briefing or ICP job titles workflows
- No database migrations
- No deploy commands

## Commit convention

Each deliverable is one commit. Do not push.

## Deploy protocol reminder

When this work is eventually deployed: Railway first (wait for it to be live), Trigger.dev second. The person intel briefings upsert endpoint must exist on FastAPI before the workflow runs. `PARALLEL_API_KEY` must be set in Trigger.dev env vars (it already is in production).

## When done

Report back with:
(a) Prompt file location and how person + client context is templated into the prompt
(b) Confirm the shared polling utility was reused with no custom polling logic
(c) How confirmed writes work for the dual-write path (entity state + person_intel_briefings)
(d) The input shape — what person identity fields and client context fields are required
(e) How this workflow differs from the company intel briefing workflow (beyond prompt, input shape, and persistence target)
(f) Test count and what they cover
(g) Anything to flag — whether all three Parallel.ai workflows now share a consistent pattern, any remaining divergence, suggestions for consolidation
