# Directive: Adyntel Ads Persistence Layer

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We have 3 Adyntel ad search operations live (`company.ads.search.linkedin`, `company.ads.search.meta`, `company.ads.search.google`). Their output currently only persists to `step_results`. We need a dedicated `company_ads` table so ad data is directly queryable by company, platform, and recency. This follows the same pattern we used for `company_customers` and `gemini_icp_job_titles` — migration, upsert service, internal endpoint, auto-persist in run-pipeline.ts, and a tenant query endpoint.

---

## Existing code to read before starting

- `supabase/migrations/018_alumnigtm_persistence.sql` — pattern reference for dedicated tables (company_customers, gemini_icp_job_titles)
- `app/services/company_customers.py` — pattern reference for upsert + query service
- `app/routers/internal.py` — pattern for internal upsert endpoints (request model + endpoint)
- `app/routers/entities_v1.py` — pattern for tenant query endpoints
- `app/contracts/company_ads.py` — existing output contracts (LinkedInAdsOutput, MetaAdsOutput, GoogleAdsOutput). Read to understand the output shapes.
- `app/services/adyntel_operations.py` — existing service functions. Read to understand what `output` looks like for each operation.
- `trigger/src/tasks/run-pipeline.ts` — read existing auto-persist blocks (~line 1767-1853) for the pattern.

---

## Deliverable 1: Migration

**File:** `supabase/migrations/019_company_ads.sql` (new file)

```sql
-- 019_company_ads.sql
-- Persisted ad intelligence from Adyntel (LinkedIn, Meta, Google).

CREATE TABLE IF NOT EXISTS company_ads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_domain TEXT NOT NULL,
    company_entity_id UUID,
    platform TEXT NOT NULL,
    ad_id TEXT,
    ad_type TEXT,
    ad_format TEXT,
    headline TEXT,
    body_text TEXT,
    cta_text TEXT,
    landing_page_url TEXT,
    media_url TEXT,
    media_type TEXT,
    advertiser_name TEXT,
    advertiser_url TEXT,
    start_date TEXT,
    end_date TEXT,
    is_active BOOLEAN,
    impressions_range TEXT,
    spend_range TEXT,
    country_code TEXT,
    raw_ad JSONB NOT NULL,
    discovered_by_operation_id TEXT NOT NULL,
    source_submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    source_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Dedup: one ad per platform per domain per org. ad_id is the platform-specific unique identifier.
-- If ad_id is null (some platforms don't provide one), allow duplicates — raw_ad JSONB is the archive.
CREATE UNIQUE INDEX IF NOT EXISTS idx_company_ads_dedup
    ON company_ads(org_id, company_domain, platform, ad_id)
    WHERE ad_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_company_ads_org
    ON company_ads(org_id);
CREATE INDEX IF NOT EXISTS idx_company_ads_company
    ON company_ads(org_id, company_domain);
CREATE INDEX IF NOT EXISTS idx_company_ads_platform
    ON company_ads(org_id, company_domain, platform);
CREATE INDEX IF NOT EXISTS idx_company_ads_entity
    ON company_ads(org_id, company_entity_id);

DROP TRIGGER IF EXISTS update_company_ads_updated_at ON company_ads;
CREATE TRIGGER update_company_ads_updated_at
    BEFORE UPDATE ON company_ads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE company_ads ENABLE ROW LEVEL SECURITY;
```

**Column rationale:**
- `platform`: `"linkedin"`, `"meta"`, or `"google"` — all 3 platforms in one table rather than 3 tables. Simpler querying, single index.
- `ad_id`: Platform-specific identifier. LinkedIn ads have a page_id-based key, Meta/Google may have unique identifiers in the raw payload. Extract the best available unique ID from each platform's raw ad object.
- Structured fields (`headline`, `body_text`, `cta_text`, `landing_page_url`, etc.) are nullable — extract what's available from each platform. Not all platforms return all fields.
- `raw_ad`: The full raw ad object as JSONB. Always stored regardless of extraction success.
- `is_active`, `impressions_range`, `spend_range`: Platform-specific metrics, nullable.

Commit standalone with message: `migration 019: add company_ads table for Adyntel ad persistence`

---

## Deliverable 2: Upsert + Query Service

**File:** `app/services/company_ads.py` (new file)

### Ad field extraction

Create a helper that extracts structured fields from a raw ad dict, adapting per platform:

```python
def _extract_ad_fields(raw_ad: dict[str, Any], platform: str) -> dict[str, Any]:
```

**LinkedIn ads** — the raw ad is typically shaped like:
```python
{
    "ad_id": "...",
    "headline": "...",
    "body": "...",
    "cta": "...",
    "landing_page": "...",
    "image_url": "...",
    "media_type": "...",
    ...
}
```
Extract: `ad_id`, `headline` (from `headline`), `body_text` (from `body` or `description`), `cta_text` (from `cta` or `call_to_action`), `landing_page_url` (from `landing_page` or `destination_url`), `media_url` (from `image_url` or `video_url`), `media_type`.

**Meta ads** — similar shape but different field names. Extract what's available.

**Google ads** — similar. Extract what's available.

The extraction should be best-effort: try multiple field name candidates, return None for anything not found. The `raw_ad` JSONB is the authoritative store.

### `upsert_company_ads`

```python
def upsert_company_ads(
    *,
    org_id: str,
    company_domain: str,
    company_entity_id: str | None = None,
    platform: str,
    ads: list[dict[str, Any]],
    discovered_by_operation_id: str,
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
```

Logic:
1. Normalize `company_domain`.
2. For each ad in `ads`, build a row:
   - Extract structured fields via `_extract_ad_fields(ad, platform)`
   - Set `raw_ad = ad` (full raw dict)
   - Set `platform`, `org_id`, `company_domain`, `company_entity_id`, `discovered_by_operation_id`, source fields, `updated_at`
3. Upsert to `company_ads` with `on_conflict="org_id,company_domain,platform,ad_id"`.
4. For ads without an `ad_id` (where the partial unique index doesn't apply), just insert — they'll accumulate.
5. Return upserted rows.

### `query_company_ads`

```python
def query_company_ads(
    *,
    org_id: str,
    company_domain: str | None = None,
    company_entity_id: str | None = None,
    platform: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
```

Standard query with optional filters. Ordered by `created_at` desc.

Commit standalone with message: `add company_ads upsert and query service`

---

## Deliverable 3: Internal Endpoint

**File:** `app/routers/internal.py`

### Request model

```python
class InternalUpsertCompanyAdsRequest(BaseModel):
    company_domain: str
    company_entity_id: str | None = None
    platform: str
    ads: list[dict[str, Any]]
    discovered_by_operation_id: str
    source_submission_id: str | None = None
    source_pipeline_run_id: str | None = None
```

### Endpoint

**`POST /company-ads/upsert`**
- Requires internal key auth
- Extracts `org_id` from `x-internal-org-id` header
- Calls `upsert_company_ads` from `app.services.company_ads`
- Returns `DataEnvelope(data=result)`

Import the service function at the top of the file.

Commit standalone with message: `add internal upsert endpoint for company_ads`

---

## Deliverable 4: Auto-Persist Wiring in Pipeline Runner

**File:** `trigger/src/tasks/run-pipeline.ts`

Add 3 auto-persist blocks after the existing Gemini ICP job titles block (or after the last existing auto-persist block), before the `cumulativeContext = mergeContext(...)` line.

All 3 follow the same pattern — only the operation_id, platform name, and ads field name differ:

### LinkedIn Ads

```typescript
if (operationId === "company.ads.search.linkedin" && result.status === "found" && result.output) {
  try {
    const output = result.output as Record<string, unknown>;
    const ads = output.ads;
    if (Array.isArray(ads) && ads.length > 0) {
      const companyDomain = String(
        cumulativeContext.company_domain || cumulativeContext.domain || cumulativeContext.canonical_domain || ""
      );
      if (companyDomain) {
        await internalPost(internalConfig, "/api/internal/company-ads/upsert", {
          company_domain: companyDomain,
          company_entity_id: cumulativeContext.entity_id || null,
          platform: "linkedin",
          ads,
          discovered_by_operation_id: operationId,
          source_submission_id: run.submission_id,
          source_pipeline_run_id: pipeline_run_id,
        });
        logger.info("LinkedIn ads persisted to dedicated table", {
          domain: companyDomain,
          ads_count: ads.length,
          pipeline_run_id,
        });
      }
    }
  } catch (error) {
    logger.warn("Failed to persist LinkedIn ads to dedicated table", {
      pipeline_run_id,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}
```

### Meta Ads

Same pattern but:
- `operationId === "company.ads.search.meta"`
- `const ads = output.results;` (Meta uses `results`, not `ads`)
- `platform: "meta"`
- Log message: `"Meta ads persisted..."`

### Google Ads

Same pattern but:
- `operationId === "company.ads.search.google"`
- `const ads = output.ads;`
- `platform: "google"`
- Log message: `"Google ads persisted..."`

All 3 wrapped in try/catch — failure logs a warning, never fails the pipeline step.

Commit standalone with message: `add auto-persist wiring for Adyntel ads in pipeline runner`

---

## Deliverable 5: Tenant Query Endpoint

**File:** `app/routers/entities_v1.py`

### `POST /api/v1/company-ads/query`

Request body: `company_domain` (optional), `company_entity_id` (optional), `platform` (optional — `"linkedin"`, `"meta"`, `"google"`), `limit` (default 100), `offset` (default 0).

Calls `query_company_ads` from `app.services.company_ads`. Uses tenant auth. Scoped by `org_id`.

Commit standalone with message: `add tenant query endpoint for company_ads`

---

## Deliverable 6: Update Documentation

### File: `CLAUDE.md`

Add to API Endpoints:
```
- `POST /api/v1/company-ads/query`
- `POST /api/internal/company-ads/upsert`
```

Add to Database / Migrations:
```
19. `019_company_ads.sql`
```

### File: `docs/SYSTEM_OVERVIEW.md`

Add `company_ads` table to Infrastructure Features. Update migration table.

Commit standalone with message: `update documentation for Adyntel ads persistence layer`

---

## What is NOT in scope

- No changes to existing Adyntel provider adapters or service functions
- No changes to existing output contracts
- No new operations — the 3 existing operations stay as-is
- No deploy commands
- Do NOT run the migration — the chief agent runs it after review

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Migration file name, table name, column list, dedup strategy
(b) Ad field extraction — what structured fields are extracted per platform, how ad_id is determined
(c) Upsert function signature and on_conflict key
(d) Query function signature and available filters
(e) Internal endpoint path and request model fields
(f) Auto-persist — which 3 operation_ids trigger it, which field holds the ads list per platform
(g) Tenant query endpoint path
(h) Anything to flag
