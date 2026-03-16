**Directive: Add provider_data to All Active Canonical Mappers**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** Every canonical mapper in the codebase cherry-picks ~15-17 fields from provider responses and drops the rest. The raw response is preserved in `step_results` via `provider_attempts`, but the canonical output — which feeds entity state upserts, search results, and list snapshots — loses high-value data like funding, tech stack, social URLs, classification codes, phone numbers, and business attributes. Fix: add a `provider_data` field to every active canonical mapper that carries the full raw provider response alongside the existing mapped fields.

**What this is NOT:** This is not a schema migration. `provider_data` is added to the Python dict output of each mapper function. It flows into entity upserts (which store JSONB), search result dicts, and list snapshot_data. No database column changes needed.

**Existing code to read:**

- `app/services/company_operations.py` — all `_canonical_company_from_*` functions (lines 107-204)
- `app/providers/blitzapi.py` — `canonical_company_result()` (line 80), `canonical_person_result()` (line 100)
- `app/providers/prospeo.py` — `canonical_person_result()` (line 112)
- `app/providers/leadmagic.py` — `_canonical_person_result()` (line 25)
- `app/providers/icypeas.py` — `resolve_email()` (line 28) — mapped output shape
- `app/providers/companyenrich.py` — SKIP, no longer active

---

### Changes Required

**Important:** Do NOT modify existing canonical field mappings. Do NOT remove or rename the existing `raw` field on person mappers. This is purely additive — add `provider_data` to the return dict of each function.

#### 1. `_canonical_company_from_prospeo()` — `app/services/company_operations.py`

Add two fields to the return dict:

```python
"company_linkedin_id": company.get("linkedin_id"),  # BUG FIX: was missing
"provider_data": company,                            # full Prospeo company response
```

The `company` parameter already IS the full Prospeo company dict, so just pass it through.

#### 2. `_canonical_company_from_blitz()` — `app/services/company_operations.py`

Add one field to the return dict:

```python
"provider_data": company,  # full BlitzAPI company response
```

The `company` parameter already IS the full BlitzAPI company dict.

#### 3. `_canonical_company_from_leadmagic()` — `app/services/company_operations.py`

Add one field to the return dict:

```python
"provider_data": company,  # full Leadmagic company response
```

#### 4. `canonical_person_result()` — `app/providers/prospeo.py`

This function takes individual kwargs + `raw: dict` and already includes `"raw": raw` in its output. Add:

```python
"provider_data": raw,  # full Prospeo person response
```

This will coexist with `raw` — both point to the same dict. Existing consumers of `raw` are unaffected.

#### 5. `canonical_person_result()` — `app/providers/blitzapi.py`

Already includes `"raw": raw`. Add:

```python
"provider_data": raw,  # full BlitzAPI person response
```

#### 6. `_canonical_person_result()` — `app/providers/leadmagic.py`

Already includes `"raw": raw`. Add:

```python
"provider_data": raw,  # full Leadmagic person response
```

#### 7. `resolve_email()` — `app/providers/icypeas.py`

This is an email resolution adapter, not a canonical entity mapper. The mapped output is `{"email": resolved_email}`. Change the success return (around line 143) to:

```python
"mapped": {"email": resolved_email, "provider_data": last_body},
```

Where `last_body` is the full Icypeas poll response that's already in scope at that point.

---

### Tests

No new test file needed. The changes are purely additive (adding a key to existing dicts). Verify that all existing tests still pass — none should break since no existing field is modified or removed.

If any existing test asserts an exact dict match (e.g., `assert result == {...}`), it will need the new `provider_data` key added to the expected dict. Fix those assertions to include the new field.

---

**What is NOT in scope:**

- No database migrations. `provider_data` is a dict key, not a DB column.
- No changes to CompanyEnrich mappers (no longer active).
- No changes to `_merge_company_profile()` or any downstream consumer. They use first-non-null field merging which ignores unknown keys.
- No changes to contracts, routers, or services beyond the mapper functions.
- No deploy.

**Commit convention:** All changes in one commit — these are all one-line additions to existing functions. Do not push.

**When done:** Report back with: (a) which 7 functions were modified, (b) confirm the linkedin_id fix was applied to `_canonical_company_from_prospeo`, (c) any tests that needed assertion updates and what changed, (d) anything to flag.
