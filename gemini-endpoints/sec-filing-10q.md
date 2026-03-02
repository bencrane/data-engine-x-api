# SEC 10-Q Filing Analysis

**Endpoint:** `POST /analyze_sec_10q`

**Modal URL:** `https://bencrane--hq-master-data-ingest-analyze-sec-10q.modal.run`

---

## Prompt

```
You are analyzing an SEC 10-Q quarterly report for a sales team preparing for a call with this company.

Extract and summarize the following in a structured format:

1. **Quarter Highlights** (2-3 sentences)
   - What happened this quarter? Any notable changes?

2. **Financial Performance**
   - Revenue this quarter
   - QoQ and YoY comparison
   - Any guidance updates?

3. **Recent Developments** (bullet points)
   - New products, partnerships, or initiatives mentioned?
   - Any leadership changes?

4. **Challenges or Concerns**
   - What headwinds are they facing?

5. **Sales Talking Points** (2-3 actionable insights)
   - What's timely and relevant to bring up in a sales call right now?

Keep responses concise and actionable. Focus on recent developments and timely insights.
```

---

## Input Payload

```json
{
  "document_url": "https://www.sec.gov/Archives/edgar/data/1652044/000165204424000022/goog-20240630.htm",
  "domain": "google.com",
  "company_name": "Alphabet Inc."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| document_url | string | Yes | URL of SEC 10-Q filing |
| domain | string | No | Company website domain |
| company_name | string | No | Company name |

---

## Sample Output

```json
{
  "success": true,
  "filing_type": "10-Q",
  "document_url": "https://www.sec.gov/Archives/edgar/data/1652044/000165204424000022/goog-20240630.htm",
  "domain": "google.com",
  "company_name": "Alphabet Inc.",
  "analysis": "## Quarter Highlights\nAlphabet reported strong Q2 results driven by Search and Cloud growth. YouTube advertising also showed recovery compared to prior quarters.\n\n## Financial Performance\n- Revenue: $84.7 billion (+14% YoY)\n- Google Cloud: $10.3 billion (+29% YoY)\n- Operating income: $27.4 billion\n- Raised full-year guidance for Cloud segment\n\n## Recent Developments\n- Launched Gemini AI across Google products\n- Expanded Cloud AI offerings for enterprise\n- Announced $1B investment in data center in Texas\n\n## Challenges or Concerns\n- Ongoing antitrust litigation\n- AI infrastructure costs impacting margins\n- Competition from Microsoft/OpenAI in AI space\n\n## Sales Talking Points\n- Cloud is their fastest-growing segment - they're actively expanding enterprise capabilities\n- Heavy AI investment = opportunity for AI-adjacent tools and services\n- Data center expansion signals infrastructure modernization priorities"
}
```

---

## Notes

- Uses `gemini-2.0-flash` model
- Fetches SEC filing HTML directly
- Truncates filing content to 100,000 characters
- Prompts stored in `prompts/sec_filings.py` for easy iteration
- Timeout: 300 seconds (5 minutes)
