# Writing Executor Directives

How to write directives that executor agents can implement correctly without ambiguity.

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

---

**What is NOT in scope:** [Explicit exclusions]

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) ..., (b) ..., (c) ..., (d) ..., (e) anything to flag.
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
