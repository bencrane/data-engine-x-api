# Pricing Model Inference

**Endpoint:** `POST /infer_pricing_model`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-pricing-model.modal.run`

---

## Prompt

```
Analyze this pricing page content and determine the pricing model.

Company: {company_name}
Pricing Page URL: {pricing_page_url}

Pricing Page Content:
{page_text}

Classify as ONE of:
- seat_based: Per user/seat pricing (e.g., $10/user/month)
- usage_based: Pay for what you use (e.g., API calls, storage, transactions)
- flat: Single flat rate for the product
- tiered: Multiple tiers with different features at different price points
- custom: Custom/enterprise pricing only, no standard pricing shown
- multiple: Combination of pricing models (e.g., base fee + per seat + usage)

Respond in this exact JSON format:
{"pricing_model": "seat_based|usage_based|flat|tiered|custom|multiple", "explanation": "1-2 sentence explanation"}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "company_name": "Figma",
  "domain": "figma.com",
  "pricing_page_url": "https://www.figma.com/pricing"
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
  "domain": "figma.com",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "pricing_model": "seat_based",
  "explanation": "Figma charges per editor seat with different tiers (Starter, Professional, Organization, Enterprise) at different per-seat prices."
}
```

---

## Valid Values

- `seat_based` - Per user/seat pricing
- `usage_based` - Pay for usage
- `flat` - Single flat rate
- `tiered` - Multiple feature tiers
- `custom` - Custom pricing only
- `multiple` - Combination of models

---

## Database Writes

- **raw**: `raw.pricing_model_payloads`
- **extracted**: `extracted.company_pricing_model`
- **core**: `core.company_pricing_model` (upsert on domain)

---

## Notes

- Uses `gemini-3-flash-preview` model
- Fetches and parses pricing page HTML
- Truncates page content to 8000 characters
- Timeout: 60 seconds
