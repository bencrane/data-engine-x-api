# Industry Inference

**Endpoint:** `POST /infer_company_industry`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-company-industry.modal.run`

---

## Prompt

```
Given the following company information, return the most likely industry or industries (up to 3).

Company Name: {company_name}
Description: {short_description or 'N/A'}

Return only the industry names, one per line. Be specific but use common industry terminology.
```

---

## Input Payload

```json
{
  "company_name": "Stripe",
  "domain": "stripe.com",
  "short_description": "Online payment processing platform for internet businesses"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| company_name | string | Yes | Company name |
| domain | string | No | Company website domain |
| short_description | string | No | Brief company description |

---

## Sample Output

```json
{
  "success": true,
  "company_name": "Stripe",
  "gemini_raw": [
    "Financial Technology (Fintech)",
    "Payment Processing",
    "Software as a Service (SaaS)"
  ],
  "matched_industries": [
    {
      "gemini_guess": "Financial Technology (Fintech)",
      "matched_industry": "Financial Services",
      "match_type": "fuzzy",
      "match_word": "Financial"
    },
    {
      "gemini_guess": "Payment Processing",
      "matched_industry": "Payment Processing",
      "match_type": "exact"
    }
  ],
  "best_match": "Financial Services",
  "input_tokens": 45,
  "output_tokens": 28,
  "cost_usd": 0.000016
}
```

---

## Notes

- Uses `gemini-3-flash-preview` model
- Fuzzy matches against `reference.industry_lookup` table
- Returns up to 3 industry matches
- Cost: ~$0.10/1M input tokens, ~$0.40/1M output tokens
