# Minimum Seats Inference

**Endpoint:** `POST /infer_minimum_seats`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-minimum-seats.modal.run`

---

## Prompt

```
Analyze this pricing page content and determine if minimum seats/users are required.

Company: {company_name}
Pricing Page URL: {pricing_page_url}

Pricing Page Content:
{page_text}

Look for phrases like:
- "Minimum X seats"
- "Starts at X users"
- "Minimum purchase of X licenses"
- "X seat minimum"
- "Billed for minimum of X users"

Classify as ONE of:
- yes: Minimum seats/users requirement is mentioned
- no: Single user/seat purchase is explicitly allowed
- not_mentioned: No mention of seat minimums either way

Respond in this exact JSON format:
{"minimum_seats": "yes|no|not_mentioned", "explanation": "1-2 sentence explanation"}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "company_name": "Lattice",
  "domain": "lattice.com",
  "pricing_page_url": "https://lattice.com/pricing"
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
  "domain": "lattice.com",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "minimum_seats": "yes",
  "explanation": "Lattice requires a minimum of 25 seats for their People Management platform."
}
```

---

## Valid Values

- `yes` - Minimum seats required
- `no` - Single seat allowed
- `not_mentioned` - No information either way

---

## Database Writes

- **raw**: `raw.minimum_seats_payloads`
- **extracted**: `extracted.company_minimum_seats`
- **core**: `core.company_minimum_seats` (upsert on domain)

---

## Notes

- Uses `gemini-3-flash-preview` model
- Fetches and parses pricing page HTML
- Truncates page content to 8000 characters
- Timeout: 60 seconds
