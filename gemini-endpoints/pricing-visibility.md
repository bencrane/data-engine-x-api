# Pricing Visibility Inference

**Endpoint:** `POST /infer_pricing_visibility`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-pricing-visibility.modal.run`

---

## Prompt

```
Analyze this pricing page content and determine pricing visibility.

Company: {company_name}
Pricing Page URL: {pricing_page_url}

Pricing Page Content:
{page_text}

Classify as ONE of:
- public: Full pricing is publicly visible (specific dollar amounts, all tiers shown)
- hidden: No pricing shown, must contact sales or request a quote
- partial: Some pricing shown but not complete (e.g., "starting at $X", only some tiers priced, or "contact us for enterprise")

Respond in this exact JSON format:
{"pricing_visibility": "public|hidden|partial", "explanation": "1-2 sentence explanation"}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "company_name": "Slack",
  "domain": "slack.com",
  "pricing_page_url": "https://slack.com/pricing"
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
  "domain": "slack.com",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "pricing_visibility": "partial",
  "explanation": "Slack shows pricing for Free, Pro, and Business+ tiers but requires contacting sales for Enterprise Grid pricing."
}
```

---

## Valid Values

- `public` - All pricing visible
- `hidden` - No pricing shown
- `partial` - Some pricing visible

---

## Database Writes

- **raw**: `raw.pricing_visibility_payloads`
- **extracted**: `extracted.company_pricing_visibility`
- **core**: `core.company_pricing_visibility` (upsert on domain)

---

## Notes

- Uses `gemini-3-flash-preview` model
- Fetches and parses pricing page HTML
- Truncates page content to 8000 characters
- Timeout: 60 seconds
