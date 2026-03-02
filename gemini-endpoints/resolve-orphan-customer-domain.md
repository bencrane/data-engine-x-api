# Resolve Orphan Customer Domain

**Endpoint:** `POST /resolve_orphan_customer_domain`

**Modal URL:** `https://bencrane--hq-master-data-ingest-resolve-orphan-customer-domain.modal.run`

---

## Prompt

```
You are a B2B company identification expert. Find the website domain for a company given its name and business context.

**Company to find:** "{customer_company_name}"

**Context - this company is a customer of:**
- Vendor: {origin_company_name} ({origin_company_domain})
- Vendor industry: {origin_company_industry}
- Vendor description: {origin_company_description}

**Use this context to disambiguate:**
- Think about what {origin_company_name} sells and what kinds of companies would buy their product/service
- If the customer name is ambiguous (e.g., "Mercury" could be many companies), use the B2B context to pick the most likely match
- A fintech vendor's customer named "Mercury" is probably mercury.com (the banking startup), not a car brand
- Consider common abbreviations: "AWS" = amazon.com, "JPM" = jpmorgan.com, "MSFT" = microsoft.com

**Rules:**
- Return ONLY the bare domain (e.g., "stripe.com", not "https://www.stripe.com")
- If the company is a subsidiary or division, return the parent company's primary domain
- "high" confidence = you found clear evidence this is the company's official domain
- "medium" confidence = likely correct but some ambiguity exists
- "low" confidence = best guess based on name pattern
- If you truly cannot determine the domain, return null for domain

**Return ONLY valid JSON:**
{
  "domain": "example.com",
  "confidence": "high",
  "reason": "Brief explanation"
}
```

---

## Input Payload

```json
{
  "customer_company_name": "Mercury",
  "origin_company_name": "Ramp",
  "origin_company_domain": "ramp.com",
  "origin_company_industry": "Fintech",
  "origin_company_description": "Corporate cards and spend management platform"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| customer_company_name | string | Yes | Name of the customer to look up |
| origin_company_name | string | No | Name of the vendor company |
| origin_company_domain | string | Yes | Domain of the vendor company |
| origin_company_industry | string | No | Industry of vendor (for context) |
| origin_company_description | string | No | Description of vendor (for context) |

---

## Sample Output

```json
{
  "success": true,
  "customer_company_name": "Mercury",
  "origin_company_domain": "ramp.com",
  "domain": "mercury.com",
  "confidence": "high",
  "reason": "Mercury is a fintech startup offering banking for startups, aligns with B2B fintech context",
  "input_tokens": 150,
  "output_tokens": 50,
  "cost_usd": 0.00004
}
```

---

## Confidence Levels

- `high` - Clear evidence of company domain
- `medium` - Likely correct but some ambiguity
- `low` - Best guess based on name
- `none` - Failed to parse response

---

## Database Writes

- **raw**: `raw.resolve_customer_domain_payloads`
- **core**: Updates `core.company_customers` with `customer_domain_source = "gemini-orphan-resolve"`

---

## Notes

- Uses `gemini-2.0-flash` model
- Uses structured JSON output mode (`response_mime_type="application/json"`)
- Temperature: 0.1 (low for consistency)
- Cost: ~$0.10/1M input tokens, ~$0.40/1M output tokens
- Timeout: 60 seconds
