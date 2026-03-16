# BlitzAPI Response Payloads

Response schemas for each BlitzAPI endpoint we call. Base URL: `https://api.blitz-api.ai`. Auth: `x-api-key` header.

Any property can be `null` when unavailable. Nested objects (e.g. `location`, `hq`) can also be `null`.

---

## 1. Domain to LinkedIn URL

**Endpoint:** `POST /v2/enrichment/domain-to-linkedin`

### Success Response (200)

```json
{
  "found": true,
  "company_linkedin_url": "https://www.linkedin.com/company/blitz-api"
}
```

| Property | Type | Description |
|----------|------|-------------|
| `found` | boolean | `true` if a LinkedIn company page was found. |
| `company_linkedin_url` | string | LinkedIn company page URL. |

### Not Found (200)

When no match: `found` is `false` or absent; `company_linkedin_url` may be absent or `null`.

### Error Responses

| Status | Body |
|--------|------|
| 401 | `{"message": "Missing API key, please provide a valid API key in the 'x-api-key' header"}` |
| 402 | `{"message": "Insufficient credits balance"}` |
| 422 | `{"success": false, "error": {"code": "INVALID_INPUT", "message": "Missing required fields"}}` |
| 500 | `{"success": false, "message": "..."}` |

---

## 2. Company Enrichment

**Endpoint:** `POST /v2/enrichment/company`

### Success Response (200)

```json
{
  "found": true,
  "company": {
    "linkedin_url": "https://www.linkedin.com/company/blitz-api",
    "linkedin_id": 108037802,
    "name": "Blitzapi",
    "about": "BlitzAPI provides enriched B2B data access...",
    "specialties": null,
    "industry": "Technology; Information and Internet",
    "type": "Privately Held",
    "size": "1-10",
    "employees_on_linkedin": 3,
    "followers": 6,
    "founded_year": null,
    "hq": { ... },
    "domain": "blitz-api.ai",
    "website": "https://blitz-api.ai"
  }
}
```

| Top-level | Type | Description |
|-----------|------|-------------|
| `found` | boolean | `true` if company was matched. |
| `company` | object | Enriched company. See Company Object below. |

### Company Object (enrichment/company)

| Property | Type | Description |
|----------|------|-------------|
| `linkedin_url` | string | LinkedIn company page URL. |
| `linkedin_id` | number | LinkedIn numeric org ID. |
| `name` | string | Company name. |
| `about` | string \| null | Company description. |
| `specialties` | string \| null | Specialties. |
| `industry` | string \| null | Industry. |
| `type` | string \| null | Company type (e.g. `Privately Held`). |
| `size` | string \| null | Employee range (e.g. `1-10`). |
| `employees_on_linkedin` | number \| null | LinkedIn employee count. |
| `followers` | number \| null | LinkedIn follower count. |
| `founded_year` | number \| null | Founding year. |
| `hq` | object \| null | HQ location. See HQ Object. |
| `domain` | string \| null | Root domain. |
| `website` | string \| null | Website URL. |

#### HQ Object

| Property | Type | Description |
|----------|------|-------------|
| `city` | string \| null | City. |
| `state` | string \| null | State/region. |
| `postcode` | string \| null | Postal code. |
| `country_code` | string \| null | Alpha-2 country code. |
| `country_name` | string \| null | Country name. |
| `region` | string \| null | Region. |
| `continent` | string \| null | Continent. |
| `street` | string \| null | Street address. |

### Error Responses

| Status | Meaning |
|--------|---------|
| 401 | Invalid API key. |
| 404 | Company not found. |
| 429 | Rate limit exceeded. |
| 500 | Internal server error. |

---

## 3. Find Companies (Search Companies)

**Endpoint:** `POST /v2/search/companies`

### Success Response (200)

```json
{
  "results_count": 2,
  "total_results": 148,
  "cursor": "eyJwYWdlIjoyLCJzZWFyY2hfaWQiOiJhYmMxMjMifQ==",
  "results": [
    {
      "linkedin_url": "https://www.linkedin.com/company/blitz-api",
      "linkedin_id": 108037802,
      "name": "Blitzapi",
      "about": "BlitzAPI provides enriched B2B data access...",
      "industry": "Technology; Information and Internet",
      "type": "Privately Held",
      "size": "1-10",
      "employees_on_linkedin": 3,
      "followers": 6,
      "founded_year": null,
      "specialties": null,
      "hq": { ... },
      "domain": "blitz-api.ai",
      "website": "https://blitz-api.ai"
    }
  ]
}
```

| Top-level | Type | Description |
|-----------|------|-------------|
| `results_count` | number | Number of companies in this page. |
| `total_results` | number | Total matching companies. |
| `cursor` | string \| null | Pagination cursor for next page. `null` when no more pages. |
| `results` | array | Company objects. Same schema as Company Object above. |

### Result Item (Company)

Same schema as Company Enrichment: `linkedin_url`, `linkedin_id`, `name`, `about`, `industry`, `type`, `size`, `employees_on_linkedin`, `followers`, `founded_year`, `specialties`, `hq`, `domain`, `website`.

### Error Responses

| Status | Meaning |
|--------|---------|
| 401 | Invalid API key. |
| 402 | Insufficient credits. |
| 422 | Invalid input. |
| 429 | Rate limit exceeded. |
| 500 | Internal server error. |

---

## 4. Waterfall ICP Search

**Endpoint:** `POST /v2/search/waterfall-icp-keyword`

### Success Response (200)

```json
{
  "company_linkedin_url": "https://www.linkedin.com/company/wttj-fr",
  "max_results": 6,
  "results_length": 6,
  "results": [
    {
      "person": { ... },
      "icp": 2,
      "ranking": 1,
      "what_matched": [
        {
          "value": "Growth Marketing Manager Welcome to the Jungle (France)",
          "key": "job_title"
        }
      ]
    }
  ]
}
```

| Top-level | Type | Description |
|-----------|------|-------------|
| `company_linkedin_url` | string | Input company URL. |
| `max_results` | number | Requested max results. |
| `results_length` | number | Number of results returned. |
| `results` | array | Result items. See Result Item below. |

### Result Item

| Property | Type | Description |
|----------|------|-------------|
| `person` | object | Person profile. See Person Object below. |
| `icp` | number | Cascade tier that matched (1-indexed). |
| `ranking` | number | Result rank. |
| `what_matched` | array | Matched fields: `{key, value}` objects. |

### Person Object (Waterfall ICP)

| Property | Type | Description |
|----------|------|-------------|
| `first_name` | string | First name. |
| `last_name` | string | Last name. |
| `full_name` | string | Full name. |
| `nickname` | string \| null | Nickname. |
| `civility_title` | string \| null | Title (e.g. Mr, Dr). |
| `headline` | string \| null | LinkedIn headline. |
| `about_me` | string \| null | About section. |
| `location` | object \| null | Location. See Person Location. |
| `linkedin_url` | string | LinkedIn profile URL. |
| `connections_count` | number | Connection count. |
| `profile_picture_url` | string \| null | Profile picture URL. |
| `experiences` | array | Work history. See Experience Entry. |
| `education` | array | Education entries. |
| `skills` | array | Skills. |
| `certifications` | array | Certifications. |

#### Person Location

| Property | Type | Description |
|----------|------|-------------|
| `city` | string \| null | City. |
| `state_code` | string \| null | State code. |
| `country_code` | string \| null | Alpha-2 country code. |
| `continent` | string \| null | Continent. |

#### Experience Entry

| Property | Type | Description |
|----------|------|-------------|
| `job_title` | string | Job title. |
| `company_linkedin_url` | string | Company LinkedIn URL. |
| `company_linkedin_id` | string | Company LinkedIn ID. |
| `job_description` | string \| null | Job description. |
| `job_start_date` | string | Start date (YYYY-MM-DD). |
| `job_end_date` | string \| null | End date. |
| `job_is_current` | boolean | Whether role is current. |
| `job_location` | object \| null | Job location. |

#### Education Entry

| Property | Type | Description |
|----------|------|-------------|
| `degree` | string | Degree. |
| `start_date` | string | Start date. |
| `end_date` | string | End date. |
| `linkedin_url` | string | School LinkedIn URL. |
| `organization` | string | School name. |

### Error Responses

| Status | Body |
|--------|------|
| 402 | `{"message": "Insufficient credits balance"}` |
| 422 | `{"success": false, "error": {"code": "INVALID_INPUT", "message": "Missing required fields"}}` |
| 500 | `{"success": false, "message": "..."}` |

---

## 5. Employee Finder

**Endpoint:** `POST /v2/search/employee-finder`

### Success Response (200)

```json
{
  "company_linkedin_url": "https://www.linkedin.com/company/wttj-fr",
  "max_results": 3,
  "results_length": 3,
  "page": 1,
  "total_pages": 82,
  "results": [
    {
      "first_name": "Hélène",
      "last_name": "Pillon",
      "full_name": "Hélène Pillon",
      "nickname": null,
      "civility_title": null,
      "headline": "Journaliste freelance",
      "about_me": "Depuis Marseille...",
      "location": { ... },
      "linkedin_url": "https://www.linkedin.com/in/...",
      "connections_count": 361,
      "profile_picture_url": "https://media.licdn.com/dms/image/...",
      "experiences": [ ... ],
      "education": [],
      "skills": [],
      "certifications": []
    }
  ]
}
```

| Top-level | Type | Description |
|-----------|------|-------------|
| `company_linkedin_url` | string | Input company URL. |
| `max_results` | number | Requested max results. |
| `results_length` | number | Number of results in this page. |
| `page` | number | Current page. |
| `total_pages` | number | Total pages. |
| `results` | array | Person objects. Same schema as Person Object above. |

### Result Item (Person)

Same schema as Waterfall ICP Person Object: `first_name`, `last_name`, `full_name`, `nickname`, `civility_title`, `headline`, `about_me`, `location`, `linkedin_url`, `connections_count`, `profile_picture_url`, `experiences`, `education`, `skills`, `certifications`.

**Note:** Employee Finder returns person objects directly (no `person` wrapper). Waterfall ICP wraps each in `person` and adds `icp`, `ranking`, `what_matched`.

### Error Responses

Same as Waterfall ICP: 402, 422, 500.

---

## 6. Find Mobile & Direct Phone

**Endpoint:** `POST /v2/enrichment/phone`

### Success Response (200)

```json
{
  "found": true,
  "phone": "+1234567890"
}
```

| Property | Type | Description |
|----------|------|-------------|
| `found` | boolean | `true` if phone was found. |
| `phone` | string | E.164 formatted phone number. |

### Not Found (200)

When no phone: `found` is `false` or absent; `phone` may be absent or `null`.

### Error Responses

| Status | Body |
|--------|------|
| 401 | `{"message": "Missing API key, please provide a valid API key in the 'x-api-key' header"}` |
| 402 | `{"message": "Insufficient credits balance"}` |
| 500 | `{"success": false, "message": "..."}` |

---

## 7. Find Work Email

**Endpoint:** `POST /v2/enrichment/email`

### Success Response (200)

```json
{
  "found": true,
  "email": "antoine@blitz-agency.com",
  "all_emails": [
    {
      "email": "antoine@blitz-agency.com",
      "job_order_in_profile": 1,
      "company_linkedin_url": "https://www.linkedin.com/company/blitz-api",
      "email_domain": "blitz-agency.com"
    }
  ]
}
```

| Property | Type | Description |
|----------|------|-------------|
| `found` | boolean | `true` if email was found. |
| `email` | string | Primary work email. |
| `all_emails` | array | All emails with context. See Email Entry. |

### Email Entry (in `all_emails`)

| Property | Type | Description |
|----------|------|-------------|
| `email` | string | Email address. |
| `job_order_in_profile` | number | Order in profile. |
| `company_linkedin_url` | string | Associated company. |
| `email_domain` | string | Email domain. |

### Not Found (200)

When no email: `found` is `false` or absent; `email` and `all_emails` may be absent.

### Error Responses

Same as Find Mobile: 401, 402, 500.

---

## Object Reference Summary

| Object | Used In |
|--------|---------|
| **Company** | Company Enrichment, Find Companies |
| **Person** | Waterfall ICP Search (wrapped in `person`), Employee Finder (direct) |
| **HQ** | Company object |
| **Person Location** | Person object |
| **Experience** | Person `experiences` array |
| **Education** | Person `education` array |
| **Email Entry** | Find Work Email `all_emails` |

---

## Common Error Codes

| HTTP | Meaning |
|------|---------|
| 401 | Invalid or missing API key. |
| 402 | Insufficient credits. |
| 404 | Resource not found (company enrichment). |
| 422 | Invalid input; see `error.code` and `error.message`. |
| 429 | Rate limit exceeded. |
| 500 | Internal server error. |
