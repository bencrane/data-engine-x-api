# Number of Tiers Inference

**Endpoint:** `POST /infer_number_of_tiers`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-number-of-tiers.modal.run`

---

## Prompt

```
Analyze this pricing page content and count the number of distinct pricing tiers.

Company: {company_name}
Pricing Page URL: {pricing_page_url}

Pricing Page Content:
{page_text}

Count the pricing tiers (e.g., Free, Starter, Pro, Enterprise). Do NOT count "Contact Sales" or "Custom" as a tier unless it has a specific price.

Classify as ONE of:
- 1: Single tier/plan
- 2: Two tiers
- 3: Three tiers
- 4+: Four or more tiers

Respond in this exact JSON format:
{"number_of_tiers": "1|2|3|4+", "explanation": "1-2 sentence explanation listing the tier names"}

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
  "number_of_tiers": "4+",
  "explanation": "Notion has 4 tiers: Free, Plus, Business, and Enterprise."
}
```

---

## Valid Values

- `1` - Single tier
- `2` - Two tiers
- `3` - Three tiers
- `4+` - Four or more tiers

---

## Database Writes

- **raw**: `raw.number_of_tiers_payloads`
- **extracted**: `extracted.company_number_of_tiers`
- **core**: `core.company_number_of_tiers` (upsert on domain)

---

## Notes

- Uses `gemini-3-flash-preview` model
- Does NOT count "Contact Sales" or "Custom" as a tier unless priced
- Fetches and parses pricing page HTML
- Truncates page content to 8000 characters
- Timeout: 60 seconds
