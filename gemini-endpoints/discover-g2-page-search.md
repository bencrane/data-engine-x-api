# Discover G2 Page URL (Search)

**Endpoint:** `POST /discover_g2_page_gemini_search`

**Modal URL:** `https://bencrane--hq-master-data-ingest-discover-g2-page-gemini-search.modal.run`

---

## Prompt

```
Search for the G2.com page for {company_name} (website: {domain}).

G2.com is a software review platform. Company pages can be at URLs like:
- https://www.g2.com/products/slack
- https://www.g2.com/sellers/palo-alto-networks
- https://www.g2.com/products/hubspot-marketing-hub

DO NOT guess or interpolate the URL. Only return a URL if you can actually find/verify it exists.

If you find the G2 page, return ONLY the full URL.
If you cannot find it, return exactly: NOT_FOUND
```

---

## Input Payload

```json
{
  "domain": "datadog.com",
  "company_name": "Datadog"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| domain | string | Yes | Company website domain |
| company_name | string | Yes | Company name |

---

## Sample Output

```json
{
  "success": true,
  "domain": "datadog.com",
  "company_name": "Datadog",
  "g2_url": "https://www.g2.com/products/datadog",
  "input_tokens": 85,
  "output_tokens": 12,
  "cost_usd": 0.000013
}
```

---

## Notes

- Uses `gemini-2.0-flash` model
- Validates URL matches G2 pattern (`/products/`, `/sellers/`, `/vendors/`)
- Returns `null` for `g2_url` if not found
- Includes token usage and cost tracking
- Does NOT write to database (read-only lookup)
- Cost: ~$0.10/1M input tokens, ~$0.40/1M output tokens
- Timeout: 60 seconds
