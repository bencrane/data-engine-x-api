# Country Inference

**Endpoint:** `POST /infer_company_country`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-company-country.modal.run`

---

## Prompt

```
Given the following company information, return the headquarters location.

Company Name: {company_name}
Domain: {domain or 'N/A'}
LinkedIn URL: {company_linkedin_url or 'N/A'}

Return a JSON object with city, state, and country fields. Use null for any field you cannot determine.
Example: {"city": "San Francisco", "state": "California", "country": "United States"}
Example: {"city": "London", "state": null, "country": "United Kingdom"}

Return ONLY the JSON object, no other text.
```

---

## Input Payload

```json
{
  "company_name": "Stripe",
  "domain": "stripe.com",
  "company_linkedin_url": "https://www.linkedin.com/company/stripe"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| company_name | string | Yes | Company name |
| domain | string | No | Company website domain |
| company_linkedin_url | string | No | Company LinkedIn page URL |

---

## Sample Output

```json
{
  "success": true,
  "company_name": "Stripe",
  "city": "San Francisco",
  "state": "California",
  "country": "United States",
  "input_tokens": 52,
  "output_tokens": 24,
  "cost_usd": 0.000015
}
```

---

## Notes

- Uses `gemini-3-flash-preview` model
- Returns structured location data (city, state, country)
- Any field may be null if undetermined
- Cost: ~$0.10/1M input tokens, ~$0.40/1M output tokens
