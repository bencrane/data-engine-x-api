# Directive: Unified Input Extraction — Kill Field Name Mismatches Forever

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We have a critical recurring bug: every service function has its own inline alias tuple for extracting `company_name`, `domain`, `description`, etc. from input_data and cumulative_context. These alias lists are inconsistent — some check `current_company_name`, some don't. Some check `description_raw`, some only check `description`. Every time we add a new pipeline that passes data with a different field name, operations break with `missing_inputs`. This has caused 5+ production failures. It ends now.

---

## The Fix

Create a single shared input extraction module that ALL service functions use. One canonical alias map. One place to update.

### Deliverable 1: Shared Input Extraction Module

**File:** `app/services/_input_extraction.py` (new file)

```python
"""Unified input extraction from input_data + cumulative_context.

Every operation service function should use these helpers instead of
defining its own alias tuples. When a new field name variant appears
in pipeline context, add it here ONCE and every operation benefits.
"""

from __future__ import annotations

from typing import Any


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_list(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        return value
    return None


def _ctx(input_data: dict[str, Any]) -> dict[str, Any]:
    context = input_data.get("cumulative_context")
    if isinstance(context, dict):
        return context
    return {}


def _options(input_data: dict[str, Any]) -> dict[str, Any]:
    opts = input_data.get("options")
    if isinstance(opts, dict):
        return opts
    return {}


def extract_str(input_data: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        value = _as_str(input_data.get(alias))
        if value:
            return value
    context = _ctx(input_data)
    for alias in aliases:
        value = _as_str(context.get(alias))
        if value:
            return value
    opts = _options(input_data)
    for alias in aliases:
        value = _as_str(opts.get(alias))
        if value:
            return value
    return None


def extract_list(input_data: dict[str, Any], aliases: tuple[str, ...]) -> list[Any] | None:
    for alias in aliases:
        value = _as_list(input_data.get(alias))
        if value is not None:
            return value
    context = _ctx(input_data)
    for alias in aliases:
        value = _as_list(context.get(alias))
        if value is not None:
            return value
    opts = _options(input_data)
    for alias in aliases:
        value = _as_list(opts.get(alias))
        if value is not None:
            return value
    return None


# ---------------------------------------------------------------------------
# Canonical alias maps — THE SINGLE SOURCE OF TRUTH for field name variants.
# When a new variant appears (e.g., a provider returns "companyName" instead
# of "company_name"), add it to the appropriate tuple below.
# ---------------------------------------------------------------------------

COMPANY_NAME = ("company_name", "current_company_name", "canonical_name", "name", "companyName", "matched_name")
COMPANY_DOMAIN = ("domain", "company_domain", "canonical_domain", "customer_domain")
COMPANY_LINKEDIN_URL = ("company_linkedin_url", "linkedin_url", "customer_linkedin_url")
COMPANY_LINKEDIN_ID = ("company_linkedin_id", "org_id", "orgId", "linkedin_id")
COMPANY_DESCRIPTION = ("description", "description_raw", "company_description", "about")
COMPANY_INDUSTRY = ("industry", "industry_primary", "current_company_industry")
COMPANY_LOCATION = ("hq_locality", "hq_country_code", "current_company_location", "geo_region")

PERSON_LINKEDIN_URL = ("person_linkedin_url", "linkedin_url")
PERSON_FULL_NAME = ("full_name", "person_full_name", "name")
PERSON_EMAIL = ("work_email", "email")

ICP_CRITERION = ("criterion", "icp_criterion")
ICP_TITLES = ("champion_titles", "titles", "icp_titles")
CUSTOMERS = ("customers",)

SALES_NAV_URL = ("sales_nav_url", "salesnav_url")


# ---------------------------------------------------------------------------
# Convenience extractors — use these in service functions.
# ---------------------------------------------------------------------------

def extract_company_name(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, COMPANY_NAME)

def extract_domain(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, COMPANY_DOMAIN)

def extract_company_linkedin_url(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, COMPANY_LINKEDIN_URL)

def extract_company_linkedin_id(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, COMPANY_LINKEDIN_ID)

def extract_description(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, COMPANY_DESCRIPTION)

def extract_criterion(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, ICP_CRITERION)

def extract_person_linkedin_url(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, PERSON_LINKEDIN_URL)

def extract_person_full_name(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, PERSON_FULL_NAME)

def extract_sales_nav_url(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, SALES_NAV_URL)

def extract_customers(input_data: dict[str, Any]) -> list[Any] | None:
    return extract_list(input_data, CUSTOMERS)

def extract_titles(input_data: dict[str, Any]) -> list[Any] | None:
    return extract_list(input_data, ICP_TITLES)
```

Commit standalone with message: `add unified input extraction module with canonical alias maps`

---

### Deliverable 2: Migrate `hq_workflow_operations.py`

**File:** `app/services/hq_workflow_operations.py`

Replace all inline `_extract_str(input_data, ("company_name", ...))` calls with the shared extractors:

```python
from app.services._input_extraction import (
    extract_company_name,
    extract_domain,
    extract_company_linkedin_url,
    extract_company_linkedin_id,
    extract_description,
    extract_criterion,
    extract_str,
    extract_list,
    COMPANY_NAME,
    COMPANY_DOMAIN,
    ICP_TITLES,
    CUSTOMERS,
)
```

Then replace every occurrence:
- `_extract_str(input_data, ("company_name", "current_company_name", "canonical_name", "name"))` → `extract_company_name(input_data)`
- `_extract_str(input_data, ("domain", "company_domain", "canonical_domain"))` → `extract_domain(input_data)`
- `_extract_str(input_data, ("company_description", "description_raw", "description"))` → `extract_description(input_data)`
- `_extract_str(input_data, ("criterion", "icp_criterion"))` → `extract_criterion(input_data)`
- `_extract_str(input_data, ("company_linkedin_id", "org_id", "orgId", "linkedin_id"))` → `extract_company_linkedin_id(input_data)`

Keep the local `_extract_str`, `_extract_list`, `_ctx` functions for now (other functions in the file may use them) but mark them as deprecated with a comment. They can be removed in a follow-up.

Remove the `_coerce_customer_names` and `_coerce_titles` functions and replace with shared versions from the extraction module OR keep them locally but make sure they use the shared extractors for the initial list fetch.

Commit standalone with message: `migrate hq_workflow_operations to unified input extraction`

---

### Deliverable 3: Migrate `blitzapi_person_operations.py`

Same pattern. Replace inline alias tuples with shared extractors.

Commit standalone with message: `migrate blitzapi_person_operations to unified input extraction`

---

### Deliverable 4: Migrate `company_operations.py`

Same pattern for `execute_company_enrich_profile_blitzapi` and any other functions that extract company_name, domain, linkedin_url from input_data.

Commit standalone with message: `migrate company_operations to unified input extraction`

---

### Deliverable 5: Migrate `resolve_operations.py`

Same pattern.

Commit standalone with message: `migrate resolve_operations to unified input extraction`

---

### Deliverable 6: Migrate `salesnav_operations.py`

Same pattern.

Commit standalone with message: `migrate salesnav_operations to unified input extraction`

---

### Deliverable 7: Migrate `blitzapi_company_search.py`

Same pattern.

Commit standalone with message: `migrate blitzapi_company_search to unified input extraction`

---

### Deliverable 8: Migrate remaining service files

Migrate these files:
- `research_operations.py`
- `adyntel_operations.py`
- `email_operations.py`
- `person_enrich_operations.py`
- `search_operations.py`
- `sec_filing_operations.py`
- `pricing_intelligence_operations.py`
- `theirstack_operations.py`
- `courtlistener_operations.py`
- `shovels_operations.py`
- `change_detection_operations.py`
- `icp_extraction_operations.py`

For each: replace inline alias tuples with shared extractors where applicable. Not every file will use every extractor — only replace the ones that extract company_name, domain, description, linkedin_url, etc.

Commit standalone with message: `migrate remaining service files to unified input extraction`

---

## Critical Rules

1. **NEVER define alias tuples inline in service functions anymore.** Always use the shared extractors from `_input_extraction.py`.
2. **When a new field name variant appears**, add it to the canonical alias tuple in `_input_extraction.py`. ONE place.
3. **Do not break existing behavior.** Every alias that currently exists in any service function must be present in the canonical map. If a service function checks `"work_email"`, that alias must be in the shared map.
4. **Run existing tests after each migration** to confirm nothing breaks: `PYTHONPATH=. uv run --with pytest --with pytest-asyncio --with pyyaml pytest tests/ -x -q`

---

## What is NOT in scope

- No changes to provider adapters
- No changes to contracts
- No changes to routers
- No database migrations
- No changes to `run-pipeline.ts`
- No deploy commands

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Full list of canonical alias tuples and what's in each
(b) Number of service files migrated
(c) Number of inline alias tuples replaced
(d) Test results — all passing?
(e) Any aliases you found in existing code that weren't in my list above (add them to the canonical map)
(f) Anything to flag
