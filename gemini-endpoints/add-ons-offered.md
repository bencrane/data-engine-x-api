# Add-ons Offered Inference

**Endpoint:** `POST /infer_add_ons_offered`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-add-ons-offered.modal.run`

---

## Prompt

```
Analyze this pricing page content and determine if the company offers add-ons or optional extras.

Company: {company_name}
Pricing Page URL: {pricing_page_url}

Pricing Page Content:
{page_text}

Add-ons are optional features, modules, or extras that can be purchased separately on top of a base plan (e.g., extra storage, premium support, additional integrations, API access as add-on).

Classify as ONE of:
- yes: Add-ons or optional extras are clearly offered
- no: No add-ons mentioned, all features are included in the tiers
- unclear: Cannot determine from the pricing page content

Respond in this exact JSON format:
{"add_ons_offered": "yes|no|unclear", "explanation": "1-2 sentence explanation"}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "company_name": "HubSpot",
  "domain": "hubspot.com",
  "pricing_page_url": "https://www.hubspot.com/pricing"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| company_name | string | No | Company name |
| domain | string | Yes | Company website domain |
| pricing_page_url | string | Yes | URL of the pricing page |

---

## Sample Output

```json
{
  "success": true,
  "domain": "hubspot.com",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "add_ons_offered": "yes",
  "explanation": "HubSpot offers several add-ons including additional marketing contacts, API calls, ads management, and transactional email."
}
```

---

## Valid Values

- `yes` - Add-ons available
- `no` - No add-ons offered
- `unclear` - Cannot determine

---

## Database Writes

- **raw**: `raw.add_ons_offered_payloads`
- **extracted**: `extracted.company_add_ons_offered`
- **core**: `core.company_add_ons_offered` (upsert on domain)

---

## Notes

- Uses `gemini-3-flash-preview` model
- Fetches and parses pricing page HTML
- Truncates page content to 8000 characters
- Timeout: 60 seconds
