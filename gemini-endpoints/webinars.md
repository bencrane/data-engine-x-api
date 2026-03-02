# Webinars Extraction

**Endpoint:** `POST /infer_webinars`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-webinars.modal.run`

---

## Prompt

```
Analyze this company's webinar page and extract individual webinars.

Company: {company_name}
Webinar Page URL: {webinar_page_url}

Webinar Page Content:
{webinar_page_text}

Extract SPECIFIC webinars with their actual titles - NOT generic "Webinars" links.
Look for:
- Individual webinar titles (e.g., "How to Scale Your Sales Team", "AI in Customer Service")
- On-demand or upcoming webinar listings
- Webinar series or episodes

For each specific webinar found, extract:
1. The title (the actual webinar name, not "Webinars")
2. The topic/category (e.g., "AI", "Sales", "Customer Success", "Product")

Respond in this exact JSON format:
{
  "webinars": [
    {"title": "How to Scale Customer Support with AI", "topic": "AI"},
    {"title": "Best Practices for Enterprise CX", "topic": "Customer Experience"}
  ]
}

If no specific webinars found (just a generic webinar page), return: {"webinars": []}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "company_name": "Gong",
  "domain": "gong.io"
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
  "domain": "gong.io",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "has_webinars": true,
  "webinar_count": 4,
  "webinars": [
    {"title": "Revenue Intelligence Best Practices", "topic": "Revenue"},
    {"title": "AI-Powered Sales Coaching", "topic": "AI"},
    {"title": "Closing Deals in Q4", "topic": "Sales"},
    {"title": "Building a Data-Driven Sales Team", "topic": "Sales Strategy"}
  ],
  "webinar_topics": ["Revenue", "AI", "Sales", "Sales Strategy"]
}
```

---

## Database Writes

- **raw**: `raw.webinars_payloads`
- **extracted**: `extracted.company_webinars` (one row per webinar)
- **core**: `core.company_webinars` (upsert on domain with summary)

---

## Notes

- Uses `gemini-3-flash-preview` model
- First searches homepage for webinar page link
- Then fetches and analyzes the webinar page
- Returns early with `has_webinars: false` if no webinar page found
- Truncates webinar page content to 10000 characters
- Timeout: 60 seconds
