# Money Back Guarantee Inference

**Endpoint:** `POST /infer_money_back_guarantee`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-money-back-guarantee.modal.run`

---

## Prompt

```
Analyze this pricing page content and determine if a money back guarantee is offered.

Company: {company_name}
Pricing Page URL: {pricing_page_url}

Pricing Page Content:
{page_text}

Look for phrases like:
- "Money back guarantee"
- "30-day guarantee"
- "Full refund"
- "Risk-free"
- "Satisfaction guaranteed"
- "No questions asked refund"

Classify as ONE of:
- yes: Money back guarantee or refund policy is mentioned
- no: No money back guarantee mentioned

You must choose yes or no.

Respond in this exact JSON format:
{"money_back_guarantee": "yes|no", "explanation": "1-2 sentence explanation"}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "company_name": "Basecamp",
  "domain": "basecamp.com",
  "pricing_page_url": "https://basecamp.com/pricing"
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
  "domain": "basecamp.com",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "money_back_guarantee": "yes",
  "explanation": "Basecamp offers a 30-day money back guarantee mentioned prominently on their pricing page."
}
```

---

## Valid Values

- `yes` - Money back guarantee offered
- `no` - No money back guarantee

---

## Database Writes

- **raw**: `raw.money_back_guarantee_payloads`
- **extracted**: `extracted.company_money_back_guarantee`
- **core**: `core.company_money_back_guarantee` (upsert on domain)

---

## Notes

- Uses `gemini-3-flash-preview` model
- Defaults to "no" if parsing fails
- Fetches and parses pricing page HTML
- Truncates page content to 8000 characters
- Timeout: 60 seconds
