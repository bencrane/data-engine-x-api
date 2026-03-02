# Discover Pricing Page URL

**Endpoint:** `POST /discover_pricing_page_url`

**Modal URL:** `https://bencrane--hq-master-data-ingest-discover-pricing-page-url.modal.run`

---

## Prompt

```
Analyze this website and find the pricing page URL.

Company: {company_name}
Homepage: https://{domain}

Links found on the page:
{links_text}

Page content excerpt:
{page_text}

Your task: Find the URL that leads to the company's pricing page.

Look for:
- Links with text like "Pricing", "Plans", "Plans & Pricing", "Get Started", "See Plans"
- Common URL patterns like /pricing, /plans, /packages, /pricing-plans

If you find a clear pricing page link, report it with HIGH confidence.
If you find a likely candidate but aren't certain, report it with MEDIUM confidence.
If you cannot find any pricing page link, report null with LOW confidence.

Respond in this exact JSON format:
{"pricing_page_url": "https://example.com/pricing or null", "confidence": "high|medium|low", "explanation": "1-2 sentence explanation"}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "domain": "monday.com",
  "company_name": "Monday.com"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| domain | string | Yes | Company website domain |
| company_name | string | No | Company name |

---

## Sample Output

```json
{
  "success": true,
  "domain": "monday.com",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "pricing_page_url": "https://monday.com/pricing",
  "confidence": "high",
  "explanation": "Found clear 'Pricing' link in main navigation pointing to /pricing"
}
```

---

## Confidence Levels

- `high` - Clear pricing page link found
- `medium` - Likely candidate but not certain
- `low` - No pricing page found

---

## Database Writes

- **raw**: `raw.discover_pricing_page_payloads`
- **extracted**: `extracted.discover_pricing_page`
- **core**: `core.ancillary_urls` (upsert on domain if high/medium confidence)

---

## Notes

- Uses `gemini-2.0-flash` model
- Fetches homepage and extracts all links (up to 100)
- Normalizes relative URLs to absolute
- Truncates page text to 4000 characters
- Timeout: 60 seconds
