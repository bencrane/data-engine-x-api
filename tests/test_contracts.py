from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.company_ads import GoogleAdsOutput, LinkedInAdsOutput, MetaAdsOutput
from app.contracts.company_enrich import CompanyEnrichProfileOutput
from app.contracts.company_research import ResolveG2UrlOutput, ResolvePricingPageUrlOutput
from app.contracts.person_contact import (
    ResolveEmailOutput,
    ResolveMobilePhoneOutput,
    VerifyEmailOutput,
)
from app.contracts.person_enrich import PersonEnrichProfileOutput
from app.contracts.search import CompanySearchOutput, PersonSearchOutput


CONTRACT_CASES = [
    (
        ResolveEmailOutput,
        {"email": "alex@example.com", "source_provider": "leadmagic", "verification": None},
        {"email": "alex@example.com", "verification": None},
    ),
    (
        VerifyEmailOutput,
        {"email": "alex@example.com", "verification": {"provider": "mv", "status": "valid", "inconclusive": False, "raw_response": {}}},
        {"verification": None},
    ),
    (
        ResolveMobilePhoneOutput,
        {"mobile_phone": "+15551234567", "source_provider": "leadmagic"},
        {"mobile_phone": "+15551234567"},
    ),
    (
        PersonEnrichProfileOutput,
        {
            "full_name": "Alex Smith",
            "first_name": "Alex",
            "last_name": "Smith",
            "linkedin_url": "https://linkedin.com/in/alexsmith",
            "headline": "VP of Sales",
            "current_title": "VP of Sales",
            "work_history": [{"title": "VP of Sales", "current": True}],
            "education": [{"institution_name": "Stanford University"}],
            "skills": ["Sales", "Leadership"],
            "source_provider": "prospeo",
        },
        {
            "full_name": "Alex Smith",
            "skills": ["Sales"],
        },
    ),
    (
        CompanySearchOutput,
        {
            "results": [
                {
                    "company_name": "Acme",
                    "company_domain": "acme.com",
                    "company_website": "https://acme.com",
                    "company_linkedin_url": "https://linkedin.com/company/acme",
                    "industry_primary": "SaaS",
                    "employee_range": "51-200",
                    "founded_year": 2018,
                    "hq_country_code": "US",
                    "source_company_id": "cmp_1",
                    "source_provider": "prospeo",
                    "raw": {},
                }
            ],
            "result_count": 1,
            "provider_order_used": ["prospeo"],
            "pagination": {"page": 1},
        },
        {
            "results": [],
            "provider_order_used": ["prospeo"],
            "pagination": {"page": 1},
        },
    ),
    (
        PersonSearchOutput,
        {
            "results": [
                {
                    "full_name": "Alex Smith",
                    "first_name": "Alex",
                    "last_name": "Smith",
                    "linkedin_url": "https://linkedin.com/in/alex",
                    "headline": "Head of Growth",
                    "current_title": "Head of Growth",
                    "current_company_name": "Acme",
                    "current_company_domain": "acme.com",
                    "location_name": "Austin",
                    "country_code": "US",
                    "source_person_id": "prs_1",
                    "source_provider": "prospeo",
                    "raw": {},
                }
            ],
            "result_count": 1,
            "provider_order_used": ["prospeo"],
            "pagination": {"page": 1},
        },
        {
            "results": [],
            "provider_order_used": ["prospeo"],
            "pagination": {"page": 1},
        },
    ),
    (
        CompanyEnrichProfileOutput,
        {
            "company_profile": {
                "company_name": "Acme",
                "company_domain": "acme.com",
            },
            "source_providers": ["prospeo", "blitzapi"],
        },
        {"company_profile": {"company_name": "Acme"}},
    ),
    (
        ResolveG2UrlOutput,
        {
            "company_name": "Acme",
            "company_domain": "acme.com",
            "g2_url": "https://g2.com/products/acme",
            "confidence": 0.95,
            "provider_used": "parallel",
        },
        {
            "company_domain": "acme.com",
            "g2_url": "https://g2.com/products/acme",
            "confidence": 0.95,
            "provider_used": "parallel",
        },
    ),
    (
        ResolvePricingPageUrlOutput,
        {
            "company_name": "Acme",
            "company_domain": "acme.com",
            "pricing_page_url": "https://acme.com/pricing",
            "confidence": 0.85,
            "provider_used": "parallel",
        },
        {
            "company_domain": "acme.com",
            "pricing_page_url": "https://acme.com/pricing",
            "confidence": 0.85,
            "provider_used": "parallel",
        },
    ),
    (
        LinkedInAdsOutput,
        {"ads": [{"id": "ad_1"}], "ads_count": 1},
        {"ads_count": 1},
    ),
    (
        MetaAdsOutput,
        {"results": [{"id": "ad_1"}], "results_count": 1, "endpoint_used": "meta-search-v2"},
        {"results": [{"id": "ad_1"}], "results_count": 1},
    ),
    (
        GoogleAdsOutput,
        {"ads": [{"id": "ad_1"}], "ads_count": 1},
        {"ads": [{"id": "ad_1"}]},
    ),
]


@pytest.mark.parametrize(("schema", "valid_payload", "invalid_payload"), CONTRACT_CASES)
def test_contracts_accept_valid_payloads(schema, valid_payload, invalid_payload):
    model = schema.model_validate(valid_payload)
    assert model is not None


@pytest.mark.parametrize(("schema", "valid_payload", "invalid_payload"), CONTRACT_CASES)
def test_contracts_reject_invalid_payloads(schema, valid_payload, invalid_payload):
    with pytest.raises(ValidationError):
        schema.model_validate(invalid_payload)
