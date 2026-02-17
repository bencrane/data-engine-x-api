# Source-Agnostic Action Input Refactor

**Goal:** Decouple data source (Clay webhook, direct API, scheduled job, etc.) from action logic so the same function can process data from any source.

**Current State:** Functions are tightly coupled to Clay's payload structure and expect specific field names/shapes.

**Target State:** Functions accept a canonical input contract; a binding layer transforms source-specific payloads into this contract.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           SOURCE LAYER                                   │
├──────────────┬──────────────┬──────────────┬──────────────┬─────────────┤
│ Clay Webhook │ Direct API   │ Scheduled    │ Prior Step   │ DB Trigger  │
│              │ Call         │ Job          │ Output       │             │
└──────┬───────┴──────┬───────┴──────┬───────┴──────┬───────┴──────┬──────┘
       │              │              │              │              │
       ▼              ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         BINDING LAYER (NEW)                              │
│  - Source detection (Clay vs API vs DB)                                  │
│  - Field mapping (source.field → canonical.field)                        │
│  - Fallback resolution (try A, then B, then DB lookup)                   │
│  - Validation (required fields, types)                                   │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      CANONICAL INPUT CONTRACT                            │
│  Standard Pydantic models with clear required/optional fields            │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         ACTION LAYER                                     │
│  Pure business logic - no knowledge of data source                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Function Analysis & Refactor Plan

---

### 1. `ingest_clay_company_firmo` (Company Firmographics)

**File:** `modal-functions/src/ingest/company.py`

#### Current Required Inputs

| Field | Type | Required | Source |
|-------|------|----------|--------|
| `company_domain` | str | Yes | Submission (Clay webhook) |
| `workflow_slug` | str | Yes | Submission (hardcoded in Clay table) |
| `raw_payload` | dict | Yes | Submission (full Clay enrichment result) |

#### Current Source Dependencies

```python
# Expects Clay-specific structure
CompanyIngestRequest(
    company_domain: str,       # Clay: "Domain" column
    workflow_slug: str,        # Clay: hardcoded per table
    raw_payload: dict          # Clay: entire row as JSON
)
```

#### Canonical Input Contract

```python
class CompanyFirmographicsInput(BaseModel):
    """Source-agnostic company firmographics input."""

    # Required identifiers
    domain: str                           # Primary key

    # Optional identifiers (for matching)
    linkedin_url: Optional[str] = None
    company_name: Optional[str] = None

    # Firmographic data (all optional - fill what you have)
    employee_count: Optional[int] = None
    employee_range: Optional[str] = None
    industry: Optional[str] = None
    founded_year: Optional[int] = None
    headquarters_city: Optional[str] = None
    headquarters_state: Optional[str] = None
    headquarters_country: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None

    # Metadata
    source: str = "unknown"               # "clay", "apollo", "api", "db"
    source_payload: Optional[dict] = None # Original payload for audit
    workflow_slug: Optional[str] = None   # Optional workflow tracking
```

#### Binding Rules

| Source | Field Mapping | Fallback |
|--------|---------------|----------|
| Clay webhook | `raw_payload.Domain` → `domain` | None (required) |
| Clay webhook | `raw_payload.Company LinkedIn URL` → `linkedin_url` | None |
| Clay webhook | `raw_payload.Company Name` → `company_name` | None |
| Clay webhook | `raw_payload.Employees` → `employee_count` | Parse from `employee_range` |
| Direct API | Pass fields directly | None |
| DB trigger | Query `staging.companies` by id | None |
| Prior step | Use `output.domain` from previous step | None |

#### Code Changes

**New file: `modal-functions/src/bindings/company.py`**

```python
from typing import Union
from pydantic import BaseModel

class ClayCompanyPayload(BaseModel):
    """Clay-specific payload structure."""
    Domain: str
    company_linkedin_url: Optional[str] = Field(None, alias="Company LinkedIn URL")
    company_name: Optional[str] = Field(None, alias="Company Name")
    employees: Optional[Union[int, str]] = Field(None, alias="Employees")
    industry: Optional[str] = Field(None, alias="Industry")
    # ... other Clay fields

def bind_clay_to_canonical(clay_payload: dict) -> CompanyFirmographicsInput:
    """Transform Clay payload to canonical input."""
    parsed = ClayCompanyPayload(**clay_payload)

    # Parse employee count
    employee_count = None
    if parsed.employees:
        if isinstance(parsed.employees, int):
            employee_count = parsed.employees
        elif parsed.employees.isdigit():
            employee_count = int(parsed.employees)

    return CompanyFirmographicsInput(
        domain=parsed.Domain.lower().strip(),
        linkedin_url=normalize_linkedin_url(parsed.company_linkedin_url),
        company_name=parsed.company_name,
        employee_count=employee_count,
        industry=parsed.industry,
        source="clay",
        source_payload=clay_payload,
    )

def bind_db_to_canonical(db_row: dict) -> CompanyFirmographicsInput:
    """Transform DB row to canonical input."""
    return CompanyFirmographicsInput(
        domain=db_row["domain"],
        linkedin_url=db_row.get("linkedin_url"),
        company_name=db_row.get("name"),
        employee_count=db_row.get("employee_count"),
        source="db",
    )

def bind_api_to_canonical(api_payload: dict) -> CompanyFirmographicsInput:
    """Direct API payload (already canonical-ish)."""
    return CompanyFirmographicsInput(**api_payload, source="api")
```

**Refactored action: `modal-functions/src/actions/company_firmographics.py`**

```python
async def process_company_firmographics(
    input: CompanyFirmographicsInput,
    pool: asyncpg.Pool
) -> CompanyFirmographicsResult:
    """
    Pure action logic - no source knowledge.
    """
    # Store audit record
    raw_id = await store_raw_payload(
        pool,
        table="raw.company_firmographics",
        domain=input.domain,
        source=input.source,
        payload=input.source_payload or input.dict()
    )

    # Extract and store
    extracted_id = await upsert_extracted(
        pool,
        table="extracted.company_firmographics",
        domain=input.domain,
        employee_count=input.employee_count,
        industry=input.industry,
        # ...
    )

    # Update core
    await upsert_core_company(pool, input.domain, input.company_name, input.linkedin_url)

    return CompanyFirmographicsResult(
        success=True,
        raw_id=raw_id,
        extracted_id=extracted_id
    )
```

---

### 2. `ingest_clay_signal_job_change` (Job Change Signal)

**File:** `modal-functions/src/ingest/signal_job_change.py`

#### Current Required Inputs

| Field | Type | Required | Source |
|-------|------|----------|--------|
| `person_linkedin_url` | str | Yes | Submission (Clay) |
| `signal_slug` | str | Yes | Submission (default: "clay-job-change") |
| `confidence` | int | No | Submission |
| `previous_company_linkedin_url` | str | No | Submission |
| `new_company_linkedin_url` | str | No | Submission |
| `new_company_domain` | str | No | Submission |
| `new_company_name` | str | No | Submission |
| `start_date_at_new_job` | str | No | Submission |
| `lookback_threshold_days` | int | No | Submission |
| `job_change_event_raw_payload` | dict | No | Submission |
| `person_record_raw_payload` | dict | No | Submission |
| `clay_table_url` | str | No | Submission |

#### Current Source Dependencies

- **Expects flattened fields from Clay** (not nested payload)
- **Reconstructs** raw payload from flattened fields (coupling)
- **Hardcoded** signal registry lookup

#### Canonical Input Contract

```python
class JobChangeSignalInput(BaseModel):
    """Source-agnostic job change signal."""

    # Required identifier
    person_linkedin_url: str

    # Signal data
    previous_company: Optional[CompanyRef] = None  # Nested object
    new_company: Optional[CompanyRef] = None       # Nested object
    start_date: Optional[date] = None
    confidence_score: Optional[float] = None       # 0.0-1.0

    # Detection config
    lookback_days: int = 90

    # Metadata
    source: str = "unknown"
    detected_at: Optional[datetime] = None
    source_payload: Optional[dict] = None

class CompanyRef(BaseModel):
    """Reference to a company."""
    domain: Optional[str] = None
    linkedin_url: Optional[str] = None
    name: Optional[str] = None
```

#### Binding Rules

| Source | Field Mapping | Fallback |
|--------|---------------|----------|
| Clay webhook | `previous_company_linkedin_url` → `previous_company.linkedin_url` | None |
| Clay webhook | `new_company_domain` → `new_company.domain` | Extract from LinkedIn URL |
| Clay webhook | `new_company_linkedin_url` → `new_company.linkedin_url` | None |
| Clay webhook | `start_date_at_new_job` → `start_date` | Parse string to date |
| Clay webhook | `confidence` → `confidence_score` | Normalize 0-100 to 0.0-1.0 |
| Apollo | Different field names | Map accordingly |
| DB trigger | Query `extracted.person_experience` for changes | Compute diff |

#### Code Changes

**New file: `modal-functions/src/bindings/signals.py`**

```python
def bind_clay_job_change(payload: dict) -> JobChangeSignalInput:
    """Transform Clay job change webhook to canonical input."""

    # Parse confidence
    confidence = None
    if payload.get("confidence"):
        confidence = float(payload["confidence"]) / 100.0  # Clay uses 0-100

    # Parse start date
    start_date = None
    if payload.get("start_date_at_new_job"):
        start_date = parse_date(payload["start_date_at_new_job"])

    return JobChangeSignalInput(
        person_linkedin_url=normalize_linkedin_url(payload["person_linkedin_url"]),
        previous_company=CompanyRef(
            linkedin_url=payload.get("previous_company_linkedin_url"),
        ) if payload.get("previous_company_linkedin_url") else None,
        new_company=CompanyRef(
            domain=payload.get("new_company_domain"),
            linkedin_url=payload.get("new_company_linkedin_url"),
            name=payload.get("new_company_name"),
        ) if any([payload.get("new_company_domain"),
                  payload.get("new_company_linkedin_url")]) else None,
        start_date=start_date,
        confidence_score=confidence,
        lookback_days=payload.get("lookback_threshold_days", 90),
        source="clay",
        source_payload=payload,
    )
```

---

### 3. `infer_pricing_visibility` (Gemini Analysis)

**File:** `modal-functions/src/ingest/pricing_visibility.py`

#### Current Required Inputs

| Field | Type | Required | Source |
|-------|------|----------|--------|
| `domain` | str | Yes | Submission |
| `pricing_page_url` | str | Yes | Submission |
| `company_name` | str | No | Submission |

#### Current Source Dependencies

- **Hardcoded** Gemini model name
- **Hardcoded** HTML truncation (8000 chars)
- **Hardcoded** timeout (15s)

#### Canonical Input Contract

```python
class PricingAnalysisInput(BaseModel):
    """Source-agnostic pricing analysis input."""

    # Required
    domain: str
    pricing_page_url: str

    # Optional context
    company_name: Optional[str] = None

    # Config (with sensible defaults)
    model: str = "gemini-2.0-flash"
    max_content_length: int = 8000
    timeout_seconds: int = 15

    # Metadata
    source: str = "unknown"
    source_payload: Optional[dict] = None

class PricingAnalysisConfig(BaseModel):
    """Externalized config for pricing analysis."""
    model: str = "gemini-2.0-flash"
    max_content_length: int = 8000
    timeout_seconds: int = 15
    classification_prompt: str = DEFAULT_PRICING_PROMPT
```

#### Binding Rules

| Source | Field Mapping | Fallback |
|--------|---------------|----------|
| Clay webhook | `raw_payload.pricing_url` → `pricing_page_url` | Discover from domain |
| Direct API | Pass directly | None |
| Prior step | `output.discovered_pricing_url` → `pricing_page_url` | None |
| DB | Query `extracted.company_urls` for pricing URL | None |

#### Code Changes

```python
# Before (hardcoded)
model = genai.GenerativeModel("gemini-3-flash-preview")
response = model.generate_content(prompt, request_options={"timeout": 15})
truncated = page_content[:8000]

# After (configurable)
async def analyze_pricing(
    input: PricingAnalysisInput,
    config: PricingAnalysisConfig = PricingAnalysisConfig()
) -> PricingAnalysisResult:
    model = genai.GenerativeModel(config.model)
    truncated = page_content[:config.max_content_length]
    response = model.generate_content(
        prompt,
        request_options={"timeout": config.timeout_seconds}
    )
```

---

### 4. `lookup_company_icp` (Multi-Source Lookup)

**File:** `modal-functions/src/ingest/lookup_company_icp.py`

#### Current Required Inputs

| Field | Type | Required | Source |
|-------|------|----------|--------|
| `domain` | str | Yes | Submission |

#### Current Source Dependencies

- **Hardcoded** fallback order: `core.icp_criteria` → `extracted.*` tables
- **No binding layer** - directly queries DB

#### Canonical Input Contract

```python
class CompanyICPLookupInput(BaseModel):
    """Source-agnostic ICP lookup input."""

    # Identifier (at least one required)
    domain: Optional[str] = None
    linkedin_url: Optional[str] = None
    company_name: Optional[str] = None

    # Config
    include_customers: bool = True
    fallback_to_extracted: bool = True

    @root_validator
    def at_least_one_identifier(cls, values):
        if not any([values.get("domain"), values.get("linkedin_url"), values.get("company_name")]):
            raise ValueError("At least one identifier required")
        return values
```

#### Binding Rules

| Source | Field Mapping | Fallback |
|--------|---------------|----------|
| Direct API | `domain` passed directly | Resolve from `linkedin_url` or `company_name` |
| Prior step | `output.resolved_domain` | None |
| Clay | `raw_payload.Domain` → `domain` | None |

#### Code Changes

```python
# New resolver layer
async def resolve_domain(
    pool: asyncpg.Pool,
    input: CompanyICPLookupInput
) -> str:
    """Resolve domain from any identifier."""
    if input.domain:
        return input.domain

    if input.linkedin_url:
        row = await pool.fetchrow(
            "SELECT domain FROM core.companies WHERE linkedin_url = $1",
            input.linkedin_url
        )
        if row:
            return row["domain"]

    if input.company_name:
        row = await pool.fetchrow(
            "SELECT domain FROM extracted.cleaned_company_names WHERE cleaned_company_name ILIKE $1",
            input.company_name
        )
        if row:
            return row["domain"]

    raise ValueError(f"Could not resolve domain from input: {input}")
```

---

### 5. `ingest_icp_industries` (AI Enrichment)

**File:** `modal-functions/src/ingest/icp_industries.py`

#### Current Required Inputs

| Field | Type | Required | Source |
|-------|------|----------|--------|
| `company_name` | str | Yes | Submission |
| `domain` | str | Yes | Submission |
| `company_linkedin_url` | str | No | Submission |
| `raw_target_icp_industries_payload` | dict | Yes | Submission (AI output) |
| `workflow_slug` | str | No | Submission (default) |

#### Canonical Input Contract

```python
class ICPIndustriesInput(BaseModel):
    """Source-agnostic ICP industries input."""

    # Company identifiers
    domain: str
    company_name: Optional[str] = None
    linkedin_url: Optional[str] = None

    # Industries (flexible input)
    industries: Union[List[str], str, dict]  # Accept various formats

    # Config
    match_to_canonical: bool = True
    canonical_list_source: str = "reference.industries"

    # Metadata
    source: str = "unknown"
    source_payload: Optional[dict] = None
```

#### Binding Rules

| Source | Field Mapping | Fallback |
|--------|---------------|----------|
| Clay (Claygent) | `raw_payload.industries` (array) → `industries` | Parse from string |
| Clay (Claygent) | `raw_payload.target_industries` → `industries` | Try alternate field name |
| Direct API | `industries` passed directly | None |
| AI output | Parse JSON array | Split comma-separated string |

#### Code Changes

```python
def normalize_industries_input(raw: Union[List[str], str, dict]) -> List[str]:
    """Normalize various industry input formats to list."""
    if isinstance(raw, list):
        return [str(i).strip() for i in raw if i]

    if isinstance(raw, str):
        # Try JSON parse first
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(i).strip() for i in parsed if i]
        except json.JSONDecodeError:
            pass
        # Fall back to comma-separated
        return [i.strip() for i in raw.split(",") if i.strip()]

    if isinstance(raw, dict):
        # Look for common keys
        for key in ["industries", "target_industries", "industry_list"]:
            if key in raw:
                return normalize_industries_input(raw[key])

    return []
```

---

## Implementation Checklist

### Phase 1: Core Infrastructure

- [ ] **Create bindings module structure**
  - [ ] `modal-functions/src/bindings/__init__.py`
  - [ ] `modal-functions/src/bindings/base.py` - Base classes
  - [ ] `modal-functions/src/bindings/company.py` - Company data bindings
  - [ ] `modal-functions/src/bindings/person.py` - Person data bindings
  - [ ] `modal-functions/src/bindings/signals.py` - Signal event bindings
  - [ ] `modal-functions/src/bindings/icp.py` - ICP data bindings

- [ ] **Create canonical contracts module**
  - [ ] `modal-functions/src/contracts/__init__.py`
  - [ ] `modal-functions/src/contracts/company.py` - Company input/output models
  - [ ] `modal-functions/src/contracts/person.py` - Person input/output models
  - [ ] `modal-functions/src/contracts/signals.py` - Signal input/output models
  - [ ] `modal-functions/src/contracts/icp.py` - ICP input/output models
  - [ ] `modal-functions/src/contracts/common.py` - Shared models (CompanyRef, etc.)

- [ ] **Create config externalization**
  - [ ] `modal-functions/src/config/models.py` - AI model configs
  - [ ] `modal-functions/src/config/defaults.py` - Default values
  - [ ] Environment variable loading for overrides

### Phase 2: High-Priority Function Refactors

- [ ] **`ingest_clay_company_firmo`**
  - [ ] Create `CompanyFirmographicsInput` contract
  - [ ] Create `bind_clay_to_firmographics()` function
  - [ ] Refactor action to accept canonical input
  - [ ] Add tests for Clay binding
  - [ ] Add tests for direct API binding

- [ ] **`ingest_clay_signal_job_change`**
  - [ ] Create `JobChangeSignalInput` contract
  - [ ] Create `bind_clay_job_change()` function
  - [ ] Remove payload reconstruction logic
  - [ ] Refactor action to accept canonical input
  - [ ] Add tests

- [ ] **`infer_pricing_visibility`**
  - [ ] Create `PricingAnalysisInput` contract
  - [ ] Create `PricingAnalysisConfig` externalization
  - [ ] Remove hardcoded model/timeout/truncation
  - [ ] Add config parameter to action
  - [ ] Add tests

### Phase 3: Remaining Ingest Functions

- [ ] **`ingest_clay_find_companies`**
  - [ ] Create `CompanyDiscoveryInput` contract
  - [ ] Create binding layer
  - [ ] Refactor action

- [ ] **`ingest_all_comp_customers`**
  - [ ] Create `CompanyCustomersInput` contract
  - [ ] Normalize array explosion logic
  - [ ] Refactor action

- [ ] **`ingest_icp_*` family (5 functions)**
  - [ ] Create unified `ICPInput` contracts
  - [ ] Create bindings for each
  - [ ] Refactor actions

### Phase 4: Lookup Functions

- [ ] **`lookup_company_icp`**
  - [ ] Create `CompanyICPLookupInput` contract
  - [ ] Add domain resolver
  - [ ] Refactor action

- [ ] **`lookup_person_location`**
  - [ ] Create `LocationLookupInput` contract
  - [ ] Refactor action

- [ ] **`lookup_job_title`**
  - [ ] Create `JobTitleLookupInput` contract
  - [ ] Refactor action

### Phase 5: Signal Functions

- [ ] **`ingest_clay_signal_*` family**
  - [ ] Create signal-specific contracts
  - [ ] Create bindings
  - [ ] Refactor actions

### Phase 6: API Layer Updates

- [ ] **Update `hq-api/routers/run.py`**
  - [ ] Import binding functions
  - [ ] Detect source type (Clay vs direct)
  - [ ] Apply appropriate binding
  - [ ] Pass canonical input to Modal function

- [ ] **Add source detection middleware**
  - [ ] Check for Clay-specific headers/fields
  - [ ] Check for workflow_slug presence
  - [ ] Default to "api" source

### Phase 7: Testing & Documentation

- [ ] **Unit tests for bindings**
  - [ ] Test Clay → canonical transformation
  - [ ] Test API → canonical transformation
  - [ ] Test DB → canonical transformation
  - [ ] Test fallback resolution

- [ ] **Integration tests**
  - [ ] End-to-end Clay webhook processing
  - [ ] End-to-end direct API processing
  - [ ] End-to-end scheduled job processing

- [ ] **Documentation**
  - [ ] Update `docs/api/ENDPOINT_MAPPING.md` with new contracts
  - [ ] Create `docs/architecture/input-contracts.md`
  - [ ] Update function docstrings

---

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `modal-functions/src/bindings/__init__.py` | Create | Bindings module init |
| `modal-functions/src/bindings/base.py` | Create | Base binding classes |
| `modal-functions/src/bindings/company.py` | Create | Company data bindings |
| `modal-functions/src/bindings/person.py` | Create | Person data bindings |
| `modal-functions/src/bindings/signals.py` | Create | Signal event bindings |
| `modal-functions/src/bindings/icp.py` | Create | ICP data bindings |
| `modal-functions/src/contracts/__init__.py` | Create | Contracts module init |
| `modal-functions/src/contracts/company.py` | Create | Company input/output models |
| `modal-functions/src/contracts/person.py` | Create | Person input/output models |
| `modal-functions/src/contracts/signals.py` | Create | Signal input/output models |
| `modal-functions/src/contracts/icp.py` | Create | ICP input/output models |
| `modal-functions/src/contracts/common.py` | Create | Shared models |
| `modal-functions/src/config/models.py` | Create | AI model configs |
| `modal-functions/src/config/defaults.py` | Create | Default config values |
| `modal-functions/src/ingest/company.py` | Modify | Use canonical inputs |
| `modal-functions/src/ingest/signal_job_change.py` | Modify | Use canonical inputs |
| `modal-functions/src/ingest/pricing_visibility.py` | Modify | Use config + canonical |
| `modal-functions/src/ingest/lookup_company_icp.py` | Modify | Add resolver layer |
| `modal-functions/src/ingest/icp_industries.py` | Modify | Use canonical inputs |
| `hq-api/routers/run.py` | Modify | Add binding layer |

---

## Migration Strategy

1. **Additive approach** - Create new modules alongside existing code
2. **Feature flag** - Add `use_canonical_inputs=True` parameter to test
3. **Gradual rollout** - Migrate one function category at a time
4. **Backward compatible** - Old API signatures continue to work via auto-binding
5. **Parallel testing** - Run both paths, compare outputs

---

*Created: 2026-02-16*
