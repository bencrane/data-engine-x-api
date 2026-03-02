# Comparison Page Exists Inference

**Endpoint:** `POST /infer_comparison_page_exists`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-comparison-page-exists.modal.run`

---

## Prompt

```
Analyze this company's homepage and extract all comparison pages.

Company: {company_name}
Homepage URL: https://{domain}

Links found on homepage:
{links_text}

Look for comparison pages like:
- "X vs Y" pages
- "Alternative to X" pages
- "Compare" pages
- "Why choose us over X" pages
- URLs containing /vs/, /compare, /alternatives, /versus

For each comparison page found, extract:
1. The URL (relative or absolute)
2. The title/link text
3. The competitor being compared (if identifiable)

Respond in this exact JSON format:
{
  "comparison_pages": [
    {"url": "/vs-salesforce", "title": "Acme vs Salesforce", "competitor": "Salesforce"},
    {"url": "/alternatives/hubspot", "title": "HubSpot Alternative", "competitor": "HubSpot"}
  ]
}

If no comparison pages found, return: {"comparison_pages": []}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "company_name": "Pipedrive",
  "domain": "pipedrive.com"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| company_name | string | No | Company name |
| domain | string | Yes | Company website domain |

---

## Sample Output

```json
{
  "success": true,
  "domain": "pipedrive.com",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "has_comparison_pages": true,
  "comparison_count": 3,
  "comparison_pages": [
    {"url": "/vs/salesforce", "title": "Pipedrive vs Salesforce", "competitor": "Salesforce"},
    {"url": "/vs/hubspot-sales", "title": "Pipedrive vs HubSpot Sales", "competitor": "HubSpot"},
    {"url": "/vs/zoho-crm", "title": "Pipedrive vs Zoho CRM", "competitor": "Zoho"}
  ],
  "competitors_mentioned": ["Salesforce", "HubSpot", "Zoho"]
}
```

---

## Database Writes

- **raw**: `raw.comparison_page_exists_payloads`
- **extracted**: `extracted.company_comparison_pages` (one row per comparison page)
- **core**: `core.company_comparison_pages` (upsert on domain with summary)

---

## Notes

- Uses `gemini-3-flash-preview` model
- Fetches homepage and extracts all links
- Analyzes up to 300 links from the page
- Returns list of competitors mentioned
- Timeout: 60 seconds
