# Bug Fix Directive: `company.derive.icp_criterion` Fails with 422

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**The problem:** All 7 runs of the AlumniGTM Company Workflow v1 blueprint failed at step 5 (`company.derive.icp_criterion`). The HQ endpoint returned HTTP 422: `"Input should be a valid list"` for field `customers` — the value was `null`.

**Root cause — 3 bugs:**

1. **`_coerce_customer_names` checks wrong field name.** The customers from step 4 (`discover_customers_gemini`) are dicts shaped `{"company_name": "A&O Shearman", "domain": "aoshearman.com", "evidence_url": "..."}`. But `_coerce_customer_names` at line 61 extracts `item.get("name")` — wrong key. Should check `"name"` AND `"company_name"`.

2. **Null coercion returns propagate to provider.** `_coerce_customer_names` and `_coerce_titles` return `None` when they find no valid items or receive `None`. The service function at lines 319-320 passes these `None` values directly to the provider adapter.

3. **Provider sends `null` for required array fields.** `icp_criterion.py` line 47-48 puts `customers` and `icp_titles` into the payload as-is. When they're `None`, HQ receives `"customers": null` and rejects with 422 — it requires a list.

---

## Fix 1: `_coerce_customer_names` — check both field names

**File:** `app/services/hq_workflow_operations.py`

**Current (line 55-68):**
```python
def _coerce_customer_names(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = _as_str(item.get("name"))
            if name:
                names.append(name)
            continue
        name = _as_str(item)
        if name:
            names.append(name)
    return names or None
```

**Fix:** Check `"name"` first, then fall back to `"company_name"`:

```python
def _coerce_customer_names(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = _as_str(item.get("name")) or _as_str(item.get("company_name"))
            if name:
                names.append(name)
            continue
        name = _as_str(item)
        if name:
            names.append(name)
    return names or None
```

---

## Fix 2: Service function — default to empty list

**File:** `app/services/hq_workflow_operations.py`

**Current (lines 319-320):**
```python
    customers = _coerce_customer_names(_extract_list(input_data, ("customers",)))
    icp_titles = _coerce_titles(_extract_list(input_data, ("champion_titles", "titles")))
```

**Fix:** Default to empty list when coercion returns None:

```python
    customers = _coerce_customer_names(_extract_list(input_data, ("customers",))) or []
    icp_titles = _coerce_titles(_extract_list(input_data, ("champion_titles", "titles"))) or []
```

---

## Fix 3: Provider adapter — never send null for array fields

**File:** `app/providers/revenueinfra/icp_criterion.py`

**Current (lines 44-49):**
```python
    payload: dict[str, Any] = {
        "company_name": normalized_company_name,
        "domain": normalized_domain,
        "customers": customers,
        "icp_titles": icp_titles,
    }
```

**Fix:** Default to empty list:

```python
    payload: dict[str, Any] = {
        "company_name": normalized_company_name,
        "domain": normalized_domain,
        "customers": customers if customers is not None else [],
        "icp_titles": icp_titles if icp_titles is not None else [],
    }
```

---

## Scope

Fix only the 3 locations listed above. Do not change any other files or functions.

**One commit. Do not push.**

Commit message: `fix icp_criterion 422: coerce customer names from company_name field, default arrays to empty list`

## When done

Report back with:
(a) Confirmation all 3 fixes applied
(b) Run existing tests to confirm nothing breaks: `PYTHONPATH=. uv run --with pytest --with pytest-asyncio --with pyyaml pytest tests/test_hq_workflow_operations.py -v`
(c) Anything to flag
