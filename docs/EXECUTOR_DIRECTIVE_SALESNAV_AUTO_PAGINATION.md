# Directive: Auto-Pagination for `person.search.sales_nav_url`

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The `person.search.sales_nav_url` operation currently fetches only page 1 (25 results) from the RapidAPI Sales Navigator scraper and stops. A typical query returns 100-500+ total results. The operation must auto-paginate by default — fetch all pages, aggregate all results, and return the complete set. A `max_pages` parameter should allow callers to cap pagination if needed.

---

## Existing code to read before starting

- `app/services/salesnav_operations.py` — the service function `execute_person_search_sales_nav_url`. This is where the pagination loop goes.
- `app/providers/rapidapi_salesnav.py` — the provider adapter `scrape_sales_nav_url`. Read the full function to understand what it returns: `results` (list), `result_count`, `total_available`, `page`, `source_url`. The provider already accepts a `page` parameter. Do NOT modify this file.
- `app/contracts/sales_nav.py` — the output contract. May need updating if fields change.

---

## The Fix

**File:** `app/services/salesnav_operations.py`

Rewrite `execute_person_search_sales_nav_url` to auto-paginate. The logic:

### Input extraction (add `max_pages`)

```python
max_pages = _as_int(
    input_data.get("max_pages") or options.get("max_pages") or context.get("max_pages"),
    default=50,
    minimum=1,
)
```

Default is 50 pages (1,250 results). This prevents runaway pagination on enormous result sets. Callers can override via input, step_config options, or cumulative context.

### Pagination loop

Replace the single provider call with a loop:

```python
settings = get_settings()
all_results: list[dict[str, Any]] = []
current_page = 1
total_available: int | None = None

while current_page <= max_pages:
    provider_result = await rapidapi_salesnav.scrape_sales_nav_url(
        api_key=settings.rapidapi_salesnav_scrape_api_key,
        sales_nav_url=sales_nav_url,
        page=current_page,
        account_number=account_number,
    )
    attempt = _as_dict(provider_result.get("attempt"))
    attempts.append(attempt)

    provider_status = attempt.get("status", "failed")
    if provider_status in {"failed", "skipped"}:
        break

    mapped = _as_dict(provider_result.get("mapped"))
    page_results = mapped.get("results")
    if not isinstance(page_results, list):
        page_results = []

    all_results.extend(page_results)

    if total_available is None:
        total_available = mapped.get("total_available")

    # Stop if no results on this page (we've exhausted the data)
    if len(page_results) == 0:
        break

    # Stop if we've fetched all available results
    if isinstance(total_available, int) and len(all_results) >= total_available:
        break

    current_page += 1
```

### Output construction

After the loop, build the output from the aggregated results:

```python
try:
    output = SalesNavSearchOutput.model_validate(
        {
            "results": all_results,
            "result_count": len(all_results),
            "total_available": total_available,
            "page": current_page,  # last page fetched
            "pages_fetched": current_page if all_results else 0,
            "source_url": sales_nav_url,
            "source_provider": "rapidapi_salesnav",
        }
    ).model_dump()
except Exception as exc:
    # ... existing validation error handling ...
```

### Status determination

Same logic as before but based on the aggregated results:

```python
if not all_results and attempts:
    last_attempt = attempts[-1]
    last_status = last_attempt.get("status", "failed")
    if last_status in {"failed", "skipped"}:
        status = "failed"
    else:
        status = "not_found"
else:
    status = "found" if all_results else "not_found"
```

---

## Contract update

**File:** `app/contracts/sales_nav.py`

Add `pages_fetched` field to `SalesNavSearchOutput`:

```python
pages_fetched: int | None = None
```

This is an optional field — existing callers won't break.

---

## Important considerations

1. **Rate limiting**: RapidAPI may rate-limit rapid sequential calls. Add a small delay between pages if needed. Start without a delay — if we see 429s in production, we'll add one.

2. **The loop MUST terminate**: The `max_pages` cap and the `len(page_results) == 0` check ensure the loop always terminates. Both conditions are required.

3. **Provider attempts accumulate**: Each page call appends to the `attempts` list. This is correct — it gives full visibility into how many calls were made and whether any individual pages failed.

4. **Fan-out compatibility**: The output still has `results` as a top-level list. When this operation is used with `fan_out: true` in a blueprint, the pipeline runner will create child runs from each result — which is exactly what we want (one child per prospect).

---

## Scope

Two files: `app/services/salesnav_operations.py` and `app/contracts/sales_nav.py`. Do not change any other files.

**One commit. Do not push.**

Commit message: `add auto-pagination to person.search.sales_nav_url, default max 50 pages`

## When done

Report back with:
(a) Pagination loop logic — how it decides when to stop
(b) `max_pages` default value and where it's extracted from
(c) Confirmation `all_results` aggregates across all pages
(d) Confirmation `result_count` reflects total aggregated count (not just last page)
(e) Contract change — `pages_fetched` field added
(f) Anything to flag (e.g., rate limiting concerns)
