# Annual Commitment Required Inference

**Endpoint:** `POST /infer_annual_commitment`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-annual-commitment.modal.run`

---

## Prompt

```
Analyze this pricing page content and determine if an annual commitment is required.

Company: {company_name}
Pricing Page URL: {pricing_page_url}

Pricing Page Content:
{page_text}

Look for indicators like:
- "Annual contract required"
- "Billed annually only"
- "Minimum 12-month commitment"
- Only annual pricing shown with no monthly option
- Monthly option available (suggests no annual commitment required)

Classify as ONE of:
- yes: Annual commitment is clearly required (no month-to-month option)
- no: Month-to-month option is available, no annual commitment required
- unclear: Commitment terms are not mentioned on the pricing page

Respond in this exact JSON format:
{"annual_commitment_required": "yes|no|unclear", "explanation": "1-2 sentence explanation"}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "company_name": "Zendesk",
  "domain": "zendesk.com",
  "pricing_page_url": "https://www.zendesk.com/pricing"
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
  "domain": "zendesk.com",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "annual_commitment_required": "no",
  "explanation": "Zendesk offers both monthly and annual billing options, with a toggle to switch between them on the pricing page."
}
```

---

## Valid Values

- `yes` - Annual commitment required
- `no` - Month-to-month available
- `unclear` - Terms not mentioned

---

## Database Writes

- **raw**: `raw.annual_commitment_required_payloads`
- **extracted**: `extracted.company_annual_commitment_required`
- **core**: `core.company_annual_commitment_required` (upsert on domain)

---

## Notes

- Uses `gemini-3-flash-preview` model
- Fetches and parses pricing page HTML
- Truncates page content to 8000 characters
- Timeout: 60 seconds
