**Bug Fix Directive: `query_leads` RPC Schema Routing (BLOCKING)**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting. You just completed the directive in `docs/EXECUTOR_DIRECTIVE_BACKFILL_ENTITY_RELATIONSHIPS_AND_LEADS_QUERY.md`. This is a follow-up fix to work you already built.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Severity: BLOCKING runtime defect.** The leads query endpoint will 500 on every request until this is fixed.

---

**The problem:**

The migration `supabase/migrations/028_leads_query_function.sql` correctly creates the function as `entities.query_leads(...)` — migration 021 moved all entity tables into the `entities` schema, so the `entities.` prefix is correct.

However, `app/services/leads_query.py` calls `client.rpc("query_leads", ...)`. The `SchemaAwareSupabaseClient` in `app/database.py` auto-routes `.table()` calls to the correct schema, but `.rpc()` falls through via `__getattr__` to the raw Supabase client, which defaults to the `public` schema. PostgREST will not find `entities.query_leads` when called as `client.rpc("query_leads", ...)`.

The fix is a one-line change: route the RPC call through the `entities` schema explicitly.

---

**The fix:**

In `app/services/leads_query.py`, change the RPC call to route through the entities schema. Two acceptable approaches (use your judgment):

- `client.schema("entities").rpc("query_leads", rpc_params).execute()`
- Or: import `get_entities_client` from `app/database` and use `get_entities_client().rpc("query_leads", rpc_params).execute()`

**Existing code to read:**

- `app/services/leads_query.py` — the RPC call site (your prior work)
- `app/database.py` — `SchemaAwareSupabaseClient`, `get_entities_client()`, schema routing logic

---

**What is NOT in scope:**

- No changes to `028_leads_query_function.sql` — the migration is correct as written.
- No changes to the backfill script, endpoint, request model, or tests.
- No deploy commands.

**Commit convention:** One commit for the fix. Do not push.

**When done:** Report back with: (a) the exact line changed, (b) which schema routing approach you chose and why.
