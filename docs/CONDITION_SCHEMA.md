# Condition Schema

`step_config` for a blueprint step may include a `condition` object that controls whether the step executes at runtime.

If no condition is provided, the step always runs (backward compatible).

## Where It Lives

Each step supports:

```json
{
  "operation_id": "company.derive.pricing_intelligence",
  "position": 3,
  "step_config": {
    "condition": { "field": "pricing_page_url", "op": "exists" }
  }
}
```

The runtime evaluates `step_config.condition` (or top-level `condition` in step snapshots) against the current cumulative context.

## Condition Shapes

### 1) Single field condition

```json
{ "field": "pricing_page_url", "op": "exists" }
```

```json
{ "field": "has_raised_vc", "op": "eq", "value": true }
```

```json
{ "field": "employee_count", "op": "lt", "value": 100 }
```

### 2) Logical AND

```json
{
  "all": [
    { "field": "pricing_page_url", "op": "exists" },
    { "field": "employee_count", "op": "gt", "value": 10 }
  ]
}
```

### 3) Logical OR

```json
{
  "any": [
    { "field": "current_job_title", "op": "icontains", "value": "VP" },
    { "field": "current_job_title", "op": "icontains", "value": "Director" },
    { "field": "current_job_title", "op": "icontains", "value": "Head of" }
  ]
}
```

## Operators

Supported `op` values:

- `exists`: field exists and is not `null` / empty string / empty array
- `eq`: equals `value`
- `ne`: not equal to `value`
- `lt`: less than `value` (numeric)
- `gt`: greater than `value` (numeric)
- `lte`: less than or equal to `value` (numeric)
- `gte`: greater than or equal to `value` (numeric)
- `contains`: case-sensitive substring search
- `icontains`: case-insensitive substring search
- `in`: field value is present in the list provided as `value`

## Field Resolution

- `field` supports dot notation for nested access.
- Example: `company_profile.industry` resolves `context["company_profile"]["industry"]`.

## Runtime Semantics

- Missing field:
  - `exists` returns `false`
  - all other operators return `false`
- `condition: null` or omitted condition => `true` (always run)
- Empty condition object `{}` => treated as no-op => `true`
- `all` evaluates all children with logical AND
- `any` evaluates all children with logical OR

## Type Coercion Rules

- Numeric operators (`lt`, `gt`, `lte`, `gte`) coerce numeric strings to numbers when possible.
- String operators (`contains`, `icontains`) coerce values to strings.
- Comparisons are null-safe and never throw due to missing/null fields.
