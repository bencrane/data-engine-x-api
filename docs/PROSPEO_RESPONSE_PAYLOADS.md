# Prospeo API Response Payloads

Response schemas for each Prospeo endpoint we call. Any property can be `null` when unavailable. Nested objects (e.g. `location`, `company`) can also be `null`.

---

## 1. Enrich Person API

**Endpoint:** `POST https://api.prospeo.io/enrich-person`

### Success Response (200)

```json
{
  "error": false,
  "free_enrichment": false,
  "person": { ... },
  "company": { ... }
}
```

| Top-level | Type | Description |
|-----------|------|-------------|
| `error` | boolean | `false` on success; `true` when an error occurred (see `error_code`). |
| `free_enrichment` | boolean | `true` if no charge (previously enriched); `false` if charged. |
| `person` | object | Matched person. See Person Object below. |
| `company` | object \| null | Current company of the person. See Company Object. `null` if no current job. |

### Person Object (enrich-person)

| Property | Type | Description |
|----------|------|-------------|
| `person_id` | string | Prospeo person ID. |
| `first_name` | string | Given name. |
| `last_name` | string | Family name. |
| `full_name` | string | Full name. |
| `linkedin_url` | string | Public LinkedIn profile URL. |
| `current_job_title` | string | Current job title. |
| `current_job_key` | string \| null | Internal key for main current job. |
| `headline` | string | LinkedIn headline. |
| `linkedin_member_id` | string \| null | LinkedIn member ID. |
| `last_job_change_detected_at` | datetime \| null | Last detected job change. |
| `job_history` | array | Past and current roles. See Job History Entry. |
| `mobile` | object \| null | Mobile phone data. See Mobile Object. |
| `email` | object \| null | Email data. See Email Object. |
| `location` | object \| null | Location. See Location Object. |
| `skills` | array of strings | Self-reported skills. |

#### Job History Entry

| Property | Type | Description |
|----------|------|-------------|
| `title` | string | Job title. |
| `company_name` | string | Company name. |
| `logo_url` | string | Logo filename. |
| `current` | boolean | `true` if current role. |
| `start_year` | integer | Start year. |
| `start_month` | integer \| null | Start month (1–12). |
| `end_year` | integer \| null | End year. |
| `end_month` | integer \| null | End month. |
| `duration_in_months` | integer | Duration in months. |
| `departments` | array of strings | Departments. |
| `seniority` | string | Seniority. |
| `company_id` | string \| null | Prospeo company ID. |
| `job_key` | string | Internal job key. |

#### Mobile Object

| Property | Type | Description |
|----------|------|-------------|
| `status` | string | `VERIFIED` or `UNAVAILABLE`. |
| `revealed` | boolean | `true` if paid and revealed. |
| `mobile` | string | E.164 number (when revealed). |
| `mobile_national` | string | National format (when revealed). |
| `mobile_international` | string | International format (when revealed). |
| `mobile_country` | string | Country name (when revealed). |
| `mobile_country_code` | string | Alpha-2 code (when revealed). |

#### Email Object

| Property | Type | Description |
|----------|------|-------------|
| `status` | string | `VERIFIED` or `UNAVAILABLE`. |
| `revealed` | boolean | `true` if revealed. |
| `email` | string | Email address (when revealed). |
| `verification_method` | string | `SMTP` or `BOUNCEBAN`. |
| `email_mx_provider` | string | MX provider (e.g. `Google`). |

#### Location Object

| Property | Type | Description |
|----------|------|-------------|
| `country` | string | Country name. |
| `country_code` | string | Alpha-2 code. |
| `state` | string | State/region. |
| `city` | string | City. |
| `time_zone` | string | IANA timezone. |
| `time_zone_offset` | number | UTC offset in hours. |

### Error Response (400+)

```json
{
  "error": true,
  "error_code": "NO_MATCH"
}
```

| `error_code` | Meaning |
|--------------|---------|
| `NO_MATCH` | No matching person. |
| `INVALID_DATAPOINTS` | Input does not meet minimum requirements. |
| `INSUFFICIENT_CREDITS` | Not enough credits. |
| `INVALID_API_KEY` | Invalid API key (401). |
| `RATE_LIMITED` | Rate limit (429). |
| `INVALID_REQUEST` | Invalid request. |
| `INTERNAL_ERROR` | Server error. |

---

## 2. Enrich Company API

**Endpoint:** `POST https://api.prospeo.io/enrich-company`

### Success Response (200)

```json
{
  "error": false,
  "free_enrichment": false,
  "company": { ... }
}
```

| Top-level | Type | Description |
|-----------|------|-------------|
| `error` | boolean | `false` on success. |
| `free_enrichment` | boolean | `true` if no charge (previously enriched). |
| `company` | object | Matched company. See Company Object below. |

### Company Object (enrich-company)

| Property | Type | Description |
|----------|------|-------------|
| `company_id` | string | Prospeo company ID. |
| `name` | string | Company name. |
| `website` | string | Main website URL. |
| `domain` | string | Root domain. |
| `other_websites` | array of strings | Additional websites. |
| `description` | string | Company description. |
| `description_seo` | string | SEO description. |
| `description_ai` | string | AI-generated summary. |
| `type` | string | Legal type (e.g. `Private`, `Public`). |
| `industry` | string | Main industry. |
| `employee_count` | integer | Estimated headcount. |
| `employee_count_on_prospeo` | integer | Employees in Prospeo DB. |
| `employee_range` | string | Bucketed range (e.g. `1001-2000`). |
| `location` | object \| null | HQ location. See Location Object. |
| `sic_codes` | array of strings | SIC codes. |
| `naics_codes` | array | NAICS codes. |
| `email_tech` | object \| null | Email infrastructure. |
| `linkedin_url` | string | LinkedIn company page. |
| `twitter_url` | string \| null | Twitter. |
| `facebook_url` | string \| null | Facebook. |
| `crunchbase_url` | string \| null | Crunchbase. |
| `instagram_url` | string \| null | Instagram. |
| `youtube_url` | string \| null | YouTube. |
| `phone_hq` | object \| null | HQ phone. |
| `linkedin_id` | string \| null | LinkedIn org ID. |
| `founded` | integer \| null | Founding year. |
| `revenue_range` | object \| null | `{min, max}` in USD. |
| `revenue_range_printed` | string \| null | Human-readable revenue. |
| `keywords` | array of strings | Company keywords. |
| `logo_url` | string | Logo URL. |
| `attributes` | object \| null | Flags (e.g. `is_b2b`, `has_pricing`). |
| `funding` | object \| null | Funding info. |
| `technology` | object \| null | Tech stack. |
| `job_postings` | object \| null | Active job postings. |

#### Company `location`

| Key | Type | Description |
|-----|------|-------------|
| `country` | string | Country name. |
| `country_code` | string | Alpha-2 code. |
| `state` | string | State/region. |
| `city` | string | City. |
| `raw_address` | string | Unstructured address. |

#### Company `email_tech`

| Key | Type | Description |
|-----|------|-------------|
| `domain` | string | Email domain. |
| `mx_provider` | string | MX provider. |
| `catch_all_domain` | boolean | Catch-all domain. |

#### Company `phone_hq`

| Key | Type | Description |
|-----|------|-------------|
| `phone_hq` | string | E.164 number. |
| `phone_hq_national` | string | National format. |
| `phone_hq_international` | string | International format. |
| `phone_hq_country` | string | Country name. |
| `phone_hq_country_code` | string | Alpha-2 code. |

#### Company `attributes`

| Key | Type | Description |
|-----|------|-------------|
| `is_b2b` | boolean | B2B company. |
| `has_demo` | boolean \| null | Offers demo. |
| `has_free_trial` | boolean \| null | Offers free trial. |
| `has_downloadable` | boolean \| null | Downloadable product. |
| `has_mobile_apps` | boolean \| null | Has mobile apps. |
| `has_online_reviews` | boolean \| null | Has online reviews. |
| `has_pricing` | boolean \| null | Public pricing page. |

#### Company `funding`

| Key | Type | Description |
|-----|------|-------------|
| `count` | integer | Number of rounds. |
| `total_funding` | integer | Total raised (USD). |
| `total_funding_printed` | string | Human-readable total. |
| `latest_funding_date` | datetime | Latest round date. |
| `latest_funding_stage` | string | Latest stage. |
| `funding_events` | array | Rounds: `{amount, amount_printed, raised_at, stage, link}`. |

#### Company `technology`

| Key | Type | Description |
|-----|------|-------------|
| `count` | integer | Tech count. |
| `technology_names` | array of strings | Tech names. |
| `technology_list` | array | `{name, category}` objects. |

#### Company `job_postings`

| Key | Type | Description |
|-----|------|-------------|
| `active_count` | integer | Open roles. |
| `active_titles` | array of strings | Job titles. |

### Error Response (400+)

| `error_code` | Meaning |
|--------------|---------|
| `NO_MATCH` | No matching company. |
| `INSUFFICIENT_CREDITS` | Not enough credits. |
| `INVALID_API_KEY` | Invalid API key (401). |
| `RATE_LIMITED` | Rate limit (429). |
| `INVALID_REQUEST` | Invalid request. |
| `INTERNAL_ERROR` | Server error. |

---

## 3. Search Person API

**Endpoint:** `POST https://api.prospeo.io/search-person`

### Success Response (200)

```json
{
  "error": false,
  "results": [
    {
      "person": { ... },
      "company": { ... }
    }
  ],
  "pagination": {
    "current_page": 1,
    "per_page": 25,
    "total_page": 11,
    "total_count": 271
  }
}
```

| Top-level | Type | Description |
|-----------|------|-------------|
| `error` | boolean | `false` on success. |
| `results` | array | Up to 25 results per page. |
| `pagination` | object | Pagination metadata. |

### Result Item

| Property | Type | Description |
|----------|------|-------------|
| `person` | object | Person. Same schema as Person Object, but **without** `mobile` and `email`. |
| `company` | object \| null | Current company if person has a current job. Same schema as Company Object. |

### Pagination Object

| Property | Type | Description |
|----------|------|-------------|
| `current_page` | integer | Current page. |
| `per_page` | integer | Results per page (25). |
| `total_page` | integer | Total pages. |
| `total_count` | integer | Total matching records. |

**Note:** Search Person does not return `mobile` or `email`. Use Enrich Person (or Bulk Enrich Person) with `person_id` to get them.

### Error Response (400+)

```json
{
  "error": true,
  "error_code": "INVALID_FILTERS",
  "filter_error": "The value `Accountingg` is not supported for the filter `company_industry`."
}
```

| `error_code` | Meaning |
|--------------|---------|
| `INVALID_FILTERS` | Invalid filters; see `filter_error`. |
| `NO_RESULTS` | No matches. |
| `INSUFFICIENT_CREDITS` | Not enough credits. |
| `INVALID_API_KEY` | Invalid API key (401). |
| `RATE_LIMITED` | Rate limit (429). |
| `INVALID_REQUEST` | Invalid request. |
| `INTERNAL_ERROR` | Server error. |

---

## 4. Search Company API

**Endpoint:** `POST https://api.prospeo.io/search-company`

### Success Response (200)

```json
{
  "error": false,
  "results": [
    {
      "company": { ... }
    }
  ],
  "pagination": {
    "current_page": 1,
    "per_page": 25,
    "total_page": 11,
    "total_count": 271
  }
}
```

| Top-level | Type | Description |
|-----------|------|-------------|
| `error` | boolean | `false` on success. |
| `results` | array | Up to 25 results per page. |
| `pagination` | object | Pagination metadata. |

### Result Item

| Property | Type | Description |
|----------|------|-------------|
| `company` | object | Company. Same schema as Company Object. |

### Pagination Object

Same as Search Person: `current_page`, `per_page`, `total_page`, `total_count`.

### Error Response (400+)

Same error codes as Search Person.

---

## Object Reference Summary

| Object | Used In |
|--------|---------|
| **Person** | Enrich Person (full), Search Person (no `mobile`/`email`) |
| **Company** | Enrich Person (`company`), Enrich Company, Search Person (per result), Search Company (per result) |

Full schemas for Person and Company are in `docs/api-reference-docs/prospeo/04-object-schemas/`.
