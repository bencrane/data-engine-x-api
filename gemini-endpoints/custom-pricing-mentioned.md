# Custom Pricing Mentioned Inference

**Endpoint:** `POST /infer_custom_pricing_mentioned`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-custom-pricing-mentioned.modal.run`

---

## Prompt

```
Analyze this pricing page content and determine if custom pricing is mentioned.

Company: {company_name}
Pricing Page URL: {pricing_page_url}

Pricing Page Content:
{page_text}

Look for phrases like:
- "Custom pricing"
- "Contact sales"
- "Contact us for pricing"
- "Get a quote"
- "Request pricing"
- "Talk to sales"
- "Custom plan"
- "Tailored pricing"

Classify as ONE of:
- yes: Custom pricing or contact sales option is mentioned
- no: No custom pricing mentioned, only fixed pricing shown

You must choose yes or no.

Respond in this exact JSON format:
{"custom_pricing_mentioned": "yes|no", "explanation": "1-2 sentence explanation"}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "company_name": "Intercom",
  "domain": "intercom.com",
  "pricing_page_url": "https://www.intercom.com/pricing"
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
  "domain": "intercom.com",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "custom_pricing_mentioned": "yes",
  "explanation": "Intercom has 'Talk to Sales' CTAs and mentions custom pricing for larger deployments."
}
```

---

## Valid Values

- `yes` - Custom pricing mentioned
- `no` - Only fixed pricing

---

## Database Writes

- **raw**: `raw.custom_pricing_mentioned_payloads`
- **extracted**: `extracted.company_custom_pricing_mentioned`
- **core**: `core.company_custom_pricing_mentioned` (upsert on domain)

---

## Notes

- Uses `gemini-3-flash-preview` model
- Defaults to "no" if parsing fails
- Fetches and parses pricing page HTML
- Truncates page content to 8000 characters
- Timeout: 60 seconds
