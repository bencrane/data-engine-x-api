# Security Compliance Gating Inference

**Endpoint:** `POST /infer_security_gating`

**Modal URL:** `https://bencrane--hq-master-data-ingest-infer-security-gating.modal.run`

---

## Prompt

```
Analyze this pricing page content and determine if security/compliance features are gated to higher tiers.

Company: {company_name}
Pricing Page URL: {pricing_page_url}

Pricing Page Content:
{page_text}

Security/compliance features include: SSO, SAML, SOC2, HIPAA, GDPR compliance, audit logs, role-based access control (RBAC), custom security reviews, dedicated support, SLAs, etc.

Classify as ONE of:
- yes: Security/compliance features are clearly gated to higher tiers (e.g., SSO only on Enterprise)
- no: Security/compliance features are available on all tiers or included in base plan
- not_mentioned: Pricing page doesn't discuss security/compliance features

Respond in this exact JSON format:
{"security_compliance_gating": "yes|no|not_mentioned", "explanation": "1-2 sentence explanation"}

Only return the JSON, nothing else.
```

---

## Input Payload

```json
{
  "company_name": "Slack",
  "domain": "slack.com",
  "pricing_page_url": "https://slack.com/pricing"
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
  "domain": "slack.com",
  "raw_payload_id": "550e8400-e29b-41d4-a716-446655440000",
  "security_compliance_gating": "yes",
  "explanation": "Slack gates SSO/SAML, HIPAA compliance, and custom security reviews to Enterprise Grid tier only."
}
```

---

## Valid Values

- `yes` - Security features gated to higher tiers
- `no` - Security features available on all tiers
- `not_mentioned` - No security features discussed

---

## Database Writes

- **raw**: `raw.security_compliance_gating_payloads`
- **extracted**: `extracted.company_security_compliance_gating`
- **core**: `core.company_security_compliance_gating` (upsert on domain)

---

## Notes

- Uses `gemini-3-flash-preview` model
- Fetches and parses pricing page HTML
- Truncates page content to 8000 characters
- Timeout: 60 seconds
