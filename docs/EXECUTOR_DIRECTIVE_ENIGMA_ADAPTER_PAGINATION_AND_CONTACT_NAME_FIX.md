# Executor Directive: Enigma Adapter Pagination & Contact Name Fix

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** Two bugs were identified in the Enigma adapters committed in the SMB discovery build (commit `7ba36bc`). Both are in `app/providers/enigma.py`. Neither is deployed yet — these are pre-deploy fixes.

---

## Existing code to read

- `app/providers/enigma.py` — the file being fixed. Read the entire file. Pay particular attention to:
  - `SEARCH_BRANDS_BY_PROMPT_QUERY` (line 643) — the GraphQL query missing pagination support
  - `search_brands_by_prompt()` (line 893) — the adapter function that hardcodes `has_next_page: False` and `next_page_token: None` at lines 1016-1017
  - `_build_locations_enriched_query()` (line 677) — the dynamic query builder where the roles fragment (line 732) is missing person name fields
  - `_map_enriched_location()` (line 833) — the response mapper where contacts are built without a `full_name` field
- `docs/ENIGMA_API_REFERENCE.md` — sections 5 and 8 for the search pagination model and Role type field reference.
- `app/contracts/company_enrich.py` — the `EnigmaContactItem` contract that has a `full_name` field that's never populated.

---

## Bug 1: Brand Search Pagination

### Problem

`search_brands_by_prompt()` accepts a `page_token` parameter and correctly passes it in the SearchInput `conditions` (line 932-933), but the response always returns `has_next_page: False` and `next_page_token: None` (lines 1016-1017). There is no way for callers to paginate through results.

### Root cause

Enigma's `search()` API uses **offset-style pagination via `pageToken`**, not cursor-based `pageInfo`. The search results come back as a flat array (`data.search`), not a connection with `pageInfo`. The `pageToken` values are string-encoded offsets: `"0"`, `"50"`, `"100"`, etc. (See `docs/ENIGMA_API_REFERENCE.md` lines 826-827: "Next page: pageToken: '50', then '100', etc.")

The GraphQL query does NOT need a `pageInfo` block. Instead, pagination is inferred: if the number of results returned equals the requested limit, there are likely more results available and the next `pageToken` is the current offset + limit.

### Fix

In `search_brands_by_prompt()`, replace the hardcoded pagination values (lines 1016-1017) with computed values:

1. Determine the current offset from `page_token`. If `page_token` is `None` or not provided, the offset is `0`. Otherwise parse it as an integer.
2. If the number of brands returned equals `safe_limit`, set `has_next_page = True` and compute `next_page_token = str(current_offset + safe_limit)`.
3. If fewer brands were returned than `safe_limit`, set `has_next_page = False` and `next_page_token = None`.

The fix should look approximately like:

```python
current_offset = 0
if page_token:
    try:
        current_offset = int(page_token)
    except (TypeError, ValueError):
        current_offset = 0

has_next = len(brands) >= safe_limit
mapped = {
    "brands": brands,
    "total_returned": len(brands),
    "has_next_page": has_next,
    "next_page_token": str(current_offset + safe_limit) if has_next else None,
}
```

**No changes to the GraphQL query itself.** The query is fine — pagination is handled entirely through the `conditions.pageToken` input variable, not through response structure.

---

## Bug 2: Contact `full_name` Not Populated

### Problem

The `EnigmaContactItem` contract has a `full_name: str | None` field, but the `roles` GraphQL fragment in `_build_locations_enriched_query()` (line 732-757) does not request any name field. The `_map_enriched_location()` mapper (line 880) builds contact dicts without `full_name`. Every contact will have `full_name: null`.

### Root cause

The `Role` type in Enigma's schema does not have a direct name field. Person names are accessed via the `Role → legalEntities → persons` connection chain. The Person type has `firstName`, `lastName`, and `fullName` fields.

### Fix

**Step 1:** Update the roles fragment in `_build_locations_enriched_query()` to traverse the `legalEntities → persons` connection:

```python
roles_fragment = ""
if include_roles:
    roles_fragment = """
            roles(first: 10) {
              edges {
                node {
                  jobTitle
                  jobFunction
                  managementLevel
                  emailAddresses(first: 3) {
                    edges {
                      node {
                        emailAddress
                      }
                    }
                  }
                  phoneNumbers(first: 3) {
                    edges {
                      node {
                        phoneNumber
                      }
                    }
                  }
                  legalEntities(first: 1) {
                    edges {
                      node {
                        persons(first: 1) {
                          edges {
                            node {
                              fullName
                              firstName
                              lastName
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
"""
```

**Important:** Verify the exact field names against the Enigma GraphQL schema. Read `docs/ENIGMA_API_REFERENCE.md` section 8 and any SDL reference in `docs/api-reference-docs-new/enigma/`. The path `legalEntities → persons` and the field `fullName` need to be confirmed. If the schema uses different names (e.g., `person` singular, or `name` instead of `fullName`), adjust accordingly. If the executor cannot confirm the field names from documentation, add a code comment noting the assumption and flag it in the report.

**Step 2:** Update `_map_enriched_location()` to extract the person name from the nested connection. After the existing roles mapping code (around line 880), add name extraction:

```python
# Inside the contact-building loop, after extracting email and phone:
legal_entity_node = _first_edge_node(role_node.get("legalEntities"))
person_node = _first_edge_node(legal_entity_node.get("persons")) if legal_entity_node else {}
full_name = _as_str(person_node.get("fullName"))
if not full_name:
    first = _as_str(person_node.get("firstName")) or ""
    last = _as_str(person_node.get("lastName")) or ""
    combined = f"{first} {last}".strip()
    full_name = combined if combined else None

contacts.append({
    "full_name": full_name,
    "job_title": _as_str(role_node.get("jobTitle")),
    "job_function": _as_str(role_node.get("jobFunction")),
    "management_level": _as_str(role_node.get("managementLevel")),
    "email": _as_str(email_node.get("emailAddress")),
    "phone": _as_str(phone_contact_node.get("phoneNumber")),
})
```

The `_first_edge_node()` helper already exists in the file and handles the `edges[0].node` traversal pattern.

---

## What is NOT in scope

- **No changes to any file other than `app/providers/enigma.py`.** The contracts, services, workflow, migration, and all other files are correct as-is.
- **No new operations or adapters.** These are fixes to existing code.
- **No deploy commands.** Do not push.
- **No test data or production API calls.**

## Commit convention

Both fixes in a single commit. Do not push. Add a last-updated timestamp at the top of the file as a comment: `# Last updated: 2026-03-18T[HH:MM:SS]Z`.

## When done

Report back with:
(a) Pagination fix: confirm the offset-based `pageToken` approach was implemented. Show the exact logic for computing `has_next_page` and `next_page_token`.
(b) Contact name fix: confirm the `legalEntities → persons` traversal path. Report the exact GraphQL field names used. Flag if any field name could not be confirmed from documentation.
(c) Lines changed: approximate line count of the diff.
