# Gemini Endpoints Documentation

This folder contains documentation for all Gemini-powered API endpoints.

**Base URL:** `https://bencrane--hq-master-data-ingest-{endpoint-name}.modal.run`

---

## Endpoint Categories

### Company Inference
| Endpoint | Description | Model |
|----------|-------------|-------|
| [industry-inference](./industry-inference.md) | Infer company industry | gemini-3-flash-preview |
| [country-inference](./country-inference.md) | Infer HQ location (city, state, country) | gemini-3-flash-preview |
| [employee-range-inference](./employee-range-inference.md) | Infer employee count range | gemini-3-flash-preview |
| [linkedin-url-inference](./linkedin-url-inference.md) | Infer company LinkedIn URL | gemini-3-flash-preview |

### Customer Domain Resolution
| Endpoint | Description | Model |
|----------|-------------|-------|
| [infer-customer-domain](./infer-customer-domain.md) | Find customer domain with context | gemini-2.0-flash |
| [resolve-orphan-customer-domain](./resolve-orphan-customer-domain.md) | Resolve domain for orphan customers | gemini-2.0-flash |
| [ingest-orphan-customer-domain](./ingest-orphan-customer-domain.md) | Store orphan domain resolution results | N/A (ingestion) |

### Pricing Page Analysis
| Endpoint | Description | Model |
|----------|-------------|-------|
| [free-trial](./free-trial.md) | Detect free trial availability | gemini-3-flash-preview |
| [sales-motion](./sales-motion.md) | Classify sales motion (self-serve/sales-led/hybrid) | gemini-3-flash-preview |
| [pricing-visibility](./pricing-visibility.md) | Classify pricing visibility (public/hidden/partial) | gemini-3-flash-preview |
| [pricing-model](./pricing-model.md) | Classify pricing model (seat-based/usage/flat/etc) | gemini-3-flash-preview |
| [billing-default](./billing-default.md) | Detect default billing period | gemini-3-flash-preview |
| [number-of-tiers](./number-of-tiers.md) | Count pricing tiers | gemini-3-flash-preview |
| [add-ons-offered](./add-ons-offered.md) | Detect add-ons availability | gemini-3-flash-preview |
| [enterprise-tier-exists](./enterprise-tier-exists.md) | Detect enterprise tier | gemini-3-flash-preview |
| [security-compliance-gating](./security-compliance-gating.md) | Detect security feature gating | gemini-3-flash-preview |
| [annual-commitment-required](./annual-commitment-required.md) | Detect annual commitment | gemini-3-flash-preview |
| [plan-naming-style](./plan-naming-style.md) | Classify plan naming convention | gemini-3-flash-preview |
| [custom-pricing-mentioned](./custom-pricing-mentioned.md) | Detect custom pricing mentions | gemini-3-flash-preview |
| [money-back-guarantee](./money-back-guarantee.md) | Detect refund policy | gemini-3-flash-preview |
| [minimum-seats](./minimum-seats.md) | Detect minimum seat requirements | gemini-3-flash-preview |

### Discovery
| Endpoint | Description | Model |
|----------|-------------|-------|
| [discover-pricing-page](./discover-pricing-page.md) | Find pricing page URL | gemini-2.0-flash |
| [discover-g2-page](./discover-g2-page.md) | Find G2.com page URL | gemini-2.0-flash |
| [discover-g2-page-search](./discover-g2-page-search.md) | Find G2 page with search | gemini-2.0-flash |
| [comparison-page-exists](./comparison-page-exists.md) | Extract competitor comparison pages | gemini-3-flash-preview |
| [webinars](./webinars.md) | Extract webinar listings | gemini-3-flash-preview |

### SEC Filing Analysis
| Endpoint | Description | Model |
|----------|-------------|-------|
| [sec-filing-10k](./sec-filing-10k.md) | Analyze 10-K annual reports | gemini-2.0-flash |
| [sec-filing-10q](./sec-filing-10q.md) | Analyze 10-Q quarterly reports | gemini-2.0-flash |
| [sec-filing-8k-executive](./sec-filing-8k-executive.md) | Analyze 8-K executive changes | gemini-2.0-flash |

---

## Common Patterns

### Pricing Page Endpoints
Most pricing page analysis endpoints share this pattern:
1. Accept `domain`, `company_name`, `pricing_page_url`
2. Fetch and parse the pricing page HTML
3. Send to Gemini for classification
4. Write to `raw.{feature}_payloads`, `extracted.company_{feature}`, and `core.company_{feature}`

### Cost Tracking
Most endpoints return:
- `input_tokens` - Gemini input token count
- `output_tokens` - Gemini output token count
- `cost_usd` - Estimated API cost

### Pricing (Gemini 2.0/3.0 Flash)
- Input: ~$0.10/1M tokens
- Output: ~$0.40/1M tokens
- Typical cost per call: $0.00001 - $0.0001

---

## Database Schema Pattern

Most endpoints write to three schemas:
1. **raw** - Store original request payload
2. **extracted** - Store parsed/classified result
3. **core** - Upsert final value (on conflict: domain)
