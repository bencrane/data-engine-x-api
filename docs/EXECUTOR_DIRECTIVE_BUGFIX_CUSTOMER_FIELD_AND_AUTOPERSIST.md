# Bug Fix Directive: Customer Name Field + Auto-Persist for Resolved Customer Lookup

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**The problem:** Two issues discovered during SecurityPal AI pipeline test:

1. The `company.derive.icp_criterion` step sends `customers: []` to HQ even though 58 customers are in cumulative context. The `_coerce_customer_names` function doesn't check the `customer_name` field — it only checks `name` and `company_name`. The HQ resolved customer lookup returns objects with `customer_name` as the key.

2. The `company.research.lookup_customers_resolved` operation has no auto-persist wiring in `run-pipeline.ts`. When customers come from this operation (instead of `discover_customers_gemini`), they don't get written to the `company_customers` table.

---

## Fix 1: Add `customer_name` to `_coerce_customer_names`

**File:** `app/services/hq_workflow_operations.py`

**Current (line 63):**
```python
            name = _as_str(item.get("name")) or _as_str(item.get("company_name"))
```

**Fix:**
```python
            name = _as_str(item.get("name")) or _as_str(item.get("company_name")) or _as_str(item.get("customer_name"))
```

---

## Fix 2: Add auto-persist for `lookup_customers_resolved` in pipeline runner

**File:** `trigger/src/tasks/run-pipeline.ts`

Find the existing auto-persist block for `company.research.discover_customers_gemini` (~line 2180). It starts with:

```typescript
if (operationId === "company.research.discover_customers_gemini" && result.status === "found" && result.output) {
```

Change the condition to also trigger for the resolved lookup operation:

```typescript
if ((operationId === "company.research.discover_customers_gemini" || operationId === "company.research.lookup_customers_resolved") && result.status === "found" && result.output) {
```

That's it. The rest of the block is identical — it reads `customers` from `result.output`, posts to `/api/internal/company-customers/upsert`. Both operations return `customers` in the same shape.

---

## Scope

Two files only. Do not change anything else.

**One commit. Do not push.**

Commit message: `fix customer name coercion (add customer_name alias) and auto-persist for lookup_customers_resolved`

## When done

Report back with:
(a) Confirm `_coerce_customer_names` now checks `name`, `company_name`, and `customer_name`
(b) Confirm auto-persist block triggers for both `discover_customers_gemini` and `lookup_customers_resolved`
(c) Anything to flag
