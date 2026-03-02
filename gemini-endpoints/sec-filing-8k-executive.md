# SEC 8-K Executive Changes Analysis

**Endpoint:** `POST /analyze_sec_8k_executive`

**Modal URL:** `https://bencrane--hq-master-data-ingest-analyze-sec-8k-executive.modal.run`

---

## Prompt

```
You are analyzing an SEC 8-K filing about executive changes for a sales team.

Extract:

1. **Who left?** (name, title, effective date)
2. **Who joined?** (name, title, background if mentioned)
3. **Why?** (reason given, if any)
4. **Sales Implication** (1-2 sentences)
   - Is this a good time to reach out? New decision maker? Transition period?

Keep it brief and actionable.
```

---

## Input Payload

```json
{
  "document_url": "https://www.sec.gov/Archives/edgar/data/12345/0001234567890-25-001234.htm",
  "domain": "example.com",
  "company_name": "Example Corp"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| document_url | string | Yes | URL of SEC 8-K filing |
| domain | string | No | Company website domain |
| company_name | string | No | Company name |

---

## Sample Output

```json
{
  "success": true,
  "filing_type": "8-K-executive",
  "document_url": "https://www.sec.gov/Archives/edgar/data/12345/0001234567890-25-001234.htm",
  "domain": "example.com",
  "company_name": "Example Corp",
  "analysis": "## Who Left?\n- **John Smith**, Chief Technology Officer\n- Effective Date: March 15, 2025\n\n## Who Joined?\n- **Sarah Johnson**, Chief Technology Officer\n- Background: Previously VP of Engineering at Google Cloud, 15+ years in enterprise software\n\n## Why?\n- John Smith is retiring after 12 years with the company\n- No unusual circumstances mentioned\n\n## Sales Implication\nExcellent time to reach out. New CTO with Google Cloud background suggests enterprise cloud and AI priorities. Consider positioning cloud-native solutions. Allow 30-60 days for transition before expecting major decisions."
}
```

---

## Notes

- Uses `gemini-2.0-flash` model
- Fetches SEC filing HTML directly
- Truncates filing content to 100,000 characters
- Prompts stored in `prompts/sec_filings.py` for easy iteration
- Timeout: 300 seconds (5 minutes)
