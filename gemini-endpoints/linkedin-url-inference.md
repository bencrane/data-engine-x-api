# LinkedIn URL Inference

**Endpoint:** `POST /infer_company_linkedin_url`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-company-linkedin-url.modal.run`

---

## Prompt

```
Given the following company information, return the most likely LinkedIn company page URL.

Company Name: {company_name}
Domain: {domain or 'N/A'}

Return ONLY the full LinkedIn URL in the format: https://www.linkedin.com/company/[company-slug]
If you cannot determine the LinkedIn URL, return "Unknown".
Do not include any other text.
```

---

## Input Payload

```json
{
  "company_name": "Stripe",
  "domain": "stripe.com"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| company_name | string | Yes | Company name |
| domain | string | No | Company website domain |

---

## Sample Output

```json
{
  "success": true,
  "company_name": "Stripe",
  "linkedin_url": "https://www.linkedin.com/company/stripe",
  "input_tokens": 38,
  "output_tokens": 12,
  "cost_usd": 0.000009
}
```

---

## Notes

- Uses `gemini-3-flash-preview` model
- Returns `null` if URL doesn't match LinkedIn format
- Validates URL starts with `https://www.linkedin.com/company/` or `https://linkedin.com/company/`
- Cost: ~$0.10/1M input tokens, ~$0.40/1M output tokens
