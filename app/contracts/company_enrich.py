from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CompanyProfileOutput(BaseModel):
    company_name: str | None = None
    company_domain: str | None = None
    company_website: str | None = None
    company_linkedin_url: str | None = None
    company_linkedin_id: str | None = None
    company_type: str | None = None
    industry_primary: str | None = None
    industry_derived: list[Any] | str | None = None
    employee_count: int | str | None = None
    employee_range: str | None = None
    founded_year: int | None = None
    hq_locality: str | None = None
    hq_country_code: str | None = None
    description_raw: str | None = None
    specialties: list[Any] | str | None = None
    annual_revenue_range: str | None = None
    follower_count: int | str | None = None
    logo_url: str | None = None
    source_company_id: str | int | None = None


class CompanyEnrichProfileOutput(BaseModel):
    company_profile: CompanyProfileOutput | None
    source_providers: list[str]


class BulkCompanyEnrichItem(BaseModel):
    identifier: str
    company_profile: CompanyProfileOutput | None


class BulkCompanyEnrichOutput(BaseModel):
    matched: list[BulkCompanyEnrichItem]
    not_matched: list[str]
    invalid_datapoints: list[str]
    total_submitted: int
    total_matched: int
    total_cost: int | None = None
    source_provider: str = "prospeo"


class BulkProfileEnrichItem(BaseModel):
    identifier: str
    status: str
    company_profile: CompanyProfileOutput | None = None
    source_providers: list[str] = []


class BulkProfileEnrichOutput(BaseModel):
    results: list[BulkProfileEnrichItem]
    total_submitted: int
    total_found: int
    total_not_found: int
    total_failed: int


class BlitzAPICompanyEnrichOutput(BaseModel):
    company_name: str | None = None
    company_domain: str | None = None
    company_website: str | None = None
    company_linkedin_url: str | None = None
    company_linkedin_id: str | None = None
    company_type: str | None = None
    industry_primary: str | None = None
    employee_count: int | str | None = None
    employee_range: str | None = None
    founded_year: int | None = None
    hq_locality: str | None = None
    hq_country_code: str | None = None
    description_raw: str | None = None
    specialties: list[Any] | str | None = None
    follower_count: int | str | None = None
    source_provider: str = "blitzapi"


class TechnologyItem(BaseModel):
    name: str
    category: str | None = None
    website: str | None = None
    icon: str | None = None


class TechnographicsOutput(BaseModel):
    technologies: list[TechnologyItem]
    categories: dict[str, list[str]] | None = None
    technology_count: int
    source_provider: str = "leadmagic"


class EcommerceAppItem(BaseModel):
    name: str
    categories: list[str] | None = None
    monthly_cost: str | None = None


class EcommerceTechItem(BaseModel):
    name: str
    description: str | None = None


class EcommerceContactItem(BaseModel):
    type: str
    value: str
    source: str | None = None


class EcommerceEnrichOutput(BaseModel):
    merchant_name: str | None = None
    ecommerce_platform: str | None = None
    ecommerce_plan: str | None = None
    estimated_monthly_sales_cents: int | None = None
    employee_count: int | None = None
    product_count: int | None = None
    global_rank: int | None = None
    platform_rank: int | None = None
    monthly_app_spend_cents: int | None = None
    installed_apps: list[EcommerceAppItem] | None = None
    technologies: list[EcommerceTechItem] | None = None
    contact_info: list[EcommerceContactItem] | None = None
    country_code: str | None = None
    city: str | None = None
    domain_state: str | None = None
    description: str | None = None
    store_created_at: str | None = None
    shipping_carriers: list[str] | None = None
    sales_carriers: list[str] | None = None
    features: list[str] | None = None
    source_provider: str = "storeleads"


class CardRevenueTimeSeriesPoint(BaseModel):
    period_start: str
    value: float | None = None


class CardRevenueOutput(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    location_count: int | None = None
    annual_card_revenue: float | None = None
    annual_card_revenue_yoy_growth: float | None = None
    annual_avg_daily_customers: float | None = None
    annual_transaction_count: float | None = None
    annual_avg_transaction_size: float | None = None
    annual_refunds: float | None = None
    monthly_revenue: list[CardRevenueTimeSeriesPoint] | None = None
    monthly_revenue_growth: list[CardRevenueTimeSeriesPoint] | None = None
    monthly_avg_daily_customers: list[CardRevenueTimeSeriesPoint] | None = None
    monthly_transactions: list[CardRevenueTimeSeriesPoint] | None = None
    monthly_avg_transaction_size: list[CardRevenueTimeSeriesPoint] | None = None
    monthly_refunds: list[CardRevenueTimeSeriesPoint] | None = None
    source_provider: str = "enigma"


class EnigmaLocationItem(BaseModel):
    enigma_location_id: str | None = None
    location_name: str | None = None
    full_address: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    operating_status: str | None = None


class EnigmaLocationsOutput(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    total_location_count: int | None = None
    locations: list[EnigmaLocationItem] | None = None
    location_count: int | None = None
    open_count: int | None = None
    closed_count: int | None = None
    has_next_page: bool | None = None
    end_cursor: str | None = None
    source_provider: str = "enigma"


class EnigmaBrandItem(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    website: str | None = None
    location_count: int | None = None
    industries: list[str] | None = None


class EnigmaDiscoveryLocationItem(BaseModel):
    enigma_location_id: str | None = None
    location_name: str | None = None
    full_address: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    operating_status: str | None = None
    website: str | None = None
    phone: str | None = None
    parent_brand_id: str | None = None
    parent_brand_name: str | None = None


class EnigmaBrandDiscoveryOutput(BaseModel):
    brands: list[EnigmaBrandItem] | None = None
    locations: list[EnigmaDiscoveryLocationItem] | None = None
    entity_type: str | None = None
    total_returned: int | None = None
    has_next_page: bool | None = None
    next_page_token: str | None = None
    prompt: str | None = None
    geography_filter: str | None = None
    source_provider: str = "enigma"


class EnigmaContactItem(BaseModel):
    full_name: str | None = None
    job_title: str | None = None
    job_function: str | None = None
    management_level: str | None = None
    email: str | None = None
    phone: str | None = None


class EnigmaLocationEnrichedItem(EnigmaLocationItem):
    phone: str | None = None
    website: str | None = None
    annual_card_revenue: float | None = None
    annual_card_revenue_yoy_growth: float | None = None
    annual_avg_daily_customers: float | None = None
    annual_transaction_count: float | None = None
    competitive_rank: int | None = None
    competitive_rank_total: int | None = None
    review_count: int | None = None
    review_avg_rating: float | None = None
    contacts: list[EnigmaContactItem] | None = None


class EnigmaLocationsEnrichedOutput(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    total_location_count: int | None = None
    locations: list[EnigmaLocationEnrichedItem] | None = None
    location_count: int | None = None
    open_count: int | None = None
    closed_count: int | None = None
    has_next_page: bool | None = None
    end_cursor: str | None = None
    source_provider: str = "enigma"


class FMCSABasicScore(BaseModel):
    category: str
    percentile: float | None = None
    violation_count: int | None = None
    serious_violation_count: int | None = None
    deficiency: bool | None = None


class FMCSACarrierEnrichOutput(BaseModel):
    dot_number: str
    legal_name: str | None = None
    dba_name: str | None = None
    allow_to_operate: bool | None = None
    out_of_service: bool | None = None
    out_of_service_date: str | None = None
    total_drivers: int | None = None
    total_power_units: int | None = None
    bus_vehicles: int | None = None
    van_vehicles: int | None = None
    passenger_vehicles: int | None = None
    address_street: str | None = None
    address_city: str | None = None
    address_state: str | None = None
    address_zip: str | None = None
    phone: str | None = None
    complaint_count: int | None = None
    basic_scores: list[FMCSABasicScore] | None = None
    authority_status: str | None = None
    authority_grant_date: str | None = None
    source_provider: str = "fmcsa"


# ---------------------------------------------------------------------------
# Enigma additional operation contracts
# ---------------------------------------------------------------------------


class EnigmaAggregateOutput(BaseModel):
    brands_count: int | None = None
    locations_count: int | None = None
    legal_entities_count: int | None = None
    geography_state: str | None = None
    geography_city: str | None = None
    operating_status_filter: str | None = None
    source_provider: str = "enigma"


class EnigmaRegistrationItem(BaseModel):
    enigma_registration_id: str | None = None
    registration_type: str | None = None
    registration_state: str | None = None
    jurisdiction_type: str | None = None
    registered_name: str | None = None
    file_number: str | None = None
    issue_date: str | None = None
    status: str | None = None
    sub_status: str | None = None


class EnigmaRegisteredEntityItem(BaseModel):
    enigma_registered_entity_id: str | None = None
    name: str | None = None
    registered_entity_type: str | None = None
    formation_date: str | None = None
    formation_year: int | None = None
    registrations: list[EnigmaRegistrationItem] | None = None


class EnigmaLegalEntityPersonItem(BaseModel):
    enigma_person_id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    date_of_birth: str | None = None


class EnigmaLegalEntityItem(BaseModel):
    enigma_legal_entity_id: str | None = None
    legal_entity_name: str | None = None
    legal_entity_type: str | None = None
    registered_entities: list[EnigmaRegisteredEntityItem] | None = None
    persons: list[EnigmaLegalEntityPersonItem] | None = None


class EnigmaLegalEntitiesOutput(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    legal_entities: list[EnigmaLegalEntityItem] | None = None
    legal_entity_count: int | None = None
    source_provider: str = "enigma"


class EnigmaDeliverabilityItem(BaseModel):
    enigma_location_id: str | None = None
    location_name: str | None = None
    full_address: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    operating_status: str | None = None
    rdi: str | None = None
    delivery_type: str | None = None
    deliverable: str | None = None
    virtual: str | None = None


class EnigmaAddressDeliverabilityOutput(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    total_location_count: int | None = None
    locations: list[EnigmaDeliverabilityItem] | None = None
    location_count: int | None = None
    deliverable_count: int | None = None
    vacant_count: int | None = None
    not_deliverable_count: int | None = None
    virtual_count: int | None = None
    source_provider: str = "enigma"


class EnigmaTechnologyItem(BaseModel):
    technology: str | None = None
    category: str | None = None
    first_observed_date: str | None = None
    last_observed_date: str | None = None


class EnigmaLocationTechnologyItem(BaseModel):
    enigma_location_id: str | None = None
    location_name: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    operating_status: str | None = None
    technologies: list[EnigmaTechnologyItem] | None = None


class EnigmaTechnologiesOutput(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    total_location_count: int | None = None
    locations: list[EnigmaLocationTechnologyItem] | None = None
    location_count: int | None = None
    locations_with_technology_count: int | None = None
    technology_summary: dict[str, int] | None = None
    source_provider: str = "enigma"


class EnigmaPersonBrandResult(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    website: str | None = None
    location_count: int | None = None
    industries: list[str] | None = None


class EnigmaPersonLocationResult(BaseModel):
    enigma_location_id: str | None = None
    location_name: str | None = None
    full_address: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    operating_status: str | None = None
    website: str | None = None
    phone: str | None = None
    parent_brand_id: str | None = None
    parent_brand_name: str | None = None


class EnigmaPersonLegalEntityResult(BaseModel):
    enigma_legal_entity_id: str | None = None
    legal_entity_name: str | None = None
    legal_entity_type: str | None = None


class EnigmaPersonSearchOutput(BaseModel):
    brands: list[EnigmaPersonBrandResult] | None = None
    operating_locations: list[EnigmaPersonLocationResult] | None = None
    legal_entities: list[EnigmaPersonLegalEntityResult] | None = None
    total_returned: int | None = None
    source_provider: str = "enigma"


class EnigmaIndustryItem(BaseModel):
    industry_desc: str | None = None
    industry_code: str | None = None
    industry_type: str | None = None


class EnigmaIndustriesOutput(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    industries: list[EnigmaIndustryItem] | None = None
    industry_count: int | None = None
    naics_codes: list[str] | None = None
    sic_codes: list[str] | None = None
    source_provider: str = "enigma"


# --- Enigma affiliated brands ---

class EnigmaAffiliatedBrandItem(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    website: str | None = None
    location_count: int | None = None
    affiliation_type: str | None = None
    rank: int | None = None
    first_observed_date: str | None = None


class EnigmaAffiliatedBrandsOutput(BaseModel):
    enigma_brand_id: str | None = None
    affiliated_brand_count: int | None = None
    affiliated_brands: list[EnigmaAffiliatedBrandItem] | None = None
    source_provider: str = "enigma"


# --- Enigma marketability ---

class EnigmaMarketabilityOutput(BaseModel):
    enigma_brand_id: str | None = None
    is_marketable: bool | None = None
    first_observed_date: str | None = None
    last_observed_date: str | None = None
    source_provider: str = "enigma"


# --- Enigma activity flags ---

class EnigmaActivityFlagItem(BaseModel):
    activity_type: str | None = None
    first_observed_date: str | None = None
    last_observed_date: str | None = None


class EnigmaActivityFlagsOutput(BaseModel):
    enigma_brand_id: str | None = None
    activity_count: int | None = None
    activity_flags: list[EnigmaActivityFlagItem] | None = None
    has_flags: bool | None = None
    activity_types: list[str] | None = None
    source_provider: str = "enigma"


# --- Enigma bankruptcy ---

class EnigmaBankruptcyRecord(BaseModel):
    case_number: str | None = None
    chapter_type: str | None = None
    petition: str | None = None
    debtor_name: str | None = None
    filing_date: str | None = None
    entry_date: str | None = None
    date_terminated: str | None = None
    debtor_discharged_date: str | None = None
    plan_confirmed_date: str | None = None
    judge: str | None = None
    trustee: str | None = None
    first_observed_date: str | None = None
    last_observed_date: str | None = None


class EnigmaBankruptcyLegalEntityItem(BaseModel):
    enigma_legal_entity_id: str | None = None
    legal_entity_name: str | None = None
    legal_entity_type: str | None = None
    bankruptcy_count: int | None = None
    bankruptcies: list[EnigmaBankruptcyRecord] | None = None


class EnigmaBankruptcyOutput(BaseModel):
    enigma_brand_id: str | None = None
    legal_entity_count: int | None = None
    total_bankruptcy_count: int | None = None
    has_active_bankruptcy: bool | None = None
    legal_entities_with_bankruptcies: list[EnigmaBankruptcyLegalEntityItem] | None = None
    source_provider: str = "enigma"


# --- Enigma watchlist ---

class EnigmaWatchlistEntry(BaseModel):
    watchlist_name: str | None = None
    connection_type: str | None = None  # "is_flagged_by" or "appears_on"
    first_observed_date: str | None = None
    last_observed_date: str | None = None


class EnigmaWatchlistLegalEntityItem(BaseModel):
    enigma_legal_entity_id: str | None = None
    legal_entity_name: str | None = None
    legal_entity_type: str | None = None
    watchlist_hit_count: int | None = None
    watchlist_entries: list[EnigmaWatchlistEntry] | None = None


class EnigmaWatchlistOutput(BaseModel):
    enigma_brand_id: str | None = None
    legal_entity_count: int | None = None
    total_watchlist_hit_count: int | None = None
    has_watchlist_hits: bool | None = None
    legal_entities_with_hits: list[EnigmaWatchlistLegalEntityItem] | None = None
    source_provider: str = "enigma"


# --- Enigma brand roles ---

class EnigmaRoleItem(BaseModel):
    job_title: str | None = None
    job_function: str | None = None
    management_level: str | None = None
    phone_numbers: list[str] | None = None
    email_addresses: list[str] | None = None
    linkedin_url: str | None = None
    first_observed_date: str | None = None
    last_observed_date: str | None = None


class EnigmaLocationRolesItem(BaseModel):
    enigma_location_id: str | None = None
    location_name: str | None = None
    full_address: str | None = None
    city: str | None = None
    state: str | None = None
    operating_status: str | None = None
    role_count: int | None = None
    roles: list[EnigmaRoleItem] | None = None


class EnigmaBrandRolesOutput(BaseModel):
    enigma_brand_id: str | None = None
    location_count: int | None = None
    total_role_count: int | None = None
    locations: list[EnigmaLocationRolesItem] | None = None
    source_provider: str = "enigma"


# --- Enigma officer persons ---

class EnigmaOfficerPersonItem(BaseModel):
    enigma_person_id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    date_of_birth: str | None = None


class EnigmaOfficerRoleItem(BaseModel):
    job_title: str | None = None
    job_function: str | None = None
    management_level: str | None = None


class EnigmaOfficerLegalEntityItem(BaseModel):
    enigma_legal_entity_id: str | None = None
    legal_entity_name: str | None = None
    legal_entity_type: str | None = None
    registered_entity_name: str | None = None
    registered_entity_type: str | None = None
    formation_date: str | None = None
    person_count: int | None = None
    persons: list[EnigmaOfficerPersonItem] | None = None
    officer_roles: list[EnigmaOfficerRoleItem] | None = None


class EnigmaOfficerPersonsOutput(BaseModel):
    enigma_brand_id: str | None = None
    legal_entity_count: int | None = None
    total_person_count: int | None = None
    legal_entities: list[EnigmaOfficerLegalEntityItem] | None = None
    source_provider: str = "enigma"


# --- Enigma KYB verification ---

class EnigmaKYBOutput(BaseModel):
    business_name_queried: str | None = None
    enigma_brand_id: str | None = None
    enigma_registered_entity_id: str | None = None
    name_verification: str | None = None
    sos_name_verification: str | None = None
    address_verification: str | None = None
    person_verification: str | None = None
    domestic_registration: str | None = None
    name_match: bool | None = None
    address_match: bool | None = None
    person_match: bool | None = None
    domestic_active: bool | None = None
    registered_entity_count: int | None = None
    brand_count: int | None = None
    raw_tasks: dict[str, Any] | None = None
    source_provider: str = "enigma"
