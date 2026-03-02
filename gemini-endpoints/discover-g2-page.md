# Discover G2 Page URL

**Endpoint:** `POST /discover_g2_page_gemini`

**Modal URL:** `https://bencrane--hq-master-data-ingest-discover-g2-page-gemini.modal.run`

---

## Prompt

```
Find the G2.com product page URL for {company_name} (website: {domain}).

G2.com is a software review platform. Companies have product pages at URLs like:
- https://www.g2.com/products/slack
- https://www.g2.com/products/salesforce-sales-cloud
- https://www.g2.com/products/hubspot-marketing-hub

Search your knowledge for the G2 product page URL for {company_name}.

If you know the URL, respond with ONLY the URL, nothing else.
If you don't know or can't find it, respond with: NOT_FOUND

Example good response: https://www.g2.com/products/stripe
Example not found response: NOT_FOUND
```

---

## Input Payload

```json
{
  "domain": "notion.so",
  "company_name": "Notion"
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
  "domain": "notion.so",
  "company_name": "Notion",
  "g2_url": "https://www.g2.com/products/notion",
  "raw_response": "https://www.g2.com/products/notion"
}
```

---

## Notes

- Uses `gemini-2.0-flash` model
- Relies on Gemini's knowledge of G2 product URLs
- Returns `null` for `g2_url` if not found or invalid
- Validates URL matches G2 product page pattern
- Does NOT write to database (read-only lookup)
- Timeout: 60 seconds
