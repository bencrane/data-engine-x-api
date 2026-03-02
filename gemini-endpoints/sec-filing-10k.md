# SEC 10-K Filing Analysis

**Endpoint:** `POST /analyze_sec_10k`

**Modal URL:** `https://bencrane--hq-master-data-ingest-analyze-sec-10k.modal.run`

---

## Prompt

```
You are analyzing an SEC 10-K annual report for a sales team preparing for a call with this company.

Extract and summarize the following in a structured format:

1. **Business Overview** (2-3 sentences)
   - What does this company do? Who are their customers?

2. **Key Financial Metrics**
   - Revenue (latest year)
   - YoY growth %
   - Net income/loss
   - Cash position

3. **Strategic Priorities** (bullet points)
   - What are they focused on for the next 1-2 years?

4. **Risk Factors** (top 3 most relevant for a sales conversation)
   - What challenges are they facing?

5. **Technology & Infrastructure** (if mentioned)
   - What tech stack, platforms, or infrastructure do they discuss?

6. **Sales Talking Points** (2-3 actionable insights)
   - Based on this filing, what would be smart things to mention in a sales call?

Keep responses concise and actionable. Focus on what matters for a sales conversation.
```

---

## Input Payload

```json
{
  "document_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
  "domain": "apple.com",
  "company_name": "Apple Inc."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| document_url | string | Yes | URL of SEC 10-K filing |
| domain | string | No | Company website domain |
| company_name | string | No | Company name |

---

## Sample Output

```json
{
  "success": true,
  "filing_type": "10-K",
  "document_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
  "domain": "apple.com",
  "company_name": "Apple Inc.",
  "analysis": "## Business Overview\nApple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories. Their primary revenue comes from iPhone sales, with services becoming an increasingly significant segment.\n\n## Key Financial Metrics\n- Revenue: $394.3 billion\n- YoY Growth: +8.1%\n- Net Income: $96.9 billion\n- Cash Position: $61.6 billion\n\n## Strategic Priorities\n- Expand services revenue (App Store, Apple Music, iCloud)\n- Accelerate AI/ML integration across product lines\n- Grow wearables and home accessories segment\n- Increase geographic diversification\n\n## Risk Factors\n1. Supply chain concentration in Asia\n2. Intense competition in smartphone market\n3. Regulatory scrutiny of App Store practices\n\n## Technology & Infrastructure\n- Custom silicon (M-series chips) for Macs\n- Proprietary iOS, macOS, watchOS ecosystems\n- Major investments in data centers for services\n\n## Sales Talking Points\n- Their services business is growing faster than hardware - focus on solutions that enhance customer engagement\n- They're investing heavily in AI - position any AI-adjacent offerings\n- Supply chain diversification is a priority - relevant for enterprise vendors"
}
```

---

## Notes

- Uses `gemini-2.0-flash` model
- Fetches SEC filing HTML directly
- Truncates filing content to 100,000 characters
- Prompts stored in `prompts/sec_filings.py` for easy iteration
- Timeout: 300 seconds (5 minutes)
- User-Agent: `HQ Master Data ben@revenueinfra.com`
