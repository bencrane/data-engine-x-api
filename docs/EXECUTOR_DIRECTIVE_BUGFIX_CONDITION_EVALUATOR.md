# Bug Fix Directive: Condition Evaluator Missing Shorthand Format Support

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**The problem:** Blueprint step conditions using the shorthand format `{"exists": "field_name"}` always evaluate to `false`, causing steps to be incorrectly skipped. This broke Blueprint 1's step 2 (BlitzAPI enrich) and step 6 (Sales Nav URL builder) — both were skipped even though the required fields were present in cumulative context.

**Root cause:** The condition evaluator in `trigger/src/utils/evaluate-condition.ts` only handles three formats:
1. `{"all": [...]}` — group AND
2. `{"any": [...]}` — group OR
3. `{"field": "X", "op": "exists"}` — single condition with explicit field + op

But blueprints use the shorthand format `{"exists": "field_name"}` (and potentially `{"eq": {"field": "X", "value": "Y"}}`, `{"ne": {...}}`, `{"not": {...}}`). These fall through to `return false` at line 149.

The staffing blueprint also uses this shorthand format — its conditions have been silently broken (steps skipped or conditions ignored).

---

## File to read before starting

- `trigger/src/utils/evaluate-condition.ts` — the entire file. It's ~150 lines. Read all of it.

---

## The Fix

Add shorthand format handling to the `evaluateCondition` function. The shorthand formats to support:

### 1. `{"exists": "field_name"}` → `{"field": "field_name", "op": "exists"}`

```typescript
if ("exists" in conditionValue && typeof conditionValue.exists === "string") {
  return evaluateSingleCondition(
    { field: conditionValue.exists, op: "exists" },
    context,
  );
}
```

### 2. `{"eq": {"field": "X", "value": "Y"}}` → `{"field": "X", "op": "eq", "value": "Y"}`

```typescript
if ("eq" in conditionValue && isRecord(conditionValue.eq)) {
  const inner = conditionValue.eq as Record<string, unknown>;
  if (typeof inner.field === "string") {
    return evaluateSingleCondition(
      { field: inner.field, op: "eq", value: inner.value },
      context,
    );
  }
}
```

### 3. Same pattern for `ne`, `lt`, `gt`, `lte`, `gte`, `contains`, `icontains`, `in`

Each shorthand: `{"op_name": {"field": "X", "value": "Y"}}` maps to `{"field": "X", "op": "op_name", "value": "Y"}`.

Rather than duplicating the block for each operator, handle them in a loop:

```typescript
const shorthandOps: ComparisonOp[] = ["eq", "ne", "lt", "gt", "lte", "gte", "contains", "icontains", "in"];
for (const op of shorthandOps) {
  if (op in conditionValue && isRecord(conditionValue[op])) {
    const inner = conditionValue[op] as Record<string, unknown>;
    if (typeof inner.field === "string") {
      return evaluateSingleCondition(
        { field: inner.field, op, value: inner.value },
        context,
      );
    }
  }
}
```

### 4. `{"not": <condition>}` → negate the inner condition

```typescript
if ("not" in conditionValue && isRecord(conditionValue.not)) {
  return !evaluateCondition(conditionValue.not, context);
}
```

### Placement

Add all shorthand handlers **after** the `"any"` group check and **before** the `"field" + "op"` single condition check. The order in `evaluateCondition` should be:

1. `"all"` group (existing)
2. `"any"` group (existing)
3. `"not"` negation (new)
4. `"exists"` shorthand (new)
5. Comparison operator shorthands — `eq`, `ne`, etc. (new)
6. `"field" + "op"` explicit format (existing)
7. `return false` fallback (existing)

---

## Scope

Fix only `trigger/src/utils/evaluate-condition.ts`. Do not change any other files.

**One commit. Do not push.**

Commit message: `fix condition evaluator: add shorthand format support (exists, eq, ne, not, etc.)`

## When done

Report back with:
(a) List of shorthand formats now supported
(b) Confirm `{"exists": "company_linkedin_url"}` evaluates to `true` when the field is present
(c) Confirm `{"not": {"exists": "company_domain"}}` evaluates to `true` when the field is absent
(d) Confirm `{"eq": {"field": "status", "value": "active"}}` works
(e) Confirm existing formats (`{"field": "X", "op": "exists"}`, `{"all": [...]}`, `{"any": [...]}`) still work unchanged
(f) Anything to flag
