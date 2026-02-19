# Data Engine X — Capabilities & GTM Use Cases

What we can do, who it serves, and how the pieces connect.

---

## The Core Idea

Give us a company domain (or a name, or a DOT number, or a zip code) and we return everything you need to run intelligent outbound — enriched company profiles, decision-maker contacts with verified emails, competitive intelligence, revenue signals, hiring trends, and buying triggers from government filings. All assembled automatically through configurable workflows.

---

## What We Can Do For a Client

### 1. Enrich Their CRM / TAM

**Starting point:** Client gives us a list of company domains.

**What we return:**
- Company profile: name, industry, employee count, LinkedIn, headquarters, description, revenue range, founded year
- Technology stack (what's on their website): analytics, CRM, hosting, frameworks, CDN
- Technology stack (what they hire for): programming languages, databases, tools — with confidence scores and trend data
- Hiring signals: total open jobs, jobs posted in last 30 days, recent job titles
- Pricing intelligence: pricing model (seat-based, usage, flat), free trial availability, sales motion (self-serve vs sales-led), number of tiers, enterprise tier, billing default, add-ons, minimum seats
- G2 review page URL
- Pricing page URL
- VC funding status: has raised or not, investor names, founded date
- Card transaction revenue (for consumer-facing businesses): annual revenue, monthly trends, YoY growth, market rank, transaction counts
- Ecommerce store data (for Shopify/BigCommerce businesses): platform, plan, estimated monthly sales, installed apps, product count, global rank
- SEC filing analysis (for public companies): 10-K annual report summary, 10-Q quarterly summary, 8-K executive change alerts — all AI-analyzed for sales talking points
- Court filings check: any active lawsuits or bankruptcy proceedings

---

### 2. Find Decision-Makers and Get Their Contact Info

**Starting point:** We already enriched the company (or it's part of a workflow).

**What we return:**
- People at the company: names, titles, LinkedIn URLs
- Filtered by role: VP, Director, C-level, or specific title keywords
- Filtered by department: Sales, Marketing, Engineering, etc.
- Full person profile: seniority, department, work history, education, skills, bio
- Verified work email (with deliverability status: safe, catch-all, risky)
- Mobile phone number
- For construction: contractor employees with direct email, phone, LinkedIn
- For properties: resident/owner data with name, email, phone, net worth, income range

---

### 3. Discover New Targets (Not Just Enrich Known Ones)

**Starting point:** Client describes who they want to reach.

**What we can discover:**
- Companies using specific technologies ("find all companies using Salesforce that are hiring data engineers")
- Companies by hiring patterns ("who posted VP of Sales roles in the last 30 days")
- Ecommerce stores by platform, revenue, country, installed apps
- FMCSA carriers by name (trucking companies)
- Building permits by location, date, type, property value, contractor classification
- Contractors by geography, permit activity, specialization
- Bankruptcy filings by date range (companies in financial distress)
- Companies similar to a given company (lookalike targeting)
- Companies that are competitors of a given company
- Companies that are customers of a given company (from our database)

---

### 4. Mine Relationship Intelligence

**Starting point:** We know a target company. We dig deeper.

**What we can surface:**
- **Their customers** — names, domains, LinkedIn URLs of companies that buy from them
- **Their competitors** — direct market rivals with domains and LinkedIn
- **Similar companies** — lookalikes with similarity scores
- **Former employees (alumni)** — people who used to work there, where they are now, what they do now, what they did before
- **Case study champions** — people featured in their case studies, with their current company, title, and the case study URL
- **Champion testimonials** — the actual quotes from case studies, attributed to specific people
- **VC investors** — which funds backed them

**Why this matters for outbound:** "Hey Sarah, I noticed you were an AE at Salesforce before joining Stripe. We work with 3 of Salesforce's customers..." is a fundamentally different email than "Hey, we sell X."

---

### 5. Detect Buying Triggers

**Starting point:** We monitor public data sources for change events.

**What we detect:**

**Trucking (FMCSA):**
- New carrier registration (needs insurance, ELD, fuel cards, compliance — immediately)
- Fleet size growth (needs more trucks, drivers, fuel, maintenance)
- Operating authority granted/suspended/revoked
- Insurance changes
- Out-of-service orders lifted (back in business, needs vendors)
- Process agent changes (BOC3 — new carrier setup signal)

**Construction (Shovels):**
- New building permits filed (needs materials, contractors, financing)
- Permit type signals: solar installation, HVAC, roofing, electrical, plumbing
- Property type: residential vs commercial vs industrial
- Contractor activity changes (growing vs shrinking permit volume)

**Legal (CourtListener):**
- Bankruptcy filings (Chapter 7, Chapter 11)
- Court case activity for specific companies (risk signal)
- Executive change 8-K filings (new decision-maker = outreach window)

**B2B SaaS (TheirStack + entity snapshots):**
- Hiring acceleration (jobs posted last 30 days vs total)
- New technology adoption (first seen using Kubernetes, Snowflake, etc.)
- Technology abandonment (stopped mentioning a tool in job postings)
- Employee count changes over time
- Revenue/funding changes

---

### 6. Geographic Market Intelligence

**Starting point:** Client wants to understand a market before entering.

**What we provide:**
- City/county/zipcode/jurisdiction-level permit metrics (monthly trends, current snapshot)
- Geographic market details
- Address-level property data and metrics
- Market search: find cities, counties, zipcodes matching criteria

**Use case:** "Show me all counties in Texas where solar permit volume grew 50%+ last year" → client targets those markets for solar installer outbound.

---

## Verticals We Cover

| Vertical | Data Sources | Key Capability |
|---|---|---|
| **B2B SaaS** | Prospeo, BlitzAPI, CompanyEnrich, LeadMagic, TheirStack, Adyntel | Full company + person enrichment, tech stack, hiring signals, ads intelligence |
| **Ecommerce** | StoreLeads | Platform, plan, revenue estimates, installed apps, product count |
| **Trucking** | FMCSA QCMobile API + daily census feeds | Carrier profiles, safety scores, authority status, daily change triggers |
| **Construction** | Shovels | Permits, contractors, employees, residents, geographic market metrics |
| **Legal / Risk** | CourtListener | Bankruptcy signals, court filing checks, docket detail |
| **Revenue Intelligence** | Enigma | Card transaction revenue, growth trends, market rank (consumer-facing businesses) |
| **Public Companies** | RevenueInfra + SEC EDGAR | SEC filing analysis (10-K, 10-Q, 8-K), financial metrics, strategic priorities |

---

## How Workflows Chain Together

These aren't isolated lookups. They chain into multi-step workflows:

**Example 1: Full Company Intelligence + Outbound**
```
Input: stripe.com
→ Enrich company profile (industry, employees, LinkedIn)
→ Find G2 page, pricing page
→ Analyze pricing (model, tiers, free trial)
→ Check VC funding
→ Search LinkedIn ads
→ Find VP-level decision-makers (fan-out per person)
  → Get verified email for each
```

**Example 2: Customer Intelligence → Outbound to Their Network**
```
Input: hubspot.com
→ Look up their customers (263 found)
→ Fan-out: enrich each customer company
→ Fan-out: find people at each customer
  → Get emails for each person
```

**Example 3: Trucking Trigger → Outbound**
```
Daily: Pull FMCSA new authority grants
→ Fan-out: enrich each new carrier (fleet size, safety, phone)
→ Find owner/decision-maker
→ Get email
→ Ready for outbound: "Congratulations on your new operating authority..."
```

**Example 4: Construction Lead Gen**
```
Input: Search permits in Austin, TX for solar installations, last 30 days
→ Fan-out per permit: enrich the contractor
→ Get contractor employees
→ Ready for outbound to solar contractors with recent permit activity
```

**Example 5: Competitive Intelligence Package**
```
Input: competitor.com
→ Enrich profile
→ Find their customers
→ Find similar companies
→ Find alumni (former employees)
→ Get champion testimonials from case studies
→ Check SEC filings + analyze 10-K
→ Package: "Here's everything about your competitor's market"
```

---

## What Makes This Different

1. **Intelligence, not just data.** We don't just find an email. We find the email of a VP who used to work at your prospect's customer, and we know what that customer said about the product in a case study.

2. **Multi-hop workflows.** Start with one domain → get their customers → find people at those customers → get emails. All automatic, all in one submission.

3. **Buying triggers from public data.** Government filings (FMCSA, building permits, bankruptcy) are signals nobody else monitors at scale. A new carrier registration = 13 different vendors need to reach out.

4. **Coverage across verticals.** B2B SaaS, ecommerce, trucking, construction, legal. Same engine, different data sources.

5. **AI-assembled workflows.** Describe what you want in natural language → system builds the workflow → submit domains → get results.

---

## What We Deliver To Clients

For each target entity, the system produces:
- **Enriched company record** with 50+ canonical fields
- **Decision-maker contacts** with verified emails and phone numbers
- **Relationship context** (customers, competitors, alumni, champions)
- **Intelligence signals** (hiring trends, revenue growth, technology changes, permit activity, court filings)
- **Personalization data** (testimonials, case study URLs, work history for "warm" references)

All queryable via API, filterable by title/seniority/department/industry, and ready for campaign enrollment (email + direct mail).
