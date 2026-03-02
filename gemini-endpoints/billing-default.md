# Billing Default Inference

**Endpoint:** `POST /infer_billing_default`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-billing-default.modal.run`

---

## Prompt

```
Analyze this pricing page content and determine the default billing period.

Company: {company_name}
Pricing Page URL: {pricing_page_url}

Pricing Page Content:
{page_text}

Classify as ONE of:
- monthly: Only monthly billing shown, or monthly is the default/emphasized option
- annual: Only annual billing shown, or annual is the default/emphasized option
- both_annual_emphasized: Both options available but annual is pre-selected, highlighted, or shows "save X%" prominently
- both_monthly_emphasized: Both options available but monthly is pre-selected or shown first without annual emphasis

Respond in this exact JSON format:
{"billing_default": "monthly|annual|both_annual_emphasized|both_monthly_emphasized", "explanation": "1-2 sentence explanation"}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "company_name": "Asana",
  "domain": "asana.com",
  "pricing_page_url": "https://asana.com/pricing"
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
  "domain": "asana.com",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "billing_default": "both_annual_emphasized",
  "explanation": "Asana shows both monthly and annual options with the annual toggle pre-selected and 'Save' badge highlighting annual discounts."
}
```

---

## Valid Values

- `monthly` - Monthly only or emphasized
- `annual` - Annual only or emphasized
- `both_annual_emphasized` - Both available, annual highlighted
- `both_monthly_emphasized` - Both available, monthly default

---

## Database Writes

- **raw**: `raw.billing_default_payloads`
- **extracted**: `extracted.company_billing_default`
- **core**: `core.company_billing_default` (upsert on domain)

---

## Notes

- Uses `gemini-3-flash-preview` model
- Fetches and parses pricing page HTML
- Truncates page content to 8000 characters
- Timeout: 60 seconds
