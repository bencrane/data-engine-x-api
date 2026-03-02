# Ingest Orphan Customer Domain

**Endpoint:** `POST /ingest_orphan_customer_domain`

**Modal URL:** `https://bencrane--hq-master-data-ingest-ingest-orphan-customer-domain.modal.run`

---

## Purpose

Stores the result from Gemini domain inference for orphan customers (customers with no case study URL). This is an **ingestion** endpoint that receives the result of a domain resolution and writes it to the database.

---

## Input Payload

```json
{
  "domain": "javelintechnologies.com",
  "reason": "Aurea Software was acquired by ESW Capital...",
  "success": true,
  "cost_usd": 0.00007,
  "confidence": "high",
  "input_tokens": 412,
  "output_tokens": 71,
  "customer_company_name": "Aurea Software",
  "origin_company_domain": "12twenty.com"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| customer_company_name | string | Yes | Customer company name |
| origin_company_domain | string | Yes | Domain of vendor company |
| domain | string | No | Inferred customer domain |
| confidence | string | No | Confidence level (high/medium/low) |
| reason | string | No | Explanation for inference |
| success | boolean | No | Whether inference succeeded |
| input_tokens | integer | No | Gemini input tokens used |
| output_tokens | integer | No | Gemini output tokens used |
| cost_usd | float | No | Gemini API cost |

---

## Sample Output

```json
{
  "success": true,
  "raw_id": "550e8400-e29b-41d4-a716-446655440000",
  "extracted_id": "661f9500-f30c-52e5-b827-557766550111"
}
```

---

## Database Writes

- **raw**: `raw.orphan_customer_domain_payloads`
- **extracted**: `extracted.orphan_customer_domain`
- **core**: Updates `core.company_customers` with:
  - `customer_domain` = inferred domain
  - `customer_domain_source` = "gemini-orphan-resolve"
  - Only updates where `customer_domain` is currently NULL

---

## Notes

- This is an ingestion endpoint, not an inference endpoint
- Pairs with `resolve_orphan_customer_domain` endpoint which performs the actual Gemini inference
- Typical workflow: Call `resolve_orphan_customer_domain` → get result → send to `ingest_orphan_customer_domain`
- Timeout: 30 seconds
