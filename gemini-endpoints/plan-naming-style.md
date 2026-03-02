# Plan Naming Style Inference

**Endpoint:** `POST /infer_plan_naming_style`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-plan-naming-style.modal.run`

---

## Prompt

```
Analyze this pricing page content and determine the plan naming style.

Company: {company_name}
Pricing Page URL: {pricing_page_url}

Pricing Page Content:
{page_text}

Classify the plan naming style as ONE of:
- generic: Standard tier names like "Free", "Basic", "Starter", "Pro", "Plus", "Premium", "Enterprise", "Growth"
- persona_based: Named after target users like "Individual", "Team", "Business", "Developer", "Agency", "Freelancer", "Small Business"
- feature_based: Named after key features or capabilities like "Analytics", "Automation", "Scale", "Core", "Complete"
- other: Creative, branded, or unique names that don't fit above categories

Respond in this exact JSON format:
{"plan_naming_style": "generic|persona_based|feature_based|other", "explanation": "1-2 sentence explanation listing the plan names"}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "company_name": "Mailchimp",
  "domain": "mailchimp.com",
  "pricing_page_url": "https://mailchimp.com/pricing"
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
  "domain": "mailchimp.com",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "plan_naming_style": "generic",
  "explanation": "Mailchimp uses standard tier names: Free, Essentials, Standard, and Premium."
}
```

---

## Valid Values

- `generic` - Standard tier names (Free, Pro, Enterprise)
- `persona_based` - Named after users (Team, Developer, Agency)
- `feature_based` - Named after features (Analytics, Scale)
- `other` - Creative/branded names

---

## Database Writes

- **raw**: `raw.plan_naming_style_payloads`
- **extracted**: `extracted.company_plan_naming_style`
- **core**: `core.company_plan_naming_style` (upsert on domain)

---

## Notes

- Uses `gemini-3-flash-preview` model
- Fetches and parses pricing page HTML
- Truncates page content to 8000 characters
- Timeout: 60 seconds
