# Employee Range Inference

**Endpoint:** `POST /infer_company_employee_range`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-company-employee-range.modal.run`

---

## Prompt

```
Given the following company information, estimate the employee count and classify it into one of these ranges:
1-10, 11-50, 51-100, 101-250, 251-500, 501-1000, 1001-5000, 5001-10000, 10001+

Company Name: {company_name}
Domain: {domain or 'N/A'}
LinkedIn URL: {company_linkedin_url or 'N/A'}

Return ONLY one of the exact ranges listed above (e.g., "51-100" or "1001-5000"). If you cannot determine, return "Unknown".
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
| domain | string | Yes | Company website domain |
| company_linkedin_url | string | No | Company LinkedIn page URL |

---

## Sample Output

```json
{
  "success": true,
  "company_name": "Stripe",
  "employee_range": "5001-10000",
  "input_tokens": 48,
  "output_tokens": 8,
  "cost_usd": 0.000012
}
```

---

## Valid Ranges

- `1-10`
- `11-50`
- `51-100`
- `101-250`
- `251-500`
- `501-1000`
- `1001-5000`
- `5001-10000`
- `10001+`

---

## Notes

- Uses `gemini-3-flash-preview` model
- Returns `null` for employee_range if response doesn't match valid ranges
- Cost: ~$0.15/1M input tokens, ~$0.60/1M output tokens
