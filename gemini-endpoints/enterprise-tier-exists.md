# Enterprise Tier Exists Inference

**Endpoint:** `POST /infer_enterprise_tier_exists`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-enterprise-tier-exists.modal.run`

---

## Prompt

```
Analyze this pricing page content and determine if an enterprise tier exists.

Company: {company_name}
Pricing Page URL: {pricing_page_url}

Pricing Page Content:
{page_text}

An enterprise tier is typically labeled "Enterprise", "Business", "Company", "Team", or similar, and often has "Contact Sales", "Contact Us", or custom pricing.

Classify as ONE of:
- yes: An enterprise tier or custom pricing option for larger customers exists
- no: No enterprise tier or custom pricing option visible

You must choose yes or no. If uncertain, lean toward no.

Respond in this exact JSON format:
{"enterprise_tier_exists": "yes|no", "explanation": "1-2 sentence explanation"}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "company_name": "Airtable",
  "domain": "airtable.com",
  "pricing_page_url": "https://airtable.com/pricing"
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
  "domain": "airtable.com",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "enterprise_tier_exists": "yes",
  "explanation": "Airtable has an Enterprise tier with 'Contact Sales' pricing, offering advanced admin controls, SSO, and dedicated support."
}
```

---

## Valid Values

- `yes` - Enterprise tier exists
- `no` - No enterprise tier

---

## Database Writes

- **raw**: `raw.enterprise_tier_exists_payloads`
- **extracted**: `extracted.company_enterprise_tier_exists`
- **core**: `core.company_enterprise_tier_exists` (upsert on domain)

---

## Notes

- Uses `gemini-3-flash-preview` model
- Defaults to "no" if uncertain
- Fetches and parses pricing page HTML
- Truncates page content to 8000 characters
- Timeout: 60 seconds
