# Infer Customer Domain

**Endpoint:** `POST /infer_customer_domain`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-customer-domain.modal.run`

---

## Prompt

```
Find the website domain for this company.

Company to find: "{customer_company_name}"

Context (this company is a customer of):
{context}

Search for the company's official website domain. Use the context to help disambiguate -
for example if the origin company is a B2B SaaS company, the customer is likely a business, not a consumer brand with the same name.

Return JSON only with 1-3 most likely domain candidates:
{
  "candidates": [
    {"domain": "example.com", "confidence": "high/medium/low", "reason": "Brief explanation"}
  ]
}

Rules:
- Return actual domains (e.g., "carrefour.it") not URLs
- If you can't find a likely domain, return empty candidates array
- "high" confidence = you found clear evidence this is the company's domain
- "medium" confidence = likely but not 100% certain
- "low" confidence = best guess based on name pattern

Return only valid JSON, nothing else.
```

---

## Input Payload

```json
{
  "customer_company_name": "Carrefour Italy",
  "origin_company_name": "Appier",
  "origin_company_domain": "appier.com",
  "origin_company_description": "Appier is an AI-powered marketing platform",
  "origin_company_industry": "Marketing Technology",
  "case_study_url": "https://appier.com/success-stories/carrefour"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| customer_company_name | string | Yes | Name of customer to look up |
| origin_company_name | string | No | Name of vendor company |
| origin_company_domain | string | No | Domain of vendor company |
| origin_company_description | string | No | Description of vendor |
| origin_company_industry | string | No | Industry of vendor |
| case_study_url | string | No | URL of case study |

---

## Sample Output

```json
{
  "success": true,
  "customer_company_name": "Carrefour Italy",
  "candidates": [
    {"domain": "carrefour.it", "confidence": "high", "reason": "Italian subsidiary of Carrefour"},
    {"domain": "carrefour.com", "confidence": "medium", "reason": "Parent company domain"}
  ],
  "input_tokens": 150,
  "output_tokens": 50,
  "cost_usd": 0.00004
}
```

---

## Confidence Levels

- `high` - Clear evidence of company domain
- `medium` - Likely but not 100% certain
- `low` - Best guess based on name

---

## Notes

- Uses `gemini-2.0-flash` model
- Returns 1-3 domain candidates
- Builds context from all provided fields
- Does NOT write to database (read-only lookup)
- Cost: ~$0.10/1M input tokens, ~$0.40/1M output tokens
- Timeout: 60 seconds
