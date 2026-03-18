# Writing Executor Directives

**Last updated:** 2026-03-18T07:00:00Z

How to write directives that executor agents can implement correctly without ambiguity.

Canonical-standard rule: this file is the directive-writing authority for the repo. If any older template or prior directive example conflicts with this file, this file wins.

Chief Agent grounding rule: before writing a directive, route yourself through `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md`, then the audited production-truth docs, then `CLAUDE.md`, and only then the workflow/doctrine docs.

Production-truth rule: example directives in this file show structure, not current production truth. Do not infer system health, feature completeness, or production readiness from example wording. Cross-check current reality in `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md`, `docs/DATA_ENGINE_X_ARCHITECTURE.md`, and `CLAUDE.md`.

Directive-status rule: existing `docs/EXECUTOR_DIRECTIVE_*.md` files are scope documents and format/style examples. They are not deployment records, not production verification, and not evidence that the described target architecture is live.

---

## What A Directive Is

A directive defines:

- the problem to solve
- the files and contracts the executor must understand
- the allowed scope
- the acceptance criteria
- the reporting requirements

A directive does not certify:

- that prior work was executed
- that prior work shipped
- that the described architecture is already in production
- that the repo's latest implementation matches the directive exactly

If you include current-state claims in a directive background section, tie them to the production-truth docs and date-scope them.

---

## Before You Draft

1. Start with `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md`.
2. Read `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md`, `docs/DATA_ENGINE_X_ARCHITECTURE.md`, and `CLAUDE.md`.
3. Use `docs/STRATEGIC_DIRECTIVE.md` and `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` only for doctrine and intended design.
4. Use `docs/SYSTEM_OVERVIEW.md` only as secondary technical reference if needed.
5. Use older `docs/EXECUTOR_DIRECTIVE_*.md` files for scope/style calibration, not as proof that the described state is live.

---

## Structure

Every directive follows this template:

```
**Directive: [Name]**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** [1-3 sentences on WHY this work matters]

**[API/endpoint details if applicable]**

**Existing code to read:** [List specific files]

---

### Deliverable 1: [Name]
[Exact instructions]
Commit standalone.

### Deliverable 2: [Name]
[Exact instructions]
Commit standalone.

[... more deliverables ...]

### Final Deliverable: Work Log Entry
Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file. This is your final commit.

---

**What is NOT in scope:** [Explicit exclusions]

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) ..., (b) ..., (c) ..., (d) ..., (e) anything to flag. The work log entry should be included in the executor's final commit.
```

---

## Rules

1. **List every file the agent should read before building.** Include full paths. Don't assume the agent knows where things are.

2. **Be explicit about what NOT to do.** "No deploy commands", "No database migrations", "Do not change existing operations" — state these clearly.

3. **One deliverable = one commit.** This keeps the work reviewable and revertable.

4. **"Do not push"** — the chief agent pushes after review. The executor never pushes.

5. **Include the API/endpoint shapes** when wiring external providers. Don't make the agent guess request/response formats.

6. **Specify file names for new files.** If two agents might work in parallel, give them different files to avoid conflicts. Example: `app/providers/storeleads_enrich.py` and `app/providers/storeleads_search.py`, not both in `app/providers/storeleads.py`.

7. **Always request a report.** The "When done" section tells the agent what to report so the chief can verify without reading every line of code.

8. **Do not use existing directives as status documents.** Use them for scope and style calibration only. If production status matters, cite the audited truth docs explicitly inside the directive.

9. **Keep the workflow docs aligned.** `docs/EXECUTOR_AGENT_DIRECTIVE.md` may be used as a convenience scaffold, but this file defines the standard template and wording.

10. **Every directive includes a work log entry as its final deliverable.** The executor appends to `docs/EXECUTOR_WORK_LOG.md` with the directive path, a 1-3 sentence summary, and any flags.

---

## Example: New Provider + Operation (Most Common Pattern)

```
**Directive: `company.research.lookup_alumni` Operation**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** [standard text]

**Background:** An external API at `api.revenueinfra.com` returns alumni data...

**The endpoint:**
POST https://api.revenueinfra.com/run/companies/db/alumni/lookup
Request: {"past_company_domain": "salesforce.com"}
Response: { "success": true, "alumni_count": 150, "alumni": [...] }

No auth required. Timeout: 30 seconds.

**Existing code to read:**
- `app/providers/revenueinfra/_common.py`
- `app/providers/revenueinfra/champions.py` (reference pattern)
- `app/providers/revenueinfra/__init__.py` (add re-export)
- `app/contracts/company_research.py` (add contract here)
- `app/services/research_operations.py` (add operation here)
- `app/routers/execute_v1.py` (wire in)

---

### Deliverable 1: Provider Adapter
Create `app/providers/revenueinfra/alumni.py`:
**`lookup_alumni(*, base_url, domain)`**
- Calls POST {base_url}/run/companies/db/alumni/lookup with {"past_company_domain": domain}
- [Handle cases: missing → skip, HTTP errors → failed, empty → not_found]
Update `__init__.py` to re-export.
Commit standalone.

### Deliverable 2: Canonical Contract
Add to `app/contracts/company_research.py` (do NOT overwrite existing):
[Exact Pydantic model definition]
Commit standalone.

### Deliverable 3: Service Operation
Add `execute_company_research_lookup_alumni(*, input_data: dict) -> dict` to `app/services/research_operations.py`.
Input: company_domain from cumulative context. Missing → failed.
Single provider call. Validate with contract. Flatten output.
Commit standalone.

### Deliverable 4: Wire Into Execute Router
Add to SUPPORTED_OPERATION_IDS + dispatch branch + persist_operation_execution.
Commit standalone.

### Deliverable 5: Tests
Add `tests/test_alumni.py`:
- [List specific test cases]
Mock all HTTP calls.
Commit standalone.

---

**What is NOT in scope:** No changes to other operations. No deploy commands. No migrations.

**When done:** Report back with: (a) adapter shape, (b) contract, (c) router wiring, (d) test count, (e) anything to flag.
```

---

## Example: Bug Fix Directive

```
**Bug Fix Directive: `person.search` 500 when called via pipeline**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**The problem:** [Exact error message and when it occurs]

**Investigation path:**
1. Read [specific file] — trace what happens when [specific input]
2. The crash is likely one of: [list candidates]
3. Compare against API docs at [specific doc path]

**Fix:** [What the fix should achieve, not how to implement it]

**Scope:** Fix in [specific files] only. Do not change other operations. Do not deploy.

**One commit. Do not push.**

**When done:** Report back with: (a) what caused the error, (b) what you fixed.
```

---

## Example: Infrastructure/Feature Directive

```
**Phase Directive: Conditional Step Execution**

**Context:** [standard]

**Background:** [WHY this matters — what it unlocks]

**Files to read before starting:** [list]

---

### Deliverable 1: Define the Schema
[Schema definition with examples]
Commit standalone.

### Deliverable 2: Core Logic
[Implementation details]
Commit standalone.

### Deliverable 3: Integration
[Where it plugs in]
Commit standalone.

### Deliverable 4: Tests
[Specific test cases]
Commit standalone.

---

**What is NOT in scope:** [explicit]
**When done:** Report back with: [specific items]
```

---

## Common Mistakes to Avoid

1. **Don't say "clean up whatever looks wrong"** — the agent will either do nothing or touch things it shouldn't. Be specific about what to change.

2. **Don't assume the agent knows the codebase.** Always list files to read. Even if it seems obvious.

3. **Don't combine unrelated work** in one directive. One directive = one coherent piece of work.

4. **Don't forget to specify where new files go.** "Create a provider adapter" is ambiguous. "Create `app/providers/fmcsa.py`" is not.

5. **Don't let two agents edit the same file.** If parallel work is needed, split the file first (like we did with `revenueinfra/` package).

6. **Don't skip the "existing code to read" section.** The agent needs reference patterns. Without them, it invents its own conventions.
