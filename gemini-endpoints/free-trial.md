# Free Trial Inference

**Endpoint:** `POST /infer_free_trial`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-free-trial.modal.run`

---

## Prompt

```
Analyze this pricing page content and determine if the company offers a free trial.

Company: {company_name}
Pricing Page URL: {pricing_page_url}

Pricing Page Content:
{page_text}

Classify as ONE of:
- yes: Company offers a free trial (self-serve, can start without talking to sales)
- no: No free trial offered (must pay upfront or no self-serve option)
- demo_only: Only offers demos or sales calls, no self-serve free trial

Respond in this exact JSON format:
{"free_trial": "yes|no|demo_only", "explanation": "1-2 sentence explanation"}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "company_name": "Notion",
  "domain": "notion.so",
  "pricing_page_url": "https://www.notion.so/pricing"
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
  "domain": "notion.so",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "free_trial": "yes",
  "explanation": "Notion offers a free Personal plan with unlimited pages and blocks, and all paid plans have a free trial option."
}
```

---

## Valid Values

- `yes` - Free trial available
- `no` - No free trial
- `demo_only` - Only demos/sales calls available

---

## Database Writes

- **raw**: `raw.free_trial_payloads`
- **extracted**: `extracted.company_free_trial`
- **core**: `core.company_free_trial` (upsert on domain)

---

## Notes

- Uses `gemini-3-flash-preview` model
- Fetches and parses pricing page HTML
- Truncates page content to 8000 characters
- Timeout: 60 seconds
