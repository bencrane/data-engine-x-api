# Sales Motion Inference

**Endpoint:** `POST /infer_sales_motion`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-sales-motion.modal.run`

---

## Prompt

```
Analyze this pricing page content and classify the company's sales motion.

Company: {company_name}
Pricing Page URL: {pricing_page_url}

Pricing Page Content:
{page_text}

Classify the sales motion as ONE of:
- self_serve: Customers can sign up, see pricing, and pay online without talking to sales
- sales_led: Customers must contact sales, book a demo, or request a quote to get pricing
- hybrid: Company offers both self-serve options AND sales-assisted options

Also determine if there is a "Contact Sales" CTA:
- yes: Page has "Contact Sales", "Talk to Sales", "Contact Us", "Get a Demo", "Book a Demo", or similar CTA
- no: No contact sales CTA visible

Respond in this exact JSON format:
{"sales_motion": "self_serve|sales_led|hybrid", "contact_sales_cta": "yes|no", "explanation": "1-2 sentence explanation"}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "company_name": "Salesforce",
  "domain": "salesforce.com",
  "pricing_page_url": "https://www.salesforce.com/pricing"
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
  "domain": "salesforce.com",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "sales_motion": "hybrid",
  "contact_sales_cta": "yes",
  "explanation": "Salesforce shows pricing for smaller tiers but emphasizes 'Contact Sales' for enterprise and offers free trials alongside demo requests."
}
```

---

## Valid Values

**sales_motion:**
- `self_serve` - Fully self-service
- `sales_led` - Must contact sales
- `hybrid` - Both options available

**contact_sales_cta:**
- `yes` - Contact sales CTA present
- `no` - No contact sales CTA

---

## Database Writes

- **raw**: `raw.sales_motion_payloads`
- **extracted**: `extracted.company_sales_motion`
- **core**: `core.company_sales_motion` (upsert on domain)

---

## Notes

- Uses `gemini-3-flash-preview` model
- Fetches and parses pricing page HTML
- Truncates page content to 8000 characters
- Timeout: 60 seconds
